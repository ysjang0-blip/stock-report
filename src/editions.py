"""어느 리포트가 어느 날짜 판(edition)에 실렸는지 기록한다.

날짜로만 거르면 '전날 저녁 늦게 올라온 리포트'가 어느 날짜 판에도 안 실리고 사라진다.
그래서 최근 며칠치 리포트를 모두 가져온 뒤, 아직 어느 판에도 실리지 않은 것을 오늘 판에 넣는다.
"""
import json
import os

PATH = os.path.join(os.path.dirname(__file__), "..", "data", "editions.json")
LOOKBACK_DAYS = 4      # 월요일 아침에 금요일 저녁 리포트까지 챙기도록


def load():
    if os.path.exists(PATH):
        with open(PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"start": None, "ids": {}}


def save(state):
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=0, sort_keys=True)


def already_sent_ids(state, date):
    """date 판보다 앞선 판에 이미 실린 리포트 id."""
    return {i for i, d in state["ids"].items() if d < date}


def select(reports, state, date):
    """이번 date 판에 실을 리포트. 기록을 시작하기 전 날짜의 리포트는 넘어간 것으로 본다."""
    start = state["start"] or date
    sent = already_sent_ids(state, date)
    picked = []
    for r in reports:
        if any(i in sent for i in r["ids"]):
            continue
        if r["date"] < min(start, date):
            continue
        r["carried"] = r["date"] < date      # 전날 늦게 올라와 이번 판에 실리는 리포트
        picked.append(r)
    return picked


def mark(state, reports, date):
    if not state["start"] or date < state["start"]:
        state["start"] = date
    for r in reports:
        for i in r["ids"]:
            state["ids"].setdefault(i, date)
    return state
