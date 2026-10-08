"""판정 규칙 회귀 테스트 — 실제 리포트 문구에서 뽑은 사례들.

실행: python -m pytest tests  (pytest가 없으면: python tests/test_rules.py)
규칙(src/pdf_changes.py 등)을 고친 뒤 반드시 돌려서 기존 사례가 깨지지 않았는지 확인한다.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import editions  # noqa: E402
import monitor  # noqa: E402
import pdf_changes as pc  # noqa: E402
from fetch_brokers import _fix_ocr  # noqa: E402

# (문구, 이번 목표가, 기대 방향, 기대 직전 목표가)
TARGET_CASES = [
    ("BUY (M) 목표주가 265,000원 (M) 직전 목표주가 265,000원 현재주가", 265000, "=", 265000),       # 유안타
    ("Buy (유지) 목표주가 (상향) 400,000 원 현재주가 308,500 원", 400000, "▲", None),               # LS
    ("BUY (유지) 목표주가(12M) 380,000원(상향) 현재주가(10.06)", 380000, "▲", None),                 # 하나
    ("Buy (유지) 목표주가(유지): 110,000원 현재 주가(10/7) 72,100원", 110000, "=", 110000),          # 한화
    ("목표주가 30.5->38만원으로 상향 조정", 380000, "▲", 305000),                                    # 하나
    ("목표주가는 기존 100,000원에서 90,000원으로 10.0% 하향 한다", 90000, "▼", 100000),             # 하나
    ("BUY 유지 TP 370,000원 유지 ... 목표주가 370,000원으로 하향조정 투자의견 Buy 및 목표주가는 "
     "370,000원으로 -5.1% 하향조정(기존 390,000원).", 370000, "▼", 390000),                         # 교보: 표지≠본문
    ("목표주가 500,000원으로 16.7% 하향: 3분기 파업과 원화 강세", 500000, "▼", None),               # 삼성(소수점)
    ("신규 기존 증감 투자의견 BUY BUY 목표주가 80,000 80,000 0.0%", 80000, "=", 80000),             # 삼성 변경표
    ("투자의견 BUY 매수, 유지 6개월 목표주가 23,000 상향 현재주가", 23000, "▲", None),              # 대신
    ("투자의견 ‘매수’, 목표주가 213,000 원 제시 ... 커버리지를 개시한다", 213000, "N", None),       # SK 신규
    ("매수(유지) 목표주가: 610,000 원(유지) 현재주가: 276,000 원", 610000, "=", 610000),            # SK
]

# (문구, 기대 의견 변동)
OPINION_CASES = [
    ("Hold (하향) 목표주가(하향): 110,000원", "▼"),                         # 한화 롯데칠성
    ("투자의견 BUY(상향) 목표주가 120,000원(상향)", "▲"),                   # 유진
    ("투자의견 Hold로 하향, 목표주가는 23,000원 유지", "▼"),                # iM HMM
    ("BUY(Maintain) 목표주가: 120,000원", "="),                             # 키움
    ("신규 기존 증감 투자의견 BUY HOLD 목표주가 500,000 400,000 25.0%", "▲"),  # 삼성 변경표
    ("매수(신규편입) 목표주가: 213,000 원(신규편입)", "N"),                 # SK
]


def test_target_change():
    for text, target, sym, prev in TARGET_CASES:
        got = pc.target_change_detail(text, target)
        assert got[0] == sym, (text, got)
        if prev is not None:
            assert got[1] == prev, (text, got)


def test_opinion_change():
    for text, sym in OPINION_CASES:
        assert pc.opinion_change(text) == sym, (text, pc.opinion_change(text))


def test_target_pct_and_find():
    assert pc.target_pct("목표주가 23,000원으로 상향 (기존 대비 +35%)") == 35.0
    assert pc.target_pct("목표주가 500,000원으로 16.7% 하향") == -16.7
    assert pc.find_target("투자의견 Buy 및 목표주가 58,000원 유지") == 58000
    assert pc.find_target("투자의견 BUY, 적정주가 27만원으로 상향") == 270000
    assert pc.find_opinion("투자의견 매수와 목표주가 115,000원을 유지한다") == "매수"


def test_editions_carry_over():
    st = {"start": None, "ids": {}}
    R = lambda i, d: {"ids": [i], "date": d}
    a = editions.select([R("a", "2026-10-07")], st, "2026-10-07")
    st = editions.mark(st, a, "2026-10-07")
    # 같은 날 저녁 보충판: 아침 것 + 새 것 모두
    b = editions.select([R("a", "2026-10-07"), R("b", "2026-10-07")], st, "2026-10-07")
    assert [r["ids"][0] for r in b] == ["a", "b"]
    st = editions.mark(st, b, "2026-10-07")
    # 다음 날: 전날 늦게 올라온 c는 이월, 이미 실린 a·b는 제외
    c = editions.select([R("a", "2026-10-07"), R("c", "2026-10-07"), R("d", "2026-10-08")], st, "2026-10-08")
    assert [(r["ids"][0], r["carried"]) for r in c] == [("c", True), ("d", False)]


def test_monitor_warnings():
    z = {"hankyung": 0, "naver": 0, "included": 0, "carried": 0, "pdf_read": 0, "pdf_judged": 0}
    assert monitor.check(z, "2026-10-08", "main")          # 평일 0건 → 경고
    assert not monitor.check(z, "2026-10-10", "main")      # 토요일 0건 → 정상
    assert monitor.check({**z, "naver": 40, "included": 40, "pdf_read": 38}, "2026-10-08", "main")  # 한경만 0
    assert monitor.check({**z, "brokers": {"NH투자증권": "오류: Timeout"}}, "2026-10-10", "main")


def test_ocr_fix():
    assert _fix_ocr("3026 영업이익 186먹원, 30268 증믹") == "3Q26 영업이익 186억원, 3Q26E 증익"
    assert _fix_ocr("2026년 1,300") == "2026년 1,300"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
