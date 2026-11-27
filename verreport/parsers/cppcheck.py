"""Cppcheck XML(version 2) 결과 파서 (`cppcheck --xml --xml-version=2`)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from ..model import CppcheckIssue, CppcheckReport, IssueLocation
from ..paths import normalize_path


def parse_cppcheck(path: str | Path, root: str | None = None) -> CppcheckReport:
    top = ET.parse(path).getroot()
    version_el = top.find("cppcheck")
    issues = []
    for err in top.iter("error"):
        cwe = err.get("cwe")
        issues.append(CppcheckIssue(
            id=err.get("id", ""),
            severity=err.get("severity", ""),
            message=err.get("msg", ""),
            verbose=err.get("verbose", ""),
            cwe=int(cwe) if cwe else None,
            locations=[_location(loc, root) for loc in err.iter("location")],
        ))
    return CppcheckReport(
        issues=issues,
        version=version_el.get("version") if version_el is not None else None,
    )


def _location(loc: ET.Element, root: str | None) -> IssueLocation:
    column = loc.get("column")
    return IssueLocation(
        path=normalize_path(loc.get("file", ""), root),
        line=int(loc.get("line", 0)),
        column=int(column) if column else None,
        info=loc.get("info"),
    )
