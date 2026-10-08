"""한경컨센서스 기업 리포트 목록 (작성자, 요약 bullet 포함)."""
import re

from bs4 import BeautifulSoup

from common import get, to_int

LIST_URL = "https://consensus.hankyung.com/analysis/list"
BASE = "https://consensus.hankyung.com"


def fetch(sdate, edate=None):
    """sdate~edate(YYYY-MM-DD) 사이의 기업 리포트를 모두 가져온다."""
    edate = edate or sdate
    reports, page = [], 1
    while True:
        r = get(LIST_URL, params={
            "skinType": "business", "sdate": sdate, "edate": edate,
            "pagenum": 200, "now_page": page,
        })
        soup = BeautifulSoup(r.content, "html.parser")
        rows = soup.select("table tbody tr")
        parsed = [p for p in (_parse_row(tr) for tr in rows) if p]
        reports += parsed
        if len(rows) < 200:
            break
        page += 1
    return reports


def _parse_row(tr):
    td = tr.find_all("td")
    if len(td) < 6 or not td[1].a:
        return None
    full_title = td[1].a.get_text(strip=True)
    m = re.match(r"^(.*?)\((\d{6})\)\s*(.*)$", full_title)
    if not m:
        return None
    name, code, title = m.group(1).strip(), m.group(2), m.group(3).strip()
    bullets = [li.get_text(" ", strip=True) for li in td[1].select("ul li")]
    bullets = [b for b in bullets if b]
    idx = re.search(r"report_idx=(\d+)", td[1].a["href"])
    return {
        "source": "hankyung",
        "ids": [f"hk:{idx.group(1)}"] if idx else [f"hk:{code}:{td[0].get_text(strip=True)}:{title}"],
        "date": td[0].get_text(strip=True),
        "code": code,
        "name": name,
        "title": title,
        "target": to_int(td[2].get_text(strip=True)),
        "opinion": "" if "없음" in td[3].get_text() else td[3].get_text(strip=True),
        "author": re.sub(r"\s*,\s*", ",", td[4].get_text(strip=True)),
        "broker": td[5].get_text(strip=True),
        "bullets": bullets,
        "pdf": BASE + td[1].a["href"],
    }
