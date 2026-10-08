"""내 관심 종목 목록. 보유 종목이 드러나지 않도록 저장소에는 올리지 않는다.

- PC: 프로젝트 폴더의 watchlist.txt (한 줄에 하나, 종목명 또는 6자리 코드, # 뒤는 메모)
- GitHub: 저장소 Secrets의 WATCHLIST (쉼표나 줄바꿈으로 구분)
"""
import os
import re

PATH = os.path.join(os.path.dirname(__file__), "..", "watchlist.txt")


def _norm(s):
    return re.sub(r"\s+", "", s).upper()


def load():
    raw = os.environ.get("WATCHLIST", "")
    if not raw and os.path.exists(PATH):
        with open(PATH, encoding="utf-8") as f:
            raw = f.read()
    items = set()
    for line in re.split(r"[,\n]", raw):
        line = line.split("#", 1)[0].strip()
        if line:
            items.add(_norm(line))
    return items


def matches(report, watch):
    return bool(watch) and (report["code"] in watch or _norm(report["name"]) in watch)
