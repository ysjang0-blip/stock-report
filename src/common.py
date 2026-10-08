import re
import time

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    )
}

_session = requests.Session()
_session.headers.update(HEADERS)


def get(url, params=None, retries=3, delay=0.3, headers=None):
    """사이트에 부담을 주지 않도록 요청 사이에 잠깐 쉬고, 실패하면 몇 번 재시도한다."""
    for attempt in range(retries):
        try:
            r = _session.get(url, params=params, headers=headers, timeout=20)
            r.raise_for_status()
            time.sleep(delay)
            return r
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def norm_broker(name):
    return re.sub(r"\s+", "", name or "").replace("(리서치센터)", "")


def to_int(s):
    if s is None:
        return None
    s = re.sub(r"[^\d]", "", str(s))
    return int(s) if s and int(s) > 0 else None


def opinion_category(text):
    """투자의견 문구를 매수/중립/매도 세 가지로 묶는다 (의견변동 비교용)."""
    t = (text or "").strip().lower()
    if not t or "없음" in t or t in ("nr", "not rated", "n/a"):
        return ""
    if any(k in t for k in ("strong buy", "buy", "매수", "outperform", "overweight", "trading buy")):
        return "buy"
    if any(k in t for k in ("sell", "매도", "underperform", "underweight", "reduce")):
        return "sell"
    if any(k in t for k in ("hold", "중립", "neutral", "marketperform", "market perform")):
        return "hold"
    return t


OPINION_RANK = {"sell": 0, "hold": 1, "buy": 2}
