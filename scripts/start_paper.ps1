param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Error "No existe el venv oficial en .venv. Crea/reconstruye el entorno antes de arrancar PAPER."
    exit 2
}

Write-Host "[PAPER-V1] Ejecutando readiness check..."
& $Python "scripts\check_paper_release.py"
if ($LASTEXITCODE -ne 0) {
    Write-Error "PAPER v1 NO esta listo. Corrige los BLOCKER mostrados arriba. No se arranca uvicorn."
    exit $LASTEXITCODE
}

Write-Host "[PAPER-V1] Readiness OK. Arrancando backend en ${HostAddress}:${Port} con un solo worker."
Write-Host "[PAPER-V1] Alembic NO se aplica automaticamente."

& $Python -m uvicorn backend.main:app --host $HostAddress --port $Port --workers 1
exit $LASTEXITCODE
