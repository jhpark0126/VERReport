from datetime import datetime
from pathlib import Path

import pytest

from verreport.cli import detect_root, main, parse_build_time

REPORTS = Path(__file__).parent / "fixtures" / "reports"
JENKINS_ENV = ("BUILD_NUMBER", "JOB_NAME", "BRANCH_NAME", "GIT_BRANCH", "GIT_COMMIT",
               "BUILD_URL", "WORKSPACE", "VERREPORT_BUILD_TIME")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in JENKINS_ENV:
        monkeypatch.delenv(k, raising=False)


def read(out, page="index.html"):
    return (out / page).read_text(encoding="utf-8")


def test_generates_site(tmp_path, capsys):
    out = tmp_path / "out"
    rc = main([str(REPORTS), "-o", str(out), "--build-id", "7", "--branch", "develop",
               "--commit", "deadbeef", "--build-time", "2026-11-27T09:15:00"])
    assert rc == 0
    for page in ("index.html", "gtest.html", "coverage.html", "cppcheck.html", "lizard.html"):
        assert (out / page).is_file()
    html = read(out)
    assert "#7" in html and "develop" in html and "2026-11-27 09:15:00" in html
    assert "전체 판정: 실패" in capsys.readouterr().out


def test_jenkins_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("BUILD_NUMBER", "123")
    monkeypatch.setenv("JOB_NAME", "ClaudeClang/develop")
    monkeypatch.setenv("BRANCH_NAME", "develop")
    monkeypatch.setenv("GIT_COMMIT", "0123456789abcdef")
    monkeypatch.setenv("BUILD_URL", "http://localhost:8080/job/x/123/")
    monkeypatch.setenv("VERREPORT_BUILD_TIME", "1795770000000")   # Jenkins: 밀리초
    out = tmp_path / "out"
    assert main([str(REPORTS), "-o", str(out)]) == 0
    html = read(out)
    assert "#123" in html and "ClaudeClang/develop" in html and "0123456789" in html
    assert 'href="http://localhost:8080/job/x/123/"' in html
    assert datetime.fromtimestamp(1795770000).strftime("%Y-%m-%d %H:%M:%S") in html


def test_git_branch_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_BRANCH", "origin/feature/x")
    out = tmp_path / "out"
    main([str(REPORTS), "-o", str(out)])
    assert "feature/x" in read(out) and "origin/feature/x" not in read(out)


def test_source_root_is_detected(tmp_path):
    # 결과 파일 경로는 /work/... 이다. 루트를 주지 않아도 src/... 로 보여야 한다.
    out = tmp_path / "out"
    main([str(REPORTS), "-o", str(out)])
    html = read(out, "lizard.html")
    assert "src/door/door_state.c:1" in html
    assert "/work/" not in html


def test_explicit_source_root(tmp_path):
    out = tmp_path / "out"
    main([str(REPORTS), "-o", str(out), "--source-root", "/work"])
    assert "/work/" not in read(out, "cppcheck.html")


def test_thresholds(tmp_path):
    out = tmp_path / "out"
    main([str(REPORTS), "-o", str(out), "--max-ccn", "15", "--max-length", "100"])
    assert "위반 함수 0개" in read(out)


def test_fail_on_fail(tmp_path):
    assert main([str(REPORTS), "-o", str(tmp_path / "a"), "--fail-on-fail"]) == 1


def test_missing_reports_dir(tmp_path, capsys):
    assert main([str(tmp_path / "nope"), "-o", str(tmp_path / "out")]) == 2
    assert "리포트 폴더가 없습니다" in capsys.readouterr().err


def test_broken_input(tmp_path, capsys):
    d = tmp_path / "r"
    d.mkdir()
    (d / "cppcheck.xml").write_text("<not-xml", encoding="utf-8")
    assert main([str(d), "-o", str(tmp_path / "out")]) == 2
    assert "cppcheck.xml" in capsys.readouterr().err


# --- 보조 함수 ---

@pytest.mark.parametrize("raw,expected", [
    ("2026-11-27T09:15:00", datetime(2026, 11, 27, 9, 15)),
    ("2026-11-27 09:15:00", datetime(2026, 11, 27, 9, 15)),
    ("1795770000000", datetime.fromtimestamp(1795770000)),
    ("1795770000", datetime.fromtimestamp(1795770000)),
])
def test_parse_build_time(raw, expected):
    assert parse_build_time(raw) == expected


def test_parse_build_time_invalid():
    with pytest.raises(ValueError):
        parse_build_time("어제")


@pytest.mark.parametrize("paths,root", [
    (["/work/src/a.c", "/work/test/unit/t.cpp", "/work/include/a.h"], "/work"),
    (["/var/jenkins_home/workspace/CC/src/a.c"], "/var/jenkins_home/workspace/CC"),
    (["C:/ws/src/a.c", "C:/ws/test/t.cpp"], "C:/ws"),
    (["src/a.c", "test/t.cpp"], None),          # 이미 상대 경로
    ([], None),
])
def test_detect_root(paths, root):
    assert detect_root(paths) == root
