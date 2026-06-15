import json
import ire.explainer.explainer as ex

class _FakeResp:
    def __init__(self, payload): self._p = payload
    def raise_for_status(self): pass
    def json(self): return self._p

def test_explain_ollama_builds_payload_and_parses(monkeypatch):
    captured = {}
    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        # имитируем ответ Ollama: модель вернула JSON-строку в message.content
        content = '{"driving": ["позже тормози"], "setup_changes": [], "delta": {"X": 1}}'
        return _FakeResp({"message": {"content": content}})
    monkeypatch.setenv("IRE_LLM", "ollama")
    monkeypatch.setenv("IRE_OLLAMA_MODEL", "qwen2.5:7b")
    monkeypatch.setattr(ex.httpx, "post", fake_post)

    r = ex.explain({"balance": {}}, setup_fields={"X": 1}, car="Cadillac GTP", track="Watkins Glen")
    assert r["driving"] == ["позже тормози"]
    assert r["delta"]["X"] == 1
    # payload ушёл на локальный Ollama, /api/chat, с нужной моделью и format=json
    assert captured["url"].endswith("/api/chat")
    assert captured["json"]["model"] == "qwen2.5:7b"
    assert captured["json"]["format"] == "json"
    assert captured["json"]["stream"] is False
    # системный промпт и пользовательский промпт переданы
    roles = [m["role"] for m in captured["json"]["messages"]]
    assert "system" in roles and "user" in roles

def test_default_provider_is_ollama(monkeypatch):
    monkeypatch.delenv("IRE_LLM", raising=False)
    called = {}
    monkeypatch.setattr(ex, "_explain_ollama", lambda prompt: called.setdefault("ollama", True) or {"ok": 1})
    monkeypatch.setattr(ex, "_explain_claude", lambda prompt: called.setdefault("claude", True) or {"ok": 2})
    ex.explain({"balance": {}}, setup_fields={}, car="C", track="T")
    assert called.get("ollama") and not called.get("claude")
