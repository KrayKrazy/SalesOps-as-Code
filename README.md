# Kelevra Corp — SalesOps as Code

Motor comercial multi-agente: **Coletar → Prospectar → Qualificar → Agendar → Corrigir**
sobre DeepSeek + Supabase + Evolution API (WhatsApp) + Dify + n8n.

## Estrutura
- `pipeline/` — orquestrador executável (100% stdlib, sem dependências)
  - `kelevra.py` — núcleo compartilhado (Supabase REST, DeepSeek, Evolution, logging)
  - `sdr_pipeline.py` — outbound: lê leads → blocklist → dedupe → [score] → abertura → envia → loga
  - `corretor.py` — agente de auditoria/retroalimentação (taxa de entrega + falhas)
  - `inbound_sync.py` — captura respostas (inbound) da Evolution → `messages_log`
  - `respondentes.py` — lista priorizada de respondentes + soft delete (finalizar)
  - `followup_pipeline.py` — follow-up automático (2º toque) + marca `finalizado`
  - `importar_respondentes.py` — importa respondentes de um `.txt` → `messages_log`
  - `block_closed.py` — bloqueia clientes fechados (via `C:\mycelium\fechados.txt`)
  - `setup_env.ps1` — gera o `.env` real a partir do cofre local
  - `.env.example` — template (o `.env` real é gitignored)
- `supabase/migrations/` — migrações idempotentes (DDL)
- `n8n_workflows_kelevra/` — workflows n8n
- `agente_sdr/` — prompts/chatflow Dify
- `pitch/` — knowledge base (FAQ + produtos)

## Configuração (uma vez)
```powershell
powershell -ExecutionPolicy Bypass -File pipeline\setup_env.ps1
```
Lê `C:\mycelium\.env` + o cofre `C:\mycelium\env\todas as apis.txt.enc` (DPAPI)
e grava `pipeline\.env` (nunca commitar — protegido pelo `.gitignore`).

## Executar
```powershell
cd C:\mycelium\SalesOps-as-Code

# DRY-RUN (não envia, só gera e valida):
python pipeline\sdr_pipeline.py

# Com scoring ICP (DeepSeek reasoner):
python pipeline\sdr_pipeline.py --score

# ENVIO REAL (com cuidado):
python pipeline\sdr_pipeline.py --send --limit 5

# Auditoria / Corretor:
python pipeline\corretor.py
python pipeline\corretor.py --list-failed
```

## Anti-ban / segurança
- Cap diário de disparos (`SDR_DAILY_LEAD_CAP`, padrão 50).
- Round-robin entre instâncias ativas (`whatsapp_instances`) com quota por instância
  (`SDR_QUOTA_PER_INSTANCE`, padrão 48). Instâncias em cooldown/quarentena são puladas.
- Blocklist (`blocked_numbers`/`blocked_contacts`) e dedupe de 72h.
- Sem `--send` é sempre dry-run (nunca envia).

## Bloqueador conhecido
- DDL (tabelas `whatsapp_instances`, `agent_runs`, `error_log`, `audit_log`) depende de
  aplicar `supabase/migrations/0001_salesops_v3_reconcile.sql` no Supabase cloud
  (resetar senha Postgres no dashboard). O pipeline funciona sem elas (degradação graciosa).

## Bloqueio de clientes fechados + agendamento

```powershell
# 1) Bloquear clientes que já fecharam (txt em C:\mycelium\fechados.txt, um por linha):
python pipeline\block_closed.py --dry-run
python pipeline\block_closed.py

# 2) Registrar os 3 disparos diários (janelas aleatórias: 08:30-10:30 / 13:30-15:30 / 18:30-20:30):
powershell -ExecutionPolicy Bypass -File pipeline\schedule.ps1

# 3) Executar 1 disparo manualmente (envio real de 14) com log em logs\:
powershell -ExecutionPolicy Bypass -File pipeline\dispatch.ps1
powershell -ExecutionPolicy Bypass -File pipeline\dispatch.ps1 -DryRun
```

- `sdr_pipeline.py --limit N` agora significa "enviar **N** mensagens" (faz overfetch e
  para no alvo), compensando leads bloqueados/duplicados/sem WhatsApp.
- O txt de fechados é lido como blocklist local em memória a cada execução.
- Horário aleatório dentro da janela (`dispatch.ps1 -WindowMinutes`) + intervalo de
  **2–4 min** entre mensagens (`SDR_SEND_INTERVAL_MIN/MAX`) — ambos anti-ban.
