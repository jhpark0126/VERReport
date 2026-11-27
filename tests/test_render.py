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


def test_writes_all_pages_and_stylesheet(tmp_path):
    build = load_build(REPORTS, root="/work", info=BuildInfo(**INFO))
    written = render_site(build, tmp_path)
    assert [p.name for p in written] == list(PAGES)
    assert (tmp_path / "assets" / "style.css").is_file()


PAGES = ("index.html", "gtest.html", "coverage.html", "cppcheck.html", "lizard.html")


@pytest.fixture
def site(tmp_path):
    build = load_build(REPORTS, root="/work", info=BuildInfo(**INFO))
    render_site(build, tmp_path)
    return {p: (tmp_path / p).read_text(encoding="utf-8") for p in PAGES}


@pytest.mark.parametrize("page", PAGES)
def test_jenkins_csp_safe(site, page):
    # Jenkins HTML Publisher 기본 CSP: 스크립트·인라인 스타일 금지
    html = site[page]
    assert "<script" not in html
    assert "style=" not in html
    assert "<style" not in html
    assert 'href="assets/style.css"' in html


@pytest.mark.parametrize("page", PAGES)
def test_every_page_has_build_time_and_nav(site, page):
    html = site[page]
    assert "2026-11-27 14:30:00" in html
    for p in PAGES:
        assert f'href="{p}"' in html
    assert html.count('aria-current="page"') == 1


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


# --- 상세 페이지 ---

def summaries(html):
    """<details> 펼침 상태와 제목: [(열림?, 제목 텍스트)]"""
    out = []
    for m in re.finditer(r'<details class="tree[^"]*"( open)?[^>]*>\s*<summary>(.*?)</summary>', html, re.S):
        text = re.sub(r"<[^>]+>", " ", m.group(2))
        out.append((bool(m.group(1)), " ".join(text.split())))
    return out


def test_gtest_detail(site):
    html = site["gtest.html"]
    # 실패 메시지와 위치
    assert "DoorUnit.UnlockedWhenStateFive" in html
    assert "intended failure" in html
    assert "test/unit/door_unit_test.cpp:4" in html
    # 스위트 → 시험: 실패가 있는 스위트만 펼친다
    opened = [t for o, t in summaries(html) if o]
    assert len(opened) == 1 and opened[0].startswith("DoorUnit")
    assert "DISABLED_Pending" in html and "비활성" in html


def test_coverage_detail(site):
    html = site["coverage.html"]
    s = summaries(html)
    # 단위: 기준 미달인 src/door 모듈과 door.c 파일만 펼친다. TDD(판정 없음)는 펼치지 않는다.
    opened = [t.split()[0] for o, t in s if o]
    assert opened == ["src/door", "door.c"]
    # 함수 단위 행
    assert "Door_IsLocked" in html and "Limiter_Clamp" in html
    assert "미호출" in html                    # Door_Unused
    assert "한 번도 호출되지 않은 함수 1개" in html
    assert "src/door/door_state.c" in html     # 미측정 파일


def test_coverage_detail_summary_only(tmp_path):
    d = tmp_path / "r"
    (d / "unit").mkdir(parents=True)
    (d / "unit" / "summary.json").write_bytes((REPORTS / "unit" / "summary.json").read_bytes())
    render_site(load_build(d, root="/work", info=BuildInfo(**INFO)), tmp_path / "out")
    html = (tmp_path / "out" / "coverage.html").read_text(encoding="utf-8")
    assert "파일 단위까지만" in html


def test_cppcheck_detail(site):
    html = site["cppcheck.html"]
    assert "arrayIndexOutOfBounds" in html
    assert "CWE-788" in html
    # Lizard 함수 범위로 찾은 함수
    assert re.search(r'<td class="mono">Door_IsLocked</td>', html)
    assert "추적 경로 3단계" in html
    assert "Assuming condition is false" in html


def test_lizard_detail(site):
    html = site["lizard.html"]
    assert "기준 위반 함수 1개" in html
    assert "src/door/door_state.c:1" in html
    assert "복잡도 초과" in html and "길이 초과" in html
    opened = [t.split()[0] for o, t in summaries(html) if o]
    assert opened == ["src/door", "door_state.c"]


@pytest.mark.parametrize("page", PAGES[1:])
def test_detail_pages_without_results(tmp_path, page):
    render_site(load_build(tmp_path / "none", info=BuildInfo(**INFO)), tmp_path / "out")
    html = (tmp_path / "out" / page).read_text(encoding="utf-8")
    assert "결과 파일이 없습니다" in html


def test_same_input_same_output(tmp_path):
    outs = []
    for i in range(2):
        build = load_build(REPORTS, root="/work", info=BuildInfo(**INFO))
        render_site(build, tmp_path / str(i))
        outs.append([(tmp_path / str(i) / p).read_text(encoding="utf-8") for p in PAGES])
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


# --- 시각 표시 ---

def test_fmt_dt_shows_timezone():
    from datetime import timedelta, timezone

    from verreport.render import fmt_dt
    t = datetime(2026, 11, 27, 15, 13, 16)
    assert fmt_dt(t) == "2026-11-27 15:13:16"                       # 시간대 모름
    assert fmt_dt(t.replace(tzinfo=timezone(timedelta(hours=9)))) == "2026-11-27 15:13:16 (UTC+09:00)"
    assert fmt_dt(t.replace(tzinfo=timezone.utc)) == "2026-11-27 15:13:16 (UTC)"
    assert fmt_dt(t.replace(tzinfo=timezone(timedelta(hours=-3, minutes=-30)))) == "2026-11-27 15:13:16 (UTC-03:30)"
    assert fmt_dt(None) == "-"
