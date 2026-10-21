"""Free AI for writing (and for looking at pictures), from whichever free provider is set up.

Providers, tried in the order set in config.yaml (ai.providers):
  gemini      Google AI Studio key (GEMINI_API_KEY). Free tier on the Flash models; no card needed.
  groq        GROQ_API_KEY. Free tier, very fast open models.
  cloudflare  Workers AI with your Cloudflare account (CLOUDFLARE_ACCOUNT_ID + CLOUDFLARE_API_TOKEN with the
              Workers AI permission). 10,000 free "neurons" a day, shared with image generation.
  openrouter  OPENROUTER_API_KEY. Its ":free" models.
  pollinations  No key at all. A community-run service; used only when ai.keyless_fallback is true.

Model names change often, so each provider's model list is read and the best free model picked
automatically. When a provider says "too many requests" it rests until tomorrow and the next one is
tried. When none answers, callers fall back to built-in templates, so the agent never stops.

Only public business information is ever sent (names, websites, what they sell): free tiers may use
prompts to improve their models.
"""
import base64
import json
import re
import time

import requests

from .store import now

TIMEOUT = 90
THINKING_ROOM = 3000      # newer Gemini models think before answering, and that counts toward the answer's limit
GEMINI = "https://generativelanguage.googleapis.com/v1beta"
GROQ = "https://api.groq.com/openai/v1"
OPENROUTER = "https://openrouter.ai/api/v1"
CF = "https://api.cloudflare.com/client/v4/accounts/{account}/ai"
POLLINATIONS = "https://text.pollinations.ai/openai"

GROQ_PREFER = ["openai/gpt-oss-120b", "llama-3.3-70b-versatile", "moonshotai/kimi-k2-instruct",
               "meta-llama/llama-4-maverick-17b-128e-instruct", "qwen/qwen3-32b", "openai/gpt-oss-20b",
               "llama-3.1-8b-instant"]
OPENROUTER_PREFER = ["minimax/minimax-m3.1-flash:free", "google/gemma-4-31b-it:free",           # free list, Oct 2026
                     "nvidia/nemotron-3-super-120b-a12b:free", "dots-studio/dots-3-note-preview:free",
                     "thinkingmachines/inkling:free", "nvidia/nemotron-3-ultra-550b-a55b:free",
                     "google/gemma-4-26b-a4b-it:free", "openai/gpt-oss-120b:free", "meta-llama/llama-3.3-70b-instruct:free"]
CF_TEXT = ["@cf/meta/llama-3.3-70b-instruct-fp8-fast", "@cf/meta/llama-3.1-8b-instruct-fp8-fast"]
CF_VISION = "@cf/meta/llama-3.2-11b-vision-instruct"


class NoAI(Exception):
    pass


def _key(cfg, provider):
    if provider == "gemini":
        return cfg.secret("GEMINI_API_KEY")
    if provider == "groq":
        return cfg.secret("GROQ_API_KEY")
    if provider == "openrouter":
        return cfg.secret("OPENROUTER_API_KEY")
    if provider == "cloudflare":
        return cfg.secret("CLOUDFLARE_ACCOUNT_ID") and cfg.secret("CLOUDFLARE_API_TOKEN")
    if provider == "pollinations":
        return cfg["ai"].get("keyless_fallback")
    return None


def available(cfg):
    providers = list(cfg["ai"].get("providers") or [])
    if cfg["ai"].get("keyless_fallback") and "pollinations" not in providers:
        providers.append("pollinations")
    return [p for p in providers if _key(cfg, p)]


def _resting(store, provider):
    until = (store.flag("ai_rest") or {}).get(provider)
    return bool(until) and until > time.time()


def _busy(store, provider):
    """Models set aside because the (free) server behind them keeps turning requests away."""
    return {m for m, until in ((store.flag("ai_busy") or {}).get(provider) or {}).items() if until > time.time()}


def _set_aside(store, provider, model, hours=6):
    busy = store.flag("ai_busy") or {}
    busy[provider] = {m: t for m, t in (busy.get(provider) or {}).items() if t > time.time()}
    busy[provider][model] = time.time() + hours * 3600
    store.flag("ai_busy", busy)
    models = store.flag("ai_models") or {}
    models.pop(provider, None)                             # so the next call picks another model
    store.flag("ai_models", models)


def _rest(store, provider, seconds):
    rest = store.flag("ai_rest") or {}
    rest[provider] = time.time() + seconds
    store.flag("ai_rest", rest)


def _wait_seconds(r):
    """How long a 429 asks to wait: the Retry-After header, "try again in 1m2.5s" (Groq), or Gemini's
    retryDelay. None when it doesn't say."""
    try:
        return float((getattr(r, "headers", None) or {}).get("retry-after"))
    except (TypeError, ValueError):
        pass
    text = getattr(r, "text", "") or ""
    m = re.search(r"try again in ((?:\d+(?:\.\d+)?(?:ms|h|m|s))+)", text) or \
        re.search(r'"retryDelay":\s*"((?:\d+(?:\.\d+)?s))"', text)
    if not m:
        return None
    return sum(float(n) * {"h": 3600, "m": 60, "s": 1, "ms": 0.001}[u]
               for n, u in re.findall(r"(\d+(?:\.\d+)?)(ms|h|m|s)", m.group(1)))


def _until_tomorrow():
    t = now()
    return max(600, 86400 - (t.hour * 3600 + t.minute * 60 + t.second) + 300)


# Picking models ---------------------------------------------------------------------------------
def _cached_model(store, provider, pick):
    cache = store.flag("ai_models") or {}
    today = now().strftime("%Y-%m-%d")
    if cache.get(provider, {}).get("day") == today and cache[provider].get("model"):
        return cache[provider]["model"]
    model = pick()
    if model:
        cache[provider] = {"day": today, "model": model}
        store.flag("ai_models", cache)
    return model


def _gemini_model(cfg):
    r = requests.get(f"{GEMINI}/models", params={"key": cfg.secret("GEMINI_API_KEY"), "pageSize": 200}, timeout=30)
    names = [m["name"].split("/", 1)[1] for m in r.json().get("models", [])
             if "generateContent" in (m.get("supportedGenerationMethods") or [])]
    flash = [n for n in names if "flash" in n and not re.search(r"image|tts|audio|live|exp|preview|thinking|8b", n)]
    if not flash:
        flash = [n for n in names if "flash" in n and not re.search(r"image|tts|audio|live", n)]

    def version(n):
        nums = re.findall(r"\d+(?:\.\d+)?", n)
        return (float(nums[0]) if nums else 0, "lite" not in n, "latest" in n)
    return max(flash, key=version) if flash else "gemini-flash-latest"


def _listed(url, key, prefer, skip=()):
    r = requests.get(url, headers={"Authorization": f"Bearer {key}"}, timeout=30)
    ids = {m.get("id") for m in r.json().get("data", [])} - set(skip)
    return next((p for p in prefer if p in ids), None) or next(
        (i for i in sorted(ids) if i and i.endswith(":free") and re.search(r"70b|120b|235b|405b|27b|32b", i)), None)


# Calling providers ------------------------------------------------------------------------------
def _openai_style(url, key, model, system, prompt, max_tokens, temperature, json_mode, headers=None):
    body = {"model": model, "messages": ([{"role": "system", "content": system}] if system else [])
            + [{"role": "user", "content": prompt}], "max_tokens": max_tokens, "temperature": temperature}
    if "gpt-oss" in (model or "") or model == "openai":
        body["reasoning_effort"] = "low"                   # reasoning models: keep the budget for the answer
        body["max_tokens"] = max_tokens + 2500
    elif url.startswith(OPENROUTER):                       # its free models all think before answering: briefly
        body["reasoning"] = {"effort": "low"}
        body["max_tokens"] = max_tokens + 1500
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    h = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"} if key else {"Content-Type": "application/json"}
    h.update(headers or {})
    r = requests.post(url, json=body, headers=h, timeout=TIMEOUT)
    if r.status_code == 400 and json_mode:                 # some models don't take response_format
        body.pop("response_format", None)
        r = requests.post(url, json=body, headers=h, timeout=TIMEOUT)
    def text():
        choice = r.json()["choices"][0]
        content = (choice.get("message") or {}).get("content")
        if not content:
            raise NoAI(f"empty answer ({choice.get('finish_reason')})")
        return content
    return r, text


def _call(cfg, store, provider, system, prompt, max_tokens, temperature, json_mode):
    if provider == "gemini":
        model = _cached_model(store, "gemini", lambda: _gemini_model(cfg))
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": max_tokens + THINKING_ROOM, "temperature": temperature}}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"
        r = requests.post(f"{GEMINI}/models/{model}:generateContent", params={"key": cfg.secret("GEMINI_API_KEY")},
                          json=body, timeout=TIMEOUT)
        text = lambda: "".join(p.get("text", "") for p in r.json()["candidates"][0]["content"]["parts"])
    elif provider == "groq":
        key = cfg.secret("GROQ_API_KEY")
        model = _cached_model(store, "groq", lambda: _listed(f"{GROQ}/models", key, GROQ_PREFER))
        r, text = _openai_style(f"{GROQ}/chat/completions", key, model, system, prompt, max_tokens, temperature, json_mode)
    elif provider == "openrouter":
        key = cfg.secret("OPENROUTER_API_KEY")
        busy = _busy(store, "openrouter")
        model = _cached_model(store, "openrouter", lambda: _listed(f"{OPENROUTER}/models", key, OPENROUTER_PREFER, busy))
        if not model:
            raise NoAI("openrouter: no free model is available right now")
        r, text = _openai_style(f"{OPENROUTER}/chat/completions", key, model, system, prompt, max_tokens, temperature,
                                json_mode, headers={"X-Title": "studio-agent"})
        if r.status_code in (429, 502, 503) and "free-models-per" not in r.text:
            _set_aside(store, "openrouter", model)         # that model's free server is busy or down, not your account
            raise NoAI(f"openrouter: {r.status_code} {model} is busy upstream")
        if r.status_code == 404 and "no endpoints found" in r.text.lower():
            _set_aside(store, "openrouter", model, hours=24)   # e.g. your privacy settings rule out its free host
            why = "your OpenRouter privacy settings rule out its free host" if "data policy" in r.text else "not offered"
            raise NoAI(f"openrouter: 404 {model} is off for this account ({why})")
    elif provider == "cloudflare":
        model = CF_TEXT[0] if (store.usage("cf_neurons_est", period="day") < 5000) else CF_TEXT[1]
        url = CF.format(account=cfg.secret("CLOUDFLARE_ACCOUNT_ID")) + "/run/" + model
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        r = requests.post(url, json={"messages": msgs, "max_tokens": max_tokens, "temperature": temperature},
                          headers={"Authorization": f"Bearer {cfg.secret('CLOUDFLARE_API_TOKEN')}"}, timeout=TIMEOUT)
        text = lambda: r.json()["result"]["response"]
        store.add_usage("cf_neurons_est", 60 if "70b" in model else 15, period="day")
    elif provider == "pollinations":
        model = "openai"
        wait = 31 - (time.time() - (store.flag("pollinations_at") or 0))
        if wait > 0:
            time.sleep(wait)                               # its free tier answers once every 30 seconds
        r, text = _openai_style(POLLINATIONS, None, model, system, prompt, max_tokens, temperature, json_mode)
        store.flag("pollinations_at", time.time())
        if r.status_code == 402 and "FREE_LIMIT" in r.text:
            time.sleep(31)
            r, text = _openai_style(POLLINATIONS, None, model, system, prompt, max_tokens, temperature, json_mode)
            store.flag("pollinations_at", time.time())
    else:
        raise NoAI(provider)
    if r.status_code == 429:
        daily = bool(re.search(r"per[\s_-]?day|\((?:TPD|RPD)\)", r.text or "", re.I))
        wait = _wait_seconds(r)
        if wait is None and re.search(r"per[\s_-]?min|\((?:TPM|RPM)\)", r.text or "", re.I):
            wait = 60
        if provider == "pollinations":
            wait = 120
        # a per-minute limit (Groq's free tier hits one with almost every big answer) is a short pause; only a
        # used-up day, or a limit that doesn't say how long, rests the provider until tomorrow
        seconds = _until_tomorrow() if daily or wait is None else min(wait, _until_tomorrow())
        _rest(store, provider, seconds)
        e = NoAI(f"{provider}: rate limited" + (" (today's free requests are used up)" if daily else
                                                 f" for {seconds:.0f}s" if seconds < 3600 else ""))
        e.wait = seconds if seconds <= 45 else None
        raise e
    if r.status_code >= 400:
        if r.status_code in (401, 403):
            _rest(store, provider, _until_tomorrow())
        elif r.status_code == 404:                         # the cached model went away: pick again next call
            models = store.flag("ai_models") or {}
            models.pop(provider, None)
            store.flag("ai_models", models)
        raise NoAI(f"{provider}: {r.status_code} {r.text[:200]}")
    out = text()
    if isinstance(out, dict):
        out = json.dumps(out)
    return out, f"{provider}:{model}"


def ask(cfg, store, prompt, system=None, json_mode=True, max_tokens=2000, temperature=0.8):
    """Ask the first free provider that answers. Returns parsed JSON (json_mode) or text; None if no
    provider could answer (callers then use their built-in templates)."""
    if store.usage("ai_calls", period="day") >= cfg["limits"]["ai_calls_per_day"]:
        return None
    for provider in available(cfg):
        if _resting(store, provider):
            continue
        try:
            try:
                text, used = _call(cfg, store, provider, system, prompt, max_tokens, temperature, json_mode)
            except NoAI as e:
                if not getattr(e, "wait", None):
                    raise
                print(f"AI: {e}; waiting, then asking it again")       # better than a weaker model's answer
                time.sleep(e.wait + 1)                                  # (its pause is over by then)
                text, used = _call(cfg, store, provider, system, prompt, max_tokens, temperature, json_mode)
        except (NoAI, requests.RequestException, KeyError, IndexError, ValueError, TypeError) as e:
            print(f"AI: {str(e)[:160]}")
            continue
        store.add_usage("ai_calls", period="day")
        store.add_usage("ai:" + provider, period="day")
        if not json_mode:
            return text.strip()
        data = parse_json(text)
        if data is not None:
            data_used = data if isinstance(data, dict) else {"items": data}
            data_used.setdefault("_model", used)
            return data_used
        print(f"AI: {used} didn't return JSON ({_shape(text)})")
    return None


def _shape(text):
    """What a non-JSON reply looked like, without its words."""
    t = (text or "").strip()
    if not t:
        return "empty"
    hints = [f"{len(t)} chars"]
    if "<think>" in t:
        hints.append("thinking left in" if "</think>" in t else "only thinking, cut off")
    elif t.count("{") > t.count("}"):
        hints.append("cut off")
    elif "{" not in t:
        hints.append("no braces")
    return ", ".join(hints)


def parse_json(text):
    """The JSON object in a model's reply, even when wrapped in prose, code fences or "thinking" tags, or with
    trailing commas."""
    if not text:
        return None
    text = re.sub(r"(?s)<think>.*?</think>", "", text)
    t = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    data = _loads(t)
    if data is not None:
        return data
    return _loads(re.sub(r",(\s*[}\]])", r"\1", t))


def _loads(t):
    """json.loads on the reply, or on the first complete object or list in it."""
    try:
        return json.loads(t)
    except ValueError:
        pass
    start = min([i for i in (t.find("{"), t.find("[")) if i >= 0] or [-1])
    if start < 0:
        return None
    depth, quote, escape = 0, False, False
    for i in range(start, len(t)):
        ch = t[i]
        if quote:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                quote = False
        elif ch == '"':
            quote = True
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(t[start:i + 1])
                except ValueError:
                    return None
    return None


def see(cfg, store, image_path, prompt, max_tokens=600):
    """Ask a vision model about a picture (JSON reply). Gemini first, then Cloudflare's Llama Vision."""
    if store.usage("ai_calls", period="day") >= cfg["limits"]["ai_calls_per_day"]:
        return None
    data = base64.b64encode(open(image_path, "rb").read()).decode()
    mime = "image/png" if str(image_path).endswith(".png") else "image/jpeg"
    if cfg.secret("GEMINI_API_KEY") and not _resting(store, "gemini"):
        try:
            model = _cached_model(store, "gemini", lambda: _gemini_model(cfg))
            r = requests.post(f"{GEMINI}/models/{model}:generateContent", params={"key": cfg.secret("GEMINI_API_KEY")},
                              json={"contents": [{"parts": [{"inline_data": {"mime_type": mime, "data": data}},
                                                            {"text": prompt}]}],
                                    "generationConfig": {"maxOutputTokens": max_tokens + THINKING_ROOM,
                                                         "responseMimeType": "application/json"}}, timeout=TIMEOUT)
            if r.status_code == 429:
                _rest(store, "gemini", _until_tomorrow())
            elif r.status_code == 200:
                store.add_usage("ai_calls", period="day")
                return parse_json("".join(p.get("text", "") for p in r.json()["candidates"][0]["content"]["parts"]))
        except (requests.RequestException, KeyError, IndexError, ValueError):
            pass
    if cfg.secret("CLOUDFLARE_ACCOUNT_ID") and cfg.secret("CLOUDFLARE_API_TOKEN") and not _resting(store, "cloudflare"):
        try:
            url = CF.format(account=cfg.secret("CLOUDFLARE_ACCOUNT_ID")) + "/run/" + CF_VISION
            r = requests.post(url, headers={"Authorization": f"Bearer {cfg.secret('CLOUDFLARE_API_TOKEN')}"}, timeout=TIMEOUT,
                              json={"messages": [{"role": "user", "content": [
                                  {"type": "text", "text": prompt + " Reply with JSON only."},
                                  {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}]}],
                                  "max_tokens": max_tokens})
            if r.status_code == 200:
                store.add_usage("ai_calls", period="day")
                store.add_usage("cf_neurons_est", 40, period="day")
                return parse_json(r.json()["result"]["response"])
        except (requests.RequestException, KeyError, ValueError):
            pass
    return None
