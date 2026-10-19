// Starts your agents on time.
//
// GitHub's own scheduler has been starting workflows hours late, or not at all, since late August 2026,
// while a manual "Run workflow" always starts right away. This free Cloudflare Worker presses that
// "Run workflow" button for you, on schedule, through GitHub's API.
//
// Setup (about 10 minutes) is in README.md next to this file. In short:
//   1. A GitHub token that can only run workflows in your agent repositories.
//   2. A Cloudflare Worker with this code, the token saved as the secret GITHUB_TOKEN,
//      and one Cron Trigger:  7,13,37 * * * *   (minute 7 = daily runs, 13 = reply checks, 37 = studio agent)

const OWNER = "OmarBader-dev";
const HOURS = (from, to) => Array.from({ length: to - from + 1 }, (_, i) => from + i);

// Times are UTC. "weekdays" means Monday to Friday. "date" (UTC, YYYY-MM-DD) limits a job to one day. "workflow" is the name at the top of the workflow file.
// If you named a repository differently, change "repo" here.
const JOBS = [
  // The website agent: send windows for the East Coast, Central/Mountain and West Coast.
  { repo: "lead-agent", workflow: "Lead agent", command: "daily", minute: 7, hours: [14, 17, 20], weekdays: true },
  // Replies, every 3 hours from 06:13 to 21:13 UTC (morning to around midnight in Beirut), to save GitHub minutes
  // for the studio agent. For every hour again, use hours: HOURS(5, 21).
  { repo: "lead-agent", workflow: "Lead agent", command: "inbox", minute: 13, hours: [6, 9, 12, 15, 18, 21] },

  // The security agent: two send windows on weekdays, and replies plus the links you share with its bot.
  { repo: "security-agent", workflow: "Security agent", command: "daily", minute: 7, hours: [13, 16], weekdays: true },
  { repo: "security-agent", workflow: "Security agent", command: "inbox", minute: 13, hours: [6, 9, 12, 15, 18, 21] },

  // The studio agent (social media + design): samples and emails on weekdays at 14:37 UTC, and its inbox
  // (your Telegram commands, replies, client requests) at 06:37, 10:37 and 19:37 UTC (9:37, 13:37, 22:37 Beirut).
  { repo: "studio-agent", workflow: "Studio agent", command: "daily", minute: 37, hours: [14], weekdays: true },
  { repo: "studio-agent", workflow: "Studio agent", command: "inbox", minute: 37, hours: [6, 10, 19] },
];

function due(date) {
  const day = date.getUTCDay();
  return JOBS.filter((j) => j.minute === date.getUTCMinutes() && j.hours.includes(date.getUTCHours())
    && !(j.weekdays && (day === 0 || day === 6)) && (!j.date || j.date === date.toISOString().slice(0, 10)));
}

function github(env, path, body) {
  return fetch(`https://api.github.com/repos/${OWNER}/${path}`, {
    method: body ? "POST" : "GET",
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "agent-scheduler",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
}

async function run(env, job) {
  // Find the workflow by its name, so it works whatever the file is called (main.yml, agent.yml...).
  const list = await github(env, `${job.repo}/actions/workflows?per_page=100`);
  // 401 = the token expired or is wrong. 404 = no such repository yet, or the token can't see it.
  if (!list.ok) return console.log(`${job.repo}: can't see its workflows (${list.status})`);
  const flow = ((await list.json()).workflows || []).find((w) => w.name === job.workflow);
  if (!flow) return console.log(`${job.repo}: no workflow named "${job.workflow}"`);
  const r = await github(env, `${job.repo}/actions/workflows/${flow.id}/dispatches`,
    { ref: "main", inputs: { command: job.command } });
  console.log(`${job.repo} ${job.command}: ${r.status === 204 ? "started" : `failed (${r.status}) ${await r.text()}`}`);
}

export default {
  async scheduled(event, env) {
    await Promise.all(due(new Date(event.scheduledTime)).map((job) => run(env, job)));
  },
  // Visit <your worker address>/check to see whether the token can reach both repos. Read-only: it starts
  // nothing and never shows the token.
  async fetch(request, env) {
    if (new URL(request.url).pathname !== "/check") {
      return new Response("Agent scheduler is running. It starts your agents on GitHub on schedule.\n");
    }
    if (!env.GITHUB_TOKEN) return new Response("No GITHUB_TOKEN secret is set on this Worker.\n");
    const lines = [];
    for (const [repo, name] of [...new Map(JOBS.map((j) => [j.repo, j.workflow]))]) {
      const r = await github(env, `${repo}/actions/workflows?per_page=100`);
      if (r.ok) {
        const found = ((await r.json()).workflows || []).some((w) => w.name === name);
        lines.push(`${repo}: ${found ? `OK, found the "${name}" workflow` : `token works, but no workflow named "${name}"`}`);
      } else {
        const why = { 401: "the token was rejected: it's wrong, expired, or pasted with extra spaces",
                      403: "the token isn't allowed: set Actions to Read and write",
                      404: "the token can't see this repo: choose 'Only select repositories' and tick it" }[r.status];
        lines.push(`${repo}: error ${r.status}${why ? ` (${why})` : ""}`);
      }
    }
    return new Response(lines.join("\n") + "\n");
  },
};
