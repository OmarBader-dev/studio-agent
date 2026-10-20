# Studio agent: social media + graphic design for local businesses

Two AI agents that work together, for $0 a month:

- **The social media agent** watches what's happening (holidays and "national days", the season, local weather
  and events, what people are searching and talking about today) and turns it into posts that fit one brand:
  the idea, the words on the image, the caption, hashtags, alt text and the best time to post.
- **The graphic design agent** reads a business's look from its own website (logo, colors, fonts, photos),
  follows this week's design directions from design publications (Behance, Abduzeedo, The Dieline, Creative
  Bloq, Dezeen), and designs posts, stories, short videos (Reels/TikTok), Google Business Profile posts,
  flyers and more in that brand. Every design is checked automatically: no text overflowing, nothing too
  small to read, readable colors.

Together they find clients and serve them:

1. **Find businesses.** Restaurants, cafes, bakeries, gyms, salons and shops in your cities, from free open
   map data. Chains, sold or hijacked websites, and departments of big organizations are skipped.
2. **Make each one a free sample.** A private page with a week of posts made for them, in their own brand,
   tied to what's coming up, with captions they can copy, a short Reel of the first post, and a brand board
   showing their kit.
3. **Email it** (or, when there's no public email, send it to you on Telegram with a DM to copy for their
   Instagram or Facebook). Two short follow-ups. Replies come to you on Telegram.
4. **Serve clients.** Each week it plans and designs their posts (plus story versions, a Reel and a post for
   their Google Business Profile), you check them on Telegram, the client gets them by email with the images
   and video attached, "approved" approves them, and they're posted for them (with Meta connected) or you get
   a reminder with the image and caption on the day. Design clients email requests ("a flyer for Friday's
   open mic") and get three versions back after you check them. Weeks still waiting for your check two days before
   they start get you a reminder.

It runs on GitHub Actions and starts in **draft mode**: it makes samples and writes the emails, but sends
nothing until you set `mode: "live"`.

## What clients get: three plans

Each agent is sold on its own. A client gets both only with the bundle (set `plan` in `clients.yaml`).

| | Social ($99/month) | Design ($49/month) | Social + Design ($129/month) |
|---|---|---|---|
| 3 posts a week, designed in their brand, tied to holidays, the season, local weather and trends | ✓ | | ✓ |
| Captions, hashtags, alt text and the best time to post | ✓ | | ✓ |
| Story versions, a Reel (video) and a Google Business Profile post every week | ✓ | | ✓ |
| Posts approved by email, then posted for them (Meta) or sent to you to post | ✓ | | ✓ |
| Designs on request: 3 versions of any flyer, promo, sign or social graphic | | 8 a month | 8 a month |
| Menus, price lists and class schedules, print-ready PDFs plus Instagram versions | | ✓ | ✓ |
| Their brand kit (logo, colors, fonts) kept ready | ✓ | ✓ | ✓ |
| Monthly report (posts made and posted, likes, next month's moments) | ✓ | designs made | ✓ |

When a Social client emails asking for a flyer, the agent doesn't make it: it tells you on Telegram and suggests
offering Design or the bundle (or `/design` makes it anyway). Weekly posts only go to Social and bundle clients.
Over the monthly design allowance you're told, and you decide.

The free sample a business gets shows both agents: a week of posts and a Reel (social) and, when its website has
one, its own menu, price list or class schedule redesigned in its brand (design).

## Autopilot: what it does without you

With `autopilot` on (the default in `config.yaml`), the agents run the business and you step in only where a
person has to:

| It does on its own | You do |
|---|---|
| Finds businesses, makes their free samples, emails them and follows up | DM the few with no email (Meta bans automated DMs), or set `dm_handover_per_day: 0` |
| Answers "how much?" with the plans and prices, then catches the plan they choose | |
| Onboards them: welcome email, first week of posts made right away | Send `/client Joe's Pizza social` once they've chosen |
| Weekly posts, stories, Reel and Google post, sent to the client after its own checks | Nothing, unless a check fails (then it comes to you) |
| Posts them to Instagram and Facebook (once the client adds you to their Page, it connects them by itself) | Ask the client to add you to their Page |
| Designs they email for: versions to pick from ("reply 1, 2 or 3"), changes redone, final print-ready files | |
| Posters for upcoming holidays for every Design client, print-ready, without being asked | |
| Monthly reports to clients, and a reminder to you to bill each client every month | Send the Payoneer request, then `/paid name` |

Set `autopilot.clients: false` to check everything yourself first, or `review_first: true` for one client.

## What it costs: nothing

| What | Free service | Notes |
|---|---|---|
| Running it | GitHub Actions | 2,000 free minutes a month for private repos, unlimited for public ones (see "Minutes") |
| Pages | Cloudflare Pages | Your existing free account |
| Writing | Gemini, Groq, Cloudflare Workers AI, OpenRouter | Free tiers, no card. Works with any one of them |
| Abstract backgrounds | Cloudflare Workers AI | 10,000 free "neurons" a day, about 170 images |
| Photos | The business's own, Pixabay, Openverse | Free licenses |
| Businesses | Overture Maps | Free open data |
| Trends | Google Trends, Bluesky, Nager.Date, Open-Meteo | No keys |
| Fonts and icons | Google Fonts | Open licenses |
| Videos (Reels) | the same headless browser + ffmpeg | Built in; no music added (pick a free trending sound in Instagram) |
| Email | Gmail | 10 new businesses a day the first week, then 15 (plus up to 8 a day for you to DM) |

With no AI key at all it still works, using built-in templates (plainer writing).

## Setup (about 30 minutes)

### 1. A Gmail account for the studio
Use a new Gmail just for the studio (for example `omar.bader.studio@gmail.com`, if that name is free), so a
spam complaint can't hurt your other agents.
Turn on 2-Step Verification, then make an **App password** (Google Account → Security → App passwords).

### 2. A new Telegram bot
Each agent needs its own bot (two agents reading one bot would steal each other's messages). In Telegram,
message **@BotFather** → `/newbot` → copy the token. Send your new bot any message.

### 3. Free AI keys (any one is enough; more means more free requests)
- **Gemini**: aistudio.google.com/apikey → Create API key.
- **Groq**: console.groq.com/keys → Create API Key.
- **OpenRouter** (optional): openrouter.ai/keys.
- **Pixabay** (optional, theme photos): log in at pixabay.com, open pixabay.com/api/docs and copy your key
  (secret `PIXABAY_API_KEY`). Without it the agent uses the business's own photos and free Openverse photos.
  Pexels works too (`PEXELS_API_KEY`), but has paused new keys.

### 4. A Cloudflare token
dash.cloudflare.com → My Profile → API Tokens → Create Token → Custom token with:
- Account · **Cloudflare Pages** · Edit
- Account · **Workers AI** · Edit
- Account · **Workers Scripts** · Edit, Account · **D1** · Edit and Account · **Account Settings** · Read: these three
  are for HQ, your dashboard (see "HQ" below)

Your Account ID is on the right side of the Cloudflare dashboard's home page.

### 5. The GitHub repository
Create a new repository named `studio-agent` and upload all these files. Then Settings → Secrets and
variables → Actions → New repository secret, for each:

| Secret | Value |
|---|---|
| `GMAIL_APP_PASSWORD` | the app password from step 1 |
| `TELEGRAM_BOT_TOKEN` | from step 2 |
| `TELEGRAM_CHAT_ID` | run **Actions → Studio agent → Run workflow → telegram-id** after adding the token, and copy the number from the log |
| `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` | from step 4 |
| `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `PIXABAY_API_KEY` | from step 3 (any you have) |
| `STATE_KEY` | encrypts the agent's memory so the repository can be public: see "Minutes" |

### 6. config.yaml
Set `you.email` to the studio Gmail, check your mailing address (US law requires it in sales emails), your
cities, the kinds of businesses, and your prices. Commit.

### 7. Try it (still in draft mode)
1. **Run workflow → check**: it tests every key you've added (Gmail, AI, photos, Cloudflare, HQ) and sends
   you a ✅/❌ report on Telegram.
2. **Run workflow → trends** (target: `Columbus, OH`): the log lists what's worth posting about this week.
3. **Run workflow → sample** (target: any business website). Telegram sends you its sample page and a DM to copy.
4. Send your bot `/kit https://some-cafe.com` and `/trends`.
5. **Run workflow → daily**. Telegram shows the summary, one draft email, and the businesses to DM.
6. When you like the drafts, set `mode: "live"`.

### 8. Run it on schedule
Add these lines to `JOBS` in your agent-scheduler Worker (Cloudflare → Workers → agent-scheduler → Edit code),
then Deploy:

```js
  // The studio agent: samples and emails on weekdays, inbox (your Telegram commands, replies) 3 times a day.
  { repo: "studio-agent", workflow: "Studio agent", command: "daily", minute: 37, hours: [14], weekdays: true },
  { repo: "studio-agent", workflow: "Studio agent", command: "inbox", minute: 37, hours: [6, 10, 19] },
```

and change the Worker's Cron Trigger to `7,13,37 * * * *`. The `worker.js` in this repository already has these
lines, and checks your other agents' replies every 2 hours instead of every hour to stay in your free minutes
(see "Minutes"), so you can paste it whole. Also tick the new repository in the Worker's
GitHub token (Only select repositories), or `/check` will show a 404 for it.

With a public repository (unlimited minutes) you can check the inbox every hour instead, so the bot answers your
links and client emails within the hour: use `hours: HOURS(5, 21)` on the inbox line.

## Using the Telegram bot

Send it (it answers on the next inbox run, or run **inbox** yourself for an instant answer):

| Message | What happens |
|---|---|
| a business's website | it makes them a free sample and sends you the link plus a DM to copy |
| `/sample URL cafe` | the same, saying what kind of business it is |
| `/kit URL` | the brand kit of any website (logo, colors, fonts, photos) |
| `/design maple: flyer for open mic, Friday 7pm, free` | three versions for a client |
| `/design maple: menu` followed by lines like `Latte $4.50` | a menu (or price list, or class schedule) as three print-ready PDFs plus Instagram versions. With just `/design maple: our menu` it uses the menu on their website. Nothing is added that they didn't write |
| `/send JOB` or `/send JOB 2` | emails the client all versions, or just version 2 (with the PDFs) |
| `/week maple` | makes a client's posts for next week now |
| `/approve maple` | sends the posts you checked to the client |
| `/client Joe's Pizza social` | makes a business a client (social, design or bundle): welcome email, first posts now. Use its name from your leads, or its website. Add an email if they gave you another one |
| `/paid maple` | marks this month as paid (stops the payment reminders) |
| `/pause maple`, `/resume maple`, `/plan maple bundle` | stop or restart a client, or change their plan |
| `/trends` or `/trends Charlotte, NC` | what's worth posting about this week |
| `/status`, `/help` | counts, and the list |

Finding businesses yourself works great with this: when you see a local business on Instagram or Google
Maps, send its website to the bot, then send them the DM it gives you.

## When someone says yes

1. On autopilot they've already had the plans and prices. When they pick one, Telegram tells you: send
   `/client their name plan` and they're set up (welcome email, first posts). You can also add clients by hand
   in `clients.yaml` (copy the example in the file).
2. Send the Payoneer payment request (Social $99, Design $49, or both $129 a month) after their free week; the
   agent reminds you each month, and `/paid name` marks it paid. Photos they email you are saved and used
   automatically.
3. On their content day (default Thursday) the agent makes next week's posts and, on autopilot, emails them
   to the client (you get a copy on Telegram). If a check fails, or with `review_first: true`, they come to you
   first and `/approve name` sends them. "approved", or no answer by the day before the week starts, approves
   them; any other reply to that email is taken as changes, and the week is redone and sent again.
4. Approved posts, the Reel and the stories are posted for them once they've added you to their Facebook Page
   (below). Until then the client gets each day's post by email, ready to share. The Google post is in the pack
   (their profile → Add update).
5. Design clients email what they need and get versions to pick from; "2" gets the final print-ready file,
   anything else is redone (up to 3 rounds, then it's yours). They also get posters for what's coming up.
6. On the first run of each month, each client gets a short report: what was made and posted, and what's
   coming up next month (you get a copy on Telegram). Set `reports: false` for a client to skip the email.

## HQ: your dashboard

`hq/` is a private web app on your Cloudflare account (free) for all three agents: every business by stage (preview
sent, replied, interested, client, lost), who to call today with the best time in Beirut time, a Call button that
calls from your own US Twilio number, and your clients with the date they bought and when they renew. Anyone you
mark interested, bought or not interested there stops getting the agents' emails, and a studio business you mark as
bought can have its service started straight away. Setup and details: [hq/README.md](hq/README.md).

## Posting for clients

1. Create a free Meta app at developers.facebook.com (type Business). In development mode it can post to
   Pages and Instagram accounts of people with a role on the app.
2. Generate a long-lived user token in the Graph API Explorer with `pages_show_list`, `pages_manage_posts`,
   `pages_read_engagement`, `instagram_basic`, `instagram_content_publish`, and save it as the
   `META_ACCESS_TOKEN` secret. It lasts 60 days; renew it every 2 months.
3. That's all on your side. The welcome email asks each client to add your Facebook account to their Page
   (Meta Business Suite → Settings → People) with their Instagram connected. On its next run the agent finds
   their Page by name or website, connects it, and from then on posts their pictures, Reels and stories itself.
   (You can still set `meta_page_id` and `meta_ig_id` by hand in `clients.yaml`.)

## Minutes

GitHub gives private repositories 2,000 free minutes a month, shared by all your repositories (when they run
out, every private agent stops until the next month). Public repositories run free without limit, so this
agent is meant to live in a **public** repository, with its memory encrypted:

1. **Make a STATE_KEY.** On your computer, open any browser tab, press F12, open the Console, paste this line
   and press Enter:
   `btoa(String.fromCharCode(...crypto.getRandomValues(new Uint8Array(32)))).replace(/\+/g,'-').replace(/\//g,'_')`
   It shows a random 44-character key (or run
   `python -c "import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"`).
2. **Save it twice:** as the secret `STATE_KEY` in this repository (Settings → Secrets and variables →
   Actions), and in your password manager. Without it the agent can't read its own memory; with a different
   key, runs stop instead of starting over and emailing businesses twice.
3. **Then make the repository public:** Settings → General → Danger Zone → Change visibility.
4. Settings → Actions → General → "Fork pull request workflows from outside collaborators": choose
   **Require approval for all outside collaborators**, and never approve runs on pull requests from strangers.

In a public repository the agent only ever saves `data/state.enc` (encrypted). Logs show counts and business
names, never emails; client photos they email you stay in the run cache; HQ's address isn't printed. If
`STATE_KEY` is missing in a public repository, the workflow stops before running and saves nothing.

## Rules it follows

- Sales emails only to US businesses, with a clear "this is a sales email", your mailing address, an easy
  opt-out, at most two follow-ups, and nothing ever again after "no thanks". "Remove" also hides their page.
- Emails are never guessed: only addresses the business lists on its own website or map listing that match it.
- No scraping of Instagram or Facebook. DMs are sent by you, by hand.
- Posts never invent prices, discounts, products or weather: anything the business's website doesn't back up
  is removed. They never promise giveaways, prizes or surprises the business didn't announce, and never say
  "swipe up". Product days (Chocolate Day, Taco Day...) are only used for businesses that sell the product.
  No celebrity, team or brand names ("the big game", not the trademark). No tragedies, politics or illness
  in trend posts. Alcohol posts are 21+ and never push drinking.
- Departments of big organizations (a museum's cafe, a hotel's bar) and chains are skipped: they don't hire a
  one-person studio.
- AI pictures are only abstract backgrounds, never fake photos of a business's food, products or place.
- Design trends are inspiration only. Nobody's work is copied; fonts are Google Fonts (open licenses).
- Sample pages are private (not indexed) and deleted after 30 days.

## Files

`agent/` the code (`social.py` writes the posts, `designer.py`, `styles.py`, `motion.py` and `menus.py` make the
designs, Reels and menus, `pipeline.py` finds and contacts businesses, `clients.py` serves clients) ·
`config.yaml` your settings · `clients.yaml` your clients · `data/state.json` (or `state.enc`) its memory ·
`clients/` client photos you add · `worker.js` the updated scheduler · `hq/` your dashboard (HQ) · `tests/` offline
tests (`python -m unittest discover tests`).
