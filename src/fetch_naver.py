"""네이버 증권 리서치(종목분석) — 한경에 없는 증권사까지 넓게 커버한다."""
import html
import re

from common import get, to_int

LIST_URL = "https://stock.naver.com/api/stockSecurity/researches/v2/company"
DETAIL_URL = "https://stock.naver.com/api/stockSecurity/researches/v2/company/{nid}"


def fetch_list(since, until=None, page_size=50, max_pages=200):
    """writeDate가 since~until(YYYY-MM-DD) 사이인 목록 항목. 최신순이므로 since보다 오래되면 멈춘다."""
    until = until or "9999-12-31"
    items = []
    for index in range(max_pages):
        data = get(LIST_URL, params={"index": index, "size": page_size}).json()
        page = data.get("items", [])
        for it in page:
            if since <= it["writeDate"] <= until:
                items.append(it)
        if not page or page[-1]["writeDate"] < since or not data.get("hasNext"):
            break
    return items


def fetch(since, until=None, skip=()):
    """since~until 기간 리포트 + 상세(PDF 링크). skip에 든 리포트(이미 보낸 것)는 상세 조회를 건너뛴다."""
    reports = []
    for it in fetch_list(since, until or since):
        if f"nv:{it['nid']}" in skip:
            continue
        d = get(DETAIL_URL.format(nid=it["nid"])).json()
        reports.append({
            "source": "naver",
            "ids": [f"nv:{it['nid']}"],
            "date": d["writeDate"],
            "code": d["itemCode"],
            "name": d["itemName"],
            "title": html.unescape(d["title"]).strip(),
            "target": to_int(d.get("goalPrice")),
            "opinion": "" if d.get("opinionText") == "없음" else (d.get("opinionText") or ""),
            "author": "",
            "broker": d["brokerName"],
            "bullets": summarize(d.get("content", "")),
            "pdf": d.get("attachUrl", ""),
        })
    return reports


def summarize(content_html, max_sentences=3, max_chars=220):
    """본문 앞부분에서 핵심 문장 몇 개를 뽑아 bullet로 만든다 (AI 없이 무료로)."""
    text = re.sub(r"<br\s*/?>|</p>|</li>", "\n", content_html or "", flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    lines = [re.sub(r"\s+", " ", l).strip() for l in text.split("\n")]
    lines = [l for l in lines if len(l) > 1]

    # 짧은 줄은 소제목으로 보고 건너뛰고, 긴 문단은 문장 단위로 자른다.
    sentences = []
    for line in lines:
        if len(line) < 25:
            continue
        sentences += [s.strip() for s in re.split(r"(?<=[다음함임됨]\.)\s+|(?<=[.!?])\s+(?=[가-힣A-Z])", line) if s.strip()]

    out, total = [], 0
    for s in sentences:
        s = re.sub(r"^[■□▶▷●○◆◇•·\"'“”‘’\-\s]+", "", s)
        if len(s) > 130:
            s = s[:128].rstrip() + "…"
        if len(out) >= max_sentences or total + len(s) > max_chars and out:
            break
        out.append(s)
        total += len(s)
    return out
