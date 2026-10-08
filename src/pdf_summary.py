"""리포트 PDF 첫 페이지에서 굵은 핵심 문장(소제목)을 뽑아 요약 bullet로 만든다.

증권사마다 양식이 달라서 정해진 위치 대신 '글자 모양'으로 찾는다.
  1) 첫 페이지의 줄을 글꼴·크기별로 묶는다.
  2) 본문보다 크거나 굵은 글씨이면서 2~5개 정도 반복되는 묶음 = 소제목 후보.
  3) 리포트 제목, 표, 오른쪽 주가 정보 칸, 안내 문구는 제외한다.
"""
import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher

import pymupdf

from common import get

SKIP = re.compile(
    r"Appendix|Compliance|본 (자료|조사분석)|투자판단|무단|저작권|Analyst|애널리스트|RA\b|"
    r"@|\.com|Tel|☎|Research|리서치센터|Company (Report|Note|Update|Analysis)|기업분석|"
    r"^(Financial|Stock|Key|Consensus|Market|Price) Data$|^\(?\d{6}\)?$|^[\d,.%()\s/+\-원배조억]+$"
)


MARKERS = ("▶", "•", "■", "◼", "□", "ㆍ", "-", "·", "▷", "●")


def _is_bold(span):
    f = span["font"].lower()
    return bool(span["flags"] & 16) or any(k in f for k in ("bold", "heavy", "black", "-b", "extrab", "semib", "medium"))


def _lines(page):
    out = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            spans = [s for s in l["spans"] if s["text"].strip()]
            if not spans:
                continue
            text = re.sub(r"\s+", " ", "".join(s["text"] for s in l["spans"])).strip()
            main = max(spans, key=lambda s: len(s["text"].strip()))
            out.append({
                "text": text,
                "size": round(main["size"] * 2) / 2,
                "bold": _is_bold(main),
                "font": main["font"],
                "x0": l["bbox"][0], "x1": l["bbox"][2],
                "y0": l["bbox"][1], "y1": l["bbox"][3],
            })
    return out


def _merge_wrapped(lines):
    """같은 모양으로 이어지는 줄(줄바꿈된 한 문장)을 합친다."""
    lines = sorted(lines, key=lambda l: (round(l["y0"]), l["x0"]))
    units = []
    for l in lines:
        u = units[-1] if units else None
        if (u and u["key"] == (l["font"], l["size"]) and abs(l["x0"] - u["x0"]) < 30
                and 0 <= l["y0"] - u["y1"] < l["size"] * 0.9 and not l["text"].startswith(MARKERS)):
            u["text"] += ("" if u["text"].endswith(("-",)) else " ") + l["text"]
            u["y1"] = l["y1"]
            u["x1"] = max(u["x1"], l["x1"])
        else:
            units.append({**l, "key": (l["font"], l["size"])})
    return units


def extract(pdf_bytes, title="", name=""):
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    if not len(doc):
        return []
    page = doc[0]
    if len(page.get_text().strip()) < 300 and len(doc) > 1:
        page = doc[1]
    width = page.rect.width
    lines = [l for l in _lines(page) if len(l["text"]) >= 2]
    if not lines:
        return []

    # 본문 글자 크기 = 긴 줄들에서 가장 많이 쓰인 크기
    body = Counter()
    for l in lines:
        if len(l["text"]) >= 25:
            body[l["size"]] += len(l["text"])
    body_size = body.most_common(1)[0][0] if body else 9

    def similar(a, b):
        a, b = re.sub(r"\W", "", a), re.sub(r"\W", "", b)
        return a and b and (a in b or b in a or SequenceMatcher(None, a, b).ratio() > 0.75)

    units = _merge_wrapped(lines)
    title_units = [u for u in units if title and similar(u["text"], title)]
    title_y = min((u["y0"] for u in title_units), default=0)
    # 제목과 같은 문장이 소제목으로 한 번 더 나오는 양식이 있어, 가장 큰 글씨만 제목으로 본다
    title_units = sorted(title_units, key=lambda u: -u["size"])[:1]
    title_keys = {u["key"] for u in title_units}

    cands = []
    for u in units:
        t = u["text"].strip(" ▶•■◼□ㆍ·-▷●")
        u["marker"] = u["text"].lstrip().startswith(MARKERS)
        if len(t) < 6 or len(t) > 160 or SKIP.search(t):
            continue
        if u["key"] in title_keys or name and t.replace(" ", "") == name.replace(" ", ""):
            continue
        if len(t) < 30 and re.search(r"\(\s*[0-9A-Z]{6}", t):   # '종목명 (123456)'
            continue
        if not re.search(r"[가-힣A-Za-z]{2}", t):
            continue
        if u["x0"] > width * 0.62:          # 오른쪽 주가 정보 칸
            continue
        if u["size"] < body_size or (u["size"] == body_size and not u["bold"]):
            continue
        cands.append({**u, "text": t})

    groups = defaultdict(list)
    for c in cands:
        groups[c["key"]].append(c)

    def followed_by_body(u):
        below = [l for l in lines if l["y0"] > u["y1"] - 1 and l["y0"] - u["y1"] < u["size"] * 2.5
                 and abs(l["x0"] - u["x0"]) < 40 and l["size"] < u["size"] + 0.1 and len(l["text"]) >= 20]
        return bool(below) and below[0]["size"] <= body_size and not below[0]["text"].lstrip().startswith(MARKERS)

    best, best_score = None, 0
    for key, g in groups.items():
        if key in title_keys and len(g) < 2:
            continue
        n = len(g)
        if n > 8:
            continue
        avg_len = sum(len(c["text"]) for c in g) / n
        top = min(c["y0"] for c in g)
        body_after = sum(followed_by_body(c) for c in g) / n
        markers = sum(c["marker"] for c in g) / n
        score = (
            (3 if 2 <= n <= 5 else 1)
            + 1.5 * body_after
            - 1.0 * markers
            + (1 if g[0]["bold"] else 0)
            + min(g[0]["size"] - body_size, 4) * 0.4
            + (1 if 12 <= avg_len <= 90 else 0)
            + (1 if top >= title_y else 0)
            - top / page.rect.height
        )
        if score > best_score:
            best, best_score = g, score
    if not best:
        return []
    best = sorted(best, key=lambda c: (round(c["y0"]), c["x0"]))
    return [c["text"].strip("[] ") for c in best][:3]


def first_page_text(pdf_bytes):
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        # 1쪽이 표지(그림)인 리포트는 2쪽까지 읽는다
        text = ""
        for page in list(doc)[:2]:
            text += page.get_text() + "\n"
            if len(text.strip()) >= 300:
                break
        return text
    except Exception:
        return ""


def from_url(url, title="", name=""):
    try:
        r = get(url, delay=0.2)
        if not r.content.startswith(b"%PDF"):
            return []
        return extract(r.content, title, name)
    except Exception:
        return []
