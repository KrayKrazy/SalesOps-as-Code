"""Higienização de leads — valida WhatsApp via Evolution e bloqueia inválidos."""
import json
import os
import re
import sys
import time
import urllib.parse

sys.path.insert(0, r"C:\mycelium\SalesOps-as-Code\pipeline")
import kelevra as K

K.setup_console_encoding()
DRY = "--dry-run" in sys.argv
APPLY = "--apply" in sys.argv
BATCH = 100
DELAY = 0.2
OUT = r"C:\Users\Solano\Documents\plano de ação\prospeccao\higiene-leads-resultado.json"

cfg = K.get_config()
s = K.Supabase(cfg)
evo = K.Evolution(cfg)
client = K.HttpClient(evo.base, {"apikey": evo.apikey}, timeout=60)
inst = urllib.parse.quote(evo.instance)


def norm(p):
    d = re.sub(r"\D", "", str(p or ""))
    return ("55" + d) if len(d) in (10, 11) else d


def fetch_unique(table, key="telefone"):
    rows = s.get(table, f"select={key}&limit=10000") or []
    out = {}
    for r in rows:
        p = norm(r.get(key))
        if p and len(p) >= 12:
            out[p] = out.get(p, 0) + 1
    return out


def check_batch(numbers):
    """Mapeia resultado por posição (Evolution preserva ordem)."""
    res = {}
    st, data = client.request("POST", "/chat/whatsappNumbers/" + inst,
                              body={"numbers": numbers})
    if st == 200 and isinstance(data, list) and len(data) == len(numbers):
        for n, d in zip(numbers, data):
            res[n] = bool(d.get("exists")) if isinstance(d, dict) else None
    else:
        # fallback: tenta casar pelo campo number, mas só se casar com o input
        by_number = {}
        if isinstance(data, list):
            for d in data:
                if isinstance(d, dict):
                    by_number[norm(d.get("number") or "")] = bool(d.get("exists"))
        for n in numbers:
            res[n] = by_number.get(n, None)
    return res, st


def apply_from_report():
    """Aplica gravações a partir do relatório JSON salvo (sem re-checar)."""
    if not os.path.exists(OUT):
        sys.exit("Relatório não encontrado. Rode primeiro sem --apply.")
    with open(OUT, "r", encoding="utf-8") as fh:
        rep = json.load(fh)
    valid = set(rep.get("com_whatsapp", []))
    invalid = set(rep.get("sem_whatsapp", []))
    to_block = set(rep.get("a_bloquear", []))
    bc = {norm(r.get("phone")) for r in (s.get("blocked_contacts", "select=phone&limit=10000") or [])}
    to_block = [p for p in to_block if p not in bc]
    print("Aplicando:", len(to_block), "bloqueios + cold_leads + leads")
    inserted = 0
    for i in range(0, len(to_block), 200):
        chunk = to_block[i:i + 200]
        payload = [{"phone": p, "reason": "sem_whatsapp_29-09-2026",
                    "blocked_at": K.now_iso()} for p in chunk]
        if s.insert("blocked_numbers", payload):
            inserted += len(chunk)
        else:
            for p in chunk:
                if s.insert("blocked_numbers", {"phone": p,
                            "reason": "sem_whatsapp_29-09-2026",
                            "blocked_at": K.now_iso()}):
                    inserted += 1
    print("  blocked_numbers inseridos:", inserted)
    cl_rows = s.get("cold_leads", "select=id,telefone&limit=10000") or []
    cl_upd = 0
    for r in cl_rows:
        p = norm(r.get("telefone"))
        if p in valid:
            val = True
        elif p in invalid:
            val = False
        else:
            continue
        if s.update("cold_leads", {"whatsapp_valid": val}, "id", r.get("id")):
            cl_upd += 1
    print("  cold_leads.whatsapp_valid:", cl_upd)
    ld_upd = 0
    for i in range(0, len(to_block), 50):
        chunk = to_block[i:i + 50]
        q = "telefone=in.({})".format(",".join(f'"{urllib.parse.quote(p)}"' for p in chunk))
        st, _ = s.client.request("PATCH", s._path("leads", q),
                                 body={"status": "desqualificado"},
                                 headers={"Prefer": "return=minimal"})
        if st in (200, 204):
            ld_upd += len(chunk)
    print("  leads.status='desqualificado' (lotes):", ld_upd, "(aprox)")
    print("\nAPLICAÇÃO CONCLUÍDA")


def main():
    if APPLY:
        apply_from_report()
        return
    print("=" * 70)
    print("HIGIENIZAÇÃO DE LEADS — validação WhatsApp" + (" [DRY-RUN]" if DRY else ""))
    print("Instância:", evo.instance)
    print("=" * 70)

    uniq = fetch_unique("leads")
    cl = fetch_unique("cold_leads")
    for p, c in cl.items():
        uniq[p] = uniq.get(p, 0) + c
    all_numbers = sorted(uniq.keys())
    print("Números únicos a checar:", len(all_numbers))

    bn = {r.get("phone") for r in (s.get("blocked_numbers", "select=phone&limit=10000") or [])}
    bc = {norm(r.get("phone")) for r in (s.get("blocked_contacts", "select=phone&limit=10000") or [])}
    print("blocked_numbers existentes:", len(bn), "| blocked_contacts (clientes):", len(bc))

    valid, invalid, unknown = {}, {}, {}
    total = len(all_numbers)
    t0 = time.time()
    for i in range(0, total, BATCH):
        chunk = all_numbers[i:i + BATCH]
        res, st = check_batch(chunk)
        if st != 200:
            time.sleep(2)
            res, st = check_batch(chunk)
        for p, exists in res.items():
            if exists is True:
                valid[p] = True
            elif exists is False:
                invalid[p] = True
            else:
                unknown[p] = True
        print("  [%d/%d] v=%d i=%d e=%d" % (min(i + BATCH, total), total,
              len(valid), len(invalid), len(unknown)))
        time.sleep(DELAY)

    elapsed = int(time.time() - t0)
    print()
    print("Total=%d | ComWhatsApp=%d | SemWhatsApp=%d | Erro=%d | %ds"
          % (total, len(valid), len(invalid), len(unknown), elapsed))
    to_block = [p for p in invalid if p not in bc]
    print("A bloquear (novos):", len(to_block))

    report = {"data": K.now_iso(), "instance": evo.instance, "total": total,
              "com_whatsapp": sorted(valid.keys()),
              "sem_whatsapp": sorted(invalid.keys()),
              "erro_indefinido": sorted(unknown.keys()),
              "a_bloquear": sorted(to_block)}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print("Relatório:", OUT)

    if DRY:
        print("[DRY-RUN] nada gravado.")
        return

    # ---- GRAVAÇÃO ----
    print("\nGravando resultados...")
    inserted = 0
    for i in range(0, len(to_block), 200):
        chunk = to_block[i:i + 200]
        payload = [{"phone": p, "reason": "sem_whatsapp_29-09-2026",
                    "blocked_at": K.now_iso()} for p in chunk]
        if s.insert("blocked_numbers", payload):
            inserted += len(chunk)
        else:
            for p in chunk:
                if s.insert("blocked_numbers", {"phone": p,
                            "reason": "sem_whatsapp_29-09-2026",
                            "blocked_at": K.now_iso()}):
                    inserted += 1
    print("  blocked_numbers inseridos:", inserted)

    cl_rows = s.get("cold_leads", "select=id,telefone&limit=10000") or []
    cl_upd = 0
    for r in cl_rows:
        p = norm(r.get("telefone"))
        if p in valid:
            val = True
        elif p in invalid:
            val = False
        else:
            continue
        if s.update("cold_leads", {"whatsapp_valid": val}, "id", r.get("id")):
            cl_upd += 1
    print("  cold_leads.whatsapp_valid atualizados:", cl_upd)

    ld_upd = 0
    for i in range(0, len(to_block), 50):
        chunk = to_block[i:i + 50]
        q = "telefone=in.({})".format(",".join(f'"{urllib.parse.quote(p)}"' for p in chunk))
        st, _ = s.client.request("PATCH", s._path("leads", q),
                                 body={"status": "desqualificado"},
                                 headers={"Prefer": "return=minimal"})
        if st in (200, 204):
            ld_upd += len(chunk)
    print("  leads.status='desqualificado' (lotes):", ld_upd, "(aprox)")

    print("\nHIGIENIZAÇÃO CONCLUÍDA")


if __name__ == "__main__":
    main()
