#!/bin/bash

set -ex

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default values
DISTRO="${DISTRO:-ubuntu_noble}"
PROJECT_REF="${PROJECT_REF:-master}"
REGISTRY="${REGISTRY:-docker.io}"
IMAGE_PREFIX="${IMAGE_PREFIX:-openstackhelm}"
VARIANT="${VARIANT:-both}"  # standard | ovn | both
PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.python.org/simple}"
PIP_TRUSTED_HOST="${PIP_TRUSTED_HOST:-pypi.python.org}"

DOCKERFILE="${SCRIPT_DIR}/Dockerfile.${DISTRO}"

if [[ ! -f "${DOCKERFILE}" ]]; then
    echo "Error: Dockerfile ${DOCKERFILE} not found"
    exit 1
fi

build_variant() {
    local include_ovn=$1
    local tag_suffix=$2
    local image_tag="${PROJECT_REF}-${DISTRO}${tag_suffix}"

    echo "Building: ${REGISTRY}/${IMAGE_PREFIX}/ovn-bgp-agent:${image_tag}"

    docker build \
        --network=host \
        --force-rm \
        --pull \
        --no-cache \
        --file "${DOCKERFILE}" \
        --build-arg INCLUDE_OVN="${include_ovn}" \
        --build-arg PROJECT_REF="${PROJECT_REF}" \
        --build-arg PIP_INDEX_URL="${PIP_INDEX_URL}" \
        --build-arg PIP_TRUSTED_HOST="${PIP_TRUSTED_HOST}" \
        --build-arg http_proxy="${http_proxy}" \
        --build-arg https_proxy="${https_proxy}" \
        --build-arg HTTP_PROXY="${HTTP_PROXY}" \
        --build-arg HTTPS_PROXY="${HTTPS_PROXY}" \
        --build-arg no_proxy="${no_proxy}" \
        --build-arg NO_PROXY="${NO_PROXY}" \
        --tag "${REGISTRY}/${IMAGE_PREFIX}/ovn-bgp-agent:${image_tag}" \
        "${SCRIPT_DIR}"

    echo "Successfully built: ${REGISTRY}/${IMAGE_PREFIX}/ovn-bgp-agent:${image_tag}"

    if [[ "${PUSH}" == "true" ]]; then
        docker push "${REGISTRY}/${IMAGE_PREFIX}/ovn-bgp-agent:${image_tag}"
        echo "Successfully pushed: ${REGISTRY}/${IMAGE_PREFIX}/ovn-bgp-agent:${image_tag}"
    fi
}

case "$VARIANT" in
    standard)
        build_variant "false" ""
        ;;
    ovn)
        build_variant "true" "-ovn"
        ;;
    both)
        build_variant "false" ""
        build_variant "true" "-ovn"
        ;;
    *)
        echo "Error: Unknown VARIANT=${VARIANT}. Use: standard, ovn, or both"
        exit 1
        ;;
esac