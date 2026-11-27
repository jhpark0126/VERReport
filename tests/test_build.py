from datetime import datetime
from pathlib import Path

import pytest

from verreport.build import BuildInfo, load_build

REPORTS = Path(__file__).parent / "fixtures" / "reports"


@pytest.fixture
def build():
    info = BuildInfo(build_id="42", branch="feature/x", commit="abc1234",
                     build_time=datetime(2026, 11, 27, 14, 30))
    return load_build(REPORTS, root="/work", info=info)


# --- 불러오기 ---

def test_loads_all_suites(build):
    assert list(build.tests) == ["tdd", "unit", "integration"]
    assert list(build.coverage) == ["tdd", "unit", "integration"]
    assert build.cppcheck is not None
    assert build.lizard is not None


def test_prefers_full_coverage_export_and_lizard_csv(build):
    assert build.coverage["unit"].function_level is True
    assert build.lizard.length_available is True


def test_falls_back_to_summary_and_xml(tmp_path):
    (tmp_path / "unit").mkdir()
    (tmp_path / "unit" / "summary.json").write_bytes((REPORTS / "unit" / "summary.json").read_bytes())
    (tmp_path / "lizard.xml").write_bytes((REPORTS / "lizard.xml").read_bytes())
    b = load_build(tmp_path, root="/work")
    assert b.coverage["unit"].function_level is False
    assert b.lizard.length_available is False


def test_missing_results_are_not_available(tmp_path):
    b = load_build(tmp_path)
    assert b.tests == {} and b.coverage == {}
    assert b.cppcheck is None and b.lizard is None
    assert b.overall_status == "na"
    assert all(t.status == "na" for t in b.tools())


def test_build_info_defaults_to_now():
    before = datetime.now().astimezone()
    info = BuildInfo()
    assert info.build_time >= before
    assert info.generated_at >= before


# --- 판정 ---

def test_test_status_per_suite(build):
    assert {k: build.test_status(k) for k in build.tests} == {
        "tdd": "pass", "unit": "fail", "integration": "pass"}


def test_coverage_gates(build):
    # 단위: MC/DC 100%, 통합: 함수 100%, TDD: 판정 없음
    assert build.coverage_gate("unit") == ("mcdc", 100.0)
    assert build.coverage_gate("integration") == ("functions", 100.0)
    assert build.coverage_gate("tdd") is None
    assert build.coverage_status("unit") == "fail"         # MC/DC 2/4
    assert build.coverage_status("integration") == "pass"  # 함수 2/2
    assert build.coverage_status("tdd") == "info"


def test_tool_verdicts(build):
    tools = {t.key: t for t in build.tools()}
    assert list(tools) == ["gtest", "coverage", "cppcheck", "lizard"]
    assert tools["gtest"].status == "fail"
    assert tools["coverage"].status == "fail"
    assert tools["cppcheck"].status == "fail"
    assert tools["lizard"].status == "fail"
    assert build.overall_status == "fail"


def test_tool_headlines(build):
    tools = {t.key: t for t in build.tools()}
    assert tools["gtest"].headline == "11개 중 9개 성공"
    assert tools["cppcheck"].headline == "지적 1건"
    assert tools["lizard"].headline == "위반 함수 1개"


def test_all_pass_overall(tmp_path):
    (tmp_path / "unit").mkdir()
    (tmp_path / "unit" / "results.xml").write_text(
        '<testsuites><testsuite name="S"><testcase name="A" status="run" result="completed"/>'
        '</testsuite></testsuites>', encoding="utf-8")
    (tmp_path / "cppcheck.xml").write_text(
        '<results version="2"><errors/></results>', encoding="utf-8")
    b = load_build(tmp_path)
    # 커버리지·Lizard 결과는 없으므로 N/A, 나머지가 모두 통과면 전체 통과
    assert [t.status for t in b.tools()] == ["pass", "na", "pass", "na"]
    assert b.overall_status == "pass"


# --- 미측정 파일 (커버리지에 아예 없는 제품 소스) ---

def test_unmeasured_files(build):
    # door_state.c 는 어떤 시험도 호출하지 않아 링크되지 않았다
    assert build.unmeasured_files("unit") == ["src/door/door_state.c"]
    assert build.unmeasured_files("integration") == [
        "src/door/door.c", "src/door/door_state.c"]
    assert build.unmeasured_files("tdd") == [
        "src/controller.c", "src/door/door.c", "src/door/door_state.c"]


def test_unmeasured_needs_lizard(tmp_path):
    (tmp_path / "unit").mkdir()
    (tmp_path / "unit" / "coverage.json").write_bytes((REPORTS / "unit" / "coverage.json").read_bytes())
    b = load_build(tmp_path, root="/work")
    assert b.unmeasured_files("unit") == []


# --- 라인 → 함수 찾기 (Cppcheck 지적을 함수 단위로 묶을 때) ---

def test_function_at(build):
    issue = build.cppcheck.issues[0]          # src/door/door.c:13
    assert build.function_at(issue.path, issue.line).name == "Door_IsLocked"
    assert build.function_at("src/door/door.c", 16) is None   # 두 함수 사이 빈 줄
    assert build.function_at("src/door/door.c", 17).name == "Door_Unused"
    assert build.function_at("src/none.c", 1) is None


def test_function_at_without_end_line(tmp_path):
    # Lizard XML에는 끝 라인이 없어 함수를 찾지 않는다
    (tmp_path / "lizard.xml").write_bytes((REPORTS / "lizard.xml").read_bytes())
    b = load_build(tmp_path, root="/work")
    assert b.function_at("src/door/door.c", 13) is None


# --- 모듈별 현황 ---

def test_module_rows(build):
    rows = {r.module: r for r in build.module_rows()}
    assert list(rows) == ["src", "src/door", "test/integration", "test/tdd", "test/unit"]
    door = rows["src/door"]
    assert door.files == 2
    assert door.functions == 3
    assert door.cppcheck == 1
    assert door.lizard_violations == 1
    assert (door.coverage["unit"].covered, door.coverage["unit"].count) == (0, 2)  # MC/DC
    assert (door.coverage["integration"].covered, door.coverage["integration"].count) == (0, 0)
    assert door.unmeasured == 2   # 통합 기준 door.c, door_state.c


def test_module_columns(build):
    assert build.module_coverage_columns() == [
        ("tdd", "lines"), ("unit", "mcdc"), ("integration", "functions")]
