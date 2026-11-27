import re

from verreport.charts import Part, hbar_chart, meter, segmented_bar


def widths(svg):
    return [float(w) for w in re.findall(r'<rect class="s-\w+" x="[^"]+" y="0" width="([^"]+)"', svg)]


def test_segmented_bar_proportions_with_gaps():
    svg = segmented_bar([Part("성공", 3, "s-pass"), Part("실패", 1, "s-fail")], "결과", width=202)
    w = widths(svg)
    assert len(w) == 2
    assert abs(w[0] - 150) < 0.01 and abs(w[1] - 50) < 0.01   # 202 - 2px 간격
    assert "<title>성공 3</title>" in svg


def test_segmented_bar_skips_zero_parts():
    svg = segmented_bar([Part("성공", 2, "s-pass"), Part("실패", 0, "s-fail")], "x", width=100)
    assert widths(svg) == [100.0]


def test_segmented_bar_empty_draws_track():
    svg = segmented_bar([Part("성공", 0, "s-pass")], "x")
    assert 'class="track"' in svg


def test_meter_fill_and_target_tick():
    svg = meter(50.0, "라인 50%", target=100.0, width=100)
    assert 'width="50"' in svg
    assert 'class="tick"' in svg


def test_meter_none_has_only_track():
    svg = meter(None, "측정 대상 없음")
    assert 'class="fill-accent"' not in svg


def test_hbar_chart_threshold_and_escaping():
    svg = hbar_chart([Part("a<b>", 13, "s-fail"), Part("ok", 3, "s-neutral")],
                     "복잡도", threshold=10, threshold_label="기준 10")
    assert "a&lt;b&gt;" in svg
    assert 'class="threshold"' in svg
    assert "기준 10" in svg
    assert svg.count("<path") == 2


def test_hbar_zero_value_has_no_bar():
    svg = hbar_chart([Part("none", 0, "s-accent")], "x")
    assert "<path" not in svg


def test_no_inline_style_or_script():
    # Jenkins CSP: style 속성과 스크립트를 쓰지 않는다
    for svg in (segmented_bar([Part("a", 1, "s-pass")], "x"), meter(10, "x", 50),
                hbar_chart([Part("a", 1, "s-pass")], "x", 1, "t")):
        assert "style=" not in svg and "<script" not in svg
