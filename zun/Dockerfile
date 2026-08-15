# syntax=docker/dockerfile:1
ARG BASE_VENV_BUILDER=quay.io/airshipit/venv_builder:2025.2-ubuntu_noble
ARG BASE_RUNTIME=quay.io/airshipit/base:2025.2-ubuntu_noble
FROM ${BASE_VENV_BUILDER} AS build

ENV PATH=/var/lib/openstack/bin:$PATH

ARG ZUN_REPO=https://opendev.org/openstack/zun
ARG ZUN_REF=stable/2026.1
ARG PROFILES=""

# Use bindep to determine packages needed for this profile set
COPY bindep.txt pydep.txt /opt/
RUN mkdir -p /etc/image_info && \
    uvx bindep -f /opt/bindep.txt -b -l newline zun ${PROFILES} > /etc/image_info/bindep_runtime.txt && \
    uvx bindep -f /opt/bindep.txt -b -l newline zun build ${PROFILES} > /etc/image_info/bindep_build.txt && \
    uvx bindep -f /opt/pydep.txt -b -l newline zun ${PROFILES} > /etc/image_info/python_packages.txt

RUN if [ -s /etc/image_info/bindep_build.txt ]; then \
        apt-get update \
        && DEBIAN_FRONTEND=noninteractive xargs --no-run-if-empty apt-get install -y --no-install-recommends < /etc/image_info/bindep_build.txt \
        && rm -rf /var/lib/apt/lists/*; \
    fi

RUN sed -i '/^zun===/d' /upper-constraints.txt \
    && git clone --filter=blob:none -b ${ZUN_REF} ${ZUN_REPO} /tmp/zun \
    && uv pip install \
         --build-constraint /upper-constraints.txt \
         -c /upper-constraints.txt \
         -r /etc/image_info/python_packages.txt \
         /tmp/zun \
    # fork master 的 CRI stub 由新工具链生成:api_pb2.py 要 protobuf runtime
    # >= gencode 7.35.1,api_pb2_grpc.py 要 grpcio>=1.83.0;upper-constraints
    # 钉的旧版会在驱动插件 import 时直接崩死(VersionError/RuntimeError),
    # 故这两个包脱离 constraints 单独升级
    && uv pip install 'protobuf>=7.35.1' 'grpcio>=1.83.0' \
    && git -C /tmp/zun log --oneline -1 > /etc/image_info/project.txt \
    && rm -rf /tmp/zun \
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

RUN groupadd -g 42424 zun \
    && useradd -u 42424 -g 42424 -M -d /var/lib/zun \
               -s /usr/sbin/nologin -c "zun user" zun \
    && mkdir -p /etc/zun /var/log/zun /var/lib/zun /var/cache/zun \
    && chown zun:zun \
         /etc/zun /var/log/zun /var/lib/zun /var/cache/zun
