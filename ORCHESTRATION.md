# ORQUESTRAÇÃO — Kelevra SalesOps (SalesOps-as-Code)

Motor comercial multi-agente: **Coletar → Prospectar → Qualificar → Agendar → Corrigir**.

## Mapa de agentes × componentes (estado verificado em 28/09/2026)

| Agente | Componente | Identificador | Status |
|---|---|---|---|
| 1. Coletor | Google Maps Scraper Kit | contêiner `gmaps-scraper` (VPS) | ✅ up |
| 2. Prospector | OpenSEO + DeepSeek | contêiner `openseo-open-seo-1` | ✅ up |
| 3. Qualificador SDR | Dify "SDR v2" (chatflow) | `app-spFBhC6pWmkjenZ4buAOJuWS` | ⚠️ migrar p/ DeepSeek |
| 3b. Orquestrador | Dify "GMN SDR Agent" | `app-FMHK9pnZJttxKbppgnnXBvHG` | ✅ agent-chat |
| 4. Agendador | Cal.com + forms | `agenda.kelevra.shop`, `forms.kelevra.shop` | ✅ up |
| 5. Corretor | n8n `Global Error Catcher` | `fUtzLR0YdEmBax0C` | ❌ inativo |
| Middleware | n8n MS-01/02/03/04 | WeiLqh8dtbAG1Wov, CelMsgRuDAWWYURA, o0FfyZg0AnoZKViV, uH9wAN6cCuc9sAU2 | ❌ inativos |
| Handoff | Chatwoot | `chatwoot.vps10393.panel.icontainer.run` | ✅ up |
| CRM espelho | Twenty + sync | workflow `48g1MCKpsbssuG4o` | ❌ inativo |

## Serviços (chaves ficam no `.env` local / cofre — NUNCA commitar)

- **DeepSeek** (LLM): base `api.deepseek.com`, modelos `deepseek-chat` / `deepseek-reasoner`.
- **Supabase** cloud `omdieogddacchiihjqyl`: migração v3.0 aplicada (11 tabelas + colunas ICP/anti-ban + `trace_id`).
- **Evolution API** (WhatsApp): `evo.vps10393.panel.icontainer.run`, instância `Número comercial`.
- **n8n**: `n8n.vps10393.panel.icontainer.run`.
- **Dify**: `dify.kelevra.shop`, 2 apps (`SDR v2` chatflow + `GMN SDR Agent`).

## Próximas ações (ordem)

1. Importar `agente_sdr/SDR_Kelevra_Chatflow_DeepSeek.yml` no Dify (substitui o "SDR v2" que está em OpenAI).
2. Revisar e reativar os workflows n8n: MS-01/02/03/04, Outbound SDR Machine, Firewall SDR Inbound, Global Error Catcher, Sync Supabase→Twenty.
3. Atualizar domínios do playbook (`api.kelevra.shop` / `n8n.kelevra.shop` → `*.vps10393.panel.icontainer.run`).
4. Rodar pipeline: `python pipeline/sdr_pipeline.py --dry-run` (valida) → `--send` (dispara).
