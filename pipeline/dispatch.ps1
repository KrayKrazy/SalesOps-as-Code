# dispatch.ps1 — Executa UM disparo do SDR Kelevra e registra o log.
# Uso:  powershell -ExecutionPolicy Bypass -File dispatch.ps1            (envio real, 14 leads)
#       powershell -ExecutionPolicy Bypass -File dispatch.ps1 -Limit 14  (explícito)
#       powershell -ExecutionPolicy Bypass -File dispatch.ps1 -DryRun    (validação, não envia)
param(
    [int]$Limit = 14,
    [int]$WindowMinutes = 0,
    [switch]$DryRun
)
$ErrorActionPreference = 'Continue'

$root   = Split-Path -Parent $PSScriptRoot          # C:\mycelium\SalesOps-as-Code
$py     = 'C:\Users\Solano\AppData\Local\Programs\Python\Python312\python.exe'
$pipe   = Join-Path $root 'pipeline\sdr_pipeline.py'
$logDir = Join-Path $root 'logs'
if (-not (Test-Path -LiteralPath $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
$stamp  = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'
$log    = Join-Path $logDir ("dispatch_" + $stamp + ".log")

# Janela aleatoria (anti-ban): dorme um tempo aleatorio antes de disparar.
$sleepSeconds = 0
if ($WindowMinutes -gt 0) {
    $sleepSeconds = Get-Random -Minimum 0 -Maximum ($WindowMinutes * 60)
    Start-Sleep -Seconds $sleepSeconds
}

if ($DryRun) {
    $pyArgs = @($pipe, '--limit', $Limit)
} else {
    $pyArgs = @($pipe, '--send', '--limit', $Limit)
}

Push-Location (Join-Path $root 'pipeline')
try {
    $output = & $py @pyArgs 2>&1 | Out-String
} finally {
    Pop-Location
}

$output | Out-File -LiteralPath $log -Encoding utf8

$allLog = Join-Path $logDir 'dispatch_all.log'
Add-Content -LiteralPath $allLog -Value ("===== " + $stamp + " | Limit=" + $Limit + " | WindowMin=" + $WindowMinutes + " | SleepSec=" + $sleepSeconds + " | DryRun=" + $DryRun + " =====")
Add-Content -LiteralPath $allLog -Value $output
