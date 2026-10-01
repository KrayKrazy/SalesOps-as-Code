"""FOLLOW-UP PIPELINE — segundo toque automático para quem respondeu.

Lê os respondentes (inbound em messages_log) em ordem de prioridade, gera o
follow-up (DeepSeek), envia (Evolution) e marca o lead como 'finalizado'
(soft delete) — concluindo o ciclo de cadência.

Uso:
    python followup_pipeline.py                     # dry-run, 3 respondentes
    python followup_pipeline.py --send --limit 5    # envia de verdade
    python followup_pipeline.py --no-validate       # pula validação de WhatsApp
"""
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kelevra as K


def main():
    K.setup_console_encoding()
    argv = sys.argv[1:]
    dry_run = "--send" not in argv
    validate = "--no-validate" not in argv
    limit = 3
    if "--limit" in argv:
        i = argv.index("--limit")
        if i + 1 < len(argv):
            try:
                limit = int(argv[i + 1])
            except ValueError:
                limit = 3

    cfg = K.get_config()
    supa = K.Supabase(cfg)
    ds = K.DeepSeek(cfg)
    evo = K.Evolution(cfg)

    daily_cap = int(cfg.get("SDR_DAILY_LEAD_CAP", "50") or 50)
    per_instance_quota = cfg.get("SDR_QUOTA_PER_INSTANCE") or None
    done_status = cfg.get("SDR_STATUS_DONE", "finalizado")
    interval_min = int(cfg.get("SDR_SEND_INTERVAL_MIN", "120") or 120)
    interval_max = int(cfg.get("SDR_SEND_INTERVAL_MAX", "240") or 240)
    interval_max = max(interval_max, interval_min)

    pool = K.InstancePool(K.get_whatsapp_pool(supa, evo.instance, per_instance_quota))
    if pool.instances:
        evo.instance = pool.instances[0]["name"]

    if not (supa.url and supa.key):
        sys.exit("ERRO: Supabase sem URL/KEY.")
    if not ds.key:
        sys.exit("ERRO: DEEPSEEK_API_KEY ausente.")
    if not dry_run and not (evo.base and evo.apikey):
        sys.exit("ERRO: Evolution sem base/apikey.")

    print("=" * 72)
    print("KELEVRA FOLLOW-UP PIPELINE — %s" % ("DRY-RUN (não envia)" if dry_run else "ENVIO REAL"))
    print("=" * 72)

    respondents = K.get_respondents(supa, done_status=done_status)
    if not respondents:
        sys.exit("Nenhum respondente pendente de follow-up.")

    sent_today = K.count_sent_today(supa)
    print("Respondentes pendentes: %d | disparos hoje: %d / cap %d"
          % (len(respondents), sent_today, daily_cap))
    if not dry_run and sent_today >= daily_cap:
        sys.exit("Cap diário atingido (anti-ban). Abortando.")

    target = limit
    if not dry_run:
        target = min(limit, daily_cap - sent_today)
        if target <= 0:
            sys.exit("Cap diário atingido (anti-ban). Abortando.")

    ok = skipped = failed = 0
    last_send_ts = 0.0

    for idx, r in enumerate(respondents, 1):
        if ok >= target:
            break
        phone = r["telefone"]
        nome = r["nome"]
        lid = r["id"]
        print("[%d] %s | %s | %s" % (idx, nome, phone, r["nicho"]))

        if K.is_blocked(supa, phone):
            print("  ⏭ bloqueado (blocklist)")
            skipped += 1
            continue
        if K.was_contacted_recently(supa, phone, 1):
            print("  ⏭ contatado recentemente (anti-duplo)")
            skipped += 1
            continue
        if validate:
            v = K.check_whatsapp_batch(evo, [phone])
            if v.get(phone) is False:
                print("  ⏭ sem WhatsApp")
                skipped += 1
                continue

        try:
            text, _u = K.generate_followup(ds, r, r["resposta"])
        except Exception as e:
            print(f"  ✗ geração falhou: {e}")
            failed += 1
            continue
        if not text:
            print("  ✗ mensagem vazia")
            failed += 1
            continue

        print("  ── {}".format(text.replace("\n", " ")[:140]))

        if dry_run:
            print("  [DRY-RUN] não enviado")
            ok += 1
            continue

        if last_send_ts:
            wait = random.uniform(interval_min, interval_max) - (time.time() - last_send_ts)
            if wait > 0:
                print(f"  ⏳ aguardando {wait:.0f}s (anti-ban)")
                time.sleep(wait)

        inst = pool.next()
        if inst is None:
            print("  ⏹ quota das instâncias esgotada — abortando")
            skipped += 1
            break
        evo.instance = inst["name"]

        try:
            st, resp = evo.send_text(phone, text)
        except Exception as e:
            st, resp = -1, str(e)
        last_send_ts = time.time()

        if st in (200, 201):
            pool.record_send(inst)
            K.increment_instance_sent(supa, inst["name"])
            K.log_message(supa, {"id": lid, "telefone": phone}, text, "sent",
                          http_resp=resp, trace=K.trace_id(), follow_up_num=1)
            if lid:
                try:
                    supa.update("leads", {"status": done_status}, "id", lid)
                except Exception:
                    pass
            print(f"  ✔ follow-up enviado e lead -> {done_status}")
            ok += 1
        else:
            K.log_message(supa, {"id": lid, "telefone": phone}, text, "failed",
                          error=str(resp), trace=K.trace_id(), follow_up_num=1)
            print(f"  ✗ falha ({st}): {str(resp)[:200]}")
            failed += 1

    print("\n" + "=" * 72)
    print("RESUMO follow-up: ok=%d pulados=%d falhas=%d" % (ok, skipped, failed))
    print("=" * 72)


if __name__ == "__main__":
    main()
