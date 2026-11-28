"""Installer contracts only: never install, uninstall, or touch user shortcuts."""
import codecs
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/test_windows_installer.ps1"
SPEC = ROOT / "packaging/windows/installer.iss"


def script_text():
    return SCRIPT.read_text(encoding="utf-8-sig")


def test_chinese_script_is_utf8_bom_for_windows_powershell_51():
    assert SCRIPT.read_bytes().startswith(codecs.BOM_UTF8)
    assert "生物科研决策支持工作台（候选版）.lnk" in script_text()


def test_shortcut_names_and_explicit_group_match_installer():
    text, spec = script_text(), SPEC.read_text(encoding="utf-8")
    group = re.search(r"^DefaultGroupName=(.+)$", spec, re.M).group(1).strip()
    assert f"$groupName = '{group}'" in text
    assert "('/GROUP=\"' + $groupName + '\"')" in text
    for title in re.findall(r'Name: "\{(?:group|autodesktop)\}\\([^"\n]+)"', spec):
        assert title + ".lnk" in text
    assert "抗体科研工作台（候选版）.lnk" not in text


def test_preexisting_installation_and_shortcut_guards_precede_writes():
    text = script_text()
    first_write = text.index("New-Item -ItemType Directory -Path $work")
    for guard in ("if (Test-Path $uninstallKey)", "if (Test-Path -LiteralPath $desktopShortcut)",
                  "if (Test-Path -LiteralPath $groupDirectory)", "if (Test-Path -LiteralPath $work)"):
        assert text.index(guard) < first_write
    assert "Use a new dist/ acceptance directory" in text


def test_each_shortcut_is_verified_and_uninstall_cleans_registration():
    text = script_text()
    for name in ("$startShortcut", "$desktopShortcut", "$uninstallShortcut"):
        assert "Assert-InstallerShortcut -Shortcut " + name in text
        assert "Test-Path -LiteralPath " + name in text
    assert "if (Test-Path $uninstallKey)" in text
    assert "Get-FileHash -LiteralPath $sentinel" in text
    assert "Uninstaller changed user data" in text


def test_basic_smoke_contract_and_qualification_limits():
    text = script_text()
    assert "-ArgumentList '--installation-smoke'" in text
    assert "Assert-InstallationSmokeReport -Report $smoke" in text
    assert "-ExpectedPid $smokeProcess.Id" in text
    assert "-Encoding UTF8 -Raw | ConvertFrom-Json" in text
    assert "clean_windows_qualified=$false" in text
    assert "gui_readability='NOT_TESTED'" in text
    assert "synthetic sentinel byte integrity" in text


@pytest.fixture(params=["powershell.exe", "pwsh"])
def engine(request):
    path = shutil.which(request.param)
    if not path:
        pytest.skip(request.param + " is not installed; no environment installation")
    return path


def run_functions(engine, tmp_path, body):
    # Parse, then load function definitions only. Never dot-source the installer.
    literal = lambda value: "'" + str(value).replace("'", "''") + "'"
    program = "$contractSource = " + literal(SCRIPT) + "\n$testRoot = " + literal(tmp_path) + r'''
$ErrorActionPreference = 'Stop'
$tokens = $null; $errors = $null
$tree = [System.Management.Automation.Language.Parser]::ParseFile($contractSource, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw ($errors | Out-String) }
foreach ($name in @('Assert-InstallerShortcut','Assert-InstallationSmokeReport')) {
    $node = $tree.Find({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name}, $true)
    if ($null -eq $node) { throw ('Missing helper: ' + $name) }
    . ([scriptblock]::Create($node.Extent.Text))
}
''' + body
    source = tmp_path / "contract.ps1"
    source.write_text(program, encoding="utf-8-sig")
    # Standard command mode tests fixed functions without changing execution
    # policy or requiring permission to run a whole installer acceptance file.
    result = subprocess.run([engine, "-NoProfile", "-NonInteractive", "-Command", program],
                            capture_output=True, timeout=30)
    assert result.returncode == 0, repr(result.stdout + result.stderr)


def test_powershell_parser_preserves_actual_chinese_names(engine, tmp_path):
    run_functions(engine, tmp_path, r'''
$strings = $tree.FindAll({param($n) $n -is [System.Management.Automation.Language.StringConstantExpressionAst]}, $true)
if (-not ($strings.Value -contains '生物科研决策支持工作台（候选版）.lnk')) { throw 'Parsed Chinese name damaged' }
if ($PSVersionTable.PSVersion.Major -lt 5) { throw 'Unsupported PowerShell' }
Write-Output $PSVersionTable.PSVersion
''')


@pytest.mark.parametrize("field,value", [
    ("status", "FAIL"), ("pages", 7), ("frozen", False), ("phase", "restore"),
    ("source_mode", True), ("network_attempts", 1), ("trained", True),
    ("provider_called", True), ("model_loaded", True), ("pid", 999),
    ("executable", "different.exe"),
])
def test_smoke_rejects_false_success(engine, tmp_path, field, value):
    mutation = json.dumps({field: value})
    run_functions(engine, tmp_path, r'''
$exe = Join-Path $testRoot 'synthetic.exe'
$report = [pscustomobject]@{status='PASS'; pages=8; frozen=$true; phase='basic'; source_mode=$false; network_attempts=0; trained=$false; provider_called=$false; model_loaded=$false; pid=123; executable=$exe}
Assert-InstallationSmokeReport -Report $report -ExpectedExecutable $exe -ExpectedPid 123
''' + "$mutation = '" + mutation + r"' | ConvertFrom-Json" + r'''
foreach ($property in $mutation.PSObject.Properties) { $report.($property.Name) = $property.Value }
$rejected = $false
try { Assert-InstallationSmokeReport -Report $report -ExpectedExecutable $exe -ExpectedPid 123 } catch { $rejected = $true }
if (-not $rejected) { throw 'False successful smoke accepted' }
''')


def test_smoke_requires_complete_safe_report(engine, tmp_path):
    run_functions(engine, tmp_path, r'''
$rejected = $false
try { Assert-InstallationSmokeReport -Report ([pscustomobject]@{status='PASS'}) -ExpectedExecutable 'synthetic.exe' -ExpectedPid 123 } catch { $rejected = $true }
if (-not $rejected) { throw 'Incomplete smoke accepted' }
''')


@pytest.mark.skipif(sys.platform != "win32", reason="Real Windows Shell COM link test")
def test_real_start_and_desktop_links_and_wrong_target(engine, tmp_path):
    run_functions(engine, tmp_path, r'''
$exe = Join-Path $testRoot 'synthetic.exe'
[IO.File]::WriteAllText($exe, 'not executable; synthetic shortcut target')
$shell = New-Object -ComObject WScript.Shell
foreach ($name in @('start-menu.lnk','desktop.lnk')) {
    $path = Join-Path $testRoot $name
    $link = $shell.CreateShortcut($path); $link.TargetPath = $exe; $link.Save()
    Assert-InstallerShortcut -Shortcut $path -ExpectedTarget $exe -DiagnosticPath (Join-Path $testRoot ($name + '.json'))
}
$bad = Join-Path $testRoot 'wrong.lnk'
$link = $shell.CreateShortcut($bad); $link.TargetPath = Join-Path $testRoot 'other.exe'; $link.Save()
$rejected = $false
try { Assert-InstallerShortcut -Shortcut $bad -ExpectedTarget $exe -DiagnosticPath (Join-Path $testRoot 'wrong.json') } catch { $rejected = $true }
if (-not $rejected) { throw 'Wrong shortcut target accepted' }
''')
