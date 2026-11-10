"""텔레그램 봇으로 PDF/메시지 전송. 토큰이 없으면 조용히 건너뛴다.

- TELEGRAM_CHAT_ID   : 나에게 오는 개인 채팅 (관심 종목·경고 포함 전체본)
- TELEGRAM_CHANNEL_ID: 공유용 채널(선택). 공개 채널은 "@채널주소", 비공개 채널은 "-100…" 숫자.
                       관심 종목 구역과 수집 경고는 빼고 보낸다(main.py).
"""
import os

import requests

API = "https://api.telegram.org/bot{token}/{method}"


def _token():
    return os.environ.get("TELEGRAM_BOT_TOKEN")


def _chat():
    return os.environ.get("TELEGRAM_CHAT_ID")


def channel():
    return (os.environ.get("TELEGRAM_CHANNEL_ID") or "").strip()


def enabled():
    return bool(_token() and _chat())


def channel_enabled():
    return bool(_token() and channel())


def send_document(path, caption="", chat=None):
    with open(path, "rb") as f:
        r = requests.post(API.format(token=_token(), method="sendDocument"),
                          data={"chat_id": chat or _chat(), "caption": caption[:1024]},
                          files={"document": (os.path.basename(path), f, "application/pdf")},
                          timeout=60)
    r.raise_for_status()


def send_message(text, chat=None):
    r = requests.post(API.format(token=_token(), method="sendMessage"),
                      data={"chat_id": chat or _chat(), "text": text[:4096]}, timeout=30)
    r.raise_for_status()
