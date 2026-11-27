from pathlib import Path

import pytest

from verreport.parsers.lizard import parse_lizard

FIX = Path(__file__).parent / "fixtures" / "lizard"


# --- CSV (함수 길이 포함) ---

@pytest.fixture
def csv_report():
    return parse_lizard(FIX / "sample.csv", root="/work")


def test_csv_reads_all_functions(csv_report):
    assert [f.name for f in csv_report.functions] == [
        "complex_fn", "ok_fn", "long_fn", "both_fn", "helper"]


def test_csv_function_fields(csv_report):
    f = csv_report.functions[0]
    assert f.path == "src/door/bad.c"
    assert f.module == "src/door"
    assert f.long_name == "complex_fn( int a)"
    assert (f.start_line, f.end_line) == (1, 14)
    assert (f.nloc, f.ccn, f.length, f.params, f.tokens) == (12, 11, 14, 1, 80)


def test_csv_has_length(csv_report):
    assert csv_report.length_available is True


def test_violation_kinds(csv_report):
    kinds = {f.name: csv_report.violations_of(f) for f in csv_report.functions}
    assert kinds == {
        "complex_fn": ["ccn"],
        "ok_fn": [],
        "long_fn": ["length"],
        "both_fn": ["ccn", "length"],
        "helper": [],
    }


def test_threshold_is_exclusive():
    # 기준값과 같으면 위반이 아니다 (10 이하, 80 이하 허용)
    r = parse_lizard(FIX / "sample.csv", root="/work", max_ccn=11, max_length=95)
    assert r.violations_of(r.functions[0]) == []   # ccn 11
    assert r.violations_of(r.functions[2]) == []   # length 95


def test_violations_list(csv_report):
    assert [f.name for f in csv_report.violations] == ["complex_fn", "long_fn", "both_fn"]


def test_summary(csv_report):
    assert csv_report.summary() == {
        "functions": 5,
        "files": 3,
        "violations": 3,
        "ccn_violations": 2,
        "length_violations": 2,
        "max_ccn": 15,
        "max_length": 120,
    }


def test_status(csv_report):
    assert csv_report.status == "fail"
    clean = parse_lizard(FIX / "sample.csv", max_ccn=100, max_length=1000)
    assert clean.status == "pass"


def test_group_by_module(csv_report):
    groups = csv_report.by_module()
    assert list(groups) == ["(root)", "src/door", "src/lock"]
    assert [f.name for f in groups["src/lock"]] == ["long_fn", "both_fn"]


def test_group_by_file(csv_report):
    groups = csv_report.by_file()
    assert list(groups) == ["main.c", "src/door/bad.c", "src/lock/lock.c"]


# --- XML (함수 길이 없음) ---

@pytest.fixture
def xml_report():
    return parse_lizard(FIX / "sample.xml", root="/work")


def test_xml_reads_functions(xml_report):
    f = xml_report.functions[0]
    assert (f.name, f.path, f.start_line, f.nloc, f.ccn) == (
        "complex_fn", "src/door/bad.c", 1, 12, 11)
    assert f.length is None
    assert [g.name for g in xml_report.functions] == ["complex_fn", "ok_fn"]


def test_xml_has_no_length(xml_report):
    assert xml_report.length_available is False
    assert xml_report.summary()["length_violations"] is None
    assert xml_report.summary()["max_length"] is None


def test_xml_ccn_violation_still_judged(xml_report):
    assert [f.name for f in xml_report.violations] == ["complex_fn"]


# --- 오류 ---

def test_unknown_extension(tmp_path):
    p = tmp_path / "x.txt"
    p.write_text("")
    with pytest.raises(ValueError):
        parse_lizard(p)


def test_empty_csv_means_no_functions(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text("")
    r = parse_lizard(p)
    assert r.functions == []
    assert r.status == "pass"
