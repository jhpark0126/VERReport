"""Google Test XML 결과 파서 (`--gtest_output=xml:...`)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from ..model import DISABLED, FAILED, PASSED, SKIPPED, TestCase, TestRunReport
from ..paths import normalize_path


def parse_gtest(path: str | Path, name: str, root: str | None = None) -> TestRunReport:
    top = ET.parse(path).getroot()
    cases = []
    for suite in top.iter("testsuite"):
        for tc in suite.iter("testcase"):
            status, message = _status_of(tc)
            line = tc.get("line")
            cases.append(TestCase(
                suite=suite.get("name", tc.get("classname", "")),
                name=tc.get("name", ""),
                path=normalize_path(tc.get("file", ""), root),
                line=int(line) if line else None,
                status=status,
                time=float(tc.get("time") or 0),
                message=message,
            ))
    return TestRunReport(name=name, cases=cases, timestamp=top.get("timestamp"))


def _status_of(tc: ET.Element) -> tuple[str, str | None]:
    problems = tc.findall("failure") + tc.findall("error")
    if problems:
        return FAILED, "\n".join(_text_of(p) for p in problems)
    skipped = tc.find("skipped")
    if skipped is not None or tc.get("result") == "skipped":
        return SKIPPED, _text_of(skipped) if skipped is not None else None
    if tc.get("status") == "notrun" or tc.get("result") == "suppressed":
        return DISABLED, None
    return PASSED, None


def _text_of(el: ET.Element) -> str:
    # 본문(CDATA)이 메시지 속성보다 자세하다.
    return (el.text or "").strip() or el.get("message", "")
