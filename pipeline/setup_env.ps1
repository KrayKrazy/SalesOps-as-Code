# setup_env.ps1 — Gera o .env real do pipeline a partir do cofre local.
# =============================================================================
# Fontes:
#   1) C:\mycelium\.env               (Supabase + Evolution)
#   2) C:\mycelium\env\todas as apis.txt.enc  (chave DeepSeek, via DPAPI)
# Saida: pipeline\.env (NUNCA commitar — protegido pelo .gitignore)
# Uso:  powershell -ExecutionPolicy Bypass -File pipeline\setup_env.ps1
# =============================================================================
$ErrorActionPreference = 'Stop'

$masterPath = 'C:\mycelium\.env'
$vaultPath  = 'C:\mycelium\env\todas as apis.txt.enc'
$target     = Join-Path $PSScriptRoot '.env'

# 1) Ler master .env para um hashtable (sem expor valores no console)
$master = @{}
if (Test-Path -LiteralPath $masterPath) {
    foreach ($line in [System.IO.File]::ReadAllLines($masterPath)) {
        $t = $line.Trim()
        if ($t -eq '' -or $t.StartsWith('#')) { continue }
        $i = $t.IndexOf('=')
        if ($i -gt 0) {
            $k = $t.Substring(0, $i).Trim()
            $v = $t.Substring($i + 1).Trim()
            $master[$k] = $v
        }
    }
}

# 2) Extrair chave DeepSeek do cofre (DPAPI do Windows, mesmo usuario/maquina)
$deepseekKey = ''
if (Test-Path -LiteralPath $vaultPath) {
    Add-Type -AssemblyName System.Security
    $encBytes = [System.IO.File]::ReadAllBytes($vaultPath)
    $scope    = [System.Security.Cryptography.DataProtectionScope]::CurrentUser
    $decBytes = [System.Security.Cryptography.ProtectedData]::Unprotect($encBytes, $null, $scope)
    $vaultTxt = [System.Text.Encoding]::UTF8.GetString($decBytes)
    $m = [regex]::Match($vaultTxt, 'deepseek:\s*(sk-[A-Za-z0-9]+)', 'IgnoreCase')
    if ($m.Success) { $deepseekKey = $m.Groups[1].Value }
}

# 3) Valores finais (master sobrepoe default; vazio fica vazio para aviso)
$cfg = [ordered]@{
    'SUPABASE_PROJECT_URL' = 'https://omdieogddacchiihjqyl.supabase.co'
    'SUPABASE_SECRET_KEY'  = ''
    'DEEPSEEK_API_KEY'     = $deepseekKey
    'EVOLUTION_BASE_URL'   = 'https://evo.vps10393.panel.icontainer.run'
    'EVOLUTION_API_KEY'    = ''
    'EVO_INSTANCE'         = ('N' + [char]0xFA + 'mero comercial')
    'SDR_STATUS_SENT'      = 'contatado'
    'SDR_STATUS_ERROR'     = 'erro'
    'SDR_QUOTA_PER_INSTANCE' = '48'
    'SDR_DAILY_LEAD_CAP'   = '50'
}
foreach ($k in @($cfg.Keys)) {
    if ($master.ContainsKey($k) -and $master[$k] -ne '') { $cfg[$k] = $master[$k] }
}
# A chave Supabase correta para o projeto cloud omdieogddacchiihjqyl e a *_PROJ
if ($master.ContainsKey('SUPABASE_SECRET_KEY_PROJ') -and $master['SUPABASE_SECRET_KEY_PROJ'] -ne '') {
    $cfg['SUPABASE_SECRET_KEY'] = $master['SUPABASE_SECRET_KEY_PROJ']
}
# A chave Evolution correta (produção) e a *_NEW
if ($master.ContainsKey('EVOLUTION_API_KEY_NEW') -and $master['EVOLUTION_API_KEY_NEW'] -ne '') {
    $cfg['EVOLUTION_API_KEY'] = $master['EVOLUTION_API_KEY_NEW']
}

# 4) Gravar .env (UTF-8 sem BOM)
$sb = New-Object System.Text.StringBuilder
[void]$sb.AppendLine('# KELEVRA SALESOPS — .env real (gitignored). Gerado por setup_env.ps1.')
foreach ($k in @($cfg.Keys)) {
    [void]$sb.AppendLine(("{0}={1}" -f $k, $cfg[$k]))
}
[System.IO.File]::WriteAllText($target, $sb.ToString(), (New-Object System.Text.UTF8Encoding($false)))

# 5) Relatorio (somente nomes + preenchimento, sem valores)
Write-Host ("Escrito: " + $target)
Write-Host 'Chaves gravadas:'
foreach ($k in @($cfg.Keys)) {
    $filled = if ($cfg[$k] -ne '') { '[OK]' } else { '[VAZIO - preencher]' }
    Write-Host ("  {0,-26} {1}" -f $k, $filled)
}
