import re
from datetime import datetime
from pathlib import Path

import pytest

from verreport.build import BuildInfo, load_build
from verreport.render import render_site

REPORTS = Path(__file__).parent / "fixtures" / "reports"
INFO = dict(build_id="42", job="ClaudeClang", branch="feature/door", commit="61d3f6b2a9c0ffee",
            build_time=datetime(2026, 11, 27, 14, 30, 0),
            generated_at=datetime(2026, 11, 27, 14, 35, 0))


@pytest.fixture
def html(tmp_path):
    build = load_build(REPORTS, root="/work", info=BuildInfo(**INFO))
    render_site(build, tmp_path)
    return (tmp_path / "index.html").read_text(encoding="utf-8")


def test_writes_index_and_stylesheet(tmp_path):
    build = load_build(REPORTS, root="/work", info=BuildInfo(**INFO))
    written = render_site(build, tmp_path)
    assert tmp_path / "index.html" in written
    assert (tmp_path / "assets" / "style.css").is_file()


def test_jenkins_csp_safe(html):
    # Jenkins HTML Publisher 기본 CSP: 스크립트·인라인 스타일 금지
    assert "<script" not in html
    assert "style=" not in html
    assert "<style" not in html
    assert 'href="assets/style.css"' in html


def test_build_metadata(html):
    assert "2026-11-27 14:30:00" in html     # 빌드 일시
    assert "2026-11-27 14:35:00" in html     # 리포트 생성
    assert "#42" in html and "feature/door" in html
    assert "61d3f6b2a9" in html and "61d3f6b2a9c" not in html   # 커밋은 10자리


def test_overall_verdict(html):
    assert "4개 도구 중 4개가 기준 미달" in html
    assert 'class="verdict verdict-fail"' in html


def test_has_charts_tables_and_detail_buttons(html):
    assert html.count('class="segbar"') == 3          # 시험 묶음별 분포
    assert html.count('class="meter"') == 12          # 커버리지 3묶음 x 4지표
    assert html.count('class="hbar"') == 3            # Cppcheck 1 + Lizard 2
    assert html.count("<table") >= 4
    for page in ("gtest.html", "coverage.html", "cppcheck.html", "lizard.html"):
        assert f'class="btn" href="{page}"' in html


def test_tool_results(html):
    assert "11개 중 9개 성공" in html
    assert "단위 MC/DC 50.0% · 통합 함수 100.0%" in html
    assert "지적 1건" in html
    assert "위반 함수 1개" in html


def test_unmeasured_warning(html):
    assert "TDD 3개 · 단위 1개 · 통합 2개" in html
    assert "src/door/door_state.c" in html


def test_test_macro_labels(html):
    # 막대 라벨은 폭에 맞춰 줄이고, 전체 위치는 <title>(마우스 오버)에 둔다
    assert "TEST @limiter_unit_test" in html
    assert "TEST (test/unit/limiter_unit_test.cpp:" in html


def test_module_table(html):
    rows = re.findall(r'<th scope="row" class="mono">([^<]+)</th>', html)
    assert rows == ["src", "src/door", "test/integration", "test/tdd", "test/unit"]


def test_same_input_same_output(tmp_path):
    outs = []
    for i in range(2):
        build = load_build(REPORTS, root="/work", info=BuildInfo(**INFO))
        render_site(build, tmp_path / str(i))
        outs.append((tmp_path / str(i) / "index.html").read_text(encoding="utf-8"))
    assert outs[0] == outs[1]


def test_empty_reports(tmp_path):
    build = load_build(tmp_path / "none", info=BuildInfo(**INFO))
    render_site(build, tmp_path / "out")
    html = (tmp_path / "out" / "index.html").read_text(encoding="utf-8")
    assert "판정할 결과가 없습니다" in html
    assert 'class="btn"' not in html                 # 결과가 없으면 상세 버튼 비활성
    assert html.count("결과 파일이 없습니다") == 4


def test_lizard_xml_without_length(tmp_path):
    d = tmp_path / "r"
    d.mkdir()
    (d / "lizard.xml").write_bytes((REPORTS / "lizard.xml").read_bytes())
    render_site(load_build(d, root="/work", info=BuildInfo(**INFO)), tmp_path / "out")
    html = (tmp_path / "out" / "index.html").read_text(encoding="utf-8")
    assert "판정 불가" in html
    assert "lizard --csv" in html
