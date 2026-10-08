# syntax=docker/dockerfile:1
ARG BASE_VENV_BUILDER=quay.io/airshipit/venv_builder:2026.1-ubuntu_noble
ARG BASE_RUNTIME=quay.io/airshipit/base:2026.1-ubuntu_noble
FROM ${BASE_VENV_BUILDER} AS build

ENV PATH=/var/lib/openstack/bin:$PATH

ARG AODH_REPO=https://opendev.org/openstack/aodh
ARG AODH_REF=stable/2026.1
ARG PROFILES="fluent apache"

# Use bindep to determine packages needed for this profile set
COPY bindep.txt pydep.txt /opt/
RUN mkdir -p /etc/image_info && \
    uvx bindep -f /opt/bindep.txt -b -l newline aodh ${PROFILES} > /etc/image_info/bindep_runtime.txt && \
    uvx bindep -f /opt/bindep.txt -b -l newline aodh build ${PROFILES} > /etc/image_info/bindep_build.txt && \
    uvx bindep -f /opt/pydep.txt -b -l newline aodh ${PROFILES} > /etc/image_info/python_packages.txt

RUN if [ -s /etc/image_info/bindep_build.txt ]; then \
        apt-get update \
        && DEBIAN_FRONTEND=noninteractive xargs --no-run-if-empty apt-get install -y --no-install-recommends < /etc/image_info/bindep_build.txt \
        && rm -rf /var/lib/apt/lists/*; \
    fi

RUN sed -i '/^aodh===/d' /upper-constraints.txt \
    && git clone --filter=blob:none -b ${AODH_REF} ${AODH_REPO} /tmp/aodh \
    && uv pip install \
         --build-constraint /upper-constraints.txt \
         -c /upper-constraints.txt \
         -r /etc/image_info/python_packages.txt \
         /tmp/aodh \
    && git -C /tmp/aodh log --oneline -1 > /etc/image_info/project.txt \
    && rm -rf /tmp/aodh \
    && uv pip freeze > /etc/image_info/pip.txt

# cotyledon: Python 3.14 made 'forkserver' the default multiprocessing start
# method on Linux and cotyledon 2.2.0 follows the default, so its workers no
# longer inherit the logging set up in the master (INFO lost, errors printed
# as the bare message). The fork keeps forking (sileht/cotyledon#94). Only the
# cells that set COTYLEDON_REF install it -- the 2026.2 ones, the first on
# Python 3.14. The ref is a commit, so the layer needs no cache-bust.
ARG COTYLEDON_REPO=https://github.com/fivetime/cotyledon
ARG COTYLEDON_REF=
RUN if [ -n "${COTYLEDON_REF}" ]; then \
        sed -i '/^cotyledon===/d' /upper-constraints.txt \
        && uv pip install --no-deps "cotyledon @ git+${COTYLEDON_REPO}@${COTYLEDON_REF}" \
        && echo "${COTYLEDON_REPO}@${COTYLEDON_REF}" > /etc/image_info/cotyledon.txt \
        && uv pip freeze > /etc/image_info/pip.txt; \
    fi

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

RUN groupadd -g 42425 aodh \
    && useradd -u 42425 -g 42425 -M -d /var/lib/aodh \
               -s /usr/sbin/nologin -c "aodh user" aodh \
    && mkdir -p /etc/aodh /var/log/aodh /var/lib/aodh /var/cache/aodh \
    && chown aodh:aodh \
         /etc/aodh /var/log/aodh /var/lib/aodh /var/cache/aodh
