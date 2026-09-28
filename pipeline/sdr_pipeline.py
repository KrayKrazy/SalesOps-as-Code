"""
SDR PIPELINE — Kelevra SalesOps (Coletar -> Qualificar -> Disparar -> Logar)
Fluxo: lê leads pendentes do Supabase -> gera mensagem (DeepSeek) -> envia (Evolution) -> loga/atualiza status.

Uso:
  python sdr_pipeline.py --dry-run --limit 3     # apenas gera e mostra (sem enviar)
  python sdr_pipeline.py --send --limit 5        # envia de verdade (cuidado!)
"""
import json
import os
import sys
import urllib.request
import urllib.parse

SUPA_URL = os.environ.get("SUPABASE_PROJECT_URL", "https://omdieogddacchiihjqyl.supabase.co")
SUPA_KEY = os.environ.get("SUPABASE_SECRET_KEY", "")
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
EVO_BASE = os.environ.get("EVOLUTION_BASE_URL", "https://evo.vps10393.panel.icontainer.run")
EVO_APIKEY = os.environ.get("EVOLUTION_API_KEY", "")
EVO_INSTANCE = os.environ.get("EVO_INSTANCE", "Número comercial")


def supabase(method, path, body=None):
    r = urllib.request.Request(SUPA_URL + path, method=method)
    r.add_header("apikey", SUPA_KEY)
    r.add_header("Authorization", "Bearer " + SUPA_KEY)
    r.add_header("User-Agent", "supabase-js/2.45.0")
    r.add_header("X-Client-Info", "supabase-js/2.45.0")
    r.add_header("Content-Type", "application/json")
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(r, data=data, timeout=30) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        print("  [SUPABASE HTTP %s] %s" % (e.code, e.read().decode()[:200]))
        return None


def deepseek(messages, max_tokens=300):
    req = urllib.request.Request(
        "https://api.deepseek.com/chat/completions", method="POST"
    )
    req.add_header("Authorization", "Bearer " + DEEPSEEK_KEY)
    req.add_header("Content-Type", "application/json")
    body = json.dumps(
        {"model": "deepseek-chat", "messages": messages,
         "max_tokens": max_tokens, "temperature": 0.7}
    ).encode()
    with urllib.request.urlopen(req, data=body, timeout=60) as r:
        return json.loads(r.read().decode())


def evolution_send_text(phone, text):
    instance = urllib.parse.quote(EVO_INSTANCE)
    req = urllib.request.Request(
        "%s/message/sendText/%s" % (EVO_BASE, instance), method="POST"
    )
    req.add_header("apikey", EVO_APIKEY)
    req.add_header("Content-Type", "application/json")
    body = json.dumps({"number": phone, "text": text, "delay": 1500}).encode()
    with urllib.request.urlopen(req, data=body, timeout=40) as r:
        return json.loads(r.read().decode())


def get_pending_leads(limit):
    # Fonte: view pronta de prospecção, prioriza audit_score
    path = (
        "/rest/v1/vw_leads_para_prospectar"
        "?select=nome,telefone,category,gmn_rating,gmn_reviews,audit_score,bairro,cidade"
        "&order=audit_score.desc.nullslast&limit=%d" % limit
    )
    rows = supabase("GET", path)
    return rows or []


def generate_message(lead):
    nome = lead.get("nome") or "negócio local"
    nicho = lead.get("category") or lead.get("subcategory") or "negócio local"
    rating = lead.get("gmn_rating")
    reviews = lead.get("gmn_reviews")
    bairro = lead.get("bairro")
    cidade = lead.get("cidade")

    system = (
        "Você é Solano, SDR Hunter da Kelevra Corp. Seu objetivo é QUALIFICAR o lead "
        "de forma sutil pelo WhatsApp e AGENDAR uma reunião. O foco exclusivo é vender o "
        '"Protocolo Presença Blindada" (SEO Local, Google Maps e Funil de Avaliações).\n\n'
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
        + " Escreva a MENSAGEM DE ABERTURA (primeiro toque, cold reading)."
    )
    resp = deepseek(
        [{"role": "system", "content": system}, {"role": "user", "content": user}]
    )
    return resp["choices"][0]["message"]["content"].strip()


def main():
    args = sys.argv[1:]
    dry_run = "--send" not in args
    limit = 3
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])

    leads = get_pending_leads(limit)
    print("LEADS PENDENTES:", len(leads))
    for lead in leads:
        msg = generate_message(lead)
        print("\n--- %s (%s) ---" % (lead.get("nome"), lead.get("telefone")))
        print(msg)
        if not dry_run:
            r = evolution_send_text(lead["telefone"], msg)
            print("[ENVIADO] %s" % json.dumps(r, ensure_ascii=False))
        else:
            print("[DRY-RUN — não enviado]")


if __name__ == "__main__":
    main()
