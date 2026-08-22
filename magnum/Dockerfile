# syntax=docker/dockerfile:1
ARG BASE_VENV_BUILDER=quay.io/airshipit/venv_builder:2025.2-ubuntu_noble
ARG BASE_RUNTIME=quay.io/airshipit/base:2025.2-ubuntu_noble
FROM ${BASE_VENV_BUILDER} AS build

ENV PATH=/var/lib/openstack/bin:$PATH

ARG MAGNUM_REPO=https://opendev.org/openstack/magnum
ARG MAGNUM_REF=stable/2026.1
# Cluster API driver for Magnum (vexxhost). Published as cp38-abi3 manylinux
# wheels with the Rust extension precompiled, so no cargo toolchain needed.
ARG MAGNUM_CLUSTER_API_VERSION=0.38.1
ARG PROFILES=""

# Use bindep to determine packages needed for this profile set
COPY bindep.txt pydep.txt /opt/
RUN mkdir -p /etc/image_info && \
    uvx bindep -f /opt/bindep.txt -b -l newline magnum ${PROFILES} > /etc/image_info/bindep_runtime.txt && \
    uvx bindep -f /opt/bindep.txt -b -l newline magnum build ${PROFILES} > /etc/image_info/bindep_build.txt && \
    uvx bindep -f /opt/pydep.txt -b -l newline magnum ${PROFILES} > /etc/image_info/python_packages.txt

RUN if [ -s /etc/image_info/bindep_build.txt ]; then \
        apt-get update \
        && DEBIAN_FRONTEND=noninteractive xargs --no-run-if-empty apt-get install -y --no-install-recommends < /etc/image_info/bindep_build.txt \
        && rm -rf /var/lib/apt/lists/*; \
    fi

RUN sed -i '/^magnum===/d;/^magnum-cluster-api===/d' /upper-constraints.txt \
    && git clone --filter=blob:none -b ${MAGNUM_REF} ${MAGNUM_REPO} /tmp/magnum \
    && uv pip install \
         --build-constraint /upper-constraints.txt \
         -c /upper-constraints.txt \
         -r /etc/image_info/python_packages.txt \
         /tmp/magnum \
         magnum-cluster-api==${MAGNUM_CLUSTER_API_VERSION} \
         'setuptools<81' \
    && git -C /tmp/magnum log --oneline -1 > /etc/image_info/project.txt \
    && echo "magnum-cluster-api ${MAGNUM_CLUSTER_API_VERSION}" >> /etc/image_info/project.txt \
    && rm -rf /tmp/magnum \
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

# magnum-cluster-api shells out to `helm` to install its in-cluster addon
# charts (cilium, CCM, cinder/manila CSI, autoscaler), so the binary has to
# be in the runtime image -- upstream's own image does the same.
# NOTE: ARG scope is per-stage; a redeclaration without a default resolves to
# the empty string, which silently turns the download URL into a 404.
ARG HELM_VERSION=v3.19.4
ARG TARGETARCH
RUN curl -fsSL "https://get.helm.sh/helm-${HELM_VERSION}-linux-${TARGETARCH}.tar.gz" \
        -o /tmp/helm.tgz \
    && tar -xzf /tmp/helm.tgz -C /tmp \
    && install -o root -g root -m 0755 "/tmp/linux-${TARGETARCH}/helm" /usr/local/bin/helm \
    && rm -rf /tmp/helm.tgz "/tmp/linux-${TARGETARCH}" \
    && helm version --short >> /etc/image_info/project.txt

# magnum-cluster-api ships the cinder/manila CSI charts with hostNetwork (and a
# node DNS policy) only on the *node* plugins. The controller plugins keep the
# default ClusterFirst policy, so they resolve through the workload cluster's own
# CoreDNS -- which is authoritative for cluster.local and never forwards upstream.
# An OpenStack endpoint published under *.svc.cluster.local is therefore NXDOMAIN
# for them, and cinder-csi-controllerplugin crash-loops on GetOpenStackProvider.
# "Default" here means the node's resolv.conf, which does resolve those names.
# The greps make a missed anchor fail the build instead of shipping a silently
# unpatched image.
RUN set -eu; \
    cinder=$(find /var/lib/openstack -path '*/magnum_cluster_api/charts/openstack-cinder-csi/templates/controllerplugin-deployment.yaml'); \
    manila=$(find /var/lib/openstack -path '*/magnum_cluster_api/charts/openstack-manila-csi/templates/controllerplugin-statefulset.yaml'); \
    test -n "$cinder" && test -n "$manila"; \
    grep -q '^      dnsPolicy:' "$cinder" && { echo "cinder chart already sets dnsPolicy; review patch" >&2; exit 1; } || true; \
    sed -i '/^      serviceAccount: csi-cinder-controller-sa$/a\      dnsPolicy: Default' "$cinder"; \
    sed -i '/^      serviceAccountName: {{ include "openstack-manila-csi.serviceAccountName.controllerplugin" . }}$/a\      dnsPolicy: Default' "$manila"; \
    grep -q '^      dnsPolicy: Default$' "$cinder"; \
    grep -q '^      dnsPolicy: Default$' "$manila"; \
    echo "csi controllerplugin dnsPolicy patched" >> /etc/image_info/project.txt

RUN find /var/lib/openstack \( -name "*.pyc" -o -name "__pycache__" \) -delete \
    && rm -rf /tmp/* /root/.cache /etc/machine-id

RUN groupadd -g 42424 magnum \
    && useradd -u 42424 -g 42424 -M -d /var/lib/magnum \
               -s /usr/sbin/nologin -c "magnum user" magnum \
    && mkdir -p /etc/magnum /var/log/magnum /var/lib/magnum /var/cache/magnum \
    && chown magnum:magnum \
         /etc/magnum /var/log/magnum /var/lib/magnum /var/cache/magnum
