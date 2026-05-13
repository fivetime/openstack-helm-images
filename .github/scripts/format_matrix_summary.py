#!/usr/bin/env python3
"""Render a matrix JSON dump as a Markdown table for $GITHUB_STEP_SUMMARY.

Used by .github/workflows/build-all-images.yml so the embedded summary
generation doesn't need an inline ``python -c`` heredoc -- those collide
with YAML block-scalar indentation and produce IndentationError at runtime.
"""

from __future__ import annotations

import argparse
import json
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("json_path")
    ap.add_argument("--title", required=True)
    args = ap.parse_args()

    with open(args.json_path) as f:
        rows = json.load(f)

    print(f"### {args.title}")
    if not rows:
        print()
        print("_(no entries)_")
        print()
        return 0

    print("| Image | Release | Tag | Platforms |")
    print("|---|---|---|---|")
    for r in rows:
        svc = (
            r["job"]
            .replace("openstack-helm-images-build-", "")
            .replace("build-local-", "")
        )
        tag = r["primary_tag"].rsplit(":", 1)[-1]
        print(f"| {svc} | {r['release']} | `{tag}` | {r['platforms']} |")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
