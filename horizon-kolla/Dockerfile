# syntax=docker/dockerfile:1
# Fork-only: kolla horizon + zun-ui.
# The kolla 2026.1 horizon image bundles most dashboard plugins but not
# zun-ui; the airshipit (loci) horizon image bundles none at all. Add the
# missing plugin on top of the kolla base so conf.horizon.extra_panels can
# enable it (the chart start script symlinks enabled/ files and runs
# collectstatic+compress at startup, so no other build step is needed).
# zun-ui comes from the fivetime fork, which carries the $gray-lighter
# SCSS fix (compress aborts on it -> dashboard crash-loop) and the
# absolute-path validation on the mounts form.
ARG BASE=quay.io/openstack.kolla/horizon:2026.1-ubuntu-noble
FROM ${BASE}

ARG RELEASE=2026.1
ARG ZUN_UI_REPO=https://github.com/fivetime/openstack-zun-ui
ARG ZUN_UI_REF=master
# zunclient carries the CREATION_ATTRIBUTES whitelist zun-ui filters through;
# the flavor limit fields exist only in the fork.
ARG ZUNCLIENT_REPO=https://github.com/fivetime/openstack-zunclient
ARG ZUNCLIENT_REF=master

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
    && /var/lib/kolla/venv/bin/pip show zun-ui python-zunclient | grep -E "Name|Version" \
    && rm -f /tmp/uc.txt \
    # guard: the fork must have fixed this, or compress dies at pod start
    && ! grep -rq '\$gray-lighter' /var/lib/kolla/venv/lib/python3*/site-packages/zun_ui/static
USER horizon
