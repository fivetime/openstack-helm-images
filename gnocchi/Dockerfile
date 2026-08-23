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

RUN groupadd -g 42426 gnocchi \
    && useradd -u 42426 -g 42426 -M -d /var/lib/gnocchi \
               -s /usr/sbin/nologin -c "gnocchi user" gnocchi \
    && mkdir -p /etc/gnocchi /var/log/gnocchi /var/lib/gnocchi /var/cache/gnocchi \
    && chown gnocchi:gnocchi \
         /etc/gnocchi /var/log/gnocchi /var/lib/gnocchi /var/cache/gnocchi
