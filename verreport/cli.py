"""명령줄 실행.

    verreport <리포트 폴더> -o <출력 폴더> [옵션]

빌드 정보는 옵션으로 주거나, 없으면 Jenkins 환경변수에서 읽는다.
    BUILD_NUMBER, JOB_NAME, BRANCH_NAME(없으면 GIT_BRANCH), GIT_COMMIT, BUILD_URL,
    WORKSPACE(소스 루트), VERREPORT_BUILD_TIME(빌드 시작 시각: ISO 또는 epoch 초/밀리초)

종료 코드: 0 리포트 생성 (판정과 무관), 1 --fail-on-fail 이고 전체 판정이 실패,
          2 결과 파일 손상 (결과 폴더가 없으면 "결과 없음" 대시보드를 만들고 0)
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from . import __version__
from .build import BuildInfo, Criteria, ReportError, load_build, raw_paths
from .render import STATUS_LABELS, render_site

# 저장소 루트 바로 아래에 오는 폴더 (ClaudeClang 구조)
TOP_DIRS = ("src", "include", "test")


def parse_build_time(raw: str) -> datetime:
    raw = raw.strip()
    if re.fullmatch(r"\d{10,13}", raw):
        seconds = int(raw) / (1000 if len(raw) == 13 else 1)
        return datetime.fromtimestamp(seconds)
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        raise ValueError(f"빌드 시각 형식을 알 수 없습니다: {raw!r} "
                         "(예: 2026-11-27T09:15:00 또는 epoch 밀리초)") from None


def detect_root(paths: list[str]) -> str | None:
    """'/work/src/a.c' 처럼 src·include·test 앞부분을 소스 루트로 본다 (가장 많이 나온 것)."""
    pattern = re.compile(r"^(.*?)/(?:%s)/" % "|".join(TOP_DIRS))
    roots = Counter()
    for p in paths:
        m = pattern.match(p.replace("\\", "/"))
        if m and m.group(1):
            roots[m.group(1)] += 1
    return roots.most_common(1)[0][0] if roots else None


def _branch_from_env() -> str | None:
    branch = os.environ.get("BRANCH_NAME") or os.environ.get("GIT_BRANCH")
    if branch and branch.startswith("origin/"):
        branch = branch[len("origin/"):]
    return branch


def build_parser() -> argparse.ArgumentParser:
    env = os.environ.get
    p = argparse.ArgumentParser(
        prog="verreport",
        description="검증 결과(Google Test, llvm-cov, Cppcheck, Lizard)를 HTML 대시보드로 만든다.")
    p.add_argument("reports", help="결과 폴더 (예: build/reports)")
    p.add_argument("-o", "--output", default="report", help="HTML을 쓸 폴더 (기본: report)")
    p.add_argument("--source-root", default=env("WORKSPACE"),
                   help="결과 파일의 절대 경로에서 뗄 소스 루트 (기본: $WORKSPACE, 없으면 자동 판단)")
    g = p.add_argument_group("빌드 정보 (기본: Jenkins 환경변수)")
    g.add_argument("--build-id", default=env("BUILD_NUMBER"))
    g.add_argument("--job", default=env("JOB_NAME"))
    g.add_argument("--branch", default=_branch_from_env())
    g.add_argument("--commit", default=env("GIT_COMMIT"))
    g.add_argument("--build-url", default=env("BUILD_URL"))
    g.add_argument("--build-time", default=env("VERREPORT_BUILD_TIME"),
                   help="빌드 시작 시각: ISO 형식 또는 epoch 초/밀리초 (기본: 지금)")
    c = p.add_argument_group("기준")
    c.add_argument("--max-ccn", type=int, default=10, help="순환복잡도 상한 (기본 10)")
    c.add_argument("--max-length", type=int, default=80, help="함수 길이 상한 (기본 80)")
    p.add_argument("--fail-on-fail", action="store_true",
                   help="전체 판정이 실패면 종료 코드 1 (기본은 판정과 무관하게 0)")
    p.add_argument("--version", action="version", version=f"verreport {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    reports = Path(args.reports)
    notes = []
    if not reports.is_dir():
        # 검사할 소스가 없으면 CI 게이트가 결과를 하나도 만들지 않는다. 오류로 끝내지 않고
        # '결과 없음' 대시보드를 만들어 Jenkins 링크가 비지 않게 한다.
        notes.append(f"결과 폴더가 없습니다: {reports} — 검사할 소스가 없어 게이트가 "
                     "건너뛰었거나, 결과가 다른 곳에 만들어졌습니다.")
        print(f"verreport: {notes[-1]}", file=sys.stderr)

    try:
        info = BuildInfo(build_id=args.build_id, job=args.job, branch=args.branch,
                         commit=args.commit, url=args.build_url)
        if args.build_time:
            info.build_time = parse_build_time(args.build_time)
        criteria = Criteria(max_ccn=args.max_ccn, max_length=args.max_length)

        root = args.source_root
        if not root:
            root = detect_root(raw_paths(load_build(reports, criteria=criteria)))
        build = load_build(reports, root=root, info=info, criteria=criteria)
        build.notes.extend(notes)
    except (ReportError, ValueError) as e:
        print(f"verreport: {e}", file=sys.stderr)
        return 2

    written = render_site(build, args.output)
    print(f"verreport: 전체 판정: {STATUS_LABELS[build.overall_status]}")
    for t in build.tools():
        print(f"  - {t.label}: {STATUS_LABELS[t.status]} ({t.headline})")
    print(f"verreport: {written[0]} 외 {len(written) - 1}개 페이지를 만들었습니다.")
    return 1 if args.fail_on_fail and build.overall_status == "fail" else 0
