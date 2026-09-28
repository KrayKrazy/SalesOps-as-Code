# System Patterns — Kelevra SalesOps

## Schema Supabase (PORTUGUÊS — não renomear)
- leads (base enriquecida GMN) — 1000+ regs
- cold_leads (fila SDR) — dify_conversation_id, is_bot_active
- messages_log (entrega) — direction, delivered_at, read_at
- blocked_numbers / blocked_contacts (blocklist)
- webhook_queue (fila de entrada)
- vw_leads_para_prospectar (view de prospecção)

## Padrões
- Idempotência: telefone normalizado + status check antes de enviar.
- Anti-ban: quota 48/dia/chip, round-robin, quarentena.
- LGPD: blocklist + opt-out ("SAIR") + retenção 180d.
- Observabilidade: messages_log + trace_id.

## Migração v3.0
supabase/migrations/0001_salesops_v3_reconcile.sql (additive, aguarda senha DB).
