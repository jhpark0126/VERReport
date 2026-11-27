"""llvm-cov JSON export 파서.

지원 형식
- 전체 export (`llvm-cov export ...`, 권장): 파일 + 함수 단위 (라인, 분기, MC/DC, 영역)
- 요약 export (`llvm-cov export -summary-only ...`): 파일 단위까지만

파일 단위 값은 llvm-cov가 계산한 summary를 그대로 쓴다.
함수 단위 라인 커버리지는 llvm-cov에 없어서, llvm-cov가 라인을 판정하는 방식
(LineCoverageIterator / LineCoverageStats)을 그대로 옮겨 파일 세그먼트로 계산한다.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..model import Counter, CoverageReport, FileCoverage, FunctionCoverage
from ..paths import normalize_path

# 영역(region) 배열: [LineStart, ColStart, LineEnd, ColEnd, Count, FileID, ExpandedFileID, Kind]
# llvm-cov는 함수 본문 파일(FileID 0)의 코드 영역과 매크로 확장 영역을 영역 수로 센다.
_COUNTED_KINDS = (0, 1)   # CodeRegion, ExpansionRegion
# 분기(branch) 배열: [LineStart, ColStart, LineEnd, ColEnd, TrueCount, FalseCount, FileID, ExpandedFileID, Kind]
# 세그먼트 배열: [Line, Col, Count, HasCount, IsRegionEntry, IsGapRegion]


def parse_coverage(path: str | Path, name: str, root: str | None = None) -> CoverageReport:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if not str(doc.get("type", "")).startswith("llvm.coverage.json.export"):
        raise ValueError(f"llvm-cov JSON export 파일이 아닙니다: {path}")
    data = doc["data"][0]

    files = [_file_coverage(f, root) for f in data["files"]]
    function_level = "functions" in data and all("segments" in f for f in data["files"])
    functions: list[FunctionCoverage] = []
    if function_level:
        line_maps = {f["filename"]: _line_counts(f["segments"]) for f in data["files"]}
        for fn in data["functions"]:
            main_file = fn["filenames"][0]
            if main_file in line_maps:   # 소스 필터에 든 파일의 함수만 (테스트 코드 제외)
                functions.append(_function_coverage(fn, line_maps[main_file], root))
        functions.sort(key=lambda f: (f.path, f.start_line))

    files.sort(key=lambda f: f.path)
    return CoverageReport(name=name, files=files, functions=functions,
                          function_level=function_level)


def _counter(summary: dict, metric: str) -> Counter:
    s = summary.get(metric, {})
    return Counter(covered=int(s.get("covered", 0)), count=int(s.get("count", 0)))


def _file_coverage(f: dict, root: str | None) -> FileCoverage:
    s = f["summary"]
    return FileCoverage(
        path=normalize_path(f["filename"], root),
        lines=_counter(s, "lines"),
        functions=_counter(s, "functions"),
        branches=_counter(s, "branches"),
        mcdc=_counter(s, "mcdc"),
        regions=_counter(s, "regions"),
    )


def _function_coverage(fn: dict, line_counts: dict[int, int], root: str | None) -> FunctionCoverage:
    code = [r for r in fn["regions"] if r[5] == 0 and r[7] in _COUNTED_KINDS]
    start = min(r[0] for r in code)
    end = max(r[2] for r in code)

    lines = [c for ln, c in line_counts.items() if start <= ln <= end]
    branches = Counter()
    for b in fn.get("branches", []):
        if b[6] == 0:
            branches = branches + Counter(int(b[4] > 0) + int(b[5] > 0), 2)
    mcdc = Counter()
    for rec in fn.get("mcdc_records", []):
        conds = next(x for x in reversed(rec) if isinstance(x, list) and
                     all(isinstance(c, bool) for c in x))
        mcdc = mcdc + Counter(sum(conds), len(conds))

    return FunctionCoverage(
        name=fn["name"],
        path=normalize_path(fn["filenames"][0], root),
        start_line=start,
        end_line=end,
        calls=int(fn["count"]),
        lines=Counter(sum(1 for c in lines if c > 0), len(lines)),
        branches=branches,
        mcdc=mcdc,
        regions=Counter(sum(1 for r in code if r[4] > 0), len(code)),
    )


def _line_counts(segments: list[list]) -> dict[int, int]:
    """라인 번호 → 실행 횟수. 실행 대상이 아닌 라인은 빠진다 (llvm-cov 와 같은 판정)."""
    result: dict[int, int] = {}
    if not segments:
        return result
    i, n = 0, len(segments)
    line = segments[0][0]
    wrapped = None
    current: list[list] = []
    while i < n:
        if current:
            wrapped = current[-1]
        current = []
        while i < n and segments[i][0] == line:
            current.append(segments[i])
            i += 1
        mapped, count = _line_stats(current, wrapped)
        if mapped:
            result[line] = count
        line += 1
    return result


def _line_stats(line_segs: list[list], wrapped: list | None) -> tuple[bool, int]:
    def has_count(s): return bool(s[3])
    def is_entry(s): return bool(s[4])
    def is_gap(s): return bool(s[5])
    def starts_region(s): return not is_gap(s) and has_count(s) and is_entry(s)

    region_starts = sum(1 for s in line_segs if starts_region(s))
    skipped = bool(line_segs) and not has_count(line_segs[0]) and is_entry(line_segs[0])
    mapped = not skipped and ((wrapped is not None and has_count(wrapped)) or region_starts > 0)
    mapped = mapped or any(is_entry(s) and has_count(s) for s in line_segs)
    if not mapped:
        return False, 0

    count = int(wrapped[2]) if wrapped is not None else 0
    if region_starts:
        for s in line_segs:
            if starts_region(s):
                count = max(count, int(s[2]))
    return True, count
