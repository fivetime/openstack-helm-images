# syntax=docker/dockerfile:1
ARG BASE_VENV_BUILDER=quay.io/airshipit/venv_builder:2026.2-ubuntu_resolute
ARG BASE_RUNTIME=quay.io/airshipit/base:2026.2-ubuntu_resolute
FROM ${BASE_VENV_BUILDER} AS build

ENV PATH=/var/lib/openstack/bin:$PATH

# Karbor is retired upstream (opendev's master holds only a README and there
# is no stable/2026.2); the fork carries it forward. Keep the default on the
# fork: generate_pydep.py would otherwise fetch the requirements of the
# retired opendev repository for the release branch, get a 404 and fail the
# whole build. karbor's driver packages are listed in pydep.txt by hand.
ARG KARBOR_REPO=https://github.com/fivetime/openstack-karbor
# A release tag (or a commit). The repositories are private, so the ref
# cannot be watched through the API the way public forks are; naming it
# makes the build reproducible and invalidates the layer by itself.
ARG KARBOR_REF=2.0.0
# karbor-operationengine calls the karbor API through python-karborclient,
# also retired: the release on PyPI (2.1.0) breaks with the PrettyTable of
# 2026.2 and upper-constraints no longer lists it. Install the fork's.
ARG KARBORCLIENT_REPO=https://github.com/fivetime/python-karborclient
ARG KARBORCLIENT_REF=3.0.0
ARG PROFILES="fluent"

# Use bindep to determine packages needed for this profile set
COPY bindep.txt pydep.txt /opt/
RUN mkdir -p /etc/image_info && \
    uvx bindep -f /opt/bindep.txt -b -l newline karbor ${PROFILES} > /etc/image_info/bindep_runtime.txt && \
    uvx bindep -f /opt/bindep.txt -b -l newline karbor build ${PROFILES} > /etc/image_info/bindep_build.txt && \
    uvx bindep -f /opt/pydep.txt -b -l newline karbor ${PROFILES} > /etc/image_info/python_packages.txt

RUN if [ -s /etc/image_info/bindep_build.txt ]; then \
        apt-get update \
        && DEBIAN_FRONTEND=noninteractive xargs --no-run-if-empty apt-get install -y --no-install-recommends < /etc/image_info/bindep_build.txt \
        && rm -rf /var/lib/apt/lists/*; \
    fi

# CI supplies src_repo_token as a BuildKit secret; the token and the
# temporary git rewrite live only inside this RUN and never reach an image
# layer. A full (blobless) clone, not a single commit: pbr computes the
# version from the tags.
RUN --mount=type=secret,id=src_repo_token \
    if [ -s /run/secrets/src_repo_token ]; then \
        token="$(cat /run/secrets/src_repo_token)"; \
        git config --global \
          url."https://x-access-token:${token}@github.com/".insteadOf \
          "https://github.com/"; \
    fi \
    && git clone --filter=blob:none ${KARBOR_REPO} /tmp/karbor \
    && git clone --filter=blob:none ${KARBORCLIENT_REPO} /tmp/karborclient \
    # Still authenticated: a blobless checkout fetches the blobs it needs.
    && git -C /tmp/karbor checkout --detach ${KARBOR_REF} \
    && git -C /tmp/karborclient checkout --detach ${KARBORCLIENT_REF} \
    && rm -f /root/.gitconfig \
    && sed -i '/^karbor===/d; /^python-karborclient===/d' /upper-constraints.txt \
    && uv pip install \
         --build-constraint /upper-constraints.txt \
         -c /upper-constraints.txt \
         -r /etc/image_info/python_packages.txt \
         /tmp/karbor /tmp/karborclient \
    && { git -C /tmp/karbor log --oneline -1; \
         git -C /tmp/karborclient log --oneline -1; } > /etc/image_info/project.txt \
    && rm -rf /tmp/karbor /tmp/karborclient \
    && uv pip freeze > /etc/image_info/pip.txt

FROM ${BASE_RUNTIME} AS runtime

ENV PATH=/var/lib/openstack/bin:$PATH


COPY --from=build --link /var/lib/openstack /var/lib/openstack
COPY --from=build /etc/image_info /etc/image_info
COPY --from=build /upper-constraints.txt /

# Install packages determined by bindep in build stage
RUN if [ -s /etc/image_info/bindep_runtime.txt ]; then \
        apt-get update \
        && DEBIAN_FRONTEND=noninteractive xargs --no-run-if-empty apt-get install -y --no-install-recommends < /etc/image_info/bindep_runtime.txt \
        && rm -rf /var/lib/apt/lists/*; \
    fi

RUN find /var/lib/openstack \( -name "*.pyc" -o -name "__pycache__" \) -delete \
    && rm -rf /tmp/* /root/.cache /etc/machine-id

# karbor runs on native threads: the commands select the threading backend
# of oslo.service and nothing may monkey patch. (oslo.service still depends
# on eventlet, and futurist imports it when present; that alone patches
# nothing.) The API is a WSGI application only (no karbor-api command).
RUN PYTHONDONTWRITEBYTECODE=1 python3 - <<'EOF'
import importlib.metadata
import importlib.util
import sys

import karbor.cmd  # noqa: F401
from oslo_service import backend
import karbor.services.operationengine.manager  # noqa: F401
import karbor.services.protection.manager  # noqa: F401
# karbor.wsgi.api builds the application on import, which needs the
# configuration; the module only has to be there.
import karbor.wsgi.wsgi  # noqa: F401
assert importlib.util.find_spec('karbor.wsgi.api')
from karborclient import client  # noqa: F401
import pymysql  # noqa: F401

assert backend.get_backend_type() == backend.BackendType.THREADING
if 'eventlet' in sys.modules:
    from eventlet import patcher
    assert not patcher.is_monkey_patched('thread'), 'monkey patched'
# Every protection plugin and bank of the entry points must load.
eps = importlib.metadata.entry_points(group='karbor.protections')
for ep in eps:
    ep.load()
print('karbor: threading backend, not monkey patched, %d plugins' % len(eps))
EOF

RUN groupadd -g 42424 karbor \
    && useradd -u 42424 -g 42424 -M -d /var/lib/karbor \
               -s /usr/sbin/nologin -c "karbor user" karbor \
    && mkdir -p /etc/karbor /var/log/karbor /var/lib/karbor /var/cache/karbor \
    && chown karbor:karbor \
         /etc/karbor /var/log/karbor /var/lib/karbor /var/cache/karbor
