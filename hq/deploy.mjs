// Deploys HQ to your Cloudflare account: finds (or makes) the "studio-hq" D1 database, writes its id into
// wrangler.toml, then runs wrangler deploy. Needs CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID.
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";

const WRANGLER = ["--yes", "wrangler@4.147.0"];
const NAME = "studio-hq";
const wrangler = (args, inherit = false) =>
  execFileSync("npx", [...WRANGLER, ...args], { encoding: "utf8", stdio: inherit ? "inherit" : ["ignore", "pipe", "inherit"] });

function findDb() {
  const out = wrangler(["d1", "list", "--json"]);
  const list = JSON.parse(out.slice(out.indexOf("[")));
  return list.find((d) => d.name === NAME);
}

let db = findDb();
if (!db) {
  console.log(`Making the D1 database "${NAME}"…`);
  wrangler(["d1", "create", NAME]);
  db = findDb();
}
if (!db || !db.uuid) throw new Error(`Couldn't find or make the D1 database "${NAME}".`);
console.log(`D1 database: ${NAME} (${db.uuid})`);

const toml = readFileSync("wrangler.toml", "utf8").replace(/database_id = "[^"]*"/, `database_id = "${db.uuid}"`);
writeFileSync("wrangler.toml", toml);
if (process.env.VISIBILITY === "public") {
  // Anyone can read a public repository's logs, so HQ's address isn't printed here.
  const out = wrangler(["deploy"]);
  console.log(out.replace(/https:\/\/[a-z0-9.-]+\.workers\.dev/gi, "https://studio-hq.<your-subdomain>.workers.dev"));
  console.log("\nHQ is deployed. Its address: Cloudflare → Workers & Pages → studio-hq (Domains & Routes).");
} else {
  wrangler(["deploy"], true);
  console.log("\nHQ is deployed. Its address is the workers.dev link above.");
}
console.log("Next: in Cloudflare, add the secret HQ_PASSWORD to the studio-hq Worker, then open HQ's address.");
