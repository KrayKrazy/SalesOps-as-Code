"""INBOUND SYNC — puxa as respostas (inbound) da Evolution e grava em messages_log.

Só são consideradas mensagens de números que existem na tabela `leads` (ou seja,
respostas reais ao disparo — e não conversas pessoais do número comercial).

Uso:
    python inbound_sync.py --dry-run           # mostra o que sincronizaria
    python inbound_sync.py                     # sincroniza (grava em messages_log)
    python inbound_sync.py --pages 20          # mais páginas (100 msgs/página)
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kelevra as K


def jid_phone(jid):
    if not jid:
        return ""
    return jid.split("@")[0]


def message_text(msg):
    mt = msg.get("messageType") or ""
    m = msg.get("message") or {}
    if mt == "conversation":
        return m.get("conversation") or ""
    if mt == "extendedTextMessage":
        return (m.get("extendedTextMessage") or {}).get("text") or ""
    if mt == "audioMessage":
        return "[audio]"
    if mt == "imageMessage":
        return "[imagem]"
    if mt == "videoMessage":
        return "[video]"
    if mt == "documentMessage":
        return "[documento]"
    if mt == "stickerMessage":
        return "[figurinha]"
    return "[" + mt + "]"


def main():
    K.setup_console_encoding()
    argv = sys.argv[1:]
    dry_run = "--dry-run" in argv
    pages = 20
    if "--pages" in argv:
        i = argv.index("--pages")
        if i + 1 < len(argv):
            try:
                pages = int(argv[i + 1])
            except ValueError:
                pages = 20

    cfg = K.get_config()
    supa = K.Supabase(cfg)
    evo = K.Evolution(cfg)
    if not (supa.url and supa.key):
        sys.exit("ERRO: Supabase sem URL/KEY.")
    if not (evo.base and evo.apikey):
        sys.exit("ERRO: Evolution sem base/apikey.")

    # Telefones/id dos leads (para filtrar respostas reais e associar lead_id).
    leads = K.fetch_all(supa, "leads", "id,telefone")
    lead_by_phone = {}
    for l in leads:
        ph = K.normalize_phone(l.get("telefone") or "")
        if ph and ph not in lead_by_phone:
            lead_by_phone[ph] = l.get("id")

    # Idempotência: trace_ids de inbound já gravados.
    existing = K.fetch_all(supa, "messages_log", "trace_id",
                           extra="direction=eq.inbound")
    seen = {(r.get("trace_id") or "") for r in existing}

    print("=" * 72)
    print("INBOUND SYNC — %s" % ("DRY-RUN (não grava)" if dry_run else "APLICAR"))
    print("Leads conhecidos: %d | páginas: %d" % (len(lead_by_phone), pages))
    print("=" * 72)

    synced = 0
    for page in range(1, pages + 1):
        st, data = evo.find_messages({"key": {"fromMe": False}}, page=page, limit=100)
        if st != 200:
            print("  página %d: HTTP %s" % (page, st))
            continue
        records = []
        try:
            records = (data.get("messages") or {}).get("records") or []
        except Exception:
            records = data if isinstance(data, list) else []
        if not records:
            break

        for msg in records:
            key = msg.get("key") or {}
            if key.get("fromMe") is not False:
                continue  # só inbound (segurança extra, mesmo com o filtro)
            raw = key.get("remoteJidAlt") or key.get("remoteJid") or ""
            phone = K.normalize_phone(jid_phone(raw))
            if not phone or phone not in lead_by_phone:
                continue  # não é lead nosso (conversa pessoal/outro)
            msg_id = key.get("id") or ""
            trace = "evo:" + msg_id if msg_id else K.trace_id()
            if trace in seen:
                continue

            content = message_text(msg)
            ts = msg.get("messageTimestamp") or 0
            created = K.now_iso()
            if ts:
                try:
                    created = time.strftime("%Y-%m-%dT%H:%M:%S+00:00",
                                            time.gmtime(int(ts)))
                except Exception:
                    pass

            print(f"  {phone} | {content[:60]} | {created}")
            if not dry_run:
                payload = {
                    "lead_id": lead_by_phone.get(phone),
                    "telefone": phone,
                    "direction": "inbound",
                    "message_type": "text",
                    "content": content,
                    "status": "received",
                    "workflow_name": "inbound_sync",
                    "campaign_id": "salesops-inbound-v1",
                    "trace_id": trace,
                    "created_at": created,
                }
                try:
                    if supa.insert("messages_log", payload):
                        seen.add(trace)
                        synced += 1
                except Exception as e:
                    print(f"    ERRO ao gravar: {e}")
        time.sleep(1)  # evita rate limit da Evolution

    print("-" * 72)
    print("Novas respostas: %d%s" % (synced, " (dry-run)" if dry_run else ""))


if __name__ == "__main__":
    main()
