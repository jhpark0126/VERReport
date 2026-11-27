from pathlib import Path

import pytest

from verreport.parsers.gtest import parse_gtest

FIX = Path(__file__).parent / "fixtures" / "gtest"


@pytest.fixture
def report():
    return parse_gtest(FIX / "unit_results.xml", name="unit", root="/work")


def test_reads_all_cases(report):
    assert len(report.cases) == 9
    assert report.name == "unit"
    assert report.timestamp == "2026-11-27T05:12:13.600"


def test_case_fields(report):
    c = report.cases[0]
    assert (c.suite, c.name, c.path, c.line, c.status) == (
        "DoorUnit", "LockedWhenStateOne", "test/unit/door_unit_test.cpp", 3, "passed")
    assert c.message is None


def test_failed_case_has_message(report):
    c = report.cases[1]
    assert c.status == "failed"
    assert "intended failure" in c.message
    assert c.message.startswith("/work/test/unit/door_unit_test.cpp:4")


def test_disabled_case(report):
    assert report.cases[2].status == "disabled"


def test_summary_matches_ci_gate(report):
    # ci/run_tests.sh 와 같은 식: 성공률 = 성공 / 전체(비활성 포함)
    assert report.summary() == {
        "tests": 9, "passed": 7, "failed": 1, "disabled": 1, "skipped": 0,
        "pass_rate": pytest.approx(77.777, abs=0.01),
    }
    assert report.status == "fail"


def test_failures(report):
    assert [c.name for c in report.failures] == ["UnlockedWhenStateFive"]


def test_group_by_suite(report):
    groups = report.by_suite()
    assert list(groups) == ["ControllerUnit", "DoorUnit", "LimiterUnit"]
    assert len(groups["LimiterUnit"]) == 5


def test_group_by_file(report):
    assert list(report.by_file()) == [
        "test/unit/door_unit_test.cpp", "test/unit/limiter_unit_test.cpp"]


SKIPPED_AND_ERROR = """<?xml version="1.0" encoding="UTF-8"?>
<testsuites tests="2" failures="0" disabled="0" errors="0" name="AllTests">
  <testsuite name="S" tests="2">
    <testcase name="Skip" file="/w/t.cpp" line="1" status="run" result="skipped" time="0." classname="S">
      <skipped message="not ready"/>
    </testcase>
    <testcase name="Err" file="/w/t.cpp" line="2" status="run" result="completed" time="0.5" classname="S">
      <error message="crashed"/>
    </testcase>
  </testsuite>
</testsuites>
"""


def test_skipped_and_error(tmp_path):
    p = tmp_path / "r.xml"
    p.write_text(SKIPPED_AND_ERROR, encoding="utf-8")
    r = parse_gtest(p, name="x", root="/w")
    assert [c.status for c in r.cases] == ["skipped", "failed"]
    assert r.cases[0].message == "not ready"
    assert r.cases[1].message == "crashed"
    assert r.cases[1].time == 0.5
    assert r.summary()["skipped"] == 1


def test_all_passed_is_pass(tmp_path):
    p = tmp_path / "r.xml"
    p.write_text('<testsuites tests="1"><testsuite name="S">'
                 '<testcase name="A" status="run" result="completed" time="0"/>'
                 '</testsuite></testsuites>', encoding="utf-8")
    r = parse_gtest(p, name="x")
    assert r.status == "pass"
    assert r.cases[0].path == ""


def test_no_tests_is_fail(tmp_path):
    p = tmp_path / "r.xml"
    p.write_text('<testsuites tests="0"></testsuites>', encoding="utf-8")
    r = parse_gtest(p, name="x")
    assert r.status == "fail"
    assert r.summary()["pass_rate"] is None
