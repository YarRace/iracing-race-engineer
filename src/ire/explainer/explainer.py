"""Разбор заезда: симптомы + сетап -> рекомендации по пилотированию и правкам.

LLM-провайдер выбирается через переменную окружения IRE_LLM:
  - "ollama" (по умолчанию) — локальный сервер Ollama, бесплатно, без облака
    (IRE_OLLAMA_HOST, IRE_OLLAMA_MODEL);
  - "claude" — облачный Anthropic API, требует ANTHROPIC_API_KEY.

Построение промпта (build_prompt) и парсинг ответа (parse_response) общие
для обоих провайдеров.
"""
import json, os
import httpx

SYSTEM = (
    "Ты — гоночный инженер по сетапам iRacing. На вход: посчитанные симптомы заезда "
    "и текущие значения сетапа. Меняй ТОЛЬКО переданные поля, в их разумных пределах. "
    "Верни строго JSON: {driving:[...], setup_changes:[{field,from,to,why}], delta:{field:value}}."
)

def build_prompt(symptoms, setup_fields, car, track):
    return (f"Машина: {car}. Трасса: {track}.\n"
            f"Текущий сетап (только эти поля можно менять):\n{json.dumps(setup_fields, ensure_ascii=False, indent=2)}\n"
            f"Симптомы заезда:\n{json.dumps(symptoms, ensure_ascii=False, indent=2)}\n"
            "Дай разбор пилотирования и правки сетапа.")

def parse_response(text):
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])

def explain(symptoms, setup_fields, car="Cadillac GTP", track="Watkins Glen"):
    prompt = build_prompt(symptoms, setup_fields, car, track)
    provider = os.environ.get("IRE_LLM", "ollama").lower()
    if provider == "claude":
        return _explain_claude(prompt)
    return _explain_ollama(prompt)

def _explain_claude(prompt):
    from anthropic import Anthropic
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model="claude-opus-4-8", max_tokens=2000, system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return parse_response(msg.content[0].text)

def _explain_ollama(prompt):
    host = os.environ.get("IRE_OLLAMA_HOST", "http://localhost:11434")
    model = os.environ.get("IRE_OLLAMA_MODEL", "qwen2.5:7b")
    resp = httpx.post(
        f"{host}/api/chat",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.3},
        },
        timeout=120,
    )
    resp.raise_for_status()
    return parse_response(resp.json()["message"]["content"])
