$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (!(Test-Path $Python)) {
    throw "Create .venv and install -e '.[dev]' as described in README first."
}
& $Python -m denon_controller @args
exit $LASTEXITCODE
