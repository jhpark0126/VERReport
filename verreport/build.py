"""한 빌드의 검증 결과를 모으고 판정한다.

리포트 폴더 구조는 ClaudeClang CI(`ci/*.sh`)가 만드는 그대로다.

    <reports>/
      {tdd,unit,integration}/results.xml          Google Test
      {tdd,unit,integration}/coverage.json        llvm-cov 전체 export (없으면 summary.json)
      cppcheck.xml                                Cppcheck
      lizard.csv                                  Lizard (없으면 lizard.xml)

결과 파일이 없는 도구는 'na'(미실행)로 둔다. 오류로 보지 않는다.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .model import (FAIL, PASS, Counter, CoverageReport, CppcheckReport,
                    LizardReport, TestRunReport, group_by)
from .parsers.coverage import parse_coverage
from .parsers.cppcheck import parse_cppcheck
from .parsers.gtest import parse_gtest
from .parsers.lizard import parse_lizard
from .paths import module_of

NA = "na"       # 결과 없음
INFO = "info"   # 기록만 하고 판정하지 않음

SUITES = ("tdd", "unit", "integration")
SUITE_LABELS = {"tdd": "TDD", "unit": "단위", "integration": "통합"}
METRIC_LABELS = {"lines": "라인", "functions": "함수", "branches": "분기",
                 "mcdc": "MC/DC", "regions": "영역"}


@dataclass
class BuildInfo:
    build_id: str | None = None
    job: str | None = None
    branch: str | None = None
    commit: str | None = None
    url: str | None = None
    # 기본값은 이 컴퓨터(컨테이너)의 시간대가 붙은 현재 시각. 시간대는 TZ 환경변수를 따른다.
    build_time: datetime = field(default_factory=lambda: datetime.now().astimezone())
    generated_at: datetime = field(default_factory=lambda: datetime.now().astimezone())


@dataclass
class Criteria:
    """품질 기준. 기본값은 ClaudeClang CLAUDE.md 2장."""

    coverage_gates: dict[str, tuple[str, float]] = field(default_factory=lambda: {
        "unit": ("mcdc", 100.0),
        "integration": ("functions", 100.0),
    })
    max_ccn: int = 10
    max_length: int = 80
    product_prefixes: tuple[str, ...] = ("src/",)


@dataclass
class ToolVerdict:
    key: str
    label: str
    status: str
    headline: str
    criterion: str
    page: str


@dataclass
class ModuleRow:
    module: str
    files: int
    functions: int
    cppcheck: int
    lizard_violations: int
    coverage: dict[str, Counter]
    unmeasured: int


@dataclass
class BuildResult:
    info: BuildInfo
    criteria: Criteria
    tests: dict[str, TestRunReport] = field(default_factory=dict)
    coverage: dict[str, CoverageReport] = field(default_factory=dict)
    cppcheck: CppcheckReport | None = None
    lizard: LizardReport | None = None
    notes: list[str] = field(default_factory=list)   # 대시보드 위에 보일 안내

    # --- 시험 ---

    def test_status(self, suite: str) -> str:
        r = self.tests.get(suite)
        return r.status if r else NA

    def tests_total(self) -> dict:
        total = {"tests": 0, "passed": 0, "failed": 0, "disabled": 0, "skipped": 0}
        for r in self.tests.values():
            s = r.summary()
            for k in total:
                total[k] += s[k]
        total["pass_rate"] = 100.0 * total["passed"] / total["tests"] if total["tests"] else None
        return total

    # --- 커버리지 ---

    def coverage_gate(self, suite: str) -> tuple[str, float] | None:
        return self.criteria.coverage_gates.get(suite)

    def coverage_metric(self, suite: str) -> str:
        """묶음을 대표하는 지표: 판정 지표, 판정이 없으면 라인."""
        gate = self.coverage_gate(suite)
        return gate[0] if gate else "lines"

    def coverage_status(self, suite: str) -> str:
        r = self.coverage.get(suite)
        if r is None:
            return NA
        gate = self.coverage_gate(suite)
        if gate is None:
            return INFO
        metric, target = gate
        c = r.totals[metric]
        # 측정 대상이 없으면(0/0) 기준을 자명하게 충족한다 (CI 게이트와 같음)
        pct = c.percent if c.count else 100.0
        return PASS if pct >= target else FAIL

    def product_files(self) -> list[str]:
        if self.lizard is None:
            return []
        prefixes = self.criteria.product_prefixes
        return sorted({f.path for f in self.lizard.functions if f.path.startswith(prefixes)})

    def unmeasured_files(self, suite: str) -> list[str]:
        """Lizard가 본 제품 소스 중 이 묶음의 커버리지에 아예 없는 파일."""
        r = self.coverage.get(suite)
        if r is None:
            return []
        measured = {f.path for f in r.files}
        return [p for p in self.product_files() if p not in measured]

    def function_at(self, path: str, line: int | None):
        """path:line 을 포함하는 Lizard 함수. 끝 라인을 모르면(XML) 찾지 않는다."""
        if self.lizard is None or line is None:
            return None
        for f in self.lizard.functions:
            if f.path == path and f.end_line is not None and f.start_line <= line <= f.end_line:
                return f
        return None

    # --- 도구별 판정 ---

    def tools(self) -> list[ToolVerdict]:
        return [self._gtest_verdict(), self._coverage_verdict(),
                self._cppcheck_verdict(), self._lizard_verdict()]

    @property
    def overall_status(self) -> str:
        statuses = [t.status for t in self.tools()]
        if FAIL in statuses:
            return FAIL
        if PASS in statuses:
            return PASS
        return NA

    def _gtest_verdict(self) -> ToolVerdict:
        if not self.tests:
            status, headline = NA, "결과 없음"
        else:
            t = self.tests_total()
            status = FAIL if FAIL in (r.status for r in self.tests.values()) else PASS
            headline = f"{t['tests']}개 중 {t['passed']}개 성공"
        return ToolVerdict("gtest", "Google Test", status, headline,
                           "모든 시험 묶음의 성공률 100%", "gtest.html")

    def _coverage_verdict(self) -> ToolVerdict:
        gated = [s for s in self.coverage if self.coverage_gate(s)]
        if not self.coverage:
            status, headline = NA, "결과 없음"
        elif not gated:
            status, headline = INFO, "판정 대상 묶음 없음"
        else:
            failed = [s for s in gated if self.coverage_status(s) == FAIL]
            status = FAIL if failed else PASS
            parts = []
            for s in gated:
                metric = self.coverage_metric(s)
                pct = self.coverage[s].totals[metric].percent
                parts.append(f"{SUITE_LABELS[s]} {METRIC_LABELS[metric]} {_pct(pct)}")
            headline = ", ".join(parts)
        crit = ", ".join(f"{SUITE_LABELS[s]} {METRIC_LABELS[m]} {t:g}%"
                         for s, (m, t) in self.criteria.coverage_gates.items())
        return ToolVerdict("coverage", "커버리지 (llvm-cov)", status, headline, crit,
                           "coverage.html")

    def _cppcheck_verdict(self) -> ToolVerdict:
        if self.cppcheck is None:
            status, headline = NA, "결과 없음"
        else:
            status, headline = self.cppcheck.status, f"지적 {len(self.cppcheck.issues)}건"
        return ToolVerdict("cppcheck", "Cppcheck", status, headline, "지적 0건",
                           "cppcheck.html")

    def _lizard_verdict(self) -> ToolVerdict:
        if self.lizard is None:
            status, headline = NA, "결과 없음"
        else:
            status, headline = self.lizard.status, f"위반 함수 {len(self.lizard.violations)}개"
        c = self.criteria
        return ToolVerdict("lizard", "Lizard", status, headline,
                           f"순환복잡도 {c.max_ccn} 이하, 함수 길이 {c.max_length}라인 이하",
                           "lizard.html")

    # --- 모듈별 현황 ---

    def module_coverage_columns(self) -> list[tuple[str, str]]:
        return [(s, self.coverage_metric(s)) for s in self.coverage]

    def module_rows(self) -> list[ModuleRow]:
        files_by_module: dict[str, set[str]] = {}
        for path in self._all_paths():
            files_by_module.setdefault(module_of(path), set()).add(path)

        lizard_fns = group_by(self.lizard.functions, lambda f: f.module) if self.lizard else {}
        issues = self.cppcheck.by_module() if self.cppcheck else {}
        unmeasured = set()
        for s in self.coverage:
            if self.coverage_gate(s):
                unmeasured.update(self.unmeasured_files(s))

        rows = []
        for module in sorted(set(files_by_module) | set(issues)):
            fns = lizard_fns.get(module, [])
            cov = {}
            for suite, metric in self.module_coverage_columns():
                cov[suite] = self.coverage[suite].module_totals(module)[metric]
            rows.append(ModuleRow(
                module=module,
                files=len(files_by_module.get(module, ())),
                functions=len(fns),
                cppcheck=len(issues.get(module, [])),
                lizard_violations=sum(1 for f in fns if self.lizard.violations_of(f)),
                coverage=cov,
                unmeasured=sum(1 for p in files_by_module.get(module, ()) if p in unmeasured),
            ))
        return rows

    def _all_paths(self) -> set[str]:
        paths = set()
        if self.lizard:
            paths.update(f.path for f in self.lizard.functions)
        for r in self.coverage.values():
            paths.update(f.path for f in r.files)
        if self.cppcheck:
            paths.update(i.path for i in self.cppcheck.issues if i.path)
        return paths


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f}%"


def load_build(reports_dir: str | Path, root: str | None = None,
               info: BuildInfo | None = None, criteria: Criteria | None = None) -> BuildResult:
    d = Path(reports_dir)
    criteria = criteria or Criteria()
    result = BuildResult(info=info or BuildInfo(), criteria=criteria)

    for suite in SUITES:
        results = d / suite / "results.xml"
        if results.is_file():
            result.tests[suite] = _parse(parse_gtest, results, name=suite, root=root)
        cov = _first_existing(d / suite / "coverage.json", d / suite / "summary.json")
        if cov:
            result.coverage[suite] = _parse(parse_coverage, cov, name=suite, root=root)

    if (d / "cppcheck.xml").is_file():
        result.cppcheck = _parse(parse_cppcheck, d / "cppcheck.xml", root=root)
    liz = _first_existing(d / "lizard.csv", d / "lizard.xml")
    if liz:
        result.lizard = _parse(parse_lizard, liz, root=root, max_ccn=criteria.max_ccn,
                               max_length=criteria.max_length)
    return result


class ReportError(Exception):
    """결과 파일을 읽지 못했다 (어느 파일인지 메시지에 들어 있다)."""


def _parse(parser, path: Path, **kwargs):
    try:
        return parser(path, **kwargs)
    except (OSError, ValueError, KeyError, IndexError, TypeError, ET.ParseError) as e:
        raise ReportError(f"{path}: 결과 파일을 읽지 못했습니다 ({type(e).__name__}: {e})") from e


def _first_existing(*paths: Path) -> Path | None:
    return next((p for p in paths if p.is_file()), None)


def raw_paths(result: BuildResult) -> list[str]:
    """결과에 들어 있는 모든 소스 경로 (루트 자동 판단용)."""
    paths = list(result._all_paths())
    for r in result.tests.values():
        paths.extend(c.path for c in r.cases if c.path)
    return paths
