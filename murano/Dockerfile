# syntax=docker/dockerfile:1
ARG BASE_VENV_BUILDER=quay.io/airshipit/venv_builder:2026.2-ubuntu_resolute
ARG BASE_RUNTIME=quay.io/airshipit/base:2026.2-ubuntu_resolute
FROM ${BASE_VENV_BUILDER} AS build

ENV PATH=/var/lib/openstack/bin:$PATH

# Murano is retired upstream (opendev's master holds only a README and there
# is no stable/2026.2); the fork carries it forward. Keep the default on the
# fork: generate_pydep.py would otherwise fetch the requirements of the
# retired opendev repository for the release branch, get a 404 and fail the
# whole build. murano's database driver is listed in pydep.txt by hand.
ARG MURANO_REPO=https://github.com/fivetime/openstack-murano
# A release tag (or a commit). The repositories are private, so the ref
# cannot be watched through the API the way public forks are; naming it
# makes the build reproducible and invalidates the layer by itself.
ARG MURANO_REF=17.0.4
# murano-engine downloads the application packages through
# python-muranoclient, which needs murano-pkg-check; both are retired too and
# their last releases on PyPI do not install with 2026.2. Install the forks'.
ARG MURANOCLIENT_REPO=https://github.com/fivetime/python-muranoclient
ARG MURANOCLIENT_REF=3.0.2
ARG MURANOPKGCHECK_REPO=https://github.com/fivetime/murano-pkg-check
ARG MURANOPKGCHECK_REF=0.4.0
ARG PROFILES="fluent"

# Use bindep to determine packages needed for this profile set
COPY bindep.txt pydep.txt /opt/
RUN mkdir -p /etc/image_info && \
    uvx bindep -f /opt/bindep.txt -b -l newline murano ${PROFILES} > /etc/image_info/bindep_runtime.txt && \
    uvx bindep -f /opt/bindep.txt -b -l newline murano build ${PROFILES} > /etc/image_info/bindep_build.txt && \
    uvx bindep -f /opt/pydep.txt -b -l newline murano ${PROFILES} > /etc/image_info/python_packages.txt

RUN if [ -s /etc/image_info/bindep_build.txt ]; then \
        apt-get update \
        && DEBIAN_FRONTEND=noninteractive xargs --no-run-if-empty apt-get install -y --no-install-recommends < /etc/image_info/bindep_build.txt \
        && rm -rf /var/lib/apt/lists/*; \
    fi

# CI supplies src_repo_token as a BuildKit secret; the token and the
# temporary git rewrite live only inside this RUN and never reach an image
# layer. Full (blobless) clones, not single commits: pbr computes the
# versions from the tags.
RUN --mount=type=secret,id=src_repo_token \
    if [ -s /run/secrets/src_repo_token ]; then \
        token="$(cat /run/secrets/src_repo_token)"; \
        git config --global \
          url."https://x-access-token:${token}@github.com/".insteadOf \
          "https://github.com/"; \
    fi \
    && git clone --filter=blob:none ${MURANO_REPO} /tmp/murano \
    && git clone --filter=blob:none ${MURANOCLIENT_REPO} /tmp/muranoclient \
    && git clone --filter=blob:none ${MURANOPKGCHECK_REPO} /tmp/muranopkgcheck \
    # Still authenticated: a blobless checkout fetches the blobs it needs.
    && git -C /tmp/murano checkout --detach ${MURANO_REF} \
    && git -C /tmp/muranoclient checkout --detach ${MURANOCLIENT_REF} \
    && git -C /tmp/muranopkgcheck checkout --detach ${MURANOPKGCHECK_REF} \
    && rm -f /root/.gitconfig \
    && sed -i '/^murano===/d; /^python-muranoclient===/d; /^murano-pkg-check===/d' /upper-constraints.txt \
    && uv pip install \
         --build-constraint /upper-constraints.txt \
         -c /upper-constraints.txt \
         -r /etc/image_info/python_packages.txt \
         /tmp/murano /tmp/muranoclient /tmp/muranopkgcheck \
    # The core library (io.murano) and the application development library
    # (io.murano.applications) are packages the API imports once
    # (murano-manage import-package); they are not part of the Python package.
    && mkdir -p /var/lib/openstack/share/murano \
    && cp -a /tmp/murano/meta /var/lib/openstack/share/murano/meta \
    && { git -C /tmp/murano log --oneline -1; \
         git -C /tmp/muranoclient log --oneline -1; \
         git -C /tmp/muranopkgcheck log --oneline -1; } > /etc/image_info/project.txt \
    && rm -rf /tmp/murano /tmp/muranoclient /tmp/muranopkgcheck \
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

# murano runs on native threads: the commands and the WSGI applications
# select the threading backend of oslo.service and nothing may monkey patch.
# (oslo.service still depends on eventlet, and futurist imports it when
# present; that alone patches nothing.) The API is a WSGI application only
# (no murano-api command).
RUN PYTHONDONTWRITEBYTECODE=1 python3 - <<'EOF'
import importlib.metadata as m
import importlib.util
import os
import sys

import murano.cmd  # noqa: F401
from oslo_service import backend
# the options the engine and the DSL read at import, as murano-engine
# registers them first
import murano.common.config  # noqa: F401
import murano.common.engine  # noqa: F401
import murano.common.server  # noqa: F401
import murano.httpd  # noqa: F401
# murano.wsgi.api builds the application on import, which needs the
# configuration; the modules only have to be there.
for module in ('murano.wsgi.api', 'murano.wsgi.cfapi'):
    assert importlib.util.find_spec(module), module
from muranoclient import client  # noqa: F401
import muranopkgcheck.manager  # noqa: F401
import pymysql  # noqa: F401

assert backend.get_backend_type() == backend.BackendType.THREADING
if 'eventlet' in sys.modules:
    from eventlet import patcher
    assert not patcher.is_monkey_patched('thread'), 'monkey patched'
# The versions come from the tags; 0.x for murano means pbr saw none.
versions = {p: m.version(p) for p in
            ('murano', 'python-muranoclient', 'murano-pkg-check')}
assert int(versions['murano'].split('.')[0]) >= 17, versions
meta = '/var/lib/openstack/share/murano/meta'
for package in ('io.murano', 'io.murano.applications'):
    assert os.path.isfile(os.path.join(meta, package, 'manifest.yaml')), package
print('murano: threading backend, not monkey patched, %s' % versions)
EOF

RUN groupadd -g 42424 murano \
    && useradd -u 42424 -g 42424 -M -d /var/lib/murano \
               -s /usr/sbin/nologin -c "murano user" murano \
    && mkdir -p /etc/murano /var/log/murano /var/lib/murano /var/cache/murano \
    && chown murano:murano \
         /etc/murano /var/log/murano /var/lib/murano /var/cache/murano
