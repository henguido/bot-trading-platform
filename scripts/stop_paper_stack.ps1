$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Runtime = Join-Path $Root ".runtime"
$PidFiles = @(
    @{ Name = "frontend"; Path = Join-Path $Runtime "paper-frontend.pid" },
    @{ Name = "backend"; Path = Join-Path $Runtime "paper-backend.pid" }
)

$detenidos = 0
foreach ($item in $PidFiles) {
    if (-not (Test-Path $item.Path)) {
        continue
    }

    try {
        $savedPid = [int](Get-Content $item.Path -Raw).Trim()
        $process = Get-Process -Id $savedPid -ErrorAction Stop
        Stop-Process -Id $savedPid -Force -ErrorAction Stop
        Write-Host "[BOT PAPER] $($item.Name) detenido (PID $savedPid)." -ForegroundColor Green
        $detenidos += 1
    }
    catch {
        Write-Host "[BOT PAPER] $($item.Name) ya no estaba activo; limpiando PID." -ForegroundColor Yellow
    }
    finally {
        Remove-Item $item.Path -Force -ErrorAction SilentlyContinue
    }
}

if ($detenidos -eq 0) {
    Write-Host "[BOT PAPER] No habia procesos iniciados por el lanzador." -ForegroundColor Yellow
}

Write-Host "[BOT PAPER] Apagado completado. No se tocaron otros procesos ni puertos." -ForegroundColor DarkGray
