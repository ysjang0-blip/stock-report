"""증권사·종목별 과거 투자의견/목표가 이력 (의견변동·방향 계산용)."""
import csv
import os
from datetime import date as Date, timedelta

from common import norm_broker, opinion_category

PATH = os.path.join(os.path.dirname(__file__), "..", "data", "history.csv")
FIELDS = ["date", "code", "broker", "opinion", "target"]


def load():
    if not os.path.exists(PATH):
        return []
    with open(PATH, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save(rows):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    uniq = {(r["date"], r["code"], r["broker"], r["opinion"], str(r["target"])): r for r in rows}
    rows = sorted(uniq.values(), key=lambda r: (r["date"], r["code"], r["broker"]))
    with open(PATH, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def to_row(rep):
    return {
        "date": rep["date"],
        "code": rep["code"],
        "broker": norm_broker(rep["broker"]),
        "opinion": opinion_category(rep.get("opinion")),
        "target": rep.get("target") or "",
    }


def previous(rows, code, broker, before):
    """before 날짜 이전, 같은 증권사·같은 종목의 가장 최근 기록."""
    b = norm_broker(broker)
    cands = [r for r in rows if r["code"] == code and r["broker"] == b and r["date"] < before]
    return max(cands, key=lambda r: r["date"]) if cands else None


def bootstrap(days=180):
    """처음 한 번: 최근 N일치 리포트를 모아 이력을 만든다."""
    import fetch_hankyung
    import fetch_naver
    from common import to_int

    end = Date.today()
    start = (end - timedelta(days=days)).isoformat()
    rows = load()
    for it in fetch_naver.fetch_list(start, end.isoformat()):
        rows.append(to_row({
            "date": it["writeDate"], "code": it["itemCode"], "broker": it["brokerName"],
            "opinion": it.get("opinionText"), "target": to_int(it.get("goalPrice")),
        }))
    # 한경은 기간을 한 달씩 나눠 요청
    cur = end - timedelta(days=days)
    while cur <= end:
        nxt = min(cur + timedelta(days=30), end)
        for rep in fetch_hankyung.fetch(cur.isoformat(), nxt.isoformat()):
            rows.append(to_row(rep))
        cur = nxt + timedelta(days=1)
    rows += bootstrap_kb_rows(start, end.isoformat())
    save(rows)
    return len(rows)


def bootstrap_kb_rows(since, until):
    """KB증권은 목록 API에 모든 리포트가 있어 과거 이력을 빠짐없이 모을 수 있다."""
    import fetch_brokers
    from common import to_int
    out = []
    for it in fetch_brokers.kb_list(since, until):
        if it.get("stkCd"):
            out.append(to_row({"date": it["publicDate"], "code": it["stkCd"], "broker": "KB증권",
                               "opinion": it.get("recomm"),
                               "target": to_int((it.get("tp") or "").split(".")[0])}))
    return out
