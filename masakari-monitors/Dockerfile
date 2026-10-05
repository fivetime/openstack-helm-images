# syntax=docker/dockerfile:1
ARG BASE_VENV_BUILDER=quay.io/airshipit/venv_builder:2025.2-ubuntu_noble
ARG BASE_RUNTIME=quay.io/airshipit/base:2025.2-ubuntu_noble
FROM ${BASE_VENV_BUILDER} AS build

ENV PATH=/var/lib/openstack/bin:$PATH

ARG MASAKARI_MONITORS_REPO=https://opendev.org/openstack/masakari-monitors
ARG MASAKARI_MONITORS_REF=stable/2026.1
ARG PROFILES=""

# Use bindep to determine packages needed for this profile set
COPY bindep.txt pydep.txt /opt/
RUN mkdir -p /etc/image_info && \
    uvx bindep -f /opt/bindep.txt -b -l newline masakari-monitors ${PROFILES} > /etc/image_info/bindep_runtime.txt && \
    uvx bindep -f /opt/bindep.txt -b -l newline masakari-monitors build ${PROFILES} > /etc/image_info/bindep_build.txt && \
    uvx bindep -f /opt/pydep.txt -b -l newline masakari-monitors ${PROFILES} > /etc/image_info/python_packages.txt

RUN if [ -s /etc/image_info/bindep_build.txt ]; then \
        apt-get update \
        && DEBIAN_FRONTEND=noninteractive xargs --no-run-if-empty apt-get install -y --no-install-recommends < /etc/image_info/bindep_build.txt \
        && rm -rf /var/lib/apt/lists/*; \
    fi

RUN sed -i '/^masakari-monitors===/d' /upper-constraints.txt \
    && git clone --filter=blob:none -b ${MASAKARI_MONITORS_REF} ${MASAKARI_MONITORS_REPO} /tmp/masakari-monitors \
    && uv pip install \
         --build-constraint /upper-constraints.txt \
         -c /upper-constraints.txt \
         -r /etc/image_info/python_packages.txt \
         /tmp/masakari-monitors \
    && git -C /tmp/masakari-monitors log --oneline -1 > /etc/image_info/project.txt \
    && rm -rf /tmp/masakari-monitors

# The Incus exporter and notifier, masakari-incus-exporter and
# masakari-incus-notifier, come from their own package. A cell that leaves
# INCUS_MONITOR_REF empty builds plain masakari-monitors. The ref is a commit,
# so a new one changes the build argument and rebuilds this layer. The
# repository is private: CI supplies src_repo_token as a BuildKit secret, used
# only by the fetch below and never written to git config or a layer. Its
# dependencies (masakari-monitors, openstacksdk, oslo.*) are installed above.
ARG INCUS_MONITOR_REPO=https://github.com/fivetime/incus-monitor.git
ARG INCUS_MONITOR_REF=""
RUN --mount=type=secret,id=src_repo_token \
    if [ -n "${INCUS_MONITOR_REF}" ]; then \
        set -e; \
        auth=""; \
        if [ -s /run/secrets/src_repo_token ]; then \
            auth="url.https://x-access-token:$(cat /run/secrets/src_repo_token)@github.com/.insteadOf=https://github.com/"; \
        fi; \
        git init -q /tmp/incus-monitor; \
        git -C /tmp/incus-monitor ${auth:+-c "$auth"} fetch -q --depth=1 \
            "${INCUS_MONITOR_REPO}" "${INCUS_MONITOR_REF}"; \
        git -C /tmp/incus-monitor checkout -q --detach FETCH_HEAD; \
        uv pip install --no-deps /tmp/incus-monitor; \
        git -C /tmp/incus-monitor log --oneline -1 > /etc/image_info/incus-monitor.txt; \
        rm -rf /tmp/incus-monitor; \
    fi

RUN uv pip freeze > /etc/image_info/pip.txt

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

RUN groupadd -g 42424 masakari \
    && useradd -u 42424 -g 42424 -M -d /var/lib/masakari \
               -s /usr/sbin/nologin -c "masakari user" masakari \
    && mkdir -p /etc/masakari /var/log/masakari /var/lib/masakari /var/cache/masakari \
    && chown masakari:masakari \
         /etc/masakari /var/log/masakari /var/lib/masakari /var/cache/masakari
