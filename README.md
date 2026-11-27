# VERReport

테스트, 정적분석 등의 결과를 한 번에 보여준다.

빌드마다 나오는 검증 결과를 읽어서 정적 HTML 리포트를 만든다. 리포트는 대시보드 1장과 도구별 상세 페이지 4장으로 이루어진다.

| 도구 | 입력 파일 | 판정 기준 (기본값) |
|---|---|---|
| Google Test | `{tdd,unit,integration}/results.xml` | 모든 묶음 성공률 100% |
| 커버리지 (llvm-cov) | `{tdd,unit,integration}/coverage.json` (없으면 `summary.json`) | 단위 MC/DC 100%, 통합 함수 100%, TDD는 기록만 |
| Cppcheck | `cppcheck.xml` | 지적 0건 |
| Lizard | `lizard.csv` (없으면 `lizard.xml`) | 순환복잡도 10 이하, 함수 길이 80라인 이하 |

입력 폴더 구조는 ClaudeClang CI(`ci/*.sh`)가 `build/reports/`에 만드는 구조와 같다. 결과 파일이 없는 도구는 "결과 없음"으로 표시하고, 오류로 처리하지 않는다.

## 설치

```bash
python -m venv .venv
.venv/bin/pip install .            # 개발할 때: pip install -e ".[dev]"
```

파이썬 3.10 이상이 필요하고, 외부 의존성은 `jinja2` 하나다.

## 사용법

```bash
verreport build/reports -o build/reports/verreport
# 또는
python -m verreport build/reports -o build/reports/verreport --build-id 42 --branch develop
```

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `-o, --output` | `report` | HTML을 쓸 폴더 |
| `--source-root` | `$WORKSPACE`, 없으면 자동 판단 | 결과 파일의 절대 경로에서 떼어낼 앞부분 (예: `/work`) |
| `--build-id` | `$BUILD_NUMBER` | 빌드 번호 |
| `--job` | `$JOB_NAME` | 작업 이름 |
| `--branch` | `$BRANCH_NAME`, 없으면 `$GIT_BRANCH` | 브랜치 |
| `--commit` | `$GIT_COMMIT` | 커밋 |
| `--build-url` | `$BUILD_URL` | 빌드 링크 |
| `--build-time` | `$VERREPORT_BUILD_TIME`, 없으면 지금 | 빌드 일시. ISO 형식, 또는 epoch 초나 밀리초 |
| `--max-ccn` / `--max-length` | 10 / 80 | Lizard 기준 |
| `--fail-on-fail` | 꺼짐 | 전체 판정이 실패면 종료 코드 1 |

종료 코드는 다음과 같다.
- `0`: 리포트를 만들었다. 판정 결과와 무관하다. 판정으로 빌드를 실패시키는 일은 CI 게이트가 맡는다.
- `1`: `--fail-on-fail`을 줬고 전체 판정이 실패다.
- `2`: 결과 파일이 손상돼 읽지 못했다.

결과 폴더가 없으면 오류로 끝내지 않고, 이유를 적은 "결과 없음" 대시보드를 만든다. 검사할 소스가 없어 CI 게이트가 아무것도 만들지 않은 경우에도 Jenkins 링크가 비지 않게 하려는 것이다.

## 더 자세한 결과를 얻으려면

| 원하는 것 | 추가할 출력 |
|---|---|
| 함수 길이 판정 | `lizard --csv ... > lizard.csv` (XML에는 함수 길이가 없다) |
| 함수 단위 커버리지(MC/DC 포함) | `llvm-cov export <exe> -instr-profile=<profdata> <src> > coverage.json` (`-summary-only`로 만든 결과는 파일 단위까지만 나온다) |
| Cppcheck 지적이 있는 함수 | Lizard CSV가 있으면 함수 범위로 자동으로 찾는다 |

## 리포트 구성

- `index.html`: 빌드 일시, 전체 판정, 도구별 요약 표, 도구별 차트 카드, 모듈별 현황
- `gtest.html`, `coverage.html`, `cppcheck.html`, `lizard.html`: 모듈 → 파일 → 함수 순으로 펼쳐 볼 수 있다. 기준을 어긴 곳은 처음부터 펼쳐져 있다.
- 모듈은 소스 파일이 있는 폴더를 뜻한다.
- 커버리지에 아예 나타나지 않은 제품 소스(`src/`)는 "미측정 파일"로 따로 경고한다. 시험에서 호출하지 않은 파일은 링크되지 않아 퍼센트 계산에서 빠지기 때문이다.

Jenkins HTML Publisher의 기본 보안 정책(CSP)에서도 그대로 보이도록 다음을 지킨다.
- JavaScript를 쓰지 않는다.
- 인라인 스타일을 쓰지 않고, 스타일은 `assets/style.css` 파일에 둔다.
- 차트는 SVG로 그린다.

## 개발

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest
```

`tests/fixtures/`의 결과 파일은 ClaudeClang 빌드 이미지(`claudeclangbuild`)에서 실제 CI 스크립트로 만든 것이다.
