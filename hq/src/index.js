// HQ: one private web app for every business your agents find, with calling through Twilio.
//
// A Cloudflare Worker with a D1 database (binding DB) and the web app in ../public (binding ASSETS).
// Secrets (Workers & Pages → studio-hq → Settings → Variables and Secrets):
//   HQ_PASSWORD                            required: the password you log in with
//   TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN  for calling (then Settings → Connect Twilio in the app)
//   TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID   for the daily call list and missed-call messages
//
// The agents send their businesses to /api/sync after every run, with the agent token shown in Settings.

const AGENTS = { lead: "Websites", security: "Security", studio: "Studio", manual: "Added by you" };
const OWN_STAGES = ["interested", "client", "lost"];
const OUTCOMES = {
  interested: "Talked: interested", not_interested: "Talked: not interested", callback: "Call back later",
  voicemail: "Left a voicemail", no_answer: "No answer", wrong_number: "Wrong number", talked: "Talked",
};
const SESSION_DAYS = 30;
const DAY = 86400000;
const enc = new TextEncoder();

// Database -----------------------------------------------------------------------------------------------
const VIEW = "pipeline_v1";      // a new definition gets a new name, so running copies never see it change
const SCHEMA = [
  `CREATE TABLE IF NOT EXISTS businesses (
     key TEXT PRIMARY KEY, agent TEXT NOT NULL, lead_id TEXT NOT NULL, name TEXT NOT NULL DEFAULT '',
     kind TEXT, city TEXT, state TEXT, website TEXT, email TEXT, phone TEXT, phone_e164 TEXT, socials TEXT,
     preview_url TEXT, status TEXT, touches INTEGER NOT NULL DEFAULT 0, created_at TEXT, first_sent_at TEXT,
     last_sent_at TEXT, replied_at TEXT, handed_over TEXT, reply_text TEXT, extra TEXT, synced_at TEXT,
     stage TEXT, lost_reason TEXT, plan TEXT, plan_label TEXT, price REAL, setup_fee REAL, cycle TEXT, bought_at TEXT,
     renews_at TEXT, start_service INTEGER NOT NULL DEFAULT 0, remind_at TEXT, remind_note TEXT,
     my_phone TEXT, my_email TEXT, calls INTEGER NOT NULL DEFAULT 0, last_call_at TEXT, last_call_outcome TEXT,
     updated_at TEXT)`,
  "CREATE INDEX IF NOT EXISTS businesses_agent ON businesses(agent)",
  "CREATE INDEX IF NOT EXISTS businesses_phone ON businesses(phone_e164)",
  "CREATE INDEX IF NOT EXISTS businesses_my_phone ON businesses(my_phone)",
  `CREATE TABLE IF NOT EXISTS activity (
     id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT NOT NULL, at TEXT NOT NULL, kind TEXT NOT NULL,
     detail TEXT, meta TEXT)`,
  "CREATE INDEX IF NOT EXISTS activity_key ON activity(key, at)",
  "CREATE TABLE IF NOT EXISTS settings (k TEXT PRIMARY KEY, v TEXT)",
  "CREATE TABLE IF NOT EXISTS attempts (ip TEXT NOT NULL, at INTEGER NOT NULL)",
  `CREATE TABLE IF NOT EXISTS calls (
     sid TEXT PRIMARY KEY, key TEXT, number TEXT, direction TEXT, at TEXT, status TEXT, duration INTEGER,
     recording_sid TEXT, activity_id INTEGER)`,
  // The stage you see: your own choice (interested, client, lost) wins; otherwise it follows the agent.
  `CREATE VIEW IF NOT EXISTS ${VIEW} AS SELECT *,
     CASE
       WHEN stage IN ('interested', 'client', 'lost') THEN stage
       WHEN status = 'client' THEN 'client'
       WHEN status = 'replied' THEN 'replied'
       WHEN status = 'emailed' THEN 'contacted'
       WHEN status = 'ready' THEN 'new'
       WHEN status IN ('manual', 'added') THEN 'to_contact'
       WHEN status = 'bounced' AND COALESCE(my_phone, phone_e164, '') != '' THEN 'to_contact'
       WHEN status IN ('finished', 'expired') THEN 'no_reply'
       ELSE 'lost'
     END AS eff,
     COALESCE(my_phone, phone_e164) AS dial,
     COALESCE(my_email, email) AS mail
   FROM businesses`,
];
// Columns added after the first version: older databases get them added once.
const LATER_COLUMNS = [["plan_label", "TEXT"]];
let schemaReady = null;
async function migrate(env) {
  await env.DB.batch(SCHEMA.map((s) => env.DB.prepare(s)));
  const have = new Set((await env.DB.prepare("SELECT name FROM pragma_table_info('businesses')").all()).results.map((r) => r.name));
  for (const [col, type] of LATER_COLUMNS) {
    if (!have.has(col)) await env.DB.prepare(`ALTER TABLE businesses ADD COLUMN ${col} ${type}`).run();
  }
}
function schema(env) {
  schemaReady ??= migrate(env).catch((e) => { schemaReady = null; throw e; });
  return schemaReady;
}

async function getSetting(env, k, fallback = null) {
  const row = await env.DB.prepare("SELECT v FROM settings WHERE k = ?").bind(k).first();
  if (!row) return fallback;
  try { return JSON.parse(row.v); } catch { return fallback; }
}
function setSetting(env, k, v) {
  return env.DB.prepare("INSERT INTO settings (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v")
    .bind(k, JSON.stringify(v)).run();
}
function logActivity(env, key, kind, detail, meta = null, at = nowIso()) {
  return env.DB.prepare("INSERT INTO activity (key, at, kind, detail, meta) VALUES (?, ?, ?, ?, ?)")
    .bind(key, at, kind, detail, meta ? JSON.stringify(meta) : null);
}

// Small helpers ---------------------------------------------------------------------------------------------
const nowIso = () => new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
const today = (tz = "Asia/Beirut", at = Date.now()) => {
  const p = parts(at, tz);
  return `${p.y}-${String(p.m).padStart(2, "0")}-${String(p.d).padStart(2, "0")}`;
};
const clip = (s, n) => (s == null ? null : String(s).slice(0, n));
const b64 = (bytes) => btoa(String.fromCharCode(...bytes));
const b64url = (bytes) => b64(bytes).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const b64urlText = (text) => b64url(enc.encode(text));
const xml = (s) => String(s ?? "").replace(/[<>&"']/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;", "'": "&apos;" }[c]));
const html = (s) => String(s ?? "").replace(/[<>&"]/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;" }[c]));

function e164(phone) {
  const raw = String(phone || "").trim();
  const d = raw.replace(/\D/g, "");
  if (raw.startsWith("+") && d.length >= 8 && d.length <= 15) return "+" + d;
  if (d.length === 10) return "+1" + d;
  if (d.length === 11 && d.startsWith("1")) return "+" + d;
  return null;
}
// +1 numbers outside the US and Canada (the Caribbean, Bermuda) cost international rates, and 900/976 are paid
// lines: HQ never dials them.
const NOT_DOMESTIC = new Set(["242", "246", "264", "268", "284", "345", "441", "473", "649", "658", "664", "721", "758",
                              "767", "784", "809", "829", "849", "868", "869", "876", "900", "976"]);
const usCallable = (n) => {
  const m = /^\+1([2-9]\d{2})[2-9]\d{6}$/.exec(n || "");
  return !!m && !NOT_DOMESTIC.has(m[1]);
};

function addCycle(date, cycle, times = 1) {
  if (!date || !["monthly", "yearly"].includes(cycle)) return null;
  const [y, m, d] = date.split("-").map(Number);
  const months = cycle === "monthly" ? times : 12 * times;
  const target = new Date(Date.UTC(y, m - 1 + months, 1));
  const last = new Date(Date.UTC(target.getUTCFullYear(), target.getUTCMonth() + 1, 0)).getUTCDate();
  target.setUTCDate(Math.min(d, last));
  return target.toISOString().slice(0, 10);
}
const validDate = (s) => /^\d{4}-\d{2}-\d{2}$/.test(s || "") && !Number.isNaN(Date.parse(s + "T00:00:00Z"));
const fmtDay = (s) => (validDate(s) ? new Date(s + "T12:00:00Z").toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" }) : s);

function timingSafeEqual(a, b) {
  const x = enc.encode(String(a)), y = enc.encode(String(b));
  let diff = x.length ^ y.length;
  for (let i = 0; i < Math.max(x.length, y.length); i++) diff |= (x[i] || 0) ^ (y[i] || 0);
  return diff === 0;
}
async function hmac(keyBytes, data, hash = "SHA-256") {
  const key = await crypto.subtle.importKey("raw", keyBytes, { name: "HMAC", hash }, false, ["sign"]);
  return new Uint8Array(await crypto.subtle.sign("HMAC", key, enc.encode(data)));
}
const sha256 = async (text) => new Uint8Array(await crypto.subtle.digest("SHA-256", enc.encode(text)));

// Time zones: when to call a business, shown in Beirut time ------------------------------------------------
const ZONES = {
  "America/New_York": "CT DE DC FL GA IN KY ME MD MA MI NH NJ NY NC OH PA RI SC VT VA WV",
  "America/Chicago": "AL AR IL IA KS LA MN MS MO NE ND OK SD TN TX WI",
  "America/Denver": "CO ID MT NM UT WY", "America/Phoenix": "AZ", "America/Los_Angeles": "CA NV OR WA",
  "America/Anchorage": "AK", "Pacific/Honolulu": "HI",
};
const STATE_TZ = Object.fromEntries(Object.entries(ZONES).flatMap(([tz, s]) => s.split(" ").map((st) => [st, tz])));
const tzFor = (state) => STATE_TZ[String(state || "").toUpperCase()] || "America/New_York";

const FORMATS = new Map();          // making a date formatter is slow, so each time zone gets one, once
function parts(at, tz) {
  let f = FORMATS.get(tz);
  if (!f) {
    f = new Intl.DateTimeFormat("en-US", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit",
                                           hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
    FORMATS.set(tz, f);
  }
  const o = {};
  for (const { type, value } of f.formatToParts(new Date(at))) o[type] = value;
  return { y: +o.year, m: +o.month, d: +o.day, h: +o.hour % 24, mi: +o.minute };
}
function offsetMin(tz, at) {
  const p = parts(at, tz);
  return (Date.UTC(p.y, p.m - 1, p.d, p.h, p.mi) - Math.floor(at / 60000) * 60000) / 60000;
}
function localToUtc(y, m, d, h, mi, tz) {
  const guess = Date.UTC(y, m - 1, d, h, mi);
  return guess - offsetMin(tz, guess) * 60000;
}
const FOOD = /restaurant|cafe|café|coffee|bakery|bar\b|pizza|grill|diner|deli|bistro|brew|pub|taco|sushi|food|kitchen|dessert|donut|ice cream|tea/i;
const TRADE = /plumb|hvac|roof|electric|contractor|heating|cooling|handyman/i;
function windowsFor(kind) {
  if (FOOD.test(kind || "")) return [[14, 0, 16, 30]];            // between lunch and dinner
  if (TRADE.test(kind || "")) return [[8, 0, 10, 0], [15, 0, 17, 0]];   // before or after the day's jobs
  return [[10, 0, 12, 0], [14, 0, 16, 0]];
}
function beirutClock(ms) {
  const p = parts(ms, "Asia/Beirut");
  const h12 = p.h % 12 || 12, ampm = p.h < 12 ? "am" : "pm";
  return { text: p.mi ? `${h12}:${String(p.mi).padStart(2, "0")}` : `${h12}`, ampm };
}
// The next good window to call (today, or tomorrow if today's have passed), in Beirut time.
function callWindow(kind, state, at = Date.now()) {
  const tz = tzFor(state);
  const beirutDay = (ms) => { const p = parts(ms, "Asia/Beirut"); return Date.UTC(p.y, p.m - 1, p.d); };
  for (let dayAhead = 0; dayAhead < 4; dayAhead++) {
    const p = parts(at + dayAhead * DAY, tz);
    const weekday = new Date(Date.UTC(p.y, p.m - 1, p.d)).getUTCDay();
    if (weekday === 0) continue;                                   // nobody wants a sales call on Sunday
    for (const [h1, m1, h2, m2] of windowsFor(kind)) {
      const start = localToUtc(p.y, p.m, p.d, h1, m1, tz), end = localToUtc(p.y, p.m, p.d, h2, m2, tz);
      if (end <= at) continue;
      const a = beirutClock(start), b = beirutClock(end);
      const label = `${a.text}${a.ampm === b.ampm ? "" : a.ampm}–${b.text}${b.ampm}`;
      const days = Math.round((beirutDay(start) - beirutDay(at)) / DAY);
      const when = days <= 0 ? "" : days === 1 ? "tomorrow " :
        new Date(beirutDay(start)).toLocaleDateString("en-US", { weekday: "short", timeZone: "UTC" }) + " ";
      return { start, end, label: `${when}${label}`, now: start <= at && at < end };
    }
  }
  return null;
}
const ago = (iso, at = Date.now()) => (iso ? Math.max(0, Math.floor((at - Date.parse(iso)) / DAY)) : null);

// Sessions -----------------------------------------------------------------------------------------------
async function sessionKey(env) { return sha256("hq-session:" + env.HQ_PASSWORD); }
async function makeSession(env) {
  const exp = Date.now() + SESSION_DAYS * DAY;
  return `${exp}.${b64url(await hmac(await sessionKey(env), "session:" + exp))}`;
}
async function loggedIn(request, env) {
  if (!env.HQ_PASSWORD) return false;
  const m = (request.headers.get("Cookie") || "").match(/(?:^|;\s*)hq=([^;]+)/);
  if (!m) return false;
  const [exp, sig] = m[1].split(".");
  if (!exp || !sig || Number(exp) < Date.now()) return false;
  return timingSafeEqual(sig, b64url(await hmac(await sessionKey(env), "session:" + exp)));
}
const cookie = (value, maxAge) => `hq=${value}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${maxAge}`;

// Responses ------------------------------------------------------------------------------------------------
function json(data, status = 200, headers = {}) {
  return new Response(JSON.stringify(data), {
    status, headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store", ...headers },
  });
}
const twiml = (body) => new Response(`<?xml version="1.0" encoding="UTF-8"?><Response>${body}</Response>`,
  { headers: { "Content-Type": "text/xml; charset=utf-8" } });
const SECURITY_HEADERS = {
  "Content-Security-Policy": [
    "default-src 'self'", "script-src 'self' https://cdn.jsdelivr.net", "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:", "media-src 'self' blob: https://*.twilio.com", "font-src 'self'",
    "connect-src 'self' https://*.twilio.com wss://*.twilio.com", "frame-ancestors 'none'", "base-uri 'none'",
    "form-action 'self'",
  ].join("; "),
  "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY",
  "Permissions-Policy": "microphone=(self), camera=(), geolocation=()",
};
function withHeaders(response) {
  const r = new Response(response.body, response);
  for (const [k, v] of Object.entries(SECURITY_HEADERS)) r.headers.set(k, v);
  return r;
}

// The router --------------------------------------------------------------------------------------------------
export default {
  async fetch(request, env, ctx) {
    try {
      return await route(request, env, ctx);
    } catch (e) {
      console.log("error", e && e.stack || e);
      return json({ error: "Something went wrong in HQ. Try again in a minute." }, 500);
    }
  },
  async scheduled(event, env, ctx) {
    ctx.waitUntil(hourly(env, event.scheduledTime).catch((e) => console.log("cron error", e && e.stack || e)));
  },
};

async function route(request, env, ctx) {
  const url = new URL(request.url);
  const path = url.pathname;
  if (!path.startsWith("/api/") && !path.startsWith("/twilio/")) {
    return withHeaders(await env.ASSETS.fetch(request));
  }
  if (!env.DB) return json({ error: "The D1 database isn't connected to this Worker (binding DB)." }, 500);
  await schema(env);

  if (path.startsWith("/twilio/")) return twilioWebhook(request, env, path.slice(8), url);
  if (path === "/api/sync" && request.method === "POST") return sync(request, env);
  if (path === "/api/login" && request.method === "POST") return login(request, env, url);
  if (path === "/api/logout" && request.method === "POST") return json({ ok: true }, 200, { "Set-Cookie": cookie("", 0) });

  if (!(await loggedIn(request, env))) return json({ error: "login", password_set: !!env.HQ_PASSWORD }, 401);
  if (request.method !== "GET") {
    const origin = request.headers.get("Origin");                 // a page on another site can't act for you
    if (origin && origin !== url.origin) return json({ error: "Wrong origin" }, 403);
    if (!(request.headers.get("Content-Type") || "").includes("application/json")) {
      return json({ error: "Send JSON" }, 415);
    }
  }
  await rememberUrl(env, url);

  const m = path.match(/^\/api\/business\/([^/]+)$/);
  if (m && request.method === "GET") return businessDetail(env, decodeURIComponent(m[1]));
  if (m && request.method === "POST") return businessAction(env, decodeURIComponent(m[1]), await request.json());
  const rec = path.match(/^\/api\/recording\/(RE[0-9a-f]{32})$/);
  if (rec) return recording(env, rec[1]);

  const routes = {
    "GET /api/me": () => me(env),
    "GET /api/today": () => todayView(env),
    "GET /api/businesses": () => listBusinesses(env, url.searchParams),
    "POST /api/businesses": async () => addBusiness(env, await request.json()),
    "GET /api/clients": () => clientsView(env),
    "GET /api/settings": () => settingsView(env, url),
    "POST /api/settings": async () => saveSettings(env, await request.json()),
    "POST /api/settings/token": () => newToken(env),
    "POST /api/telegram/test": () => telegramTest(env, url),
    "GET /api/digest": async () => json({ text: (await digestText(env)) || "" }),
    "POST /api/twilio/connect": () => twilioConnect(env, url),
    "GET /api/twilio/token": () => twilioToken(env),
  };
  const handler = routes[`${request.method} ${path}`];
  return handler ? handler() : json({ error: "Not found" }, 404);
}

async function rememberUrl(env, url) {
  const known = await getSetting(env, "url");
  if (known !== url.origin) await setSetting(env, "url", url.origin);
}

async function login(request, env, url) {
  if (!env.HQ_PASSWORD) return json({ error: "Add the HQ_PASSWORD secret to this Worker first." }, 400);
  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  const since = Date.now() - 15 * 60000;
  const tries = await env.DB.prepare("SELECT COUNT(*) AS n FROM attempts WHERE ip = ? AND at > ?").bind(ip, since).first();
  if (tries && tries.n >= 8) return json({ error: "Too many tries. Wait 15 minutes." }, 429);
  let body = {};
  try { body = await request.json(); } catch { /* empty */ }
  const ok = timingSafeEqual(b64(await sha256(String(body.password || ""))), b64(await sha256(env.HQ_PASSWORD)));
  if (!ok) {
    await env.DB.prepare("INSERT INTO attempts (ip, at) VALUES (?, ?)").bind(ip, Date.now()).run();
    return json({ error: "Wrong password." }, 401);
  }
  await rememberUrl(env, url);
  return json({ ok: true }, 200, { "Set-Cookie": cookie(await makeSession(env), SESSION_DAYS * 86400) });
}

// From the agents ------------------------------------------------------------------------------------------
const AGENT_FIELDS = ["name", "kind", "city", "state", "website", "email", "phone", "phone_e164", "socials",
                      "preview_url", "status", "touches", "created_at", "first_sent_at", "last_sent_at", "replied_at",
                      "handed_over", "reply_text", "extra"];
const UPSERT = `INSERT INTO businesses (key, agent, lead_id, ${AGENT_FIELDS.join(", ")}, synced_at, updated_at)
  VALUES (${Array(AGENT_FIELDS.length + 5).fill("?").join(", ")})
  ON CONFLICT(key) DO UPDATE SET ${AGENT_FIELDS.map((f) => `${f} = excluded.${f}`).join(", ")},
    synced_at = excluded.synced_at,
    updated_at = CASE WHEN businesses.status IS NOT excluded.status OR businesses.touches IS NOT excluded.touches
                      THEN excluded.synced_at ELSE businesses.updated_at END`;

function agentEvent(old, rec) {
  if (old && old.status === rec.status && (old.touches || 0) === (rec.touches || 0)) return null;
  if (rec.status === "emailed") {
    const t = rec.touches || 1;
    if (old && old.status === "emailed" && t > (old.touches || 0)) return `Follow-up ${t - 1} sent`;
    return t > 1 ? `Emailed (${t - 1} follow-up${t > 2 ? "s" : ""} sent)` : "Preview emailed";
  }
  return {
    ready: "Preview made, email queued", manual: "Preview made. No email: call or message them",
    finished: "All follow-ups sent, no reply", replied: "They replied", client: "Became a client",
    opted_out: "Asked not to be contacted", bounced: "Their email bounced", expired: "Preview page expired",
  }[rec.status] || null;
}

function cleanRecord(agent, r) {
  const socials = r.socials && typeof r.socials === "object" ? JSON.stringify(r.socials).slice(0, 2000) : null;
  const extra = r.extra && typeof r.extra === "object" ? JSON.stringify(r.extra).slice(0, 2000) : null;
  const phone = clip(r.phone, 40);
  return {
    key: `${agent}:${String(r.id).slice(0, 200)}`, lead_id: String(r.id).slice(0, 200),
    name: clip(r.name, 200) || String(r.id).slice(0, 200), kind: clip(r.kind, 80), city: clip(r.city, 80),
    state: clip(r.state, 20), website: clip(r.website, 500), email: clip(r.email, 200), phone,
    phone_e164: e164(phone), socials, preview_url: clip(r.preview_url, 500), status: clip(r.status, 30),
    touches: Number.isFinite(+r.touches) ? Math.max(0, Math.min(99, Math.floor(+r.touches))) : 0,
    created_at: clip(r.created_at, 40), first_sent_at: clip(r.first_sent_at, 40), last_sent_at: clip(r.last_sent_at, 40),
    replied_at: clip(r.replied_at, 40), handed_over: clip(r.handed_over, 40), reply_text: clip(r.reply_text, 3000),
    extra,
  };
}

async function sync(request, env) {
  const auth = (request.headers.get("Authorization") || "").replace(/^Bearer\s+/i, "");
  const token = await getSetting(env, "agent_token");
  if (!token || !auth || !timingSafeEqual(auth, token)) return json({ error: "Wrong agent token" }, 401);
  if (Number(request.headers.get("Content-Length") || 0) > 3_000_000) return json({ error: "Too big" }, 413);
  const body = await request.json();
  const agent = String(body.agent || "");
  if (!["lead", "security", "studio"].includes(agent)) return json({ error: "Unknown agent" }, 400);
  const records = (Array.isArray(body.businesses) ? body.businesses : [])
    .filter((r) => r && r.id && r.status !== "skipped").slice(0, 500).map((r) => cleanRecord(agent, r));
  const at = nowIso();

  const old = new Map();
  for (let i = 0; i < records.length; i += 90) {
    const keys = records.slice(i, i + 90).map((r) => r.key);
    const rows = await env.DB.prepare(`SELECT key, status, touches FROM businesses WHERE key IN (${keys.map(() => "?").join(",")})`)
      .bind(...keys).all();
    for (const row of rows.results) old.set(row.key, row);
  }
  const statements = [];
  for (const r of records) {
    statements.push(env.DB.prepare(UPSERT).bind(r.key, agent, r.lead_id, ...AGENT_FIELDS.map((f) => r[f] ?? null), at, at));
    const event = agentEvent(old.get(r.key), r);
    if (event) statements.push(logActivity(env, r.key, "agent", event, null, at));
  }
  for (let i = 0; i < statements.length; i += 400) await env.DB.batch(statements.slice(i, i + 400));

  if (body.offer && typeof body.offer === "object") await setSetting(env, `offer:${agent}`, body.offer);
  const seen = (await getSetting(env, `sync:${agent}`, {})) || {};
  await setSetting(env, `sync:${agent}`, { at, received: records.length, total: (seen.total || 0) + records.length,
                                           mode: clip(body.mode, 10) });

  // What you decided here goes back to the agent: stop emailing anyone you're handling yourself.
  const stop = await env.DB.prepare(`SELECT lead_id FROM businesses WHERE agent = ? AND stage IN ('interested', 'client', 'lost')
                                     AND status IN ('ready', 'emailed', 'manual')`).bind(agent).all();
  const reply = { ok: true, received: records.length, stop: stop.results.map((r) => r.lead_id) };
  if (agent === "studio") {
    const onboard = await env.DB.prepare(`SELECT lead_id, plan, COALESCE(my_email, email) AS email FROM businesses
      WHERE agent = 'studio' AND stage = 'client' AND start_service = 1 AND COALESCE(status, '') != 'client'`).all();
    reply.onboard = onboard.results.map((r) => ({ id: r.lead_id, plan: r.plan, email: r.email }));
  }
  return json(reply);
}

// Views ------------------------------------------------------------------------------------------------------
const CARD = `key, agent, name, kind, city, state, eff, status, touches, dial, mail, preview_url, first_sent_at, created_at,
  replied_at, reply_text, calls, last_call_at, last_call_outcome, remind_at, remind_note, plan, plan_label, price, cycle,
  bought_at, renews_at, updated_at, synced_at, handed_over`;

function card(row, at = Date.now()) {
  const c = { ...row };
  if (c.reply_text) c.reply_text = c.reply_text.slice(0, 280);
  return c;
}

function callReason(b, at = Date.now()) {
  if (b.eff === "replied") return "They replied: call them back";
  if (b.eff === "interested") return "Interested: follow up";
  if (b.last_call_outcome === "callback") return "Asked you to call back";
  if (b.eff === "contacted") {
    const d = ago(b.first_sent_at, at);
    return d === 0 ? "Emailed today" : `Emailed ${d} day${d === 1 ? "" : "s"} ago, no reply yet`;
  }
  if (b.eff === "to_contact") return b.status === "bounced" ? "Their email bounced" : "No email: a call is the way in";
  if (b.eff === "no_reply") return "No reply to the emails: one last try";
  return "";
}

async function callList(env, at = Date.now(), limit = 12) {
  const recent = new Date(at - 3 * DAY).toISOString();
  const rows = (await env.DB.prepare(`SELECT ${CARD} FROM ${VIEW}
    WHERE dial IS NOT NULL AND dial != '' AND eff IN ('replied', 'interested', 'contacted', 'to_contact', 'no_reply')
      AND COALESCE(last_call_outcome, '') NOT IN ('not_interested', 'wrong_number', 'talked')
      AND (last_call_at IS NULL OR last_call_at < ? OR last_call_outcome = 'callback')
      AND (remind_at IS NULL OR remind_at <= ?)
    ORDER BY CASE eff WHEN 'replied' THEN 0 WHEN 'interested' THEN 1 WHEN 'contacted' THEN 2 WHEN 'to_contact' THEN 3 ELSE 4 END,
      COALESCE(first_sent_at, created_at) ASC
    LIMIT 80`).bind(recent, today("Asia/Beirut", at)).all()).results;
  const picked = [];
  for (const b of rows) {
    if (!usCallable(b.dial)) continue;
    const sent = ago(b.first_sent_at, at);
    if (b.eff === "contacted" && (sent === null || sent < 2 || sent > 14) && b.last_call_outcome !== "callback") continue;
    if (b.eff === "no_reply" && b.calls > 0) continue;
    if (b.eff === "to_contact" && b.calls >= 2) continue;
    if (b.eff === "contacted" && b.calls >= 2) continue;
    picked.push({ ...card(b, at), why: callReason(b, at), window: callWindow(b.kind, b.state, at) });
    if (picked.length >= limit) break;
  }
  return picked;
}

async function todayView(env) {
  const at = Date.now();
  const day = today("Asia/Beirut", at);
  const week = new Date(at + 7 * DAY).toISOString().slice(0, 10);
  const q = (sql, ...args) => env.DB.prepare(sql).bind(...args).all().then((r) => r.results.map((b) => card(b, at)));
  const [calls, replies, interested, renewals, reminders, counts] = await Promise.all([
    callList(env, at),
    q(`SELECT ${CARD} FROM ${VIEW} WHERE eff = 'replied' ORDER BY replied_at DESC LIMIT 20`),
    q(`SELECT ${CARD} FROM ${VIEW} WHERE eff = 'interested' ORDER BY updated_at DESC LIMIT 20`),
    q(`SELECT ${CARD} FROM ${VIEW} WHERE eff = 'client' AND renews_at IS NOT NULL AND renews_at <= ? ORDER BY renews_at LIMIT 20`, week),
    q(`SELECT ${CARD} FROM ${VIEW} WHERE remind_at IS NOT NULL AND remind_at <= ? ORDER BY remind_at LIMIT 20`, day),
    env.DB.prepare(`SELECT eff, COUNT(*) AS n FROM ${VIEW} GROUP BY eff`).all().then((r) => Object.fromEntries(r.results.map((x) => [x.eff, x.n]))),
  ]);
  return json({ day, calls, replies, interested, renewals, reminders, counts });
}

async function listBusinesses(env, params) {
  const where = [], args = [];
  const stage = params.get("stage"), agent = params.get("agent"), q = (params.get("q") || "").trim();
  if (stage && stage !== "all") { where.push("eff = ?"); args.push(stage); }
  if (agent && agent !== "all") { where.push("agent = ?"); args.push(agent); }
  if (q) {
    where.push("(name LIKE ? OR city LIKE ? OR COALESCE(my_email, email, '') LIKE ? OR COALESCE(website, '') LIKE ? OR COALESCE(dial, '') LIKE ?)");
    const like = `%${q.replace(/[%_]/g, "")}%`;
    args.push(like, like, like, like, `%${q.replace(/\D/g, "") || "x"}%`);
  }
  const limit = Math.min(100, Math.max(1, +params.get("limit") || 50)), offset = Math.max(0, +params.get("offset") || 0);
  const sql = `SELECT ${CARD} FROM ${VIEW} ${where.length ? "WHERE " + where.join(" AND ") : ""}
               ORDER BY COALESCE(updated_at, synced_at) DESC, name LIMIT ? OFFSET ?`;
  const rows = (await env.DB.prepare(sql).bind(...args, limit + 1, offset).all()).results;
  const counts = Object.fromEntries((await env.DB.prepare(
    `SELECT eff, COUNT(*) AS n FROM ${VIEW} ${agent && agent !== "all" ? "WHERE agent = ?" : ""} GROUP BY eff`)
    .bind(...(agent && agent !== "all" ? [agent] : [])).all()).results.map((x) => [x.eff, x.n]));
  return json({ items: rows.slice(0, limit).map((b) => card(b)), more: rows.length > limit, counts });
}

const monthly = (b) => (b.cycle === "monthly" ? +b.price || 0 : b.cycle === "yearly" ? (+b.price || 0) / 12 : 0);

async function clientsView(env) {
  const rows = (await env.DB.prepare(`SELECT ${CARD}, setup_fee FROM ${VIEW} WHERE eff = 'client'
    ORDER BY CASE WHEN renews_at IS NULL THEN 1 ELSE 0 END, renews_at, name`).all()).results;
  const mrr = rows.reduce((s, b) => s + monthly(b), 0);
  const byAgent = {};
  for (const b of rows) byAgent[b.agent] = (byAgent[b.agent] || 0) + 1;
  return json({ items: rows.map((b) => card(b)), mrr: Math.round(mrr * 100) / 100, count: rows.length, by_agent: byAgent,
                today: today() });
}

async function businessDetail(env, key) {
  const b = await env.DB.prepare(`SELECT * FROM ${VIEW} WHERE key = ?`).bind(key).first();
  if (!b) return json({ error: "Not found" }, 404);
  const activity = (await env.DB.prepare("SELECT id, at, kind, detail, meta FROM activity WHERE key = ? ORDER BY at DESC, id DESC LIMIT 150")
    .bind(key).all()).results.map((a) => ({ ...a, meta: a.meta ? JSON.parse(a.meta) : null }));
  for (const f of ["socials", "extra"]) { try { b[f] = b[f] ? JSON.parse(b[f]) : null; } catch { b[f] = null; } }
  const offer = await getSetting(env, `offer:${b.agent}`, null);
  return json({ business: { ...b, why: callReason(b), window: b.dial ? callWindow(b.kind, b.state) : null },
                activity, offer, plans: plansFor(b.agent, offer) });
}

// Plans and prices per agent, from what each agent sends (its config.yaml "offer").
function plansFor(agent, offer) {
  const o = offer || {};
  if (agent === "lead") {
    return [{ id: "website", label: "Website", price: o.monthly_price ?? 20, setup_fee: o.setup_price ?? 120, cycle: "monthly" }];
  }
  if (agent === "security") {
    return [{ id: "monitoring", label: "Monitoring", price: o.monthly_price ?? 70, cycle: "monthly" },
            { id: "pentest", label: "Full pentest", price: o.full_pentest_price ?? 150, cycle: "once" }];
  }
  if (agent === "studio") {
    return [{ id: "social", label: "Social", price: o.social_monthly ?? 99, cycle: "monthly" },
            { id: "design", label: "Design", price: o.design_monthly ?? 49, cycle: "monthly" },
            { id: "bundle", label: "Social + Design", price: o.bundle_monthly ?? 129, cycle: "monthly" }];
  }
  return [{ id: "custom", label: "Custom", price: 0, cycle: "monthly" }];
}

async function addBusiness(env, body) {
  const name = clip((body.name || "").trim(), 200);
  if (!name) return json({ error: "Give the business a name." }, 400);
  const id = `${Date.now().toString(36)}${b64url(crypto.getRandomValues(new Uint8Array(4)))}`;
  const key = `manual:${id}`, at = nowIso();
  const phone = clip(body.phone, 40);
  await env.DB.batch([
    env.DB.prepare(`INSERT INTO businesses (key, agent, lead_id, name, kind, city, state, website, email, phone, phone_e164,
      status, created_at, synced_at, updated_at) VALUES (?, 'manual', ?, ?, ?, ?, ?, ?, ?, ?, ?, 'added', ?, ?, ?)`)
      .bind(key, id, name, clip(body.kind, 80), clip(body.city, 80), clip((body.state || "").toUpperCase(), 20),
            clip(body.website, 500), clip(body.email, 200), phone, e164(phone), at, at, at),
    logActivity(env, key, "stage", "Added by you", null, at),
  ]);
  return json({ ok: true, key });
}

async function businessAction(env, key, body) {
  const b = await env.DB.prepare(`SELECT * FROM ${VIEW} WHERE key = ?`).bind(key).first();
  if (!b) return json({ error: "Not found" }, 404);
  const at = nowIso(), day = today();
  const s = [];
  const set = (fields) => {
    const cols = Object.keys(fields);
    s.push(env.DB.prepare(`UPDATE businesses SET ${cols.map((c) => `${c} = ?`).join(", ")}, updated_at = ? WHERE key = ?`)
      .bind(...cols.map((c) => fields[c]), at, key));
  };
  switch (body.action) {
    case "note": {
      const text = clip((body.text || "").trim(), 4000);
      if (!text) return json({ error: "Write something first." }, 400);
      s.push(logActivity(env, key, "note", text, null, at));
      break;
    }
    case "stage": {
      const stage = body.stage || null;
      if (stage && !["interested", "lost"].includes(stage)) return json({ error: "Unknown stage" }, 400);
      set({ stage, lost_reason: stage === "lost" ? clip(body.reason || "Not interested", 200) : null });
      s.push(logActivity(env, key, "stage", stage === "interested" ? "Marked interested"
        : stage === "lost" ? `Marked lost: ${clip(body.reason || "Not interested", 200)}` : "Back to following the agent", null, at));
      break;
    }
    case "bought": {
      const boughtAt = validDate(body.bought_at) ? body.bought_at : day;
      const cycle = ["monthly", "yearly", "once"].includes(body.cycle) ? body.cycle : "monthly";
      const price = Math.max(0, +body.price || 0), setup = Math.max(0, +body.setup_fee || 0);
      const renews = validDate(body.renews_at) ? body.renews_at : addCycle(boughtAt, cycle);
      const plan = clip(body.plan || "custom", 40), label = clip(body.plan_label || plan, 60);
      set({ stage: "client", lost_reason: null, plan, plan_label: label, price, setup_fee: setup, cycle, bought_at: boughtAt,
            renews_at: cycle === "once" ? null : renews, start_service: b.agent === "studio" && body.start_service ? 1 : 0 });
      const money = `$${price}${cycle === "monthly" ? "/month" : cycle === "yearly" ? "/year" : ""}${setup ? ` + $${setup} setup` : ""}`;
      s.push(logActivity(env, key, "bought", `Bought ${label}: ${money}${cycle === "once" ? "" : `. First renewal ${fmtDay(renews)}`}`,
                         { plan, price, setup_fee: setup, cycle, bought_at: boughtAt }, at));
      break;
    }
    case "paid": {
      if (b.eff !== "client" || !["monthly", "yearly"].includes(b.cycle)) return json({ error: "Not a paying client" }, 400);
      const from = b.renews_at || day;
      const next = addCycle(from, b.cycle);
      set({ renews_at: next });
      s.push(logActivity(env, key, "paid", `Paid $${b.price} for ${fmtDay(from)} to ${fmtDay(next)}. Next renewal ${fmtDay(next)}`,
                         { amount: b.price, period_from: from, next }, at));
      break;
    }
    case "renews": {
      if (!validDate(body.date)) return json({ error: "Pick a date" }, 400);
      set({ renews_at: body.date });
      s.push(logActivity(env, key, "paid", `Next renewal moved to ${fmtDay(body.date)}`, null, at));
      break;
    }
    case "cancel": {
      set({ stage: "lost", lost_reason: "Cancelled", renews_at: null, start_service: 0 });
      s.push(logActivity(env, key, "stage", "Cancelled their plan", null, at));
      break;
    }
    case "remind": {
      const date = body.date && validDate(body.date) ? body.date : null;
      set({ remind_at: date, remind_note: date ? clip(body.note || "Follow up", 200) : null });
      s.push(logActivity(env, key, "remind", date ? `Reminder for ${fmtDay(date)}: ${clip(body.note || "Follow up", 200)}` : "Reminder cleared", null, at));
      break;
    }
    case "contact": {
      const phone = body.phone !== undefined ? (body.phone ? e164(body.phone) : null) : b.my_phone;
      if (body.phone && !phone) return json({ error: "That phone number doesn't look right." }, 400);
      const email = body.email !== undefined ? clip((body.email || "").trim(), 200) || null : b.my_email;
      set({ my_phone: phone, my_email: email });
      s.push(logActivity(env, key, "note", "Contact details updated", null, at));
      break;
    }
    case "call_outcome": {
      const outcome = body.outcome in OUTCOMES ? body.outcome : "talked";
      const fields = { last_call_outcome: outcome };
      if (outcome === "interested") Object.assign(fields, { stage: "interested", lost_reason: null });
      if (outcome === "not_interested") Object.assign(fields, { stage: "lost", lost_reason: "Not interested (call)" });
      if (outcome === "wrong_number") Object.assign(fields, { my_phone: null });
      if (outcome === "callback" && validDate(body.date)) Object.assign(fields, { remind_at: body.date, remind_note: "Call back" });
      set(fields);
      const note = clip((body.note || "").trim(), 2000);
      s.push(logActivity(env, key, "call", `${OUTCOMES[outcome]}${outcome === "callback" && validDate(body.date) ? ` on ${fmtDay(body.date)}` : ""}${note ? `: ${note}` : ""}`,
                         { outcome, sid: clip(body.sid, 40) }, at));
      break;
    }
    default:
      return json({ error: "Unknown action" }, 400);
  }
  await env.DB.batch(s);
  return businessDetail(env, key);
}

// Settings ------------------------------------------------------------------------------------------------
async function agentToken(env) {
  let token = await getSetting(env, "agent_token");
  if (!token) {
    token = b64url(crypto.getRandomValues(new Uint8Array(24)));
    await setSetting(env, "agent_token", token);
  }
  return token;
}
async function newToken(env) {
  const token = b64url(crypto.getRandomValues(new Uint8Array(24)));
  await setSetting(env, "agent_token", token);
  return json({ token });
}
async function me(env) {
  const twilio = await getSetting(env, "twilio");
  return json({ ok: true, twilio: !!(twilio && twilio.app_sid && env.TWILIO_AUTH_TOKEN), number: twilio && twilio.number,
                name: (await getSetting(env, "name")) || "HQ" });
}
async function settingsView(env, url) {
  const agents = {};
  for (const a of ["lead", "security", "studio"]) agents[a] = await getSetting(env, `sync:${a}`);
  const twilio = (await getSetting(env, "twilio")) || {};
  const counts = Object.fromEntries((await env.DB.prepare("SELECT agent, COUNT(*) AS n FROM businesses GROUP BY agent").all())
    .results.map((r) => [r.agent, r.n]));
  return json({
    url: url.origin, token: await agentToken(env), agents, counts,
    twilio: { secrets: !!(env.TWILIO_ACCOUNT_SID && env.TWILIO_AUTH_TOKEN), connected: !!twilio.app_sid,
              number: twilio.number || null, connected_at: twilio.at || null },
    telegram: !!(botToken(env) && chatId(env)),
    digest_hour: (await getSetting(env, "digest_hour")) ?? 20, name: (await getSetting(env, "name")) || "",
  });
}
async function saveSettings(env, body) {
  if (body.digest_hour !== undefined) {
    const h = Math.floor(+body.digest_hour);
    if (!(h >= 0 && h <= 23)) return json({ error: "Pick an hour from 0 to 23" }, 400);
    await setSetting(env, "digest_hour", h);
  }
  if (body.name !== undefined) await setSetting(env, "name", clip((body.name || "").trim(), 80));
  return json({ ok: true });
}

// Telegram ---------------------------------------------------------------------------------------------------
// Forgiving about how the secrets were pasted: spaces around them, a "bot" in front of the token, or the chat ID
// copied together with the name next to it ("5365752518 (Omar)").
const botToken = (env) => String(env.TELEGRAM_BOT_TOKEN || "").trim().replace(/^bot(?=\d+:)/i, "");
const chatId = (env) => (String(env.TELEGRAM_CHAT_ID || "").match(/-?\d{5,}/) || [""])[0];

function telegramReason(status, body) {
  let d = "";
  try { d = JSON.parse(body).description || ""; } catch { d = body.slice(0, 120); }
  if (status === 401 || status === 404) return "Telegram doesn't recognise the bot token. Copy it again from @BotFather (/mybots → your bot → API Token), with nothing before or after it.";
  if (/initiate conversation|blocked by the user|deactivated/i.test(d)) return "The bot isn't allowed to message you yet: open your bot in Telegram and press Start, then try again.";
  if (/chat not found/i.test(d)) return "Telegram can't find that chat: check TELEGRAM_CHAT_ID (just the number), and press Start in your bot.";
  return `Telegram said: ${d || "error " + status}`;
}

async function telegram(env, text) {
  const token = botToken(env), chat = chatId(env);
  if (!token || !chat) return { ok: false, why: "Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to this Worker's secrets first." };
  const r = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chat, text: text.slice(0, 4000), parse_mode: "HTML", disable_web_page_preview: true }),
  });
  if (r.ok) return { ok: true };
  const body = await r.text();
  console.log("telegram", r.status, body.slice(0, 200));
  return { ok: false, why: telegramReason(r.status, body) };
}
async function telegramTest(env, url) {
  const sent = await telegram(env, `HQ is connected. Your daily call list comes here. <a href="${html(url.origin)}/">Open HQ</a>`);
  return sent.ok ? json({ ok: true }) : json({ error: sent.why }, 502);
}

async function digestText(env, at = Date.now()) {
  const base = (await getSetting(env, "url")) || "";
  const link = (b) => `<a href="${html(base)}/b/${encodeURIComponent(b.key)}">${html(b.name)}</a>`;
  const calls = await callList(env, at, 10);
  const replies = (await env.DB.prepare(`SELECT key, name FROM ${VIEW} WHERE eff = 'replied' ORDER BY replied_at DESC LIMIT 8`).all()).results;
  const week = new Date(at + 7 * DAY).toISOString().slice(0, 10);
  const renewals = (await env.DB.prepare(`SELECT key, name, plan, plan_label, price, renews_at FROM ${VIEW} WHERE eff = 'client' AND renews_at IS NOT NULL
    AND renews_at <= ? ORDER BY renews_at LIMIT 10`).bind(week).all()).results;
  const reminders = (await env.DB.prepare(`SELECT key, name, remind_note FROM ${VIEW} WHERE remind_at IS NOT NULL AND remind_at <= ?
    ORDER BY remind_at LIMIT 10`).bind(today("Asia/Beirut", at)).all()).results;
  if (!calls.length && !replies.length && !renewals.length && !reminders.length) return null;
  const p = parts(at, "Asia/Beirut");
  const dayName = new Date(Date.UTC(p.y, p.m - 1, p.d)).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" });
  const lines = [`<b>HQ · ${dayName}</b>`];
  if (calls.length) {
    lines.push("", `📞 <b>${calls.length} call${calls.length === 1 ? "" : "s"} to make</b> (best times, Beirut time)`);
    calls.forEach((b, i) => lines.push(`${i + 1}. ${link(b)} · ${html(b.city || AGENTS[b.agent])}${b.state ? ", " + html(b.state) : ""}`
      + `${b.window ? " · " + html(b.window.label) : ""}\n    <i>${html(b.why)}</i>`));
  }
  if (replies.length) lines.push("", `↩️ <b>${replies.length} repl${replies.length === 1 ? "y" : "ies"} waiting</b>: ${replies.map(link).join(", ")}`);
  if (renewals.length) {
    lines.push("", "🔁 <b>Renewals this week</b>");
    for (const b of renewals) lines.push(`• ${link(b)} · ${html(b.plan_label || b.plan || "")} $${b.price ?? ""} · ${html(fmtDay(b.renews_at))}`);
  }
  if (reminders.length) {
    lines.push("", "⏰ <b>Reminders</b>");
    for (const b of reminders) lines.push(`• ${link(b)}: ${html(b.remind_note || "Follow up")}`);
  }
  if (base) lines.push("", `<a href="${html(base)}/">Open HQ</a>`);
  return lines.join("\n");
}

async function hourly(env, at = Date.now()) {
  await schema(env);
  await env.DB.prepare("DELETE FROM attempts WHERE at < ?").bind(at - DAY).run();
  const hour = parts(at, "Asia/Beirut").h, day = today("Asia/Beirut", at);
  const want = (await getSetting(env, "digest_hour")) ?? 20;
  if (hour !== want || (await getSetting(env, "digest_date")) === day) return;
  await setSetting(env, "digest_date", day);
  const text = await digestText(env, at);
  if (text) await telegram(env, text);
}

// Twilio --------------------------------------------------------------------------------------------------------
const twilioApi = (env, path, form) => fetch(`https://api.twilio.com/2010-04-01/Accounts/${env.TWILIO_ACCOUNT_SID}${path}`, {
  method: form ? "POST" : "GET",
  headers: { Authorization: "Basic " + btoa(`${env.TWILIO_ACCOUNT_SID}:${env.TWILIO_AUTH_TOKEN}`),
             ...(form ? { "Content-Type": "application/x-www-form-urlencoded" } : {}) },
  body: form ? new URLSearchParams(form) : undefined,
});

async function secretKey(env) {
  return crypto.subtle.importKey("raw", await sha256("hq-twilio:" + env.TWILIO_AUTH_TOKEN), "AES-GCM", false, ["encrypt", "decrypt"]);
}
async function seal(env, text) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const data = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv }, await secretKey(env), enc.encode(text)));
  return `${b64(iv)}.${b64(data)}`;
}
async function unseal(env, sealed) {
  const [iv, data] = String(sealed || "").split(".").map((s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0)));
  return new TextDecoder().decode(await crypto.subtle.decrypt({ name: "AES-GCM", iv }, await secretKey(env), data));
}

async function twilioConnect(env, url) {
  if (!env.TWILIO_ACCOUNT_SID || !env.TWILIO_AUTH_TOKEN) {
    return json({ error: "Add TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN to this Worker's secrets first." }, 400);
  }
  const fail = async (r, what) => json({ error: `Twilio refused to ${what} (${r.status}): ${(await r.text()).slice(0, 200)}` }, 502);
  const nums = await twilioApi(env, "/IncomingPhoneNumbers.json?PageSize=50");
  if (!nums.ok) return fail(nums, "list your numbers");
  const list = ((await nums.json()).incoming_phone_numbers || []).filter((n) => !n.capabilities || n.capabilities.voice !== false);
  if (!list.length) return json({ error: "Your Twilio account has no phone number yet. Buy a US local number in Twilio first." }, 400);
  const saved = (await getSetting(env, "twilio")) || {};
  const number = list.find((n) => n.sid === saved.number_sid) || list[0];

  let keySid = saved.key_sid, keySecret = saved.key_secret;
  if (!keySid || !keySecret) {
    const k = await twilioApi(env, "/Keys.json", { FriendlyName: "HQ calling" });
    if (!k.ok) return fail(k, "make an API key");
    const key = await k.json();
    keySid = key.sid;
    keySecret = await seal(env, key.secret);
  }
  const app = { FriendlyName: "HQ calling", VoiceUrl: `${url.origin}/twilio/voice`, VoiceMethod: "POST" };
  let appSid = saved.app_sid;
  let a = appSid ? await twilioApi(env, `/Applications/${appSid}.json`, app) : null;
  if (!a || !a.ok) a = await twilioApi(env, "/Applications.json", app);
  if (!a.ok) return fail(a, "make the calling app");
  appSid = (await a.json()).sid;
  const n = await twilioApi(env, `/IncomingPhoneNumbers/${number.sid}.json`,
                            { VoiceUrl: `${url.origin}/twilio/incoming`, VoiceMethod: "POST" });
  if (!n.ok) return fail(n, "point your number at HQ");
  const twilio = { number: number.phone_number, number_sid: number.sid, app_sid: appSid, key_sid: keySid,
                   key_secret: keySecret, at: nowIso() };
  await setSetting(env, "twilio", twilio);
  return json({ ok: true, number: number.phone_number });
}

async function twilioToken(env) {
  const t = await getSetting(env, "twilio");
  if (!t || !t.app_sid || !env.TWILIO_AUTH_TOKEN) return json({ error: "Connect Twilio in Settings first." }, 400);
  let secret;
  try { secret = await unseal(env, t.key_secret); } catch {
    return json({ error: "The Twilio auth token changed. Press Connect Twilio in Settings again." }, 400);
  }
  const now = Math.floor(Date.now() / 1000);
  const header = { alg: "HS256", typ: "JWT", cty: "twilio-fpa;v=1" };
  const payload = { jti: `${t.key_sid}-${now}`, iss: t.key_sid, sub: env.TWILIO_ACCOUNT_SID, iat: now, nbf: now, exp: now + 3600,
                    grants: { identity: "omar", voice: { incoming: { allow: true }, outgoing: { application_sid: t.app_sid } } } };
  const body = `${b64urlText(JSON.stringify(header))}.${b64urlText(JSON.stringify(payload))}`;
  const sig = b64url(await hmac(enc.encode(secret), body));
  return json({ token: `${body}.${sig}`, number: t.number, identity: "omar" });
}

async function twilioValid(request, env, params) {
  const sig = request.headers.get("X-Twilio-Signature") || "";
  if (!env.TWILIO_AUTH_TOKEN || !sig) return false;
  const data = request.url + Object.keys(params).sort().map((k) => k + params[k]).join("");
  return timingSafeEqual(b64(await hmac(enc.encode(env.TWILIO_AUTH_TOKEN), data, "SHA-1")), sig);
}

async function byPhone(env, number) {
  if (!number) return null;
  return env.DB.prepare(`SELECT key, name, agent FROM ${VIEW} WHERE dial = ? OR phone_e164 = ? ORDER BY updated_at DESC LIMIT 1`)
    .bind(number, number).first();
}

async function twilioWebhook(request, env, hook, url) {
  if (request.method !== "POST") return new Response("Twilio only", { status: 405 });
  const form = await request.formData();
  const params = {};
  for (const [k, v] of form.entries()) params[k] = typeof v === "string" ? v : "";
  if (!(await twilioValid(request, env, params))) return new Response("Bad signature", { status: 403 });
  const t = (await getSetting(env, "twilio")) || {};
  const at = nowIso();
  const studio = (await getSetting(env, "name")) || "";

  if (hook === "voice") {                                        // you pressed Call in HQ
    if (!String(params.From || params.Caller || "").startsWith("client:")) return twiml("<Reject/>");
    const b = params.key ? await env.DB.prepare(`SELECT key, name, dial FROM ${VIEW} WHERE key = ?`).bind(params.key).first() : null;
    const to = e164(params.To);
    if (!b || !to || b.dial !== to || !usCallable(to)) {
      return twiml("<Say>HQ only calls US and Canadian numbers of businesses saved in it.</Say>");
    }
    const act = await logActivity(env, b.key, "call", "Outgoing call", { sid: params.CallSid, number: to }, at).run();
    await env.DB.batch([
      env.DB.prepare("INSERT OR REPLACE INTO calls (sid, key, number, direction, at, status, activity_id) VALUES (?, ?, ?, 'out', ?, 'started', ?)")
        .bind(params.CallSid, b.key, to, at, act.meta && act.meta.last_row_id),
      env.DB.prepare("UPDATE businesses SET calls = calls + 1, last_call_at = ?, updated_at = ? WHERE key = ?").bind(at, at, b.key),
    ]);
    return twiml(`<Dial callerId="${xml(t.number)}" answerOnBridge="true" timeLimit="1800"><Number statusCallbackEvent="completed" `
      + `statusCallback="${xml(url.origin)}/twilio/status" statusCallbackMethod="POST">${xml(to)}</Number></Dial>`);
  }
  if (hook === "status") {                                       // how the call to the business ended
    const call = await env.DB.prepare("SELECT * FROM calls WHERE sid = ?").bind(params.ParentCallSid || params.CallSid).first();
    if (call) {
      const secs = +params.CallDuration || 0;
      const status = params.CallStatus || "completed";
      const detail = status === "completed" && secs > 0 ? `Outgoing call · ${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")}`
        : { busy: "Outgoing call · busy", "no-answer": "Outgoing call · no answer", failed: "Outgoing call · didn't go through",
            canceled: "Outgoing call · cancelled" }[status] || "Outgoing call";
      await env.DB.batch([
        env.DB.prepare("UPDATE calls SET status = ?, duration = ? WHERE sid = ?").bind(status, secs, call.sid),
        env.DB.prepare("UPDATE activity SET detail = ?, meta = ? WHERE id = ?")
          .bind(detail, JSON.stringify({ sid: call.sid, number: call.number, status, duration: secs }), call.activity_id || -1),
      ]);
    }
    return twiml("");
  }
  if (hook === "incoming") {                                     // someone called your Twilio number
    const from = e164(params.From) || params.From || "";
    const b = await byPhone(env, from);
    const key = b ? b.key : `caller:${from}`;
    const act = b ? await logActivity(env, b.key, "call", "Incoming call", { sid: params.CallSid, number: from }, at).run() : null;
    await env.DB.prepare("INSERT OR REPLACE INTO calls (sid, key, number, direction, at, status, activity_id) VALUES (?, ?, ?, 'in', ?, 'ringing', ?)")
      .bind(params.CallSid, key, from, at, act && act.meta && act.meta.last_row_id).run();
    return twiml(`<Dial timeout="20" answerOnBridge="true" action="${xml(url.origin)}/twilio/missed"><Client><Identity>omar</Identity>`
      + `<Parameter name="key" value="${xml(b ? b.key : "")}"/><Parameter name="name" value="${xml(b ? b.name : from)}"/></Client></Dial>`);
  }
  if (hook === "missed") {                                       // you didn't pick up in HQ: take a message
    if (["completed", "answered"].includes(params.DialCallStatus)) return twiml("<Hangup/>");
    const call = await env.DB.prepare("SELECT * FROM calls WHERE sid = ?").bind(params.CallSid).first();
    const b = call && call.key && !call.key.startsWith("caller:") ? await env.DB.prepare("SELECT key, name FROM businesses WHERE key = ?").bind(call.key).first() : null;
    const base = (await getSetting(env, "url")) || url.origin;
    await telegram(env, `📞 Missed call from ${b ? `<a href="${html(base)}/b/${encodeURIComponent(b.key)}">${html(b.name)}</a>` : html(call ? call.number : params.From)}`
      + `${b && call ? ` (${html(call.number)})` : ""}. If they leave a voicemail, it'll be in HQ.`);
    return twiml(`<Say>Thanks for calling${studio ? " " + xml(studio) : ""}. Please leave a message after the tone, and we'll call you back.</Say>`
      + `<Record maxLength="120" playBeep="true" timeout="5" action="${xml(url.origin)}/twilio/done" `
      + `recordingStatusCallback="${xml(url.origin)}/twilio/voicemail" recordingStatusCallbackEvent="completed"/>`);
  }
  if (hook === "done") return twiml("<Say>Thank you. Goodbye.</Say><Hangup/>");
  if (hook === "voicemail") {                                    // the message they left
    const call = await env.DB.prepare("SELECT * FROM calls WHERE sid = ?").bind(params.CallSid).first();
    const secs = +params.RecordingDuration || 0;
    if (call) {
      await env.DB.prepare("UPDATE calls SET recording_sid = ?, status = 'voicemail', duration = ? WHERE sid = ?")
        .bind(params.RecordingSid, secs, call.sid).run();
      if (call.key && !call.key.startsWith("caller:")) {
        await logActivity(env, call.key, "call", `Voicemail · ${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")}`,
                          { recording: params.RecordingSid, number: call.number }, at).run();
      }
    }
    const b = call && call.key && !call.key.startsWith("caller:") ? await env.DB.prepare("SELECT key, name FROM businesses WHERE key = ?").bind(call.key).first() : null;
    const base = (await getSetting(env, "url")) || url.origin;
    await telegram(env, `🎙️ Voicemail (${secs}s) from ${b ? `<a href="${html(base)}/b/${encodeURIComponent(b.key)}">${html(b.name)}</a>` : html(call ? call.number : "a caller")}.`
      + ` ${b ? "Listen to it on their page in HQ." : `Listen: <a href="${html(base)}/api/recording/${html(params.RecordingSid)}">open</a> (log in to HQ first).`}`);
    return twiml("");
  }
  return new Response("Unknown hook", { status: 404 });
}

async function recording(env, sid) {
  if (!env.TWILIO_ACCOUNT_SID || !env.TWILIO_AUTH_TOKEN) return json({ error: "Twilio isn't set up" }, 400);
  const r = await twilioApi(env, `/Recordings/${sid}.mp3`);
  if (!r.ok) return json({ error: "Couldn't get that recording from Twilio" }, 502);
  return new Response(r.body, { headers: { "Content-Type": "audio/mpeg", "Cache-Control": "private, max-age=3600" } });
}

// For tests.
export const _test = { telegramReason, botToken, chatId, e164, addCycle, callWindow, agentEvent, cleanRecord, plansFor, usCallable, digestText, hourly, twilioValid };
