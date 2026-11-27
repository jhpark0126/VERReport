"""BuildResult를 정적 HTML 사이트로 만든다.

    <out>/index.html          대시보드 (총괄)
    <out>/gtest.html          Google Test 상세
    <out>/coverage.html       커버리지 상세
    <out>/cppcheck.html       Cppcheck 상세
    <out>/lizard.html         Lizard 상세
    <out>/assets/style.css    스타일 (Jenkins CSP 때문에 외부 파일)
"""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from . import details
from .build import METRIC_LABELS, SUITE_LABELS, BuildResult
from .charts import Part, hbar_chart, meter, segmented_bar
from .model import DISABLED, FAILED, PASSED, SEVERITIES, SKIPPED, Counter

STATIC_DIR = Path(__file__).parent / "static"

STATUS_LABELS = {"pass": "통과", "fail": "실패", "na": "결과 없음", "info": "기록"}
TEST_PARTS = ((PASSED, "성공", "s-pass"), (FAILED, "실패", "s-fail"),
              (DISABLED, "비활성", "s-disabled"), (SKIPPED, "건너뜀", "s-skipped"))
COVERAGE_METRICS = ("lines", "functions", "branches", "mcdc")
TOP_N = 5


def pct(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f}%"


def fmt_dt(value: datetime | None) -> str:
    return "-" if value is None else value.strftime("%Y-%m-%d %H:%M:%S")


def anchor(text: str, prefix: str = "") -> str:
    """경로를 HTML id로: 'src/door/door.c' -> 'src-door-door-c'."""
    slug = re.sub(r"[^0-9A-Za-z]+", "-", text).strip("-").lower() or "root"
    return f"{prefix}{slug}"


def make_env() -> Environment:
    env = Environment(loader=PackageLoader("verreport", "templates"),
                      autoescape=select_autoescape(["html"]),
                      trim_blocks=True, lstrip_blocks=True)
    env.filters["pct"] = pct
    env.filters["dt"] = fmt_dt
    env.filters["anchor"] = anchor
    env.globals.update(TEST_MACROS=TEST_MACROS,STATUS_LABELS=STATUS_LABELS, SUITE_LABELS=SUITE_LABELS,
                       METRIC_LABELS=METRIC_LABELS)
    return env


def render_site(build: BuildResult, out_dir: str | Path) -> list[Path]:
    out = Path(out_dir)
    (out / "assets").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(STATIC_DIR / "style.css", out / "assets" / "style.css")

    env = make_env()
    pages = {
        "index.html": dashboard_view(build),
        "gtest.html": details.gtest_view(build, TEST_PARTS),
        "coverage.html": details.coverage_view(build, coverage_cell),
        "cppcheck.html": details.cppcheck_view(build),
        "lizard.html": details.lizard_view(build),
    }
    written = []
    for name, view in pages.items():
        path = out / name
        path.write_text(env.get_template(name).render(**view), encoding="utf-8")
        written.append(path)
    return written


# --- 대시보드 화면 데이터 ---

def dashboard_view(build: BuildResult) -> dict:
    tools = build.tools()
    failed = [t for t in tools if t.status == "fail"]
    judged = [t for t in tools if t.status in ("pass", "fail")]
    return {
        "page": "index",
        "build": build,
        "info": build.info,
        "overall": build.overall_status,
        "overall_text": (f"{len(judged)}개 도구 중 {len(failed)}개가 기준 미달"
                         if failed else
                         f"{len(judged)}개 도구 모두 기준 충족" if judged else
                         "판정할 결과가 없습니다"),
        "tools": tools,
        "tool_map": {t.key: t for t in tools},
        "gtest": _gtest_view(build),
        "coverage": _coverage_view(build),
        "cppcheck": _cppcheck_view(build),
        "lizard": _lizard_view(build),
        "modules": build.module_rows(),
        "module_columns": build.module_coverage_columns(),
    }


def _gtest_view(build: BuildResult) -> dict:
    rows = []
    for suite, report in build.tests.items():
        s = report.summary()
        label = f"{SUITE_LABELS[suite]} 시험 결과"
        rows.append({
            "suite": suite,
            "summary": s,
            "status": report.status,
            "bar": segmented_bar([Part(name, s[key], css, f"{name} {s[key]}개")
                                  for key, name, css in TEST_PARTS], label, width=120),
        })
    return {"rows": rows, "total": build.tests_total(),
            "legend": [(css, name) for _, name, css in TEST_PARTS]}


def coverage_cell(build: BuildResult, suite: str, metric: str, c: Counter,
                  width: int = 110) -> dict:
    """커버리지 한 칸: 판정 지표면 기준 눈금과 판정 색을 쓴다."""
    gate = build.coverage_gate(suite)
    is_gate = gate is not None and gate[0] == metric
    target = gate[1] if is_gate else None
    css = "fill-accent"
    if is_gate:
        ok = (c.percent if c.count else 100.0) >= target
        css = "s-pass" if ok else "s-fail"
    label = (f"{SUITE_LABELS[suite]} {METRIC_LABELS[metric]} 커버리지 "
             f"{pct(c.percent)} ({c.covered}/{c.count})")
    return {"metric": metric, "counter": c, "is_gate": is_gate, "target": target,
            "meter": meter(c.percent, label, target=target, css=css, width=width)}


def _coverage_view(build: BuildResult) -> dict:
    suites = list(build.coverage)
    # 행 = 지표, 열 = 시험 묶음 (카드 폭에 맞게)
    rows = [{"metric": m,
             "cells": [coverage_cell(build, s, m, build.coverage[s].totals[m]) for s in suites]}
            for m in COVERAGE_METRICS]
    unmeasured = {s: build.unmeasured_files(s) for s in suites}
    return {
        "suites": [{"suite": s, "status": build.coverage_status(s),
                    "gate": build.coverage_gate(s)} for s in suites],
        "rows": rows,
        "unmeasured": {s: files for s, files in unmeasured.items() if files},
    }


def _cppcheck_view(build: BuildResult) -> dict | None:
    if build.cppcheck is None:
        return None
    s = build.cppcheck.summary()
    sev = s["by_severity"]
    chart = hbar_chart([Part(name, sev.get(name, 0), "fill-accent", f"{name}: {sev.get(name, 0)}건")
                        for name in SEVERITIES], "심각도별 Cppcheck 지적 수",
                       label_width=100, width=360)
    return {"summary": s, "chart": chart, "version": build.cppcheck.version}


TEST_MACROS = {"TEST", "TEST_F", "TEST_P", "TYPED_TEST", "TYPED_TEST_P"}


def function_label(f) -> str:
    """gtest 매크로(TEST 등)는 이름만으로 구분이 안 돼 파일:라인을 붙인다."""
    if f.name in TEST_MACROS:
        return f"{f.name} @{f.path.rsplit('/', 1)[-1]}:{f.start_line}"
    return f.name


def _lizard_view(build: BuildResult) -> dict | None:
    lz = build.lizard
    if lz is None:
        return None

    def css(over: bool) -> str:
        return "s-fail" if over else "s-neutral"

    by_ccn = sorted(lz.functions, key=lambda f: f.ccn, reverse=True)[:TOP_N]
    ccn_chart = hbar_chart(
        [Part(function_label(f), f.ccn, css(f.ccn > lz.max_ccn),
              f"{f.name} ({f.path}:{f.start_line}) 순환복잡도 {f.ccn}") for f in by_ccn],
        f"순환복잡도 상위 {TOP_N}개 함수", threshold=lz.max_ccn, label_width=190,
        threshold_label=f"기준 {lz.max_ccn}")
    length_chart = None
    if lz.length_available:
        by_len = sorted(lz.functions, key=lambda f: f.length or 0, reverse=True)[:TOP_N]
        length_chart = hbar_chart(
            [Part(function_label(f), f.length or 0, css((f.length or 0) > lz.max_length),
                  f"{f.name} ({f.path}:{f.start_line}) 길이 {f.length}라인") for f in by_len],
            f"함수 길이 상위 {TOP_N}개 함수", threshold=lz.max_length, label_width=190,
            threshold_label=f"기준 {lz.max_length}")
    return {"summary": lz.summary(), "report": lz, "ccn_chart": ccn_chart,
            "length_chart": length_chart, "top_n": TOP_N}
