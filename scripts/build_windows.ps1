$ErrorActionPreference = "Stop"

$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RootDir

$PythonBin = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }
$VenvDir = if ($env:VENV_DIR) { $env:VENV_DIR } else { ".venv-build" }

$VersionCheck = @'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10+ is required")
if sys.version_info >= (3, 14):
    print("WARNING: Python 3.14+ may not have wheels for PyInstaller/PyVista/VTK yet.")
    print("         Prefer Python 3.11 or 3.12 for release builds.")
'@
$VersionCheck | & $PythonBin -

& $PythonBin -m venv $VenvDir
. (Join-Path $VenvDir "Scripts\Activate.ps1")

python -m pip install --upgrade pip
python -m pip install -r requirements-build.txt
python -m compileall -q main.py app scripts tests
pyinstaller packaging/split3r.spec --clean --noconfirm

Write-Host ""
Write-Host "Build ready at: $RootDir\dist\Split3rClone"
