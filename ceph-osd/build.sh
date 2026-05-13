#!/bin/bash
set -ex

# Ceph 版本配置
CEPH_RELEASE=${CEPH_RELEASE:-"reef"}  # 或 quincy, pacific 等
CEPH_RELEASE_TAG=${CEPH_RELEASE_TAG:-"18.2.1-1noble"}  # 根据实际版本调整
CEPH_REPO=${CEPH_REPO:-"https://download.ceph.com/debian-${CEPH_RELEASE}"}
CEPH_KEY=${CEPH_KEY:-"https://download.ceph.com/keys/release.asc"}

# 镜像配置
IMAGE_NAME=${IMAGE_NAME:-"ceph-osd"}
IMAGE_TAG=${IMAGE_TAG:-"noble-${CEPH_RELEASE}"}
REGISTRY=${REGISTRY:-"your-registry.com"}

docker build \
    --build-arg CEPH_RELEASE=${CEPH_RELEASE} \
    --build-arg CEPH_RELEASE_TAG=${CEPH_RELEASE_TAG} \
    --build-arg CEPH_REPO=${CEPH_REPO} \
    --build-arg CEPH_KEY=${CEPH_KEY} \
    -t ${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG} \
    -f Dockerfile .

# 可选：推送到镜像仓库
# docker push ${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}