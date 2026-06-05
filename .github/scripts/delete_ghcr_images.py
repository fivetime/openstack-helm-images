#!/usr/bin/env python3
"""Delete GHCR container images under a namespace prefix for a GitHub user.

Manual cleanup tool: wipes ``ghcr.io/<OWNER>/<NAMESPACE_PREFIX>*`` so the next
daily build republishes fresh images and stale tags can't silently linger and
hide problems.

GHCR stores each container image as a "package" of type=container, so this
talks to the GitHub *packages* API even though we think of them as images;
PACKAGE_TYPE/package terms below are the literal API vocabulary.

Everything is driven by env vars; the calling workflow injects the token from
a repo secret. NEVER hard-code a token here.

  GH_TOKEN          (required) token with `read:packages` + `delete:packages`
                    (and `repo` for private images). The workflow passes
                    secrets.CR_PAT.
  OWNER             default 'fivetime'
  PACKAGE_TYPE      default 'container'
  NAMESPACE_PREFIX  default 'openstackhelm/' -- ONLY images whose name starts
                    with this are ever touched; everything else is listed and
                    left alone.
  DRY_RUN           '1'/'true' (default) = list only; '0'/'false' = delete
  CONFIRM           must equal 'DELETE' when DRY_RUN is false, else abort

Deletes the whole image (package) in one call, which removes all its versions
(tags). Exits non-zero on a hard error or if any deletion failed.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"
API_VERSION = "2022-11-28"


def env_bool(name, default):
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _request(method, url, token, accept="application/vnd.github+json"):
    r = urllib.request.Request(url, method=method)
    r.add_header("Authorization", f"Bearer {token}")
    r.add_header("Accept", accept)
    r.add_header("X-GitHub-Api-Version", API_VERSION)
    return urllib.request.urlopen(r)


def list_packages(token, ptype):
    """All container packages for the *authenticated* user (incl. private)."""
    pkgs = []
    page = 1
    while True:
        url = (f"{API}/user/packages?package_type={ptype}"
               f"&per_page=100&page={page}")
        try:
            with _request("GET", url, token) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            sys.exit(f"ERROR listing packages (HTTP {e.code}): {body}\n"
                     f"(token needs read:packages scope)")
        if not data:
            break
        pkgs.extend(data)
        if len(data) < 100:
            break
        page += 1
    return pkgs


def delete_package(token, ptype, name):
    """DELETE the whole package (all versions). Returns HTTP status."""
    enc = urllib.parse.quote(name, safe="")  # encode the '/' in e.g. foo/bar
    url = f"{API}/user/packages/{ptype}/{enc}"
    for attempt in range(5):
        try:
            with _request("DELETE", url, token) as resp:
                return resp.status
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return 404  # already gone -- treat as success
            if e.code in (429, 502, 503) and attempt < 4:
                time.sleep(2 ** attempt)
                continue
            body = e.read().decode(errors="replace")
            raise RuntimeError(f"HTTP {e.code}: {body}")
    return -1


def main():
    token = os.environ.get("GH_TOKEN")
    if not token:
        sys.exit("ERROR: GH_TOKEN not set "
                 "(the workflow injects it from secrets.CR_PAT).")

    ptype = os.environ.get("PACKAGE_TYPE", "container")
    prefix = os.environ.get("NAMESPACE_PREFIX", "openstackhelm/")
    dry = env_bool("DRY_RUN", True)
    confirm = os.environ.get("CONFIRM", "")

    print(f"package_type={ptype}  prefix='{prefix}'  dry_run={dry}")

    all_pkgs = list_packages(token, ptype)
    targets = sorted(p["name"] for p in all_pkgs
                     if p["name"].startswith(prefix))
    others = sorted(p["name"] for p in all_pkgs
                    if not p["name"].startswith(prefix))

    print(f"\nTotal {ptype} images found: {len(all_pkgs)}")
    print(f"Matching prefix '{prefix}': {len(targets)}")
    for n in targets:
        print(f"  [TARGET] {n}")
    if others:
        print(f"Not matching (left untouched): {len(others)}")
        for n in others:
            print(f"  [keep]   {n}")

    if not targets:
        print("\nNothing to delete.")
        return

    if dry:
        print("\nDRY RUN -- no deletions performed.\n"
              "Re-run with dry_run=false AND confirm=DELETE to actually delete.")
        return

    if confirm != "DELETE":
        sys.exit("\nABORT: dry_run=false but confirm != 'DELETE'. "
                 "Refusing to delete without explicit confirmation.")

    print(f"\nDeleting {len(targets)} image(s)...")
    failed = []
    for n in targets:
        try:
            status = delete_package(token, ptype, n)
            print(f"  deleted {n} -> HTTP {status}")
        except Exception as e:  # noqa: BLE001 -- report and keep going
            print(f"  FAILED  {n} -> {e}")
            failed.append(n)
        time.sleep(0.3)  # be gentle with the API

    ok = len(targets) - len(failed)
    print(f"\nDone. deleted={ok} failed={len(failed)}")
    if failed:
        print("Failed images:")
        for n in failed:
            print(f"  {n}")
        sys.exit(1)


if __name__ == "__main__":
    main()
