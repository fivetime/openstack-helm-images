# syntax=docker/dockerfile:1
ARG BASE_VENV_BUILDER=quay.io/airshipit/venv_builder:2025.2-ubuntu_noble
ARG BASE_RUNTIME=quay.io/airshipit/base:2025.2-ubuntu_noble
FROM ${BASE_VENV_BUILDER} AS build

ENV PATH=/var/lib/openstack/bin:$PATH

ARG MISTRAL_REPO=https://opendev.org/openstack/mistral
ARG MISTRAL_REF=stable/2026.1
# mistral-extra delivers the OpenStack actions (nova.*, glance.*, ...);
# split out of the mistral tree since 2023.1, so without it the image only
# has the std.* actions. It is versioned alongside mistral, so its ref
# follows MISTRAL_REF instead of carrying a default of its own: a hardcoded
# default silently pairs one release of mistral with another release of
# mistral-extra for every cell that does not override it, which is what
# happened to the 2026.2 cell the moment upstream added it.
#
# This holds as long as the ref names a branch that exists in opendev's
# mistral-extra too. The 2026.1 cell passes MISTRAL_REF=master and pairs with
# mistral-extra master, and the opendev cells pass stable/<release>. A ref
# that mistral-extra does not carry must pass MISTRAL_EXTRA_REF explicitly
# (the 2026.2 cell passes the mistral-extra fork's own fivetime/stable/2026.2,
# which has the Senlin actions); an explicit value still wins.
ARG MISTRAL_EXTRA_REPO=https://opendev.org/openstack/mistral-extra
ARG MISTRAL_EXTRA_REF=${MISTRAL_REF}
# The Murano actions of mistral-extra need python-muranoclient, and it needs
# murano-pkg-check; both are retired and their last releases on PyPI do not
# install with 2026.2, so a cell whose mistral-extra has the Murano actions
# installs the forks' (the same as the murano image). Empty refs install
# neither. The forks are private: the refs are tags, not branches watched
# through the API.
ARG MURANOCLIENT_REPO=https://github.com/fivetime/python-muranoclient
ARG MURANOCLIENT_REF=
ARG MURANOPKGCHECK_REPO=https://github.com/fivetime/murano-pkg-check
ARG MURANOPKGCHECK_REF=
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
# gets its layer reused and quietly builds yesterday's code. When the branch
# moves, this ref file changes and the clone layer rebuilds (which also
# refreshes mistral-extra).
#
# The default tracks the fork's master, which the 2026.1 cell builds. A cell
# that builds another fork branch passes the ref URL for that branch, or it
# would only rebuild when master happens to move.
ARG MISTRAL_REF_URL=https://api.github.com/repos/fivetime/openstack-mistral/git/refs/heads/master
ADD ${MISTRAL_REF_URL} /tmp/mistral.ref
# The same for a cell that builds mistral-extra from a fork branch; by
# default it repeats the mistral ref.
ARG MISTRAL_EXTRA_REF_URL=${MISTRAL_REF_URL}
ADD ${MISTRAL_EXTRA_REF_URL} /tmp/mistral-extra.ref

# CI supplies src_repo_token as a BuildKit secret for the private murano
# forks; the token and the temporary git rewrite live only inside this RUN
# and never reach an image layer. Full (blobless) clones: pbr computes the
# versions from the tags.
RUN --mount=type=secret,id=src_repo_token \
    sed -i '/^mistral===/d;/^mistral-extra===/d' /upper-constraints.txt \
    && git clone --filter=blob:none -b ${MISTRAL_REF} ${MISTRAL_REPO} /tmp/mistral \
    && git clone --filter=blob:none -b ${MISTRAL_EXTRA_REF} ${MISTRAL_EXTRA_REPO} /tmp/mistral-extra \
    && murano_pkgs="" \
    && if [ -n "${MURANOCLIENT_REF}" ]; then \
         if [ -s /run/secrets/src_repo_token ]; then \
           token="$(cat /run/secrets/src_repo_token)"; \
           git config --global \
             url."https://x-access-token:${token}@github.com/".insteadOf \
             "https://github.com/"; \
         fi \
         && git clone --filter=blob:none ${MURANOCLIENT_REPO} /tmp/muranoclient \
         && git clone --filter=blob:none ${MURANOPKGCHECK_REPO} /tmp/muranopkgcheck \
         # Still authenticated: a blobless checkout fetches the blobs it needs.
         && git -C /tmp/muranoclient checkout --detach ${MURANOCLIENT_REF} \
         && git -C /tmp/muranopkgcheck checkout --detach ${MURANOPKGCHECK_REF} \
         && rm -f /root/.gitconfig \
         && sed -i '/^python-muranoclient===/d;/^murano-pkg-check===/d' /upper-constraints.txt \
         && murano_pkgs="/tmp/muranoclient /tmp/muranopkgcheck"; \
       fi \
    && uv pip install \
         --build-constraint /upper-constraints.txt \
         -c /upper-constraints.txt \
         -r /etc/image_info/python_packages.txt \
         /tmp/mistral /tmp/mistral-extra ${murano_pkgs} \
    && echo "mistral ${MISTRAL_REF} (${MISTRAL_REPO})" > /etc/image_info/project.txt \
    && git -C /tmp/mistral log --oneline -1 >> /etc/image_info/project.txt \
    && echo "mistral-extra ${MISTRAL_EXTRA_REF} (${MISTRAL_EXTRA_REPO})" >> /etc/image_info/project.txt \
    && git -C /tmp/mistral-extra log --oneline -1 >> /etc/image_info/project.txt \
    && if [ -n "${murano_pkgs}" ]; then \
         git -C /tmp/muranoclient log --oneline -1 >> /etc/image_info/project.txt \
         && git -C /tmp/muranopkgcheck log --oneline -1 >> /etc/image_info/project.txt; \
       fi \
    && rm -rf /tmp/mistral /tmp/mistral-extra /tmp/muranoclient /tmp/muranopkgcheck \
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
