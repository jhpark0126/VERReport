from pathlib import Path

import pytest

from verreport.parsers.cppcheck import parse_cppcheck

FIX = Path(__file__).parent / "fixtures" / "cppcheck"


@pytest.fixture
def report():
    return parse_cppcheck(FIX / "cppcheck.xml", root="/work")


def test_reads_issue(report):
    assert report.version == "2.13.0"
    assert len(report.issues) == 1
    i = report.issues[0]
    assert (i.id, i.severity, i.cwe) == ("arrayIndexOutOfBounds", "error", 788)
    assert i.message == "Array 'buf[4]' accessed at index 4, which is out of bounds."
    # 첫 위치가 지적 위치다
    assert (i.path, i.line, i.column) == ("src/door/door.c", 13, 8)
    assert i.module == "src/door"


def test_trace_locations(report):
    locs = report.issues[0].locations
    assert [(loc.line, loc.info) for loc in locs] == [
        (13, "Array index out of bounds"),
        (9, "Assuming condition is false"),
        (8, "Assignment 'idx=4', assigned value is 4"),
    ]


def test_status(report):
    assert report.status == "fail"


MIXED = """<?xml version="1.0" encoding="UTF-8"?>
<results version="2">
  <cppcheck version="2.13.0"/>
  <errors>
    <error id="unusedVariable" severity="style" msg="Unused variable: x" verbose="v1">
      <location file="/w/src/b/b.c" line="3" column="9"/>
    </error>
    <error id="nullPointer" severity="warning" msg="Null pointer" verbose="v2" cwe="476">
      <location file="/w/src/a.c" line="10" column="1"/>
    </error>
    <error id="toomanyconfigs" severity="information" msg="Too many configs" verbose="v3"/>
    <error id="passedByValue" severity="performance" msg="Pass by ref" verbose="v4">
      <location file="/w/src/a.c" line="2" column="1"/>
    </error>
  </errors>
</results>
"""


@pytest.fixture
def mixed(tmp_path):
    p = tmp_path / "c.xml"
    p.write_text(MIXED, encoding="utf-8")
    return parse_cppcheck(p, root="/w")


def test_issue_without_location(mixed):
    i = mixed.issues[2]
    assert (i.path, i.line, i.module) == ("", None, "(none)")
    assert i.cwe is None


def test_summary_by_severity(mixed):
    assert mixed.summary() == {
        "total": 4,
        "files": 2,
        "by_severity": {"error": 0, "warning": 1, "style": 1, "performance": 1,
                        "portability": 0, "information": 1},
    }


def test_by_severity_order(mixed):
    assert list(mixed.by_severity()) == ["warning", "style", "performance", "information"]


def test_by_module_and_file(mixed):
    assert list(mixed.by_module()) == ["(none)", "src", "src/b"]
    files = mixed.by_file()
    assert list(files) == ["", "src/a.c", "src/b/b.c"]
    # 파일 안에서는 라인 순서
    assert [i.line for i in files["src/a.c"]] == [2, 10]


def test_empty_is_pass(tmp_path):
    p = tmp_path / "c.xml"
    p.write_text('<results version="2"><cppcheck version="2.13.0"/><errors></errors></results>',
                 encoding="utf-8")
    r = parse_cppcheck(p)
    assert r.issues == []
    assert r.status == "pass"
