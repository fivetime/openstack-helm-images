# syntax=docker/dockerfile:1
# Fork-only: kolla horizon + the dashboard plugins kolla leaves out.
# The kolla 2026.1 horizon image bundles most dashboard plugins but not
# zun-ui, barbican-ui, freezer-web-ui or zaqar-ui; the airshipit (loci)
# horizon image bundles none at all. Add the missing plugins on top of the
# kolla base so conf.horizon.extra_panels can enable them (the chart start
# script symlinks enabled/ files and runs collectstatic+compress at startup,
# so no other build step is needed).
# zun-ui comes from the fivetime fork, which carries the $gray-lighter
# SCSS fix (compress aborts on it -> dashboard crash-loop) and the
# absolute-path validation on the mounts form.
#
# NOTE: upper-constraints pins no horizon plugin at all -- not zun-ui, not
# octavia-dashboard, not the three added here -- so these are pinned by hand.
# Bump them together with RELEASE. Their clients (python-freezerclient,
# python-zaqarclient, python-barbicanclient) ARE in constraints and are left
# to resolve from there.
ARG BASE=quay.io/openstack.kolla/horizon:2026.1-ubuntu-noble
FROM ${BASE}

ARG RELEASE=2026.1
ARG ZUN_UI_REPO=https://github.com/fivetime/openstack-zun-ui
ARG ZUN_UI_REF=master
# zunclient carries the CREATION_ATTRIBUTES whitelist zun-ui filters through;
# the flavor limit fields exist only in the fork.
ARG ZUNCLIENT_REPO=https://github.com/fivetime/openstack-zunclient
ARG ZUNCLIENT_REF=master

# barbican-ui is never published to PyPI and its master carries no release
# tags (pbr reports it as 0.0.1.devN), so it is pinned by commit. A SHA in
# the RUN line is its own cache key, so it needs no ADD cache-buster the way
# the moving branches above do.
# Deliberately NOT named *_REPO: generate_pydep.py treats every
# "ARG <X>_REPO=https://{opendev,github}.com/openstack/<proj>" as a backing
# service repo and fetches requirements.txt from its stable/<release> branch.
# barbican-ui has only master, so that lookup 404s and, being the sole match,
# fails the whole build. horizon-kolla has no business in that scan anyway --
# it consumes no pydep.txt and needs neither psycopg2 nor confluent-kafka.
ARG BARBICAN_UI_GIT=https://opendev.org/openstack/barbican-ui
ARG BARBICAN_UI_REF=f962e455b529580c2bb0e924a6fd39185a77ec16
# These two are on PyPI; 18.0.0 and 20.0.0 are the 2026.1 releases.
ARG FREEZER_WEB_UI_VERSION=18.0.0
ARG ZAQAR_UI_VERSION=20.0.0

# raas-ui: the RaaS (Runner-as-a-Service) Horizon panel, fivetime-only and
# in a PRIVATE repository. Pinned by commit rather than branch: the ADD
# refs-API cache-buster used above returns 404 anonymously for a private
# repo, and a branch name in a RUN line is an unchanging cache key -- the
# build would keep serving stale code without a word. RAAS_UI_REF is in
# PINNED_BUILD_ARGS so this default and the build-local.d pin cannot drift.
# Same *_GIT (not *_REPO) naming as barbican-ui, for the same
# generate_pydep.py reason.
ARG RAAS_UI_GIT=https://github.com/fivetime/openstack-raas-ui
ARG RAAS_UI_REF=96c1ebe24b19283dbc63ed2fe250e0afe5778c66

# A pip install from a moving branch is one unchanging RUN line, so the
# layer is reused and the branch's new commits never arrive -- an image
# that looks rebuilt and is not. Fetching the ref itself first makes the
# layer depend on where the branch points.
ADD https://api.github.com/repos/fivetime/openstack-zun-ui/git/refs/heads/master /tmp/zun-ui.ref
ADD https://api.github.com/repos/fivetime/openstack-zunclient/git/refs/heads/master /tmp/zunclient.ref

USER root
RUN curl -fsSL "https://releases.openstack.org/constraints/upper/${RELEASE}" \
        -o /tmp/uc.txt \
    && sed -i -e '/^zun-ui===/d' -e '/^python-zunclient===/d' /tmp/uc.txt \
    && /var/lib/kolla/venv/bin/pip install --no-cache-dir \
        -c /tmp/uc.txt \
        "git+${ZUNCLIENT_REPO}@${ZUNCLIENT_REF}#egg=python-zunclient" \
        "git+${ZUN_UI_REPO}@${ZUN_UI_REF}#egg=zun-ui" \
        "git+${BARBICAN_UI_GIT}@${BARBICAN_UI_REF}#egg=barbican-ui" \
        "freezer-web-ui==${FREEZER_WEB_UI_VERSION}" \
        "zaqar-ui==${ZAQAR_UI_VERSION}" \
    && /var/lib/kolla/venv/bin/pip show zun-ui python-zunclient \
        barbican-ui freezer-web-ui zaqar-ui | grep -E "Name|Version" \
    && /var/lib/kolla/venv/bin/pip check \
    && rm -f /tmp/uc.txt \
    # guard: the fork must have fixed this, or compress dies at pod start
    && ! grep -rq '\$gray-lighter' /var/lib/kolla/venv/lib/python3*/site-packages/zun_ui/static \
    # guard: extra_panels matches on the *module* directory, which differs
    # from the pip name for every one of these (freezer-web-ui -> freezer_ui).
    # A plugin whose enabled/ files are missing is skipped in silence at pod
    # start, so fail the build here instead.
    && for m in zun_ui barbican_ui freezer_ui zaqar_ui; do \
         ls /var/lib/kolla/venv/lib/python3*/site-packages/$m/enabled/_[1-9]*.py \
           >/dev/null || exit 1; \
       done

# raas-ui goes in its own layer with the secret mount, kept apart from the
# public plugins above so a token rotation or raas-ui bump does not
# invalidate their (slow, constraint-resolving) layer. CI supplies
# src_repo_token (from CR_PAT); the token and the git url rewrite live only
# inside this RUN and reach no image layer. With the secret absent (local
# build, or the repo made public) it falls through to an anonymous clone.
COPY check-raas-ui-enabled.py /tmp/check-raas-ui-enabled.py
RUN --mount=type=secret,id=src_repo_token \
    if ! command -v git >/dev/null; then \
        apt-get update && apt-get install -y --no-install-recommends git \
        && rm -rf /var/lib/apt/lists/*; \
    fi \
    && if [ -s /run/secrets/src_repo_token ]; then \
        TOK="$(cat /run/secrets/src_repo_token)"; \
        git config --global \
          url."https://x-access-token:${TOK}@github.com/".insteadOf "https://github.com/"; \
    fi \
    && PBR_VERSION=0.1.0 /var/lib/kolla/venv/bin/pip install --no-cache-dir \
        "raas-ui @ git+${RAAS_UI_GIT}@${RAAS_UI_REF}" \
    && rm -f /root/.gitconfig \
    && /var/lib/kolla/venv/bin/pip show raas-ui | grep -E "Name|Version" \
    # same silent-skip guard as the four above: extra_panels needs enabled/
    && ls /var/lib/kolla/venv/lib/python3*/site-packages/raas_ui/enabled/_[1-9]*.py >/dev/null \
    # and the plugin must at least compile and its enabled/ modules import.
    # A *full* import (panel, api) is deliberately NOT attempted at build
    # time: it drags in openstack_dashboard.api -> openstack_auth -> Django
    # auth models, which need django.setup(), which then needs Horizon's
    # configured DB backend (MySQLdb here). That is a runtime dependency; no
    # image build can satisfy it, and two CI rounds proved it. The enabled/
    # files are plain Python with no Horizon import, so they are checkable;
    # whether the panel actually renders was verified against a live Horizon.
    && /var/lib/kolla/venv/bin/python3 -m compileall -q \
         /var/lib/kolla/venv/lib/python3*/site-packages/raas_ui \
    && /var/lib/kolla/venv/bin/python3 -c "import raas_ui.enabled._2810_project_ci_panel_group, raas_ui.enabled._2820_project_runners_panel" \
    && python3 /tmp/check-raas-ui-enabled.py \
    && rm -f /tmp/check-raas-ui-enabled.py
USER horizon
