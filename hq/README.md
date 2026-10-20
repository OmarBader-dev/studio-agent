# HQ

Your private dashboard for every business your three agents find (websites, security, studio): what stage each
one is at, who to call today, and your clients with the date they bought and when they renew. You can call any
business from it with your own US Twilio number, right in the browser.

## What it does

| Page | What's on it |
|---|---|
| **Today** | Calls to make, each with the best time to call in Beirut time; replies waiting (with what they wrote); interested businesses; renewals this week; your reminders |
| **Pipeline** | Every business by stage: Replied, Interested, Preview sent, Call or DM, Preview ready, No reply, Clients, Lost. Filter by agent, search by name, city, email or phone, add a business by hand |
| **Clients** | Plan, price, date they bought, next renewal, Mark paid. Your monthly revenue at the top |
| **A business** | Call, email, open their preview or website; mark Interested, Bought (plan, price, setup fee, monthly/yearly/once) or Not interested; reminders; notes; the whole history (emails the agent sent, follow-ups, replies, calls, voicemails) |
| **Settings** | Connect the agents, Twilio and Telegram; when the daily list comes |

What you decide in HQ goes back to the agents on their next run:
- Anyone you mark **interested**, **bought** or **not interested** stops getting the agent's emails.
- A studio business you mark as bought with **Start their service now** gets the welcome email and its first week
  of posts from the studio agent, same as `/client` on Telegram.

On Telegram (any of your bots works): one list a day at the hour you pick (calls, replies, renewals, reminders),
and a message right away for missed calls and voicemails.

## What it costs

HQ itself is free: a Cloudflare Worker and a D1 database on the free plan. Calling uses Twilio: about $1.15 a month
for the number and 1.3 cents a minute, so 100 two-minute calls cost about $4.

## Setup (about 20 minutes)

1. **Cloudflare token.** The `CLOUDFLARE_API_TOKEN` secret in this repository needs these permissions, on top of
   Cloudflare Pages · Edit and Workers AI · Edit: **Workers Scripts · Edit**, **D1 · Edit** and
   **Account Settings · Read**. Cloudflare → My Profile → API Tokens → your token → Edit (no need for a new one).
2. **Put HQ online.** GitHub → studio-agent → Actions → **HQ** → Run workflow. Your HQ address, like
   `https://studio-hq.your-name.workers.dev`, is in Cloudflare → Workers & Pages → studio-hq (a private repository
   also prints it at the end of the log). Bookmark it, or add it to your phone's home screen.
3. **Your password.** Cloudflare → Workers & Pages → **studio-hq** → Settings → Variables and Secrets → Add →
   type **Secret**, name `HQ_PASSWORD`, a long password only you know. Open your HQ address and log in.
4. **Connect the agents.** HQ → Settings shows two values, `HQ_URL` and `HQ_TOKEN`. Add both as secrets in each
   agent's repository (lead-agent, security-agent, studio-agent → Settings → Secrets and variables → Actions). Each
   agent sends its businesses after its next run, and Settings shows when each one was last heard from.
5. **Telegram.** On the studio-hq Worker, add the secrets `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` (the studio
   bot's are fine: HQ only sends). Then HQ → Settings → Send a test.
6. **Calling (Twilio).**
   1. Sign up at twilio.com and add some credit. A free trial can only call numbers you've verified yourself.
   2. Phone Numbers → Buy a number → United States, with Voice. A local area code from your target cities
      (614 for Columbus, 317 for Indianapolis…) looks local on their phone.
   3. From the Twilio Console home, copy the Account SID and Auth Token into two more Worker secrets:
      `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN`.
   4. HQ → Settings → **Connect Twilio**. HQ makes its own API key and calling app in your Twilio account and
      points your number at HQ.
   5. Register the number for free at freecallerregistry.com, so it's less likely to show up as "Spam Likely".
   6. The first time you press Call, your browser asks to use the microphone: allow it.

## Calling

- Press **Call** on a business. They see your Twilio number. When you hang up, pick how it went: Interested,
  Not interested, Call back later (with a date, which becomes a reminder), Left a voicemail, No answer, Wrong number.
- HQ only dials the phone numbers of businesses saved in it, and only US and Canadian numbers, so a leaked
  login can't run up an international bill.
- When a business calls your number back, it rings in HQ for 20 seconds if HQ is open; otherwise they hear your
  voicemail greeting (with the name from Settings) and you get a Telegram message. Voicemails play on the
  business's page in HQ.
- Calls aren't recorded. Texting isn't included: US carriers require a business registration (A2P 10DLC) first.

## Updates and your data

HQ puts itself back online whenever its files change in this repository (Actions → HQ). Your businesses, notes,
calls and clients live in the `studio-hq` D1 database in your Cloudflare account and stay through updates.

## Files

| File | What it is |
|---|---|
| `src/index.js` | The Worker: login, the agents' sync, the pages' data, Twilio calls and voicemail, the daily list |
| `public/` | The web app (no build step) |
| `wrangler.toml`, `deploy.mjs` | Deployment (the database id is filled in at deploy time) |
| `test/e2e.py` | End-to-end test against a local copy: `npx wrangler dev`, then `python3 test/e2e.py` |
