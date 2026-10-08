"""HTML 표를 만들어 크롬(Playwright)으로 PDF로 인쇄한다."""
import os

import pymupdf

from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright

ROOT = os.path.join(os.path.dirname(__file__), "..")


def render(sections, total, date, out_path, digest=()):
    env = Environment(loader=FileSystemLoader(os.path.join(ROOT, "templates")), autoescape=True)
    html = env.get_template("report.html").render(sections=sections, total=total, digest=digest, date_dot=date.replace("-", "."),
        carried=any(r.get("carried") for sec in sections for reps in sec["stocks"] for r in reps))

    html_path = os.path.splitext(out_path)[0] + ".html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html, wait_until="load")
        page.pdf(path=out_path, format="A4", landscape=True, print_background=True,
                 prefer_css_page_size=True)
        browser.close()
    os.remove(html_path)
    _drop_blank_pages(out_path)
    return out_path


def _drop_blank_pages(path):
    """표가 페이지 끝에 딱 맞으면 크롬이 빈 페이지를 하나 더 붙이므로 지운다."""
    doc = pymupdf.open(path)
    blank = [i for i, page in enumerate(doc) if not page.get_text().strip()]
    if blank and len(blank) < len(doc):
        doc.delete_pages(blank)
        doc.save(path + ".tmp")
        doc.close()
        os.replace(path + ".tmp", path)
    else:
        doc.close()
