"""BLOQUEIO DE CLIENTES FECHADOS — lê um .txt e grava na blocklist.

Os clientes que já fecharam (pagaram) são removidos da prospecção outbound:
- `blocked_numbers`  (reason = cliente_fechado)  -> usada pelo is_blocked()
- `blocked_contacts` (status = pago)             -> convenção já usada no projeto

O .txt aceita um cliente por linha, em praticamente qualquer formato:
    Nome do Cliente 11999999999
    Nome;11 99999-9999
    +55 (11) 99999-9999
    11999999999

Uso:
    python block_closed.py                     # lê C:\\mycelium\\fechados.txt (padrão)
    python block_closed.py --file C:\\caminho\\clientes.txt
    python block_closed.py --dry-run           # só mostra, não grava
"""
import os
import sys
import urllib.parse

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
        path = cfg.get("CLOSED_CLIENTS_FILE") or r"C:\mycelium\fechados.txt"

    supa = K.Supabase(cfg)
    if not (supa.url and supa.key):
        sys.exit("ERRO: Supabase sem URL/KEY (rode setup_env.ps1).")

    clients = K.read_closed_phones(path)
    if not clients:
        print(f"Nenhum cliente encontrado em: {path}")
        print("Formato esperado (um por linha): [nome opcional] telefone")
        sys.exit(0)

    print("=" * 72)
    print("BLOQUEAR CLIENTES FECHADOS — %s" % ("DRY-RUN (não grava)" if dry_run else "APLICAR"))
    print("Arquivo: %s (%d cliente(s) lido(s))" % (path, len(clients)))
    print("=" * 72)

    added_num = added_ct = already_num = already_ct = fail = 0

    for phone, name in sorted(clients.items()):
        # 1) blocked_numbers (blocklist principal do pipeline)
        exists_num = supa.get("blocked_numbers",
                              f"phone=eq.{urllib.parse.quote(phone)}&select=phone")
        if exists_num:
            num_state = "já em blocked_numbers"
            already_num += 1
        elif dry_run:
            num_state = "bloquearia (numbers)"
            added_num += 1
        else:
            ok = K.block_phone(supa, phone, reason="cliente_fechado")
            num_state = "bloqueado (numbers)" if ok else "FALHA ao gravar"
            if ok:
                added_num += 1
            else:
                fail += 1

        # 2) blocked_contacts (convenção status=pago, guarda o nome)
        exists_ct = supa.get("blocked_contacts",
                             f"phone=eq.{urllib.parse.quote(phone)}&select=phone")
        if exists_ct:
            ct_state = "já em blocked_contacts"
            already_ct += 1
        elif dry_run:
            ct_state = "bloquearia (contacts)"
            added_ct += 1
        else:
            payload = {"phone": phone, "name": name or "", "status": "pago",
                       "created_at": K.now_iso()}
            ok = supa.insert("blocked_contacts", payload)
            ct_state = "bloqueado (contacts)" if ok else "FALHA ao gravar"
            if ok:
                added_ct += 1
            else:
                fail += 1

        print("  %s | %-24s | %s | %s" % (phone, (name or "-")[:24], num_state, ct_state))

    print("-" * 72)
    print("RESUMO: novos em numbers=%d, novos em contacts=%d, já existiam=%d, falhas=%d"
          % (added_num, added_ct, already_num + already_ct, fail))
    if dry_run:
        print("(dry-run — nada foi gravado. Remova --dry-run para aplicar.)")


if __name__ == "__main__":
    main()
