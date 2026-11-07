# Maintainer-only current-host acceptance. Never a clean Windows certification.
param(
    [Parameter(Mandatory=$true)][string]$Installer,
    [Parameter(Mandatory=$true)][string]$WorkDirectory
)
$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path $PSScriptRoot -Parent
$work = [IO.Path]::GetFullPath($WorkDirectory)
$allowed = [IO.Path]::GetFullPath((Join-Path $repositoryRoot 'dist')) + [IO.Path]::DirectorySeparatorChar
if (-not $work.StartsWith($allowed, [StringComparison]::OrdinalIgnoreCase)) { throw 'Use a new dist/ acceptance directory' }
if (Test-Path -LiteralPath $work) { throw 'Acceptance directory must not exist' }
$uninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{22D5F89B-1F42-4D31-9A95-11752830ECF0}_is1'
if (Test-Path $uninstallKey) { throw 'An existing product installation is registered; do not overwrite it during acceptance' }
$desktopShortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) '抗体科研工作台（候选版）.lnk'
if (Test-Path -LiteralPath $desktopShortcut) { throw 'Existing desktop shortcut must be preserved' }
New-Item -ItemType Directory -Path $work | Out-Null
$env:TEMP = (New-Item -ItemType Directory (Join-Path $work 'temp')).FullName
$env:TMP = $env:TEMP
$env:LOCALAPPDATA = Join-Path $work 'local'
$env:APPDATA = Join-Path $work 'roaming'
$env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
$env:QT_QPA_PLATFORM = 'offscreen'
$installDirectory = Join-Path $work 'installed'
$groupName = 'Antibody Research Workbench'
$groupDirectory = Join-Path ([Environment]::GetFolderPath('Programs')) $groupName
if (Test-Path -LiteralPath $groupDirectory) { throw 'Existing acceptance shortcut group must be preserved' }
$arguments = @('/SP-','/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CURRENTUSER',
    ('/DIR="' + $installDirectory + '"'),('/GROUP="' + $groupName + '"'),'/TASKS=desktopicon')
$installProcess = Start-Process -FilePath ([IO.Path]::GetFullPath($Installer)) -ArgumentList ($arguments + ('/LOG="' + (Join-Path $work 'install.log') + '"')) -Wait -PassThru -WindowStyle Hidden
if ($installProcess.ExitCode -ne 0) { throw "Install failed: $($installProcess.ExitCode)" }
$executable = Join-Path $installDirectory 'AntibodyResearchWorkbench.exe'
if (-not (Test-Path -LiteralPath $executable)) { throw 'Installed executable missing' }
$startShortcut = Join-Path $groupDirectory '抗体科研工作台（候选版）.lnk'
if (-not (Test-Path -LiteralPath $startShortcut) -or -not (Test-Path -LiteralPath $desktopShortcut)) { throw 'Shortcuts missing' }
$shell = New-Object -ComObject WScript.Shell
$shortcutTarget = $shell.CreateShortcut($startShortcut).TargetPath
Copy-Item -LiteralPath $startShortcut -Destination (Join-Path $work 'start-menu.lnk')
Copy-Item -LiteralPath $desktopShortcut -Destination (Join-Path $work 'desktop.lnk')
# The WSH automation getter may return empty for a Shell-created link. Read
# the same link through the documented ShellLinkObject.Path API as well.
$shellApplication = New-Object -ComObject Shell.Application
$shellFolder = $shellApplication.NameSpace([IO.Path]::GetDirectoryName($startShortcut))
$shellTarget = $shellFolder.ParseName([IO.Path]::GetFileName($startShortcut)).GetLink.Path
$shortcutDiagnostic = @{shortcut=$startShortcut; wscript_target=$shortcutTarget; shell_target=$shellTarget; expected_target=$executable}
$shortcutDiagnostic | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $work 'shortcut-diagnostic.json') -Encoding UTF8
if ([string]::IsNullOrEmpty($shortcutTarget)) { $shortcutTarget = $shellTarget }
if ($shortcutTarget -ne $executable) { throw ('Shortcut points to wrong executable: ' + ($shortcutDiagnostic | ConvertTo-Json -Compress)) }
$smokeProcess = Start-Process -FilePath $executable -ArgumentList '--installation-smoke' -Wait -PassThru -WindowStyle Hidden -RedirectStandardError (Join-Path $work 'smoke-stderr.txt')
if ($smokeProcess.ExitCode -ne 0) { throw "Installed executable smoke failed: $($smokeProcess.ExitCode)" }
$smoke = Get-Content -LiteralPath (Join-Path $env:LOCALAPPDATA 'AntibodyResearchWorkbench/installation-smoke.json') -Raw | ConvertFrom-Json
if ($smoke.status -ne 'PASS') { throw 'Smoke report missing PASS' }
$reinstallProcess = Start-Process -FilePath ([IO.Path]::GetFullPath($Installer)) -ArgumentList ($arguments + ('/LOG="' + (Join-Path $work 'reinstall.log') + '"')) -Wait -PassThru -WindowStyle Hidden
if ($reinstallProcess.ExitCode -ne 0) { throw 'Same-version reinstall failed' }
$sentinelDirectory = New-Item -ItemType Directory -Force (Join-Path $env:APPDATA 'AntibodyAI')
$sentinel = Join-Path $sentinelDirectory.FullName 'acceptance-preserve.txt'
Set-Content -LiteralPath $sentinel -Value 'synthetic acceptance data'
$uninstallProcess = Start-Process -FilePath (Join-Path $installDirectory 'unins000.exe') -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',('/LOG="' + (Join-Path $work 'uninstall.log') + '"')) -Wait -PassThru -WindowStyle Hidden
if ($uninstallProcess.ExitCode -ne 0) { throw 'Uninstall failed' }
if (Test-Path -LiteralPath $executable) { throw 'Executable remains after uninstall' }
if ((Test-Path -LiteralPath $desktopShortcut) -or (Test-Path -LiteralPath $startShortcut)) { throw 'Shortcut remains after uninstall' }
if (-not (Test-Path -LiteralPath $sentinel)) { throw 'Uninstaller removed user data' }
if (Test-Path $uninstallKey) { throw 'Uninstall registration remains' }
$report = @{
    status='PASS'; scope='Current Windows development host, silent install + offscreen exe smoke'
    clean_windows_qualified=$false; external_python_on_path=$false
    install='PASS'; start_menu_shortcut='PASS'; optional_desktop_shortcut='PASS'
    installed_smoke=$smoke; same_version_reinstall='PASS'; real_cross_version_upgrade='NOT_TESTED'
    uninstall='PASS'; user_data_preserved='PASS'; gui_wizard_click_acceptance='NOT_TESTED'
}
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $work 'acceptance.json') -Encoding UTF8
$report | ConvertTo-Json -Depth 8
