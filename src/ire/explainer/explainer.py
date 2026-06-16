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

# Глоссарий: как правильно называть параметры по-русски (поля сетапа адресуются
# английскими путями вида "Chassis.Front.ArbSize", но в тексте 'why'/'driving' —
# человеческие русские термины).
GLOSSARY = (
    "Термины (пиши в тексте по-русски правильно): ARB/ArbSize = стабилизатор поперечной "
    "устойчивости; Camber = развал; ToeIn = схождение; RideHeight = клиренс; SpringRate = "
    "жёсткость пружины; Shock/Damping = амортизатор (Comp = сжатие, Rbd = отбой); Preload = "
    "преднатяг дифференциала; BrakePressureBias = баланс тормозов; StartingPressure = давление "
    "в шине; understeer = недостаточная поворачиваемость (недоруль); oversteer = избыточная (переруль)."
)

# Базовые инженерные правила, чтобы советы шли в верную сторону.
RULES = (
    "Правила настройки. При НЕДОСТАТОЧНОЙ поворачиваемости (understeer) — добавить переднего "
    "сцепления: смягчить ПЕРЕДНИЙ стабилизатор ИЛИ ужестчить ЗАДНИЙ; снизить давление передних "
    "шин или повысить задних; добавить отрицательного развала спереди; смягчить передние пружины "
    "или ужестчить задние. При ИЗБЫТОЧНОЙ (oversteer) — всё наоборот. Меняй значения маленькими "
    "шагами и только в сторону, согласованную с симптомами заезда."
)

SYSTEM = (
    "Ты — гоночный инженер по сетапам iRacing. Отвечай СТРОГО на русском языке "
    "(весь текст внутри JSON — по-русски, без китайских иероглифов). На вход: посчитанные "
    "симптомы заезда и текущие значения сетапа. Меняй ТОЛЬКО переданные поля сетапа. "
    + GLOSSARY + " " + RULES + " "
    "Верни СТРОГО один JSON-объект без текста вне него, по схеме: "
    '{"driving": ["совет по пилотированию", ...], '
    '"setup_changes": [{"field": "имя поля", "from": "текущее значение", "to": "новое значение", "why": "причина"}], '
    '"delta": {"имя поля": "новое значение"}}. '
    "ВАЖНО: значения 'to' и значения в 'delta' — это ИТОГОВЫЕ значения той же формы и в тех же "
    'единицах, что в исходном сетапе (например "148 kPa", "-3.1 deg"), а НЕ приращения. '
    "Пары field→to из setup_changes должны точно совпадать с парами в delta."
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
