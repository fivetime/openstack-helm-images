# syntax=docker/dockerfile:1
ARG BASE_VENV_BUILDER=quay.io/airshipit/venv_builder:2025.2-ubuntu_noble
ARG BASE_RUNTIME=quay.io/airshipit/base:2025.2-ubuntu_noble
FROM ${BASE_VENV_BUILDER} AS build

ENV PATH=/var/lib/openstack/bin:$PATH

ARG MISTRAL_REPO=https://opendev.org/openstack/mistral
ARG MISTRAL_REF=stable/2026.1
# mistral-extra delivers the OpenStack actions (nova.*, glance.*, ...);
# split out of the mistral tree since 2023.1, so without it the image only
# has the std.* actions.
ARG MISTRAL_EXTRA_REPO=https://opendev.org/openstack/mistral-extra
ARG MISTRAL_EXTRA_REF=stable/2026.1
ARG PROFILES="fluent apache"

# Use bindep to determine packages needed for this profile set
COPY bindep.txt pydep.txt /opt/
RUN mkdir -p /etc/image_info && \
    uvx bindep -f /opt/bindep.txt -b -l newline mistral ${PROFILES} > /etc/image_info/bindep_runtime.txt && \
    uvx bindep -f /opt/bindep.txt -b -l newline mistral build ${PROFILES} > /etc/image_info/bindep_build.txt && \
    uvx bindep -f /opt/pydep.txt -b -l newline mistral ${PROFILES} > /etc/image_info/python_packages.txt

RUN if [ -s /etc/image_info/bindep_build.txt ]; then \
        apt-get update \
        && DEBIAN_FRONTEND=noninteractive xargs --no-run-if-empty apt-get install -y --no-install-recommends < /etc/image_info/bindep_build.txt \
        && rm -rf /var/lib/apt/lists/*; \
    fi

# Same reason as zun: a clone of a moving branch inside an unchanging RUN
# gets its layer reused and quietly builds yesterday's code. The 2026.1 cell
# builds from the fivetime fork branch below; when it moves, this ref file
# changes and the clone layer rebuilds (which also refreshes mistral-extra).
ADD https://api.github.com/repos/fivetime/openstack-mistral/git/refs/heads/stable/2026.1 /tmp/mistral.ref

RUN sed -i '/^mistral===/d;/^mistral-extra===/d' /upper-constraints.txt \
    && git clone --filter=blob:none -b ${MISTRAL_REF} ${MISTRAL_REPO} /tmp/mistral \
    && git clone --filter=blob:none -b ${MISTRAL_EXTRA_REF} ${MISTRAL_EXTRA_REPO} /tmp/mistral-extra \
    && uv pip install \
         --build-constraint /upper-constraints.txt \
         -c /upper-constraints.txt \
         -r /etc/image_info/python_packages.txt \
         /tmp/mistral /tmp/mistral-extra \
    && git -C /tmp/mistral log --oneline -1 > /etc/image_info/project.txt \
    && git -C /tmp/mistral-extra log --oneline -1 >> /etc/image_info/project.txt \
    && rm -rf /tmp/mistral /tmp/mistral-extra \
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

RUN groupadd -g 42424 mistral \
    && useradd -u 42424 -g 42424 -M -d /var/lib/mistral \
               -s /usr/sbin/nologin -c "mistral user" mistral \
    && mkdir -p /etc/mistral /var/log/mistral /var/lib/mistral /var/cache/mistral \
    && chown mistral:mistral \
         /etc/mistral /var/log/mistral /var/lib/mistral /var/cache/mistral
