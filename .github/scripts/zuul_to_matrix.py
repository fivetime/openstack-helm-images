#!/usr/bin/env python3
"""Generate a GitHub Actions build matrix from zuul.d/ and build-local.d/.

The data source is the ``container_images`` Ansible variable on each Zuul
build job. Upstream openstack-helm-images defines those for every official
image; this fork drops additional entries (fork-only Dockerfile variants,
new images not in upstream) into ``build-local.d/`` using the same schema,
so adding a new image is a one-file change and the workflow never has to
be touched.

Job filter: only jobs whose name starts with ``openstack-helm-images-build-``
(upstream) or ``build-local-`` (fork) are considered, so the same vars
shared via YAML anchors with ``-upload-`` / ``-promote-`` jobs do not get
counted three times.

Output: one matrix entry per ``container_images`` element, post-filtering,
plus optional synthesized master variants derived from each 2026.1 entry.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml


# Zuul files use custom YAML tags like `!encrypted/pkcs1-oaep` for secrets.
# We don't care about those values for build matrix generation; register a
# fallback constructor so PyYAML returns them as plain Python objects instead
# of failing on the unknown tag.
def _passthrough(loader, tag_suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


yaml.SafeLoader.add_multi_constructor("!", _passthrough)


TEMPLATED_TAG_RE = re.compile(r"\{\{")
BUILD_JOB_NAME_RE = re.compile(r"(^openstack-helm-images-build-|^build-local-)")
RELEASE_PREFIX_RE = re.compile(r"^(\d{4}\.\d+)\b")

# Foundation jobs build the layers everything else FROM s. They must build
# before any service-tier cell. Names taken from upstream zuul.d/.
FOUNDATION_JOB_SUFFIXES = ("-build-base", "-build-venv-builder")


def load_jobs(paths: list[Path]) -> list[dict]:
    out: list[dict] = []
    for p in paths:
        with p.open(encoding="utf-8") as f:
            docs = yaml.safe_load(f) or []
        for item in docs:
            if isinstance(item, dict) and "job" in item:
                out.append(item["job"])
    return out


def select_build_jobs(jobs: list[dict]) -> list[dict]:
    result: list[dict] = []
    seen: set[str] = set()
    for j in jobs:
        name = j.get("name", "")
        if not BUILD_JOB_NAME_RE.search(name):
            continue
        # Abstract jobs are templates used as parents (e.g. ceph-common is
        # the base for ceph-config-helper / ceph-daemon / ceph-utility) and
        # carry incomplete container_images entries that lack 'repository'.
        # Skip them silently; the concrete child jobs will be processed.
        if j.get("abstract") is True:
            continue
        if name in seen:
            continue
        seen.add(name)
        if "container_images" in j.get("vars", {}):
            result.append(j)
    return result


def remap_repository(repo: str, owner: str) -> str:
    if repo.startswith("quay.io/airshipit/"):
        return f"ghcr.io/{owner}/openstackhelm/{repo[len('quay.io/airshipit/'):]}"
    if repo.startswith(("ghcr.io/", "quay.io/", "docker.io/")):
        return repo
    if "/" in repo:
        return f"ghcr.io/{owner}/{repo}"
    return f"ghcr.io/{owner}/openstackhelm/{repo}"


def extract_release(tags: list[str]) -> str:
    """Classify the release a container_images entry belongs to.

    Some upstream entries declare multiple tags for the same image (e.g.
    libvirt declares ``epoxy-ubuntu_noble`` and ``2025.1-ubuntu_noble`` on
    the same row). Prefer the OpenStack-numbered form so the image is
    correctly classified to its release; only fall back to ``master`` or
    ``rolling`` when no tag carries a release number.
    """
    for tag in tags:
        m = RELEASE_PREFIX_RE.match(tag)
        if m:
            return m.group(1)
    for tag in tags:
        if tag.startswith("master"):
            return "master"
    return "rolling"


def render_image(img: dict, owner: str, job_name: str = "") -> dict | None:
    raw_tags = [t for t in img.get("tags", []) if not TEMPLATED_TAG_RE.search(t)]
    if not raw_tags:
        return None
    if "repository" not in img:
        sys.stderr.write(
            f"WARN: skipping container_images entry without 'repository' "
            f"in job '{job_name}': {img}\n"
        )
        return None
    repo = remap_repository(img["repository"], owner)
    full_tags = [f"{repo}:{t}" for t in raw_tags]
    arches = img.get("arch", ["linux/amd64"])
    return {
        "context": img.get("context", "."),
        "container_filename": img.get(
            "container_filename", img.get("dockerfile", "Dockerfile")
        ),
        "platforms": ",".join(arches),
        "tags_cli": " ".join(f"--tag {t}" for t in full_tags),
        "build_args_cli": " ".join(
            f"--build-arg {a}" for a in img.get("build_args", [])
        ),
        "primary_tag": full_tags[0],
        "release": extract_release(raw_tags),
        "repository": repo,
    }


def synthesize_master(row: dict, owner: str) -> dict | None:
    """Return a master-tagged sibling of a 2026.1 row, or None.

    Upstream Airship does not publish quay.io/airshipit/{base,venv_builder}
    at the master tag. To produce truly self-contained master images we:

    1. Build our own ``base`` and ``venv_builder`` at the master tag by
       synthesizing them from their 2026.1 entries (no special handling
       needed -- the foundation Dockerfiles FROM raw ubuntu, so the
       synthesis just rewrites the output tag).
    2. For every service-tier master row, rewrite the ``BASE_VENV_BUILDER``
       and ``BASE_RUNTIME`` build args to point at our newly-built
       ``ghcr.io/<owner>/openstackhelm/{base,venv_builder}:master-ubuntu_noble``
       images, not quay.io/airshipit. This means master service builds
       depend on the foundation tier completing first (enforced by the
       workflow ``needs:`` chain), but it makes the master image set
       genuinely independent of upstream Periodic.
    """
    if row["release"] != "2026.1":
        return None

    # Synthesize only the 2026.1-bearing tags (rewritten to master). Tags
    # that are pure release codenames (e.g. libvirt's "gazpacho-ubuntu_noble")
    # belong to the 2026.1 build only -- if we let them ride along into the
    # master row, both the 2026.1 cell and the master cell would push to the
    # same "gazpacho-ubuntu_noble" tag and whichever runs second wins.
    old_full_tags = row["tags_cli"].replace("--tag ", "").split()
    new_full_tags = [
        t.replace("2026.1", "master") for t in old_full_tags if "2026.1" in t
    ]
    if not new_full_tags:
        return None

    new_row = dict(row)
    new_row["tags_cli"] = " ".join(f"--tag {t}" for t in new_full_tags)
    new_row["primary_tag"] = new_full_tags[0]
    new_row["release"] = "master"

    new_args = row["build_args_cli"].replace("stable/2026.1", "master")
    if row.get("tier") != "foundation":
        # Service-tier master rows: FROM our self-built foundation.
        new_args = new_args.replace(
            "quay.io/airshipit/venv_builder:2026.1-ubuntu_noble",
            f"ghcr.io/{owner}/openstackhelm/venv_builder:master-ubuntu_noble",
        )
        new_args = new_args.replace(
            "quay.io/airshipit/base:2026.1-ubuntu_noble",
            f"ghcr.io/{owner}/openstackhelm/base:master-ubuntu_noble",
        )
    new_row["build_args_cli"] = new_args
    return new_row


def classify_tier(job_name: str) -> str:
    if any(job_name.endswith(suf) for suf in FOUNDATION_JOB_SUFFIXES):
        return "foundation"
    return "service"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", required=True)
    ap.add_argument("--zuul-dir", default="zuul.d")
    ap.add_argument("--local-dir", default="build-local.d")
    ap.add_argument(
        "--releases", default="",
        help="Comma-separated release filter (e.g. '2026.1,master'). Empty = all.",
    )
    ap.add_argument(
        "--platforms", default="",
        help="Comma-separated platform filter (e.g. 'linux/amd64'). Empty = all.",
    )
    ap.add_argument(
        "--services", default="",
        help="Comma-separated job-name substring filter. Empty = all.",
    )
    ap.add_argument(
        "--include-master", action="store_true",
        help="Synthesize master variants from 2026.1 build entries.",
    )
    ap.add_argument(
        "--tier", default="",
        help="Comma-separated tier filter ('foundation' or 'service'). Empty = all.",
    )
    ap.add_argument(
        "--format", choices=["json", "github"], default="json",
        help="json = pretty-printed list, github = matrix=... line for $GITHUB_OUTPUT",
    )
    args = ap.parse_args()

    yaml_paths: list[Path] = []
    for d in (args.zuul_dir, args.local_dir):
        p = Path(d)
        if p.is_dir():
            yaml_paths.extend(sorted(p.glob("*.yaml")))
            yaml_paths.extend(sorted(p.glob("*.yml")))

    jobs = load_jobs(yaml_paths)

    service_filter = {s for s in args.services.split(",") if s}
    if service_filter:
        jobs = [
            j for j in jobs
            if any(s in j.get("name", "") for s in service_filter)
        ]

    build_jobs = select_build_jobs(jobs)

    release_filter = {r for r in args.releases.split(",") if r}
    platform_filter = {p for p in args.platforms.split(",") if p}

    rows: list[dict] = []
    for j in build_jobs:
        tier = classify_tier(j["name"])
        for img in j["vars"]["container_images"]:
            row = render_image(img, args.owner, j.get("name", ""))
            if row is None:
                continue
            row["job"] = j["name"]
            row["tier"] = tier
            rows.append(row)
            if args.include_master:
                m = synthesize_master(row, args.owner)
                if m is not None:
                    m["job"] = j["name"]
                    m["tier"] = tier
                    rows.append(m)

    if release_filter:
        rows = [r for r in rows if r["release"] in release_filter]

    tier_filter = {t for t in args.tier.split(",") if t}
    if tier_filter:
        rows = [r for r in rows if r["tier"] in tier_filter]

    if platform_filter:
        kept = []
        for r in rows:
            archs = [a for a in r["platforms"].split(",") if a in platform_filter]
            if not archs:
                continue
            r2 = dict(r)
            r2["platforms"] = ",".join(archs)
            kept.append(r2)
        rows = kept

    if args.format == "github":
        sys.stdout.write(f"matrix={json.dumps({'include': rows})}\n")
    else:
        json.dump(rows, sys.stdout, indent=2)
        sys.stdout.write("\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
