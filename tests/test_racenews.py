"""Лента новостей про гонки.

Правило Ярослава дословно: «нужно что-то прям популярное и известное.
Не всякое ралли, где победили лося в какой-то Норвегии, и никто об этом
не знает — плохой опыт уже был».

Поэтому проверяется в первую очередь ФИЛЬТР, а не разбор XML: лента без
фильтра — это лента, которую перестанут открывать на второй день.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ire.collector import racenews as N                          # noqa: E402


# ── что попадает в ленту ────────────────────────────────────────────────────

def test_big_racing_gets_in():
    for t in ("Norris extends McLaren deal until F1 2030",
              "Ferrari to deliver upgraded F1 engine at Italian GP",
              "Cadillac tops the Petit Le Mans practice",
              "IndyCar announces the 2027 calendar",
              "Porsche confirms its Hypercar line-up for Le Mans"):
        assert N.interesting(t), t


def test_sim_racing_and_hardware_get_in():
    for t in ("All iRacing content will be available in career mode",
              "MOZA announces a new direct drive wheelbase",
              "Le Mans Ultimate adds the Nordschleife",
              "Fanatec cuts prices across the range"):
        assert N.interesting(t), t


def test_the_moose_in_norway_stays_out():
    """Тот самый пример, который Ярослав привёл словами."""
    for t in ("Rally win in Norway for local privateer",
              "Regional karting championship decided on countback",
              "Hillclimb record falls at a club event",
              "Local drift series announces round four"):
        assert not N.interesting(t), t


def test_a_small_event_mentioning_something_big_still_counts():
    """«Победитель ралли протестировал машину Формулы 1» — это уже новость."""
    assert N.interesting("Rally winner tests a Formula 1 car at Fiorano")


def test_the_summary_counts_too_not_just_the_headline():
    assert N.interesting("Silly season heats up",
                         "Mercedes is expected to confirm its line-up")


# ── разбор лент ─────────────────────────────────────────────────────────────

RSS = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Norris extends McLaren deal</title>
 <link>https://x/1</link><description>&lt;p&gt;Long &lt;b&gt;text&lt;/b&gt;&lt;/p&gt;</description>
 <pubDate>Sun, 31 Aug 2026 10:00:00 GMT</pubDate></item>
<item><title>Rally in Norway</title><link>https://x/2</link></item>
</channel></rss>"""

ATOM = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>iRacing adds a new track</title>
 <link href="https://y/1"/><summary>Some &lt;i&gt;markup&lt;/i&gt; here</summary>
 <updated>2026-08-31T10:00:00Z</updated></entry></feed>"""


def test_rss_is_parsed_and_html_is_stripped():
    rows = N.parse_feed(RSS, "Test", "F1")
    assert len(rows) == 2
    assert rows[0]["title"] == "Norris extends McLaren deal"
    assert rows[0]["link"] == "https://x/1"
    assert "<b>" not in rows[0]["summary"] and "Long text" in rows[0]["summary"]
    assert rows[0]["section"] == "F1" and rows[0]["source"] == "Test"


def test_atom_is_parsed_too():
    """Половина сайтов отдаёт Atom, а не RSS. Читать надо оба."""
    rows = N.parse_feed(ATOM, "Test", "Sim racing")
    assert len(rows) == 1
    assert rows[0]["title"] == "iRacing adds a new track"
    assert rows[0]["link"] == "https://y/1"
    assert "markup" in rows[0]["summary"] and "<i>" not in rows[0]["summary"]


def test_broken_xml_is_an_empty_list_not_a_crash():
    """Источник может отдать страницу-заглушку вместо ленты — так делает
    OverTake. Валиться из-за этого нельзя."""
    assert N.parse_feed("<html>not a feed") == []
    assert N.parse_feed("") == []


def test_a_dead_source_does_not_take_the_feed_down(tmp_path, monkeypatch):
    monkeypatch.setattr(N, "_dir", lambda: tmp_path)
    monkeypatch.setattr(N, "fetch", lambda url, timeout=0:
                        RSS if "good" in url else "<html>nope")
    rows = N.load(force=True, feeds=[("A", "http://good", "F1"),
                                     ("B", "http://dead", "F1")])
    assert len(rows) == 1 and rows[0]["source"] == "A"


def test_the_same_story_from_two_sources_appears_once(tmp_path, monkeypatch):
    """Одну новость перепечатывают все — лента из дублей не читается."""
    monkeypatch.setattr(N, "_dir", lambda: tmp_path)
    monkeypatch.setattr(N, "fetch", lambda url, timeout=0: RSS)
    rows = N.load(force=True, feeds=[("A", "http://a", "F1"),
                                     ("B", "http://b", "F1")])
    assert len(rows) == 1


def test_no_internet_falls_back_to_yesterday(tmp_path, monkeypatch):
    """У Ярослава всё идёт через VPN, и туннель отваливается. Вчерашние
    новости лучше пустого экрана."""
    monkeypatch.setattr(N, "_dir", lambda: tmp_path)
    monkeypatch.setattr(N, "fetch", lambda url, timeout=0: RSS)
    first = N.load(force=True, feeds=[("A", "http://a", "F1")])
    assert first

    monkeypatch.setattr(N, "fetch", lambda url, timeout=0: "")   # сети нет
    again = N.load(force=True, feeds=[("A", "http://a", "F1")])
    assert again == first
