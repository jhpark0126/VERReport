"""도구마다 다른 경로 표기를 하나로 맞춘다.

도구 결과에는 빌드 컨테이너의 절대 경로(예: /work/src/door/bad.c)가 들어 있다.
리포트에서는 저장소 루트 기준 상대 경로(src/door/bad.c)로 보여 주고,
파일이 있는 디렉터리를 '모듈'로 본다.
"""

from __future__ import annotations

ROOT_MODULE = "(root)"


def normalize_path(raw: str, root: str | None = None) -> str:
    """구분자를 '/'로 바꾸고, root 아래 경로면 root를 떼어 상대 경로로 만든다."""
    path = raw.replace("\\", "/")
    if not root:
        return path
    prefix = root.replace("\\", "/").rstrip("/") + "/"
    if path.startswith(prefix):
        return path[len(prefix):]
    return path


def module_of(path: str) -> str:
    """파일이 있는 디렉터리를 모듈 이름으로 쓴다. 최상위 파일은 '(root)'."""
    head, sep, _ = path.rpartition("/")
    return head if sep and head else ROOT_MODULE
