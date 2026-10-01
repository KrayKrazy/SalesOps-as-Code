# schedule.ps1 — Registra os 3 disparos diarios (ALEATORIOS dentro de janelas).
# Cada tarefa dispara no INICIO da janela; o dispatch.ps1 dorme um tempo aleatorio
# (0..WindowMin) antes de enviar, tornando o horario real imprevisivel (anti-ban).
# Janelas (hora local / Brasilia):
#   Manha 08:30-10:30 | Tarde 13:30-15:30 | Noite 18:30-20:30
# Para mudar, edite abaixo e rode novamente (com -Force reescreve).
$ErrorActionPreference = 'Stop'

$dispatch = 'C:\mycelium\SalesOps-as-Code\pipeline\dispatch.ps1'
$pwsh     = 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
$windowMin = 120   # minutos de aleatoriedade (janela de disparo)

$horarios = @(
    @{ Name = 'Kelevra SDR - Manha'; Hour = 8;  Minute = 30 },
    @{ Name = 'Kelevra SDR - Tarde'; Hour = 13; Minute = 30 },
    @{ Name = 'Kelevra SDR - Noite'; Hour = 18; Minute = 30 }
)

foreach ($h in $horarios) {
    $arg = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $dispatch + '" -WindowMinutes ' + $windowMin

    $action    = New-ScheduledTaskAction -Execute $pwsh -Argument $arg
    $trigger   = New-ScheduledTaskTrigger -Daily -At (Get-Date -Hour $h.Hour -Minute $h.Minute -Second 0)
    $settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 200)
    $principal = New-ScheduledTaskPrincipal -UserId ("$env:USERDOMAIN\" + $env:USERNAME) `
        -LogonType Interactive -RunLevel Limited

    Register-ScheduledTask -TaskName $h.Name -Action $action -Trigger $trigger `
        -Settings $settings -Principal $principal -Force | Out-Null
    Write-Host ("Registrado: {0} | inicio {1:00}:{2:00} + ate {3}min" -f $h.Name, $h.Hour, $h.Minute, $windowMin)
}
# Inbound Sync (captura respostas da Evolution) — a cada 30 min
$py      = 'C:\Users\Solano\AppData\Local\Programs\Python\Python312\python.exe'
$inbound = 'C:\mycelium\SalesOps-as-Code\pipeline\inbound_sync.py'
$iAction    = New-ScheduledTaskAction -Execute $py -Argument ('"' + $inbound + '"') -WorkingDirectory 'C:\mycelium\SalesOps-as-Code\pipeline'
$iTrigger   = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 30)
$iSettings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
$iPrincipal = New-ScheduledTaskPrincipal -UserId ("$env:USERDOMAIN\" + $env:USERNAME) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'Kelevra SDR - Inbound Sync' -Action $iAction -Trigger $iTrigger -Settings $iSettings -Principal $iPrincipal -Force | Out-Null
Write-Host 'Registrado: Kelevra SDR - Inbound Sync (a cada 30 min)'

Write-Host "Concluído. Para conferir: Get-ScheduledTask | Where-Object TaskName -like 'Kelevra SDR*'"
