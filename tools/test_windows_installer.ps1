# Maintainer-only current-host acceptance. Never a clean Windows certification.
param(
    [Parameter(Mandatory=$true)][string]$Installer,
    [Parameter(Mandatory=$true)][string]$WorkDirectory
)

function Assert-InstallerShortcut {
    param([string]$Shortcut, [string]$ExpectedTarget, [string]$DiagnosticPath)
    if (-not (Test-Path -LiteralPath $Shortcut)) { throw 'Shortcut missing' }
    $shell = New-Object -ComObject WScript.Shell
    $wscriptTarget = $shell.CreateShortcut($Shortcut).TargetPath
    # WSH may return empty for a Shell-created link. Read the same link with
    # ShellLinkObject too; do not accept conflicting nonempty targets.
    $shellApplication = New-Object -ComObject Shell.Application
    $folder = $shellApplication.NameSpace([IO.Path]::GetDirectoryName($Shortcut))
    $shellTarget = $folder.ParseName([IO.Path]::GetFileName($Shortcut)).GetLink.Path
    $target = $wscriptTarget
    if ([string]::IsNullOrEmpty($target)) { $target = $shellTarget }
    $diagnostic = @{shortcut=$Shortcut; wscript_target=$wscriptTarget; shell_target=$shellTarget; expected_target=$ExpectedTarget}
    $diagnostic | ConvertTo-Json | Set-Content -LiteralPath $DiagnosticPath -Encoding UTF8
    if ($target -ne $ExpectedTarget -or
        (-not [string]::IsNullOrEmpty($shellTarget) -and $shellTarget -ne $ExpectedTarget)) {
        throw ('Shortcut points to wrong executable: ' + ($diagnostic | ConvertTo-Json -Compress))
    }
}

function Assert-InstallationSmokeReport {
    param($Report, [string]$ExpectedExecutable, [int]$ExpectedPid)
    if ($Report.status -ne 'PASS' -or $Report.pages -ne 8 -or
        $Report.frozen -ne $true -or $Report.phase -ne 'basic' -or
        $Report.source_mode -ne $false -or $Report.network_attempts -ne 0 -or
        $Report.trained -ne $false -or $Report.provider_called -ne $false -or
        $Report.model_loaded -ne $false -or $Report.pid -ne $ExpectedPid -or
        $Report.executable -ne $ExpectedExecutable) {
        throw 'Installed frozen basic smoke contract failed'
    }
}

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path $PSScriptRoot -Parent
$work = [IO.Path]::GetFullPath($WorkDirectory)
$allowed = [IO.Path]::GetFullPath((Join-Path $repositoryRoot 'dist')) + [IO.Path]::DirectorySeparatorChar
if (-not $work.StartsWith($allowed, [StringComparison]::OrdinalIgnoreCase)) { throw 'Use a new dist/ acceptance directory' }
if (Test-Path -LiteralPath $work) { throw 'Acceptance directory must not exist' }
$uninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{22D5F89B-1F42-4D31-9A95-11752830ECF0}_is1'
if (Test-Path $uninstallKey) { throw 'An existing product installation is registered; do not overwrite it during acceptance' }
$groupName = 'BioResearch Workbench'
$groupDirectory = Join-Path ([Environment]::GetFolderPath('Programs')) $groupName
$startShortcut = Join-Path $groupDirectory '生物科研决策支持工作台（候选版）.lnk'
$uninstallShortcut = Join-Path $groupDirectory '卸载生物科研决策支持工作台.lnk'
$desktopShortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) '生物科研决策支持工作台（候选版）.lnk'
if (Test-Path -LiteralPath $desktopShortcut) { throw 'Existing desktop shortcut must be preserved' }
if (Test-Path -LiteralPath $groupDirectory) { throw 'Existing acceptance shortcut group must be preserved' }
New-Item -ItemType Directory -Path $work | Out-Null
$env:TEMP = (New-Item -ItemType Directory (Join-Path $work 'temp')).FullName
$env:TMP = $env:TEMP
$env:LOCALAPPDATA = Join-Path $work 'local'
$env:APPDATA = Join-Path $work 'roaming'
$env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
$env:QT_QPA_PLATFORM = 'offscreen'
$installDirectory = Join-Path $work 'installed'
$arguments = @('/SP-','/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CURRENTUSER',
    ('/DIR="' + $installDirectory + '"'),('/GROUP="' + $groupName + '"'),'/TASKS=desktopicon')
$installProcess = Start-Process -FilePath ([IO.Path]::GetFullPath($Installer)) -ArgumentList ($arguments + ('/LOG="' + (Join-Path $work 'install.log') + '"')) -Wait -PassThru -WindowStyle Hidden
if ($installProcess.ExitCode -ne 0) { throw "Install failed: $($installProcess.ExitCode)" }
$executable = Join-Path $installDirectory 'AntibodyResearchWorkbench.exe'
if (-not (Test-Path -LiteralPath $executable)) { throw 'Installed executable missing' }
Assert-InstallerShortcut -Shortcut $startShortcut -ExpectedTarget $executable -DiagnosticPath (Join-Path $work 'start-menu-diagnostic.json')
Assert-InstallerShortcut -Shortcut $desktopShortcut -ExpectedTarget $executable -DiagnosticPath (Join-Path $work 'desktop-diagnostic.json')
Assert-InstallerShortcut -Shortcut $uninstallShortcut -ExpectedTarget (Join-Path $installDirectory 'unins000.exe') -DiagnosticPath (Join-Path $work 'uninstall-shortcut-diagnostic.json')
Copy-Item -LiteralPath $startShortcut -Destination (Join-Path $work 'start-menu.lnk')
Copy-Item -LiteralPath $desktopShortcut -Destination (Join-Path $work 'desktop.lnk')
$smokeProcess = Start-Process -FilePath $executable -ArgumentList '--installation-smoke' -Wait -PassThru -WindowStyle Hidden -RedirectStandardError (Join-Path $work 'smoke-stderr.txt')
if ($smokeProcess.ExitCode -ne 0) { throw "Installed executable smoke failed: $($smokeProcess.ExitCode)" }
$smoke = Get-Content -LiteralPath (Join-Path $env:LOCALAPPDATA 'AntibodyResearchWorkbench/installation-smoke.json') -Encoding UTF8 -Raw | ConvertFrom-Json
Assert-InstallationSmokeReport -Report $smoke -ExpectedExecutable $executable -ExpectedPid $smokeProcess.Id
$reinstallProcess = Start-Process -FilePath ([IO.Path]::GetFullPath($Installer)) -ArgumentList ($arguments + ('/LOG="' + (Join-Path $work 'reinstall.log') + '"')) -Wait -PassThru -WindowStyle Hidden
if ($reinstallProcess.ExitCode -ne 0) { throw 'Same-version reinstall failed' }
$sentinelDirectory = New-Item -ItemType Directory -Force (Join-Path $env:APPDATA 'AntibodyAI')
$sentinel = Join-Path $sentinelDirectory.FullName 'acceptance-preserve.txt'
Set-Content -LiteralPath $sentinel -Value 'synthetic acceptance data' -Encoding UTF8
$sentinelHash = (Get-FileHash -LiteralPath $sentinel -Algorithm SHA256).Hash
$uninstallProcess = Start-Process -FilePath (Join-Path $installDirectory 'unins000.exe') -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',('/LOG="' + (Join-Path $work 'uninstall.log') + '"')) -Wait -PassThru -WindowStyle Hidden
if ($uninstallProcess.ExitCode -ne 0) { throw 'Uninstall failed' }
if (Test-Path -LiteralPath $executable) { throw 'Executable remains after uninstall' }
if ((Test-Path -LiteralPath $desktopShortcut) -or (Test-Path -LiteralPath $startShortcut) -or
    (Test-Path -LiteralPath $uninstallShortcut)) { throw 'Shortcut remains after uninstall' }
if (-not (Test-Path -LiteralPath $sentinel)) { throw 'Uninstaller removed user data' }
if ((Get-FileHash -LiteralPath $sentinel -Algorithm SHA256).Hash -ne $sentinelHash) { throw 'Uninstaller changed user data' }
if (Test-Path $uninstallKey) { throw 'Uninstall registration remains' }
$report = @{
    status='PASS'; scope='Current Windows development host, silent install + offscreen exe smoke'
    clean_windows_qualified=$false; external_python_on_path=$false
    install='PASS'; start_menu_shortcut='PASS'; optional_desktop_shortcut='PASS'
    installed_smoke=$smoke; same_version_reinstall='PASS'; real_cross_version_upgrade='NOT_TESTED'
    uninstall='PASS'; user_data_preserved='PASS'; user_data_scope='synthetic sentinel byte integrity'
    gui_wizard_click_acceptance='NOT_TESTED'; gui_readability='NOT_TESTED'
}
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $work 'acceptance.json') -Encoding UTF8
$report | ConvertTo-Json -Depth 8
