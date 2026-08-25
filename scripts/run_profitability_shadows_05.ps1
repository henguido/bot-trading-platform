param(
    [int]$Hours = 4
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "[SHADOW-05] Runner combinado PAPER. Ctrl+C para detener."
Write-Host "[SHADOW-05] Ejecuta 05A/05C/05D y diagnosticos 05A/05F/05G/05H."
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

    python scripts\shadow_scanner_alpha_05c.py
    if ($LASTEXITCODE -ne 0) { throw "05C fallo con codigo $LASTEXITCODE" }

    python scripts\shadow_scanner_attribution_05d.py
    if ($LASTEXITCODE -ne 0) { throw "05D fallo con codigo $LASTEXITCODE" }

    python scripts\analyze_scanner_bucket_attribution_05g.py
    if ($LASTEXITCODE -ne 0) { throw "05G fallo con codigo $LASTEXITCODE" }

    python scripts\analyze_scanner_state_consistency_05h.py
    if ($LASTEXITCODE -ne 0) { throw "05H fallo con codigo $LASTEXITCODE" }

    Write-Host "[SHADOW-05] Proxima ejecucion en $Hours horas."
    Start-Sleep -Seconds ($Hours * 3600)
}
