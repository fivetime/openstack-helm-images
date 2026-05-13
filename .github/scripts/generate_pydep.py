#!/usr/bin/env python3
"""Augment upstream pydep.txt with PostgreSQL + Kafka driver entries.

Each OpenStack service that uses oslo.db / SQLAlchemy needs psycopg2-binary
to talk to PostgreSQL (alongside the bundled MySQL driver), and each service
using oslo.messaging needs confluent-kafka for the Kafka driver. Rather
than maintaining a hand-edited list, this generator scans each service's
upstream requirements.txt at the active release ref and emits a single
augmented pydep.txt that downstream Dockerfiles consume verbatim.

Workflow integration: run before docker build. The generated file is
written to ``--output`` (typically ``pydep.txt`` in the build context,
overlaying the checked-in upstream copy).

Failure mode: fail-fast. If any service's requirements.txt cannot be
fetched, the script exits non-zero and the build fails. The expectation
is that the daily cron retries the next day; if opendev.org is unreachable
long enough to matter, the wider OpenStack ecosystem is already broken
and a single fork's image build is the smallest concern.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Top-level dirs that do NOT correspond to OpenStack service projects.
# We skip these when auto-discovering services.
SKIP_DIRS = {
    "base",
    "venv_builder",
    "libvirt",
    "fluentd",
    "nagios",
    "mariadb",
    "node-problem-detector",
    "prometheus-webhook-snmp",
    "ceph-config-helper",
    "ceph-daemon",
    "ceph-osd",
    "ceph-utility",
    "tempest",  # tempest is a test runner, not a deploy target needing PG/Kafka
}

# Extra dirs that have Dockerfile but are fork-only or non-Python:
SKIP_DIRS_FORK = {
    "ovn",
    "openvswitch",
    "ovn-bgp-agent",
    "percona-timescaledb",
}

ARG_REPO_RE = re.compile(
    r"^ARG\s+(\w+)_REPO\s*=\s*(https?://(?:opendev\.org|github\.com)/openstack/\S+)",
    re.MULTILINE,
)

OSLO_DB_RE = re.compile(r"^(SQLAlchemy|oslo\.db)\b", re.MULTILINE | re.IGNORECASE)
OSLO_MESSAGING_RE = re.compile(r"^oslo\.messaging\b", re.MULTILINE | re.IGNORECASE)


def discover_services(repo_root: Path) -> list[tuple[str, list[str]]]:
    """Return (service_dir, [repo_url, ...]) tuples.

    Auto-discovers each top-level dir with a Dockerfile, skipping foundation
    images and non-OpenStack components. For each candidate, collects every
    ``ARG <PREFIX>_REPO=https://(opendev|github)/openstack/<proj>`` entry --
    a service may depend on multiple OpenStack projects (e.g. skyline
    composes skyline-apiserver + skyline-console; nova references nova,
    novnc, spice).
    """
    services: list[tuple[str, list[str]]] = []
    for child in sorted(repo_root.iterdir()):
        if not child.is_dir():
            continue
        if child.name in SKIP_DIRS or child.name in SKIP_DIRS_FORK:
            continue
        dockerfile = child / "Dockerfile"
        if not dockerfile.is_file():
            continue
        content = dockerfile.read_text(encoding="utf-8", errors="replace")
        repos: list[str] = []
        for m in ARG_REPO_RE.finditer(content):
            url = m.group(2).rstrip("/").removesuffix(".git")
            # Normalise github.com -> opendev.org for raw fetch (canonical)
            url = url.replace("github.com/openstack/", "opendev.org/openstack/")
            if url not in repos:
                repos.append(url)
        if not repos:
            sys.stderr.write(
                f"skip {child.name}: no OpenStack _REPO ARG found\n"
            )
            continue
        services.append((child.name, repos))
    return services


def fetch_requirements(repo_url: str, ref: str, timeout: int = 30) -> str:
    url = f"{repo_url}/raw/branch/{ref}/requirements.txt"
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def scan_service(
    service: str, repos: list[str], ref: str
) -> tuple[str, bool, bool]:
    """Scan every backing OpenStack project for oslo.db / oslo.messaging.

    A service is flagged as needing the driver if ANY of its backing
    projects pulls in the corresponding oslo lib. Missing requirements.txt
    on a sub-project (e.g. skyline-console is JS-only) is not fatal --
    that project simply contributes nothing to the union.
    """
    needs_pg = False
    needs_kafka = False
    fetched_any = False
    last_error: Exception | None = None
    for repo_url in repos:
        try:
            content = fetch_requirements(repo_url, ref)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                # Sub-project may not have requirements.txt (e.g. JS-only)
                last_error = e
                continue
            raise
        fetched_any = True
        if OSLO_DB_RE.search(content):
            needs_pg = True
        if OSLO_MESSAGING_RE.search(content):
            needs_kafka = True
    if not fetched_any:
        # Every backing repo 404'd -- treat as fatal so the build fails
        # rather than silently producing an incomplete pydep.txt.
        raise RuntimeError(
            f"{service}: no requirements.txt found in any backing repo "
            f"({repos}) -- last error: {last_error}"
        )
    return service, needs_pg, needs_kafka


def emit_pydep(
    base_pydep: str,
    pg_services: list[str],
    kafka_services: list[str],
    release: str,
) -> str:
    out = base_pydep.rstrip() + "\n\n"
    out += (
        f"# === Auto-generated fork extension (generate_pydep.py) ===\n"
        f"# Driver packages derived from requirements.txt scan against {release}.\n"
        f"# Do not hand-edit -- regenerated each build from upstream service repos.\n"
    )
    if pg_services:
        out += (
            "psycopg2-binary  ["
            + " ".join(sorted(pg_services))
            + "]\n"
        )
    if kafka_services:
        out += (
            "confluent-kafka  ["
            + " ".join(sorted(kafka_services))
            + "]\n"
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    ap.add_argument("--base", type=Path, default=Path("pydep.txt"),
                    help="Path to upstream pydep.txt to augment")
    ap.add_argument("--release", required=True,
                    help="Git ref to fetch requirements.txt against "
                         "(e.g. 'stable/2026.1' or 'master')")
    ap.add_argument("--output", type=Path, required=True,
                    help="Where to write the augmented pydep.txt")
    ap.add_argument("--max-workers", type=int, default=8)
    args = ap.parse_args()

    base_pydep = args.base.read_text(encoding="utf-8")
    services = discover_services(args.repo_root)
    if not services:
        sys.stderr.write("error: no services discovered\n")
        return 1

    print(f"Discovered {len(services)} services to scan against {args.release}",
          file=sys.stderr)

    pg_services: list[str] = []
    kafka_services: list[str] = []
    failures: list[tuple[str, Exception]] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as ex:
        futures = {
            ex.submit(scan_service, svc, repos, args.release): svc
            for svc, repos in services
        }
        for fut in concurrent.futures.as_completed(futures):
            svc = futures[fut]
            try:
                _, needs_pg, needs_kafka = fut.result()
            except Exception as e:
                failures.append((svc, e))
                continue
            if needs_pg:
                pg_services.append(svc)
            if needs_kafka:
                kafka_services.append(svc)
            print(
                f"  {svc:30s} pg={'Y' if needs_pg else '.'} "
                f"kafka={'Y' if needs_kafka else '.'}",
                file=sys.stderr,
            )

    if failures:
        sys.stderr.write("\nERROR: failed to fetch requirements.txt for:\n")
        for svc, e in failures:
            sys.stderr.write(f"  {svc}: {e}\n")
        sys.stderr.write(
            "\nThis is likely a transient opendev.org issue. The next daily\n"
            "cron will retry; no fallback list is maintained on purpose so\n"
            "that the build either reflects current upstream reality or\n"
            "fails visibly.\n"
        )
        return 1

    augmented = emit_pydep(base_pydep, pg_services, kafka_services, args.release)
    args.output.write_text(augmented, encoding="utf-8")
    print(
        f"\nWrote {args.output} ({len(pg_services)} pg, "
        f"{len(kafka_services)} kafka)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
