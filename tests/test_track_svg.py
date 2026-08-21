from ire.collector.track_svg import build_points, _flatten


def test_build_points_from_bezier_svg():
    svg = ('<svg><path class="track-surface" '
           'd="M0,0 C40,0 40,40 0,40 C-40,40 -40,0 0,0"/></svg>')
    pts = build_points(svg, baseline=0.0, clockwise=True, n=120)
    assert pts and len(pts) == 120
    assert all(0 <= p["x"] <= 100 and 0 <= p["y"] <= 100 for p in pts)
    assert pts[0]["pct"] <= pts[-1]["pct"]              # монотонно по pct (для привязки машин)


def test_ignores_d_inside_id_attribute():
    # регэксп не должен цепляться за «d» внутри id="..." (был баг)
    svg = ('<svg><g id="Full_Course_-_Config"></g>'
           '<path d="M0,0 L60,0 L60,60 L0,60 Z"/></svg>')
    pts = build_points(svg)
    assert pts and len(pts) >= 50
    xs = [p["x"] for p in pts]
    assert max(xs) - min(xs) > 50                       # это реальный квадрат, а не «мусор»


def test_flatten_handles_relative_and_absolute():
    pts = _flatten("M0,0 l10,0 l0,10 L0,10 z")
    assert len(pts) >= 4
    assert pts[0] == (0.0, 0.0)


def test_baseline_rotates_start_point():
    svg = '<svg><path d="M0,0 L100,0 L100,100 L0,100 Z"/></svg>'
    a = build_points(svg, baseline=0.0, n=80)
    b = build_points(svg, baseline=0.5, n=80)
    # старт (первая точка, pct≈0) при другом baseline — в другом месте геометрии
    assert (a[0]["x"], a[0]["y"]) != (b[0]["x"], b[0]["y"])
