# 기업리포트 요약 자동화

평일 아침마다 증권사 기업 리포트를 모아 `reports/YYYYMMDD 기업리포트 요약.pdf`로 만들고 텔레그램으로 보냅니다. 모두 무료입니다.

- 데이터: 한경컨센서스(작성자), 네이버 증권 리서치(증권사 범위가 더 넓음), 네이버·다음 시세(전일 정규장 종가)
- 증권사 홈페이지(개인 열람용): KB증권(목록 API: 의견·목표가·요약), NH투자증권(목록+요약보기), 한국투자증권(목록+상세), 다올투자증권(목록+요약 이미지 글자인식)
  - NH·한국투자는 사이트가 자동 수집을 원치 않으므로(robots.txt) 하루 2회·천천히 요청하고, 고객 전용 PDF는 받지 않음
  - 요약 PDF는 텔레그램으로만 받고 저장소에는 올리지 않음(`reports/`는 .gitignore). 저장소에는 이력·실행 기록(`data/`)만 저장
  - 수집 불가: DB증권(로그인·수집 금지), 삼성증권(로그인 필요)
- 요약: 각 리포트 PDF 첫 페이지의 굵은 핵심 문장(최대 3개). 뽑지 못하면 한경 요약 → 네이버 본문 앞부분 순으로 대신 씀
- 실행: GitHub Actions. 정시 실행은 **cron-job.org**가 GitHub API로 호출(한국시간 월~금 **08:10** 본발송 `mode=main`, **18:30** 보충발송 `mode=supplement` — 아침 이후 새 리포트가 생겼을 때만 갱신본 전송). GitHub 자체 예약은 08:50 예비 안전망(이미 보냈으면 건너뜀)
- 첫 페이지 '오늘의 핵심' 상자: 관심 종목·투자의견 변경·상향·신규·하향을 종목명과 변화율로 한눈에. 텔레그램에도 같은 요약을 먼저 보내고 PDF를 이어서 보냄
- 관심 종목: `watchlist.txt`(예시는 `watchlist.example.txt`, 저장소에 올라가지 않음) 또는 GitHub Secrets의 `WATCHLIST`. 관심 종목 리포트는 변화가 없어도 맨 위 '★ 내 관심 종목' 구역에 모임
- 정렬: 변화별 구역(★관심 종목 → ◆투자의견 변경 → ▲목표가 상향 → N신규 → ▲▼엇갈림 → ▼하향 → =유지 → 목표가 없음) → 같은 종목끼리 묶음 → 변화 구역은 목표가 변화폭 큰 순, 나머지는 Upside 순
- 의견변동/방향: 리포트 PDF의 문구('목표주가(상향)', '직전 목표주가', 'BUY(유지)' 등)로 판정. 문구가 없으면 `data/history.csv`의 직전 리포트와 비교해 추정(* 표시). 두 근거가 엇갈리면 ⚠ 표시
- 목표가 칸 아래에 직전 목표가와 변화율 표시 (예: ← 305,000 (+24.6%))
- 늦게 올라온 리포트: 최근 4일 리포트 중 아직 어느 날짜 판에도 실리지 않은 것을 포함(‘전일 발간’ 표시). 기록: `data/editions.json`
- 감시: 실행마다 `data/runs.csv`에 수집 건수를 기록하고, 평일 0건·한 출처만 0건·평소보다 크게 적음·PDF 읽기 실패가 많으면 텔레그램에 경고

## 처음 한 번 설정하기

### 1. 텔레그램 봇 만들기 (5분)
1. 텔레그램에서 **@BotFather** 검색 → `/newbot` 입력 → 이름을 정하면 **토큰**(예: `123456:ABC...`)을 줍니다.
2. 방금 만든 봇과 대화방을 열고 아무 메시지나 보냅니다.
3. 브라우저에서 `https://api.telegram.org/bot<토큰>/getUpdates` 를 열면 `"chat":{"id":123456789` 부분의 숫자가 **chat_id**입니다.

### 2. GitHub에 올리기
1. github.com 가입 → 오른쪽 위 **+ → New repository** → 이름 입력, **Private** 선택 → Create.
2. 이 폴더 전체를 그 저장소에 올립니다 (Claude에게 "GitHub에 올려줘"라고 해도 됩니다).

### 3. 비밀값 넣기
저장소 **Settings → Secrets and variables → Actions → New repository secret** 에서 두 개를 추가합니다.
- `TELEGRAM_BOT_TOKEN` : 1번의 토큰
- `TELEGRAM_CHAT_ID` : 1번의 chat_id
- `WATCHLIST` (선택) : 관심 종목, 쉼표로 구분 (예: `삼성전자,LG전자,035420`)

### 4. 시험 실행
저장소 **Actions** 탭 → **기업리포트 요약** → **Run workflow** 버튼. 몇 분 뒤 텔레그램으로 PDF가 오면 끝입니다.

## 내 PC에서 직접 돌리기
다올 요약 이미지를 읽으려면 글자인식 프로그램 Tesseract가 필요합니다(윈도우: `winget install UB-Mannheim.TesseractOCR`,
한국어 데이터 `kor.traineddata`를 `%USERPROFILE%	essdata`에 넣으면 자동으로 사용). 없으면 다올은 의견·목표가 없이 목록만 들어갑니다.
```
pip install -r requirements.txt
python -m playwright install chromium
python src/main.py --date 2026-10-07 --no-send   # PDF만 만들기
python src/main.py --bootstrap                   # 과거 180일 이력 다시 모으기
```


## cron-job.org로 정시 실행하기
GitHub 자체 예약은 몇 분~몇십 분 늦거나 건너뛸 수 있어서, 정시 실행은 cron-job.org가 GitHub를 직접 호출하게 한다.

1. **GitHub 토큰 만들기**: GitHub → Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate new token
   - Repository access: **Only select repositories** → `stock-report` 하나만
   - Permissions → Repository permissions → **Actions: Read and write**
   - 만료일은 최대 1년. 만료되면 호출이 실패하므로 달력에 기록해 둔다.
2. **cron-job.org 가입** 후 CREATE CRONJOB을 두 개 만든다. (공통 설정)
   - URL: `https://api.github.com/repos/ysjang0-blip/stock-report/actions/workflows/daily.yml/dispatches`
   - Request method: **POST**
   - Time zone: **Asia/Seoul**
   - Headers: `Accept: application/vnd.github+json`, `Authorization: Bearer <1번 토큰>`, `X-GitHub-Api-Version: 2022-11-28`, `User-Agent: cron-job-org`, `Content-Type: application/json`
3. 두 작업의 차이
   - 아침: 평일(월~금) 08:10, Request body `{"ref":"main","inputs":{"mode":"main"}}`
   - 저녁: 평일(월~금) 18:30, Request body `{"ref":"main","inputs":{"mode":"supplement"}}`
4. 성공하면 GitHub가 **204**(내용 없음)를 돌려준다. cron-job.org의 실패 알림 이메일을 켜 둔다.
5. 시험: cron-job.org에서 **Test run**을 누르면 GitHub Actions 탭에 새 실행이 나타난다.
