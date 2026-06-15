# iRacing Race Engineer

Персональный «гоночный инженер» для iRacing: после заезда анализирует телеметрию + условия трассы + текущий сетап и выдаёт разбор пилотирования, рекомендации по сетапу и готовый `.sto`-файл с объяснением.

**v1:** Cadillac V-Series.R GTP @ Watkins Glen, только пост-анализ.

## Документы
- Спека (дизайн): [`docs/superpowers/specs/2026-06-15-iracing-race-engineer-design.md`](docs/superpowers/specs/2026-06-15-iracing-race-engineer-design.md)
- План реализации (по задачам): [`docs/superpowers/plans/2026-06-15-iracing-race-engineer.md`](docs/superpowers/plans/2026-06-15-iracing-race-engineer.md)

## ⚠️ Платформа
Всё запускается на **Windows-ПК, где установлен iRacing** (SDK = Windows memory-mapped file). Разработка метрик идёт оффлайн на записанной фикстуре, но спайки и сквозной прогон требуют запущенного iRacing.

## Подхват на Windows (порядок)
```bash
git clone <этот-репозиторий>
cd iracing-race-engineer
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt        # появится после Task 1
setx ANTHROPIC_API_KEY "<ключ>"         # для модуля explainer
```
Дальше открыть план и идти по задачам **по порядку** — начиная с Task 1 (скаффолд), затем спайки Task 2–4 (снимают единственные неизвестные: реальные имена каналов SDK и формат `.sto`). Метрики (Task 10–15) пилятся на фикстуре без сима.

Рекомендуемый способ исполнения — субагент на задачу (`superpowers:subagent-driven-development`).

## Архитектура (5 модулей, всё локально на Windows)
1. **collector** — pyirsdk → нормализованный кадр телеметрии + лог стинта.
2. **metrics** — детерминированный расчёт симптомов (шины/баланс/подвеска/инпуты/стабильность) → JSON. *Тестируемое ядро.*
3. **explainer** — Claude: симптомы + сетап → разбор + дельта. *Сменный модуль (Claude Code → Claude API).*
4. **setup** — чтение/запись `.sto` (новый файл, исходник не трогаем).
5. **dashboard** — FastAPI + HTML на втором экране (живьё + разбор).

## Шаг 2 (будущее, не в v1)
Живой гоночный инженер во время гонки: пит-стратегия, слежка за соперником, подсказки по тому, что крутится на ходу (ABS/ТК/тормозной баланс). См. §11 спеки.
