# syntax=docker/dockerfile:1
ARG FROM=public.ecr.aws/ubuntu/ubuntu:noble

ARG UV_IMAGE_VERSION=latest
FROM ghcr.io/astral-sh/uv:${UV_IMAGE_VERSION} AS uv

FROM ${FROM}

ENV PATH=/var/lib/openstack/bin:$PATH
ENV LANG=C.UTF-8

ARG REQUIREMENTS_REF=master

# As of setuptools 82.0.0 (released 2026-02-08), pkg_resources was removed.
# Not needed since 2026.1.
ARG SETUPTOOLS_CONSTRAINT="<81"

# apt has no network timeout by default, so a stalled connection to a mirror
# hangs the build until the job times out. Fail fast and retry instead.
RUN printf 'Acquire::http::Timeout "30";\nAcquire::https::Timeout "30";\nAcquire::Retries "3";\n' > /etc/apt/apt.conf.d/99-timeout

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
         bind9-host \
         build-essential \
         ca-certificates \
         git \
         gnupg2 \
         libblas-dev \
         liberasurecode-dev \
         libffi-dev \
         libjpeg-dev \
         libkrb5-dev \
         liblapack-dev \
         libldap2-dev \
         libmysqlclient-dev \
         libnss3-dev \
         libpq-dev \
         librdkafka-dev \
         libsasl2-dev \
         libssl-dev \
         libsystemd-dev \
         libvirt-dev \
         libxml2-dev \
         libxslt1-dev \
         libyaml-dev \
         libz-dev \
         lsb-release \
         netbase \
         patch \
         pkg-config \
         python3 \
         python3-dev \
         python3-venv \
         sudo \
         wget \
    && rm -rf /var/lib/apt/lists/*

# PCRE1 was dropped after Noble in favour of PCRE2, so install whichever
# development package this release carries.
#
# Note: no interpreter is given after <<EOF on purpose. Naming one makes
# BuildKit wrap the whole block in an outer `/bin/sh -c` heredoc, which expands
# ${...} before the inner shell runs, so variables set in here come out empty.
RUN <<EOF
  set -xe
  . /etc/os-release
  if [ "${VERSION_CODENAME}" = "noble" ]; then
    PCRE_DEV=libpcre3-dev
  else
    PCRE_DEV=libpcre2-dev
  fi
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ${PCRE_DEV}
  rm -rf /var/lib/apt/lists/*
EOF

# install uv from container image
COPY --from=uv /uv /uvx /bin/

# create virtualenv
RUN uv venv --system-site-packages /var/lib/openstack

# Map REQUIREMENTS_REF to version for constraints URL
# stable/2025.2 -> 2025.2, stable/2026.1 -> 2026.1, stable/2026.2 -> 2026.2, master -> master
RUN <<EOF bash -xe
wget -q -O /upper-constraints.txt "https://releases.openstack.org/constraints/upper/$(echo ${REQUIREMENTS_REF} | sed 's/stable\///')"
if [ -n "${SETUPTOOLS_CONSTRAINT}" ]; then echo "setuptools${SETUPTOOLS_CONSTRAINT}" >> /upper-constraints.txt; fi
EOF

# Optional: replace oslo.messaging with a build from another repository
# (a fork carrying fixes not yet released upstream). Every service image is
# built FROM this one and installs with `-c /upper-constraints.txt`, so the
# replacement reaches all of them with no per-service change: the wheel is
# built here, the constraint is pinned to its version, and UV_FIND_LINKS
# makes `uv pip install` find it. Empty OSLO_MESSAGING_REF (the default)
# skips this and leaves the image as upstream builds it.
#
# The version is the nearest upstream tag plus a PEP 440 local label naming
# the commit (e.g. 18.3.0+g3e0efb5a): it still satisfies every service's
# oslo.messaging requirement, sorts with the release it is based on, and
# `pip freeze` shows exactly which commit is installed. pbr reads the tag
# from the clone, so the repository must carry upstream's tags.
ARG OSLO_MESSAGING_REPO=""
ARG OSLO_MESSAGING_REF=""
RUN mkdir -p /var/lib/openstack-wheels
ENV UV_FIND_LINKS=/var/lib/openstack-wheels
# No interpreter after <<EOF, for the reason given above: this block sets
# variables of its own.
RUN <<EOF
set -xe
if [ -z "${OSLO_MESSAGING_REF}" ]; then exit 0; fi
git clone --filter=blob:none "${OSLO_MESSAGING_REPO}" /tmp/oslo.messaging
git -C /tmp/oslo.messaging checkout --detach "${OSLO_MESSAGING_REF}"
tag=$(git -C /tmp/oslo.messaging describe --tags --abbrev=0)
sha=$(git -C /tmp/oslo.messaging rev-parse --short=8 HEAD)
version="${tag}+g${sha}"
PBR_VERSION="${version}" uv build --wheel --out-dir /var/lib/openstack-wheels /tmp/oslo.messaging
ls /var/lib/openstack-wheels/oslo_messaging-${version}-*.whl
grep -q '^oslo.messaging===' /upper-constraints.txt
sed -i "s|^oslo.messaging===.*|oslo.messaging===${version}|" /upper-constraints.txt
printf '%s %s %s\n' "${version}" "${OSLO_MESSAGING_REPO}" \
  "$(git -C /tmp/oslo.messaging rev-parse HEAD)" > /var/lib/openstack-wheels/oslo.messaging.txt
rm -rf /tmp/oslo.messaging
EOF
