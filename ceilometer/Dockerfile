# syntax=docker/dockerfile:1
ARG BASE_VENV_BUILDER=quay.io/airshipit/venv_builder:2025.2-ubuntu_noble
ARG BASE_RUNTIME=quay.io/airshipit/base:2025.2-ubuntu_noble
FROM ${BASE_VENV_BUILDER} AS build

ENV PATH=/var/lib/openstack/bin:$PATH

# fivetime fork (upstream stable/2026.1 + patches; see the fork's git log).
# Currently carries: volume.provider.pool.* pollsters emit the ``provider``
# metadata that gnocchi_resources.yaml requires (upstream inconsistency --
# every polled pool capacity sample was rejected by Gnocchi). The zuul.d
# entry passes the same REPO; master rows are synthesized from it.
ARG CEILOMETER_REPO=https://github.com/fivetime/openstack-ceilometer
ARG CEILOMETER_REF=stable/2026.1
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
ADD https://api.github.com/repos/fivetime/openstack-ceilometer/git/refs/heads/${CEILOMETER_REF} /tmp/ceilometer.ref

RUN sed -i '/^ceilometer===/d' /upper-constraints.txt \
    && git clone --filter=blob:none -b ${CEILOMETER_REF} ${CEILOMETER_REPO} /tmp/ceilometer \
    && uv pip install \
         --build-constraint /upper-constraints.txt \
         -c /upper-constraints.txt \
         -r /etc/image_info/python_packages.txt \
         /tmp/ceilometer \
    && git -C /tmp/ceilometer log --oneline -1 > /etc/image_info/project.txt \
    && rm -rf /tmp/ceilometer \
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
