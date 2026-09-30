# -*- coding: utf-8 -*-
"""SDR PIPELINE — orquestrador OUTBOUND Kelevra (stdlib only).

Fluxo: vw_leads_para_prospectar -> blocklist -> dedupe 72h -> [scoring ICP]
       -> abertura (DeepSeek) -> envio (Evolution, round-robin anti-ban)
       -> messages_log -> status.

Uso:
  python sdr_pipeline.py                     # dry-run, 3 leads (não envia)
  python sdr_pipeline.py --send --limit 10   # envia de verdade
  python sdr_pipeline.py --score             # scoring ICP via reasoner (custa mais)
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kelevra as K


def main():
    K.setup_console_encoding()
    argv = sys.argv[1:]
    dry_run = "--send" not in argv
    score = "--score" in argv
    validate = "--no-validate" not in argv
    limit = 3
    if "--limit" in argv:
        i = argv.index("--limit")
        if i + 1 < len(argv):
            try:
                limit = int(argv[i + 1])
            except ValueError:
                limit = 3
    instance = None
    if "--instance" in argv:
        i = argv.index("--instance")
        if i + 1 < len(argv):
            instance = argv[i + 1]

    cfg = K.get_config()
    supa = K.Supabase(cfg)
    ds = K.DeepSeek(cfg)
    evo = K.Evolution(cfg)
    if instance:
        evo.instance = instance

    daily_cap = int(cfg.get("SDR_DAILY_LEAD_CAP", "50") or 50)
    per_instance_quota = cfg.get("SDR_QUOTA_PER_INSTANCE") or None
    status_sent = cfg.get("SDR_STATUS_SENT", "contatado")

    if instance:
        evo.instance = instance
        pool = K.InstancePool([{"name": instance, "quota": 10 ** 9, "sent_today": 0}])
    else:
        pool = K.InstancePool(K.get_whatsapp_pool(supa, evo.instance, per_instance_quota))
    if pool.instances:
        evo.instance = pool.instances[0]["name"]

    if not (supa.url and supa.key):
        sys.exit("ERRO: Supabase sem URL/KEY (rode setup_env.ps1).")
    if not ds.key:
        sys.exit("ERRO: DEEPSEEK_API_KEY ausente.")
    if not dry_run and not (evo.base and evo.apikey):
        sys.exit("ERRO: Evolution sem base/apikey.")

    print("=" * 70)
    print("KELEVRA SDR PIPELINE — %s" % ("DRY-RUN (não envia)" if dry_run else "ENVIO REAL"))
    print("Pool de instâncias: %s" % (pool.summary() or evo.instance))
    print("Conversa: %s | scoring: %s" % (ds.chat_model, ds.reason_model))
    print("=" * 70)

    sent_today = K.count_sent_today(supa)
    print("Disparos hoje: %d / cap %d" % (sent_today, daily_cap))
    if not dry_run and sent_today >= daily_cap:
        sys.exit("Cap diário atingido (anti-ban). Abortando.")

    if limit and limit > 0:
        n = limit
        if not dry_run:
            n = min(limit, daily_cap - sent_today)
    else:
        n = daily_cap - sent_today
    leads = K.get_pending_leads(supa, limit=n)
    if not leads:
        sys.exit("Nenhum lead pendente em vw_leads_para_prospectar.")

    print("Leads pendentes: %d\n" % len(leads))
    ok = skipped = failed = 0

    # Pré-validação de WhatsApp (bloqueia inválidos antes de enviar)
    validation = {}
    if validate:
        candidate_phones = []
        for lead in leads:
            ph = K.normalize_phone(lead.get("telefone") or "")
            if not ph or K.is_blocked(supa, ph) or K.was_contacted_recently(supa, ph, 72):
                continue
            candidate_phones.append(ph)
        if candidate_phones:
            uniq_phones = list(dict.fromkeys(candidate_phones))
            print("Validando WhatsApp de %d número(s) únicos..." % len(uniq_phones))
            validation = K.check_whatsapp_batch(evo, uniq_phones)
            blocked_now = 0
            for ph, exists in validation.items():
                if exists is False:
                    if not dry_run:
                        K.block_phone(supa, ph, reason="sem_whatsapp_auto")
                    blocked_now += 1
            if blocked_now:
                print("  Bloqueados (sem WhatsApp): %d" % blocked_now)
            print()

    for idx, lead in enumerate(leads, 1):
        trace = K.trace_id()
        phone = K.normalize_phone(lead.get("telefone") or "")
        nome = lead.get("nome") or "(sem nome)"
        lid = lead.get("id")
        print("[%d/%d] %s | %s" % (idx, len(leads), nome, phone or "SEM TEL"))

        if not phone:
            print("  ⏭ sem telefone válido")
            skipped += 1
            continue
        if K.is_blocked(supa, phone):
            print("  ⏭ bloqueado (blocklist)")
            skipped += 1
            continue
        if K.was_contacted_recently(supa, phone, 72):
            print("  ⏭ contatado nas últimas 72h (dedupe)")
            skipped += 1
            continue
        if validate and phone in validation and validation[phone] is False:
            print("  ⏭ sem WhatsApp (validado ao vivo)")
            skipped += 1
            continue

        icp_reason = None
        if score:
            try:
                t0 = time.time()
                icp, icp_reason, u = K.score_lead(ds, lead)
                lat = int((time.time() - t0) * 1000)
                print("  ICP=%d (%s)" % (icp, icp_reason))
                K.record_agent_run(supa, "prospector", lid, ds.reason_model, "ok",
                                   {"icp_score": icp}, u.get("prompt_tokens", 0),
                                   u.get("completion_tokens", 0), trace, lat)
            except Exception as e:
                print("  ⚠ scoring falhou: %s" % e)
                K.log_error(supa, "prospector", lid, "score_error", e, {"trace": trace})

        try:
            t0 = time.time()
            text, u = K.generate_opening(ds, lead, icp_reason)
            lat = int((time.time() - t0) * 1000)
        except Exception as e:
            print("  ✗ geração falhou: %s" % e)
            K.log_error(supa, "qualificador", lid, "generate_error", e, {"trace": trace})
            failed += 1
            continue
        if not text:
            print("  ✗ mensagem vazia")
            failed += 1
            continue

        print("  ── %s" % text.replace("\n", " ")[:140])

        if dry_run:
            print("  [DRY-RUN] não enviado")
            ok += 1
            continue

        inst = pool.next()
        if inst is None:
            print("  ⏹ todas as instâncias atingiram a quota diária — abortando envio")
            skipped += 1
            break
        evo.instance = inst["name"]

        try:
            st, resp = evo.send_text(phone, text)
        except Exception as e:
            st, resp = -1, str(e)

        if st in (200, 201):
            pool.record_send(inst)
            K.increment_instance_sent(supa, inst["name"])
            K.log_message(supa, lead, text, "sent", http_resp=resp, trace=trace)
            if lid is not None:
                try:
                    supa.update("leads", {"status": status_sent}, "id", lid)
                except Exception:
                    pass
            K.record_agent_run(supa, "qualificador", lid, ds.chat_model, "sent",
                               {"telefone": phone, "instance": inst["name"]},
                               u.get("prompt_tokens", 0),
                               u.get("completion_tokens", 0), trace, lat)
            print("  ✔ enviado via %s" % inst["name"])
            ok += 1
        else:
            K.log_message(supa, lead, text, "failed", error=str(resp), trace=trace)
            K.log_error(supa, "qualificador", lid, "send_error", resp,
                        {"trace": trace, "instance": inst["name"]})
            print("  ✗ falha (%s) via %s: %s" % (st, inst["name"], str(resp)[:200]))
            failed += 1

    print("\n" + "=" * 70)
    print("RESUMO: ok=%d pulados=%d falhas=%d" % (ok, skipped, failed))
    print("=" * 70)


if __name__ == "__main__":
    main()
