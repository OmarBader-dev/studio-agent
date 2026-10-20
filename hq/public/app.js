// HQ web app. No build step and no framework. Everything that comes from a business (names, replies,
// websites) is put on the page as plain text, never as HTML, and links are only followed when they're http(s).

const SDK = "https://cdn.jsdelivr.net/npm/@twilio/voice-sdk@2.18.5/dist/twilio.min.js";
const SDK_SRI = "sha384-LUG7DmzDPWNKRYoqyGpV4d/IByMLiya/oUhMSc/4/6hi0wbzO/8PffM4lzeFEYS8";

const STAGE = { replied: "Replied", interested: "Interested", contacted: "Preview sent", to_contact: "Call or DM",
                new: "Preview ready", no_reply: "No reply", client: "Client", lost: "Lost" };
const STAGE_ORDER = ["replied", "interested", "contacted", "to_contact", "new", "no_reply", "client", "lost"];
const AGENT = { lead: "Websites", security: "Security", studio: "Studio", manual: "Yours" };
const OUTCOMES = [["interested", "Interested"], ["not_interested", "Not interested"], ["callback", "Call back later"],
                  ["voicemail", "Left a voicemail"], ["no_answer", "No answer"], ["wrong_number", "Wrong number"],
                  ["talked", "Talked, nothing yet"]];
const ICONS = {
  today: "M12 3v2M12 19v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M3 12h2M19 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z",
  pipeline: "M4 6h16M4 12h10M4 18h6",
  clients: "M16 20v-1.5a3.5 3.5 0 0 0-3.5-3.5h-5A3.5 3.5 0 0 0 4 18.5V20M10 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM20 20v-1.5a3.5 3.5 0 0 0-2.5-3.35M15.5 4.15a3.5 3.5 0 0 1 0 6.7",
  settings: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z",
  phone: "M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z",
  mail: "M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zM22 6l-10 7L2 6",
  eye: "M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  globe: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z",
  back: "M15 18l-6-6 6-6", plus: "M12 5v14M5 12h14", mic: "M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3zM19 10v2a7 7 0 0 1-14 0v-2M12 19v4",
  keypad: "M5 5h2v2H5zM11 5h2v2h-2zM17 5h2v2h-2zM5 11h2v2H5zM11 11h2v2h-2zM17 11h2v2h-2zM5 17h2v2H5zM11 17h2v2h-2zM17 17h2v2h-2z",
  end: "M10.7 13.3a16 16 0 0 0 3.4 2.6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2v3a2 2 0 0 1-2.2 2A19.8 19.8 0 0 1 3.1 4.2 2 2 0 0 1 5.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L9 9.8M22 2L2 22",
};

let ME = null;

// Building the page --------------------------------------------------------------------------------------
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : String(v));
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid instanceof Node ? kid : String(kid));
  }
  return el;
}
function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", ICONS[name] || "");
  svg.append(path);
  return svg;
}
function add(el, ...kids) {                  // like el.append, but skips empty parts (append would write "null")
  for (const kid of kids.flat(Infinity)) if (kid != null && kid !== false) el.append(kid);
  return el;
}
const KIND_NAMES = { hvac: "HVAC", cafe: "Café", bbq: "BBQ" };
const kindLabel = (k) => (!k ? "" : KIND_NAMES[String(k).toLowerCase()] || (k.length < 30 && k === k.toLowerCase() ? k[0].toUpperCase() + k.slice(1) : k));
const planName = (b) => b.plan_label || (b.plan ? b.plan[0].toUpperCase() + b.plan.slice(1) : "Plan");
const safeUrl = (u) => (/^https?:\/\//i.test(String(u || "").trim()) ? String(u).trim() : null);
const link = (href, ...kids) => h("a", { href, "data-link": "" }, ...kids);
const ext = (href, ...kids) => (safeUrl(href) ? h("a", { href: safeUrl(href), target: "_blank", rel: "noopener noreferrer" }, ...kids) : null);
const pill = (stage) => h("span", { class: "pill", style: `--c: var(--s-${stage})` }, STAGE[stage] || stage);
const badge = (agent) => h("span", { class: "badge" }, AGENT[agent] || agent);
const bizUrl = (b) => `/b/${encodeURIComponent(b.key)}`;
const place = (b) => [b.city, b.state].filter(Boolean).join(", ");
const money = (n) => (n == null ? "" : `$${Number(n) % 1 ? Number(n).toFixed(2) : Number(n)}`);
const per = (cycle) => (cycle === "monthly" ? "/month" : cycle === "yearly" ? "/year" : " once");

function toast(text, ms = 2600) {
  const t = h("div", { class: "toast", role: "status" }, text);
  document.body.append(t);
  setTimeout(() => t.remove(), ms);
}

// Dates
const todayStr = () => {
  const p = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Beirut", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
  return p;
};
const dayDiff = (dateStr) => Math.round((Date.parse(dateStr + "T00:00:00Z") - Date.parse(todayStr() + "T00:00:00Z")) / 86400000);
function fmtDate(dateStr, withYear = false) {
  if (!dateStr) return "";
  const d = new Date(dateStr.length === 10 ? dateStr + "T12:00:00Z" : dateStr);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", ...(withYear ? { year: "numeric" } : {}), timeZone: dateStr.length === 10 ? "UTC" : "Asia/Beirut" });
}
function rel(iso) {
  if (!iso) return "";
  const days = Math.floor((Date.now() - Date.parse(iso)) / 86400000);
  if (days <= 0) {
    const mins = Math.floor((Date.now() - Date.parse(iso)) / 60000);
    if (mins < 2) return "just now";
    if (mins < 60) return `${mins} min ago`;
    return `${Math.floor(mins / 60)} h ago`;
  }
  if (days === 1) return "yesterday";
  if (days < 30) return `${days} days ago`;
  return fmtDate(iso, true);
}
function untilText(dateStr) {
  const d = dayDiff(dateStr);
  if (d === 0) return "today";
  if (d === 1) return "tomorrow";
  if (d === -1) return "yesterday";
  return d > 0 ? `in ${d} days` : `${-d} days ago`;
}
function addCycle(date, cycle) {
  if (!date || !["monthly", "yearly"].includes(cycle)) return null;
  const [y, m, d] = date.split("-").map(Number);
  const t = new Date(Date.UTC(y, m - 1 + (cycle === "monthly" ? 1 : 12), 1));
  const last = new Date(Date.UTC(t.getUTCFullYear(), t.getUTCMonth() + 1, 0)).getUTCDate();
  t.setUTCDate(Math.min(d, last));
  return t.toISOString().slice(0, 10);
}
const fmtDur = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const fmtPhone = (n) => {
  const m = /^\+1(\d{3})(\d{3})(\d{4})$/.exec(n || "");
  return m ? `(${m[1]}) ${m[2]}-${m[3]}` : (n || "");
};

// Talking to the Worker ------------------------------------------------------------------------------
async function api(path, body) {
  const opts = { method: body ? "POST" : "GET", headers: {}, credentials: "same-origin" };
  if (body) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  const r = await fetch(path, opts);
  let data = null;
  try { data = await r.json(); } catch { /* not JSON */ }
  if (r.status === 401 && data && data.error === "login") {
    ME = null;
    showLogin(data.password_set !== false);
    throw new Error("login");
  }
  if (!r.ok) throw new Error((data && data.error) || `HQ answered ${r.status}`);
  return data;
}

// The frame: top bar, page, tabs ------------------------------------------------------------------------
const TABS = [["today", "/", "Today"], ["pipeline", "/pipeline", "Pipeline"], ["clients", "/clients", "Clients"], ["settings", "/settings", "Settings"]];
function frame(title, sub, active, ...content) {
  document.title = `${title} · HQ`;
  document.getElementById("app").replaceChildren(h("div", { class: "shell" },
    h("header", { class: "top" }, h("div", { class: "top-in" }, h("h1", {}, title), sub ? h("span", { class: "sub" }, sub) : null)),
    h("main", {}, ...content),
    h("nav", { class: "tabs" }, TABS.map(([id, href, label]) =>
      h("a", { href, "data-link": "", class: id === active ? "on" : null, "aria-current": id === active ? "page" : null }, icon(id), label)))));
  renderCallBar();
}
const loading = (title, active) => frame(title, null, active, h("div", { class: "empty" }, "Loading…"));
const failed = (title, active, e) => frame(title, null, active, h("div", { class: "note bad" }, e.message || String(e)));

function section(title, items, row, emptyText, extra) {
  if (!items.length && !emptyText) return null;
  return h("section", { class: "section" },
    h("h2", {}, title, items.length ? h("span", { class: "n" }, items.length) : null, extra || null),
    h("div", { class: "card" }, items.length ? h("ul", { class: "list" }, items.map(row)) : h("div", { class: "empty" }, emptyText)));
}

// Routing ---------------------------------------------------------------------------------------------
const ROUTES = [
  [/^\/$/, () => viewToday()], [/^\/pipeline$/, () => viewPipeline()], [/^\/clients$/, () => viewClients()],
  [/^\/settings$/, () => viewSettings()], [/^\/add$/, () => viewAdd()],
  [/^\/b\/(.+)$/, (m) => viewBusiness(decodeURIComponent(m[1]))],
];
let moves = 0;                      // pages opened inside HQ, so Back can go back instead of to the list
function go(path, replace = false) {
  history[replace ? "replaceState" : "pushState"]({}, "", path);
  if (!replace) moves++;
  render();
  window.scrollTo(0, 0);
}
async function render() {
  if (!ME) {
    try { ME = await api("/api/me"); } catch (e) { if (e.message !== "login") document.getElementById("app").replaceChildren(h("div", { class: "login" }, h("div", { class: "note bad" }, e.message))); return; }
    setTimeout(registerForIncoming, 1500);
  }
  for (const [re, view] of ROUTES) {
    const m = location.pathname.match(re);
    if (m) return view(m);
  }
  go("/", true);
}
document.addEventListener("click", (e) => {
  const a = e.target.closest("a[data-link]");
  if (!a || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey) return;
  e.preventDefault();
  go(a.getAttribute("href"));
});
window.addEventListener("popstate", () => { moves = Math.max(0, moves - 1); render(); });

// Login ----------------------------------------------------------------------------------------------------
function showLogin(passwordSet = true) {
  const err = h("div", { class: "note bad hide" });
  const input = h("input", { type: "password", autocomplete: "current-password", placeholder: "Password", required: true, autofocus: true });
  const btn = h("button", { class: "btn primary", type: "submit", style: "width:100%" }, "Log in");
  const form = h("form", { class: "stack", onsubmit: async (e) => {
    e.preventDefault();
    btn.disabled = true;
    err.classList.add("hide");
    try {
      const r = await fetch("/api/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password: input.value }) });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.error || "Couldn't log in");
      ME = null;
      render();
    } catch (e2) { err.textContent = e2.message; err.classList.remove("hide"); btn.disabled = false; }
  } }, input, btn, err);
  document.title = "Log in · HQ";
  document.getElementById("app").replaceChildren(h("div", { class: "login" }, h("div", { class: "card stack" },
    h("h1", {}, "HQ"), h("p", { class: "muted", style: "margin:0" }, "Every business your agents find, in one place."),
    passwordSet ? form : h("div", { class: "note" }, "Add the HQ_PASSWORD secret to this Worker in Cloudflare, then reload this page."))));
}

// Today ------------------------------------------------------------------------------------------------------
function callButton(b, big = false) {
  return h("button", { class: `btn primary${big ? "" : " small"}`, type: "button", onclick: (e) => { e.preventDefault(); startCall(b); },
                       title: ME && ME.twilio ? `Call ${fmtPhone(b.dial)}` : "Connect Twilio in Settings to call from HQ" },
    icon("phone"), "Call");
}
function rowLink(b, ...lines) {
  return h("a", { class: "grow", href: bizUrl(b), "data-link": "", style: "color:inherit;text-decoration:none" }, ...lines);
}
function metaLine(b, ...more) {
  return h("div", { class: "meta" }, badge(b.agent), " ", [place(b), kindLabel(b.kind)].filter(Boolean).join(" · "), ...more);
}
const whenLine = (w) => (w ? h("div", { class: "when-line" }, w.now ? h("span", { class: "time now" }, "Good time to call now")
  : ["Best time ", h("span", { class: "time" }, w.label)]) : null);
function callRow(b) {
  return h("li", { class: "row" }, rowLink(b, h("div", { class: "name" }, b.name), metaLine(b),
    h("div", { class: "why" }, b.why), whenLine(b.window)), callButton(b));
}
function replyRow(b) {
  return h("li", { class: "row" }, rowLink(b, h("div", { class: "name" }, b.name),
    metaLine(b, b.replied_at ? ` · ${rel(b.replied_at)}` : ""), b.reply_text ? h("div", { class: "quote" }, b.reply_text) : null),
    b.dial ? callButton(b) : null);
}
function simpleRow(b) {
  return h("li", { class: "row" }, rowLink(b, h("div", { class: "name" }, b.name), metaLine(b)), b.dial ? callButton(b) : null);
}
function renewalRow(b) {
  const d = dayDiff(b.renews_at);
  return h("li", { class: "row" }, rowLink(b, h("div", { class: "name" }, b.name),
    h("div", { class: "meta" }, badge(b.agent), " ", `${planName(b)} · ${money(b.price)}${per(b.cycle)}`),
    h("div", { class: "why", style: d < 0 ? "color:var(--danger)" : null }, d < 0 ? `Overdue since ${fmtDate(b.renews_at)}` : `Renews ${fmtDate(b.renews_at)} (${untilText(b.renews_at)})`)),
    paidButton(b));
}
function reminderRow(b) {
  return h("li", { class: "row" }, rowLink(b, h("div", { class: "name" }, b.name),
    h("div", { class: "meta" }, `⏰ ${b.remind_note || "Follow up"} · ${fmtDate(b.remind_at)}`)), b.dial ? callButton(b) : null);
}
function paidButton(b) {
  return h("button", { class: "btn small", type: "button", onclick: (e) => { e.preventDefault(); markPaid(b); } }, "Mark paid");
}
async function markPaid(b) {
  const next = addCycle(b.renews_at || todayStr(), b.cycle);
  if (!confirm(`Mark ${b.name} as paid (${money(b.price)})? The next renewal moves to ${fmtDate(next, true)}.`)) return;
  try { await api(`/api/business/${encodeURIComponent(b.key)}`, { action: "paid" }); toast("Marked paid"); render(); } catch (e) { toast(e.message); }
}

async function viewToday() {
  loading("Today", "today");
  let d;
  try { d = await api("/api/today"); } catch (e) { if (e.message !== "login") failed("Today", "today", e); return; }
  const c = d.counts || {};
  const total = Object.values(c).reduce((a, b) => a + b, 0);
  frame("Today", fmtDate(d.day), "today",
    h("div", { class: "chips" }, ["replied", "interested", "contacted", "to_contact", "client"].map((s) =>
      link(`/pipeline?stage=${s}`, h("span", { class: "chip" }, STAGE[s], h("span", { class: "n" }, c[s] || 0))))),
    total === 0 ? h("div", { class: "card pad stack" }, h("b", {}, "No businesses yet"),
      h("div", { class: "muted" }, "They appear after your agents' next runs, once each agent has HQ_URL and HQ_TOKEN in its GitHub secrets. "),
      link("/settings", "See how in Settings")) : null,
    section("Calls to make", d.calls, callRow, total ? "Nobody to call right now. Businesses show up here 2 days after their preview is emailed, or straight away when they have no email." : null,
            d.calls.length ? h("span", { class: "faint", style: "text-transform:none;letter-spacing:0;font-weight:500" }, "· best times in Beirut time") : null),
    section("Replies waiting", d.replies, replyRow),
    section("Interested", d.interested, simpleRow),
    section("Renewals this week", d.renewals, renewalRow),
    section("Reminders", d.reminders, reminderRow));
}

// Pipeline ---------------------------------------------------------------------------------------------------
async function viewPipeline() {
  const params = new URLSearchParams(location.search);
  const state = { stage: params.get("stage") || "all", agent: params.get("agent") || "all", q: params.get("q") || "", offset: 0, items: [] };
  const listBox = h("div", { class: "card" }, h("div", { class: "empty" }, "Loading…"));
  const chipsBox = h("div", { class: "chips" });
  const more = h("button", { class: "btn hide", type: "button", style: "width:100%;margin-top:10px", onclick: () => load(true) }, "Show more");
  const search = h("input", { type: "search", placeholder: "Search name, city, email, phone", value: state.q, "aria-label": "Search" });
  let timer = null;
  search.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => { state.q = search.value.trim(); load(); }, 250); });
  const seg = h("div", { class: "seg", role: "tablist" });
  const segButtons = [["all", "All"], ["lead", "Websites"], ["security", "Security"], ["studio", "Studio"], ["manual", "Yours"]].map(([id, label]) =>
    h("button", { type: "button", class: state.agent === id ? "on" : null, onclick: () => { state.agent = id; segButtons.forEach((b) => b.classList.toggle("on", b.dataset.id === id)); load(); }, "data-id": id }, label));
  seg.append(...segButtons);

  function remember() {
    const p = new URLSearchParams();
    if (state.stage !== "all") p.set("stage", state.stage);
    if (state.agent !== "all") p.set("agent", state.agent);
    if (state.q) p.set("q", state.q);
    history.replaceState({}, "", `/pipeline${p.toString() ? "?" + p : ""}`);
  }
  async function load(append = false) {
    state.offset = append ? state.offset + 50 : 0;
    remember();
    let d;
    try { d = await api(`/api/businesses?stage=${state.stage}&agent=${state.agent}&q=${encodeURIComponent(state.q)}&offset=${state.offset}`); } catch (e) {
      if (e.message !== "login") listBox.replaceChildren(h("div", { class: "empty" }, e.message));
      return;
    }
    state.items = append ? state.items.concat(d.items) : d.items;
    const counts = d.counts || {};
    const all = Object.values(counts).reduce((a, b) => a + b, 0);
    chipsBox.replaceChildren(...[["all", "All", all], ...STAGE_ORDER.map((s) => [s, STAGE[s] === "Client" ? "Clients" : STAGE[s], counts[s] || 0])].map(([id, label, n]) =>
      h("button", { type: "button", class: `chip${state.stage === id ? " on" : ""}`, onclick: () => { state.stage = id; load(); } }, label, h("span", { class: "n" }, n))));
    listBox.replaceChildren(state.items.length ? h("ul", { class: "list" }, state.items.map(pipeRow))
      : h("div", { class: "empty" }, state.q ? "Nothing matches that search." : "Nothing here yet."));
    more.classList.toggle("hide", !d.more);
  }
  frame("Pipeline", null, "pipeline",
    h("div", { class: "stack" }, h("div", { style: "display:flex;gap:8px" }, h("div", { style: "flex:1;min-width:0" }, search),
      h("a", { class: "btn", href: "/add", "data-link": "", title: "Add a business", "aria-label": "Add a business" }, icon("plus"), h("span", { class: "add-label" }, "Add"))), seg, chipsBox),
    listBox, more);
  load();
}
function lastLine(b) {
  if (b.eff === "client") return b.renews_at ? `${planName(b)} · renews ${fmtDate(b.renews_at)}` : planName(b);
  if (b.eff === "replied" && b.replied_at) return `Replied ${rel(b.replied_at)}`;
  if (b.last_call_at) return `Called ${rel(b.last_call_at)}`;
  if (b.eff === "contacted" && b.first_sent_at) return `Emailed ${rel(b.first_sent_at)}${b.touches > 1 ? ` · ${b.touches - 1} follow-up${b.touches > 2 ? "s" : ""}` : ""}`;
  return b.created_at ? `Found ${rel(b.created_at)}` : "";
}
function pipeRow(b) {
  return h("li", {}, h("a", { class: "row", href: bizUrl(b), "data-link": "" },
    h("div", { class: "grow" }, h("div", { class: "name" }, b.name), metaLine(b), h("div", { class: "meta" }, lastLine(b))),
    pill(b.eff)));
}

// Clients ------------------------------------------------------------------------------------------------------
async function viewClients() {
  loading("Clients", "clients");
  let d;
  try { d = await api("/api/clients"); } catch (e) { if (e.message !== "login") failed("Clients", "clients", e); return; }
  const due = d.items.filter((b) => b.renews_at && dayDiff(b.renews_at) <= 7).length;
  frame("Clients", null, "clients",
    h("div", { class: "stats" },
      h("div", { class: "card stat" }, h("div", { class: "v" }, money(Math.round(d.mrr))), h("div", { class: "l" }, "a month")),
      h("div", { class: "card stat" }, h("div", { class: "v" }, d.count), h("div", { class: "l" }, d.count === 1 ? "client" : "clients")),
      h("div", { class: "card stat" }, h("div", { class: "v", style: due ? "color:var(--warn)" : null }, due), h("div", { class: "l" }, "renew this week"))),
    section("Everyone who bought", d.items, clientRow, "No clients yet. Open a business and press Bought when someone says yes."));
}
function clientRow(b) {
  const d = b.renews_at ? dayDiff(b.renews_at) : null;
  return h("li", { class: "row" }, rowLink(b, h("div", { class: "name" }, b.name),
    h("div", { class: "meta" }, badge(b.agent), " ", `${planName(b)} · ${money(b.price)}${per(b.cycle)}`, b.bought_at ? ` · since ${fmtDate(b.bought_at)}` : ""),
    b.renews_at ? h("div", { class: "why", style: d < 0 ? "color:var(--danger)" : d <= 7 ? "color:var(--warn)" : null },
      d < 0 ? `Overdue since ${fmtDate(b.renews_at)}` : `Renews ${fmtDate(b.renews_at)} (${untilText(b.renews_at)})`) : null),
    ["monthly", "yearly"].includes(b.cycle) ? paidButton(b) : null);
}

// One business ---------------------------------------------------------------------------------------------
const KIND_ICON = { agent: "🤖", note: "📝", call: "📞", stage: "🏷️", bought: "💳", paid: "✅", remind: "⏰" };

async function viewBusiness(key) {
  loading("Business", "pipeline");
  let d;
  try { d = await api(`/api/business/${encodeURIComponent(key)}`); } catch (e) { if (e.message !== "login") failed("Business", "pipeline", e); return; }
  drawBusiness(d);
}
function act(b, body, msg) {
  return api(`/api/business/${encodeURIComponent(b.key)}`, body).then((d) => { if (msg) toast(msg); drawBusiness(d); return d; })
    .catch((e) => { if (e.message !== "login") toast(e.message); throw e; });
}
function drawBusiness(d) {
  const b = d.business;
  const preview = safeUrl(b.preview_url), site = safeUrl(b.website);
  const mailto = b.mail ? `mailto:${encodeURIComponent(b.mail)}?subject=${encodeURIComponent(`${b.name}`)}&body=${encodeURIComponent(
    `Hi,\n\n${preview ? `Here's the preview I made for ${b.name}: ${preview}\n\n` : ""}`)}` : null;
  const actionsRow = h("div", { class: "actions" },
    h("button", { class: "btn primary", type: "button", disabled: !b.dial, onclick: () => startCall(b) }, icon("phone"), "Call"),
    mailto ? h("a", { class: "btn", href: mailto }, icon("mail"), "Email") : h("button", { class: "btn", disabled: true, type: "button" }, icon("mail"), "Email"),
    preview ? h("a", { class: "btn", href: preview, target: "_blank", rel: "noopener noreferrer" }, icon("eye"), "Preview") : h("button", { class: "btn", disabled: true, type: "button" }, icon("eye"), "Preview"),
    site ? h("a", { class: "btn", href: site, target: "_blank", rel: "noopener noreferrer" }, icon("globe"), "Website") : h("button", { class: "btn", disabled: true, type: "button" }, icon("globe"), "Website"));

  frame("Business", null, "pipeline",
    h("a", { class: "back", href: "/pipeline", "data-link": "", onclick: (e) => { if (moves > 0) { e.preventDefault(); e.stopPropagation(); moves--; history.back(); } } }, icon("back"), "Back"),
    h("div", { class: "hero" }, h("h1", {}, b.name), h("div", { class: "split" }, pill(b.eff), badge(b.agent),
      h("span", { class: "muted small" }, [place(b), kindLabel(b.kind)].filter(Boolean).join(" · ")))),
    h("div", { class: "section" }, actionsRow),
    b.dial ? h("div", { class: "muted small", style: "margin:8px 4px 0" }, fmtPhone(b.dial), b.why ? ` · ${b.why}` : "",
      b.window ? h("div", {}, b.window.now ? h("span", { class: "time now" }, "Good time to call now")
        : ["Best time to call: ", h("span", { class: "time" }, b.window.label), " (Beirut time)"]) : null)
      : h("div", { class: "muted small", style: "margin:8px 4px 0" }, "No phone number yet. Add one under Contact."),
    planCard(b, d.plans),
    reminderCard(b),
    agentCard(b),
    contactCard(b),
    notesCard(b),
    timelineCard(d.activity));
  document.title = `${b.name} · HQ`;
}

function planCard(b, plans) {
  const box = h("section", { class: "section" }, h("h2", {}, b.eff === "client" ? "Their plan" : "Next step"));
  const card = h("div", { class: "card pad stack" });
  box.append(card);
  if (b.eff === "client") {
    const d = b.renews_at ? dayDiff(b.renews_at) : null;
    add(card,
      h("div", {}, h("b", {}, `${planName(b)} · ${money(b.price)}${per(b.cycle)}`), b.setup_fee ? h("span", { class: "muted" }, ` + ${money(b.setup_fee)} setup`) : null),
      h("div", { class: "muted small" }, b.bought_at ? `Bought ${fmtDate(b.bought_at, true)}` : "", b.renews_at ? ` · renews ${fmtDate(b.renews_at, true)} (${untilText(b.renews_at)})` : b.cycle === "once" ? " · one-time" : ""),
      d != null && d < 0 ? h("div", { class: "note bad" }, `Payment overdue since ${fmtDate(b.renews_at)}.`) : null,
      b.agent === "studio" && b.start_service && b.status !== "client" ? h("div", { class: "note" }, "The studio agent starts their service on its next run (welcome email and first week of posts).") : null,
      h("div", { class: "split" },
        ["monthly", "yearly"].includes(b.cycle) ? h("button", { class: "btn ok", type: "button", onclick: () => markPaid(b) }, "Mark paid") : null,
        ["monthly", "yearly"].includes(b.cycle) ? h("button", { class: "btn", type: "button", onclick: () => renewalSheet(b) }, "Change renewal date") : null,
        h("button", { class: "btn", type: "button", onclick: () => boughtSheet(b, plans) }, "Edit plan"),
        h("button", { class: "btn danger", type: "button", onclick: () => { if (confirm(`Cancel ${b.name}'s plan?`)) act(b, { action: "cancel" }, "Plan cancelled"); } }, "Cancel plan")));
    return box;
  }
  if (b.eff === "lost") {
    add(card, h("div", {}, h("b", {}, "Lost"), b.lost_reason ? h("span", { class: "muted" }, `: ${b.lost_reason}`) : null),
      h("div", { class: "split" }, b.stage ? h("button", { class: "btn", type: "button", onclick: () => act(b, { action: "stage", stage: null }, "Back in the pipeline") }, "Undo") : null,
        h("button", { class: "btn", type: "button", onclick: () => boughtSheet(b, plans) }, "They bought after all")));
    return box;
  }
  add(card,
    h("div", { class: "muted small" }, b.eff === "interested" ? "They're interested. When they pay, press Bought so HQ tracks their renewal."
      : "Talked to them? Mark how it went. The agent stops emailing anyone you mark here."),
    h("div", { class: "split" },
      h("button", { class: "btn ok", type: "button", onclick: () => boughtSheet(b, plans) }, "Bought"),
      b.eff !== "interested" ? h("button", { class: "btn", type: "button", onclick: () => act(b, { action: "stage", stage: "interested" }, "Marked interested") }, "Interested") : null,
      h("button", { class: "btn danger", type: "button", onclick: () => lostSheet(b) }, "Not interested"),
      b.stage ? h("button", { class: "btn", type: "button", onclick: () => act(b, { action: "stage", stage: null }, "Back to following the agent") }, "Undo") : null));
  return box;
}

function reminderCard(b) {
  const date = h("input", { type: "date", value: b.remind_at || "", min: todayStr(), "aria-label": "Reminder date" });
  const note = h("input", { type: "text", value: b.remind_note || "", placeholder: "What to do (call back, send prices…)", maxlength: 200, "aria-label": "Reminder note" });
  return h("section", { class: "section" }, h("h2", {}, "Reminder"), h("div", { class: "card pad stack" },
    b.remind_at ? h("div", {}, h("b", {}, `⏰ ${b.remind_note || "Follow up"}`), h("span", { class: "muted" }, ` · ${fmtDate(b.remind_at, true)} (${untilText(b.remind_at)})`)) : h("div", { class: "muted small" }, "It shows on Today and in the Telegram list on that day."),
    h("div", { class: "pair" }, date, note),
    h("div", { class: "split" }, h("button", { class: "btn", type: "button", onclick: () => {
      if (!date.value) return toast("Pick a date");
      act(b, { action: "remind", date: date.value, note: note.value }, "Reminder saved");
    } }, "Save reminder"), b.remind_at ? h("button", { class: "btn", type: "button", onclick: () => act(b, { action: "remind", date: null }, "Reminder cleared") }, "Clear") : null)));
}

const STATUS_TEXT = {
  ready: "Preview made, first email queued", manual: "Preview made. No public email, so call or DM them",
  emailed: "Preview emailed", finished: "All follow-ups sent, no reply", replied: "They replied", client: "Client",
  opted_out: "Asked not to be contacted", bounced: "Their email bounced", expired: "Preview page expired", added: "Added by you",
};
function agentCard(b) {
  const rows = [];
  const add = (k, v) => { if (v != null && v !== "") rows.push(h("dt", {}, k), h("dd", {}, v)); };
  add("Agent", AGENT[b.agent] || b.agent);
  add("Status", STATUS_TEXT[b.status] || b.status);
  if (b.touches) add("Emails sent", `${b.touches} (${b.touches - 1} follow-up${b.touches === 2 ? "" : "s"})`);
  add("First email", b.first_sent_at ? `${fmtDate(b.first_sent_at, true)} (${rel(b.first_sent_at)})` : null);
  add("Last email", b.last_sent_at && b.last_sent_at !== b.first_sent_at ? `${fmtDate(b.last_sent_at, true)} (${rel(b.last_sent_at)})` : null);
  add("Replied", b.replied_at ? `${fmtDate(b.replied_at, true)} (${rel(b.replied_at)})` : null);
  add("Preview", safeUrl(b.preview_url) ? ext(b.preview_url, "Open the preview") : null);
  const x = b.extra || {};
  if (x.rating) add("Google rating", `${x.rating}★${x.reviews ? ` (${x.reviews} reviews)` : ""}`);
  if (x.grade) add("Security grade", `${x.grade}${x.issue_count != null ? ` · ${x.issue_count} issue${x.issue_count === 1 ? "" : "s"}` : ""}`);
  if (x.has_reel) add("Sample", `Posts${x.has_reel ? " + a Reel" : ""}${x.redesigned ? ` + their ${x.redesigned} redesigned` : ""}`);
  add("Found", b.created_at ? fmtDate(b.created_at, true) : null);
  add("Last update", b.synced_at ? rel(b.synced_at) : null);
  return h("section", { class: "section" }, h("h2", {}, "From the agent"), h("div", { class: "card pad stack" },
    h("dl", { class: "kv" }, rows), b.reply_text ? h("div", {}, h("div", { class: "muted small" }, "What they wrote:"), h("div", { class: "quote" }, b.reply_text)) : null));
}

function contactCard(b) {
  const rows = [];
  const add = (k, v) => { if (v) rows.push(h("dt", {}, k), h("dd", {}, v)); };
  add("Phone", b.dial ? fmtPhone(b.dial) + (b.my_phone ? " (yours)" : "") : null);
  add("Email", b.mail ? h("a", { href: `mailto:${encodeURIComponent(b.mail)}` }, b.mail) : null);
  add("Website", safeUrl(b.website) ? ext(b.website, b.website.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "")) : null);
  const socials = b.socials ? (Array.isArray(b.socials) ? b.socials : Object.values(b.socials)) : [];
  const links = socials.map((u) => safeUrl(u)).filter(Boolean);
  if (links.length) rows.push(h("dt", {}, "Social"), h("dd", {}, links.map((u, i) => [i ? " · " : "", ext(u, u.replace(/^https?:\/\/(www\.)?/, "").split("/")[0])])));
  add("Place", place(b));
  return h("section", { class: "section" }, h("h2", {}, "Contact"), h("div", { class: "card pad stack" },
    rows.length ? h("dl", { class: "kv" }, rows) : h("div", { class: "muted" }, "No contact details yet."),
    h("div", {}, h("button", { class: "btn small", type: "button", onclick: () => contactSheet(b) }, "Edit phone or email"))));
}

function notesCard(b) {
  const text = h("textarea", { placeholder: "What you talked about, who the owner is, what they want…", maxlength: 4000, "aria-label": "Note" });
  return h("section", { class: "section" }, h("h2", {}, "Add a note"), h("div", { class: "card pad stack" }, text,
    h("div", {}, h("button", { class: "btn", type: "button", onclick: () => { if (!text.value.trim()) return toast("Write something first"); act(b, { action: "note", text: text.value }, "Note added"); } }, "Add note"))));
}

function timelineCard(activity) {
  if (!activity.length) return null;
  return h("section", { class: "section" }, h("h2", {}, "History"), h("div", { class: "card" }, h("ul", { class: "timeline" },
    activity.map((a) => h("li", {}, h("div", { class: "ic", "aria-hidden": "true" }, KIND_ICON[a.kind] || "•"),
      h("div", { class: "grow" }, h("div", { class: "txt" }, a.detail || a.kind),
        a.meta && a.meta.recording && /^RE[0-9a-f]{32}$/.test(a.meta.recording) ? h("audio", { controls: true, preload: "none", src: `/api/recording/${a.meta.recording}` }) : null,
        h("div", { class: "when" }, `${fmtDate(a.at, true)} · ${new Date(a.at).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: "Asia/Beirut" })}`)))))));
}

// Sheets (pop-up forms) --------------------------------------------------------------------------------------
function sheet(...content) {
  const box = h("div", { class: "sheet", role: "dialog", "aria-modal": "true" }, ...content);
  const scrim = h("div", { class: "scrim", onclick: (e) => { if (e.target === scrim) close(); } }, box);
  const onKey = (e) => { if (e.key === "Escape") close(); };
  function close() { scrim.remove(); document.removeEventListener("keydown", onKey); }
  document.addEventListener("keydown", onKey);
  document.body.append(scrim);
  const first = box.querySelector("input, select, textarea, button");
  if (first) setTimeout(() => first.focus(), 30);
  return close;
}
const field = (label, input) => h("label", { class: "field" }, h("span", {}, label), input);

function boughtSheet(b, plans) {
  plans = plans && plans.length ? plans : [{ id: "custom", label: "Custom", price: 0, cycle: "monthly" }];
  const current = plans.find((p) => p.id === b.plan) || plans[0];
  const plan = h("select", {}, plans.map((p) => h("option", { value: p.id, selected: p.id === current.id }, `${p.label} · ${money(p.price)}${per(p.cycle)}`)));
  const price = h("input", { type: "number", min: 0, step: "0.01", value: b.eff === "client" && b.price != null ? b.price : current.price });
  const setup = h("input", { type: "number", min: 0, step: "0.01", value: b.eff === "client" && b.setup_fee != null ? b.setup_fee : current.setup_fee || 0 });
  const cycle = h("select", {}, [["monthly", "Every month"], ["yearly", "Every year"], ["once", "One time"]].map(([v, l]) =>
    h("option", { value: v, selected: v === (b.eff === "client" && b.cycle ? b.cycle : current.cycle) }, l)));
  const bought = h("input", { type: "date", value: b.bought_at || todayStr(), max: todayStr() });
  const renewNote = h("div", { class: "muted small" });
  const start = h("input", { type: "checkbox", checked: b.agent === "studio" && b.eff !== "client" });
  const update = () => {
    const next = addCycle(bought.value, cycle.value);
    renewNote.textContent = cycle.value === "once" ? "One-time payment: no renewal." : next ? `First renewal: ${fmtDate(next, true)}` : "";
  };
  plan.addEventListener("change", () => {
    const p = plans.find((x) => x.id === plan.value);
    price.value = p.price; setup.value = p.setup_fee || 0; cycle.value = p.cycle; update();
  });
  cycle.addEventListener("change", update);
  bought.addEventListener("change", update);
  update();
  const save = h("button", { class: "btn ok", type: "button", style: "width:100%" }, "Save");
  const close = sheet(h("h3", {}, b.eff === "client" ? "Edit their plan" : "Mark as bought"),
    h("div", { class: "muted small", style: "margin-bottom:12px" }, `${b.name}. HQ keeps their renewal date and reminds you before it.`),
    h("div", { class: "stack" }, field("Plan", plan), h("div", { class: "grid2" }, field("Price", price), field("Paid how often", cycle)),
      h("div", { class: "grid2" }, field("Setup fee", setup), field("Date they bought", bought)), renewNote,
      b.agent === "studio" && b.eff !== "client" ? h("label", { class: "check" }, start, h("span", {}, "Start their service now: the studio agent sends the welcome email and makes their first week of posts on its next run.")) : null,
      save));
  save.addEventListener("click", async () => {
    save.disabled = true;
    const p = plans.find((x) => x.id === plan.value) || current;
    try {
      await act(b, { action: "bought", plan: p.id, plan_label: p.label, price: +price.value, setup_fee: +setup.value, cycle: cycle.value,
                     bought_at: bought.value, start_service: start.checked }, "Saved as a client");
      close();
    } catch { save.disabled = false; }
  });
}
function lostSheet(b) {
  const reasons = ["Not interested", "Already has someone", "Too expensive", "Closed down", "Asked not to be contacted"];
  const other = h("input", { type: "text", placeholder: "Other reason", maxlength: 200 });
  const close = sheet(h("h3", {}, "Why not?"), h("div", { class: "muted small", style: "margin-bottom:12px" }, "The agent stops emailing them."),
    h("div", { class: "stack" }, h("div", { class: "outcomes" }, reasons.map((r) => h("button", { class: "btn", type: "button", onclick: () => { act(b, { action: "stage", stage: "lost", reason: r }, "Marked lost"); close(); } }, r))),
      other, h("button", { class: "btn", type: "button", onclick: () => { act(b, { action: "stage", stage: "lost", reason: other.value || "Not interested" }, "Marked lost"); close(); } }, "Save")));
}
function renewalSheet(b) {
  const date = h("input", { type: "date", value: b.renews_at || todayStr() });
  const close = sheet(h("h3", {}, "Next renewal date"), h("div", { class: "stack", style: "margin-top:12px" }, date,
    h("button", { class: "btn primary", type: "button", onclick: () => { act(b, { action: "renews", date: date.value }, "Renewal date saved"); close(); } }, "Save")));
}
function contactSheet(b) {
  const phone = h("input", { type: "tel", value: b.my_phone || b.dial || "", placeholder: "(614) 555-0101" });
  const email = h("input", { type: "email", value: b.my_email || b.mail || "", placeholder: "owner@business.com" });
  const close = sheet(h("h3", {}, "Contact details"), h("div", { class: "muted small", style: "margin-bottom:12px" }, "Use this when you get the owner's direct number or email. The agent's details stay in its own records."),
    h("div", { class: "stack" }, field("Phone", phone), field("Email", email),
      h("button", { class: "btn primary", type: "button", onclick: async () => { try { await act(b, { action: "contact", phone: phone.value.trim(), email: email.value.trim() }, "Saved"); close(); } catch { /* shown */ } } }, "Save")));
}

// Adding a business by hand ----------------------------------------------------------------------------------------
function viewAdd() {
  const f = { name: h("input", { type: "text", maxlength: 200, required: true }), phone: h("input", { type: "tel" }),
              email: h("input", { type: "email" }), city: h("input", { type: "text" }), state: h("input", { type: "text", maxlength: 2, placeholder: "OH" }),
              kind: h("input", { type: "text", placeholder: "Restaurant, plumber…" }), website: h("input", { type: "text", placeholder: "https://" }) };
  const save = h("button", { class: "btn primary", type: "submit" }, "Add");
  frame("Add a business", null, "pipeline", h("form", { class: "card pad stack", onsubmit: async (e) => {
    e.preventDefault();
    save.disabled = true;
    try {
      const d = await api("/api/businesses", Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v.value.trim()])));
      go(`/b/${encodeURIComponent(d.key)}`, true);
    } catch (e2) { if (e2.message !== "login") toast(e2.message); save.disabled = false; }
  } }, h("div", { class: "muted small" }, "For a referral, someone who called you, or anyone the agents didn't find."),
    field("Business name", f.name), h("div", { class: "grid2" }, field("Phone", f.phone), field("Email", f.email)),
    h("div", { class: "grid2" }, field("City", f.city), field("State", f.state)), field("Kind of business", f.kind), field("Website", f.website), save));
}

// Settings ---------------------------------------------------------------------------------------------------------
async function viewSettings() {
  loading("Settings", "settings");
  let s;
  try { s = await api("/api/settings"); } catch (e) { if (e.message !== "login") failed("Settings", "settings", e); return; }
  const copy = (text, what) => h("button", { class: "btn small", type: "button", onclick: async () => {
    try { await navigator.clipboard.writeText(text); toast(`${what} copied`); } catch { toast("Couldn't copy: select it and copy by hand"); }
  } }, "Copy");
  const tokenBox = h("code", { class: "code" }, "•".repeat(24));
  let shown = false;
  const agentLine = (id, label) => {
    const a = s.agents[id], n = (s.counts || {})[id] || 0;
    return h("li", { class: "row" }, h("div", { class: "grow" }, h("div", { class: "name" }, label),
      h("div", { class: "meta" }, a ? `Last heard from ${rel(a.at)} · ${n} business${n === 1 ? "" : "es"} here` : "Not connected yet"),
      a && a.mode === "draft" ? h("div", { class: "meta", style: "color:var(--warn)" }, "In draft mode: it isn't emailing anyone yet") : null),
      h("span", { class: "pill", style: `--c: var(${a ? "--s-client" : "--s-no_reply"})` }, a ? "Connected" : "Waiting"));
  };
  const hourSel = h("select", { "aria-label": "Daily list time" }, Array.from({ length: 24 }, (_, i) =>
    h("option", { value: i, selected: i === s.digest_hour }, `${i % 12 || 12}:00 ${i < 12 ? "am" : "pm"}`)));
  hourSel.addEventListener("change", async () => { try { await api("/api/settings", { digest_hour: +hourSel.value }); toast("Saved"); } catch (e) { toast(e.message); } });
  const nameInput = h("input", { type: "text", value: s.name, placeholder: "Omar Bader Studio", maxlength: 80 });
  const connectBtn = h("button", { class: "btn primary", type: "button", disabled: !s.twilio.secrets, onclick: async () => {
    connectBtn.disabled = true;
    connectBtn.textContent = "Connecting…";
    try { const r = await api("/api/twilio/connect", {}); toast(`Connected: ${fmtPhone(r.number)}`); ME = null; render(); } catch (e) { toast(e.message, 6000); connectBtn.disabled = false; connectBtn.textContent = "Connect Twilio"; }
  } }, s.twilio.connected ? "Connect again" : "Connect Twilio");

  frame("Settings", null, "settings",
    h("section", { class: "section" }, h("h2", {}, "Your agents"), h("div", { class: "card" }, h("ul", { class: "list" },
      agentLine("lead", "Websites agent"), agentLine("security", "Security agent"), agentLine("studio", "Studio agent")))),
    h("div", { class: "card pad stack", style: "margin-top:10px" },
      h("div", { class: "muted small" }, "To connect an agent, add these two secrets in its GitHub repository (Settings → Secrets and variables → Actions). It sends its businesses here after its next run."),
      h("div", {}, h("div", { class: "split", style: "justify-content:space-between" }, h("b", {}, "HQ_URL"), copy(s.url, "HQ_URL")), h("code", { class: "code" }, s.url)),
      h("div", {}, h("div", { class: "split", style: "justify-content:space-between" }, h("b", {}, "HQ_TOKEN"),
        h("div", { class: "split" }, h("button", { class: "btn small", type: "button", onclick: () => { shown = !shown; tokenBox.textContent = shown ? s.token : "•".repeat(24); } }, "Show"), copy(s.token, "HQ_TOKEN"))), tokenBox),
      h("div", {}, h("button", { class: "btn small danger", type: "button", onclick: async () => {
        if (!confirm("Make a new token? Every agent stops syncing until you update HQ_TOKEN in its GitHub secrets.")) return;
        try { await api("/api/settings/token", {}); toast("New token made"); viewSettings(); } catch (e) { toast(e.message); }
      } }, "Make a new token"))),
    h("section", { class: "section" }, h("h2", {}, "Calling (Twilio)"), h("div", { class: "card pad stack" },
      s.twilio.connected ? h("div", { class: "note ok" }, `Calls go out from ${fmtPhone(s.twilio.number)}. Calls to that number ring HQ while it's open, then go to voicemail.`)
        : h("div", { class: "muted small" }, "1. In Twilio, buy a US local number. 2. Add TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN to this Worker's secrets in Cloudflare. 3. Press Connect Twilio."),
      !s.twilio.secrets ? h("div", { class: "note" }, "The Twilio secrets aren't on this Worker yet.") : null,
      h("div", {}, connectBtn))),
    h("section", { class: "section" }, h("h2", {}, "Telegram"), h("div", { class: "card pad stack" },
      s.telegram ? h("div", { class: "muted small" }, "Your call list, replies and renewals come once a day. Missed calls and voicemails come right away.")
        : h("div", { class: "note" }, "Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to this Worker's secrets (one of your agents' bots is fine)."),
      field("Daily list at (Beirut time)", hourSel),
      h("div", { class: "split" },
        h("button", { class: "btn", type: "button", disabled: !s.telegram, onclick: async () => { try { await api("/api/telegram/test", {}); toast("Sent: check Telegram"); } catch (e) { toast(e.message, 5000); } } }, "Send a test"),
        h("button", { class: "btn", type: "button", onclick: previewDigest }, "Preview today's list")))),
    h("section", { class: "section" }, h("h2", {}, "Your business"), h("div", { class: "card pad stack" },
      field("Name callers hear on your voicemail", nameInput),
      h("div", {}, h("button", { class: "btn", type: "button", onclick: async () => { try { await api("/api/settings", { name: nameInput.value }); toast("Saved"); } catch (e) { toast(e.message); } } }, "Save")))),
    h("section", { class: "section" }, h("button", { class: "btn", type: "button", onclick: async () => { await fetch("/api/logout", { method: "POST" }); ME = null; showLogin(); } }, "Log out")));
}

async function previewDigest() {
  try {
    const d = await api("/api/digest");
    const text = (d.text || "Nothing to send today: no calls, replies, renewals or reminders.")
      .replace(/<a href="[^"]*">([^<]*)<\/a>/g, "$1").replace(/<\/?[bi]>/g, "")
      .replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&amp;/g, "&");
    sheet(h("h3", {}, "Today's Telegram list"), h("div", { class: "muted small", style: "margin-bottom:10px" }, "As it will look (names are links in Telegram)."),
      h("div", { class: "quote", style: "border-left-color:var(--accent)" }, text));
  } catch (e) { if (e.message !== "login") toast(e.message); }
}

// Calling ------------------------------------------------------------------------------------------------------------
let device = null, call = null, callInfo = null, timer = null;
function loadSdk() {
  if (window.Twilio && window.Twilio.Device) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = SDK; s.integrity = SDK_SRI; s.crossOrigin = "anonymous";
    s.onload = resolve;
    s.onerror = () => reject(new Error("Couldn't load the calling library. Check your connection."));
    document.head.append(s);
  });
}
async function ensureDevice() {
  if (device) return device;
  await loadSdk();
  const t = await api("/api/twilio/token");
  device = new window.Twilio.Device(t.token, { logLevel: "error", codecPreferences: ["opus", "pcmu"], closeProtection: "You're on a call. Leave HQ anyway?" });
  device.on("tokenWillExpire", async () => { try { device.updateToken((await api("/api/twilio/token")).token); } catch { /* next call fetches one */ } });
  device.on("incoming", onIncoming);
  device.on("error", (e) => { if (e && e.code !== 31005) toast(e.message || "Calling error"); });
  return device;
}
async function registerForIncoming() {
  if (!ME || !ME.twilio) return;
  try { const d = await ensureDevice(); if (d.state !== "registered") await d.register(); } catch (e) { console.warn("HQ: incoming calls off", e); }
}
async function startCall(b) {
  if (!ME || !ME.twilio) { toast("Connect Twilio in Settings first, then you can call from here."); return; }
  if (!b.dial) { toast("No phone number for this business."); return; }
  if (call) { toast("You're already on a call."); return; }
  callInfo = { key: b.key, name: b.name, number: b.dial, status: "Connecting…", muted: false, dir: "out" };
  renderCallBar();
  try {
    const d = await ensureDevice();
    call = await d.connect({ params: { To: b.dial, key: b.key } });
    wire(call);
  } catch (e) {
    call = null; callInfo = null; renderCallBar();
    toast(e.message || "Couldn't start the call", 5000);
  }
}
function wire(c) {
  let started = null;
  c.on("ringing", () => setStatus("Ringing…"));
  c.on("accept", () => {
    started = Date.now();
    setStatus("0:00");
    clearInterval(timer);
    timer = setInterval(() => setStatus(fmtDur((Date.now() - started) / 1000)), 1000);
  });
  const end = (why) => {
    clearInterval(timer);
    const info = callInfo, sid = c.parameters && c.parameters.CallSid;
    call = null; callInfo = null; renderCallBar();
    if (why) toast(why);
    if (info && info.key) askOutcome(info, sid, started ? Math.round((Date.now() - started) / 1000) : 0);
  };
  c.on("disconnect", () => end(null));
  c.on("cancel", () => end(null));
  c.on("reject", () => end("Call declined"));
  c.on("error", (e) => end(e && e.message ? `Call problem: ${e.message}` : "The call dropped"));
}
function setStatus(text) {
  if (!callInfo) return;
  callInfo.status = text;
  const el = document.getElementById("call-status");
  if (el) el.textContent = text;
}
function renderCallBar() {
  const old = document.getElementById("callbar");
  if (old) old.remove();
  if (!callInfo || callInfo.ringing) return;
  const mute = h("button", { class: `btn icon${callInfo.muted ? " on" : ""}`, type: "button", "aria-label": "Mute", title: "Mute", onclick: () => {
    if (!call) return;
    callInfo.muted = !callInfo.muted; call.mute(callInfo.muted); mute.classList.toggle("on", callInfo.muted);
  } }, icon("mic"));
  const bar = h("div", { class: "callbar", id: "callbar", role: "region", "aria-label": "Call" },
    h("div", { class: "who" }, h("b", {}, callInfo.name), h("span", { id: "call-status" }, callInfo.status), h("span", {}, ` · ${fmtPhone(callInfo.number)}`)),
    mute,
    h("button", { class: "btn icon", type: "button", "aria-label": "Keypad", title: "Keypad", onclick: keypad }, icon("keypad")),
    h("button", { class: "btn icon end", type: "button", "aria-label": "Hang up", title: "Hang up", onclick: () => { if (call) call.disconnect(); else { callInfo = null; renderCallBar(); } } }, icon("end")));
  document.body.append(bar);
}
function keypad() {
  const shown = h("div", { class: "code", style: "min-height:36px;text-align:center;font-size:18px" }, "");
  sheet(h("h3", {}, "Keypad"), h("div", { class: "muted small" }, "For phone menus (\"press 1 for…\")."), shown,
    h("div", { class: "keypad" }, ["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"].map((k) =>
      h("button", { class: "btn", type: "button", onclick: () => { if (call) { call.sendDigits(k); shown.textContent += k; } } }, k))));
}
function onIncoming(c) {
  const params = c.customParameters || new Map();
  const name = params.get("name") || "Someone", key = params.get("key") || "";
  const close = sheet(h("h3", {}, "Incoming call"), h("div", { style: "font-size:20px;font-weight:700;margin:8px 0" }, name),
    key ? h("div", { class: "muted small" }, "One of your businesses is calling you back.") : null,
    h("div", { class: "grid2", style: "margin-top:16px" },
      h("button", { class: "btn danger solid", type: "button", onclick: () => { c.reject(); close(); } }, "Decline"),
      h("button", { class: "btn ok", type: "button", onclick: () => {
        close();
        call = c; callInfo = { key, name, number: (c.parameters && c.parameters.From) || "", status: "0:00", muted: false, dir: "in" };
        renderCallBar(); wire(c); c.accept();
      } }, "Answer")));
  c.on("cancel", close);
}
function askOutcome(info, sid, seconds) {
  let chosen = null;
  const date = h("input", { type: "date", value: new Date(Date.now() + 86400000).toISOString().slice(0, 10), min: todayStr() });
  const dateBox = h("div", { class: "hide" }, field("Call back on", date));
  const note = h("textarea", { placeholder: "Anything to remember (optional)", maxlength: 2000 });
  const buttons = OUTCOMES.map(([id, label]) => h("button", { class: "btn", type: "button", onclick: () => {
    chosen = id; buttons.forEach((b) => b.classList.toggle("on", b.dataset.id === id)); dateBox.classList.toggle("hide", id !== "callback");
  }, "data-id": id }, label));
  const save = h("button", { class: "btn primary", type: "button", style: "width:100%" }, "Save");
  const close = sheet(h("h3", {}, `How did it go with ${info.name}?`), h("div", { class: "muted small", style: "margin-bottom:12px" }, seconds ? `Call lasted ${fmtDur(seconds)}.` : "The call didn't connect."),
    h("div", { class: "stack" }, h("div", { class: "outcomes" }, buttons), dateBox, note, save,
      h("button", { class: "btn", type: "button", style: "width:100%", onclick: () => close() }, "Skip")));
  save.addEventListener("click", async () => {
    if (!chosen) { toast("Pick how it went"); return; }
    save.disabled = true;
    try {
      const d = await api(`/api/business/${encodeURIComponent(info.key)}`, { action: "call_outcome", outcome: chosen, note: note.value, date: chosen === "callback" ? date.value : null, sid });
      close();
      toast("Saved");
      if (location.pathname === `/b/${encodeURIComponent(info.key)}`) drawBusiness(d); else render();
    } catch (e) { if (e.message !== "login") toast(e.message); save.disabled = false; }
  });
}

render();
