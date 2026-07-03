"""v0.5.2 — agent loop sonlandirma + tekrar fix'leri (a/b/d)."""
import agents.code_agent as ca
from protocols.safety import ApprovalResult
from runtime.session import Session


class _Deny:
    """Her onayi reddeder (rejection senaryosu icin)."""
    def request(self, proposal):
        return ApprovalResult.deny("test-red")


def _no_ingest(monkeypatch):
    monkeypatch.setattr(ca, "ingest_session", lambda sid, w: 0)


# (a) Duz metin -> FINAL kabul edilir, tek turda biter (sessiz tekrar yok).
def test_plaintext_accepted_as_final(tmp_path, monkeypatch):
    _no_ingest(monkeypatch)
    calls = {"n": 0}

    def fake(_m, _c):
        calls["n"] += 1
        return "README ilk satiri: # Quantum Labs"   # JSON YOK, duz metin

    monkeypatch.setattr(ca, "ask_model", fake)
    ret = ca.run_agent("ozetle", session=Session(str(tmp_path)),
                       workspace=str(tmp_path), memory_injection=False, max_steps=8)
    assert calls["n"] == 1                            # tek tur (dongu yok)
    assert ret == "README ilk satiri: # Quantum Labs"


# (d) Ayni action + ayni observation 3 kez ustuste -> guard kirar, ozet doner.
def test_repeat_guard_breaks_loop(tmp_path, monkeypatch):
    _no_ingest(monkeypatch)
    (tmp_path / "hello.txt").write_text("merhaba\n", encoding="utf-8")
    calls = {"n": 0}

    def fake(_m, _c):
        calls["n"] += 1
        return '{"tool":"read_file","args":{"path":"hello.txt"}}'   # hep AYNI

    monkeypatch.setattr(ca, "ask_model", fake)
    ret = ca.run_agent("oku", session=Session(str(tmp_path)),
                       workspace=str(tmp_path), memory_injection=False, max_steps=10)
    assert calls["n"] == 3                             # 3. tekrarda kirildi (10 degil)
    assert "dongu durduruldu" in ret
    assert "merhaba" in ret                            # son observation ozette


# (d) Farkli argumanlar -> guard TETIKLENMEZ (yanlis-pozitif olmasin).
def test_repeat_guard_not_triggered_when_args_differ(tmp_path, monkeypatch):
    _no_ingest(monkeypatch)
    n = {"i": 0}

    def fake(_m, _c):
        n["i"] += 1
        return '{"tool":"search_code","args":{"query":"q%d"}}' % n["i"]

    monkeypatch.setattr(ca, "ask_model", fake)
    ret = ca.run_agent("ara", session=Session(str(tmp_path)),
                       workspace=str(tmp_path), memory_injection=False, max_steps=4)
    assert n["i"] == 4                                 # guard atesleMEDI -> max-step'e kadar
    assert ret is None


# (b) Reddedilen action bir sonraki prompt'ta ACIK uyariyla geciyor mu.
def test_rejection_feedback_in_prompt(tmp_path, monkeypatch):
    _no_ingest(monkeypatch)
    calls = {"n": 0, "msgs2": None}

    def fake(messages, _c):
        calls["n"] += 1
        if calls["n"] == 1:
            return '{"tool":"write_file","args":{"path":"x.txt","content":"hi"}}'
        calls["msgs2"] = [dict(m) for m in messages]
        return '{"tool":"final","args":{"answer":"bitti"}}'

    monkeypatch.setattr(ca, "ask_model", fake)
    ret = ca.run_agent("yaz", session=Session(str(tmp_path)), workspace=str(tmp_path),
                       approver=_Deny(), memory_injection=False, max_steps=5)
    assert ret == "bitti"
    last_user = calls["msgs2"][-1]["content"]
    assert "REDDEDILDI" in last_user                   # acik uyari eklendi
    assert "TEKRAR DENEME" in last_user
    assert not (tmp_path / "x.txt").exists()            # yazilmadi
