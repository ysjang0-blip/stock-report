"""리포트 PDF 첫 페이지 문구로 목표주가 방향·투자의견 변동을 판정한다.

예) '목표주가(유지)', '380,000원(상향)', '직전 목표주가 265,000원', '기존 100,000원에서 90,000원으로',
    '30.5->38만원', '커버리지를 개시', 'BUY (M)', '매수(유지)', 'BUY(Maintain)'
판정할 수 없으면 None을 돌려주고, 그때는 과거 이력으로 판정한다.
"""
import re

from common import to_int

TP = r"(?:목표\s*주가|적정\s*주가|TP|Target\s*Price)"
NUM = r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(만\s*원|만원|원)?"
# 같은 문장 안: 마침표는 소수점(16.7%)일 때만 허용
SAME = r"(?:[^.]|\.(?=\d))"
# 원 단위 금액만 (억원·조원·%·배 등은 제외)
WON = r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(만\s*원|만원|원)(?![가-힣]*(?:억|조))"

SYMBOL = {"상향": "▲", "하향": "▼", "유지": "=", "신규": "N"}


def _to_won(num, unit, ref=None):
    v = float(num.replace(",", ""))
    if unit and "만" in unit:
        v *= 10000
    elif ref and v < ref / 100:      # '38만원'처럼 단위가 빠진 '30.5->38만원'의 앞 숫자
        v *= 10000
    return int(v)


def _word(s):
    if re.search(r"상향|Upgrade|UP\b", s, re.I):
        return "상향"
    if re.search(r"하향|Downgrade|DOWN\b", s, re.I):
        return "하향"
    if re.search(r"유지|Maintain|\(M\)|Hold the", s, re.I):
        return "유지"
    if re.search(r"신규|개시|제시|Initiat|편입", s, re.I):
        return "신규"
    return None


def target_change(text, target):
    return target_change_detail(text, target)[0]


def target_change_detail(text, target):
    """(방향 기호, 직전 목표가) — 직전 목표가는 리포트에 숫자로 적혀 있을 때만."""
    t = re.sub(r"\s+", " ", text)

    if re.search(r"커버리지\S*\s*(개시|시작)|신규\s*편입|Initiat(e|ion)", t, re.I):
        return "N", None

    # 1) 숫자로 직접 비교: '직전 목표주가 265,000원' / '기존 X원에서 Y원으로' / 'X->Y'
    prev = None
    m = re.search(r"직전\s*" + TP + r"\s*:?\s*" + NUM, t)
    if m:
        prev = _to_won(m.group(1), m.group(2), target)
    if prev is None:
        m = re.search(TP + SAME + r"{0,25}?기존\s*" + NUM + r"\s*에서\s*" + NUM, t) \
            or re.search(r"기존\s*" + NUM + r"\s*에서\s*" + NUM + r"\s*으로\s*(상향|하향)", t)
        if m:
            prev = _to_won(m.group(1), m.group(2), target)
    if prev is None:
        m = re.search(TP + SAME + r"{0,15}?" + NUM + r"\s*(?:->|→|⇒)\s*" + NUM, t)
        if m:
            prev = _to_won(m.group(1), m.group(2), target)
    if prev is None:
        # 변경 표: '신규 기존 증감 / 투자의견 BUY BUY / 목표주가 80,000 80,000 0.0%'
        m = re.search(r"신규\s*기존.{0,60}?" + TP + r"\s*([\d,]{4,})\s+([\d,]{4,})", t)
        if m and to_int(m.group(1)) == target:
            prev = to_int(m.group(2))
    if prev is None and target:
        # '목표주가 370,000원으로 하향조정(기존 390,000원)', '종전 목표주가 X원'
        for m in re.finditer(r"(?:기존|종전|이전)\s*(?:목표\s*주가|적정\s*주가|TP)?\s*:?\s*" + WON, t):
            v = _to_won(m.group(1), m.group(2), target)
            if v != target and target * 0.3 <= v <= target * 3:
                prev = v
                break
    if prev and target:
        return ("▲" if target > prev else "▼" if target < prev else "="), prev

    # 2) 목표주가 바로 옆의 표시: '목표주가(유지)', '380,000원(상향)', 'TP 410,000원 상향', '265,000원 (M)'
    votes = []
    for m in re.finditer(TP + r"[^.가-힣]{0,6}(?:\(12M\)|\(12개월\)|\(6개월\))?\s*[(:]?\s*([가-힣A-Za-z]{2,8})?\)?\s*:?\s*"
                         + NUM + r"\s*\(?\s*(상향|하향|유지|신규편입|신규|제시|M|U|D)?\)?", t):
        w = _word(m.group(1) or "") or _word(m.group(4) or "")
        if m.group(4) in ("U",):
            w = "상향"
        elif m.group(4) in ("D",):
            w = "하향"
        if w:
            votes.append(w)
    # '6개월 목표주가 23,000 상향' 처럼 숫자 뒤에 오는 경우
    for m in re.finditer(TP + r"\s*" + NUM + r"\s*(상향|하향|유지)", t):
        votes.append(m.group(3))
    # 3) 문장: '목표주가를 ~ 으로 상향/하향', '목표주가 ~ 유지'
    for m in re.finditer(TP + SAME + r"{0,30}?(상향|하향|유지|제시)", t):
        votes.append(_word(m.group(1)))

    votes = [v for v in votes if v]
    if not votes:
        return None, None
    first = votes[0]
    # 첫 판정을 우선하되, 여러 번 반대로 나오면 다수결
    best = max(set(votes), key=votes.count)
    sym = SYMBOL[first if votes.count(first) >= votes.count(best) else best]
    return sym, (target if sym == "=" else None)


def target_pct(text):
    """'기존 대비 +35%', '목표주가 500,000원으로 16.7% 하향', '360,000원으로 9% 상향' → 변화율(%)."""
    t = re.sub(r"\s+", " ", text)
    m = re.search(TP + SAME + r"{0,60}?기존\s*대비\s*([+-]?\d+(?:\.\d+)?)\s*%", t)
    if m:
        return float(m.group(1))
    m = re.search(TP + SAME + r"{0,40}?(\d+(?:\.\d+)?)\s*%\s*(상향|하향)", t)
    if m:
        v = float(m.group(1))
        return v if m.group(2) == "상향" else -v
    return None


def opinion_change(text):
    t = re.sub(r"\s+", " ", text)
    if re.search(r"커버리지\S*\s*(개시|시작)|신규\s*편입|Initiat(e|ion)", t, re.I):
        return "N"
    m = re.search(r"(?:BUY|Buy|매수|HOLD|Hold|중립|Trading\s*Buy|Outperform|Marketperform|Sell|매도)"
                  r"\s*[(,]?\s*(유지|상향|하향|신규|Maintain|Upgrade|Downgrade|Initiate|M|U|D)\)?", t)
    if m:
        w = {"M": "유지", "U": "상향", "D": "하향"}.get(m.group(1)) or _word(m.group(1))
        if w:
            return SYMBOL[w]
    # 변경 표: '신규 기존 증감 투자의견 BUY BUY'
    m = re.search(r"신규\s*기존.{0,20}?투자\s*의견\s*([A-Za-z가-힣]+)\s+([A-Za-z가-힣]+)", t)
    if m:
        from common import OPINION_RANK, opinion_category
        new, old = opinion_category(m.group(1)), opinion_category(m.group(2))
        if new and old:
            if new == old:
                return "="
            return "▲" if OPINION_RANK.get(new, 1) > OPINION_RANK.get(old, 1) else "▼"
    m = re.search(r"투자\s*의견" + SAME + r"{0,25}?(상향|하향|유지|제시)", t)
    if m:
        return SYMBOL[_word(m.group(1))]
    return None


OPINION_WORDS = r"(Strong\s*Buy|Trading\s*Buy|BUY|Buy|매수|HOLD|Hold|중립|Neutral|Outperform|Marketperform|MarketPerform|Underperform|Sell|SELL|매도|Not\s*Rated|NR)"


def find_target(text):
    """본문에서 이번 목표주가(원)를 찾는다. 예: '목표주가 58,000원', '목표주가 27만원'."""
    t = re.sub(r"\s+", " ", text)
    for m in re.finditer(TP + r"(?:\s*\(12M\)|\s*\(12개월\))?\s*(?:를|는|은|:)?\s*(?:기존\s*" + NUM + r"\s*에서\s*)?" + WON, t):
        v = _to_won(m.group(3), m.group(4))
        if v >= 100:
            return v
    return None


def find_opinion(text):
    t = re.sub(r"\s+", " ", text)
    m = re.search(r"투자\s*의견\s*(?:을|은|는|:)?\s*[‘'\"]?" + OPINION_WORDS, t)         or re.search(OPINION_WORDS + r"\s*[(,]?\s*(?:유지|상향|하향|신규|Maintain)", t)
    return m.group(1).replace(" ", "") if m else ""
