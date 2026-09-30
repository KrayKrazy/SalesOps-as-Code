# Progress — Kelevra SalesOps

## Concluído (28/09 → 29/09/2026)
- [x] Auditar serviços (DeepSeek/Evolution/n8n/Dify/Supabase UP).
- [x] Mapear schema real + dados.
- [x] Escrever plano definitivo v3.0.
- [x] Criar migração reconciliada (0001).
- [x] Inicializar Memory Bank.
- [x] Higienização (1.016 números → 766 válidos / 250 bloqueados).
- [x] Validação de WhatsApp ao vivo no pipeline.
- [x] Migrar dados do cloud → Supabase do servidor (4.450 linhas).
- [x] Anti-ban round-robin por instância (M5) — commit `df3936a`.
- [x] Corrigir n8n Outbound (credential + campos status/stage) — commit `ef165b1`.
- [x] GitOps: token removido, SSH OK, `main` sincronizado (`ef165b1`).

## Pendente
- [ ] **PostgREST do servidor: 503 PGRST002** (schema cache) — ação do dono no icpanel.
- [ ] **Expiração do JWT = 3600s** no painel → regenerar chaves long-lived (dono).
- [ ] Apontar pipeline `.env` para o servidor (após PostgREST corrigido).
- [ ] Reimportar Dify GMN SDR Agent (DeepSeek) e n8n Outbound.
- [ ] Go-live gradual (decision gate: delivered_rate ≥ 0,95 + 0 bans).
