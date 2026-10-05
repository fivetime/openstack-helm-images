# syntax=docker/dockerfile:1
ARG BASE_VENV_BUILDER=quay.io/airshipit/venv_builder:2025.2-ubuntu_noble
ARG BASE_RUNTIME=quay.io/airshipit/base:2025.2-ubuntu_noble
FROM ${BASE_VENV_BUILDER} AS build

ENV PATH=/var/lib/openstack/bin:$PATH

# Upstream by default. The 2026.1 cell overrides this with the fivetime fork
# (and its REF with master, the only branch the fork has: its stable/2026.1
# was merged into master and deleted on 2026-10-05). The fork carries:
# volume.provider.pool.* pollsters emit the ``provider`` metadata that
# gnocchi_resources.yaml requires (upstream inconsistency -- every polled pool
# capacity sample was rejected by Gnocchi). Master rows are synthesized from
# that cell, so they land on the fork too.
#
# This default has to be upstream: the cells that build a release branch pass
# only CEILOMETER_REF, so a fork default sent them to a fork branch that does
# not exist, and both the ADD below and the clone failed on it.
ARG CEILOMETER_REPO=https://opendev.org/openstack/ceilometer
ARG CEILOMETER_REF=master
# python-gnocchiclient fork: percent-encodes resource ids in URL paths.
# Cinder pool names are "<host>@<backend>#<pool>"; upstream 7.2.0 puts the
# raw id in the path, '#' becomes a URL fragment and every resource
# update/show/delete on a pool lands on a nonexistent resource (404).
ARG GNOCCHICLIENT_REPO=https://github.com/fivetime/python-gnocchiclient
ARG GNOCCHICLIENT_REF=master
ARG PROFILES="fluent apache"

# Use bindep to determine packages needed for this profile set
COPY bindep.txt pydep.txt /opt/
RUN mkdir -p /etc/image_info && \
    uvx bindep -f /opt/bindep.txt -b -l newline ceilometer ${PROFILES} > /etc/image_info/bindep_runtime.txt && \
    uvx bindep -f /opt/bindep.txt -b -l newline ceilometer build ${PROFILES} > /etc/image_info/bindep_build.txt && \
    uvx bindep -f /opt/pydep.txt -b -l newline ceilometer ${PROFILES} > /etc/image_info/python_packages.txt

RUN if [ -s /etc/image_info/bindep_build.txt ]; then \
        apt-get update \
        && DEBIAN_FRONTEND=noninteractive xargs --no-run-if-empty apt-get install -y --no-install-recommends < /etc/image_info/bindep_build.txt \
        && rm -rf /var/lib/apt/lists/*; \
    fi

# Cache-bust: the RUN below is keyed on its text, so a rebuild against the same
# branch name would silently reuse the layer with stale code. The branch head
# JSON changes on every push and forces the clone to re-run.
#
# The URL has to follow CEILOMETER_REPO, not just CEILOMETER_REF: the default
# is opendev's Gitea API for the branch being built, and the cell that builds
# the fork passes GitHub's ref API instead. Both return only the branch head,
# so the file is byte-identical until the branch moves.
ARG CEILOMETER_REF_URL=https://opendev.org/api/v1/repos/openstack/ceilometer/branches/${CEILOMETER_REF}
ADD ${CEILOMETER_REF_URL} /tmp/ceilometer.ref
ADD https://api.github.com/repos/fivetime/python-gnocchiclient/git/refs/heads/${GNOCCHICLIENT_REF} /tmp/gnocchiclient.ref

# awscurl: ceilometer wants >=0.40 from 2026.2 on, for the tls_min/tls_max
# arguments make_request() grew in 0.40 and rgw_client.py now passes. The
# 2026.1 upper-constraints still pin ===0.36, so resolving master against
# them fails outright. Raise the pin rather than drop it, and raise it to
# the version upstream itself pins: both the 2026.2 and the master
# constraints are already on awscurl===0.44, and its make_request() keeps
# every positional argument 0.36 had, so the release cells are unaffected
# (2025.2 does not depend on awscurl at all, and 2026.2 is on 0.44 already,
# which makes this a no-op for both).
RUN sed -i '/^ceilometer===/d;s|^awscurl===.*|awscurl===0.44|' /upper-constraints.txt \
    && git clone --filter=blob:none -b ${CEILOMETER_REF} ${CEILOMETER_REPO} /tmp/ceilometer \
    && uv pip install \
         --build-constraint /upper-constraints.txt \
         -c /upper-constraints.txt \
         -r /etc/image_info/python_packages.txt \
         /tmp/ceilometer \
    && git -C /tmp/ceilometer log --oneline -1 > /etc/image_info/project.txt \
    && rm -rf /tmp/ceilometer \
    && sed -i '/^gnocchiclient===/d' /upper-constraints.txt \
    && git clone --filter=blob:none -b ${GNOCCHICLIENT_REF} ${GNOCCHICLIENT_REPO} /tmp/gnocchiclient \
    && uv pip install --no-deps -c /upper-constraints.txt /tmp/gnocchiclient \
    && git -C /tmp/gnocchiclient log --oneline -1 > /etc/image_info/gnocchiclient.txt \
    && rm -rf /tmp/gnocchiclient \
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

RUN groupadd -g 42424 ceilometer \
    && useradd -u 42424 -g 42424 -M -d /var/lib/ceilometer \
               -s /usr/sbin/nologin -c "ceilometer user" ceilometer \
    && mkdir -p /etc/ceilometer /var/log/ceilometer /var/lib/ceilometer /var/cache/ceilometer \
    && chown ceilometer:ceilometer \
         /etc/ceilometer /var/log/ceilometer /var/lib/ceilometer /var/cache/ceilometer
