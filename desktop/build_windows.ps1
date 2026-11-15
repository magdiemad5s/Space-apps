# Build on Windows x64 with Python 3.12 and Node 24. The output needs neither.
[CmdletBinding()]
param(
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$AppVersion = '0.1.1',
    [switch]$SkipInstaller
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($env:OS -ne 'Windows_NT') { throw 'Build the Windows executable on Windows, or run the Windows application bundle workflow.' }

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Executable failed with exit code $LASTEXITCODE." }
}

$Project = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Build = Join-Path $PSScriptRoot 'build'
$Dist = Join-Path $PSScriptRoot 'dist'
$Resources = Join-Path $Build 'resources'
$BackendSource = Join-Path $Project 'ai/integration/backend_review/proposed_backend'
$FrontendSource = Join-Path $Project 'frontend'
$OriginalModelSource = Join-Path $Project 'ai/artifacts/bundle.joblib'
$ModelSource = Join-Path $PSScriptRoot 'artifacts/inference_bundle.joblib'
$InferenceManifestPath = Join-Path $PSScriptRoot 'artifacts/inference_manifest.json'
$DataSource = Join-Path $Project 'ai/data/astra_shield_synthetic_ml.csv'
$ExpectedOriginalModelHash = '7731618ad68c0302338bcb4e869820601f8a43f735c8f7480fe19a121c500706'
$ExpectedDataHash = 'dd76fd2658586375a4f9fc44767c18731a5ecee061912ed625a44bd206ed6a95'
$InferenceManifest = Get-Content $InferenceManifestPath -Raw | ConvertFrom-Json
$ExpectedModelHash = $InferenceManifest.deployment_model_sha256
if ($ExpectedModelHash -notmatch '^[0-9a-f]{64}$' -or $InferenceManifest.original_model_sha256 -ne $ExpectedOriginalModelHash) {
    throw 'The inference export manifest does not identify the expected original model and deployment artifact.'
}
$Python = (Get-Command python.exe -ErrorAction Stop).Source
$Node = (Get-Command node.exe -ErrorAction Stop).Source
$Npm = (Get-Command npm.cmd -ErrorAction Stop).Source
Invoke-Checked $Python @('-c', 'import sys,struct; assert sys.version_info[:2] == (3,12) and struct.calcsize("P") == 8, "Python 3.12 x64 is required"')
$NodeVersion = (& $Node --version).Trim()
if ($NodeVersion -notmatch '^v24\.') { throw "Node 24 is required for this build; found $NodeVersion." }
if ((& $Node -p 'process.arch').Trim() -ne 'x64') { throw 'Node x64 is required.' }

function Assert-FrozenInputs {
    if ((Get-FileHash $OriginalModelSource -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedOriginalModelHash) {
        throw 'The original research model has changed. The deployment export must retain its exact selected fitted models.'
    }
    if ((Get-FileHash $ModelSource -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedModelHash) {
        throw 'The inference export does not match its reviewed deployment manifest.'
    }
    if ((Get-FileHash $DataSource -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedDataHash) {
        throw 'The original synthetic dataset has changed. Packaging must not modify the dataset.'
    }
}
Assert-FrozenInputs
if (-not $SkipInstaller) {
    # The smoke installation uses the same AppId as the delivered installer.
    # Refuse to overwrite an existing user's uninstall registration on a build
    # workstation. The clean CI runner has no existing ASTRA installation.
    $UninstallKey = '{2B11E450-13CD-48BD-9836-108C4CBA11AB}_is1'
    foreach ($Hive in @('HKCU:', 'HKLM:')) {
        foreach ($RegistryBase in @('Software/Microsoft/Windows/CurrentVersion/Uninstall', 'Software/WOW6432Node/Microsoft/Windows/CurrentVersion/Uninstall')) {
            if (Test-Path (Join-Path $Hive "$RegistryBase/$UninstallKey")) {
                throw 'ASTRA-SHIELD is already installed on this build computer. Use the clean Windows CI runner, or -SkipInstaller for a portable-only build, to preserve its installation registration.'
            }
        }
    }
}
foreach ($directory in @($Build, $Dist)) {
    if (Test-Path $directory) { Remove-Item -LiteralPath $directory -Recurse -Force }
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}
foreach ($name in @('frontend', 'backend', 'node', 'model', 'fixtures', 'licenses')) {
    New-Item -ItemType Directory -Path (Join-Path $Resources $name) -Force | Out-Null
}

# Use a clean build environment rather than dependencies from the developer's
# Python installation. No training command is run anywhere in this build.
Invoke-Checked $Python @('-m', 'venv', (Join-Path $Build 'venv'))
$BuildPython = Join-Path $Build 'venv/Scripts/python.exe'
Invoke-Checked $BuildPython @('-m', 'pip', 'install', '--disable-pip-version-check', '-r', (Join-Path $Project 'ai/requirements.txt'), '-r', (Join-Path $PSScriptRoot 'requirements-build.txt'))
Invoke-Checked $BuildPython @((Join-Path $PSScriptRoot 'runtime_tests.py'))
Invoke-Checked $BuildPython @((Join-Path $Project 'scripts/test_launcher.py'))
# Validate every output field for six training-only reference requests against
# the original Linux artifact. This loads no cross-platform research snapshot.
Invoke-Checked $BuildPython @((Join-Path $PSScriptRoot 'export_inference_bundle.py'), '--validate-only', '--artifact', $ModelSource, '--reference', (Join-Path $PSScriptRoot 'artifacts/inference_reference.json')) | Tee-Object -FilePath (Join-Path $Dist 'windows-model-equivalence-report.json')

Push-Location $FrontendSource
try {
    Invoke-Checked $Npm @('ci', '--no-audit', '--no-fund')
    Invoke-Checked $Npm @('test')
    Invoke-Checked $Npm @('run', 'build')
} finally { Pop-Location }
$FrontendOutput = Join-Path $FrontendSource 'dist/dashboard-angular'
Copy-Item -Path (Join-Path $FrontendOutput 'browser/*') -Destination (Join-Path $Resources 'frontend') -Recurse -Force
Copy-Item (Join-Path $FrontendOutput '3rdpartylicenses.txt') (Join-Path $Resources 'licenses/frontend-3rdpartylicenses.txt')

Push-Location $BackendSource
try {
    Invoke-Checked $Npm @('ci', '--no-audit', '--no-fund')
    Invoke-Checked $Npm @('test')
    Invoke-Checked $Node @((Join-Path $BackendSource 'node_modules/typescript/bin/tsc'), '-p', (Join-Path $BackendSource 'tsconfig.json'), '--noEmit', 'false', '--rewriteRelativeImportExtensions', 'true', '--outDir', (Join-Path $Resources 'backend'))
} finally { Pop-Location }
# Runtime imports are emitted as .js. The bundle needs Express/cors, not tsx,
# TypeScript, development node_modules, or test source/compiled test modules.
Get-ChildItem (Join-Path $Resources 'backend') -Filter '*.test.js' | Remove-Item -Force
Copy-Item (Join-Path $BackendSource 'package.json') (Join-Path $Resources 'backend/package.json')
Copy-Item (Join-Path $BackendSource 'package-lock.json') (Join-Path $Resources 'backend/package-lock.json')
Push-Location (Join-Path $Resources 'backend')
try { Invoke-Checked $Npm @('ci', '--omit=dev', '--no-audit', '--no-fund') }
finally { Pop-Location }

Copy-Item $Node (Join-Path $Resources 'node/node.exe')
$NodeLicense = Join-Path (Split-Path $Node) 'LICENSE'
if (Test-Path $NodeLicense) {
    Copy-Item $NodeLicense (Join-Path $Resources 'node/LICENSE')
} else {
    # setup-node may retain only the executable. Include the exact release's
    # upstream license, including Node's bundled third-party component notices.
    Invoke-WebRequest "https://raw.githubusercontent.com/nodejs/node/$NodeVersion/LICENSE" -OutFile (Join-Path $Resources 'node/LICENSE')
}
Copy-Item $ModelSource (Join-Path $Resources 'model/bundle.joblib')
Copy-Item (Join-Path $Project 'ai/artifacts/frozen_manifest.json') (Join-Path $Resources 'model/original_research_manifest.json')
Copy-Item $InferenceManifestPath (Join-Path $Resources 'model/inference_manifest.json')
Copy-Item (Join-Path $BackendSource 'examples/synthetic_daily_sequence.json') (Join-Path $Resources 'fixtures/synthetic_daily_sequence.json')
Copy-Item (Join-Path $PSScriptRoot 'artifacts/inference_reference.json') (Join-Path $Resources 'fixtures/inference_reference.json')
if ((Get-FileHash (Join-Path $Resources 'model/bundle.joblib') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedModelHash) {
    throw 'Staged inference model hash does not match the reviewed deployment export.'
}

# Preserve wheel licenses even when PyInstaller's analysis would not collect
# every distribution's .dist-info. Production npm modules retain their licenses
# within backend/node_modules. The Angular build carries its license summary.
$LicenseCollector = @'
import importlib.metadata as metadata
import json
from pathlib import Path
import re
import shutil
import sys
root = Path(sys.argv[1])
inventory = []
for distribution in sorted(metadata.distributions(), key=lambda d: d.metadata['Name'].lower()):
    name = distribution.metadata['Name']
    version = distribution.version
    destination = root / (re.sub(r'[^A-Za-z0-9_.-]', '_', name) + '-' + version)
    copied = []
    for entry in distribution.files or []:
        relative = Path(str(entry))
        if '..' in relative.parts or not re.search(r'(^|[/\\])(licen[sc]e[^/\\]*|copying[^/\\]*|notice[^/\\]*)$', str(entry), re.I):
            continue
        source = Path(distribution.locate_file(entry))
        if source.is_file():
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            copied.append(str(relative).replace('\\', '/'))
    inventory.append({'name': name, 'version': version, 'license_files': copied})
root.mkdir(parents=True, exist_ok=True)
(root / 'inventory.json').write_text(json.dumps(inventory, indent=2), encoding='utf-8')
'@
Invoke-Checked $BuildPython @('-c', $LicenseCollector, (Join-Path $Resources 'licenses/python'))
$PythonBase = (& $BuildPython -c 'import sys; print(sys.base_prefix)').Trim()
$PythonLicense = Join-Path $PythonBase 'LICENSE.txt'
if (Test-Path $PythonLicense) {
    Copy-Item $PythonLicense (Join-Path $Resources 'licenses/python-runtime-LICENSE.txt')
} else {
    $PythonVersion = (& $BuildPython -c 'import platform; print(platform.python_version())').Trim()
    Invoke-WebRequest "https://raw.githubusercontent.com/python/cpython/v$PythonVersion/LICENSE" -OutFile (Join-Path $Resources 'licenses/python-runtime-LICENSE.txt')
}

Push-Location $Project
try {
    Invoke-Checked $BuildPython @('-m', 'PyInstaller', '--noconfirm', '--clean', '--distpath', $Dist, '--workpath', (Join-Path $Build 'pyinstaller'), (Join-Path $PSScriptRoot 'astra.spec'))
} finally { Pop-Location }
$Bundle = Join-Path $Dist 'ASTRA-SHIELD'
$Executable = Join-Path $Bundle 'ASTRA-SHIELD.exe'
if (-not (Test-Path $Executable)) { throw 'PyInstaller did not produce the application executable.' }

$BundleReadme = @'
ASTRA-SHIELD - Windows prototype demonstration

This bundle includes Python, the frozen model, Node and the compiled Angular
interface. It opens the original web interface in your default browser and
binds its services to this computer's loopback interface only. No Python/Node
installation or network connection is required to run the installed bundle.

The installer and executable are unsigned. Windows may display an unknown
publisher / SmartScreen warning. Verify SHA256SUMS.txt and the project's
trusted GitHub build before deciding whether to run the downloaded installer.

The inference bundle retains the original five selected fitted models and
their metadata. Unused research baselines/ablations are omitted for portable
deployment; their Linux-specific XGBoost memory snapshots are not used by the
application. No retraining or replacement of selected models was performed.
The original research artifact remains unchanged in the source repository.

The Start menu shortcut opens the clearly labeled synthetic demo. Keep the
launcher window open while using the app; close it to stop the local services.
User records and logs are stored separately from this installation. Updating
or uninstalling the program does not intentionally delete those user records.

All model training data are synthetic. Outputs are not clinically validated,
not a diagnosis, and not an operational-readiness clearance. The alert panel
is a separate illustration, not the complete Clinical Alert Algorithm V2.

Project and original frontend credits:
https://github.com/magdiemad5s/Space-apps
https://github.com/Karam-Eyad/crew-health-console

Redistributed component licenses are in _internal/resources/licenses,
_internal/resources/node/LICENSE, backend/node_modules and the frontend's
licenses/manrope-OFL.txt. PyInstaller also retains package license metadata.
'@
$BundleReadme | Set-Content -Path (Join-Path $Bundle 'BUNDLE-README.txt') -Encoding utf8
$Commit = (& git -C $Project rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { $Commit = 'unknown-local-build' }
$Manifest = [ordered]@{
    app_version = $AppVersion
    built_at_utc = [DateTime]::UtcNow.ToString('o')
    commit = $Commit
    platform = 'Windows x64'
    python = (& $BuildPython --version).Trim()
    node = $NodeVersion
    npm = (& $Npm --version).Trim()
    original_model_sha256 = $ExpectedOriginalModelHash
    deployment_model_sha256 = $ExpectedModelHash
    original_dataset_sha256 = $ExpectedDataHash
    embedded_node_sha256 = (Get-FileHash (Join-Path $Resources 'node/node.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
    signed = $false
    data_origin = 'synthetic'
    clinical_validation = $false
    training_performed = $false
    runtime_install_required = $false
    tests = @('windows-model-equivalence-report.json', 'windows-smoke-report.json', 'installed-smoke-report.json')
}
$Manifest | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $Dist 'build-manifest.json') -Encoding utf8
Copy-Item (Join-Path $Dist 'build-manifest.json') (Join-Path $Bundle 'build-manifest.json')

function Test-FrozenRuntime {
    param([string]$Application, [string]$DataDirectory, [string]$Report)
    $PreviousPath = $env:PATH
    $PreviousPythonPath = $env:PYTHONPATH
    $PreviousPythonHome = $env:PYTHONHOME
    try {
        # A successful smoke must use the shipped runtimes, even though the
        # Windows build runner also has development tools installed.
        $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
        $env:PYTHONPATH = $null
        $env:PYTHONHOME = $null
        Invoke-Checked $Application @('--smoke-test', '--no-browser', '--data-dir', $DataDirectory, '--report', $Report)
    } catch {
        # Keep chained native-library/pickle failures visible in the job log;
        # artifact downloads are not always available to someone debugging CI.
        $RuntimeLogDirectory = Join-Path $DataDirectory 'logs'
        if (Test-Path $RuntimeLogDirectory) {
            Write-Host 'Bundled runtime failure details:'
            Get-ChildItem $RuntimeLogDirectory -Filter 'error.log' -File -Recurse | ForEach-Object { Get-Content $_.FullName }
        }
        throw
    } finally {
        $env:PATH = $PreviousPath
        $env:PYTHONPATH = $PreviousPythonPath
        $env:PYTHONHOME = $PreviousPythonHome
    }
    if (-not (Test-Path $Report)) { throw 'The executable produced no smoke-test report.' }
    $Result = Get-Content $Report -Raw | ConvertFrom-Json
    if ($Result.passed -ne $true) { throw "Bundled runtime smoke failed; see $Report." }
}
Test-FrozenRuntime $Executable (Join-Path $Build 'windows-smoke') (Join-Path $Dist 'windows-smoke-report.json')

if (-not $SkipInstaller) {
    $Compiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($Compiler) {
        $Inno = $Compiler.Source
    } else {
        $Inno = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6/ISCC.exe'
    }
    if (-not (Test-Path $Inno)) { throw 'Inno Setup 6 is required to build the installer. The Windows GitHub runner includes it.' }
    Invoke-Checked $Inno @("/DBundleDir=$Bundle", "/DOutputDir=$Dist", "/DAppVersion=$AppVersion", (Join-Path $PSScriptRoot 'installer.iss'))
    $Installer = Join-Path $Dist 'ASTRA-SHIELD-Setup-x64.exe'
    # Exercise spaces in paths as well as the actual installed executable.
    $InstallTest = Join-Path $Build 'installed application'
    $InstallLog = Join-Path $Build 'installer-test.log'
    $Installation = Start-Process -FilePath $Installer -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', ('/DIR="' + $InstallTest + '"'), ('/LOG="' + $InstallLog + '"')) -Wait -PassThru
    if ($Installation.ExitCode -ne 0) { throw "Installer test failed with exit code $($Installation.ExitCode)." }
    try {
        Test-FrozenRuntime (Join-Path $InstallTest 'ASTRA-SHIELD.exe') (Join-Path $Build 'installed-smoke') (Join-Path $Dist 'installed-smoke-report.json')
    } finally {
        $Uninstaller = Join-Path $InstallTest 'unins000.exe'
        if (Test-Path $Uninstaller) {
            $Uninstall = Start-Process -FilePath $Uninstaller -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', ('/LOG="' + (Join-Path $Build 'uninstaller-test.log') + '"')) -Wait -PassThru
            if ($Uninstall.ExitCode -ne 0) { throw "Uninstaller test failed with exit code $($Uninstall.ExitCode)." }
        }
    }
}

Assert-FrozenInputs
Compress-Archive -Path $Bundle -DestinationPath (Join-Path $Dist 'ASTRA-SHIELD-portable-x64.zip') -CompressionLevel Fastest
$Checksums = Get-ChildItem $Dist -File | Where-Object { $_.Extension -in @('.exe', '.zip') } | Sort-Object Name | ForEach-Object {
    ((Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() + '  ' + $_.Name)
}
$Checksums | Set-Content (Join-Path $Dist 'SHA256SUMS.txt') -Encoding ascii
Write-Host "Tested Windows bundle is ready in $Dist"
Write-Host 'These binaries are unsigned and are a synthetic-data prototype, not a clinically validated product.'
