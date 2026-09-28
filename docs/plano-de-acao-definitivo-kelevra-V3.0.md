# PLANO DE AÇÃO DEFINITIVO — ECOSSISTEMA KELEVRA (SALESOPS-AS-CODE)

**Documento de Engenharia — Nível Playbook — Versão 3.0 (Definitiva)**

| Campo | Valor |
| :--- | :--- |
| Código | KELEVRA-SALESOPS-MA-001 |
| Versão | **3.0 Definitiva** (consolida v1.0 + v2.0 + análise + diagnóstico de produção real) |
| Data | 28/09/2026 |
| Base de raciocínio | DeepSeek (saldo verificado: US$9,89) |
| Repositório | https://github.com/KrayKrazy/SalesOps-as-Code (local: `C:\mycelium\SalesOps-as-Code`) |

**Changelog:** v1.0 (5 agentes, 10 estados) → v2.0 (26 correções: schema 11 tabelas, LGPD engenharia, anti-ban, Langfuse) → **v3.0 (reconciliação com a produção REAL: schema PT existente, serviços UP, dados reais)**.

---

## 1. Sumário Executivo

A Kelevra roda um motor comercial multi-agente (Coletar → Prospectar → Qualificar → Agendar → Corrigir) sobre **DeepSeek + Dify + n8n + Evolution API + Supabase**. A auditoria de 28/09 — com acesso real aos serviços — concluiu que o sistema **já está em produção e operante**, porém com **desvio estrutural** entre o que v1.0/v2.0 prescrevem e o que está implementado.

**Estado real verificado:**

| Serviço | Status | Evidência |
| :--- | :---: | :--- |
| DeepSeek API | ✅ UP | `GET /user/balance` → US$9,89; chat `OK` (`deepseek-flash`) |
| Evolution API | ✅ UP | `https://evo.vps10393.panel.icontainer.run` → 200 |
| n8n | ✅ UP | `/healthz` → `{"status":"ok"}` |
| Dify | ✅ UP | `dify.kelevra.shop` → 308 (→ https) |
| Supabase cloud | ✅ UP | `omdieogddacchiihjqyl.supabase.co` via `sb_secret_` + UA servidor |
| Supabase VPS | ⚠️ | Cert autoassinado (não é o alvo primário) |

**Conclusão:** não é greenfield. É **consolidar, corrigir schema e destravar o escalonamento seguro** de um sistema que já captura e qualifica leads.

---

## 2. Diagnóstico de Produção (Gap Assessment)

### 2.1 Schema REAL (Supabase cloud)

| Tabela/View | Colunas reais | Observação |
| :--- | :--- | :--- |
| `cold_leads` | id, nome, telefone, nicho, status, created_at, dify_conversation_id, is_bot_active, last_interaction_at, chatwoot_conversation_id, failed_attempts | Fila SDR ativa (≈16 regs, `pendente`) |
| `leads` | id, nome, telefone, status, origem, criado_em, category, subcategory, bairro, cidade, gmn_rating, gmn_reviews, gmn_has_website, audit_score, fonte, created_at, stage, fase_venda, notion_page_id, nicho_kelevra | Base principal (1000+ regs) |
| `webhook_queue` | id, remote_jid, payload, status, created_at | Fila (sem `message_id`) |
| `blocked_numbers` | id, phone, reason, blocked_at | Blocklist |
| `blocked_contacts` | phone, name, status, created_at | Blocklist auxiliar |
| `messages_log` | id, lead_id, telefone, direction, message_type, content, status, error_details, http_response, campaign_id, workflow_name, follow_up_num, sent_at, delivered_at, read_at, created_at | Log rico de entrega |
| `vw_leads_para_prospectar` | id, nome, telefone, category, subcategory, bairro, cidade, gmn_rating, gmn_reviews, gmn_has_website, audit_score, fonte, created_at | **View pronta de prospecção** |

### 2.2 O desvio estrutural (a correção da v3.0)

| Aspecto | Plano (ideal) | Produção (real) | Decisão v3.0 |
| :--- | :--- | :--- | :--- |
| Idioma schema | Inglês (`name`,`phone`,`category`) | **Português** (`nome`,`telefone`,`nicho`) | **Manter PT** (renomear quebraria n8n/Dify) |
| Tabela principal | `cold_leads` (11 tabelas) | `leads` (rica) + `cold_leads` (fila) | Manter as duas |
| Estados | 14 estados EN | `leads.status` PT + `leads.stage` | **Manter PT**, mapear semanticamente |
| Blocklist | `blocklist` | `blocked_numbers` + `blocked_contacts` | Usar as existentes |
| Observabilidade | Langfuse + `trace_id` | `messages_log` (delivered/read) | +`trace_id` em `messages_log` |
| Anti-ban | `whatsapp_instances` | Não existe | **Criar** (additive) |
| Auditoria | `agent_runs`/`error_log`/`audit_log` | `messages_log` cobre parte | **Criar** (additive) |

### 2.3 Bloqueadores

1. 🔴 **Senha do Postgres do Supabase cloud desconhecida** — as 4 senhas do cofre falharam. Sem ela **não há DDL**. Mitigação: REST acessível (ler/escrever dados), mas não cria tabela/coluna.
2. ⚠️ **`SalesOps-as-Code` quase vazio** — artefatos reais vivem em `C:\mycelium\agente_sdr` e `scripts`, fora do Git.
3. ⚠️ **Risco Meta/WhatsApp ToS** — manter handoff híbrido + decision gate.

## 3. Decisões de Arquitetura (Definitivas)

1. **Fonte canônica de estado de lead:** Supabase cloud (`omdieogddacchiihjqyl`), schema PT + acréscimos additive (§6). **Nunca renomear colunas/status em produção.**
2. **`leads` vs `cold_leads`:** `leads` = base enriquecida (GMN/auditoria); `cold_leads` = fila SDR ativa. Pipeline lê de `vw_leads_para_prospectar`.
3. **CRM Agentico (`crm_src`):** espelho de negócio (Contact/Deal/Company), não fonte de estado. Sync unidirecional `leads → crm_src` via `crm_external_id`.
4. **Canal WhatsApp:** híbrido — chip frio (Evolution, 48/dia) + handoff inbound WABA oficial. **Decision gate:** só escala 50→150→300 se `delivered_rate ≥ 0,95` e 0 bans.
5. **LLM:** 100% DeepSeek (`deepseek-flash` p/ conversa/rotina; `deepseek-reasoner` p/ scoring/causa-raiz). Saldo US$9,89.
6. **Observabilidade:** `messages_log` + `trace_id` (Langfuse self-host = melhoria posterior, não bloqueante).

---

## 4. Roadmap Priorizado

| # | Marco | Conteúdo | Status |
| :---: | :--- | :--- | :---: |
| M0 | Consolidar repositório | Versionar `agente_sdr/`, prompts, workflows no `SalesOps-as-Code` | 🟡 |
| M1 | Destravar DDL | Resetar senha Postgres no dashboard Supabase (ação do dono) | 🔴 |
| M2 | Aplicar migração | §6 (colunas ICP/anti-ban + tabelas novas) | ⏸ pronto |
| M3 | Memory Bank + .clinerules | Economizar tokens DeepSeek | ✅ |
| M4 | Validar pipeline E2E | Lead pendente → DeepSeek → Evolution → `messages_log` | ⏸ |
| M5 | Anti-ban | `whatsapp_instances` quota 48, round-robin, quarentena | ⏸ |
| M6 | Go-live gradual | 10→50→150→300 com decision gate | ⏸ |

---

## 5. Riscos

| Risco | P | I | Resposta |
| :--- | :---: | :---: | :--- |
| Banimento WhatsApp (Meta ToS) | Alta | Alto | Handoff híbrido + quota + decision gate |
| Schema EN×PT divergente | Alta | Médio | Migração additive, nunca renomear |
| Senha DB desconhecida | Certa | Alto | Reset no dashboard (dono) |
| Custo token descontrolado | Média | Baixo | Memory Bank + Context Caching + flash |
| `SalesOps-as-Code` fora de sync | Alta | Médio | GitOps (M0) |

---

## 6. Migração de Schema Reconciliada

Arquivo: `C:\mycelium\SalesOps-as-Code\supabase\migrations\0001_salesops_v3_reconcile.sql`

**Princípios:** nunca renomear; nunca excluir; tudo `IF NOT EXISTS`; colunas novas em inglês técnico coexistem com o PT.

**Efeito:** `cold_leads` +21 colunas; novas tabelas `whatsapp_instances`, `agent_runs`, `error_log`, `audit_log`; `messages_log` +`trace_id`; índices de performance.

---

## 7. KPIs

| Métrica | Alvo | Fonte |
| :--- | :---: | :--- |
| Delivered rate | ≥ 0,95 | `messages_log.delivered_at/sent_at` |
| Bans de chip | 0 | `whatsapp_instances.status` |
| Taxa de resposta | ≥ 15% | `messages_log.direction='inbound'` |
| Conversão resposta→reunião | ≥ 25% | `leads.fase_venda` |
| Show-up | ≥ 60% | agenda Cal.com |
| Leads/dia | ≥ 300 | `leads.created_at` |

---

## 8. Próximas Ações Imediatas

1. ✅ Validar DeepSeek (US$9,89) e serviços UP.
2. ✅ Diagnosticar schema e dados reais.
3. ✅ Criar migração reconciliada (§6).
4. ✅ Criar Memory Bank + `.clinerules`.
5. 🔴 **Ação do dono:** resetar senha do Postgres do Supabase cloud e informar, para aplicar a migração (M2).

---

*Documento v3.0 gerado em 28/09/2026 a partir de auditoria real do ambiente. Referências: `C:\mycelium\agente_sdr\*`, `C:\mycelium\scripts\*`, `C:\mycelium\crm_src\*`, Supabase cloud `omdieogddacchiihjqyl`, Evolution/n8n/Dify UP.*
