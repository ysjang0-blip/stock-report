# AGENTS.md — 유지보수 안내 (Codex 등 코딩 에이전트용)

## 프로젝트 한 줄 요약
평일 아침마다 국내 증권사 **기업 리포트**를 무료 출처에서 모아, 변화(투자의견·목표가)가 큰 순서로 정리한
PDF를 만들고 텔레그램으로 보낸다. GitHub Actions(공개 저장소)에서 크론으로 실행한다.

## 사용자
- 개발 경험이 없는 개인 투자자. **항상 한국어로**, 전문 용어는 쉬운 말로 풀어서 설명한다.
- 기술적 선택이 필요하면 선택지마다 "무엇인지 / 고르면 어떻게 되는지 / 장단점 / 언제 좋은지"를 쉽게 설명하고 추천안을 하나 제시한다.
- 개인 열람용이다. 결과물(요약 PDF, 관심 종목)을 공개 저장소에 올리지 않는다.

## 실행
```
pip install -r requirements.txt
python -m playwright install chromium
python src/main.py --date 2026-10-08 --no-send   # 시험 실행: PDF만 reports/에 생성, 기록·발송 안 함
python src/main.py                               # 실제 실행(오늘, 한국시간): 기록 + 텔레그램 발송
python src/main.py --only-if-new                 # 보충발송: 같은 날 새 리포트가 늘었을 때만 갱신본
python src/main.py --bootstrap                   # 과거 180일 이력(data/history.csv) 재수집
python -m pytest tests                           # 판정 규칙 회귀 테스트 (pytest 없으면 python tests/test_rules.py)
```
- 다올 요약 이미지 글자인식에 Tesseract(+한국어 데이터) 필요. 윈도우는 `C:\Program Files\Tesseract-OCR`,
  한국어 데이터는 `%USERPROFILE%\tessdata\kor.traineddata`를 자동 사용. GitHub에서는 apt로 설치됨.
- 시험 실행은 `--no-send`로. 실제 실행은 `data/editions.json`, `data/runs.csv`, `data/sent.json`을 바꾼다.

## 구조 (src/)
| 파일 | 역할 |
|---|---|
| `main.py` | 전체 흐름: 수집 → 이번 판 선정 → PDF 분석 → 변동 판정 → 구역 정렬 → PDF 생성 → 기록 → 텔레그램 |
| `fetch_hankyung.py` | 한경컨센서스 목록(작성자, 요약 bullet, PDF 링크) |
| `fetch_naver.py` | 네이버 증권 리서치 API(`stock.naver.com/api/stockSecurity/researches/v2/company`) |
| `fetch_brokers.py` | 증권사 홈페이지: KB(목록 API), NH(목록+요약 API, 세션 쿠키 필요·CP949), 한국투자(목록+상세 HTML), 다올(목록+요약 JPG → Tesseract) |
| `build.py` | 출처 병합(`merge`, `add_broker_reports`), PDF 분석(`analyze_pdfs`), 변동 판정(`enrich`), 구역 정렬(`sort_sections`), 오늘의 핵심(`digest`) |
| `pdf_changes.py` | 리포트 문구로 목표가 방향·직전 목표가·변화율·투자의견 변동 판정, 본문에서 목표가/의견 추출 |
| `pdf_summary.py` | PDF 첫 페이지(표지면 2쪽)에서 굵은 소제목 = 요약 bullet 추출 |
| `prices.py` | 전일 **정규장** 종가(네이버 일별 `종가-전일대비`, 아침엔 다음 금융 기준가). 네이버 차트 종가는 야간(NXT) 포함이라 쓰지 않음 |
| `history.py` | `data/history.csv` 이력(증권사·종목별 직전 의견·목표가). KB는 목록 API로 빠짐없이 수집 |
| `editions.py` | 리포트 고유번호별로 어느 날짜 판에 실렸는지 기록 → 전날 늦게 올라온 리포트 이월(최근 4일) |
| `monitor.py` | `data/runs.csv` 실행 기록 + 이상 경고(평일 0건, 한 출처만 0건, 평소의 40% 미만, PDF 읽기 실패, 증권사 수집 실패) |
| `watchlist.py` | 관심 종목: 환경변수 `WATCHLIST` 또는 `watchlist.txt`(gitignore) |
| `render_pdf.py` | `templates/report.html` → Playwright Chromium으로 가로 A4 PDF, 빈 페이지 제거 |
| `notify_telegram.py` | 요약 메시지(sendMessage) 후 PDF(sendDocument) |

## 핵심 규칙 (바꾸기 전에 사용자와 상의)
- **변동 판정 우선순위**: ① 리포트 문구(PDF·요약·상세) → ② 과거 이력 비교(추정, `*` 표시) → ③ 근거 없음
  (네이버·한경 리포트는 `N*`, 이력이 아직 없는 증권사 홈페이지 리포트는 `–`). KB는 이력이 완전해서 이력 판정도 확정으로 본다.
- **네이버의 `prevGoalPrice`는 쓰지 않는다**(오래된 값이 섞여 오판이 확인됨).
- 문구 판정과 이력이 엇갈리면 문구를 따르고 ⚠ 메모. 목표가 메모는 직전 기록이 45일 이내일 때만.
- **정렬**: ★관심 종목 → ◆투자의견 변경 → ▲상향 → N신규 → ▲▼엇갈림 → ▼하향 → =유지 → 목표가 없음.
  같은 종목은 묶고, 변화 구역은 목표가 변화폭 큰 순, 나머지는 Upside 순.
- 실행 시각(`.github/workflows/daily.yml`, UTC 크론): 한국시간 평일 08:10 본발송, 18:30 보충발송(`--only-if-new`).

## 지켜야 할 제약
- **NH투자증권·한국투자증권은 robots.txt로 자동 수집을 막고 있다.** 사용자가 개인용으로 포함을 결정했다.
  요청은 하루 2회, 요청 간격 1초 이상(`SLOW`)을 유지하고, **고객 전용 PDF는 받지 않는다**(공개 목록·요약만).
- DB증권(로그인·robots 금지), 삼성증권(로그인 필요)은 수집하지 않는다. 로그인·보안 우회 시도 금지.
- 요약 PDF(`reports/`)와 `watchlist.txt`, 사용자가 넣은 원본 PDF(루트의 `*.pdf`)는 저장소에 올리지 않는다(.gitignore).
- 비밀값은 GitHub Secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `WATCHLIST`(선택).

## 고칠 때 검증 방법
1. `python -m pytest tests` — 실제 문구 사례 기반 회귀 테스트. 새 증권사 양식 문구를 고치면 사례를 테스트에 추가한다.
2. `python src/main.py --date <최근 평일> --no-send` 후 `reports/`의 PDF를 열어 구역·변화율·요약이 정상인지 본다.
3. 사이트 구조가 바뀌면 보통 해당 출처만 0건이 된다(`monitor.py` 경고). 해당 `fetch_*`를 고치고 2번으로 확인.
4. 판정 정확도 기준(2026-10 검증): 원본 대조 62건 오판 0, 2주 교차검증 102/106 일치(불일치는 모두 문구 쪽이 정답),
   실제 투자의견 변경 20건 중 19건 포착. 규칙 수정 후 이 수준이 떨어지지 않게 한다.

## 알려진 한계
- 그림으로 된 PDF(미래에셋 다수)는 문구 판정 불가 → 이력 판정(`*`).
- 다올 요약 문장은 글자인식이라 오탈자가 있다(`_fix_ocr`로 일부 보정, PDF에 표시).
- 한국투자 "산업Indepth" 속 종목 리포트는 목표가 정보가 없다.
- 원본(유료 서비스로 추정) 대비 중요 변화 포착률 약 81%. 빠지는 건 주로 DB·삼성·현대차·흥국 등.
