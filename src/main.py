"""매일 아침 기업리포트 요약 PDF를 만들고 텔레그램으로 보낸다.

사용 예)
  python src/main.py                      # 오늘(한국시간) 리포트
  python src/main.py --date 2026-10-07 --no-send
  python src/main.py --bootstrap          # 최초 1회: 과거 이력 수집
  python src/main.py --only-if-new        # 이미 보낸 날엔 새 리포트가 늘었을 때만 다시 전송
"""
import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timedelta, timezone

import build
import editions
import fetch_brokers
import fetch_hankyung
import fetch_naver
import history
import monitor
import notify_telegram
import render_pdf
import watchlist

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SENT_PATH = os.path.join(ROOT, "data", "sent.json")
KST = timezone(timedelta(hours=9))


def load_sent():
    if os.path.exists(SENT_PATH):
        with open(SENT_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_sent(sent):
    with open(SENT_PATH, "w", encoding="utf-8") as f:
        json.dump(sent, f, ensure_ascii=False, indent=1)


ICONS = {"관심 종목": "★", "투자의견 변경": "◆", "목표가 상향": "▲", "신규 커버리지": "N",
         "증권사별 엇갈림": "▲▼", "목표가 하향": "▼"}


def caption(sections, total, date, warns=()):
    """텔레그램 메시지: 경고 → 오늘의 핵심(관심 종목·의견 변경·상향·하향…) 순서."""
    lines = [f"📊 기업리포트 요약 {date} (총 {total}건)"]
    if warns:
        lines += [""] + [f"⚠️ {w}" for w in warns]
    for label, items in build.digest(sections):
        lines += ["", f"{ICONS.get(label, '·')} {label} ({len(items)})", ", ".join(items)]
    checks = sum(bool(r.get("notes")) for sec in sections for reps in sec["stocks"] for r in reps)
    if checks:
        lines += ["", f"⚠ 근거가 엇갈려 확인이 필요한 리포트 {checks}건 (PDF에 표시)"]
    text = "\n".join(lines)
    return text if len(text) <= 4000 else text[:3990] + "… (PDF 참고)"


def run(date, send, only_if_new):
    mode = "supplement" if only_if_new else "main"
    state = editions.load()
    lookback = (datetime.fromisoformat(date) - timedelta(days=editions.LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    since = max(lookback, state["start"]) if state["start"] else date
    skip = editions.already_sent_ids(state, date)

    hk = fetch_hankyung.fetch(since, date)
    nv = fetch_naver.fetch(since, date, skip=skip)
    extra, broker_status = fetch_brokers.fetch_all(since, date, skip=skip)
    print("증권사 홈페이지:", ", ".join(f"{k} {v}" for k, v in broker_status.items()))
    reports = editions.select(build.add_broker_reports(build.merge(hk, nv), extra), state, date)
    carried = sum(r["carried"] for r in reports)
    print(f"한경 {len(hk)}건, 네이버 {len(nv)}건 (기간 {since}~{date}) → 이번 판 {len(reports)}건 (전일 늦게 올라온 것 {carried}건)")

    stats = {"hankyung": sum(r["date"] == date for r in hk), "naver": sum(r["date"] == date for r in nv),
             "included": len(reports), "carried": carried, "pdf_read": 0, "pdf_judged": 0,
             "brokers": broker_status}

    if not reports:
        warns = monitor.check(stats, date, mode)
        print("리포트가 없습니다 (휴일이거나 아직 올라오지 않음).", *warns, sep="\n")
        if send:
            monitor.log(stats, date, mode, warns)
            if warns and notify_telegram.enabled():
                notify_telegram.send_message(f"⚠️ 기업리포트 요약 {date}\n" + "\n".join(warns))
        return

    reports = build.analyze_pdfs(reports)
    stats["pdf_read"] = sum(bool(r.get("pdf_read")) for r in reports if not r.get("no_pdf"))
    stats["pdf_total"] = sum(not r.get("no_pdf") for r in reports)
    stats["pdf_judged"] = sum(bool(r.get("pdf_tp_change")) for r in reports)
    print(f"PDF 읽음 {stats['pdf_read']}/{len(reports)}건, 핵심문장 요약 "
          f"{sum(r.get('summary_from') == 'pdf' for r in reports)}건, PDF로 목표가 방향 판정 {stats['pdf_judged']}건")

    hist_rows = history.load()
    reports = build.enrich(reports, hist_rows, date)
    watch = watchlist.load()
    sections = build.sort_sections(reports, watch)
    warns = monitor.check(stats, date, mode)
    for w in warns:
        print("⚠️", w)

    out_dir = os.path.join(ROOT, "reports")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{date.replace('-', '')} 기업리포트 요약.pdf")
    render_pdf.render(sections, len(reports), date, out_path, build.digest(sections))
    print(f"PDF 생성: {out_path} ({len(reports)}건)")

    history.save(hist_rows + [history.to_row(r) for r in reports])
    if not send:
        return          # 시험 실행: 발송 기록·판 기록을 남기지 않는다

    monitor.log(stats, date, mode, warns)
    editions.save(editions.mark(state, reports, date))
    sent = load_sent()
    if only_if_new and sent.get(date, 0) >= len(reports):
        print("새로 추가된 리포트가 없어 전송을 건너뜁니다.")
        return
    if notify_telegram.enabled():
        text = caption(sections, len(reports), date, warns)
        if sent.get(date):
            text = "🔄 보충본 (아침 이후 추가된 리포트 포함)\n" + text
        notify_telegram.send_message(text)            # 요약은 일반 메시지로(길이 제한 4,096자)
        notify_telegram.send_document(out_path, f"{date} 기업리포트 요약 PDF ({len(reports)}건)")
        sent[date] = len(reports)
        save_sent(sent)
        print("텔레그램 전송 완료")
    else:
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID가 없어 전송을 건너뜁니다.")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now(KST).strftime("%Y-%m-%d"))
    ap.add_argument("--no-send", action="store_true")
    ap.add_argument("--only-if-new", action="store_true")
    ap.add_argument("--bootstrap", action="store_true")
    args = ap.parse_args()

    if args.bootstrap:
        print(f"이력 {history.bootstrap()}건 저장")
        return

    try:
        run(args.date, not args.no_send, args.only_if_new)
    except Exception:
        traceback.print_exc()
        if not args.no_send and notify_telegram.enabled():
            notify_telegram.send_message(f"⚠️ 기업리포트 요약 {args.date} 생성 실패\n{traceback.format_exc()[-1500:]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
