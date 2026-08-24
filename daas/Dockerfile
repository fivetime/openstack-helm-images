# syntax=docker/dockerfile:1
ARG BASE_VENV_BUILDER=quay.io/airshipit/venv_builder:2026.1-ubuntu_noble
ARG BASE_RUNTIME=quay.io/airshipit/base:2026.1-ubuntu_noble
FROM ${BASE_VENV_BUILDER} AS build

ENV PATH=/var/lib/openstack/bin:$PATH

ARG DAAS_REPO=https://github.com/fivetime/openstack-daas
# A commit, not a branch. The repository is private, so the trick used
# for public forks -- fetching the ref through the API so the layer
# changes when the branch moves -- cannot authenticate. Naming the
# commit makes the build reproducible and invalidates the layer by
# itself.
ARG DAAS_REF=1ef82d36060acb6ab2bfb802edccc884eb1d308b
ARG PROFILES=""

COPY bindep.txt pydep.txt /opt/
RUN mkdir -p /etc/image_info && \
    uvx bindep -f /opt/bindep.txt -b -l newline daas ${PROFILES} > /etc/image_info/bindep_runtime.txt && \
    uvx bindep -f /opt/bindep.txt -b -l newline daas build ${PROFILES} > /etc/image_info/bindep_build.txt && \
    uvx bindep -f /opt/pydep.txt -b -l newline daas ${PROFILES} > /etc/image_info/python_packages.txt

RUN if [ -s /etc/image_info/bindep_build.txt ]; then \
        apt-get update \
        && DEBIAN_FRONTEND=noninteractive xargs --no-run-if-empty apt-get install -y --no-install-recommends < /etc/image_info/bindep_build.txt \
        && rm -rf /var/lib/apt/lists/*; \
    fi

# The repository is private. CI supplies src_repo_token as a BuildKit
# secret; the token and the temporary git rewrite live only inside
# this RUN and never reach an image layer.
RUN --mount=type=secret,id=src_repo_token \
    if [ -s /run/secrets/src_repo_token ]; then \
        token="$(cat /run/secrets/src_repo_token)"; \
        git config --global \
          url."https://x-access-token:${token}@github.com/".insteadOf \
          "https://github.com/"; \
    fi \
    && git init /tmp/daas \
    && git -C /tmp/daas remote add origin ${DAAS_REPO} \
    && git -C /tmp/daas fetch --depth=1 --filter=blob:none origin ${DAAS_REF} \
    && git -C /tmp/daas checkout --detach FETCH_HEAD \
    && rm -f /root/.gitconfig \
    && uv pip install \
         --build-constraint /upper-constraints.txt \
         -c /upper-constraints.txt \
         -r /etc/image_info/python_packages.txt \
         /tmp/daas \
    && git -C /tmp/daas log --oneline -1 > /etc/image_info/project.txt \
    && rm -rf /tmp/daas \
    && uv pip freeze > /etc/image_info/pip.txt

FROM ${BASE_RUNTIME} AS runtime

ENV PATH=/var/lib/openstack/bin:$PATH

COPY --from=build --link /var/lib/openstack /var/lib/openstack
COPY --from=build /etc/image_info /etc/image_info
COPY --from=build /upper-constraints.txt /

RUN if [ -s /etc/image_info/bindep_runtime.txt ]; then \
        apt-get update \
        && DEBIAN_FRONTEND=noninteractive xargs --no-run-if-empty apt-get install -y --no-install-recommends < /etc/image_info/bindep_runtime.txt \
        && rm -rf /var/lib/apt/lists/*; \
    fi

RUN find /var/lib/openstack \( -name "*.pyc" -o -name "__pycache__" \) -delete \
    && rm -rf /tmp/* /root/.cache /etc/machine-id

RUN groupadd -g 42430 daas \
    && useradd -u 42430 -g 42430 -M -d /var/lib/daas \
               -s /usr/sbin/nologin -c "daas user" daas \
    && mkdir -p /etc/daas /var/log/daas /var/lib/daas \
    && chown daas:daas /etc/daas /var/log/daas /var/lib/daas

USER daas
