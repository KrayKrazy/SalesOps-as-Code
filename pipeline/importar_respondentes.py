"""IMPORTAR RESPONDENTES — lê um .txt de quem respondeu e grava como inbound.

Complementa o `inbound_sync.py` (que puxa da Evolution): use este script quando
você quiser registrar manualmente os clientes que responderam (ex.: respostas
vistas fora do WhatsApp/Evolution).

O .txt aceita um respondente por linha (nome opcional + telefone):
    Nome do Cliente 11999999999
    11999999999

Uso:
    python importar_respondentes.py --dry-run
    python importar_respondentes.py
    python importar_respondentes.py --file C:/caminho/respondentes.txt
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kelevra as K


def main():
    K.setup_console_encoding()
    argv = sys.argv[1:]
    dry_run = "--dry-run" in argv
    path = None
    if "--file" in argv:
        i = argv.index("--file")
        if i + 1 < len(argv):
            path = argv[i + 1]

    cfg = K.get_config()
    if not path:
        path = cfg.get("RESPONDENTS_FILE") or r"C:\mycelium\respondentes.txt"

    supa = K.Supabase(cfg)
    if not (supa.url and supa.key):
        sys.exit("ERRO: Supabase sem URL/KEY.")

    entries = K.read_closed_phones(path)  # reutiliza o parser (telefone + nome)
    if not entries:
        print(f"Nenhum respondente em: {path}")
        print("Formato esperado (um por linha): [nome opcional] telefone")
        sys.exit(0)

    leads = K.fetch_all(supa, "leads", "id,telefone")
    lead_by_phone = {}
    for l in leads:
        ph = K.normalize_phone(l.get("telefone") or "")
        if ph and ph not in lead_by_phone:
            lead_by_phone[ph] = l.get("id")

    existing = K.fetch_all(supa, "messages_log", "trace_id", extra="direction=eq.inbound")
    seen = {(r.get("trace_id") or "") for r in existing}

    print("=" * 72)
    print("IMPORTAR RESPONDENTES — %s" % ("DRY-RUN (não grava)" if dry_run else "APLICAR"))
    print("Arquivo: %s (%d respondente(s))" % (path, len(entries)))
    print("=" * 72)

    added = 0
    for phone, name in sorted(entries.items()):
        trace = "manual:" + phone
        if trace in seen:
            print("  {} | {} | já registrado".format(phone, name or "-"))
            continue
        print("  {} | {} | {}".format(phone, name or "-",
                                   "registraria" if dry_run else "registrado"))
        if not dry_run:
            payload = {
                "lead_id": lead_by_phone.get(phone),
                "telefone": phone,
                "direction": "inbound",
                "message_type": "text",
                "content": "(resposta registrada manualmente)",
                "status": "received",
                "workflow_name": "importar_respondentes",
                "campaign_id": "salesops-inbound-v1",
                "trace_id": trace,
                "created_at": K.now_iso(),
            }
            try:
                if supa.insert("messages_log", payload):
                    seen.add(trace)
                    added += 1
            except Exception as e:
                print(f"    ERRO: {e}")

    print("-" * 72)
    print("Registrados: %d%s" % (added, " (dry-run)" if dry_run else ""))


if __name__ == "__main__":
    main()
