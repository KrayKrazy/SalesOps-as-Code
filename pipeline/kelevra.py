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


_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def display_name(nome):
    """Retorna um nome legível; UUIDs (dado não higienizado) viram string vazia."""
    nome = (nome or "").strip()
    if _UUID_RE.match(nome):
        return ""
    return nome


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

    def complete(self, messages, max_tokens=300, temperature=0.7, model=None):
        body = {
            "model": self._model(model),
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

def transcribe_audio(openai_key, base64_audio, mimetype="audio/ogg"):
    url = "https://api.openai.com/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {openai_key}"}
    ext = "ogg"
    if "mp4" in mimetype: ext = "mp4"
    elif "mpeg" in mimetype: ext = "mp3"
    elif "wav" in mimetype: ext = "wav"
    elif "webm" in mimetype: ext = "webm"
    try:
        import base64, requests
        audio_bytes = base64.b64decode(base64_audio)
        files = {"file": (f"audio.{ext}", audio_bytes, mimetype)}
        data = {"model": "whisper-1"}
        resp = requests.post(url, headers=headers, files=files, data=data, timeout=30)
        if resp.status_code == 200: return resp.json().get("text", "")
    except: pass
    return ""

def describe_image(openai_key, base64_image, mimetype="image/jpeg"):
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"}
    data_uri = f"data:{mimetype};base64,{base64_image}"
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "user", "content": [
                {"type": "text", "text": "Descreva o que tem nesta imagem. Seja curto e foque no contexto de negócios."},
                {"type": "image_url", "image_url": {"url": data_uri}}
            ]}
        ],
        "max_tokens": 100
    }
    try:
        import requests
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code == 200: return resp.json()["choices"][0]["message"]["content"]
    except: pass
    return ""


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

    def get_base64_from_media_message(self, message):
        """Baixa o base64 de uma mensagem de mídia (audioMessage, imageMessage)."""
        inst = urllib.parse.quote(self.instance)
        path = f"/chat/getBase64FromMediaMessage/{inst}"
        client = HttpClient(self.base, {"apikey": self.apikey, "Content-Type": "application/json"}, timeout=60)
        status, data = client.request("POST", path, body={"message": message})
        if status == 201 or status == 200:
            return data.get("base64"), data.get("mimetype")
        return None, None



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

    # Reset diário: no primeiro run do dia (UTC), quando ainda não houve
    # nenhum envio com sucesso, zera o `sent_today` de todas as instâncias.
    # Sem isso o contador por instância acumula de um dia para o outro e a
    # quota (48) é atingida de forma permanente.
    if rows and count_sent_today(supa) == 0:
        for r in rows:
            try:
                supa.update("whatsapp_instances", {"sent_today": 0}, "id", r.get("id"))
                r["sent_today"] = 0
            except Exception:
                pass

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
        lead = lead_by_phone.get(ph)
        if not lead or not lead.get("id"):
            continue
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
    # Só conta ENVIOS bem-sucedidos (status=sent). Mensagens que falharam
    # (ex.: "Connection Closed") nunca chegaram ao WhatsApp e não devem
    # consumir o cap anti-ban diário.
    q = (f"direction=eq.outbound&status=eq.sent&created_at=gte.{urllib.parse.quote(start)}&select=id&limit=1000")
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
        "Você é o Solano, da Kelevra Corp. O lead respondeu sua abertura no WhatsApp.\n"
        "Seu objetivo é dar uma ÚNICA resposta direta e curta, puxando para uma call de 5 min.\n\n"
        "PRODUTO EM FOCO: {nome} [{nicho}] - Dor: {dor}\n\n"
        "REGRAS DE OURO:\n"
        "1. TOM: Direto, pragmático, sem enrolação. Nada de 'Fico feliz que respondeu' ou textão.\n"
        "2. TAMANHO: Máximo 3 linhas. Seja cirúrgico.\n"
        "3. AÇÃO: Se houver abertura, diga: 'Vamos bater um papo rápido pra te mostrar na tela. Que horário fica melhor? Se preferir, escolhe aqui: forms.kelevra.shop'. Nunca use formatação markdown no link.\n"
        "4. SE FOR ÁUDIO: Diga apenas 'Estou em reunião e não consigo ouvir agora. Consegue me mandar por texto ou marcamos 5 min na agenda? forms.kelevra.shop'.\n"
        "5. PROIBIDO: Fazer mais de uma pergunta, usar jargões corporativos, ser excessivamente professoral ou enviar múltiplos links.\n"
        "6. PROIBIDO: NUNCA inicie com 'Aqui está o texto'. Forneça APENAS a mensagem final."
    ).format(
        nome=produto["nome"], nicho=produto["nicho"],
        dor=produto["dor"], promessa=produto["promessa"],
    )

    inbound_clean = (inbound_text or "(sem texto)")[:300]
    user = ("Lead: {} (nicho: {}).\nResposta do lead: {}\n"
            "Escreva o FOLLOW-UP (segundo toque) qualificando o lead (BANT) e guiando para forms.kelevra.shop se aplicável.".format(nome, nicho, inbound_clean))
    content, usage = deepseek.complete(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=300, temperature=0.7, model=deepseek.chat_model,
    )
    return content, usage

