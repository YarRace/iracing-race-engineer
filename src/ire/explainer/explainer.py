import json, os

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
    from anthropic import Anthropic
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model="claude-opus-4-8", max_tokens=2000, system=SYSTEM,
        messages=[{"role": "user", "content": build_prompt(symptoms, setup_fields, car, track)}],
    )
    return parse_response(msg.content[0].text)
