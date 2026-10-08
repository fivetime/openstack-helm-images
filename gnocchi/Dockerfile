# syntax=docker/dockerfile:1
ARG BASE_VENV_BUILDER=quay.io/airshipit/venv_builder:2026.1-ubuntu_noble
ARG BASE_RUNTIME=quay.io/airshipit/base:2026.1-ubuntu_noble
FROM ${BASE_VENV_BUILDER} AS build

ENV PATH=/var/lib/openstack/bin:$PATH

# Gnocchi is not an OpenStack deliverable: it lives on GitHub and ships its own
# release tags rather than stable/<release> branches, so pin a tag here.
ARG GNOCCHI_REPO=https://github.com/gnocchixyz/gnocchi
ARG GNOCCHI_REF=4.7.0
# ceph = no python deps (rados comes from the distro package installed in the
# runtime stage); the venv is built with --system-site-packages so it is visible.
ARG GNOCCHI_EXTRAS="postgresql,mysql,keystone,redis,s3,prometheus,ceph"
# The gnocchi CLI (python-gnocchiclient) is what the chart's resources-cleaner
# CronJob and helm test run; gnocchi itself does not depend on it, so without
# this the cleaner fails on every run. Same fork as the ceilometer image: it
# percent-encodes resource ids in URL paths (Cinder pool ids contain '#').
ARG GNOCCHICLIENT_REPO=https://github.com/fivetime/python-gnocchiclient
ARG GNOCCHICLIENT_REF=master
ARG PROFILES="fluent ceph"

# Use bindep to determine packages needed for this profile set
COPY bindep.txt pydep.txt /opt/
RUN mkdir -p /etc/image_info && \
    uvx bindep -f /opt/bindep.txt -b -l newline gnocchi ${PROFILES} > /etc/image_info/bindep_runtime.txt && \
    uvx bindep -f /opt/bindep.txt -b -l newline gnocchi build ${PROFILES} > /etc/image_info/bindep_build.txt && \
    uvx bindep -f /opt/pydep.txt -b -l newline gnocchi ${PROFILES} > /etc/image_info/python_packages.txt

RUN if [ -s /etc/image_info/bindep_build.txt ]; then \
        apt-get update \
        && DEBIAN_FRONTEND=noninteractive xargs --no-run-if-empty apt-get install -y --no-install-recommends < /etc/image_info/bindep_build.txt \
        && rm -rf /var/lib/apt/lists/*; \
    fi

# The branch head JSON changes on every push, so a new client commit re-runs
# the RUN below instead of reusing a cached layer.
ADD https://api.github.com/repos/fivetime/python-gnocchiclient/git/refs/heads/${GNOCCHICLIENT_REF} /tmp/gnocchiclient.ref

# Gnocchi is not in upper-constraints, but its dependencies are; keep the
# OpenStack constraints for the shared libraries (oslo.*, keystonemiddleware).
RUN git clone --filter=blob:none -b ${GNOCCHI_REF} ${GNOCCHI_REPO} /tmp/gnocchi \
    && uv pip install \
         --build-constraint /upper-constraints.txt \
         -c /upper-constraints.txt \
         -r /etc/image_info/python_packages.txt \
         "/tmp/gnocchi[${GNOCCHI_EXTRAS}]" \
    && git -C /tmp/gnocchi log --oneline -1 > /etc/image_info/project.txt \
    && rm -rf /tmp/gnocchi \
    && sed -i '/^gnocchiclient===/d' /upper-constraints.txt \
    && git clone --filter=blob:none -b ${GNOCCHICLIENT_REF} ${GNOCCHICLIENT_REPO} /tmp/gnocchiclient \
    && uv pip install -c /upper-constraints.txt /tmp/gnocchiclient \
    && git -C /tmp/gnocchiclient log --oneline -1 > /etc/image_info/gnocchiclient.txt \
    && rm -rf /tmp/gnocchiclient \
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

RUN groupadd -g 42426 gnocchi \
    && useradd -u 42426 -g 42426 -M -d /var/lib/gnocchi \
               -s /usr/sbin/nologin -c "gnocchi user" gnocchi \
    && mkdir -p /etc/gnocchi /var/log/gnocchi /var/lib/gnocchi /var/cache/gnocchi \
    && chown gnocchi:gnocchi \
         /etc/gnocchi /var/log/gnocchi /var/lib/gnocchi /var/cache/gnocchi
