# Active Context — 29/09/2026

## Sendo feito
- Pipeline operacional contra o Supabase cloud (dry-run validado: round-robin lê
  `whatsapp_instances`, DeepSeek gera abertura, validação WhatsApp ao vivo).
- GitOps consolidado: `main` sincronizado com origin (`ef165b1`).

## Bloqueador (infraestrutura do servidor)
- PostgREST do Supabase do servidor retorna **503 PGRST002** ("Could not query the
  database for the schema cache"). Auth (Kong) passa, mas o `PGRST_DB_URI` do
  container PostgREST está divergente (host/porta/senha do `authenticator`).
- **Expiração do JWT = 3600s** no painel icpanel → chaves anon/service expiram em 1h.
- Ambas exigem ação do dono no icpanel (não há acesso SSH à VPS).

## Próximos passos
1. Dono: no icpanel, corrigir `PGRST_DB_URI` do PostgREST + reiniciar stack.
2. Dono: mudar "Expiração do JWT" para valor longo e regenerar anon/service keys.
3. Apontar `pipeline/.env` para `supabase.vps10393.panel.icontainer.run`.
4. Validar pipeline E2E contra o servidor.
