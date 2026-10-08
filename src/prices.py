"""기준일 직전 영업일의 정규장(한국거래소) 종가.

네이버 차트의 종가는 저녁 시간대 대체거래소(NXT) 거래까지 반영돼 정규장 종가와 다를 수 있다.
그래서 '기준일 종가 - 전일 대비 변동폭'(= 기준가)을 쓰고,
기준일 장이 아직 열리기 전(아침 실행)이면 다음 기준가를 알려주는 다음 금융 시세를 쓴다.
"""
from datetime import datetime, timedelta, timezone

from common import get, to_int

NAVER_DAILY = "https://m.stock.naver.com/api/stock/{code}/price"
DAUM_QUOTE = "https://finance.daum.net/api/quotes/A{code}"
KST = timezone(timedelta(hours=9))

_cache = {}


def prev_close(code, date):
    """date(YYYY-MM-DD) 직전 영업일의 정규장 종가."""
    key = (code, date)
    if key not in _cache:
        _cache[key] = _from_naver(code, date) or _from_daum(code, date) or _naver_fallback(code, date)
    return _cache[key]


def _daily_rows(code):
    try:
        return get(NAVER_DAILY.format(code=code), params={"pageSize": 60, "page": 1}).json()
    except Exception:
        return []


def _signed(s):
    s = (s or "").replace(",", "").strip()
    return int(s) if s.lstrip("+-").isdigit() else None


def _from_naver(code, date):
    for r in _daily_rows(code):
        if r.get("localTradedAt") == date:
            close, change = to_int(r.get("closePrice")), _signed(r.get("compareToPreviousClosePrice"))
            if close and change is not None:
                return close - change
    return None


def _from_daum(code, date):
    # 오늘 날짜일 때만 유효 (다음의 기준가 = 직전 영업일 정규장 종가)
    if date != datetime.now(KST).strftime("%Y-%m-%d"):
        return None
    try:
        d = get(DAUM_QUOTE.format(code=code), params={"summary": "false"},
                headers={"Referer": "https://finance.daum.net/"}).json()
        return int(d.get("basePrice") or d.get("prevClosingPrice") or 0) or None
    except Exception:
        return None


def _naver_fallback(code, date):
    rows = [r for r in _daily_rows(code) if r.get("localTradedAt", "") < date]
    return to_int(rows[0]["closePrice"]) if rows else None
