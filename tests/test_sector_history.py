"""Разбор секторов после заезда: стабильная потеря против разовой.

Числа здесь взяты из НАСТОЯЩЕЙ базы Ярослава (Спа, Ferrari 499P, заезд на 45
кругов), а не придуманы. Так видно, что модуль отвечает то же, что видно
глазами в данных.
"""
import statistics

import pytest

from ire.metrics import sector_history as SH


def lap(n, s, ts="2026-08-20T12:00:00", track="spa", car="Ferrari 499P",
        recorded_all=True):
    return {"lap_num": n, "lap_time": round(sum(s), 2), "sectors": list(s),
            "ts": ts, "track": track, "config": "Grand Prix", "car": car,
            "session_type": "Practice", "recorded_all": recorded_all}


def run_of(k, spread=0.0, loose_sector=None, loose_by=0.0):
    """Ровный заезд из k кругов.

    `loose_sector` — сектор, в котором типичный круг ДАЛЬШЕ ОТ СВОЕГО ЛУЧШЕГО,
    чем остальные. Именно это и ищет модуль: не «сектор медленный вообще»
    (без чужой опоры такого не узнать — равномерный сдвиг двигает и лучший,
    и типичный), а «здесь ты раз за разом не попадаешь в свой же лучший».
    """
    out = []
    for i in range(k):
        s = [33.6, 30.5, 25.6]
        # Небольшой разброс, чтобы MAD не был нулём: без него стандартная
        # ошибка тоже ноль, и любые два сектора «различимы» — тест был бы
        # зелёным по недоразумению.
        s = [round(x + spread * ((i % 5) - 2) / 2.0, 3) for x in s]
        if loose_sector is not None and i > 0:
            # Первый круг остаётся эталоном, остальные не дотягивают.
            s[loose_sector] = round(s[loose_sector] + loose_by, 3)
        out.append(lap(i + 1, s))
    return out


# ── стабильно против разово ─────────────────────────────────────────────────

def test_the_sector_you_never_get_right_is_named():
    """Ради этого всё и считается: если в одном секторе типичный круг всегда
    хуже твоего же лучшего, время лежит именно там — и это сетап или
    техника, а не ошибка, которую можно объехать."""
    r = SH.report(run_of(20, spread=0.06, loose_sector=2, loose_by=0.4))
    assert r["ok"]
    assert r["stable"] == 3
    assert "S3 costs you" in r["headline"]


def test_a_sector_that_is_uniformly_slower_is_NOT_called_out():
    """Честная граница возможностей: без чужой опоры «сектор медленный
    вообще» не определить — равномерный сдвиг двигает и лучший круг, и
    типичный. Модуль обязан молчать, а не выдавать это за находку."""
    laps = []
    for i in range(20):
        s = [33.6, 30.5, 26.0]                       # S3 медленнее на 0.4 ВСЕГДА
        s = [round(x + 0.06 * ((i % 5) - 2) / 2.0, 3) for x in s]
        laps.append(lap(i + 1, s))
    r = SH.report(laps)
    assert r["stable"] is None, "выдали равномерный сдвиг за находку"


def test_one_bad_lap_does_not_become_a_verdict_about_the_setup():
    """Ошибка в одном круге и медленный сетап — разные болезни. Среднее их
    путает, поэтому опора здесь медиана."""
    laps = run_of(20, spread=0.06)
    laps[7]["sectors"][1] += 3.0                     # одна ошибка во втором
    laps[7]["lap_time"] = round(sum(laps[7]["sectors"]), 2)

    r = SH.report(laps)
    s2 = r["sectors"][1]
    assert s2["every_lap"] < 0.2, "разовая ошибка утекла в «каждый круг»"
    assert s2["one_off_total"] > 2.5, "разовую потерю не заметили вовсе"
    assert s2["one_off_laps"][0]["lap"] == 8, "виновный круг назван неверно"


def test_the_guilty_laps_are_named_by_number():
    """«Потеряно 3 секунды» без номера круга — это некуда пойти и посмотреть."""
    laps = run_of(20, spread=0.06)
    laps[3]["sectors"][0] += 2.0
    laps[3]["lap_time"] = round(sum(laps[3]["sectors"]), 2)
    r = SH.report(laps)
    worst = r["sectors"][0]["one_off_laps"][0]
    assert worst["lap"] == 4, "виновный круг назван неверно"
    assert worst["plus"] == pytest.approx(2.0, abs=0.1)


# ── честность на малой выборке ──────────────────────────────────────────────

def test_three_laps_are_not_enough_to_call_a_sector_slow():
    """Измерено на его базе: на трёх кругах правило ошибалось в половине
    случаев. Число, неверное в половине случаев, хуже отсутствия числа."""
    r = SH.report(run_of(3, spread=0.06, loose_sector=2, loose_by=0.4))
    assert r["ok"] is True
    assert r["stable"] is None
    assert "too few" in r["why"]
    assert str(SH.MIN_STABLE_LAPS) in r["why"], "не сказано, сколько нужно"


def test_two_sectors_within_the_noise_are_not_separated():
    """Назвать виновным один из двух неразличимых — это отправить человека
    крутить не тот конец машины."""
    r = SH.report(run_of(20, spread=0.4))
    assert r["stable"] is None
    assert "cannot tell them apart" in r["why"]


def test_the_per_sector_numbers_survive_even_when_the_verdict_does_not():
    """Отказ назвать виновника не повод прятать измеренное."""
    r = SH.report(run_of(3, spread=0.06))
    assert len(r["sectors"]) == 3
    assert all(s["best"] > 0 for s in r["sectors"])


# ── пит-круги и вылеты ──────────────────────────────────────────────────────

def test_a_pit_lap_does_not_become_a_one_off_loss():
    """Первая версия считала разовое по всем кругам, и на Спа выходило
    «разово потеряно 129.50с в S1» — это два заезда в боксы, а не ошибка,
    которую можно исправить."""
    laps = run_of(20, spread=0.06)
    laps[9]["sectors"][0] = 108.0                    # заезд в боксы
    laps[9]["lap_time"] = round(sum(laps[9]["sectors"]), 2)

    r = SH.report(laps)
    assert r["sectors"][0]["one_off_total"] < 5.0, "пит-стоп попал в разовое"
    assert r["skipped"] == 1, "выброшенный круг не посчитан"


def test_the_skipped_laps_are_counted_out_loud():
    """Молча выбросить круги нельзя: человек посчитает свои сам и не поймёт,
    почему у нас их меньше."""
    laps = run_of(20, spread=0.06)
    for i in (2, 5):
        laps[i]["sectors"][0] = 90.0
        laps[i]["lap_time"] = round(sum(laps[i]["sectors"]), 2)
    assert SH.report(laps)["skipped"] == 2


# ── что не записано ─────────────────────────────────────────────────────────

def test_a_lap_that_is_only_partly_recorded_says_so():
    """До 31.08.2026 в базу шли только три сектора, а на Спа их четыре: 26%
    круга не было вовсе. Промолчать — значит дать искать потерю там, где её
    не измеряли."""
    laps = [lap(i + 1, [33.6, 30.5, 25.6], recorded_all=False) for i in range(20)]
    for i, l in enumerate(laps):
        l["lap_time"] = round(l["lap_time"] + 32.3, 2)     # четвёртый сектор
    r = SH.report(laps)
    assert r["partial"] is True
    assert r["unrecorded"]["seconds"] == pytest.approx(32.3, abs=0.05)
    assert r["unrecorded"]["share"] == pytest.approx(0.26, abs=0.02)


def test_a_fully_recorded_lap_does_not_raise_the_banner():
    r = SH.report(run_of(20, spread=0.06))
    assert r["partial"] is False
    assert r["unrecorded"] is None, "предупредили о пропаже, которой нет"


# ── нарезка на заезды ───────────────────────────────────────────────────────

def test_a_long_break_starts_a_new_run():
    """Считать стабильность через две недели и другой сетап — это считать
    двух разных гонщиков за одного."""
    a = [lap(1, [33.6, 30.5, 25.6], ts="2026-08-20T12:00:00")]
    b = [lap(2, [33.6, 30.5, 25.6], ts="2026-08-20T14:00:00")]
    assert len(SH.split_runs(a + b)) == 2


def test_changing_car_starts_a_new_run():
    a = [lap(1, [33.6, 30.5, 25.6])]
    b = [lap(2, [33.6, 30.5, 25.6], car="Porsche 963")]
    assert len(SH.split_runs(a + b)) == 2


def test_a_lap_counter_going_backwards_starts_a_new_run():
    """Новая сессия на той же трассе начинается с первого круга."""
    rows = [lap(8, [33.6, 30.5, 25.6]), lap(1, [33.6, 30.5, 25.6])]
    assert len(SH.split_runs(rows)) == 2


def test_duplicates_are_dropped_but_real_laps_are_not():
    """В его базе 53 дубля из 637. Дубль вдвое занижает разброс, и правило
    становится самоуверенным. Но ключ должен быть длинным: по короткому
    лишними оказываются 114 строк, и половина из них — настоящие круги
    с разных трасс, попавшие в одну секунду."""
    same = lap(5, [33.6, 30.5, 25.6])
    other = lap(5, [33.6, 30.5, 25.6], track="monza")     # та же секунда, другая трасса
    assert len(SH.dedupe([same, dict(same), other])) == 2


# ── отказы ──────────────────────────────────────────────────────────────────

def test_a_track_without_sector_times_says_why():
    """Пустая карточка читается как поломка программы."""
    r = SH.report([{"lap_num": 1, "lap_time": 90.0, "sectors": []}])
    assert r["ok"] is False and "no lap" in r["reason"]


def test_a_single_lap_is_not_compared_to_itself():
    r = SH.report([lap(1, [33.6, 30.5, 25.6])])
    assert r["ok"] is False
    assert "only 1 clean lap" in r["reason"], r["reason"]


def test_an_out_lap_does_not_set_the_number_of_sectors():
    """У выезда из боксов первого сектора нет. Если он задаст длину набора,
    под неё не подойдёт ни один нормальный круг."""
    laps = run_of(20, spread=0.06)
    laps.append(lap(21, [30.5, 25.6]))               # круг с двумя секторами
    r = SH.report(laps)
    assert r["count"] == 3
    assert r["dropped"] == 1, "круг другой длины не посчитан выброшенным"


def test_the_latest_run_is_the_one_you_just_drove():
    old = [lap(i + 1, [33.6, 30.5, 25.6], ts="2026-08-01T10:00:00") for i in range(3)]
    new = [lap(i + 1, [33.6, 30.5, 25.6], ts="2026-08-20T12:00:00") for i in range(4)]
    assert len(SH.latest_run(old + new)) == 4


def test_the_median_is_used_rather_than_the_mean():
    """Прямая проверка выбора: один пит-круг сдвигает среднее на секунды,
    а медиану не трогает вовсе."""
    v = [30.5] * 19 + [67.5]
    assert statistics.median(v) == 30.5
    assert statistics.fmean(v) > 32


def test_the_optimal_lap_is_hidden_when_part_of_the_lap_is_missing():
    """Сумма трёх записанных секторов из четырёх — не круг. На старой Монце
    она давала 64.6 при лучшем круге 95.97: под словом «optimal» человек
    решил бы, что может проехать на тридцать секунд быстрее."""
    laps = [lap(i + 1, [33.6, 30.5, 25.6], recorded_all=False) for i in range(20)]
    for l in laps:
        l["lap_time"] = round(l["lap_time"] + 32.3, 2)
    r = SH.report(laps)
    assert r["optimal"] is None
    assert r["best_lap"] is not None, "настоящий лучший круг прятать незачем"


def test_a_fully_recorded_run_does_show_the_optimal_lap():
    r = SH.report(run_of(20, spread=0.06))
    assert r["optimal"] == pytest.approx(sum(s["best"] for s in r["sectors"]), abs=0.01)
    assert r["optimal"] <= r["best_lap"] + 0.01, "оптимальный вышел хуже настоящего"


def test_two_laps_are_not_enough_to_have_a_typical_lap():
    """На настоящем заезде в два круга выходило «типичный S1 = 116.95» при
    лучшем 10.33 — это заезд в боксы, поделённый пополам. Медиана из двух
    значений это просто среднее, и фильтр пит-кругов на двух не работает."""
    r = SH.report(run_of(2, spread=0.06))
    assert r["ok"] is False
    assert str(SH.MIN_LAPS) in r["reason"], "не сказано, сколько кругов нужно"


def test_an_optimal_lap_faster_than_the_real_best_is_suppressed():
    """Второй пояс на случай, когда невязка не поймала пропажу: сумма лучших
    секторов не может быть на проценты быстрее настоящего лучшего круга."""
    laps = [lap(i + 1, [10.0, 20.0, 24.0]) for i in range(20)]
    for l in laps:
        l["lap_time"] = 120.0                 # круг вдвое длиннее суммы секторов
    r = SH.report(laps)
    assert r["optimal"] is None
    assert r["best_lap"] == 120.0


def test_the_one_off_number_is_the_sum_of_the_laps_it_names():
    """Раньше печаталось превышение по ВСЕМ кругам сектора, а номеров стояло
    три-четыре. На Спа выходило «+6.91s на 4 кругах», а те четыре круга
    стоили 3.98s — человек шёл искать семь секунд там, где их четыре."""
    laps = run_of(30, spread=0.08)
    for i, extra in ((3, 1.2), (7, 0.9), (11, 0.7)):
        laps[i]["sectors"][0] += extra
        laps[i]["lap_time"] = round(sum(laps[i]["sectors"]), 2)

    s = SH.report(laps)["sectors"][0]
    named = sum(x["plus"] for x in s["one_off_laps"])
    assert s["one_off_named"] == pytest.approx(named, abs=0.01)
    assert s["one_off_named"] <= s["one_off_total"] + 0.01


def test_the_rest_of_the_one_off_loss_is_counted_not_hidden():
    """Молча вычесть остаток значит потерять секунды. «Размазано по двадцати
    кругам» — это и есть ответ «разового здесь нет»."""
    laps = run_of(30, spread=0.3)
    s = SH.report(laps)["sectors"][0]
    assert s["one_off_spread"] >= len(s["one_off_laps"])
    assert s["one_off_total"] >= s["one_off_named"] - 0.01


def test_a_single_bad_lap_is_named_with_its_own_number():
    laps = run_of(30, spread=0.06)
    laps[9]["sectors"][1] += 2.5
    laps[9]["lap_time"] = round(sum(laps[9]["sectors"]), 2)
    s = SH.report(laps)["sectors"][1]
    assert s["one_off_laps"][0]["lap"] == 10
    assert s["one_off_named"] == pytest.approx(s["one_off_laps"][0]["plus"]
                                               + sum(x["plus"] for x in
                                                     s["one_off_laps"][1:]), abs=0.01)


def test_a_truncated_sector_does_not_become_your_best():
    """Сектор втрое короче типичного — сбой замера, а не рекорд. Став
    «лучшим», он выдумывал секунды: на Спа заголовок объявлял «S2 стоит тебе
    17.80 секунды каждый круг», на Монце Best 3.78 при типичном 15.92."""
    laps = run_of(20, spread=0.06)
    laps[6]["sectors"][2] = 3.78
    laps[6]["lap_time"] = round(sum(laps[6]["sectors"]), 2)

    r = SH.report(laps)
    assert r["sectors"][2]["best"] > 20.0, "обрезанный замер снова стал лучшим"
    assert r["sectors"][2]["every_lap"] < 0.5, "заголовок выдумал секунды"
    assert r["truncated"] == 1


def test_a_truncated_lap_is_not_called_a_pit_stop():
    """Подписать сбой таймера как «pit or off» значит отправить человека
    вспоминать заезд в боксы, которого не было."""
    laps = run_of(20, spread=0.06)
    laps[6]["sectors"][2] = 3.78                       # сбитый замер
    laps[9]["sectors"][0] = 90.0                       # настоящий пит
    for i in (6, 9):
        laps[i]["lap_time"] = round(sum(laps[i]["sectors"]), 2)

    r = SH.report(laps)
    assert r["truncated"] == 1 and r["skipped"] == 1


def test_every_lap_of_the_run_is_accounted_for():
    """Человек считает свои круги сам. Двадцать в списке и семнадцать под
    таблицей без объяснения читаются как потеря данных."""
    laps = run_of(20, spread=0.06)
    laps[3]["sectors"][1] = 2.0                        # обрезанный
    laps[8]["sectors"][0] = 95.0                       # пит
    for i in (3, 8):
        laps[i]["lap_time"] = round(sum(laps[i]["sectors"]), 2)

    r = SH.report(laps)
    assert r["clean_laps"] + r["skipped"] + r["truncated"] == r["laps"]


def test_a_genuinely_quick_sector_is_still_your_best():
    """Нижняя граница не должна съедать настоящий быстрый круг: реальная
    езда в его данных не опускается ниже ×0.975 от типичного."""
    laps = run_of(20, spread=0.06)
    laps[4]["sectors"][0] -= 0.6                       # честно быстрее
    laps[4]["lap_time"] = round(sum(laps[4]["sectors"]), 2)

    r = SH.report(laps)
    assert r["truncated"] == 0, "быстрый круг приняли за сбой замера"
    assert r["sectors"][0]["best"] == pytest.approx(laps[4]["sectors"][0], abs=0.01)
