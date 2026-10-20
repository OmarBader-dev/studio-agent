"""End-to-end test of HQ running locally, with made-up businesses.

  cd hq && printf 'HQ_PASSWORD=test-pass-123\nTWILIO_ACCOUNT_SID=AC00000000000000000000000000000000\nTWILIO_AUTH_TOKEN=fake-auth-token-for-tests\n' > .dev.vars
  npx wrangler dev --port 8787 --local --persist-to /tmp/hq-test        (in one terminal, with a fresh folder)
  HQ_PERSIST=/tmp/hq-test python3 test/e2e.py                            (in another)

.dev.vars is only for this local test; never commit it."""
import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from agent import hq  # noqa: E402

BASE = os.environ.get("HQ_BASE", "http://127.0.0.1:8787")
AUTH = "fake-auth-token-for-tests"
PERSIST = os.environ.get("HQ_PERSIST", "/tmp/hq-test")
HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
COOKIE = {}
ok_count = 0


def req(method, path, body=None, headers=None, raw=False, form=None):
    h = dict(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h.setdefault("Content-Type", "application/json")
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        h["Content-Type"] = "application/x-www-form-urlencoded"
    if COOKIE.get("hq") and "Authorization" not in h:
        h["Cookie"] = f"hq={COOKIE['hq']}"
    r = urllib.request.Request(BASE + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            out, status, hdrs = resp.read(), resp.status, resp.headers
    except urllib.error.HTTPError as e:
        out, status, hdrs = e.read(), e.code, e.headers
    sc = hdrs.get("Set-Cookie") or ""
    if sc.startswith("hq="):
        COOKIE["hq"] = sc.split(";")[0][3:]
    if raw:
        return status, out.decode()
    try:
        return status, json.loads(out or b"null")
    except json.JSONDecodeError:
        return status, out.decode()


def check(cond, what):
    global ok_count
    if not cond:
        raise SystemExit(f"FAILED: {what}")
    ok_count += 1
    print("  ok:", what)


def twilio_sig(url, params):
    data = url + "".join(k + params[k] for k in sorted(params))
    return base64.b64encode(hmac.new(AUTH.encode(), data.encode(), hashlib.sha1).digest()).decode()


def twilio(path, params, sign=True):
    url = BASE + path
    headers = {"X-Twilio-Signature": twilio_sig(url, params) if sign else "bad"}
    return req("POST", path, form=params, headers=headers, raw=True)


print("Login")
s, d = req("GET", "/api/me")
check(s == 401 and d["error"] == "login", "not logged in at first")
s, d = req("POST", "/api/login", {"password": "nope"})
check(s == 401, "wrong password refused")
s, d = req("POST", "/api/login", {"password": "test-pass-123"})
check(s == 200 and COOKIE.get("hq"), "right password logs in")
s, d = req("GET", "/api/me")
check(s == 200 and d["ok"] and d["twilio"] is False, "me works, Twilio not connected yet")
s, d = req("POST", "/api/settings", {"name": "Omar Bader Studio"}, headers={"Origin": "https://evil.example"})
check(s == 403, "another site can't change settings")

print("Settings and agent token")
s, st = req("GET", "/api/settings")
check(s == 200 and len(st["token"]) > 20 and st["url"] == BASE, "settings show HQ_URL and HQ_TOKEN")
token = st["token"]
s, d = req("POST", "/api/sync", {"agent": "lead", "businesses": []}, headers={"Authorization": "Bearer wrong"})
check(s == 401, "sync refuses a wrong token")

print("Sync the real data of the three agents")
def fake_leads(agent, n):
    leads, now = [], "2026-10-20T12:00:00+00:00"
    statuses = ["emailed", "manual", "ready", "skipped", "finished", "bounced"]
    for i in range(n):
        st = statuses[i % len(statuses)]
        lead = {"id": f"ov:{agent}-{i}", "status": st, "created_at": "2026-10-15T12:00:00+00:00"}
        if agent == "security":
            lead.update(domain=f"site{i}.dev", title=f"Show HN: Thing {i}", report_url=f"https://r.pages.dev/r/{i}/")
        else:
            lead.update(name=f"{agent.title()} Business {i}", city="Columbus", state="OH", phone=f"(614) 555-{1000 + i}",
                        website=f"https://biz{i}.example.com", **({"trade": "plumber"} if agent == "lead" else {"niche": "cafe"}),
                        **{("preview_url" if agent == "lead" else "sample_url"): f"https://p.pages.dev/{agent}/{i}/"})
        if st in ("emailed", "finished", "bounced", "ready"):
            lead["email"] = f"owner{i}@biz{i}.example.com"
        if st in ("emailed", "finished"):
            lead.update(touches=1 if st == "emailed" else 3, first_sent_at="2026-10-16T14:00:00+00:00", last_sent_at=now)
        leads.append(lead)
    return leads


offers = {"lead": {"setup_price": 120, "monthly_price": 20}, "security": {"monthly_price": 70, "full_pentest_price": 150},
          "studio": {"social_monthly": 99, "design_monthly": 49, "bundle_monthly": 129}}
data = {a: fake_leads(a, 24) for a in offers}
expected = {}
for agent, leads in data.items():
    recs = [hq.record(l) for l in leads if l.get("status") not in (None, "skipped")]
    expected[agent] = len(recs)
    s, d = req("POST", "/api/sync", {"agent": agent, "mode": "live", "offer": offers[agent], "businesses": recs},
               headers={"Authorization": f"Bearer {token}"})
    check(s == 200 and d["received"] == len(recs) and d["stop"] == [], f"{agent}: {len(recs)} businesses synced")
s, d = req("POST", "/api/sync", {"agent": "lead", "businesses": [hq.record(l) for l in data["lead"][:3]]},
           headers={"Authorization": f"Bearer {token}"})
check(s == 200, "syncing the same businesses again is fine")

print("Views")
s, today = req("GET", "/api/today")
check(s == 200 and isinstance(today["calls"], list), f"today: {len(today['calls'])} calls, counts {today['counts']}")
check(sum(today["counts"].values()) == sum(expected.values()), "every synced business is counted once")
for c in today["calls"]:
    check(c["dial"].startswith("+1") and c["why"] and c["window"] and c["window"]["label"], f"call row: {c['name']} · {c['why']} · {c['window']['label']}")
    break
s, lst = req("GET", "/api/businesses?stage=all&agent=all&q=")
check(s == 200 and len(lst["items"]) == 50 and lst["more"], "pipeline lists 50 at a time")
s, lst2 = req("GET", "/api/businesses?stage=contacted&agent=lead&q=")
check(s == 200 and all(b["eff"] == "contacted" and b["agent"] == "lead" for b in lst2["items"]), "filter by stage and agent")
s, srch = req("GET", "/api/businesses?stage=all&agent=all&q=" + urllib.parse.quote(lst["items"][0]["name"][:6]))
check(s == 200 and srch["items"], "search finds by name")

print("Actions on one studio business")
studio_item = next(b for b in req("GET", "/api/businesses?agent=studio&stage=all")[1]["items"])
key = studio_item["key"]
s, d = req("GET", f"/api/business/{urllib.parse.quote(key, safe='')}")
check(s == 200 and d["business"]["key"] == key and d["plans"][0]["id"] == "social", "business page with studio plans")
s, d = req("POST", f"/api/business/{urllib.parse.quote(key, safe='')}", {"action": "note", "text": "Owner is Sam, wants Reels <b>bold</b>"})
check(s == 200 and d["activity"][0]["kind"] == "note", "note added")
s, d = req("POST", f"/api/business/{urllib.parse.quote(key, safe='')}", {"action": "stage", "stage": "interested"})
check(d["business"]["eff"] == "interested", "marked interested")
s, d = req("POST", f"/api/business/{urllib.parse.quote(key, safe='')}", {"action": "bought", "plan": "bundle", "plan_label": "Social + Design",
                                                                         "price": 129, "cycle": "monthly", "bought_at": "2026-10-20", "start_service": True})
b = d["business"]
check(b["eff"] == "client" and b["renews_at"] == "2026-11-20" and b["start_service"] == 1, "bought: client, renews Nov 20, service to start")
s, d = req("POST", "/api/sync", {"agent": "studio", "businesses": []}, headers={"Authorization": f"Bearer {token}"})
check(any(o["id"] == studio_item["key"].split(":", 1)[1] and o["plan"] == "bundle" for o in d["onboard"]), "the studio agent is told to start their service")
s, d = req("POST", f"/api/business/{urllib.parse.quote(key, safe='')}", {"action": "paid"})
check(d["business"]["renews_at"] == "2026-12-20", "paid: renewal moves a month")
s, cl = req("GET", "/api/clients")
check(cl["count"] == 1 and cl["mrr"] == 129, "clients: 1 client, $129 a month")
s, d = req("POST", f"/api/business/{urllib.parse.quote(key, safe='')}", {"action": "remind", "date": "2026-10-20", "note": "Send the first invoice"})
check(d["business"]["remind_at"] == "2026-10-20", "reminder saved")
s, today = req("GET", "/api/today")
check(any(r["key"] == key for r in today["reminders"]), "today shows the reminder")

print("A lead-agent business marked not interested stops its emails")
emailed = next(b for b in req("GET", "/api/businesses?agent=lead&stage=contacted")[1]["items"])
s, d = req("POST", f"/api/business/{urllib.parse.quote(emailed['key'], safe='')}", {"action": "call_outcome", "outcome": "not_interested", "note": "Has a nephew who does websites"})
check(d["business"]["eff"] == "lost", "call outcome: not interested → lost")
s, d = req("POST", "/api/sync", {"agent": "lead", "businesses": []}, headers={"Authorization": f"Bearer {token}"})
check(emailed["key"].split(":", 1)[1] in d["stop"], "the lead agent is told to stop emailing them")

print("Add a business by hand")
s, d = req("POST", "/api/businesses", {"name": "Referral Bakery", "phone": "(614) 555-0199", "city": "Columbus", "state": "oh", "kind": "bakery"})
check(s == 200 and d["key"].startswith("manual:"), "added")
manual_key = d["key"]
s, d = req("GET", f"/api/business/{urllib.parse.quote(manual_key, safe='')}")
check(d["business"]["eff"] == "to_contact" and d["business"]["dial"] == "+16145550199", "it's in Call or DM, with a callable number")

print("Twilio webhooks")
s, t = twilio("/twilio/voice", {"From": "client:omar", "To": "+16145550199", "key": manual_key, "CallSid": "CA" + "1" * 32}, sign=False)
check(s == 403, "a request without Twilio's signature is refused")
s, t = twilio("/twilio/voice", {"From": "client:omar", "Caller": "client:omar", "To": "+16145550199", "key": manual_key, "CallSid": "CA" + "1" * 32})
check(s == 200 and "<Dial" in t and "+16145550199</Number>" in t, "Call: dials the business")
s, t = twilio("/twilio/voice", {"From": "client:omar", "To": "+18095551234", "key": manual_key, "CallSid": "CA" + "2" * 32})
check("<Dial" not in t, "Call: won't dial a number that isn't the business's")
s, t = twilio("/twilio/status", {"CallSid": "CA" + "3" * 32, "ParentCallSid": "CA" + "1" * 32, "CallStatus": "completed", "CallDuration": "83"})
s, d = req("GET", f"/api/business/{urllib.parse.quote(manual_key, safe='')}")
check(any(a["kind"] == "call" and "1:23" in a["detail"] for a in d["activity"]) and d["business"]["calls"] == 1, "call logged with its length")
s, t = twilio("/twilio/incoming", {"From": "+16145550199", "To": "+16145550000", "CallSid": "CA" + "4" * 32})
check("<Client><Identity>omar</Identity>" in t and "Referral Bakery" in t, "incoming call rings HQ, with who's calling")
s, t = twilio("/twilio/missed", {"CallSid": "CA" + "4" * 32, "DialCallStatus": "no-answer"})
check("<Record" in t, "missed call goes to voicemail")
s, t = twilio("/twilio/voicemail", {"CallSid": "CA" + "4" * 32, "RecordingSid": "RE" + "a" * 32, "RecordingDuration": "21",
                                     "RecordingUrl": "https://api.twilio.com/x"})
s, d = req("GET", f"/api/business/{urllib.parse.quote(manual_key, safe='')}")
check(any(a["meta"] and a["meta"].get("recording") == "RE" + "a" * 32 for a in d["activity"]), "voicemail shows on their page")

print("Twilio token")
from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: E402
key_secret = "test-api-key-secret"
iv = os.urandom(12)
sealed = base64.b64encode(iv).decode() + "." + base64.b64encode(AESGCM(hashlib.sha256(("hq-twilio:" + AUTH).encode()).digest()).encrypt(iv, key_secret.encode(), None)).decode()
setting = json.dumps({"number": "+16145550000", "number_sid": "PN1", "app_sid": "AP" + "b" * 32, "key_sid": "SK" + "c" * 32, "key_secret": sealed, "at": "x"})
sql = "INSERT INTO settings (k, v) VALUES ('twilio', '" + setting.replace("'", "''") + "') ON CONFLICT(k) DO UPDATE SET v = excluded.v"
subprocess.run(["npx", "wrangler", "d1", "execute", "studio-hq", "--local", "--persist-to", PERSIST, "--command", sql],
               cwd=HERE, check=True, capture_output=True)
s, d = req("GET", "/api/twilio/token")
check(s == 200 and d["token"].count(".") == 2, "token made")
head, payload, sig = d["token"].split(".")
pad = lambda x: x + "=" * (-len(x) % 4)
want = base64.urlsafe_b64encode(hmac.new(key_secret.encode(), f"{head}.{payload}".encode(), hashlib.sha256).digest()).decode().rstrip("=")
claims = json.loads(base64.urlsafe_b64decode(pad(payload)))
check(sig == want and claims["grants"]["voice"]["outgoing"]["application_sid"] == "AP" + "b" * 32 and claims["grants"]["identity"] == "omar"
      and json.loads(base64.urlsafe_b64decode(pad(head)))["cty"] == "twilio-fpa;v=1", "token signed right, with the calling app and identity")
s, d = req("GET", "/api/me")
check(d["twilio"] is True, "me says Twilio is connected")

print("Daily Telegram list")
s, d = req("GET", "/api/digest")
check(s == 200 and "calls to make" in d["text"] or "call to make" in d["text"], "digest has the call list")
print(d["text"][:900])
print(f"\nAll {ok_count} checks passed.")
