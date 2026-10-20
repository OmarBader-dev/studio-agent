"""Telegram: messages and pictures to you, and the commands you send the bot.
Without a bot token, messages are just printed (useful for local test runs)."""
import html
import json
import pathlib

import requests

API = "https://api.telegram.org/bot{token}/{method}"


def esc(text):
    return html.escape(str(text or ""), quote=False)


def link(url, text):
    """An HTML link for Telegram; plain text when the address isn't a web link."""
    if not str(url or "").lower().startswith(("https://", "http://")):
        return esc(text)
    return f'<a href="{html.escape(url, quote=True)}">{esc(text)}</a>'


def _creds(cfg):
    return cfg.secret("TELEGRAM_BOT_TOKEN"), cfg.secret("TELEGRAM_CHAT_ID")


def _call(token, method, timeout=30, **kwargs):
    try:
        r = requests.post(API.format(token=token, method=method), timeout=timeout, **kwargs)
    except requests.RequestException as e:
        print("Telegram error:", e)
        return None
    if r.status_code != 200:
        print("Telegram error:", r.status_code, r.text[:300])
        return None
    return r.json().get("result")


def _offline(kind, text):
    """Without a bot, messages go to the run's log, except in a public repository, where logs are public."""
    from .settings import public_repo
    print(f"[telegram {kind}]", "(set up the Telegram secrets to get this; not shown in public logs)"
          if public_repo() else text)


def telegram(cfg, text):
    token, chat = _creds(cfg)
    if not token or not chat:
        _offline("message", text)
        return False
    if len(text) > 4000:
        text = text[:3990] + "…"
    return _call(token, "sendMessage", json={"chat_id": chat, "text": text, "parse_mode": "HTML",
                                              "disable_web_page_preview": True}) is not None


def send_to(cfg, chat_id, text):
    """A message to a given chat (before TELEGRAM_CHAT_ID is set, e.g. to tell you what it is)."""
    token = cfg.secret("TELEGRAM_BOT_TOKEN")
    return bool(token) and _call(token, "sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}) is not None


def photo(cfg, path, caption=""):
    """Send one picture (a design) with a short HTML caption."""
    token, chat = _creds(cfg)
    if not token or not chat:
        _offline("photo", f"{path} {caption}")
        return False
    with open(path, "rb") as f:
        return _call(token, "sendPhoto", timeout=60, data={"chat_id": chat, "caption": caption[:1000],
                                                           "parse_mode": "HTML"},
                     files={"photo": (pathlib.Path(path).name, f)}) is not None


def video(cfg, path, caption="", cover=None):
    """Send a short video (a Reel) that plays right in the chat. Telegram makes the preview itself."""
    token, chat = _creds(cfg)
    if not token or not chat:
        _offline("video", f"{path} {caption}")
        return False
    files = {"video": (pathlib.Path(path).name, open(path, "rb"))}
    try:
        return _call(token, "sendVideo", timeout=120, data={
            "chat_id": chat, "caption": caption[:1000], "parse_mode": "HTML", "supports_streaming": "true",
            "width": 1080, "height": 1920}, files=files) is not None
    finally:
        for f in files.values():
            f[1].close()


def album(cfg, paths, caption=""):
    """Send up to 10 pictures as one album. The caption goes on the first picture."""
    token, chat = _creds(cfg)
    paths = [p for p in paths if p][:10]
    if not token or not chat:
        _offline("album", f"{paths} {caption}")
        return False
    if len(paths) == 1:
        return photo(cfg, paths[0], caption)
    files, media = {}, []
    for i, p in enumerate(paths):
        files[f"p{i}"] = (pathlib.Path(p).name, open(p, "rb"))
        item = {"type": "photo", "media": f"attach://p{i}"}
        if i == 0 and caption:
            item.update(caption=caption[:1000], parse_mode="HTML")
        media.append(item)
    try:
        return _call(token, "sendMediaGroup", timeout=120, data={"chat_id": chat, "media": json.dumps(media)},
                     files=files) is not None
    finally:
        for f in files.values():
            f[1].close()


def chat_ids(cfg):
    """Chats that have messaged your bot. Send your bot any message first, then run this."""
    cfg.require("TELEGRAM_BOT_TOKEN")
    r = requests.get(API.format(token=cfg.secret("TELEGRAM_BOT_TOKEN"), method="getUpdates"), timeout=20)
    found = {}
    for update in r.json().get("result", []):
        chat = (update.get("message") or {}).get("chat") or {}
        if chat.get("id"):
            found[chat["id"]] = chat.get("first_name") or chat.get("title") or ""
    return found


def messages(cfg, store):
    """New messages you sent the bot since last time, as text. Only your own chat counts."""
    token, chat = _creds(cfg)
    if not token or not chat:
        return []
    params = {"timeout": 0, "allowed_updates": json.dumps(["message"])}
    if store.flag("telegram_offset"):
        params["offset"] = int(store.flag("telegram_offset")) + 1
    try:
        updates = requests.get(API.format(token=token, method="getUpdates"), params=params, timeout=20).json()
    except (requests.RequestException, ValueError):
        return []
    out = []
    for update in updates.get("result", []):
        store.flag("telegram_offset", update["update_id"])
        msg = update.get("message") or {}
        if str((msg.get("chat") or {}).get("id")) != str(chat):
            continue
        text = (msg.get("text") or msg.get("caption") or "").strip()
        if text:
            out.append(text)
    return out
