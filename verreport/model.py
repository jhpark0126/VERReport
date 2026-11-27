"""도구별 결과를 담는 공통 데이터 모델.

모든 결과는 모듈 → 파일 → 함수 계층으로 묶을 수 있게 path(상대 경로)를 가진다.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Iterable, TypeVar

from .paths import module_of

T = TypeVar("T")

PASS = "pass"
FAIL = "fail"


def group_by(items: Iterable[T], key: Callable[[T], str]) -> dict[str, list[T]]:
    """키 이름순으로 정렬된 묶음을 만든다 (묶음 안의 순서는 입력 순서 유지)."""
    groups: dict[str, list[T]] = defaultdict(list)
    for item in items:
        groups[key(item)].append(item)
    return dict(sorted(groups.items()))


# --- Lizard ---

@dataclass
class FunctionMetric:
    """함수 하나의 Lizard 측정값. length는 XML 입력이면 알 수 없어 None."""

    name: str
    long_name: str
    path: str
    start_line: int
    end_line: int | None
    nloc: int
    ccn: int
    length: int | None
    params: int | None = None
    tokens: int | None = None

    @property
    def module(self) -> str:
        return module_of(self.path)


@dataclass
class LizardReport:
    functions: list[FunctionMetric] = field(default_factory=list)
    max_ccn: int = 10
    max_length: int = 80
    length_available: bool = True

    def violations_of(self, fn: FunctionMetric) -> list[str]:
        """기준 초과 항목: 'ccn'(순환복잡도), 'length'(함수 길이). 기준값과 같으면 통과."""
        kinds = []
        if fn.ccn > self.max_ccn:
            kinds.append("ccn")
        if fn.length is not None and fn.length > self.max_length:
            kinds.append("length")
        return kinds

    @property
    def violations(self) -> list[FunctionMetric]:
        return [f for f in self.functions if self.violations_of(f)]

    @property
    def status(self) -> str:
        return FAIL if self.violations else PASS

    def summary(self) -> dict:
        fns = self.functions
        lengths = [f.length for f in fns if f.length is not None]
        return {
            "functions": len(fns),
            "files": len({f.path for f in fns}),
            "violations": len(self.violations),
            "ccn_violations": sum(1 for f in fns if f.ccn > self.max_ccn),
            "length_violations": (
                sum(1 for n in lengths if n > self.max_length)
                if self.length_available else None
            ),
            "max_ccn": max((f.ccn for f in fns), default=0),
            "max_length": max(lengths, default=0) if self.length_available else None,
        }

    def by_module(self) -> dict[str, list[FunctionMetric]]:
        return group_by(self.functions, lambda f: f.module)

    def by_file(self) -> dict[str, list[FunctionMetric]]:
        return group_by(self.functions, lambda f: f.path)


# --- Google Test ---

PASSED, FAILED, DISABLED, SKIPPED = "passed", "failed", "disabled", "skipped"


@dataclass
class TestCase:
    suite: str
    name: str
    path: str
    line: int | None
    status: str
    time: float = 0.0
    message: str | None = None

    __test__ = False  # pytest가 시험 클래스로 오인하지 않게 한다

    @property
    def module(self) -> str:
        return module_of(self.path)


@dataclass
class TestRunReport:
    """시험 묶음 하나(tdd/unit/integration)의 gtest 실행 결과."""

    name: str
    cases: list[TestCase] = field(default_factory=list)
    timestamp: str | None = None

    __test__ = False

    def _count(self, status: str) -> int:
        return sum(1 for c in self.cases if c.status == status)

    def summary(self) -> dict:
        total = len(self.cases)
        passed = self._count(PASSED)
        return {
            "tests": total,
            "passed": passed,
            "failed": self._count(FAILED),
            "disabled": self._count(DISABLED),
            "skipped": self._count(SKIPPED),
            # ci/run_tests.sh 와 같은 식: 비활성·건너뜀도 분모에 넣는다
            "pass_rate": 100.0 * passed / total if total else None,
        }

    @property
    def status(self) -> str:
        """CI 게이트와 같게, 모든 시험이 성공해야만 통과다 (0개도 실패)."""
        total = len(self.cases)
        return PASS if total and self._count(PASSED) == total else FAIL

    @property
    def failures(self) -> list[TestCase]:
        return [c for c in self.cases if c.status == FAILED]

    def by_suite(self) -> dict[str, list[TestCase]]:
        return group_by(self.cases, lambda c: c.suite)

    def by_file(self) -> dict[str, list[TestCase]]:
        return group_by(self.cases, lambda c: c.path)


# --- Cppcheck ---

# 심각도 표시 순서 (위험한 것부터)
SEVERITIES = ("error", "warning", "style", "performance", "portability", "information")
NO_FILE_MODULE = "(none)"


@dataclass
class IssueLocation:
    path: str
    line: int
    column: int | None = None
    info: str | None = None


@dataclass
class CppcheckIssue:
    id: str
    severity: str
    message: str
    verbose: str
    cwe: int | None
    locations: list[IssueLocation] = field(default_factory=list)

    @property
    def path(self) -> str:
        return self.locations[0].path if self.locations else ""

    @property
    def line(self) -> int | None:
        return self.locations[0].line if self.locations else None

    @property
    def column(self) -> int | None:
        return self.locations[0].column if self.locations else None

    @property
    def module(self) -> str:
        return module_of(self.path) if self.path else NO_FILE_MODULE


def _severity_rank(severity: str) -> int:
    return SEVERITIES.index(severity) if severity in SEVERITIES else len(SEVERITIES)


@dataclass
class CppcheckReport:
    issues: list[CppcheckIssue] = field(default_factory=list)
    version: str | None = None

    @property
    def status(self) -> str:
        return FAIL if self.issues else PASS

    def summary(self) -> dict:
        by_sev = {s: 0 for s in SEVERITIES}
        for i in self.issues:
            by_sev[i.severity] = by_sev.get(i.severity, 0) + 1
        return {
            "total": len(self.issues),
            "files": len({i.path for i in self.issues if i.path}),
            "by_severity": by_sev,
        }

    def by_severity(self) -> dict[str, list[CppcheckIssue]]:
        groups = group_by(self.issues, lambda i: i.severity)
        return dict(sorted(groups.items(), key=lambda kv: _severity_rank(kv[0])))

    def by_module(self) -> dict[str, list[CppcheckIssue]]:
        return group_by(self._sorted(), lambda i: i.module)

    def by_file(self) -> dict[str, list[CppcheckIssue]]:
        return group_by(self._sorted(), lambda i: i.path)

    def _sorted(self) -> list[CppcheckIssue]:
        return sorted(self.issues, key=lambda i: (i.path, i.line or 0))


# --- 커버리지 (llvm-cov) ---

COVERAGE_METRICS = ("lines", "functions", "branches", "mcdc", "regions")


@dataclass
class Counter:
    covered: int = 0
    count: int = 0

    @property
    def percent(self) -> float | None:
        """측정 대상이 없으면(count=0) None. 화면에는 '-'로 보인다."""
        return 100.0 * self.covered / self.count if self.count else None

    def __add__(self, other: "Counter") -> "Counter":
        return Counter(self.covered + other.covered, self.count + other.count)


@dataclass
class FileCoverage:
    path: str
    lines: Counter
    functions: Counter
    branches: Counter
    mcdc: Counter
    regions: Counter

    @property
    def module(self) -> str:
        return module_of(self.path)


@dataclass
class FunctionCoverage:
    name: str
    path: str
    start_line: int
    end_line: int
    calls: int
    lines: Counter
    branches: Counter
    mcdc: Counter
    regions: Counter

    @property
    def module(self) -> str:
        return module_of(self.path)


def sum_counters(files: Iterable[FileCoverage]) -> dict[str, Counter]:
    totals = {m: Counter() for m in COVERAGE_METRICS}
    for f in files:
        for m in COVERAGE_METRICS:
            totals[m] = totals[m] + getattr(f, m)
    return totals


@dataclass
class CoverageReport:
    """시험 묶음 하나의 커버리지. function_level=False 면 파일 단위까지만 있다."""

    name: str
    files: list[FileCoverage] = field(default_factory=list)
    functions: list[FunctionCoverage] = field(default_factory=list)
    function_level: bool = True

    @property
    def totals(self) -> dict[str, Counter]:
        return sum_counters(self.files)

    @property
    def uncovered_functions(self) -> list[FunctionCoverage]:
        return [f for f in self.functions if f.calls == 0]

    def functions_of(self, path: str) -> list[FunctionCoverage]:
        return [f for f in self.functions if f.path == path]

    def by_module(self) -> dict[str, list[FileCoverage]]:
        return group_by(self.files, lambda f: f.module)

    def module_totals(self, module: str) -> dict[str, Counter]:
        return sum_counters(f for f in self.files if f.module == module)
