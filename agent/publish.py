"""Publishing pages (free samples, client packs) to Cloudflare Pages (free plan).

Each run publishes only what it made, as its own deployment. Cloudflare keeps every deployment at its own
address (https://<id>.<project>.pages.dev) until it's deleted, so old samples stay up without being
stored anywhere, and deleting a deployment after limits.sample_days takes its samples down.
"""
import json
import re
import shutil
import subprocess
import time

import requests

from .store import iso, now, parse

CF_API = "https://api.cloudflare.com/client/v4"
MISSING_PROJECT = re.compile(r"does not exist|not found|could not find|no such project", re.I)
DEPLOY_URL = re.compile(r"https://[0-9a-f]{6,12}\.[a-z0-9-]+\.pages\.dev", re.I)


def _api(cfg, method, path, **kw):
    return requests.request(method, f"{CF_API}/accounts/{cfg.secret('CLOUDFLARE_ACCOUNT_ID')}{path}", timeout=30,
                            headers={"Authorization": f"Bearer {cfg.secret('CLOUDFLARE_API_TOKEN')}"}, **kw)


def configured(cfg):
    return bool(cfg.secret("CLOUDFLARE_API_TOKEN") and cfg.secret("CLOUDFLARE_ACCOUNT_ID"))


def deploy(cfg, folder):
    """Publish a folder. Returns {'url': this deployment's own address, 'id': ...} or None on failure."""
    cfg.require("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID")
    project = cfg["pages"]["cloudflare_project"]
    cmd = ["npx", "--yes", "wrangler@4", "pages", "deploy", str(folder), f"--project-name={project}",
           "--branch=main", "--commit-dirty=true"]
    run = lambda c: subprocess.run(c, capture_output=True, text=True, timeout=600)
    out = run(cmd)
    if out.returncode != 0 and MISSING_PROJECT.search(out.stdout + out.stderr):
        made = run(["npx", "--yes", "wrangler@4", "pages", "project", "create", project, "--production-branch=main"])
        print("Created Cloudflare Pages project", project if made.returncode == 0 else f"(failed: {made.stderr[-400:]})")
        out = run(cmd)
    if out.returncode != 0:
        print("Deploy failed:\n", out.stdout[-1500:], out.stderr[-1500:])
        return None
    url = (DEPLOY_URL.findall(out.stdout + out.stderr) or [None])[-1]
    latest = latest_deployment(cfg)
    if latest and (not url or latest.get("url", "").rstrip("/") == url.rstrip("/")):
        return {"url": latest["url"].rstrip("/"), "id": latest["id"]}
    return {"url": url.rstrip("/"), "id": None} if url else None


def latest_deployment(cfg):
    try:
        r = _api(cfg, "GET", f"/pages/projects/{cfg['pages']['cloudflare_project']}/deployments", params={"per_page": 5})
        items = r.json().get("result") or []
    except (requests.RequestException, ValueError):
        return None
    return items[0] if items else None


def is_live(url, tries=6, wait=10):
    """Whether a published page opens. Retries for about a minute while Cloudflare updates."""
    for attempt in range(tries):
        try:
            if requests.get(url, timeout=20).status_code == 200:
                return True
        except requests.RequestException:
            pass
        if attempt < tries - 1:
            time.sleep(wait)
    return False


def remember(store, deployment, kind):
    store.data.setdefault("deployments", []).append({"id": deployment.get("id"), "url": deployment["url"],
                                                     "at": iso(), "kind": kind})
    if deployment.get("removed") is not None:          # this deployment carried the newest removal list
        store.flag("removed_published", deployment["removed"])


def removed_list(store):
    """Sample pages whose business asked for them to be taken down (their tokens)."""
    return sorted({t for t in store.data.get("removed", []) if t})


def write_removed(store, folder):
    """Every deployment carries the removal list; sample pages read it from the newest one and hide themselves."""
    tokens = removed_list(store)
    (folder / "removed.json").write_text(json.dumps(tokens))
    return len(tokens)


def publish_removals(cfg, store, folder):
    """When someone asked for their page to come down since the last deployment, publish the new list right away
    (a tiny deployment with nothing else in it). Returns True if it published."""
    count = len(removed_list(store))
    if count == int(store.flag("removed_published") or 0) or not configured(cfg):
        return False
    from . import packs
    shutil.rmtree(folder, ignore_errors=True)
    packs.site_root(folder)
    write_removed(store, folder)
    dep = deploy(cfg, folder)
    if not dep:
        return False
    remember(store, dict(dep, removed=count), "removals")
    return True


def cleanup(cfg, store, days):
    """Delete deployments older than `days` (their samples expire with them). Returns how many were deleted."""
    if not configured(cfg):
        return 0
    project = cfg["pages"]["cloudflare_project"]
    keep, deleted = [], 0
    for dep in store.data.get("deployments", []):
        old = parse(dep["at"]) and (now() - parse(dep["at"])).days >= days
        if old and dep.get("id"):
            try:
                r = _api(cfg, "DELETE", f"/pages/projects/{project}/deployments/{dep['id']}", params={"force": "true"})
                if r.status_code in (200, 404):
                    deleted += 1
                    continue
            except requests.RequestException:
                pass
        if not (old and not dep.get("id")):
            keep.append(dep)
    store.data["deployments"] = keep
    return deleted
