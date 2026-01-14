ARG FROM=quay.io/airshipit/keystone:2025.2-ubuntu_noble
FROM ${FROM}

LABEL maintainer="OpenStack-Helm Authors"
LABEL description="Keystone with PostgreSQL support (psycopg2)"

USER root

RUN set -x \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        python3-psycopg2 \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

USER keystone
