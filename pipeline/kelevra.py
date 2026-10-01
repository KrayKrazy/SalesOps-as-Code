"""Kelevra SalesOps — núcleo compartilhado do motor multi-agente.

100% biblioteca padrão (stdlib). Sem dependências externas. Python 3.8+.

Agentes do ecossistema (KELEVRA-SALESOPS-MA-001):
  1. Coletor       -> lê a fila de prospecção (vw_leads_para_prospectar)
  2. Prospector    -> scoring ICP (DeepSeek reasoner)
  3. Qualificador  -> abertura/1º toque (DeepSeek chat)
  4. Agendador     -> registro de reunião (Cal.com via n8n)
  5. Corretor      -> auditoria/reparo (corretor.py)

Toda escrita/leitura é tolerante a tabelas que ainda não existem
(migração 0001 pendente): agent_runs/error_log/whatsapp_instances são
gravadas com degradação graciosa.
"""
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

DEFAULT_ENV_PATHS = [
    r"C:\mycelium\.env",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
]


def load_env(paths=None):
    """Lê arquivos .env (KEY=VALUE) sem python-dotenv."""
    data = {}
    for path in (paths or DEFAULT_ENV_PATHS):
        if not path or not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    data[key] = value
    return data


def get_config(paths=None):
    """Config final: .env + variáveis de ambiente (maior precedência)."""
    cfg = load_env(paths)
    cfg.update({k: v for k, v in os.environ.items() if v})
    return cfg


def setup_console_encoding():
    """Força stdout/stderr em UTF-8 no Windows (evita UnicodeEncodeError)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def normalize_phone(phone):
    """Normaliza para o padrão internacional (55 + DDD + número) da Evolution."""
    if not phone:
        return ""
    digits = re.sub(r"\D", "", str(phone))
    if len(digits) in (10, 11):
        return "55" + digits
    return digits


def parse_closed_line(line):
    """Extrai (nome, telefone_normalizado) de uma linha do txt de clientes fechados.

    Aceita praticamente qualquer formato: só o telefone, "Nome 11999999999",
    "Nome;11 99999-9999", "+55 (11) 99999-9999", CSV, etc. Linhas vazias ou
    iniciadas por '#' são ignoradas. Retorna (None, None) se não houver telefone.
    """
    line = (line or "").strip()
    if not line or line.startswith("#"):
        return None, None
    # Telefone: ÚLTIMO bloco de dígitos (com separadores) da linha. Assim,
    # dígitos no NOME (ex.: "Fórmula 1 Auto Center") não contaminam o número.
    m = re.search(r"(\+?\s*\d[\d\s().\-]{6,})\s*$", line)
    phone = normalize_phone(re.sub(r"\D", "", m.group(1))) if m else ""
    if not phone:
        return None, None
    name = line[:m.start()].strip(" \t;|,:-()+") if m else ""
    if not re.search(r"[A-Za-z\u00c0-\u00ff]", name):
        name = ""
    return name, phone


def read_closed_phones(path):
    """Lê o txt de clientes fechados e retorna {telefone_normalizado: nome}.

    Usado tanto pelo `block_closed.py` (persistir na blocklist) quanto pelo
    `sdr_pipeline.py` (blocklist local em memória, como rede de segurança).
    """
    out = {}
    if not path or not os.path.isfile(path):
        return out
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            for raw in fh:
                name, phone = parse_closed_line(raw)
                if phone:
                    out.setdefault(phone, name or "")
    except Exception:
        pass
    return out


def trace_id():
    return uuid.uuid4().hex


def input_hash(lead):
    h = hashlib.sha1()
    for k in sorted(lead.keys()):
        h.update(str(k).encode("utf-8"))
        h.update(str(lead[k]).encode("utf-8"))
    return h.hexdigest()[:16]


def _extract_json(text):
    """Extrai um objeto JSON de uma resposta de LLM (tolerante a code fences)."""
    if not text:
        return {}
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        text = text[start:end + 1]
    try:
        return json.loads(text)
    except Exception as e:
        raise ValueError(f"Falha de Parsing JSON da LLM. Texto bruto: {text[:200]}... Erro: {e}")


class HttpClient:
    """Wrapper minimalista sobre urllib com JSON e erros não fatais."""

    def __init__(self, base_url, default_headers=None, timeout=30):
        self.base_url = (base_url or "").rstrip("/")
        self.default_headers = default_headers or {}
        if "User-Agent" not in self.default_headers and "user-agent" not in self.default_headers:
            self.default_headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        self.timeout = timeout

    def request(self, method, path, body=None, headers=None, timeout=None):
        url = self.base_url + path
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method=method)
        for k, v in self.default_headers.items():
            req.add_header(k, v)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
                return resp.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:300]
            except Exception:
                pass
            return e.code, detail
        except urllib.error.URLError as e:
            return -1, str(e.reason)

class Supabase:
    """Cliente REST (PostgREST) do Supabase cloud via service role key."""

    def __init__(self, cfg):
        self.url = (cfg.get("SUPABASE_PROJECT_URL") or cfg.get("SUPABASE_URL") or "").rstrip("/")
        self.key = (cfg.get("SUPABASE_SECRET_KEY")
                    or cfg.get("SUPABASE_SECRET_KEY_PROJ")
                    or cfg.get("SUPABASE_ACCESS_TOKEN")
                    or cfg.get("SUPABASE_SERVICE_KEY") or "")
        headers = {
            "apikey": self.key,
            "Authorization": "Bearer " + self.key,
            "User-Agent": "supabase-js/2.45.0",
            "X-Client-Info": "supabase-js/2.45.0",
        }
        self.client = HttpClient(self.url, headers, timeout=30)

    def _path(self, table, query=""):
        return "/rest/v1/" + table + (("?" + query) if query else "")

    def get(self, table, query=""):
        status, data = self.client.request("GET", self._path(table, query))
        if status == 200 and isinstance(data, list):
            return data
        return None

    def insert(self, table, payload):
        status, _ = self.client.request(
            "POST", self._path(table), body=payload,
            headers={"Prefer": "return=minimal"},
        )
        return status in (200, 201)

    def update(self, table, payload, match_col, match_val):
        q = f"{match_col}=eq.{urllib.parse.quote(str(match_val))}"
        status, _ = self.client.request(
            "PATCH", self._path(table, q), body=payload,
            headers={"Prefer": "return=minimal"},
        )
        return status in (200, 204)


class DeepSeek:
    """Cliente da API DeepSeek (chat + reasoner)."""

    def __init__(self, cfg):
        self.key = cfg.get("DEEPSEEK_API_KEY", "")
        self.chat_model = cfg.get("DEEPSEEK_CHAT_MODEL", "deepseek/deepseek-chat")
        self.reason_model = cfg.get("DEEPSEEK_REASON_MODEL", "deepseek/deepseek-chat")
        self.client = HttpClient(
            "https://openrouter.ai/api/v1",
            {
                "Authorization": "Bearer " + self.key,
                "HTTP-Referer": "https://kelevra.shop",
                "X-Title": "Kelevra SalesOps"
            },
            timeout=30,
        )

    def complete(self, messages, max_tokens=300, temperature=0.7, model=None):
        body = {
            "model": model or self.chat_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        status, data = self.client.request(
            "POST", "/chat/completions", body=body, timeout=90)
        if status != 200:
            raise RuntimeError(f"DeepSeek HTTP {status}: {str(data)[:200]}")
        usage = data.get("usage") or {}
        content = ""
        try:
            content = data["choices"][0]["message"].get("content") or ""
        except Exception as e:
            raise RuntimeError(f"API retornou resposta malformada (sem choices). Resposta bruta: {str(data)[:300]}... Erro: {e}")
        return content.strip(), usage


class Evolution:
    """Cliente da Evolution API (envio de WhatsApp)."""

    def __init__(self, cfg):
        self.base = (cfg.get("EVOLUTION_BASE_URL") or "").rstrip("/")
        self.apikey = cfg.get("EVOLUTION_API_KEY", "")
        self.instance = cfg.get("EVO_INSTANCE", "Número comercial")

    def send_text(self, phone, text, delay=1500):
        inst = urllib.parse.quote(self.instance)
        path = "/message/sendText/" + inst
        body = {"number": phone, "text": text, "delay": delay}
        client = HttpClient(self.base, {"apikey": self.apikey}, timeout=45)
        return client.request("POST", path, body=body)

    def find_messages(self, where=None, page=1, limit=100):
        """Lista mensagens (chat) da instância. Retorna (status, data).

        `data` tem a forma {"messages": {"records": [...], "total": N, "pages": N}}.
        `where` aceita filtro Mongo-like (ex.: {"key": {"fromMe": false}}).
        """
        inst = urllib.parse.quote(self.instance)
        path = "/chat/findMessages/" + inst
        body = {"page": page, "limit": limit}
        if where:
            body["where"] = where
        client = HttpClient(self.base, {"apikey": self.apikey}, timeout=60)
        return client.request("POST", path, body=body)


def check_whatsapp_batch(evo, phones, batch=100):
    """Valida existência de WhatsApp em lote. Retorna {phone: bool|None}."""
    out = {}
    if not phones:
        return out
    inst = urllib.parse.quote(evo.instance)
    client = HttpClient(evo.base, {"apikey": evo.apikey}, timeout=60)
    for i in range(0, len(phones), batch):
        chunk = phones[i:i + batch]
        st, data = client.request("POST", "/chat/whatsappNumbers/" + inst,
                                  body={"numbers": chunk})
        if st == 200 and isinstance(data, list) and len(data) == len(chunk):
            for n, d in zip(chunk, data):
                out[n] = bool(d.get("exists")) if isinstance(d, dict) else None
        else:
            for n in chunk:
                out[n] = None
    return out


def block_phone(supa, phone, reason="sem_whatsapp"):
    """Adiciona número à blocklist (idempotente por phone)."""
    existing = supa.get("blocked_numbers",
                        f"phone=eq.{urllib.parse.quote(phone)}&select=phone")
    if existing:
        return True
    payload = {"phone": phone, "reason": reason, "blocked_at": now_iso()}
    try:
        return supa.insert("blocked_numbers", payload)
    except Exception as e:
        print(f"❌ FALHA CRÍTICA: Não foi possível inserir na blocklist. Erro: {e}")
        raise


def get_whatsapp_pool(supa, default_instance="Número comercial", quota=None):
    """Pool de instâncias ativas para round-robin (anti-ban).

    Lê a tabela `whatsapp_instances` (migração 0001) filtrando instâncias com
    status `active/open/connected` e fora de cooldown/quarentena. Se a tabela
    não existir (migração pendente) ou estiver vazia, degrada graciosamente
    para uma única instância `default_instance`.
    """
    rows = supa.get(
        "whatsapp_instances",
        "select=instance_name,daily_quota,sent_today,status,cooldown_until"
        "&order=id.asc",
    ) or []
    pool = []
    now = datetime.now(timezone.utc)
    for r in rows:
        name = (r.get("instance_name") or "").strip()
        if not name:
            continue
        status = (r.get("status") or "active").strip().lower()
        if status not in ("active", "open", "connected"):
            continue
        cooldown = r.get("cooldown_until")
        if cooldown:
            try:
                cd = datetime.fromisoformat(str(cooldown).replace("Z", "+00:00"))
                if cd.tzinfo is None:
                    cd = cd.replace(tzinfo=timezone.utc)
                if now < cd:
                    continue  # em cooldown/quarentena
            except Exception:
                pass
        q = quota or r.get("daily_quota") or 48
        try:
            q = int(q)
        except Exception:
            q = 48
        s = r.get("sent_today") or 0
        try:
            s = int(s)
        except Exception:
            s = 0
        pool.append({"name": name, "quota": q, "sent_today": s})

    if not pool:
        q = quota or 48
        pool = [{"name": default_instance, "quota": q, "sent_today": 0}]
    return pool


class InstancePool:
    """Round-robin sobre instâncias com quota por instância (anti-ban)."""

    def __init__(self, instances):
        self.instances = list(instances or [])
        self._cursor = 0

    def next(self):
        """Retorna a próxima instância com quota restante, ou None."""
        n = len(self.instances)
        if n == 0:
            return None
        for _ in range(n):
            inst = self.instances[self._cursor % n]
            self._cursor += 1
            if int(inst.get("sent_today") or 0) < int(inst.get("quota") or 0):
                return inst
        return None

    def record_send(self, inst):
        if inst is not None:
            inst["sent_today"] = int(inst.get("sent_today") or 0) + 1

    def summary(self):
        return ", ".join(
            "%s (%d/%d)" % (i["name"], int(i.get("sent_today") or 0),
                            int(i.get("quota") or 0))
            for i in self.instances
        )


def increment_instance_sent(supa, instance_name):
    """Incrementa `sent_today` da instância no banco (best-effort, não fatal)."""
    if not instance_name:
        return False
    try:
        rows = supa.get(
            "whatsapp_instances",
            f"instance_name=eq.{urllib.parse.quote(str(instance_name))}&select=id,sent_today",
        ) or []
        if not rows:
            return False
        current = int(rows[0].get("sent_today") or 0)
        return supa.update(
            "whatsapp_instances",
            {"sent_today": current + 1},
            "instance_name",
            instance_name,
        )
    except Exception:
        return False


def is_blocked(supa, phone):
    """True se o número está em qualquer blocklist (LGPD/opt-out)."""
    for table in ("blocked_numbers", "blocked_contacts"):
        rows = supa.get(table, f"phone=eq.{urllib.parse.quote(phone)}&select=phone")
        if rows:
            return True
    return False


def fetch_all(supa, table, cols, extra="", limit=1000, max_rows=10000):
    """Pagina uma tabela PostgREST (contorna o max-rows padrão de 1000).

    `extra` aceita o restante da query string (ex.: "direction=eq.inbound&order=...").
    """
    out = []
    offset = 0
    while offset < max_rows:
        q = f"select={cols}"
        if extra:
            q += "&" + extra
        q += "&limit=%d&offset=%d" % (limit, offset)
        rows = supa.get(table, q) or []
        out.extend(rows)
        if len(rows) < limit:
            break
        offset += limit
    return out


def get_respondents(supa, done_status="finalizado"):
    """Lista priorizada de respondentes pendentes de follow-up (soft-delete).

    Junta messages_log (inbound) com leads. Exclui leads com status `done_status`
    e 'desqualificado'. Ordena por resposta mais recente e, no desempate, por
    maior audit_score.
    """
    inbound = fetch_all(supa, "messages_log", "telefone,lead_id,content,created_at",
                        extra="direction=eq.inbound&order=created_at.desc")
    leads = fetch_all(supa, "leads",
                      "id,nome,telefone,category,subcategory,audit_score,gmn_rating,status")
    lead_by_phone = {}
    for l in leads:
        ph = normalize_phone(l.get("telefone") or "")
        if ph and ph not in lead_by_phone:
            lead_by_phone[ph] = l

    latest = {}
    for m in inbound:
        ph = normalize_phone(m.get("telefone") or "")
        if not ph or ph in latest:
            continue
        latest[ph] = m

    rows = []
    for ph, m in latest.items():
        lead = lead_by_phone.get(ph) or {}
        status = (lead.get("status") or "").lower()
        if status in (done_status.lower(), "desqualificado"):
            continue
        rows.append({
            "id": lead.get("id") or "",
            "nome": lead.get("nome") or "(sem nome)",
            "telefone": ph,
            "nicho": (lead.get("category") or lead.get("subcategory") or ""),
            "audit_score": lead.get("audit_score") or 0,
            "gmn_rating": lead.get("gmn_rating"),
            "resposta": (m.get("content") or "")[:200],
            "ultima_resposta": m.get("created_at") or "",
        })
    rows.sort(key=lambda r: (r["ultima_resposta"], r["audit_score"] or 0), reverse=True)
    return rows


def get_pending_leads(supa, limit=10, offset=0):
    cols = ("id,nome,telefone,category,subcategory,bairro,cidade,"
            "gmn_rating,gmn_reviews,gmn_has_website,audit_score,fonte,created_at")
    q = "select=%s&order=audit_score.desc.nullslast&limit=%d&offset=%d" % (cols, limit, offset)
    return supa.get("vw_leads_para_prospectar", q) or []


def last_outbound(supa, phone):
    q = (f"telefone=eq.{urllib.parse.quote(phone)}&direction=eq.outbound&order=created_at.desc&limit=1"
         "&select=created_at,status")
    rows = supa.get("messages_log", q)
    return rows[0] if rows else None


def was_contacted_recently(supa, phone, hours=72):
    last = last_outbound(supa, phone)
    if not last or not last.get("created_at"):
        return False
    try:
        dt = datetime.fromisoformat(str(last["created_at"]).replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - dt).total_seconds()
        return age < hours * 3600
    except Exception:
        return False


def count_sent_today(supa, workflow="sdr_pipeline"):
    start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0).isoformat()
    q = (f"direction=eq.outbound&created_at=gte.{urllib.parse.quote(start)}&select=id&limit=1000")
    rows = supa.get("messages_log", q)
    return len(rows) if rows is not None else 0


def log_message(supa, lead, text, status, error=None, http_resp=None,
                trace=None, follow_up_num=0):
    payload = {
        "lead_id": lead.get("id"),
        "telefone": lead.get("telefone"),
        "direction": "outbound",
        "message_type": "text",
        "content": text,
        "status": status,
        "campaign_id": "salesops-outbound-v1",
        "workflow_name": "sdr_pipeline",
        "follow_up_num": follow_up_num,
        "sent_at": now_iso() if status == "sent" else None,
        "created_at": now_iso(),
        "trace_id": trace,
    }
    if error:
        payload["error_details"] = str(error)[:500]
    if http_resp:
        payload["http_response"] = json.dumps(http_resp, ensure_ascii=False)[:1000]
    try:
        return supa.insert("messages_log", payload)
    except Exception:
        return False


def record_agent_run(supa, agent_id, lead_id, model, status, meta=None,
                     tokens_in=0, tokens_out=0, trace=None, latency_ms=0):
    payload = {
        "agent_id": agent_id,
        "lead_id": lead_id,
        "model": model,
        "status": status,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "latency_ms": latency_ms,
        "trace_id": trace,
        "meta": meta or {},
        "created_at": now_iso(),
    }
    try:
        return supa.insert("agent_runs", payload)
    except Exception:
        return False  # tabela pode não existir (migração pendente)


def log_error(supa, agent_id, lead_id, error_type, message, context=None,
              severity="medium"):
    payload = {
        "agent_id": agent_id,
        "lead_id": lead_id,
        "error_type": error_type,
        "message": str(message)[:1000],
        "context": context or {},
        "severity": severity,
        "created_at": now_iso(),
    }
    try:
        return supa.insert("error_log", payload)
    except Exception:
        return False

def score_lead(deepseek, lead):
    """Prospector: ICP score (0-100) + justificativa via DeepSeek reasoner."""
    system = (
        "Você é o Prospector da Kelevra Corp. Analise o lead de negócio local e "
        "retorne SOMENTE um JSON válido, sem texto extra, no formato "
        '{"icp_score": <0-100>, "icp_reason": "<1-2 frases>"}. '
        "Priorize: presença digital fraca (rating<4.5 OU review_count<50 OU sem "
        "website), negócio local de pequeno/médio porte, nicho com dor em SEO/Google "
        "Maps. Penalize grandes empresas."
    )
    user = json.dumps({
        "nome": lead.get("nome"),
        "categoria": lead.get("category") or lead.get("subcategory"),
        "bairro": lead.get("bairro"),
        "cidade": lead.get("cidade"),
        "gmn_rating": lead.get("gmn_rating"),
        "gmn_reviews": lead.get("gmn_reviews"),
        "gmn_has_website": lead.get("gmn_has_website"),
        "audit_score": lead.get("audit_score"),
    }, ensure_ascii=False)
    content, usage = deepseek.complete(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=200, temperature=0.2, model=deepseek.reason_model,
    )
    parsed = _extract_json(content)
    score = parsed.get("icp_score", 0)
    try:
        score = int(score)
    except Exception as e:
        raise ValueError(f"Falha ao interpretar ICP Score da LLM: {score}. Erro: {e}")
    return score, parsed.get("icp_reason", ""), usage


def generate_opening(deepseek, lead, icp_reason=None, seo_dossier=None):
    """Qualificador: mensagem de abertura (primeiro toque, cold reading)."""
    nome = lead.get("nome") or "negócio local"
    nicho = lead.get("category") or lead.get("subcategory") or "negócio local"
    rating = lead.get("gmn_rating")
    reviews = lead.get("gmn_reviews")
    bairro = lead.get("bairro")
    cidade = lead.get("cidade")

    system = (
        "Você é Solano, SDR Hunter da Kelevra Corp. Seu objetivo é INICIAR CONVERSA com o lead "
        "de forma sutil pelo WhatsApp.\n\n"
        "DIRETRIZES DE OURO:\n"
        '1. TOM: 100% humano, descontraído, direto ("Opa", "Fala cara", etc).\n'
        "2. PROIBIDO bullet points, listas ou formatação robótica.\n"
        "3. PROIBIDO usar aspas em volta da mensagem.\n"
        "4. No máximo 2 a 3 linhas curtas.\n"
        "5. Cold reading: cite 1 dado da pesquisa de forma natural e rápida no meio da conversa.\n"
        "6. PERGUNTA DE FECHAMENTO: Termine SEMPRE perguntando de forma casual 'por onde vocês estão captando a maioria dos clientes hoje?' (ou variação similar). NÃO tente vender ou oferecer solução nessa primeira mensagem."
    )
    user = (
        f"Lead: {nome} (nicho: {nicho})."
        + (f" Local: {bairro}, {cidade}." if bairro or cidade else "")
    )
    if seo_dossier:
        user += f" \nFATOS EXTRAÍDOS DA PESQUISA SOBRE O LEAD: {seo_dossier}. \n\nINSTRUÇÃO: Use um desses fatos (ex: vi o site X, vi o insta Y, notei a nota Z no Google) de forma ultra natural na abertura."
    else:
        user += f" Dados reais: rating={rating}, reviews={reviews}."

    if icp_reason:
        user += f" Insight do Prospector: {icp_reason}"
    user += "\n\nEscreva a MENSAGEM DE ABERTURA. Retorne APENAS o texto da mensagem, sem aspas."
    
    content, usage = deepseek.complete(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=300, temperature=0.7, model=deepseek.chat_model,
    )
    
    # Remove aspas caso o modelo ainda insista em colocar
    content = content.strip().strip('"').strip("'")
    
    return content, usage


def route_product(lead):
    """Roteia o lead para o melhor produto baseado no nicho."""
    return {
        "nome": "Presença Blindada",
        "nicho": lead.get("category", "negócio local"),
        "dor": "falta de avaliações, dificuldade de ser encontrado no Google",
        "promessa": "dominar o Google Maps e construir um funil de avaliações automático"
    }

def generate_followup(deepseek, lead, inbound_text):
    """Agente de follow-up: segundo toque para quem respondeu a abertura.

    Reforça a mesma solução roteada pelo nicho e puxa o agendamento, usando a
    resposta do lead como contexto.
    """
    nome = lead.get("nome") or "negócio local"
    nicho = lead.get("nicho") or lead.get("category") or lead.get("subcategory") or "negócio local"
    produto = route_product(lead)

    system = (
        "Você é Solano, SDR Hunter da Kelevra Corp. O lead respondeu à sua primeira "
        "mensagem. Escreva o FOLLOW-UP (segundo toque) curto e humano para QUALIFICAR "
        "e AGENDAR uma reunião. Use a resposta dele como contexto.\n\n"
        "PRODUTO EM NEGOCIAÇÃO: {nome} [{nicho}].\n"
        "  - Dor: {dor}.\n"
        "  - Promessa: {promessa}.\n\n"
        "DIRETRIZES:\n"
        "1. TOM humano, profissional e consultivo (sem \"Opa, cara\" forçado).\n"
        "2. No máximo 2 a 4 linhas, sem bullet points.\n"
        "3. Responda de forma natural à resposta do lead e reforce a dor do nicho.\n"
        "4. Puxe para agendar uma reunião/call com uma pergunta simples.\n"
        "5. NÃO invente dados. NÃO fale de preço sem a reunião."
    ).format(
        nome=produto["nome"], nicho=produto["nicho"],
        dor=produto["dor"], promessa=produto["promessa"],
    )

    user = ("Lead: {} (nicho: {}).\nResposta do lead: {}\n"
            "Escreva o FOLLOW-UP (segundo toque) reforçando o {}.".format(nome, nicho, (inbound_text or "(sem texto)")[:300], produto["nome"]))
    content, usage = deepseek.complete(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=300, temperature=0.7, model=deepseek.chat_model,
    )
    return content, usage

