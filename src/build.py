"""두 출처를 합치고, 의견변동·방향·Upside를 계산해 정렬한다."""
from datetime import datetime
from difflib import SequenceMatcher

import pdf_changes
import pdf_summary
import prices
import watchlist
from common import OPINION_RANK, get, norm_broker, opinion_category
from history import previous


def merge(hankyung, naver):
    """같은 종목·같은 증권사 리포트는 하나로 합친다. 작성자·요약은 한경 우선."""
    merged = [dict(r) for r in hankyung]
    for nv in naver:
        match = _find_match(merged, nv)
        if match is None:
            merged.append(dict(nv))
            continue
        match["matched"] = True
        match["ids"] = match["ids"] + nv["ids"]
        match["target"] = match.get("target") or nv.get("target")
        match["opinion"] = match.get("opinion") or nv.get("opinion")
        match["pdf_alt"] = nv.get("pdf")
        # 한경 요약이 제목 한 줄뿐이면 네이버 본문 요약이 더 알차다
        hk_bullets = match.get("bullets") or []
        if len(hk_bullets) <= 1 and sum(map(len, hk_bullets)) < 40 and nv.get("bullets"):
            match["bullets"] = nv["bullets"]
    return merged


def analyze_pdfs(reports):
    """리포트 PDF 첫 페이지를 읽어 요약(핵심 문장)과 목표가·의견 변동 표시를 얻는다.
    못 읽으면 기존 요약을 두고, 변동은 enrich()에서 과거 이력으로 판정한다."""
    for r in reports:
        if r.get("no_pdf"):            # 증권사 홈페이지에서 가져온 리포트는 이미 요약·판정이 끝나 있다
            continue
        pdf = None
        for url in (r.get("pdf_alt"), r.get("pdf")):
            if url and pdf is None:
                try:
                    content = get(url, delay=0.2).content
                    pdf = content if content.startswith(b"%PDF") else None
                except Exception:
                    pdf = None
        if pdf is None:
            continue
        r["pdf_read"] = True
        bullets = pdf_summary.extract(pdf, r["title"], r["name"])
        if bullets:
            r["bullets"] = bullets
            r["summary_from"] = "pdf"
        text = pdf_summary.first_page_text(pdf)
        r["pdf_tp_change"], r["pdf_prev_target"] = pdf_changes.target_change_detail(text, r.get("target"))
        r["pdf_op_change"] = pdf_changes.opinion_change(text)
        r["pdf_tp_pct"] = pdf_changes.target_pct(text)
    return reports


def add_broker_reports(merged, extra):
    """증권사 홈페이지 리포트를 더한다. 같은 날·같은 증권사·같은 종목이 이미 있으면 건너뛴다."""
    have = {(r["date"], norm_broker(r["broker"]), r["code"]) for r in merged}
    return merged + [r for r in extra if (r["date"], norm_broker(r["broker"]), r["code"]) not in have]


def _find_match(merged, nv):
    cands = [m for m in merged
             if m["source"] == "hankyung" and not m.get("matched")
             and m["code"] == nv["code"] and norm_broker(m["broker"]) == norm_broker(nv["broker"])]
    if not cands:
        return None
    return max(cands, key=lambda m: SequenceMatcher(None, m["title"], nv["title"]).ratio())


def _cmp(new, old):
    return "▲" if new > old else "▼" if new < old else "="


def enrich(reports, hist_rows, date):
    """목표가 방향·의견변동을 정한다.
    근거 우선순위: ① 리포트 PDF 문구(확실) → ② 과거 이력 비교(추정, * 표시) → ③ 둘 다 없으면 N*(신규 추정).
    두 근거가 엇갈리면 PDF를 따르되 경고 메모를 붙인다."""
    for r in reports:
        prev = previous(hist_rows, r["code"], r["broker"], date)
        notes = []

        # 투자의견
        cur_op = opinion_category(r.get("opinion"))
        hist_op = None
        if cur_op and prev and prev["opinion"]:
            hist_op = "=" if prev["opinion"] == cur_op else (
                "▲" if OPINION_RANK.get(cur_op, 1) > OPINION_RANK.get(prev["opinion"], 1) else "▼")
        if not cur_op:
            r["op_change"], r["op_basis"] = "", ""
        elif r.get("pdf_op_change"):
            r["op_change"], r["op_basis"] = r["pdf_op_change"], "pdf"
            if hist_op and hist_op != r["op_change"] and r["op_change"] != "N":
                notes.append(f"이력 비교로는 의견 {hist_op} ({prev['date']} {prev['opinion']} → {cur_op})")
        elif hist_op:
            r["op_change"], r["op_basis"] = hist_op, ("source" if r.get("history_complete") else "history")
        elif r.get("no_pdf") and not r.get("history_complete"):
            r["op_change"], r["op_basis"] = "–", "none"     # 이력이 아직 없는 증권사: 판단 불가
        else:
            r["op_change"], r["op_basis"] = "N", "none"

        # 목표주가 방향과 변화 크기
        target = r.get("target")
        hist_prev = int(prev["target"]) if prev and prev["target"] else None
        hist_tp = _cmp(target, hist_prev) if target and hist_prev else None
        r["prev_target"] = None
        if not target:
            r["tp_change"], r["tp_basis"] = "", ""
        elif r.get("pdf_tp_change"):
            r["tp_change"], r["tp_basis"] = r["pdf_tp_change"], "pdf"
            r["prev_target"] = r.get("pdf_prev_target")
            if not r["prev_target"] and hist_tp == r["tp_change"] and hist_tp in ("▲", "▼"):
                r["prev_target"] = hist_prev        # 방향이 같으면 이력의 숫자로 변화폭 계산
            # 직전 기록이 오래됐으면(45일 초과) 그 사이 리포트가 빠졌을 가능성이 커서 경고하지 않는다
            recent = prev and (datetime.fromisoformat(date) - datetime.fromisoformat(prev["date"])).days <= 45
            if hist_tp and hist_tp != r["tp_change"] and r["tp_change"] != "N" and recent:
                notes.append(f"이력 비교로는 목표가 {hist_tp} ({prev['date']} {hist_prev:,}원) — 사이에 수집 못 한 리포트가 있을 수 있음")
        elif not hist_tp and r.get("no_pdf") and not r.get("history_complete"):
            r["tp_change"], r["tp_basis"] = "–", "none"     # 이력이 아직 없는 증권사: 판단 불가
        elif hist_tp:
            # KB처럼 그 증권사 리포트를 빠짐없이 모으는 경우 이력 비교도 확실하다
            basis = "source" if r.get("history_complete") else "history"
            r["tp_change"], r["tp_basis"], r["prev_target"] = hist_tp, basis, hist_prev
        else:
            r["tp_change"], r["tp_basis"] = "N", "none"

        r["tp_pct"] = ((target / r["prev_target"] - 1) * 100
                       if target and r["prev_target"] and r["tp_change"] in ("▲", "▼") else None)
        pct = r.get("pdf_tp_pct")
        if r["tp_pct"] is None and pct and r["tp_change"] == ("▲" if pct > 0 else "▼"):
            r["tp_pct"] = pct           # 리포트에 비율만 적힌 경우 ('기존 대비 +35%')
        r["notes"] = notes

        r["prev_close"] = prices.prev_close(r["code"], date)
        if target and r["prev_close"]:
            r["upside"] = (target / r["prev_close"] - 1) * 100
        else:
            r["upside"] = None
    return reports


SECTIONS = [
    ("watch", "★ 내 관심 종목"),
    ("opinion", "◆ 투자의견 변경"),
    ("up", "▲ 목표가 상향"),
    ("new", "N 신규 커버리지"),
    ("mixed", "▲▼ 증권사별 엇갈림"),
    ("down", "▼ 목표가 하향"),
    ("keep", "= 유지"),
    ("none", "목표가 없음 (탐방·소형주 등)"),
]
CHANGE_SECTIONS = ("watch", "opinion", "up", "mixed", "down")


def _stock_section(reps, watch=()):
    if watch and any(watchlist.matches(r, watch) for r in reps):
        return "watch"
    if any(r["op_change"] in ("▲", "▼") for r in reps):
        return "opinion"
    marks = {r["tp_change"] for r in reps}
    if not any(r.get("target") for r in reps):
        return "none"
    up, down = "▲" in marks, "▼" in marks
    if up and down:
        return "mixed"
    if up:
        return "up"
    if down:
        return "down"
    if "N" in marks:
        return "new"
    return "keep"


def sort_sections(reports, watch=()):
    """변화별 구역 → 같은 종목끼리 묶음.
    변화 구역은 목표가 변화폭이 큰 종목부터, 나머지 구역은 Upside 높은 종목부터."""
    by_stock = {}
    for r in reports:
        by_stock.setdefault(r["code"], []).append(r)

    def up(r):
        return r["upside"] if r["upside"] is not None else float("-inf")

    def move(r):
        return abs(r["tp_pct"]) if r.get("tp_pct") is not None else 0

    sections = []
    for key, title in SECTIONS:
        stocks = [sorted(reps, key=lambda r: (-move(r), -up(r), r["broker"]))
                  for reps in by_stock.values() if _stock_section(reps, watch) == key]
        if key in CHANGE_SECTIONS:
            stocks.sort(key=lambda reps: (-max(move(r) for r in reps), -max(up(r) for r in reps)))
        else:
            stocks.sort(key=lambda reps: (-max(up(r) for r in reps), reps[0]["name"]))
        if stocks:
            sections.append({"key": key, "title": title, "stocks": stocks,
                             "count": sum(len(s) for s in stocks)})
    return sections


def stock_label(reps):
    """'LG전자 ▲+16.7% (8건)' 처럼 한 종목을 한 줄로."""
    r = max(reps, key=lambda r: abs(r["tp_pct"]) if r.get("tp_pct") is not None else -1)
    mark = r["tp_change"] if r["tp_change"] in ("▲", "▼", "N") else ""
    ops = [x for x in reps if x["op_change"] in ("▲", "▼")]
    text = reps[0]["name"]
    if ops:
        text += " 의견" + "/".join(f"{x['op_change']}{x['opinion']}" for x in ops)
    if mark:
        text += f" {mark}" + (f"{r['tp_pct']:+.0f}%" if r.get("tp_pct") is not None else "")
    if len(reps) > 1:
        text += f" ({len(reps)}건)"
    return text


DIGEST = [("watch", "관심 종목"), ("opinion", "투자의견 변경"), ("up", "목표가 상향"), ("new", "신규 커버리지"),
          ("mixed", "증권사별 엇갈림"), ("down", "목표가 하향")]


def digest(sections):
    """PDF 첫 페이지·텔레그램 맨 위에 넣을 '오늘의 핵심' — (제목, [종목 한 줄 요약…])."""
    by_key = {sec["key"]: sec for sec in sections}
    out = []
    for key, label in DIGEST:
        if key in by_key:
            out.append((label, [stock_label(reps) for reps in by_key[key]["stocks"]]))
    keep = by_key.get("keep")
    if keep:
        busy = [reps for reps in keep["stocks"] if len(reps) >= 3]
        if busy:
            out.append(("여러 증권사가 다룬 종목(유지)", [stock_label(r) for r in busy]))
    return out
