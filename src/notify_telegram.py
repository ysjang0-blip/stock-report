"""텔레그램 봇으로 PDF/메시지 전송. 토큰이 없으면 조용히 건너뛴다."""
import os

import requests

API = "https://api.telegram.org/bot{token}/{method}"


def _creds():
    return os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")


def enabled():
    token, chat = _creds()
    return bool(token and chat)


def send_document(path, caption=""):
    token, chat = _creds()
    with open(path, "rb") as f:
        r = requests.post(API.format(token=token, method="sendDocument"),
                          data={"chat_id": chat, "caption": caption[:1024]},
                          files={"document": (os.path.basename(path), f, "application/pdf")},
                          timeout=60)
    r.raise_for_status()


def send_message(text):
    token, chat = _creds()
    r = requests.post(API.format(token=token, method="sendMessage"),
                      data={"chat_id": chat, "text": text[:4096]}, timeout=30)
    r.raise_for_status()
