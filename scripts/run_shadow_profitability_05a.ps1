$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "[SHADOW-05A] Inicio. PAPER solamente; Ctrl+C para detener."
Write-Host "[SHADOW-05A] Cadencia: 4 horas."

while ($true) {
    $inicio = Get-Date
    Write-Host "[SHADOW-05A] Ejecutando $($inicio.ToString('s'))"

    python scripts\shadow_profitability_05a.py
    if ($LASTEXITCODE -ne 0) {
        throw "shadow_profitability_05a.py termino con codigo $LASTEXITCODE"
    }

    Write-Host "[SHADOW-05A] Proxima ejecucion en 4 horas."
    Start-Sleep -Seconds 14400
}
