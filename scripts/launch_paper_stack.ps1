param(
    [string]$HostAddress = "localhost",
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Frontend = Join-Path $Root "frontend"
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Runtime = Join-Path $Root ".runtime"
$BackendPidFile = Join-Path $Runtime "paper-backend.pid"
$FrontendPidFile = Join-Path $Runtime "paper-frontend.pid"
$BackendOut = Join-Path $Runtime "paper-backend.out.log"
$BackendErr = Join-Path $Runtime "paper-backend.err.log"
$FrontendOut = Join-Path $Runtime "paper-frontend.out.log"
$FrontendErr = Join-Path $Runtime "paper-frontend.err.log"
$FrontendUrl = "http://${HostAddress}:${FrontendPort}"
$BackendUrl = "http://${HostAddress}:${BackendPort}"

Set-Location $Root

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "[BOT PAPER] NO SE PUDO INICIAR" -ForegroundColor Red
    Write-Host $Message -ForegroundColor Red
    exit 2
}

function Process-Alive([string]$PidFile) {
    if (-not (Test-Path $PidFile)) { return $false }
    try {
        $savedPid = [int](Get-Content $PidFile -Raw).Trim()
        $null = Get-Process -Id $savedPid -ErrorAction Stop
        return $true
    }
    catch {
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
        return $false
    }
}

function Port-In-Use([int]$Port) {
    try {
        return @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop).Count -gt 0
    }
    catch {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
        try {
            $listener.Start()
            return $false
        }
        catch {
            return $true
        }
        finally {
            try { $listener.Stop() } catch {}
        }
    }
}

if (-not (Test-Path $Python)) {
    Fail "No existe .venv\Scripts\python.exe. Reconstruye el venv oficial antes de arrancar PAPER."
}

if (-not (Test-Path (Join-Path $Frontend "package.json"))) {
    Fail "No existe frontend\package.json. Ejecuta este lanzador desde el repositorio oficial."
}

$Node = Get-Command node -ErrorAction SilentlyContinue
if (-not $Node) {
    Fail "Node.js no esta disponible en PATH. Instala la version usada por el proyecto antes de arrancar la interfaz."
}

$ViteEntry = Join-Path $Frontend "node_modules\vite\bin\vite.js"
if (-not (Test-Path $ViteEntry)) {
    Fail "Faltan dependencias del frontend. Ejecuta una vez 'cd frontend' y 'npm install'; este lanzador no instala dependencias automaticamente."
}

New-Item -ItemType Directory -Force -Path $Runtime | Out-Null

$backendAlive = Process-Alive $BackendPidFile
$frontendAlive = Process-Alive $FrontendPidFile
if ($backendAlive -and $frontendAlive) {
    Write-Host "[BOT PAPER] El sistema ya parece estar iniciado." -ForegroundColor Yellow
    Write-Host "Frontend: $FrontendUrl"
    Write-Host "Backend:  $BackendUrl"
    if (-not $NoBrowser) { Start-Process $FrontendUrl }
    exit 0
}

if ($backendAlive -xor $frontendAlive) {
    Fail "Se encontro un arranque parcial previo. Ejecuta DETENER_BOT_PAPER.cmd y vuelve a intentarlo."
}

if (Port-In-Use $BackendPort) {
    Fail "El puerto backend $BackendPort ya esta ocupado. No se cerrara ningun proceso ajeno automaticamente."
}
if (Port-In-Use $FrontendPort) {
    Fail "El puerto frontend $FrontendPort ya esta ocupado. No se cerrara ningun proceso ajeno automaticamente."
}

Write-Host "[BOT PAPER] 1/4 Verificando readiness PAPER v1..." -ForegroundColor Cyan
& $Python "scripts\check_paper_release.py"
if ($LASTEXITCODE -ne 0) {
    Fail "El readiness encontro BLOCKER. No se inicio backend ni frontend."
}

Write-Host "[BOT PAPER] 2/4 Iniciando backend..." -ForegroundColor Cyan
$backendArgs = @(
    "-m", "uvicorn", "backend.main:app",
    "--host", $HostAddress,
    "--port", "$BackendPort",
    "--workers", "1"
)
$backendStart = @{
    FilePath = $Python
    ArgumentList = $backendArgs
    WorkingDirectory = $Root
    RedirectStandardOutput = $BackendOut
    RedirectStandardError = $BackendErr
    PassThru = $true
}
$backend = Start-Process @backendStart
Set-Content -Path $BackendPidFile -Value $backend.Id -Encoding ascii

$frontendProcess = $null
try {
    $healthReady = $false
    for ($i = 0; $i -lt 30; $i++) {
        if ($backend.HasExited) {
            throw "El backend termino durante el arranque. Revisa $BackendErr"
        }
        try {
            $null = Invoke-RestMethod -Method Get -Uri "$BackendUrl/health" -TimeoutSec 2
            $healthReady = $true
            break
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }
    if (-not $healthReady) {
        throw "El backend no respondio /health dentro de 30 segundos."
    }

    Write-Host "[BOT PAPER] 3/4 Ejecutando smoke runtime de solo lectura..." -ForegroundColor Cyan
    # Ejecutarlo como modulo conserva la raiz del repositorio en sys.path y
    # evita ModuleNotFoundError al importar backend.* desde Windows.
    & $Python "-m" "scripts.smoke_paper_runtime" "--base-url" $BackendUrl
    if ($LASTEXITCODE -ne 0) {
        throw "El smoke runtime PAPER no quedo READY."
    }

    Write-Host "[BOT PAPER] 4/4 Iniciando frontend..." -ForegroundColor Cyan
    $frontendArgs = @($ViteEntry, "--host", $HostAddress, "--port", "$FrontendPort", "--strictPort")
    $frontendStart = @{
        FilePath = $Node.Source
        ArgumentList = $frontendArgs
        WorkingDirectory = $Frontend
        RedirectStandardOutput = $FrontendOut
        RedirectStandardError = $FrontendErr
        PassThru = $true
    }
    $frontendProcess = Start-Process @frontendStart
    Set-Content -Path $FrontendPidFile -Value $frontendProcess.Id -Encoding ascii

    Start-Sleep -Seconds 2
    if ($frontendProcess.HasExited) {
        throw "El frontend termino durante el arranque. Revisa $FrontendErr"
    }
}
catch {
    Write-Host "[BOT PAPER] Fallo el arranque; cerrando procesos iniciados por este lanzador..." -ForegroundColor Yellow
    if ($frontendProcess -and -not $frontendProcess.HasExited) {
        Stop-Process -Id $frontendProcess.Id -Force -ErrorAction SilentlyContinue
    }
    if ($backend -and -not $backend.HasExited) {
        Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
    }
    Remove-Item $BackendPidFile, $FrontendPidFile -Force -ErrorAction SilentlyContinue
    Fail $_.Exception.Message
}

Write-Host ""
Write-Host "==============================================" -ForegroundColor Green
Write-Host " BOT Trading PAPER iniciado correctamente" -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Green
Write-Host "Frontend: $FrontendUrl"
Write-Host "Backend:  $BackendUrl"
Write-Host "Modo:     PAPER"
Write-Host "Parar:    DETENER_BOT_PAPER.cmd"
Write-Host "Logs:     .runtime\"
Write-Host ""
Write-Host "Este lanzador NO aplica migraciones, NO instala dependencias y NO habilita LIVE." -ForegroundColor DarkGray

if (-not $NoBrowser) {
    Start-Process $FrontendUrl
}
