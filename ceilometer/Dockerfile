# syntax=docker/dockerfile:1
ARG BASE_VENV_BUILDER=quay.io/airshipit/venv_builder:2025.2-ubuntu_noble
ARG BASE_RUNTIME=quay.io/airshipit/base:2025.2-ubuntu_noble
FROM ${BASE_VENV_BUILDER} AS build

ENV PATH=/var/lib/openstack/bin:$PATH

# Upstream. Every cell builds opendev ceilometer and passes only
# CEILOMETER_REF; the 2026.1 cell passes master (see zuul.d/ceilometer.yaml
# for why). The fivetime fork this used to default to carried one fix, the
# ``provider`` metadata on volume.provider.pool.* samples, which upstream
# merged as f067b91d; once the fork's tree matched opendev master it was
# dropped from the build.
#
# The default has to be upstream regardless: the release cells pass only
# CEILOMETER_REF, and a fork default sent them to fork branches that do not
# exist, so both the ADD below and the clone failed on them.
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
# is opendev's Gitea API for the branch being built, so a cell that builds
# from somewhere else must pass its own (GitHub's ref API for a GitHub repo).
# Both return only the branch head, so the file is byte-identical until the
# branch moves.
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
