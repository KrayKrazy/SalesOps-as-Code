# Kelevra Corp — SalesOps as Code

Motor comercial multi-agente: **Coletar → Prospectar → Qualificar → Agendar → Corrigir**
sobre DeepSeek + Supabase + Evolution API (WhatsApp) + Dify + n8n.

## Estrutura
- `pipeline/` — orquestrador executável (100% stdlib, sem dependências)
  - `kelevra.py` — núcleo compartilhado (Supabase REST, DeepSeek, Evolution, logging)
  - `sdr_pipeline.py` — outbound: lê leads → blocklist → dedupe → [score] → abertura → envia → loga
  - `corretor.py` — agente de auditoria/retroalimentação (taxa de entrega + falhas)
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
