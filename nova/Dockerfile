# syntax=docker/dockerfile:1
ARG BASE_VENV_BUILDER=quay.io/airshipit/venv_builder:2025.2-ubuntu_noble
ARG BASE_RUNTIME=quay.io/airshipit/base:2025.2-ubuntu_noble
FROM ${BASE_VENV_BUILDER} AS build

ENV PATH=/var/lib/openstack/bin:$PATH

ARG NOVA_REPO=https://opendev.org/openstack/nova
ARG NOVA_REF=stable/2026.1
ARG PROFILES="fluent ceph linuxbridge openvswitch configdrive qemu apache migration"

# Use bindep to determine packages needed for this profile set
COPY bindep.txt pydep.txt /opt/
RUN mkdir -p /etc/image_info && \
    uvx bindep -f /opt/bindep.txt -b -l newline nova ${PROFILES} > /etc/image_info/bindep_runtime.txt && \
    uvx bindep -f /opt/bindep.txt -b -l newline nova build ${PROFILES} > /etc/image_info/bindep_build.txt && \
    uvx bindep -f /opt/pydep.txt -b -l newline nova ${PROFILES} > /etc/image_info/python_packages.txt

RUN if [ -s /etc/image_info/bindep_build.txt ]; then \
        apt-get update \
        && DEBIAN_FRONTEND=noninteractive xargs --no-run-if-empty apt-get install -y --no-install-recommends < /etc/image_info/bindep_build.txt \
        && rm -rf /var/lib/apt/lists/*; \
    fi

# Changes carried until they merge upstream, one directory per release under
# nova/patches/nova/ (NOVA_REF without "stable/"); a release without one is
# built unpatched:
#   2026.2/0001-decide-osprofiler-tracing-after-config.patch -- trace_cls()
#     and the manager metaclass decided at import time whether to trace, before
#     the services parse [profiler] enabled, so nova-compute traced no RPC
#     client or Glance calls (https://review.opendev.org/c/openstack/nova/+/1010918,
#     bug 1731864; runtime files only, the tests stay in the change).
#   2026.2/0002-api-return-409-for-start-stop-task-state-race.patch -- two
#     concurrent os-start (or os-stop) requests for one server: the slower
#     one lost the conditional task_state save and got a 500 instead of a
#     409, although the server was being started (runtime file only).
# A patch that stops applying fails the build on purpose: rebase it, or drop it
# once merged.
COPY nova/patches/nova/ /tmp/patches/nova/
RUN sed -i '/^nova===/d' /upper-constraints.txt \
    && git clone --filter=blob:none -b ${NOVA_REF} ${NOVA_REPO} /tmp/nova \
    && release=${NOVA_REF#stable/} \
    && for p in /tmp/patches/nova/${release}/*.patch; do \
           [ -e "${p}" ] || continue; \
           echo "applying nova/${release}/${p##*/}"; \
           git -C /tmp/nova apply "${p}" || exit 1; \
           echo "nova patch ${release}/${p##*/}" >> /etc/image_info/patches.txt; \
       done \
    && rm -rf /tmp/patches \
    && uv pip install \
         --build-constraint /upper-constraints.txt \
         -c /upper-constraints.txt \
         -r /etc/image_info/python_packages.txt \
         /tmp/nova \
    && git -C /tmp/nova log --oneline -1 > /etc/image_info/project.txt \
    && rm -rf /tmp/nova \
    && uv pip freeze > /etc/image_info/pip.txt

# osprofiler tracing ([profiler] connection_string = otlp://...): fix the otlp
# driver for forking and threaded services, and clean the trace a pooled
# thread keeps between RPC messages and tasks. See osprofiler-otlp/.
COPY osprofiler-otlp/patch_otlp_driver.py osprofiler-otlp/patch_rpc_context.py /opt/
RUN PYTHONDONTWRITEBYTECODE=1 python3 /opt/patch_otlp_driver.py \
    && PYTHONDONTWRITEBYTECODE=1 python3 /opt/patch_rpc_context.py

FROM ${BASE_RUNTIME} AS runtime

ENV PATH=/var/lib/openstack/bin:$PATH

ARG NOVNC_REPO=https://github.com/novnc/novnc
ARG NOVNC_REF=v1.0.0
ARG SPICE_REPO=https://gitlab.freedesktop.org/spice/spice-html5.git
ARG SPICE_REF=spice-html5-0.1.6

ARG NOVA_TSS_USER=tss
ARG NOVA_TSS_UID=42434
ARG NOVA_TSS_GID=42434

COPY --from=build --link /var/lib/openstack /var/lib/openstack
COPY --from=build /etc/image_info /etc/image_info

# Install packages determined by bindep in build stage
RUN if [ -s /etc/image_info/bindep_runtime.txt ]; then \
        apt-get update \
        && DEBIAN_FRONTEND=noninteractive xargs --no-run-if-empty apt-get install -y --no-install-recommends < /etc/image_info/bindep_runtime.txt \
        && rm -rf /var/lib/apt/lists/*; \
    fi

RUN find /var/lib/openstack \( -name "*.pyc" -o -name "__pycache__" \) -delete \
    && rm -rf /tmp/* /root/.cache /etc/machine-id

# Install noVNC and SPICE HTML5 console clients
RUN mkdir /usr/share/novnc \
    && git clone -b ${NOVNC_REF} --depth 1 ${NOVNC_REPO} /usr/share/novnc \
    && rm -rf /usr/share/novnc/.git* \
    && if [ ! -f /usr/share/novnc/vnc_auto.html ]; then \
           ln -s vnc_lite.html /usr/share/novnc/vnc_auto.html; \
       fi \
    && mkdir /usr/share/spice-html5 \
    && git clone -b ${SPICE_REF} --depth 1 ${SPICE_REPO} /usr/share/spice-html5 \
    && rm -rf /usr/share/spice-html5/.git*

RUN groupadd -g 42424 nova \
    && useradd -u 42424 -g 42424 -M -d /var/lib/nova \
               -s /bin/bash -c "nova user" nova \
    && mkdir -p /etc/nova /var/log/nova /var/lib/nova /var/cache/nova \
    && chown nova:nova \
         /etc/nova /var/log/nova /var/lib/nova /var/cache/nova

# Create TSS user/group for emulated TPM (swtpm)
RUN groupadd -g ${NOVA_TSS_GID} ${NOVA_TSS_USER} \
    && useradd -u ${NOVA_TSS_UID} -g ${NOVA_TSS_USER} \
               -s /usr/sbin/nologin -c "${NOVA_TSS_USER} user" ${NOVA_TSS_USER}
