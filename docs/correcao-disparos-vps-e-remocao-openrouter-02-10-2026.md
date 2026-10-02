# Correção dos Disparos na VPS + Remoção do OpenRouter — 02/10/2026

**Data:** 02 de Outubro de 2026
**Escopo:** Kelevra SalesOps — pipeline SDR outbound na VPS
**Servidor:** `vps10393.panel.icontainer.run` (IP `216.22.43.239`) · Ubuntu 24.04 · `/opt/kelevra/`
**Repositório local:** `C:\mycelium\SalesOps-as-Code`

---

## 1. Resumo executivo

O motor estava **rodando no cron**, mas **não enviava nenhuma mensagem** (`ok=0 pulados=179 falhas=321`). A causa raiz era dupla:

1. **Código desatualizado na VPS:** o `kelevra.py` do servidor ainda apontava o cliente DeepSeek para o **OpenRouter** (endpoint hardcoded), enquanto o `.env` usa a **chave nativa da DeepSeek** (`sk-...`). Isso gerava `DeepSeek HTTP 401: Missing Authentication header` em toda chamada → nenhuma abertura era gerada → zero envios.
2. **A correção local nunca foi publicada no servidor:** a versão corrigida existia apenas no repositório local (e não estava commitada), por isso a VPS continuou rodando o código quebrado.

**Resultado:** o código foi corrigido, o OpenRouter foi **totalmente removido** e o disparo voltou a funcionar (validado com dry-run `ok=1 falhas=0`).

---

## 2. Diagnóstico (evidências coletadas)

### 2.1 O cron está ativo e saudável

`/etc/cron.d/kelevra` contém os 3 disparos (08:30 / 13:30 / 18:30, janela aleatória 0–120 min) + inbound sync a cada 30 min. Os logs confirmam que as janelas disparam normalmente:

```
cron_manha.log: [2026-10-02_08-30-02] Janela aleatória: dormindo 5896s antes do disparo (limit=14)
cron_tarde.log: [2026-10-01_13-30-01] Janela aleatória: dormindo 3178s antes do disparo (limit=14)
cron_noite.log: [2026-10-01_18-30-01] Janela aleatória: dormindo 5336s antes do disparo (limit=14)
```

### 2.2 O disparo rodava, mas terminava com zero envios

Log do disparo da manhã (`dispatch_2026-10-02_08-30-02.log`):

```
KELEVRA SDR PIPELINE — ENVIO REAL
Pool de instâncias: Número comercial (11/48), Whatsapp_web (0/48)
Leads pendentes (lote): 500 | alvo: 14 envio(s)
...
✗ geração falhou: DeepSeek HTTP 401: {"error":{"message":"Missing Authentication header","code":401}}
...
RESUMO: ok=0 pulados=179 falhas=321
```

- `pulados=179` → leads na blocklist (ver seção 6).
- `falhas=321` → **todos** com `401 Missing Authentication header` (falha no DeepSeek).

### 2.3 Causa raiz confirmada no código do servidor

O `kelevra.py` da VPS (versão antiga, deploy de 01/10 19:05) tinha o OpenRouter **hardcoded**:

```python
class DeepSeek:
    def __init__(self, cfg):
        self.key = cfg.get("DEEPSEEK_API_KEY", "")
        self.chat_model = cfg.get("DEEPSEEK_CHAT_MODEL", "deepseek/deepseek-chat")
        self.reason_model = cfg.get("DEEPSEEK_REASON_MODEL", "deepseek/deepseek-chat")
        self.client = HttpClient(
            "https://openrouter.ai/api/v1",   # <-- endpoint errado
            {"Authorization": "Bearer " + self.key,
             "HTTP-Referer": "https://kelevra.shop",
             "X-Title": "Kelevra SalesOps"},
            timeout=30,
        )
```

Enquanto isso, a chave no `.env` é nativa da DeepSeek. Confirmei que a chave **é válida e tem saldo** (US$ 2,80), testando direto contra `https://api.deepseek.com`:

```
balance: {"is_available":true,...,"total_balance":"2.80"}
chat status: 200 → "ok"
```

Ou seja: **o problema era só o endpoint errado no código do servidor**, não a chave.

---

## 3. O que já foi feito (ações executadas)

1. **Substituí o `kelevra.py` do servidor** pela versão corrigida (que usa `https://api.deepseek.com` como endpoint).
2. **Adicionei `--score` ao `dispatch.sh`** do servidor — o nó Prospector/ICP não rodava no cron.
3. **Validei** com `py_compile` e dry-run (`ok=1 pulados=19 falhas=0`).

---

## 4. Remoção do OpenRouter (ação desta sessão)

A pedido, **removi completamente a lógica de OpenRouter** do `kelevra.py`, pois ela não faz sentido nesta VPS (o provedor é a DeepSeek oficial).

### Antes

```python
self.is_openrouter = self.key.startswith("sk-or-")
self.base_url = (
    cfg.get("DEEPSEEK_BASE_URL")
    or ("https://openrouter.ai/api/v1" if self.is_openrouter else "https://api.deepseek.com")
).rstrip("/")
headers = {"Authorization": "Bearer " + self.key}
if self.is_openrouter:
    headers["HTTP-Referer"] = "https://kelevra.shop"
    headers["X-Title"] = "Kelevra SalesOps"
...
def _model(self, model):
    model = model or self.chat_model
    if self.is_openrouter and "/" not in model:
        return "deepseek/" + model
    return model
```

### Depois (versão final)

```python
class DeepSeek:
    """Cliente da API DeepSeek (chat + reasoner) — endpoint oficial da DeepSeek."""

    def __init__(self, cfg):
        self.key = cfg.get("DEEPSEEK_API_KEY", "")
        self.chat_model = cfg.get("DEEPSEEK_CHAT_MODEL", "deepseek-chat")
        self.reason_model = cfg.get("DEEPSEEK_REASON_MODEL", "deepseek-reasoner")
        self.base_url = (cfg.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").rstrip("/")

        headers = {"Authorization": "Bearer " + self.key}
        self.client = HttpClient(self.base_url, headers, timeout=30)

    def _model(self, model):
        """Retorna o nome do modelo DeepSeek."""
        return model or self.chat_model
```

### Verificação pós-remoção

- `git grep -ni openrouter` → **nenhuma ocorrência** (local).
- Servidor: `grep -rni 'openrouter|sk-or-|is_openrouter' /opt/kelevra/pipeline/*.py` → **nenhuma ocorrência**.
- `py_compile` local e servidor → **OK**.
- Dry-run no servidor → `RESUMO: ok=1 pulados=19 falhas=0`.

---

## 5. Validação final (dry-run no servidor)

```
KELEVRA SDR PIPELINE — DRY-RUN (não envia)
Conversa: deepseek-chat | scoring: deepseek-reasoner
Disparos hoje: 0 / cap 50
Leads pendentes (lote): 500 | alvo: 1 envio(s)
...
[20/500] (sem nome) | 5562991357116
  ICP=72 (...)
  🔍 Pesquisando empresa no Google...
  [Research] Falha ao pesquisar ...: HTTP Error 429: Too Many Requests   ← SerpAPI (não fatal)
  ── Olá, nossa inteligência mapeou operações de negócios locais em Goiânia...
  [DRY-RUN] não enviado

RESUMO: ok=1 pulados=19 falhas=0
```

O motor volta a prospectar (ICP), qualificar (abertura) e enviar no próximo cron (13:30 de hoje).

---

## 6. Observações / pendências (não bloqueiam o disparo)

| # | Item | Status |
|---|------|--------|
| 1 | **Blocklist (250 `sem_whatsapp_29-09-2026`)** — revalidei os 250 contra a Evolution: **249 realmente não têm WhatsApp** (só 1 falso positivo). A blocklist está correta; **não desbloquear em massa**. | OK, manter |
| 2 | **SerpAPI `429 Too Many Requests`** — a pesquisa de dossiê falha (não fatal); o robô manda abertura genérica. | Recarregar/trocar a chave |
| 3 | **Saldo DeepSeek = US$ 2,80** — suficiente, mas monitorar. | Monitorar |
| 4 | **Falta a pasta `pitch/` na VPS** — `/opt/kelevra/pitch/` não existe; o follow-up não carrega `visao_geral_saas.md` (degrada sem quebrar). | Opcional |
| 5 | **Correções locais não commitadas** — `git status` mostra `kelevra.py`, `sdr_pipeline.py`, `dispatch.sh` etc. modificados e não commitados. **Novo deploy a partir do git traria o bug de volta.** | Commit/push pendente |
| 6 | **`sent_today` da instância "Número comercial" = 11/48** — não vi reset diário automático; ainda longe do limite. | Conferir depois |

---

## 7. Arquivos alterados

| Arquivo | Ação |
|---------|------|
| `pipeline/kelevra.py` (local) | Removida toda a lógica de OpenRouter; endpoint fixo `https://api.deepseek.com` |
| `/opt/kelevra/pipeline/kelevra.py` (VPS) | Substituído pela versão corrigida/limpa |
| `/opt/kelevra/dispatch.sh` (VPS) | Adicionado `--score` |
| `docs/correcao-disparos-vps-e-remocao-openrouter-02-10-2026.md` | este documento |

---

*Documento gerado em 02/10/2026. Motor validado em dry-run; próximo disparo automático às 13:30 (America/Sao_Paulo).*
