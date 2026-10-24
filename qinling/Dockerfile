# syntax=docker/dockerfile:1
ARG BASE_VENV_BUILDER=quay.io/airshipit/venv_builder:2026.2-ubuntu_resolute
ARG BASE_RUNTIME=quay.io/airshipit/base:2026.2-ubuntu_resolute
FROM ${BASE_VENV_BUILDER} AS build

ENV PATH=/var/lib/openstack/bin:$PATH

# Qinling is retired upstream (opendev's master holds only a README and there
# is no stable/2026.2); the fork carries it forward. Keep the default on the
# fork: generate_pydep.py would otherwise fetch the requirements of the
# retired opendev repository for the release branch, get a 404 and fail the
# whole build. qinling's driver packages are listed in pydep.txt by hand.
ARG QINLING_REPO=https://github.com/fivetime/openstack-qinling
# A release tag (or a commit). The repository is private, so the ref cannot
# be watched through the API the way public forks are; naming it makes the
# build reproducible and invalidates the layer by itself.
ARG QINLING_REF=17.0.6
ARG PROFILES="fluent"

# Use bindep to determine packages needed for this profile set
COPY bindep.txt pydep.txt /opt/
RUN mkdir -p /etc/image_info && \
    uvx bindep -f /opt/bindep.txt -b -l newline qinling ${PROFILES} > /etc/image_info/bindep_runtime.txt && \
    uvx bindep -f /opt/bindep.txt -b -l newline qinling build ${PROFILES} > /etc/image_info/bindep_build.txt && \
    uvx bindep -f /opt/pydep.txt -b -l newline qinling ${PROFILES} > /etc/image_info/python_packages.txt

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
    && git clone --filter=blob:none ${QINLING_REPO} /tmp/qinling \
    # Still authenticated: a blobless checkout fetches the blobs it needs.
    && git -C /tmp/qinling checkout --detach ${QINLING_REF} \
    && rm -f /root/.gitconfig \
    && sed -i '/^qinling===/d' /upper-constraints.txt \
    && uv pip install \
         --build-constraint /upper-constraints.txt \
         -c /upper-constraints.txt \
         -r /etc/image_info/python_packages.txt \
         /tmp/qinling \
    && git -C /tmp/qinling log --oneline -1 > /etc/image_info/project.txt \
    && rm -rf /tmp/qinling \
    && uv pip freeze > /etc/image_info/pip.txt

# cotyledon: Python 3.14 made 'forkserver' the default multiprocessing start
# method on Linux and cotyledon 2.2.0 follows the default, so its workers no
# longer inherit the logging set up in the master (INFO lost, errors printed
# as the bare message). qinling-engine runs its engine service as a cotyledon
# worker. The fork keeps forking (sileht/cotyledon#94), as for cloudkitty.
ARG COTYLEDON_REPO=https://github.com/fivetime/cotyledon
ARG COTYLEDON_REF=e76637295655dc9b4561bdd2cafc677135e9bd3f
RUN sed -i '/^cotyledon===/d' /upper-constraints.txt \
    && uv pip install --no-deps "cotyledon @ git+${COTYLEDON_REPO}@${COTYLEDON_REF}" \
    && echo "${COTYLEDON_REPO}@${COTYLEDON_REF}" > /etc/image_info/cotyledon.txt \
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

# qinling runs on native threads: the commands and the WSGI application
# select the threading backend of oslo.service and nothing may monkey patch.
# (oslo.service still depends on eventlet, and futurist imports it when
# present; that alone patches nothing.) The API is a WSGI application only
# (no qinling-api command).
RUN PYTHONDONTWRITEBYTECODE=1 python3 - <<'EOF'
import importlib.metadata
import importlib.util
import sys

import qinling.cmd  # noqa: F401
from oslo_service import backend
import qinling.cmd.engine  # noqa: F401
import qinling.engine.service  # noqa: F401
import qinling.api.app  # noqa: F401
# qinling.api.wsgi builds the application on import, which needs the
# configuration; the module only has to be there.
assert importlib.util.find_spec('qinling.api.wsgi')
from qinling import policies
import kubernetes.client  # noqa: F401
import etcd3gw  # noqa: F401
import pymysql  # noqa: F401

assert backend.get_backend_type() == backend.BackendType.THREADING
from cotyledon import _service_manager
# The fork of cotyledon: workers are forked, not started by a forkserver.
assert _service_manager._default_mp_context().get_start_method() == 'fork'
if 'eventlet' in sys.modules:
    from eventlet import patcher
    assert not patcher.is_monkey_patched('thread'), 'monkey patched'
for group in ('qinling.orchestrator', 'qinling.storage.provider'):
    for ep in importlib.metadata.entry_points(group=group):
        ep.load()
print('qinling: threading backend, not monkey patched, %d policies'
      % len(list(policies.list_rules())))
EOF

RUN groupadd -g 42424 qinling \
    && useradd -u 42424 -g 42424 -M -d /var/lib/qinling \
               -s /usr/sbin/nologin -c "qinling user" qinling \
    && mkdir -p /etc/qinling /var/log/qinling /var/lib/qinling /var/cache/qinling \
    && chown qinling:qinling \
         /etc/qinling /var/log/qinling /var/lib/qinling /var/cache/qinling
