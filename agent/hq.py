"""Sends this agent's businesses to HQ (your dashboard) after each run, and brings back what you decided there:
anyone you marked interested, bought or lost stops getting emails, and (studio) clients you marked as bought get
their service started. Needs the secrets HQ_URL and HQ_TOKEN; without them it does nothing.

Only businesses that changed since the last sync are sent, so each run sends a few at most."""
import hashlib
import json
import os
import urllib.request

AGENT = "studio"
EXTRA = ("rating", "reviews", "grade", "score", "issue_count", "has_reel", "redesigned")
STOPPABLE = ("ready", "emailed", "manual")


def record(lead):
    """What HQ gets about one business. HQ is private to you, so contact details are included."""
    extra = {k: lead[k] for k in EXTRA if lead.get(k) not in (None, "", [], {})}
    title = (lead.get("title") or "").strip()[:80] or None      # security agent: the site's own title
    rec = {
        "id": lead["id"],
        "name": lead.get("name") or lead.get("domain") or title or lead["id"],
        "kind": lead.get("niche") or lead.get("trade") or lead.get("category") or (title if not lead.get("name") else None)
                or lead.get("builder"),
        "city": lead.get("city"), "state": lead.get("state"),
        "website": lead.get("website") or lead.get("url"),
        "email": lead.get("email"), "phone": lead.get("phone"), "socials": lead.get("socials") or None,
        "preview_url": next((lead[k] for k in ("sample_url", "preview_url", "report_url")
                             if str(lead.get(k) or "").startswith("http")), None),
        "status": lead.get("status"), "touches": lead.get("touches") or 0,
        "created_at": lead.get("created_at"), "first_sent_at": lead.get("first_sent_at"),
        "last_sent_at": lead.get("last_sent_at"), "replied_at": lead.get("replied_at"),
        "handed_over": lead.get("handed_over"), "reply_text": (lead.get("reply_text") or "")[:3000] or None,
        "extra": extra or None,
    }
    return {k: v for k, v in rec.items() if v is not None}


def _post(url, token, payload, timeout=25):
    req = urllib.request.Request(url + "/api/sync", data=json.dumps(payload, default=str).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}",
                                          "User-Agent": f"{AGENT}-agent"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def apply_stops(store, ids):
    """You're handling these yourself in HQ (interested, bought or not interested): no more emails from the agent."""
    n = 0
    for lead_id in ids or []:
        lead = store.leads.get(lead_id)
        if lead and lead.get("status") in STOPPABLE:
            lead["status"] = "finished"
            lead["hq_stopped"] = True
            store.log(lead_id, "hq", "stopped: you're handling them in HQ")
            n += 1
    return n


def sync(cfg, store, on_onboard=None):
    """Send what changed, then apply what HQ says. Never stops a run: problems are printed and retried next time."""
    url = os.environ.get("HQ_URL", "").strip().rstrip("/")
    token = os.environ.get("HQ_TOKEN", "").strip()
    if not url.startswith("https://") or not token:
        return None
    sent = store.data.setdefault("hq_sent", {})
    changed = []
    for lead in store.leads.values():
        if not lead.get("id") or lead.get("status") in (None, "skipped"):
            continue
        rec = record(lead)
        digest = hashlib.sha1(json.dumps(rec, sort_keys=True, default=str).encode()).hexdigest()[:16]
        if sent.get(lead["id"]) != digest:
            changed.append((lead["id"], digest, rec))
    offer = {k: v for k, v in (cfg.get("offer") or {}).items() if isinstance(v, (int, float, str))}
    reply, done = {}, 0
    try:
        for i in range(0, max(len(changed), 1), 200):
            batch = changed[i:i + 200]
            reply = _post(url, token, {"agent": AGENT, "mode": "live" if cfg.live else "draft", "offer": offer,
                                       "businesses": [r for _, _, r in batch]})
            for lead_id, digest, _ in batch:
                sent[lead_id] = digest
            done += len(batch)
    except Exception as e:                      # HQ down or not set up yet: the agent carries on
        print(f"HQ: couldn't sync this time ({type(e).__name__}: {str(e)[:120]}). It tries again next run.")
        return None
    stopped = apply_stops(store, reply.get("stop"))
    started = on_onboard(reply.get("onboard") or []) if on_onboard and reply.get("onboard") else 0
    print(f"HQ: {done} changed business{'' if done == 1 else 'es'} sent, {stopped} stopped, {started} started.")
    return {"sent": done, "stopped": stopped, "started": started}
