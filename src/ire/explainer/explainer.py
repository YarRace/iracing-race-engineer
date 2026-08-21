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

# Глоссарий: как правильно называть параметры по-английски (поля сетапа адресуются
# английскими путями вида "Chassis.Front.ArbSize", но в тексте 'why'/'driving' —
# человеческие английские термины).
GLOSSARY = (
    "Terms (use these exact words in your text): ARB/ArbSize = anti-roll bar; Camber = camber; "
    "ToeIn = toe; RideHeight = ride height; SpringRate = spring rate; Shock/Damping = damper "
    "(Comp = compression, Rbd = rebound); Preload = differential preload; BrakePressureBias = "
    "brake bias; StartingPressure = tire pressure; understeer = the front will not turn in (the "
    "car pushes); oversteer = the rear steps out (the car is loose)."
)

# Базовые инженерные правила, чтобы советы шли в верную сторону.
RULES = (
    "Setup rules. For UNDERSTEER — add front grip: soften the FRONT anti-roll bar OR stiffen the "
    "REAR; lower the front tire pressure or raise the rear; add negative camber at the front; "
    "soften the front springs or stiffen the rear. For OVERSTEER — do the opposite. Change values "
    "in small steps, and only in the direction that matches the symptoms from the stint."
)

SYSTEM = (
    "You are an iRacing race engineer working on car setup. Write STRICTLY in English "
    "(all text inside the JSON in English — clear, simple words, no Chinese characters). Input: "
    "computed stint symptoms and the current setup values. Change ONLY the setup fields you are given. "
    + GLOSSARY + " " + RULES + " "
    "Return STRICTLY one JSON object with no text outside it, using this schema: "
    '{"driving": ["driving tip", ...], '
    '"setup_changes": [{"field": "field name", "from": "current value", "to": "new value", "why": "reason"}], '
    '"delta": {"field name": "new value"}}. '
    "IMPORTANT: the 'to' values and the values in 'delta' are FINAL values, in the same form and the "
    'same units as in the source setup (for example "148 kPa", "-3.1 deg"), NOT increments. '
    "The field→to pairs in setup_changes must exactly match the pairs in delta."
)

def build_prompt(symptoms, setup_fields, car, track):
    # Машина и трасса приходят из живой сессии. Если их нет — честно пишем
    # «unknown»: назвать чужую машину хуже, чем признать незнание, потому что
    # советы по сетапу у GTP и GT3 разные.
    car = car or "unknown"
    track = track or "unknown"
    return (f"Car: {car}. Track: {track}.\n"
            f"Current setup (only these fields may be changed):\n{json.dumps(setup_fields, ensure_ascii=False, indent=2)}\n"
            f"Stint symptoms:\n{json.dumps(symptoms, ensure_ascii=False, indent=2)}\n"
            "Give the driving analysis and the setup changes.")

def parse_response(text):
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])

def explain(symptoms, setup_fields, car=None, track=None):
    prompt = build_prompt(symptoms, setup_fields, car, track)
    provider = os.environ.get("IRE_LLM", "ollama").lower()
    if provider == "claude":
        return _explain_claude(prompt)
    return _explain_ollama(prompt)

def _explain_claude(prompt):
    from anthropic import Anthropic
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        # модель задаётся переменной: раньше здесь стояла claude-opus-4-8,
        # которой не существует — при IRE_LLM=claude разбор просто падал
        model=os.environ.get("IRE_CLAUDE_MODEL", "claude-opus-5"),
        max_tokens=2000, system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return parse_response(msg.content[0].text)

def _explain_ollama(prompt):
    host = os.environ.get("IRE_OLLAMA_HOST", "http://localhost:11434")
    model = os.environ.get("IRE_OLLAMA_MODEL", "qwen2.5:7b")
    # GPU делится с iRacing → инференс медленный; большой таймаут + держим модель в VRAM
    timeout = float(os.environ.get("IRE_OLLAMA_TIMEOUT", "600"))
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
            "keep_alive": "30m",            # модель не выгружается между стинтами
            "options": {"temperature": 0.3, "num_predict": 2048},
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return parse_response(resp.json()["message"]["content"])


def warm_up():
    """Прогрев: грузит модель в VRAM заранее (чтобы первый разбор был быстрым).
    Безопасно — при недоступном Ollama просто молча выходит."""
    if os.environ.get("IRE_LLM", "ollama").lower() == "claude":
        return
    host = os.environ.get("IRE_OLLAMA_HOST", "http://localhost:11434")
    model = os.environ.get("IRE_OLLAMA_MODEL", "qwen2.5:7b")
    try:
        httpx.post(f"{host}/api/chat", json={
            "model": model, "messages": [{"role": "user", "content": "ok"}],
            "stream": False, "keep_alive": "30m",
        }, timeout=600)
    except Exception:
        pass
