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
