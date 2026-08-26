param(
    [int]$Hours = 4
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "[SHADOW-05] Runner combinado PAPER. Ctrl+C para detener."
Write-Host "[SHADOW-05] Ejecuta 05A + diagnosticos 05A/05F + scanner unificado 05I + challenger 05J."
Write-Host "[SHADOW-05] 05C/05D/05G/05H quedan como diagnostico historico y no capturan nuevas cohortes."
Write-Host "[SHADOW-05] Cadencia: $Hours horas."

while ($true) {
    $stamp = Get-Date -Format "yyyy-MM-ddTHH:mm:ss"
    Write-Host "[SHADOW-05] Ejecutando $stamp"

    python scripts\shadow_profitability_05a.py
    if ($LASTEXITCODE -ne 0) { throw "05A fallo con codigo $LASTEXITCODE" }

    python scripts\analyze_profitability_shadow_05a.py
    if ($LASTEXITCODE -ne 0) { throw "Diagnostico 05A fallo con codigo $LASTEXITCODE" }

    python scripts\analyze_edge_calibration_05f.py
    if ($LASTEXITCODE -ne 0) { throw "05F fallo con codigo $LASTEXITCODE" }

    python scripts\shadow_scanner_unified_05i.py
    if ($LASTEXITCODE -ne 0) { throw "05I fallo con codigo $LASTEXITCODE" }

    python scripts\analyze_scanner_challenger_05j.py
    if ($LASTEXITCODE -ne 0) { throw "05J fallo con codigo $LASTEXITCODE" }

    Write-Host "[SHADOW-05] Proxima ejecucion en $Hours horas."
    Start-Sleep -Seconds ($Hours * 3600)
}
