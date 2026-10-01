"""CORRETOR — agente de auditoria/retroalimentação (stdlib only).

Varre messages_log (outbound) e reporta taxa de entrega + falhas.

Uso:
  python corretor.py              # relatório (200 msgs recentes)
  python corretor.py --list-failed
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kelevra as K


def main():
    K.setup_console_encoding()
    list_failed = "--list-failed" in sys.argv
    cfg = K.get_config()
    supa = K.Supabase(cfg)
    if not (supa.url and supa.key):
        sys.exit("ERRO: Supabase sem URL/KEY.")

    print("=" * 70)
    print("KELEVRA CORRETOR — auditoria de entrega (outbound)")
    print("=" * 70)

    rows = supa.get(
        "messages_log",
        "direction=eq.outbound&select=id,telefone,status,error_details,delivered_at,read_at,created_at"
        "&order=created_at.desc&limit=200",
    ) or []

    ok_states = {"sent", "delivered", "read"}
    ok = [r for r in rows if (r.get("status") or "").lower() in ok_states]
    fail = [r for r in rows if (r.get("status") or "").lower() not in ok_states]
    total = len(rows)
    rate = (len(ok) / total * 100) if total else 0.0

    print("Analisadas: %d | OK: %d | Falha/outros: %d | Taxa entrega: %.1f%%"
          % (total, len(ok), len(fail), rate))
    if rate >= 95:
        print("✔ Dentro da meta (>= 95%).")
    else:
        print("⚠ Abaixo da meta — revisar antes de escalar (decision gate).")

    if list_failed and fail:
        print("\n--- Falhas / pendências ---")
        for f in fail:
            print("  {} | {} | {} | {}".format(
                f.get("created_at"), f.get("telefone"), f.get("status"),
                (f.get("error_details") or "")[:90]))

    print("\nAções sugeridas (Corretor):")
    print("  1. Instância banida -> trocar EVOLUTION_API_KEY / EVO_INSTANCE (round-robin).")
    print("  2. Número inválido -> desqualificar lead.")
    print("  3. Opt-out -> garantir em blocked_numbers/blocked_contacts.")


if __name__ == "__main__":
    main()
