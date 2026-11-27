"""Lizard 결과 파서.

지원 형식
- CSV (`lizard --csv`, 권장): 헤더 없음. 열 순서는
  NLOC, CCN, token, PARAM, length, location, file, function, long_name, start, end
- XML (`lizard --xml`, cppncss 형식): 함수 길이가 없어 길이 기준은 판정하지 않는다.
"""

from __future__ import annotations

import csv
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from ..model import FunctionMetric, LizardReport
from ..paths import normalize_path

# "complex_fn(...) at /work/src/bad.c:1"
_XML_ITEM = re.compile(r"^(?P<name>.+?)\(.*\) at (?P<file>.+):(?P<line>\d+)$")


def parse_lizard(path: str | Path, root: str | None = None,
                 max_ccn: int = 10, max_length: int = 80) -> LizardReport:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        functions, has_length = _parse_csv(path, root), True
    elif suffix == ".xml":
        functions, has_length = _parse_xml(path, root), False
    else:
        raise ValueError(f"Lizard 결과 형식을 알 수 없습니다 (.csv 또는 .xml): {path}")
    return LizardReport(functions=functions, max_ccn=max_ccn,
                        max_length=max_length, length_available=has_length)


def _parse_csv(path: Path, root: str | None) -> list[FunctionMetric]:
    functions = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.reader(fh):
            if len(row) < 11:
                continue
            nloc, ccn, token, param, length, _loc, file, name, long_name, start, end = row[:11]
            functions.append(FunctionMetric(
                name=name,
                long_name=long_name,
                path=normalize_path(file, root),
                start_line=int(start),
                end_line=int(end),
                nloc=int(nloc),
                ccn=int(ccn),
                length=int(length),
                params=int(param),
                tokens=int(token),
            ))
    return functions


def _parse_xml(path: Path, root: str | None) -> list[FunctionMetric]:
    tree = ET.parse(path)
    functions = []
    for measure in tree.getroot().iter("measure"):
        if measure.get("type") != "Function":
            continue
        labels = [lb.text for lb in measure.iter("label")]
        for item in measure.iter("item"):
            m = _XML_ITEM.match(item.get("name", ""))
            if not m:
                continue
            values = dict(zip(labels, (v.text for v in item.iter("value"))))
            functions.append(FunctionMetric(
                name=m["name"],
                long_name=m["name"],
                path=normalize_path(m["file"], root),
                start_line=int(m["line"]),
                end_line=None,
                nloc=int(values.get("NCSS", 0)),
                ccn=int(values.get("CCN", 0)),
                length=None,
            ))
    return functions
