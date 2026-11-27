"""도구별 상세 페이지의 화면 데이터.

각 페이지는 모듈 → 파일 → 함수(또는 지적·시험) 순서로 내려간다.
문제가 있는 모듈·파일은 처음부터 펼쳐 둔다 (<details open>).
"""

from __future__ import annotations

from .build import BuildResult
from .charts import Part, hbar_chart, segmented_bar
from .model import COVERAGE_METRICS, FAILED, SEVERITIES, Counter, group_by

CELL_METRICS = ("lines", "functions", "branches", "mcdc")
FN_METRICS = ("lines", "branches", "mcdc", "regions")


def _base(build: BuildResult, page: str, key: str) -> dict:
    return {"page": page, "build": build, "info": build.info,
            "tool": {t.key: t for t in build.tools()}[key]}


# --- Google Test ---

def gtest_view(build: BuildResult, test_parts) -> dict:
    suites = []
    for suite, report in build.tests.items():
        s = report.summary()
        groups = []
        for name, cases in report.by_suite().items():
            failed = sum(1 for c in cases if c.status == FAILED)
            groups.append({"name": name, "cases": cases, "failed": failed,
                           "passed": sum(1 for c in cases if c.status == "passed"),
                           "status": "fail" if failed else
                           ("pass" if all(c.status == "passed" for c in cases) else "info")})
        suites.append({
            "suite": suite, "status": report.status, "summary": s,
            "timestamp": report.timestamp,
            "bar": segmented_bar([Part(n, s[k], css, f"{n} {s[k]}개") for k, n, css in test_parts],
                                 f"{suite} 시험 결과", width=200),
            "failures": report.failures, "groups": groups,
        })
    view = _base(build, "gtest", "gtest")
    view.update(suites=suites, legend_items=[(css, n) for _, n, css in test_parts])
    return view


# --- 커버리지 ---

def _problem(build: BuildResult, suite: str, counters: dict[str, Counter]) -> bool:
    """판정 지표가 기준 미달이면 문제. 판정이 없는 묶음(TDD)은 강조하지 않는다."""
    if build.coverage_gate(suite) is None:
        return False
    c = counters[build.coverage_metric(suite)]
    return c.covered < c.count


def coverage_view(build: BuildResult, cell) -> dict:
    """cell(build, suite, metric, counter, width) -> 미터 칸 (render.coverage_cell)."""
    suites = []
    for suite, report in build.coverage.items():
        modules = []
        for module, files in report.by_module().items():
            file_rows = []
            for f in files:
                fns = [{"fn": fn,
                        "cells": [cell(build, suite, m, getattr(fn, m), 60) for m in FN_METRICS],
                        "problem": fn.calls == 0 or _fn_problem(build, suite, fn)}
                       for fn in report.functions_of(f.path)]
                counters = {m: getattr(f, m) for m in COVERAGE_METRICS}
                file_rows.append({"file": f, "functions": fns,
                                  "cells": [cell(build, suite, m, counters[m], 60) for m in CELL_METRICS],
                                  "problem": _problem(build, suite, counters)})
            totals = report.module_totals(module)
            modules.append({"module": module, "files": file_rows,
                            "cells": [cell(build, suite, m, totals[m], 60) for m in CELL_METRICS],
                            "problem": _problem(build, suite, totals)})
        totals = report.totals
        suites.append({
            "suite": suite, "status": build.coverage_status(suite),
            "gate": build.coverage_gate(suite), "function_level": report.function_level,
            "cells": [cell(build, suite, m, totals[m], 110) for m in CELL_METRICS],
            "modules": modules, "unmeasured": build.unmeasured_files(suite),
            "uncovered": report.uncovered_functions,
        })
    view = _base(build, "coverage", "coverage")
    view.update(suites=suites, cell_metrics=CELL_METRICS, fn_metrics=FN_METRICS)
    return view


def _fn_problem(build: BuildResult, suite: str, fn) -> bool:
    if build.coverage_gate(suite) is None:
        return False
    metric = build.coverage_metric(suite)
    if metric == "functions":
        return fn.calls == 0
    c = getattr(fn, metric)
    return c.covered < c.count


# --- Cppcheck ---

def cppcheck_view(build: BuildResult) -> dict:
    view = _base(build, "cppcheck", "cppcheck")
    r = build.cppcheck
    if r is None:
        view.update(report=None)
        return view
    s = r.summary()
    modules = []
    for module, issues in r.by_module().items():
        files = [{"path": path,
                  "issues": [{"issue": i, "function": build.function_at(i.path, i.line)}
                             for i in file_issues]}
                 for path, file_issues in group_by(issues, lambda i: i.path).items()]
        modules.append({"module": module, "count": len(issues), "files": files})
    rules = sorted(((rid, len(items), items[0].severity)
                    for rid, items in group_by(r.issues, lambda i: i.id).items()),
                   key=lambda x: (-x[1], x[0]))
    view.update(
        report=r, summary=s, modules=modules, rules=rules,
        chart=hbar_chart([Part(n, s["by_severity"].get(n, 0), "fill-accent",
                               f"{n}: {s['by_severity'].get(n, 0)}건") for n in SEVERITIES],
                         "심각도별 Cppcheck 지적 수", label_width=100, width=360),
    )
    return view


# --- Lizard ---

def lizard_view(build: BuildResult) -> dict:
    view = _base(build, "lizard", "lizard")
    lz = build.lizard
    if lz is None:
        view.update(report=None)
        return view
    modules = []
    for module, fns in lz.by_module().items():
        files = []
        for path, file_fns in group_by(fns, lambda f: f.path).items():
            rows = [{"fn": f, "kinds": lz.violations_of(f)} for f in file_fns]
            files.append({"path": path, "functions": rows,
                          "violations": sum(1 for r in rows if r["kinds"]),
                          "max_ccn": max(f.ccn for f in file_fns)})
        modules.append({"module": module, "files": files, "functions": len(fns),
                        "violations": sum(f["violations"] for f in files),
                        "max_ccn": max(f.ccn for f in fns)})
    view.update(report=lz, summary=lz.summary(), modules=modules,
                violations=[{"fn": f, "kinds": lz.violations_of(f)} for f in
                            sorted(lz.violations, key=lambda f: (-f.ccn, f.path))])
    return view
