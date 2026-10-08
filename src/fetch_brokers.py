"""네이버·한경에 올라오지 않는 증권사 리포트를 각 증권사 홈페이지에서 가져온다.

- KB증권: 리서치 메인이 쓰는 목록 API (의견·목표가·요약 포함)
- NH투자증권: 리서치 목록 + 요약보기 API (요약 글에서 의견·목표가를 읽음)
- 한국투자증권: 리서치 목록 + 상세 페이지 (소제목·본문에서 의견·목표가를 읽음)
- 다올투자증권: 리서치 목록 + 공개 요약 이미지 (글자 인식으로 의견·목표가·요약을 읽음)

※ 개인 열람용. NH·한국투자는 사이트가 자동 수집을 원치 않으므로(robots.txt) 하루 몇 번,
  천천히 요청하고, 고객 전용 PDF는 받지 않는다. 결과물을 공개 저장소 등에 재배포하지 않는다.
"""
import base64
import html
import io
import json
import os
import re
import shutil
import time

import requests
from bs4 import BeautifulSoup

import pdf_changes
from common import HEADERS, to_int

SLOW = 1.2          # NH·한국투자·다올 요청 간격(초)


def _session():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def _report(broker, rid, date, code, name, title, author="", target=None, opinion="", bullets=(),
            link="", text="", **extra):
    """공통 형식. text(요약·본문)가 있으면 목표가 방향·의견 변동도 판정해 둔다."""
    r = {
        "source": broker, "ids": [rid], "date": date, "code": code, "name": name.strip(),
        "title": title.strip(), "author": author, "broker": broker,
        "target": target, "opinion": opinion, "bullets": [b for b in bullets if b], "pdf": link,
        "no_pdf": True,                 # 이 증권사들은 PDF를 받지 않는다
    }
    if text:
        r["pdf_read"] = True
        r["pdf_tp_change"], r["pdf_prev_target"] = pdf_changes.target_change_detail(text, target)
        r["pdf_op_change"] = pdf_changes.opinion_change(text)
        r["pdf_tp_pct"] = pdf_changes.target_pct(text)
    r.update(extra)
    return r


# ── KB증권 ──────────────────────────────────────────────────────────────────
KB_LIST = "https://rc.kbsec.com/ajax/categoryReportList.json"
KB_FOLDERS = ("37", "38")          # 37 산업/기업, 38 스몰캡
KB_OP_CHANGE = {"유지": "=", "상향": "▲", "하향": "▼", "신규": "N"}


def kb_list(since, until):
    s = _session()
    rows = []
    for folder in KB_FOLDERS:
        page = 1
        while True:
            body = {"pageNo": page, "pageSize": 100, "registdateFrom": since.replace("-", ""),
                    "registdateTo": until.replace("-", ""), "templateid": "", "lowTempId": "",
                    "folderid": folder, "callGbn": "RCLIST"}
            r = s.post(KB_LIST, json=body, timeout=30)
            r.raise_for_status()
            data = r.json()
            got = (data.get("response") or data).get("reportList") or []
            rows += got
            if len(got) < 100:
                break
            page += 1
            time.sleep(0.5)
    return rows


def fetch_kb(since, until, skip=()):
    out = []
    for it in kb_list(since, until):
        code = it.get("stkCd")
        if not code:                 # 산업·전략 리포트는 제외
            continue
        rid = f"kb:{it['documentid']}"
        if rid in skip:
            continue
        name = re.sub(r"\s*\(\d{6}\)\s*$", "", it.get("docTitle") or "")
        bullets = [re.sub(r"^[-·•]\s*", "", l).strip() for l in (it.get("docDetail") or "").split("\n")]
        r = _report("KB증권", rid, it["publicDate"], code, name, it.get("docTitleSub") or name,
                    author=it.get("analystNm") or "", target=to_int((it.get("tp") or "").split(".")[0]),
                    opinion=it.get("recomm") or "", bullets=bullets[:4], link=it.get("urlLinkH") or "",
                    history_complete=True)      # KB는 목록에 모든 리포트가 있어 이력 비교가 정확
        if it.get("recommChg") in KB_OP_CHANGE:
            r["pdf_op_change"] = KB_OP_CHANGE[it["recommChg"]]
        out.append(r)
    return out


# ── NH투자증권 ───────────────────────────────────────────────────────────────
NH_PAGE = "https://www.nhsec.com/research/boardList.action?rsh_ppr_dit_cd=01"
NH_API = "https://www.nhsec.com/research/boardCommonTrAjax.action"


def _nh_call(s, data):
    time.sleep(SLOW)
    r = s.post(NH_API, data={"output": "json", **data}, headers={"Referer": NH_PAGE}, timeout=30)
    r.raise_for_status()
    return json.loads(r.content.decode("cp949", "ignore"), strict=False)["DATA"].get("RESPONSE")


def _nh_session():
    s = _session()
    s.get(NH_PAGE, timeout=30)          # 세션 쿠키가 있어야 응답한다
    return s


def fetch_nh(since, until, skip=()):
    s = _nh_session()
    base = {"trName": "H3211", "rsh_ppr_dit_cd": "01", "rsh_ppr_dru_dt_st": until.replace("-", ""),
            "rsh_ppr_dru_dt_ed": since.replace("-", ""), "rsh_ppr_no": "", "rsh_ppr_dru_tm_st": ""}
    rows, seen, req = [], set(), {**base, "isNext": "false"}
    for _ in range(30):
        resp = _nh_call(s, req)
        for retry in range(3):          # 가끔 빈 응답(Null-Data)을 준다 → 쉬었다가 새 세션으로 재시도
            if resp is not None:
                break
            time.sleep(3 * (retry + 1))
            s = _nh_session()
            resp = _nh_call(s, req)
        got = (resp or {}).get("H3211OutBlock2", {}).get("ROW", [])
        rows += [g for g in got if g["rsh_ppr_no"] not in seen]
        seen |= {g["rsh_ppr_no"] for g in got}
        if len(got) <= 10:              # 한 번에 10건 + 다음 시작점 1건
            break
        last = got[10]
        req = {**base, "isNext": "true", "rsh_ppr_no": last["rsh_ppr_no"],
               "rsh_ppr_dru_dt_st": last["rsh_ppr_dru_dt"], "rsh_ppr_dru_tm_st": last["rsh_ppr_dru_tm"]}

    out = []
    for it in rows:
        code = it.get("rsh_ppr_iem_cd_pcl") or ""
        if it.get("rsh_ppr_ser_cd_nm") != "기업" or not re.fullmatch(r"[0-9A-Z]{6}", code):
            continue
        rid = f"nh:{it['rsh_ppr_no']}"
        if rid in skip:
            continue
        m = re.match(r"\[(.+?)\]\s*(.*)", it["rsh_ppr_til_cts"])
        name, title = (m.group(1), m.group(2)) if m else ("", it["rsh_ppr_til_cts"])
        resp = _nh_call(s, {"trName": "H3212", "rsh_ppr_no": it["rsh_ppr_no"]})
        if resp is None:
            time.sleep(3)
            resp = _nh_call(s, {"trName": "H3212", "rsh_ppr_no": it["rsh_ppr_no"]})
        row = ((resp or {}).get("H3212OutBlock1", {}).get("ROW") or [{}])[0]
        body = html.unescape(html.unescape(row.get("rsh_ppr_cts", "")))   # 두 번 감싸져 있음
        heads = [BeautifulSoup(h, "html.parser").get_text(" ", strip=True).lstrip("▶ ").strip()
                 for h in re.findall(r"<span[^>]*font-weight:\s*bold[^>]*>(.*?)</span>", body, re.S)]
        text = BeautifulSoup(body, "html.parser").get_text(" ", strip=True)
        d = it["rsh_ppr_dru_dt"]
        out.append(_report("NH투자증권", rid, f"{d[:4]}-{d[4:6]}-{d[6:]}", code,
                           row.get("rsh_ppr_iem_nm_pcl") or name, title,
                           author=it.get("rsh_ppr_dru_emp_fnm", ""),
                           target=pdf_changes.find_target(text), opinion=pdf_changes.find_opinion(text),
                           bullets=[h for h in heads if len(h) >= 4][:3], link=NH_PAGE, text=text))
    return out


# ── 한국투자증권 ─────────────────────────────────────────────────────────────
KIS_BASE = "https://securities.koreainvestment.com"
KIS_PAGE = KIS_BASE + "/main/research/research/Search.jsp"


def fetch_kis(since, until, skip=()):
    s = _session()
    items = []
    for page in range(1, 8):
        time.sleep(SLOW)
        r = s.post(KIS_PAGE + "?cmd=TF07ae000001_List_v2_single", headers={"Referer": KIS_PAGE},
                   data={"tab1Name": "report", "tab2Name": "industry", "currentPage": page,
                         "searchColumn": "all", "searchValue": ""}, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "html.parser")
        lis = soup.select("a.view_con")
        oldest = None
        for a in lis:
            tit = a.select_one(".body_tit")
            info = a.select_one(".tit_info")
            link = re.search(r"goDetail\('([^']+)'", a.get("onclick", ""))
            if not (tit and info and link):
                continue
            dm = re.search(r"(\d{4})\.(\d{2})\.(\d{2})", info.get_text())
            date = f"{dm.group(1)}-{dm.group(2)}-{dm.group(3)}" if dm else ""
            oldest = date if not oldest or date < oldest else oldest
            if since <= date <= until:
                items.append({"title": tit.get_text(" ", strip=True), "date": date, "url": link.group(1),
                              "author": (info.select_one("em").get_text(strip=True) if info.select_one("em") else "")})
        if not lis or (oldest and oldest < since):
            break

    out = []
    for it in items:
        m = re.match(r"(.+?)\s*\((\d{6})\)\s*[:\-–]?\s*(.*)", it["title"])
        if not m or it["title"].startswith("AIR"):   # 산업·전략 리포트, AI 자동작성(AIR) 리포트는 제외
            continue
        rid = "kis:" + (re.search(r"id=(\d+)", it["url"]).group(1) if re.search(r"id=(\d+)", it["url"]) else it["title"])
        if rid in skip:
            continue
        time.sleep(SLOW)
        r = s.get(KIS_BASE + it["url"], headers={"Referer": KIS_PAGE}, timeout=30)
        soup = BeautifulSoup(r.content, "html.parser")
        heads = [h.get_text(" ", strip=True) for h in soup.select(".v_info_head")]
        if not heads:                   # 산업 리포트 속 종목 요약: 짧은 문장 몇 줄만 있음
            box = soup.select_one(".v_info_body")
            heads = [d.get_text(" ", strip=True) for d in box.find_all("div", recursive=False)] if box else []
        body = soup.select_one(".v_info_con") or soup
        text = body.get_text(" ", strip=True)
        out.append(_report("한국투자증권", rid, it["date"], m.group(2), m.group(1), m.group(3),
                           author=it["author"], target=pdf_changes.find_target(text),
                           opinion=pdf_changes.find_opinion(text), bullets=heads[:3],
                           link=KIS_BASE + it["url"], text=text))
    return out


# ── 다올투자증권 ─────────────────────────────────────────────────────────────
DAOL_BASE = "https://www.daolsecurities.com"
DAOL_LIST = DAOL_BASE + "/research/article/common.jspx?cmd=list&templet-bypass=true"
DAOL_PAGE = DAOL_BASE + "/research/article/common.jspx?rGubun=I01&sctrGubun=&web=0"


def _tesseract():
    import pytesseract
    cmd = shutil.which("tesseract") or r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    pytesseract.pytesseract.tesseract_cmd = cmd
    local = os.path.expanduser("~/tessdata")   # 관리자 권한 없이 받은 한국어 데이터(윈도우)
    if os.path.exists(os.path.join(local, "kor.traineddata")) and "TESSDATA_PREFIX" not in os.environ:
        os.environ["TESSDATA_PREFIX"] = local
    return pytesseract


OCR_FIX = [(r"[먹역]원", "억원"), (r"수믹", "수익"), (r"증믹", "증익"), (r"분격", "본격"), (r"냉극", "냉각"),
           (r"\b([1-4])0(2\d)8\b", r"\1Q\2E"), (r"\b([1-4])0(2\d)([EFP]?)\b", r"\1Q\2\3")]


def _fix_ocr(t):
    for a, b in OCR_FIX:
        t = re.sub(a, b, t)
    return t


def daol_read_image(img_bytes):
    """요약 이미지에서 (투자의견, 목표주가, 직전 목표주가, 변동, 요약 문장들)을 읽는다.
    왼쪽 표: '투자의견 BUY BUY 유지 / 적정주가 270,000 240,000 상향'
    오른쪽 Pitch 문단: 핵심 요약 (글자 인식이라 오탈자가 있을 수 있다)"""
    from PIL import Image
    tess = _tesseract()
    im = Image.open(io.BytesIO(img_bytes)).convert("L")
    w, h = im.size

    left = im.crop((0, int(h * 0.2), int(w * 0.42), int(h * 0.42)))
    table = tess.image_to_string(left.resize((left.width * 3, left.height * 3)), lang="kor+eng", config="--psm 6")
    word = {"유지": "=", "상향": "▲", "하향": "▼", "신규": "N"}
    op = re.search(r"[투두루]자\s*의견\s+([A-Za-z가-힣]+)\s+(\S+)\s+(유지|상향|하향|신규)", table)
    tp = re.search(r"(?:적정|목표)\s*주가\s+([0-9][0-9,.]{2,})\s+(\S+)(?:\s+(유지|상향|하향|신규))?", table)

    # 오른쪽 단에서 'Pitch'와 'Rationale' 제목 위치를 찾아 그 사이만 읽는다
    right = im.crop((int(w * 0.42), int(h * 0.12), w, int(h * 0.75)))
    big = right.resize((right.width * 3, right.height * 3))
    data = tess.image_to_data(big, lang="eng", config="--psm 6", output_type=tess.Output.DICT)
    ys = {t.strip().lower(): data["top"][i] for i, t in enumerate(data["text"]) if t.strip()}
    top = next((v for k, v in ys.items() if k.startswith("pitch")), None)
    bottom = next((v for k, v in ys.items() if k.startswith("rationale")), None)
    sents = []
    if top is not None and bottom is not None and bottom > top:
        para = big.crop((0, top + 45, big.width, bottom - 5))
        txt = tess.image_to_string(para, lang="kor", config="--psm 6")
        joined = " ".join(l.strip() for l in txt.split("\n") if l.strip())
        sents = [_fix_ocr(x.strip(" .")) for x in re.split(r"(?<=[.다망])\s+", joined) if len(x.strip()) > 12][:3]
    prev = to_int(tp.group(2)) if tp and re.fullmatch(r"[0-9][0-9,.]{2,}", tp.group(2)) else None
    return {
        "opinion": op.group(1) if op else "",
        "op_change": word.get(op.group(3)) if op else None,
        "target": to_int(tp.group(1)) if tp else None,
        "prev_target": prev,
        "tp_word": tp.group(3) if tp else None,
        "bullets": sents,
    }


def fetch_daol(since, until, skip=()):
    s = _session()
    rows = []
    for page in range(1, 6):
        time.sleep(SLOW)
        r = s.post(DAOL_LIST, headers={"Referer": DAOL_PAGE}, timeout=30, data={
            "curPage": page, "rGubun": "I01", "sctrGubun": "", "web": 0, "hts": "", "bbSeq": "",
            "filepath": "", "attaFileNm": "", "startDate": since.replace("-", "/"),
            "endDate": until.replace("-", "/"), "searchSelect": 0, "searchNm1": "", "searchNm2": ""})
        r.raise_for_status()
        trs = BeautifulSoup(r.content, "html.parser").select("tr")
        rows += trs
        if len(trs) < 10:
            break

    out = []
    for tr in rows:
        td = tr.find_all("td")
        a = tr.select_one("a.del_w")
        if len(td) < 2 or not a:
            continue
        m = re.match(r"(.+?)\s*\((\d{6})\)\s*-?\s*(.*)", a.get("title") or a.get_text(strip=True))
        dl = re.search(r"fn_download_before\('([^']+)',\s*'([^']+)',\s*'(\d+)'\)", a.get("href", ""))
        if not (m and dl):
            continue
        rid = f"daol:{dl.group(3)}"
        if rid in skip:
            continue
        date = td[0].get_text(strip=True).replace("/", "-")
        img_url = (f"{DAOL_BASE}/common/download.jspx?path=/attach_file/RESEARCH/{dl.group(3)}/images/"
                   f"{dl.group(2).rsplit('.', 1)[0]}.jpg")
        info = {}
        try:
            time.sleep(SLOW)
            img = s.get(img_url, headers={"Referer": DAOL_PAGE}, timeout=30)
            if img.ok and img.content[:3] == b"\xff\xd8\xff":
                info = daol_read_image(img.content)
        except Exception:
            info = {}
        r = _report("다올투자증권", rid, date, m.group(2), m.group(1), m.group(3),
                    target=info.get("target"), opinion=info.get("opinion", ""),
                    bullets=info.get("bullets", []), link=DAOL_PAGE, ocr=bool(info))
        if info:
            r["pdf_read"] = True
            if info.get("op_change"):
                r["pdf_op_change"] = info["op_change"]
            if info.get("target") and info.get("prev_target"):
                t, p = info["target"], info["prev_target"]
                r["pdf_tp_change"] = "▲" if t > p else "▼" if t < p else "="
                r["pdf_prev_target"] = p
            elif info.get("tp_word"):
                r["pdf_tp_change"] = {"유지": "=", "상향": "▲", "하향": "▼", "신규": "N"}[info["tp_word"]]
        out.append(r)
    return out


FETCHERS = {"KB증권": fetch_kb, "NH투자증권": fetch_nh, "한국투자증권": fetch_kis, "다올투자증권": fetch_daol}


def fetch_all(since, until, skip=()):
    """증권사 하나가 실패해도 나머지는 계속한다. (결과, {증권사: 건수 또는 오류})"""
    reports, status = [], {}
    for name, fn in FETCHERS.items():
        try:
            got = fn(since, until, skip)
            reports += got
            status[name] = len(got)
        except Exception as e:
            status[name] = f"오류: {type(e).__name__}"
    return reports, status
