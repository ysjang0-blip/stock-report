"""실행 기록을 남기고, 수집이 평소와 다르게 적으면 경고한다.

조용히 0건이 되는 경우(사이트 구조 변경, 해외 서버 차단 등)를 놓치지 않기 위한 장치.
"""
import csv
import os
from datetime import date as Date, datetime, timedelta, timezone
from statistics import median

PATH = os.path.join(os.path.dirname(__file__), "..", "data", "runs.csv")
FIELDS = ["run_at", "date", "mode", "hankyung", "naver", "included", "carried",
          "pdf_read", "pdf_judged", "brokers", "warnings"]
KST = timezone(timedelta(hours=9))

# 한국 공휴일·증시 휴장일(대체공휴일 포함). 이 날은 리포트가 거의 없어 "0건" 경고를 하지 않는다.
# 매년 말에 다음 해 날짜를 추가한다(2028년 이후는 아직 없음).
HOLIDAYS = {
    # 2026
    "2026-01-01", "2026-02-16", "2026-02-17", "2026-02-18", "2026-03-02", "2026-05-01",
    "2026-05-05", "2026-05-25", "2026-06-03", "2026-08-17", "2026-09-24", "2026-09-25",
    "2026-10-05", "2026-10-09", "2026-12-25", "2026-12-31",
    # 2027
    "2027-01-01", "2027-02-08", "2027-02-09", "2027-03-01", "2027-05-05", "2027-05-13",
    "2027-08-16", "2027-09-14", "2027-09-15", "2027-09-16", "2027-10-04", "2027-10-11",
    "2027-12-31",
}


def is_workday(date):
    """평일이면서 공휴일이 아닌 날."""
    return Date.fromisoformat(date).weekday() < 5 and date not in HOLIDAYS


def _load():
    if not os.path.exists(PATH):
        return []
    with open(PATH, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def check(stats, date, mode):
    """경고 문구 목록."""
    warns = []
    weekday = is_workday(date)
    hk, nv, inc = stats["hankyung"], stats["naver"], stats["included"]

    if weekday and hk == 0 and nv == 0:
        warns.append("두 출처 모두 0건 — 공휴일이 아니라면 사이트 변경·접속 차단을 의심")
    elif hk == 0 and nv >= 5:
        warns.append("한경컨센서스 0건 — 수집 문제 의심")
    elif nv == 0 and hk >= 5:
        warns.append("네이버 0건 — 수집 문제 의심")

    past = [int(r["included"]) for r in _load()
            if r["mode"] == mode and r["date"] < date and int(r["included"]) > 0][-10:]
    if weekday and len(past) >= 5 and inc < median(past) * 0.4:
        warns.append(f"수집 {inc}건 — 최근 평소({median(past):.0f}건)보다 크게 적음")

    daily = ("KB증권", "NH투자증권", "한국투자증권")     # 거의 매일 리포트를 내는 곳
    for name, v in (stats.get("brokers") or {}).items():
        if isinstance(v, str):
            warns.append(f"{name} 수집 실패({v}) — 사이트 변경·차단 의심")
        elif v == 0 and weekday and name in daily and mode == "supplement":
            warns.append(f"{name} 0건 — 휴일이 아니라면 일시 오류·사이트 변경 의심")
    pdf_total = stats.get("pdf_total", stats["included"])
    if pdf_total >= 5 and stats["pdf_read"] < pdf_total * 0.5:
        warns.append(f"리포트 PDF를 {stats['pdf_read']}/{pdf_total}건만 읽음 — 요약·변동 판정 정확도 저하")
    return warns


def log(stats, date, mode, warns):
    exists = os.path.exists(PATH)
    with open(PATH, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if not exists:
            w.writeheader()
        row = {k: v for k, v in stats.items() if k in FIELDS}
        row["brokers"] = " ".join(f"{k}:{v}" for k, v in (stats.get("brokers") or {}).items())
        w.writerow({**row, "run_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
                    "date": date, "mode": mode, "warnings": " / ".join(warns)})
