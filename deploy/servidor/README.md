# Deploy no servidor (Opção B) — Kelevra SalesOps

Este pacote instala o **pipeline Python** no servidor Linux e agenda os disparos
via **cron**, eliminando a dependência do notebook ficar ligado.

## O que cada arquivo faz

| Arquivo | Papel |
| :--- | :--- |
| `pipeline/*.py` | Motor do SDR (100% stdlib — não precisa instalar dependências) |
| `.env.servidor` | Config/segredos do servidor (copiado para `pipeline/.env` pelo deploy) |
| `dispatch.sh` | Wrapper de 1 disparo com **janela aleatória anti-ban** |
| `deploy.sh` | Instalador: cria diretórios, copia arquivos, grava o cron |

## Pré-requisitos no servidor

- Linux com **Python 3.8+** (só biblioteca padrão).
- Acesso **root** (ou `sudo`) para gravar `/etc/cron.d/kelevra`.
- `cron` (ou `cronie`) ativo.
- Fuso do servidor ajustado para `America/Sao_Paulo` (o `deploy.sh` tenta ajustar).

## Como instalar

### 1) Enviar o pacote para o servidor

Via SSH/SCP (recomendado):

```bash
# No seu PC (Windows), com o arquivo tar.gz gerado:
scp kelevra-servidor.tar.gz root@<IP_DO_SERVIDOR>:/root/

# No servidor:
cd /root
tar xzf kelevra-servidor.tar.gz
cd kelevra-servidor
```

### 2) Rodar o instalador

```bash
sudo bash deploy.sh
```

O instalador cria `/opt/kelevra/` e grava `/etc/cron.d/kelevra`.

### 3) Testar antes do primeiro disparo real (dry-run)

```bash
cd /opt/kelevra/pipeline
python3 sdr_pipeline.py --limit 3          # dry-run: NÃO envia
python3 corretor.py                          # auditoria de entrega
```

### 4) Conferir o agendamento

```bash
cat /etc/cron.d/kelevra
tail -f /opt/kelevra/logs/dispatch_all.log
```

## O que fica agendado (cron)

| Tarefa | Quando | Comando |
| :--- | :--- | :--- |
| Disparo Manhã | 08:30 + 0–120 min (aleatório) | `dispatch.sh 14 120` |
| Disparo Tarde | 13:30 + 0–120 min (aleatório) | `dispatch.sh 14 120` |
| Disparo Noite | 18:30 + 0–120 min (aleatório) | `dispatch.sh 14 120` |
| Inbound Sync | a cada 30 min | `inbound_sync.py` |
| Follow-up (opcional) | descomentado manualmente | `followup_pipeline.py --send --limit 5` |

- Cada disparo envia **14 mensagens**; total **42/dia** (dentro do cap `SDR_DAILY_LEAD_CAP=50`).
- Intervalo **2–4 min** entre mensagens (anti-ban) — dentro do `sdr_pipeline.py`.

## Comandos úteis (rodando no servidor)

```bash
cd /opt/kelevra/pipeline

# Disparo manual real (14):
python3 sdr_pipeline.py --send --limit 14

# Capturar respostas (inbound) agora:
python3 inbound_sync.py

# Lista priorizada de quem respondeu:
python3 respondentes.py
python3 respondentes.py --export respondentes.csv

# Follow-up (2º toque) manual:
python3 followup_pipeline.py --send --limit 5

# Importar respondentes de um txt (lista manual):
#   edite /opt/kelevra/respondentes.txt (um por linha: nome + telefone)
python3 importar_respondentes.py --dry-run
python3 importar_respondentes.py

# Bloquear clientes fechados:
#   edite /opt/kelevra/fechados.txt (um por linha)
python3 block_closed.py --dry-run
python3 block_closed.py
```

## Ativar o follow-up automático (opcional)

Quando quiser que o 2º toque rode sozinho, descomente a linha no
`/etc/cron.d/kelevra`:

```
*/30 * * * * root cd /opt/kelevra/pipeline && python3 followup_pipeline.py --send --limit 5 >> /opt/kelevra/logs/followup.log 2>&1
```

## Pausar / desativar (sem apagar)

```bash
# Pausar tudo:
sudo mv /etc/cron.d/kelevra /etc/cron.d/kelevra.disabled

# Reativar:
sudo mv /etc/cron.d/kelevra.disabled /etc/cron.d/kelevra
```

## IMPORTANTE — desativar o motor do notebook

Depois de validar o servidor, **desative as tarefas do Windows** para não haver
dois motores disputando os mesmos leads (disparo duplicado):

```powershell
# No notebook (PowerShell):
Disable-ScheduledTask -TaskName 'Kelevra SDR - Manha','Kelevra SDR - Tarde','Kelevra SDR - Noite','Kelevra SDR - Inbound Sync'
```

## Segurança

- `.env.servidor` contém segredos (chaves DeepSeek/Evolution/JWT). Está coberto
  pelo `.gitignore` (padrão `.env.*`). **Não commitar/pushar.**
- Mantenha o `.env` do servidor com `chmod 600` (o `deploy.sh` já faz isso).
