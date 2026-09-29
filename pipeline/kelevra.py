# -*- coding: utf-8 -*-
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
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
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
    except Exception:
        return {}


class HttpClient:
    """Wrapper minimalista sobre urllib com JSON e erros não fatais."""

    def __init__(self, base_url, default_headers=None, timeout=30):
        self.base_url = (base_url or "").rstrip("/")
        self.default_headers = default_headers or {}
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
        q = "%s=eq.%s" % (match_col, urllib.parse.quote(str(match_val)))
        status, _ = self.client.request(
            "PATCH", self._path(table, q), body=payload,
            headers={"Prefer": "return=minimal"},
        )
        return status in (200, 204)


class DeepSeek:
    """Cliente da API DeepSeek (chat + reasoner)."""

    def __init__(self, cfg):
        self.key = cfg.get("DEEPSEEK_API_KEY", "")
        self.chat_model = cfg.get("DEEPSEEK_CHAT_MODEL", "deepseek-chat")
        self.reason_model = cfg.get("DEEPSEEK_REASON_MODEL", "deepseek-reasoner")
        self.client = HttpClient(
            "https://api.deepseek.com",
            {"Authorization": "Bearer " + self.key},
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
            raise RuntimeError("DeepSeek HTTP %s: %s" % (status, str(data)[:200]))
        usage = data.get("usage") or {}
        content = ""
        try:
            content = data["choices"][0]["message"].get("content") or ""
        except Exception:
            pass
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

def is_blocked(supa, phone):
    """True se o número está em qualquer blocklist (LGPD/opt-out)."""
    for table in ("blocked_numbers", "blocked_contacts"):
        rows = supa.get(table, "phone=eq.%s&select=phone" % urllib.parse.quote(phone))
        if rows:
            return True
    return False


def get_pending_leads(supa, limit=10, offset=0):
    cols = ("id,nome,telefone,category,subcategory,bairro,cidade,"
            "gmn_rating,gmn_reviews,gmn_has_website,audit_score,fonte,created_at")
    q = "select=%s&order=audit_score.desc.nullslast&limit=%d&offset=%d" % (cols, limit, offset)
    return supa.get("vw_leads_para_prospectar", q) or []


def last_outbound(supa, phone):
    q = ("telefone=eq.%s&direction=eq.outbound&order=created_at.desc&limit=1"
         "&select=created_at,status" % urllib.parse.quote(phone))
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
    q = ("direction=eq.outbound&created_at=gte.%s&select=id&limit=1000"
         % urllib.parse.quote(start))
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
    except Exception:
        score = 0
    return score, parsed.get("icp_reason", ""), usage


def generate_opening(deepseek, lead, icp_reason=None):
    """Qualificador: mensagem de abertura (primeiro toque, cold reading)."""
    nome = lead.get("nome") or "negócio local"
    nicho = lead.get("category") or lead.get("subcategory") or "negócio local"
    rating = lead.get("gmn_rating")
    reviews = lead.get("gmn_reviews")
    bairro = lead.get("bairro")
    cidade = lead.get("cidade")

    system = (
        "Você é Solano, SDR Hunter da Kelevra Corp. Seu objetivo é QUALIFICAR o lead "
        "de forma sutil pelo WhatsApp e AGENDAR uma reunião. O foco exclusivo é vender "
        'o "Protocolo Presença Blindada" (SEO Local, Google Maps e Funil de Avaliações).\n\n'
        "DIRETRIZES DE OURO:\n"
        '1. TOM: 100% humano, descontraído, direto ("Opa", "Cara").\n'
        "2. PROIBIDO bullet points, listas ou formatação robótica.\n"
        "3. No máximo 2 a 4 linhas.\n"
        "4. BANT sutil: 1 ou no máximo 2 perguntas.\n"
        "5. Cold reading: cite 1 dado real do lead de forma casual.\n"
        "6. NÃO invente dados que não existam."
    )
    user = (
        "Lead: %s (nicho: %s)." % (nome, nicho)
        + (" Local: %s, %s." % (bairro, cidade) if bairro or cidade else "")
        + " Dados reais: rating=%s, reviews=%s." % (rating, reviews)
    )
    if icp_reason:
        user += " Insight do Prospector: %s" % icp_reason
    user += " Escreva a MENSAGEM DE ABERTURA (primeiro toque, cold reading)."
    content, usage = deepseek.complete(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=300, temperature=0.7, model=deepseek.chat_model,
    )
    return content, usage

