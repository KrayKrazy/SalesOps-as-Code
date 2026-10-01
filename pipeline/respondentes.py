"""RESPONDENTES — lista priorizada dos clientes que responderam o disparo.

Lê messages_log (inbound, sincronizado pelo inbound_sync.py) + leads e monta a
lista de prioridade para o follow-up. Também faz o "soft delete" (finalizar):
marca o lead como 'finalizado' após o contato de follow-up, tirando-o da fila.

Uso:
    python respondentes.py                        # lista priorizada (pendentes)
    python respondentes.py --export resp.csv      # exporta CSV
    python respondentes.py --finalizar <id>       # soft-delete de UM lead (por id)
    python respondentes.py --finalizar-todos      # soft-delete de TODOS pendentes
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kelevra as K


def main():
    K.setup_console_encoding()
    argv = sys.argv[1:]
    cfg = K.get_config()
    supa = K.Supabase(cfg)
    if not (supa.url and supa.key):
        sys.exit("ERRO: Supabase sem URL/KEY.")
    done_status = cfg.get("SDR_STATUS_DONE", "finalizado")

    # Soft-delete de um lead específico (por id)
    if "--finalizar" in argv and "--finalizar-todos" not in argv:
        i = argv.index("--finalizar")
        if i + 1 < len(argv):
            lid = argv[i + 1]
            ok = supa.update("leads", {"status": done_status}, "id", lid)
            print("Lead {} -> {}: {}".format(lid, done_status, "OK" if ok else "FALHA"))
            sys.exit(0)
        sys.exit("Use: respondentes.py --finalizar <lead_id>")

    rows = K.get_respondents(supa, done_status=done_status)

    if "--finalizar-todos" in argv:
        n = 0
        for r in rows:
            if r["id"] and supa.update("leads", {"status": done_status}, "id", r["id"]):
                n += 1
        print("Finalizados (%s): %d leads" % (done_status, n))
        sys.exit(0)

    print("=" * 72)
    print("RESPONDENTES (pendentes de follow-up): %d" % len(rows))
    print("=" * 72)
    for r in rows:
        print("{} | {} | {} | score={} | {}".format(r["telefone"], r["nome"][:24], r["nicho"][:18],
                 r["audit_score"], r["ultima_resposta"]))
        print("      resp: {}".format((r["resposta"] or "")[:80]))

    if "--export" in argv:
        i = argv.index("--export")
        out = argv[i + 1] if i + 1 < len(argv) else "respondentes.csv"
        with open(out, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=["id", "nome", "telefone", "nicho",
                                               "audit_score", "gmn_rating",
                                               "resposta", "ultima_resposta"])
            w.writeheader()
            w.writerows(rows)
        print(f"\nExportado: {out}")


if __name__ == "__main__":
    main()
