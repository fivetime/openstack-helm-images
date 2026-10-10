# syntax=docker/dockerfile:1
ARG BASE_VENV_BUILDER=quay.io/airshipit/venv_builder:2026.2-ubuntu_resolute
ARG BASE_RUNTIME=quay.io/airshipit/base:2026.2-ubuntu_resolute
FROM ${BASE_VENV_BUILDER} AS build

ENV PATH=/var/lib/openstack/bin:$PATH

# Senlin is retired upstream (opendev's master holds only a README and there
# is no stable/2026.2); the fork carries it forward. Keep the default on the
# fork: generate_pydep.py would otherwise fetch the requirements of the
# retired opendev repository for the release branch, get a 404 and fail the
# whole build. senlin's driver packages are listed in pydep.txt by hand.
ARG SENLIN_REPO=https://github.com/fivetime/openstack-senlin
# A release tag (or a commit). The repository is private, so the ref cannot
# be watched through the API the way public forks are; naming it makes the
# build reproducible and invalidates the layer by itself.
ARG SENLIN_REF=22.0.4
ARG PROFILES="fluent"

# Use bindep to determine packages needed for this profile set
COPY bindep.txt pydep.txt /opt/
RUN mkdir -p /etc/image_info && \
    uvx bindep -f /opt/bindep.txt -b -l newline senlin ${PROFILES} > /etc/image_info/bindep_runtime.txt && \
    uvx bindep -f /opt/bindep.txt -b -l newline senlin build ${PROFILES} > /etc/image_info/bindep_build.txt && \
    uvx bindep -f /opt/pydep.txt -b -l newline senlin ${PROFILES} > /etc/image_info/python_packages.txt

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
    && git clone --filter=blob:none ${SENLIN_REPO} /tmp/senlin \
    # Still authenticated: a blobless checkout fetches the blobs it needs.
    && git -C /tmp/senlin checkout --detach ${SENLIN_REF} \
    && rm -f /root/.gitconfig \
    && sed -i '/^senlin===/d' /upper-constraints.txt \
    && uv pip install \
         --build-constraint /upper-constraints.txt \
         -c /upper-constraints.txt \
         -r /etc/image_info/python_packages.txt \
         /tmp/senlin \
    && git -C /tmp/senlin log --oneline -1 > /etc/image_info/project.txt \
    # The chart's uWSGI loads this file (wsgi-file); pbr only writes it on
    # a regular install, so fail here rather than at pod start.
    && test -x /var/lib/openstack/bin/senlin-wsgi-api \
    && rm -rf /tmp/senlin \
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

# senlin runs on native threads: the commands select the threading backend
# of oslo.service and nothing may monkey patch. (oslo.service still depends
# on eventlet, and futurist imports it when present; that alone patches
# nothing.)
RUN PYTHONDONTWRITEBYTECODE=1 python3 - <<'EOF'
import sys

import senlin.cmd  # noqa: F401
from oslo_service import backend
import senlin.engine.service  # noqa: F401
import senlin.health_manager.service  # noqa: F401

assert backend.get_backend_type() == backend.BackendType.THREADING
if 'eventlet' in sys.modules:
    from eventlet import patcher
    assert not patcher.is_monkey_patched('thread'), 'monkey patched'
print('senlin: threading backend, not monkey patched')
EOF

RUN groupadd -g 42424 senlin \
    && useradd -u 42424 -g 42424 -M -d /var/lib/senlin \
               -s /usr/sbin/nologin -c "senlin user" senlin \
    && mkdir -p /etc/senlin /var/log/senlin /var/lib/senlin /var/cache/senlin \
    && chown senlin:senlin \
         /etc/senlin /var/log/senlin /var/lib/senlin /var/cache/senlin
