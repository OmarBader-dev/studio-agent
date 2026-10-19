"""All agent state in one JSON file (data/state.json), so GitHub can store it as plain text."""
import datetime as dt
import json
import os
import tempfile

from .settings import DATA

STATE = DATA / "state.json"

# Prospect statuses, in the order a prospect normally moves through them.
#   skipped     a chain, closed, no website to learn the brand from, or opted out before
#   manual      sample built, no public email: you message them yourself (Telegram hands you a draft)
#   ready       sample built and email found, waiting for the first email
#   emailed     first email sent, follow-ups pending
#   finished    all follow-ups sent, no reply
#   replied     they wrote back: you were pinged on Telegram (and, on autopilot, they got the plans and prices)
#   client      they became a client (/client on Telegram)
#   opted_out   they asked not to be contacted
#   bounced     the email address doesn't work
#   expired     sample page deleted after limits.sample_days
OPEN_STATUSES = {"ready", "emailed"}


def now():
    return dt.datetime.now(dt.timezone.utc)


def iso(t=None):
    return (t or now()).replace(microsecond=0).isoformat()


def parse(ts):
    return dt.datetime.fromisoformat(ts) if ts else None


def _fernet():
    """With a STATE_KEY secret, state is stored encrypted (data/state.enc), so the repo can be public."""
    key = os.environ.get("STATE_KEY", "").strip()
    if not key:
        return None
    from cryptography.fernet import Fernet
    return Fernet(key.encode())


class Store:
    def __init__(self, path=STATE):
        self.path = path
        self.fernet = _fernet() if path == STATE else None
        enc = path.with_suffix(".enc")
        if self.fernet and enc.exists():
            self.data = json.loads(self.fernet.decrypt(enc.read_bytes()).decode() or "{}")
        else:
            self.data = json.loads(path.read_text() or "{}") if path.exists() else {}
        for key, empty in (("leads", {}), ("seen", []), ("suppress", {}), ("usage", {}), ("searches", {}),
                           ("sent", {}), ("events", []), ("flags", {}), ("clients", {}), ("jobs", {}),
                           ("clients_db", {})):
            self.data.setdefault(key, empty)
        self._seen = set(self.data["seen"])

    # Prospects --------------------------------------------------------------
    @property
    def leads(self):
        return self.data["leads"]

    def add(self, lead):
        lead.setdefault("created_at", iso())
        lead["updated_at"] = iso()
        self.leads[lead["id"]] = lead
        return lead

    def update(self, lead_id, **fields):
        lead = self.leads[lead_id]
        lead.update(fields)
        lead["updated_at"] = iso()
        return lead

    def with_status(self, *statuses):
        return [l for l in self.leads.values() if l.get("status") in statuses]

    def find_by_email(self, email):
        email = (email or "").lower()
        if not email:
            return None
        for lead in self.leads.values():
            if (lead.get("email") or "").lower() == email:
                return lead
        return None

    # Clients (paying customers): their week packs, design jobs, approvals ---------------------------
    def client(self, key):
        return self.data["clients"].setdefault(key, {"weeks": {}, "posted": []})

    # Messages ---------------------------------------------------------------
    def record_sent(self, msgid, lead_id):
        self.data["sent"][msgid] = lead_id

    def lead_for_msgids(self, msgids):
        for m in msgids:
            lead_id = self.data["sent"].get(m)
            if lead_id and lead_id in self.leads:
                return self.leads[lead_id]
        return None

    def is_seen(self, msgid):
        return msgid in self._seen

    def mark_seen(self, msgid):
        if msgid and msgid not in self._seen:
            self._seen.add(msgid)
            self.data["seen"].append(msgid)
            self.data["seen"] = self.data["seen"][-5000:]

    def suppress(self, email, reason):
        if email:
            self.data["suppress"][email.lower()] = {"reason": reason, "at": iso()}

    def is_suppressed(self, email):
        return (email or "").lower() in self.data["suppress"]

    # Usage counters, events, flags --------------------------------------------
    def usage(self, key, period="month"):
        stamp = now().strftime("%Y-%m" if period == "month" else "%Y-%m-%d")
        return self.data["usage"].get(f"{stamp}:{key}", 0)

    def add_usage(self, key, n=1, period="month"):
        stamp = now().strftime("%Y-%m" if period == "month" else "%Y-%m-%d")
        k = f"{stamp}:{key}"
        self.data["usage"][k] = self.data["usage"].get(k, 0) + n
        if len(self.data["usage"]) > 400:          # keep the last few months
            for old in sorted(self.data["usage"])[:100]:
                self.data["usage"].pop(old, None)

    def log(self, lead_id, kind, detail=""):
        self.data["events"].append({"at": iso(), "lead": lead_id, "kind": kind, "detail": str(detail)[:500]})
        self.data["events"] = self.data["events"][-2000:]

    def flag(self, name, value=None):
        if value is None:
            return self.data["flags"].get(name)
        self.data["flags"][name] = value

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(self.data, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
        target = self.path.with_suffix(".enc") if self.fernet else self.path
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        with os.fdopen(fd, "wb") as f:
            f.write(self.fernet.encrypt(text.encode()) if self.fernet else text.encode())
        os.replace(tmp, target)
        if self.fernet and self.path.exists():
            self.path.unlink()                         # never leave a readable copy next to the encrypted one
