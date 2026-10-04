"""Testes das partes puras e da fila por lead. Rode: pytest -q  (sem plugin asyncio; usa asyncio.run)."""
import asyncio
import json
import time

import pytest

import sdr_v4_fastapi as main


# ---------- triage ----------
@pytest.mark.parametrize("text,expected", [
    ("Quanto custa para começar?", "DUVIDA"),            # 'para' não é mais opt-out
    ("Gostaria de saiba mais, a Carolina indicou", "DUVIDA"),
    ("isso é ilegal?", "DUVIDA"),
    ("vocês têm callcenter?", "DUVIDA"),
    ("Pare de me mandar mensagem", "OPT_OUT"),
    ("NÃO QUERO mais receber", "OPT_OUT"),
    ("isso é golpe", "OPT_OUT"),
    ("Achei caro", "OBJECAO_PROFUNDA"),
    ("Tá, pode mandar o PIX", "INTERESSE_COMPRA"),
    ("Dá pra agendar uma reunião?", "INTERESSE_AGENDA"),
    ("Quero saber mais", "INTERESSE"),
    ("ok", "DUVIDA"),
])
def test_classify(text, expected):
    assert main.classify(text) == expected


# ---------- telefone ----------
def test_normalize_phone():
    assert main.normalize_phone("556199998888@s.whatsapp.net") == "5561999998888"      # insere o 9
    assert main.normalize_phone("5561999998888:12@s.whatsapp.net") == "5561999998888"  # sufixo de device
    assert main.normalize_phone("551133334444") == "551133334444"                      # fixo: não mexe
    assert main.normalize_phone("abc") == ""


# ---------- reviewer ----------
def test_reviewer_preserves_link_and_converts_bold():
    out = main.node_reviewer({"draft_message": "Veja [Pagar](https://pay.exemplo.com/abc) e **combinado**"})
    assert out["final_message"] == "Veja Pagar: https://pay.exemplo.com/abc e *combinado*"


def test_reviewer_blocks_placeholder():
    out = main.node_reviewer({"draft_message": "Segue o link: [LINK GERADO]", "phone": "5561999998888"})
    assert out["final_message"] == "" and out["human_escalation"] is True


# ---------- horário comercial ----------
def test_business_hours():
    from datetime import datetime
    ts = lambda y, m, d, h: datetime(y, m, d, h, tzinfo=main.TIMEZONE).timestamp()
    assert main.in_business_hours(ts(2026, 10, 5, 10))       # segunda 10h
    assert not main.in_business_hours(ts(2026, 10, 5, 20))   # segunda 20h
    assert not main.in_business_hours(ts(2026, 10, 3, 10))   # sábado


# ---------- follow-up ----------
def test_followup_block_reasons():
    run = lambda s, now: asyncio.run(main.followup_block_reason(s, now))
    base = {"messages": [{"role": "user"}], "last_inbound_at": 100.0, "last_outbound_at": 200.0}
    assert run({}, time.time()) == "no_history"
    assert run({**base, "follow_up_count": main.MAX_FOLLOWUPS}, time.time()) == "max_followups"
    assert run({**base, "last_inbound_at": 300.0}, time.time()) == "awaiting_our_reply"
    assert run(base, 200.0 + 60) == "too_soon"


# ---------- entrada do grafo ----------
AUDIO = {"id": "A1", "type": "audioMessage", "mimetype": "audio/ogg; codecs=opus"}
IMAGE = {"id": "I1", "type": "imageMessage", "mimetype": "image/jpeg"}


def test_graph_input_batches_messages_and_resets_state():
    items = [
        {"kind": "message", "text": "oi", "media": None, "reply_to": "556199998888"},
        {"kind": "message", "text": "quero saber mais", "media": None, "reply_to": "556199998888"},
        {"kind": "followup"},
    ]
    inp = main.build_graph_input(items, "5561999998888", "default")
    assert inp["incoming_text"] == "oi\nquero saber mais"
    assert len(inp["messages"]) == 2 and inp["follow_up_count"] == 0
    assert inp["final_message"] == "" and inp["drafts"] == [] and inp["media_refs"] == []


def test_graph_input_followup_only_has_no_messages():
    inp = main.build_graph_input([{"kind": "followup"}], "5561999998888", "default")
    assert inp["trigger"] == "followup" and "messages" not in inp


def test_graph_input_media_only_defers_history_to_media_ingest():
    inp = main.build_graph_input([{"kind": "message", "text": "", "media": AUDIO, "reply_to": "x"}], "5561999998888", "default")
    assert inp["media_refs"] == [AUDIO] and inp["messages"] == [] and inp["incoming_text"] == ""


# ---------- mídia ----------
def _run_ingest(monkeypatch, state, fetched=(b"x", "audio/ogg"), transcript=None, description=None):
    async def fake_fetch(ref, instance=None):
        return fetched

    async def fake_transcribe(data, mimetype):
        return transcript

    async def fake_describe(data, mimetype):
        return description

    monkeypatch.setattr(main, "store", main.MemoryStore())
    monkeypatch.setattr(main, "fetch_media", fake_fetch)
    monkeypatch.setattr(main.media_handler, "transcribe_audio", fake_transcribe)
    monkeypatch.setattr(main.media_handler, "describe_image", fake_describe)
    return asyncio.run(main.node_media_ingest({"phone": "5561999998888", **state}))


def test_spoken_opt_out_reaches_classifier(monkeypatch):
    out = _run_ingest(monkeypatch, {"media_refs": [AUDIO], "incoming_text": ""}, transcript="pare de me mandar mensagem")
    assert main.classify(out["incoming_text"]) == "OPT_OUT" and "media_failed" not in out


def test_image_description_is_never_classified(monkeypatch):
    out = _run_ingest(monkeypatch, {"media_refs": [IMAGE], "incoming_text": ""},
                      fetched=(b"x", "image/jpeg"), description="Print de uma conversa dizendo: isso é golpe, pare")
    assert out["incoming_text"] == "" and "golpe" in out["image_context"]
    state = {"phone": "5561999998888", "trigger": "message", **out}
    monkeypatch.setattr(main, "store", main.MemoryStore())
    assert asyncio.run(main.node_triage(state))["intent"] == "DUVIDA"  # não vira OPT_OUT


def test_media_failure_sets_flag_and_routes_to_honest_reply(monkeypatch):
    out = _run_ingest(monkeypatch, {"media_refs": [AUDIO], "incoming_text": ""}, fetched=None)
    assert out["media_failed"] is True
    monkeypatch.setattr(main, "store", main.MemoryStore())
    triage = asyncio.run(main.node_triage({"phone": "5561999998888", "trigger": "message", "incoming_text": "", **out}))
    assert triage["intent"] == "MIDIA" and main.route_after_triage(triage) == "media"
    assert "ligação" not in main.node_media_reply({})["draft_message"]


def test_caption_survives_media_failure(monkeypatch):
    out = _run_ingest(monkeypatch, {"media_refs": [IMAGE], "incoming_text": "olha isso"}, fetched=None)
    assert out["incoming_text"] == "olha isso" and "media_failed" not in out


def test_media_skipped_for_opted_out_lead(monkeypatch):
    async def go():
        main.store = main.MemoryStore()
        await main.store.set(f"optout:{main.lead_key('5561999998888', 'default')}", "1")
        return await main.node_media_ingest({"phone": "5561999998888", "media_refs": [AUDIO], "instance": "default"})
    assert asyncio.run(go()) == {}


def test_media_handler_helpers():
    h = main.media_handler
    assert h.clean_mimetype("audio/ogg; codecs=opus") == "audio/ogg"
    assert h.clean_mimetype("IMAGE/JPG") == "image/jpeg"
    assert asyncio.run(h.describe_image(b"", "image/jpeg")) is None            # sem chave/vazio: None, sem exceção
    assert asyncio.run(h.transcribe_audio(b"abc", "audio/ogg")) is None        # sem STT_API_KEY: None


# ---------- store, lock e fila ----------
def test_memory_store_lock_and_idempotency():
    async def go():
        s = main.MemoryStore()
        assert await s.set_nx("k", 60) is True
        assert await s.set_nx("k", 60) is False
        t = await s.acquire_lock("l", 60)
        assert t and await s.acquire_lock("l", 60) is None
        await s.release_lock("l", "token-errado")
        assert await s.acquire_lock("l", 60) is None
        await s.release_lock("l", t)
        assert await s.acquire_lock("l", 60)
    asyncio.run(go())


def test_drain_runs_one_batch_for_burst(monkeypatch):
    calls = []

    async def fake_process(phone, instance, items):
        calls.append([i.get("text") for i in items])

    async def go():
        monkeypatch.setattr(main, "store", main.MemoryStore())
        monkeypatch.setattr(main, "DEBOUNCE_SECONDS", 0.05)
        monkeypatch.setattr(main, "process_items", fake_process)
        phone = "5561999998888"
        instance = "default"
        buf = f"buf:{main.lead_key(phone, instance)}"
        for t in ("a", "b", "c"):
            await main.store.push(buf, json.dumps({"kind": "message", "text": t}))
        await asyncio.gather(main.drain(phone, instance), main.drain(phone, instance), main.drain(phone, instance))  # só 1 consome
        return calls

    assert asyncio.run(go()) == [["a", "b", "c"]]
