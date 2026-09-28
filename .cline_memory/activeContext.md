# Active Context — 28/09/2026

## Sendo feito
- Plano definitivo v3.0 escrito (prospeccao/plano-de-acao-definitivo-kelevra-V3.0.md).
- Migração reconciliada criada (supabase/migrations/0001_salesops_v3_reconcile.sql).
- Memory Bank + .clinerules inicializados.

## Bloqueador
- Senha do Postgres do Supabase cloud desconhecida (4 senhas do cofre falharam).
  → Dono precisa resetar no dashboard para aplicar a migração (DDL).

## Próximos passos
1. Resetar senha DB (dono).
2. Aplicar migração 0001.
3. Validar pipeline E2E (lead → DeepSeek → Evolution → messages_log).
