# Correção do Pipeline SDR Outbound — Prospecção + Qualificação

**Data:** 01/10/2026
**Escopo:** `C:\mycelium\SalesOps-as-Code\pipeline`
**Resultado:** o motor voltou a prospectar (ICP) e qualificar (abertura) sem o erro `402 Insufficient Balance`.

---

## Resumo executivo

A automação "não prospectava nem qualificava" por três bugs de código e uma sujeira de dados:

| # | Causa | Efeito | Correção |
|---|-------|--------|----------|
| 1 | Cliente DeepSeek apontando para **OpenRouter** em vez da API oficial da DeepSeek | toda geração/qualificação falhava com `DeepSeek HTTP 402` | endpoint corrigido para `https://api.deepseek.com` |
| 2 | `score_lead` (Prospector/ICP) com `max_tokens=200` | o `deepseek-reasoner` gastava os 200 tokens só no raciocínio e devolvia `content` vazio → `icp_score = 0` | `max_tokens` → 1024 |
| 3 | Agendador rodava sem `--score` | o nó "Prospector" nunca executava em produção | `--score` adicionado em `dispatch.ps1` e `dispatch.sh` |
| 4 | 37 leads com `nome` preenchido com UUID (sujeira de import) | abertura genérica/"robótica" e score baseado em nome vazio | `nome` limpo no banco (0 restantes) |

---

## 1. Causa raiz 1 — DeepSeek apontando para OpenRouter

### O que estava errado
Em `pipeline/kelevra.py`, a classe `DeepSeek` usava:

```python
self.client = HttpClient("https://openrouter.ai/api/v1", {...})
```

Mas a credencial configurada em `pipeline/.env` é da **DeepSeek oficial** (`DEEPSEEK_API_KEY=sk-...`) e os modelos são `deepseek-chat` / `deepseek-reasoner`.

Resultado: a chave DeepSeek era enviada ao OpenRouter, que respondia `402 Insufficient Balance` (conta inexistente/zerada) — por isso o qualificador nunca gerava a abertura.

### Evidência
- Log do disparo real de 30/09 (`logs/dispatch_2026-09-30_15-48-25.log`): `✗ geração falhou: DeepSeek HTTP 402: Insufficient Balance` (3x).
- Teste via API: a chave DeepSeek **é válida e tem saldo de US$ 3,73** em `https://api.deepseek.com/user/balance`; o OpenRouter **rejeita a mesma chave** com `401`.

### De onde veio o OpenRouter (resposta à dúvida)
O OpenRouter **não foi uma escolha sua**. Ele entrou no commit `5fca8ab` ("Refatoracao anti-spam e inicio da arquitetura V4.0"), feito pela IA anterior na noite de 30/09. O `git show` desse commit prova a troca:

```diff
- self.chat_model  = cfg.get("DEEPSEEK_CHAT_MODEL",  "deepseek-chat")
- self.reason_model = cfg.get("DEEPSEEK_REASON_MODEL", "deepseek-reasoner")
+ self.chat_model  = cfg.get("DEEPSEEK_CHAT_MODEL",  "deepseek/deepseek-chat")
+ self.reason_model = cfg.get("DEEPSEEK_REASON_MODEL", "deepseek/deepseek-chat")
  self.client = HttpClient(
-     "https://api.deepseek.com",
-     {"Authorization": "Bearer " + self.key},
+     "https://openrouter.ai/api/v1",
+     {
+         "Authorization": "Bearer " + self.key,
+         "HTTP-Referer": "https://kelevra.shop",
+         "X-Title": "Kelevra SalesOps"
+     },
```

Ou seja: a refatoração "anti-spam/V4" da IA anterior trocou o endpoint para OpenRouter **por engano** (e ainda introduziu um default errado para o reasoner). A correção reverte isso, mantendo compatibilidade com OpenRouter apenas se a chave começar com `sk-or-`.

### Correção aplicada em `kelevra.py`
- Endpoint padrão: `https://api.deepseek.com`.
- Defaults corretos: `deepseek-chat` / `deepseek-reasoner`.
- Auto-detecção: se `DEEPSEEK_API_KEY` começar com `sk-or-`, roteia para OpenRouter e prefixa os modelos com `deepseek/`.

---

## 2. Causa raiz 2 — Prospector (ICP) retornando score 0

`score_lead` usava `max_tokens=200` no `deepseek-reasoner`. Como o reasoner consome tokens no "raciocínio" antes de escrever a resposta final, os 200 tokens eram insuficientes: a resposta final saía vazia e o parser JSON devolvia `{}` → `icp_score=0`, `icp_reason=""`.

Evidência (teste direto):
- `max_tokens=200` → `reasoning_tokens=200`, `content=''`, `score=0`.
- `max_tokens=1024` → `score=88` (e `score=72` em outro lead), com justificativa completa.

**Correção:** `max_tokens` de 200 → **1024** em `score_lead`.

---

## 3. Causa raiz 3 — Agendador sem `--score`

O cron rodava `sdr_pipeline.py --send --limit 14` **sem** `--score`, então o nó de ICP (Prospector) nunca era acionado em produção.

**Correção:** adicionado `--score` em:
- `pipeline/dispatch.ps1`
- `deploy/servidor/dispatch.sh`

---

## 4. Sujeira de dados — `nome` preenchido com UUID (37 leads)

### Diagnóstico
37 leads na tabela `leads` tinham o campo `nome` preenchido com UUID de lote, não com o nome do negócio:

- `aa0d7e52-ac4d-4911-ae54-7886abb58e1e` (25 leads)
- `a66e6344-5eb0-4a5f-886b-8c4d557b4868` (12 leads)

Todos com origem `Sniper` / fonte `Apify Goiânia`, importados em `2026-09-28`. O scraper da Apify gravou um UUID (id do dataset/run) no lugar do nome — o nome real não está disponível em nenhuma outra coluna.

### Executado
- `UPDATE` (via PostgREST `PATCH`) dos 37 leads: `nome = ""`.
- Verificação pós-correção: **`REMAINING_UUID_NAMES = 0`** (de 1978 leads totais).

### Mitigação no código
Adicionado `display_name()` em `kelevra.py`: se `nome` for um UUID, é tratado como vazio. Assim, mesmo que novas importações tragam o mesmo problema, a abertura nunca sai endereçada a um UUID.

---

## 5. Blocklist — revisão recomendada (NÃO revertida automaticamente)

Estado atual da blocklist (Supabase self-hosted):

| Tabela | Qtd | Motivo |
|--------|-----|--------|
| `blocked_numbers` | 281 | `sem_whatsapp_29-09-2026` = 250 · `sem_whatsapp_auto` = 18 · `cliente_fechado` = 13 |
| `blocked_contacts` | 16 | `pago` (clientes fechados) |

**Atenção:** os 250 registros `sem_whatsapp_29-09-2026` foram gravados em lote pela higienização de 29/09. Se a instância da Evolution estava desconectada/instável naquele momento, o `/chat/whatsappNumbers` pode ter retornado `exists:false` para números válidos → **falso bloqueio em massa**.

Isso é coerente com o disparo de 30/09, em que 39 de 42 leads estavam "bloqueado (blocklist)".

### Como revalidar (recomendado, com dry-run antes de aplicar)

O próprio `hygiene_leads.py` já faz a checagem; para **revalidar só os bloqueados como "sem WhatsApp"** e ver quantos são falsos positivos, rode o pipeline de higiene em modo seco:

```powershell
cd C:\mycelium\SalesOps-as-Code\pipeline
python hygiene_leads.py --dry-run
```

Depois, compare o relatório (`higiene-leads-resultado.json`) com a `blocked_numbers`: números que agora constam como **com WhatsApp** devem ser removidos da blocklist. Desbloqueio manual por lote (exemplo via SQL Editor do Supabase):

```sql
DELETE FROM blocked_numbers
WHERE reason = 'sem_whatsapp_29-09-2026';
```

> Só execute o `DELETE` depois de confirmar no relatório que a maioria é falso positivo. Números que de fato não têm WhatsApp devem permanecer bloqueados.

---

## 6. Arquivos alterados

| Arquivo | Mudança |
|---------|---------|
| `pipeline/kelevra.py` | endpoint DeepSeek corrigido; defaults de modelo corrigidos; `score_lead` com `max_tokens=1024`; helper `display_name()` |
| `pipeline/dispatch.ps1` | adicionado `--score` |
| `deploy/servidor/dispatch.sh` | adicionado `--score` |

Além disso (dados, não código): 37 leads com `nome`=UUID tiveram o `nome` limpo.

---

## 7. Validação executada

- `python -m py_compile kelevra.py sdr_pipeline.py` → **OK**.
- API DeepSeek (`deepseek-chat` e `deepseek-reasoner`) → respostas válidas.
- `score_lead` real → `ICP=88` / `ICP=72` com justificativa.
- Pipeline completo em dry-run (`--limit 1 --score --no-validate`):

```
ICP=72 (Lead sem website, sem avaliações no Google Maps e audit_score 0 ...)
🔍 Pesquisando empresa no Google...
── Olá, nossa inteligência mapeou negócios locais em Goiânia...
RESUMO: ok=1 pulados=0 falhas=0
```

---

## 8. Pendências / próximos passos

1. **SerpAPI com `429 Too Many Requests`** — a chave `SERPAPI_KEY` está sem créditos/limitada. A pesquisa de dossiê falha de forma não fatal, mas sem personalização. Recarregar ou trocar a chave.
2. **Saldo DeepSeek = US$ 3,73** — suficiente para muitas execuções, mas monitorar.
3. **Revalidar a blocklist** (seção 5) — provável origem do baixo volume de prospecção efetiva.
4. **Segurança** — os `.env` não estão versionados (verificado via `git ls-files`), mas há credenciais em texto plano em `C:\mycelium\.env` e `pipeline/.env`. Recomenda-se rotacionar e proteger.
