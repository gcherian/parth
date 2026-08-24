<#
.SYNOPSIS
  Parth: one-shot build + start for Windows (PowerShell).

.DESCRIPTION
  Mirrors setup.sh. Safe to re-run — every step is idempotent.
  Requires: Python 3.11+, Docker Desktop (for Postgres), and optionally
  Ollama (local LLM) and Flutter (mobile app). Missing optional tools are
  skipped with a warning rather than failing the whole setup.

.PARAMETER ServerOnly
  Skip the Flutter/mobile step entirely.

.PARAMETER Mobile
  Also launch the Flutter app on a connected device/emulator after the
  server is up (falls back to printing instructions if none is found).

.EXAMPLE
  .\setup.ps1
  .\setup.ps1 -ServerOnly
  .\setup.ps1 -Mobile
#>
param(
    [switch]$ServerOnly,
    [switch]$Mobile
)

$ErrorActionPreference = "Stop"

$ParthDir  = $PSScriptRoot
$ServerDir = Join-Path $ParthDir "server"
$AppDir    = Join-Path $ParthDir "app"
$Port      = if ($env:PORT) { $env:PORT } else { 8000 }
$Log       = Join-Path $env:TEMP "parth_server.log"
$PidFile   = Join-Path $env:TEMP "parth.pid"

function Ok   ($msg) { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Warn ($msg) { Write-Host "  [!]  $msg" -ForegroundColor Yellow }
function Info ($msg) { Write-Host "  $msg" }
function Die  ($msg) { Write-Host "  [X] $msg" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "  ================================" -ForegroundColor Cyan
Write-Host "     PARTH AI  --  setup.ps1" -ForegroundColor Cyan
Write-Host "  ================================" -ForegroundColor Cyan
Write-Host ""

# -- 0. Find a usable Python (no hardcoded path) ------------------------------
$PythonCmd = $null
$candidates = @(
    @{ Exe = "py"; Args = @("-3.11") },
    @{ Exe = "python3.11"; Args = @() },
    @{ Exe = "python"; Args = @() },
    @{ Exe = "python3"; Args = @() }
)
foreach ($cand in $candidates) {
    if (Get-Command $cand.Exe -ErrorAction SilentlyContinue) {
        try {
            $verOk = & $cand.Exe @($cand.Args) -c "import sys;print(sys.version_info[:2]>=(3,11))" 2>$null
            if ($verOk -eq "True") { $PythonCmd = $cand; break }
        } catch {}
    }
}
if (-not $PythonCmd) {
    if (Get-Command python -ErrorAction SilentlyContinue) { $PythonCmd = @{ Exe = "python"; Args = @() } }
}
if (-not $PythonCmd) { Die "Python 3.11+ not found. Install it from https://python.org or 'winget install Python.Python.3.11', then re-run." }
Info "Using: $($PythonCmd.Exe) $($PythonCmd.Args -join ' ')"

Set-Location $ServerDir

# -- 1. Python venv ------------------------------------------------------------
$VenvPython = Join-Path $ServerDir "venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Info "Creating Python virtual environment..."
    & $PythonCmd.Exe @($PythonCmd.Args) -m venv "$ServerDir\venv"
    & $VenvPython -m pip install --quiet --upgrade pip
    & $VenvPython -m pip install --quiet -r "$ServerDir\requirements.txt"
    Ok "Python venv created and deps installed"
} else {
    Ok "Python venv ready"
}

# -- 2. .env file ---------------------------------------------------------------
$EnvFile = Join-Path $ServerDir ".env"
if (-not (Test-Path $EnvFile)) {
    Warn ".env missing — creating from template"
    $DataDir = (Join-Path $ServerDir "data") -replace '\\','/'
    @"
DATABASE_URL=postgresql://parth:parth_dev@localhost:5432/parth

# LLM backend — set ANTHROPIC_API_KEY to switch to Claude cloud
TUTOR_BACKEND=auto
DEFAULT_MODEL=gemma3:12b
FAST_MODEL=llama3.2:latest
OLLAMA_URL=http://localhost:11434
KRISHNA_MODEL=claude-haiku-4-5-20251001
KRISHNA_INTERVAL=10

PORT=$Port
RATE_LIMIT=20
DAILY_REQUEST_CAP=200

# Security — leave empty for local dev (enforced only in production)
PARTH_API_KEY=
ADMIN_KEY=

DATA_DIR=$DataDir
"@ | Set-Content -Path $EnvFile -Encoding utf8
    Ok ".env created — add ANTHROPIC_API_KEY to it to enable cloud mode"
} else {
    Ok ".env exists"
}

# Load .env into the current process environment
Get-Content $EnvFile | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
    $k, $v = $_.Split('=', 2)
    [Environment]::SetEnvironmentVariable($k.Trim(), $v.Trim(), "Process")
}

# -- 3. Postgres ----------------------------------------------------------------
function Test-Postgres {
    try {
        & $VenvPython -c "import socket; s=socket.create_connection(('localhost',5432),2); s.close()" 2>$null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}

if (Test-Postgres) {
    Ok "Postgres ready"
} else {
    Warn "Postgres not ready — starting via Docker..."
    if ((Get-Command docker -ErrorAction SilentlyContinue) -and (Test-Path "$ServerDir\docker-compose.yml")) {
        docker compose -f "$ServerDir\docker-compose.yml" up -d postgres
        $tries = 0
        while (-not (Test-Postgres) -and $tries -lt 30) { Start-Sleep 1; $tries++ }
        if (Test-Postgres) { Ok "Postgres ready" } else { Die "Postgres failed to start — check: docker compose -f $ServerDir\docker-compose.yml logs postgres" }
    } else {
        Die "Postgres not running and Docker not available. Install Docker Desktop, or start Postgres manually and set DATABASE_URL in server\.env."
    }
}

# -- 4. DB schema -----------------------------------------------------------------
$schemaScript = @"
import asyncio, os, sys
sys.path.insert(0, r'$ServerDir')
os.chdir(r'$ServerDir')
from foundation.db import apply_schema
asyncio.run(apply_schema())
"@
& $VenvPython -c $schemaScript
if ($LASTEXITCODE -eq 0) {
    Ok "DB schema up to date"
} else {
    Warn "Schema apply failed — will retry on server start"
}

# -- 5. Ollama (optional) ----------------------------------------------------------
function Test-Ollama {
    try { (Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -UseBasicParsing -TimeoutSec 2) | Out-Null; return $true }
    catch { return $false }
}

if (Test-Ollama) {
    Ok "Ollama ready"
} elseif (Get-Command ollama -ErrorAction SilentlyContinue) {
    Warn "Ollama installed but not running — starting..."
    Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden
    $tries = 0
    while (-not (Test-Ollama) -and $tries -lt 20) { Start-Sleep 1; $tries++ }
    if (Test-Ollama) { Ok "Ollama ready" } else { Warn "Ollama not responding — set ANTHROPIC_API_KEY in server\.env to use Claude cloud instead" }
} else {
    Warn "Ollama not installed — set ANTHROPIC_API_KEY in server\.env to use Claude cloud instead (or: winget install Ollama.Ollama)"
}

# -- 6. Kill any stale Parth process ------------------------------------------------
if (Test-Path $PidFile) {
    $OldPid = Get-Content $PidFile
    Stop-Process -Id $OldPid -ErrorAction SilentlyContinue
    Remove-Item $PidFile -ErrorAction SilentlyContinue
}
Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep 1

# -- 7. Start Parth server -----------------------------------------------------------
Info "Starting Parth server..."
Set-Location $ServerDir
$proc = Start-Process -FilePath $VenvPython `
    -ArgumentList "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "$Port", "--log-level", "info" `
    -RedirectStandardOutput $Log -RedirectStandardError "$Log.err" `
    -PassThru -WindowStyle Hidden
$proc.Id | Set-Content $PidFile

Write-Host -NoNewline "  Waiting for server"
$up = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        Invoke-WebRequest -Uri "http://localhost:$Port/health" -UseBasicParsing -TimeoutSec 2 | Out-Null
        $up = $true; break
    } catch { Write-Host -NoNewline "."; Start-Sleep 1 }
}
if ($up) { Write-Host ""; Ok "Parth is UP (pid $($proc.Id))" } else { Die "Server failed to start — check: Get-Content $Log -Tail 30" }

# -- 8. Mobile app (Flutter) ----------------------------------------------------------
if (-not $ServerOnly) {
    if (Get-Command flutter -ErrorAction SilentlyContinue) {
        Info "Preparing Flutter app..."
        Push-Location $AppDir
        flutter pub get *> "$env:TEMP\parth_flutter.log"
        if ($LASTEXITCODE -eq 0) {
            Ok "Flutter deps ready"
        } else {
            Warn "flutter pub get failed — see $env:TEMP\parth_flutter.log"
        }
        if ($Mobile) {
            $devices = flutter devices 2>$null
            if ($devices -match '•.*•') {
                Info "Launching app on a connected device/emulator..."
                flutter run
            } else {
                Warn "No device/emulator detected. Start one (Android Studio > Device Manager, or plug in a phone with USB debugging on) then run: cd app; flutter run"
            }
        } else {
            Info "Mobile app deps are ready. To launch it: cd app; flutter run  (or pass -Mobile to this script)"
        }
        Pop-Location
    } else {
        Warn "Flutter not installed — mobile app skipped. Install from https://docs.flutter.dev/get-started/install, then: cd app; flutter pub get; flutter run"
    }
}

# -- 9. Banner --------------------------------------------------------------------------
$LocalIp = try {
    (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
        Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
        Select-Object -First 1 -ExpandProperty IPAddress)
} catch { $null }
if (-not $LocalIp) { $LocalIp = "localhost" }
try {
    $health = Invoke-WebRequest -Uri "http://localhost:$Port/health" -UseBasicParsing | ConvertFrom-Json
    $Backend = $health.tutor_backend
    $Rag = $health.rag_chunks
} catch { $Backend = "?"; $Rag = 0 }

Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Cyan
Write-Host "                 PARTH AI  --  READY" -ForegroundColor Cyan
Write-Host "  ============================================================" -ForegroundColor Cyan
Write-Host "  Backend : $Backend   RAG chunks: $Rag"
Write-Host "  ------------------------------------------------------------"
Write-Host "  Web App  : http://${LocalIp}:${Port}/"
Write-Host "  Monitor  : http://${LocalIp}:${Port}/monitor"
Write-Host "  Demo     : http://${LocalIp}:${Port}/demo"
Write-Host "  World    : http://${LocalIp}:${Port}/playground"
Write-Host "  API Docs : http://${LocalIp}:${Port}/docs"
Write-Host "  ------------------------------------------------------------"
Write-Host "  Mobile   : cd app; flutter run"
Write-Host "  ------------------------------------------------------------"
Write-Host "  Logs  : $Log"
Write-Host "  Stop  : Stop-Process -Id (Get-Content `"$PidFile`")"
Write-Host "  ============================================================" -ForegroundColor Cyan
Write-Host ""
