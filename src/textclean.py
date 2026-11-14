"""보내는 글자를 한글·영어로만 제한한다.

리포트 원문·글자인식 결과에 섞여 들어오는 한자, 일본어, 러시아어 등 다른 나라 글자를 지운다.
숫자, 문장부호, 우리가 쓰는 기호(▲▼◆★·⚠ 등)와 이모지는 그대로 둔다.
텔레그램 메시지(notify_telegram)와 PDF(render_pdf)에 들어가는 모든 글자에 적용된다.
"""
import re
import unicodedata

_FULLWIDTH = {c: c - 0xFEE0 for c in range(0xFF01, 0xFF5F)}   # 전각 Ａ１％ → A1%


def _allowed(c):
    return c.isascii() or "가" <= c <= "힣" or "ㄱ" <= c <= "ㆎ"   # 영어·한글 완성형·자모


def ko_en(text):
    if not isinstance(text, str):
        return text
    out = []
    for c in text.translate(_FULLWIDTH):
        if _allowed(c):
            out.append(c)
            continue
        cat = unicodedata.category(c)
        if cat[0] == "L" or cat[0] == "M":                       # 다른 나라 글자(또는 그 위의 점·획)
            base = unicodedata.normalize("NFKD", c)[0]
            if base.isascii() and base.isalpha():                # é → e 처럼 악센트만 뗀 영어 글자는 살린다
                out.append(base)
            continue
        out.append(c)                                            # 기호·문장부호·이모지
    cleaned = "".join(out)
    if cleaned == text:
        return text
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)                 # 글자를 지운 자리에 남은 겹친 빈칸
    cleaned = re.sub(r"[ \t]+([,.)\]])", r"\1", cleaned)        # "中國 , " → ","
    return "\n".join(line.strip(" \t") for line in cleaned.split("\n"))
