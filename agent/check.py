"""python -m agent check: tests every service the studio agent uses, with the keys you've added, and sends you the
result on Telegram. The log only shows ok / skipped / FAILED (with the HTTP status) per service, so it's safe in a
public repository."""
import imaplib
import os
import re
import smtplib
import urllib.error

import requests

from . import ai, hq, images, publish, web
from .inbox import IMAP_HOST
from .mailer import SMTP_HOST, SMTP_PORT
from .notify import esc, telegram
from .settings import public_repo


def gmail(cfg):
    email, password = cfg["you"].get("email"), cfg.secret("GMAIL_APP_PASSWORD")
    if not email or not password:
        return None, "add the GMAIL_APP_PASSWORD secret (and you.email in config.yaml)"
    try:
        s = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30)
        s.login(email, password)
        s.quit()
        m = imaplib.IMAP4_SSL(IMAP_HOST, 993)
        m.login(email, password)
        m.logout()
        return True, f"{email} can send and read"
    except (smtplib.SMTPAuthenticationError, imaplib.IMAP4.error):
        return False, "Gmail refused the app password: make a new one (2-Step Verification must be on)"
    except (smtplib.SMTPException, OSError) as e:
        return False, f"couldn't reach Gmail ({type(e).__name__})"


def _ask(cfg, store, provider):
    """(True, what answered) · (False, why) · (None, (model, HTTP status, why it was set aside)): ask again and
    another free model is picked."""
    try:     # room for "thinking" models, which spend part of the answer's budget before they reply
        _, model = ai._call(cfg, store, provider, None, "Reply with the single word: ready", 400, 0, False)
        return True, f"{model.split(':', 1)[-1]} answered"
    except ai.NoAI as e:
        text = str(e)
        aside = re.match(r"\w+: (\d{3}) (\S+) is (busy upstream|off for this account \((.+)\))", text)
        if aside:
            return None, (aside[2].split("/")[-1], aside[1], aside[4] or "its free server is busy")
        m = re.match(r"\w+: (\d{3}) ", text)
        code = f" (HTTP {m[1]})" if m else " (HTTP 429)" if "rate limited" in text else ""
        if re.search(r" 40[13]\b|API.key.not.valid|API_KEY_INVALID|Authentication error", text, re.I):
            return False, "the key was refused: copy it again" + code
        if "used up" in text:
            return False, "today's free requests are used up (it tries again tomorrow)" + code
        if "rate limited" in text or " 429" in text:
            return False, "busy or over today's free limit (it rests and tries again tomorrow)" + code
        if " 503" in text:
            return True, "the key works, but the model is busy right now (it retries on its own)"
        if re.search(r"data policy|settings/privacy", text, re.I):
            return False, "your privacy settings turn its free models off: openrouter.ai/settings/privacy" + code
        if " 402" in text:
            return False, "this model needs credits on the account" + code
        if text.startswith("empty answer"):
            return True, "the key works (the test answer came back empty)"
        if "no free model" in text:
            return False, "none of its free models is available right now (it tries again later)"
        return False, f"it answered with an error{code}: {text[m.end() if m else 0:][:100]}"
    except requests.RequestException as e:
        return False, f"no answer ({type(e).__name__})"
    except (KeyError, IndexError, ValueError):     # it answered (errors are raised before this), just oddly
        return True, "the key works (the test answer came back in an odd shape)"


def ai_provider(cfg, store, provider):
    if not ai._key(cfg, provider):
        return None, "no key"
    aside = []
    for _ in range(3):        # a free model that's busy or ruled out is set aside, and the next try picks another
        ok, why = _ask(cfg, store, provider)
        if ok is not None:
            break
        aside.append(why)
    notes = "; ".join(f"{model}: {reason}" for model, _, reason in aside)
    if ok is None:
        return False, f"none of the free models it tried answered ({notes}); it tries others later (HTTP {aside[-1][1]})"
    if ok:
        rest = store.flag("ai_rest") or {}
        if rest.pop(provider, None):          # a key refused earlier and fixed since is used again right away
            store.flag("ai_rest", rest)
        if aside:
            why += f". Set aside for now: {notes}"
    return ok, why


def photos(cfg, name, url, key_name, params, first, header=False):
    """Searches with the key, then downloads the first photo the way client designs do."""
    key = cfg.secret(key_name)
    if not key:
        return None, "no key (optional: Openverse photos are used without one)"
    try:
        r = requests.get(url, params=dict(params, **({} if header else {"key": key})), timeout=20,
                         headers={"Authorization": key} if header else None)
    except requests.RequestException as e:
        return False, f"no answer ({type(e).__name__})"
    if r.status_code != 200:
        return False, f"{name} refused the key (HTTP {r.status_code})"
    data = r.json()
    n = data.get("totalHits", data.get("total_results", 0))
    if not n:
        return False, "the key works but nothing came back"
    path = web.download(first(data), images.FOLDER)
    if not path:
        return False, f"the key works and {n} photos were found, but downloading one failed"
    return True, f"{n} photos found for \"autumn leaves\", one downloaded ({path.stat().st_size // 1024} KB)"


def cloudflare(cfg):
    if not publish.configured(cfg):
        return None, "add CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID"
    try:
        r = publish._api(cfg, "GET", f"/pages/projects/{cfg['pages']['cloudflare_project']}")
    except requests.RequestException as e:
        return False, f"no answer ({type(e).__name__})"
    if r.status_code == 200:
        return True, f"the sample site {cfg['pages']['cloudflare_project']}.pages.dev is ready"
    if r.status_code == 404:
        return True, "the token works; the sample site is made with the first sample"
    return False, f"Cloudflare refused the token: it needs Cloudflare Pages · Edit (HTTP {r.status_code})"


def hq_link(cfg):
    url, token = os.environ.get("HQ_URL", "").strip().rstrip("/"), os.environ.get("HQ_TOKEN", "").strip()
    if not url or not token:
        return None, "add HQ_URL and HQ_TOKEN (optional)"
    try:
        hq._post(url, token, {"agent": hq.AGENT, "businesses": []})
        return True, "connected"
    except urllib.error.HTTPError as e:
        return False, ("HQ refused the token: copy HQ_TOKEN again from HQ → Settings" if e.code == 401
                       else "HQ answered with an error") + f" (HTTP {e.code})"
    except (urllib.error.URLError, OSError, ValueError) as e:
        return False, f"couldn't reach HQ ({type(e).__name__}): check HQ_URL"


def meta(cfg):
    token = cfg.secret("META_ACCESS_TOKEN")
    if not token:
        return None, "not set (optional: for posting to clients' Instagram and Facebook)"
    try:
        r = requests.get("https://graph.facebook.com/v21.0/me", params={"access_token": token}, timeout=20)
    except requests.RequestException as e:
        return False, f"no answer ({type(e).__name__})"
    return (True, "token works") if r.status_code == 200 else (False, f"Meta refused the token (HTTP {r.status_code})")


def _safe(fn, *args, **kw):
    """One broken check shouldn't hide the others (and its error text could hold a key, so only its type is shown)."""
    try:
        return fn(*args, **kw)
    except Exception as e:
        return False, f"the check itself failed ({type(e).__name__})"


def run(cfg, store):
    results = [("Gmail", _safe(gmail, cfg))]
    for provider, label in (("gemini", "Gemini"), ("groq", "Groq"), ("openrouter", "OpenRouter"),
                            ("cloudflare", "Cloudflare Workers AI")):
        results.append((label, _safe(ai_provider, cfg, store, provider)))
    results.append(("Pixabay", _safe(photos, cfg, "Pixabay", "https://pixabay.com/api/", "PIXABAY_API_KEY",
                                     {"q": "autumn leaves", "image_type": "photo", "safesearch": "true", "per_page": 3},
                                     lambda d: (d.get("hits") or [{}])[0].get("largeImageURL"))))
    results.append(("Pexels", _safe(photos, cfg, "Pexels", "https://api.pexels.com/v1/search", "PEXELS_API_KEY",
                                    {"query": "autumn leaves", "per_page": 1},
                                    lambda d: ((d.get("photos") or [{}])[0].get("src") or {}).get("large2x"),
                                    header=True)))
    results += [("Cloudflare Pages", _safe(cloudflare, cfg)), ("HQ", _safe(hq_link, cfg)), ("Meta", _safe(meta, cfg)),
                ("Memory", (True, "encrypted with STATE_KEY") if public_repo()
                 else (None, "not encrypted (fine in a private repository)"))]
    if not any(ok for name, (ok, _) in results if name in ("Gemini", "Groq", "OpenRouter", "Cloudflare Workers AI")):
        results.append(("AI", (False, "no AI answered: posts use plainer built-in templates until one does")))
    mark = {True: "✅", False: "❌", None: "➖"}
    lines = ["<b>Studio agent check</b>"] + [f"{mark[ok]} <b>{esc(name)}</b>: {esc(why)}" for name, (ok, why) in results]
    lines.append("" if cfg.live else "\nMode is <b>draft</b>: nothing is emailed to businesses until you switch to live.")
    sent = telegram(cfg, "\n".join(lines))
    for name, (ok, why) in results:                 # error texts stay on Telegram; only the HTTP status is logged
        status = re.search(r"\(HTTP \d{3}\)", why) if ok is False else None
        print(f"{name}: {'ok' if ok else 'skipped' if ok is None else 'FAILED'}{' ' + status[0] if status else ''}")
    print(f"Telegram: {'ok (the full report is there)' if sent else 'FAILED (check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)'}")
    return results
