# syntax=docker/dockerfile:1
ARG BASE_VENV_BUILDER=quay.io/airshipit/venv_builder:2025.2-ubuntu_noble
ARG BASE_RUNTIME=quay.io/airshipit/base:2025.2-ubuntu_noble
ARG NODE_IMAGE=docker.io/library/node:24-trixie-slim

# -----------------------------------------------------------------------------
# Fork-only console-build stage: yarn build skyline-console's JS bundles.
#
# skyline-console ships only a Python wrapper in its sdist; the JS/CSS bundles
# under skyline_console/static/ are produced by `yarn build` from src/.
# Upstream's flattened Dockerfile relies on `uv pip install /tmp/skyline-console`
# producing the bundles via pbr -- which does not run yarn -- so we rebuild
# them explicitly here and inject the result before the python install step.
#
# --platform=$BUILDPLATFORM pins this stage to the buildx host arch (amd64
# in our self-hosted runners). JS bundles are architecture-independent, so
# running yarn natively on amd64 and COPYing the output into both amd64 and
# arm64 final images is correct -- and ~10x faster than letting QEMU emulate
# arm64 yarn (which previously took ~3 hours and hit the 180-minute timeout).
# -----------------------------------------------------------------------------
FROM --platform=$BUILDPLATFORM ${NODE_IMAGE} AS console-build

ARG SKYLINE_CONSOLE_REPO=https://github.com/openstack/skyline-console
ARG SKYLINE_CONSOLE_REF=stable/2026.1

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src/skyline-console
RUN git clone --depth 1 --branch "${SKYLINE_CONSOLE_REF}" \
        "${SKYLINE_CONSOLE_REPO}" . \
    || (git clone "${SKYLINE_CONSOLE_REPO}" . \
        && git checkout "${SKYLINE_CONSOLE_REF}")

# Fork-only patches, see the skyline-apiserver step below for the layout.
COPY skyline/patches/ /tmp/patches/
RUN ref="$(echo "${SKYLINE_CONSOLE_REF}" | tr / -)" \
    && for p in /tmp/patches/skyline-console/*.patch \
                "/tmp/patches/skyline-console/${ref}"/*.patch; do \
         [ -e "$p" ] || continue; \
         git apply "$p" || exit 1; \
         echo "skyline-console patch ${p#/tmp/patches/skyline-console/}" \
           >> /src/skyline-console/.fork-patches; \
       done

RUN corepack enable \
    && yarn install --frozen-lockfile --network-timeout 600000 \
    && NODE_OPTIONS=--max-old-space-size=2048 yarn run build

RUN test -d /src/skyline-console/skyline_console/static \
    && ls /src/skyline-console/skyline_console/static/*.bundle.*.js >/dev/null \
    || (echo "ERROR: yarn build did not produce skyline_console/static bundles" >&2; exit 1)

# -----------------------------------------------------------------------------
# Upstream build stage: install Python packages.
# Diverges from upstream by replacing the skyline-console git clone with
# the pre-built tree from console-build above.
# -----------------------------------------------------------------------------
FROM ${BASE_VENV_BUILDER} AS build

ENV PATH=/var/lib/openstack/bin:$PATH

ARG SKYLINE_APISERVER_REPO=https://opendev.org/openstack/skyline-apiserver
ARG SKYLINE_APISERVER_REF=stable/2026.1
ARG PROFILES=""

# Use bindep to determine packages needed for this profile set
COPY bindep.txt pydep.txt /opt/
RUN mkdir -p /etc/image_info && \
    uvx bindep -f /opt/bindep.txt -b -l newline skyline ${PROFILES} > /etc/image_info/bindep_runtime.txt && \
    uvx bindep -f /opt/bindep.txt -b -l newline skyline build ${PROFILES} > /etc/image_info/bindep_build.txt && \
    uvx bindep -f /opt/pydep.txt -b -l newline skyline ${PROFILES} > /etc/image_info/python_packages.txt

RUN if [ -s /etc/image_info/bindep_build.txt ]; then \
        apt-get update \
        && DEBIAN_FRONTEND=noninteractive xargs --no-run-if-empty apt-get install -y --no-install-recommends < /etc/image_info/bindep_build.txt \
        && rm -rf /var/lib/apt/lists/*; \
    fi

# skyline-console source tree with bundles already built
COPY --from=console-build /src/skyline-console /tmp/skyline-console

# Fork-only: fixes not yet merged upstream, as git format-patch files.
# patches/<project>/*.patch apply to every branch built,
# patches/<project>/<ref with / as ->/*.patch only to that one (a fix for
# code a branch does not have would not apply there). Each is applied with
# `git apply` right after the clone and listed in /etc/image_info/patches.txt;
# one that does not apply fails the build, so a fix that landed upstream is
# noticed. Drop a patch once its change is in the branch built.
COPY skyline/patches/ /tmp/patches/

RUN sed -i '/^skyline-apiserver===/d' /upper-constraints.txt \
    && git clone --filter=blob:none -b ${SKYLINE_APISERVER_REF} ${SKYLINE_APISERVER_REPO} /tmp/skyline-apiserver \
    && ref="$(echo "${SKYLINE_APISERVER_REF}" | tr / -)" \
    && for p in /tmp/patches/skyline-apiserver/*.patch \
                "/tmp/patches/skyline-apiserver/${ref}"/*.patch; do \
         [ -e "$p" ] || continue; \
         git -C /tmp/skyline-apiserver apply "$p" || exit 1; \
         echo "skyline-apiserver patch ${p#/tmp/patches/skyline-apiserver/}" >> /etc/image_info/patches.txt; \
       done \
    && if [ -f /tmp/skyline-console/.fork-patches ]; then \
         cat /tmp/skyline-console/.fork-patches >> /etc/image_info/patches.txt; \
       fi \
    && uv pip install \
         --build-constraint /upper-constraints.txt \
         -c /upper-constraints.txt \
         -r /etc/image_info/python_packages.txt \
         /tmp/skyline-apiserver \
         /tmp/skyline-console \
    && git -C /tmp/skyline-apiserver log --oneline -1 > /etc/image_info/project.txt \
    && rm -rf /tmp/skyline-apiserver /tmp/skyline-console \
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

RUN groupadd -g 42424 skyline \
    && useradd -u 42424 -g 42424 -M -d /var/lib/skyline \
               -s /usr/sbin/nologin -c "skyline user" skyline \
    && mkdir -p /etc/skyline /var/log/skyline /var/lib/skyline /var/cache/skyline \
    && chown skyline:skyline \
         /etc/skyline /var/log/skyline /var/lib/skyline /var/cache/skyline
