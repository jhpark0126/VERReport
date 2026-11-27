import json
from pathlib import Path

import pytest

from verreport.parsers.coverage import parse_coverage

FIX = Path(__file__).parent / "fixtures" / "coverage"
METRICS = ("lines", "functions", "branches", "mcdc", "regions")


def llvm_file_summaries(path):
    """llvm-cov 가 직접 계산한 파일별 요약값 (검증 기준)."""
    data = json.loads(path.read_text(encoding="utf-8"))["data"][0]
    return {f["filename"].replace("/work/", ""): f["summary"] for f in data["files"]}


@pytest.fixture
def unit():
    return parse_coverage(FIX / "unit" / "coverage.json", name="unit", root="/work")


# --- 전체 export (함수 단위) ---

def test_full_export_has_function_level(unit):
    assert unit.function_level is True
    assert unit.name == "unit"


def test_files(unit):
    assert [f.path for f in unit.files] == ["src/controller.c", "src/door/door.c", "src/limiter.c"]


@pytest.mark.parametrize("suite", ["unit", "integration"])
def test_file_counters_match_llvm(suite):
    r = parse_coverage(FIX / suite / "coverage.json", name=suite, root="/work")
    expected = llvm_file_summaries(FIX / suite / "summary.json")
    for f in r.files:
        for m in METRICS:
            c = getattr(f, m)
            assert (c.covered, c.count) == (expected[f.path][m]["covered"],
                                            expected[f.path][m]["count"]), (f.path, m)


def test_totals(unit):
    t = unit.totals
    assert (t["lines"].covered, t["lines"].count) == (44, 49)
    assert (t["functions"].covered, t["functions"].count) == (3, 4)
    assert (t["branches"].covered, t["branches"].count) == (14, 16)
    assert (t["mcdc"].covered, t["mcdc"].count) == (2, 4)
    assert t["mcdc"].percent == 50.0


def test_only_product_functions(unit):
    # 테스트 코드 함수(gtest TestBody)는 빠진다
    assert [f.name for f in unit.functions] == [
        "Controller_Step", "Door_IsLocked", "Door_Unused", "Limiter_Clamp"]


def test_function_fields(unit):
    f = {fn.name: fn for fn in unit.functions}
    d = f["Door_IsLocked"]
    assert (d.path, d.module, d.start_line, d.end_line, d.calls) == (
        "src/door/door.c", "src/door", 6, 15, 2)
    assert (d.branches.covered, d.branches.count) == (2, 4)
    assert (d.mcdc.covered, d.mcdc.count) == (0, 2)
    assert (d.lines.covered, d.lines.count) == (8, 10)

    u = f["Door_Unused"]
    assert u.calls == 0
    assert (u.lines.covered, u.lines.count) == (0, 3)

    lim = f["Limiter_Clamp"]
    assert (lim.mcdc.covered, lim.mcdc.count) == (2, 2)


@pytest.mark.parametrize("suite", ["unit", "integration"])
@pytest.mark.parametrize("metric", ["lines", "branches", "mcdc", "regions"])
def test_function_counters_sum_to_file(suite, metric):
    r = parse_coverage(FIX / suite / "coverage.json", name=suite, root="/work")
    for f in r.files:
        fns = r.functions_of(f.path)
        file_c = getattr(f, metric)
        assert sum(getattr(fn, metric).count for fn in fns) == file_c.count, f.path
        assert sum(getattr(fn, metric).covered for fn in fns) == file_c.covered, f.path


def test_uncovered_functions(unit):
    assert [f.name for f in unit.uncovered_functions] == ["Door_Unused"]


def test_by_module(unit):
    groups = unit.by_module()
    assert list(groups) == ["src", "src/door"]
    assert [f.path for f in groups["src"]] == ["src/controller.c", "src/limiter.c"]


def test_module_totals(unit):
    t = unit.module_totals("src")
    assert (t["lines"].covered, t["lines"].count) == (36, 36)
    assert (t["mcdc"].covered, t["mcdc"].count) == (2, 2)


# --- summary-only export (파일 단위까지만) ---

def test_summary_only_export():
    r = parse_coverage(FIX / "unit" / "summary.json", name="unit", root="/work")
    assert r.function_level is False
    assert r.functions == []
    assert [f.path for f in r.files] == ["src/controller.c", "src/door/door.c", "src/limiter.c"]
    assert (r.totals["mcdc"].covered, r.totals["mcdc"].count) == (2, 4)


# --- Counter ---

def test_percent_of_empty_counter_is_none(unit):
    c = unit.files[0].mcdc   # controller.c: MC/DC 조건 없음
    assert c.count == 0
    assert c.percent is None


def test_not_llvm_export(tmp_path):
    p = tmp_path / "x.json"
    p.write_text('{"foo": 1}', encoding="utf-8")
    with pytest.raises(ValueError):
        parse_coverage(p, name="x")
