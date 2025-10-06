#!/bin/bash

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -ex

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default values
DISTRO="${DISTRO:-ubuntu_noble}"
PROJECT_REF="${PROJECT_REF:-master}"
REGISTRY="${REGISTRY:-docker.io}"
IMAGE_PREFIX="${IMAGE_PREFIX:-openstackhelm}"
IMAGE_TAG="${IMAGE_TAG:-${PROJECT_REF}-${DISTRO}}"
DOCKERFILE="${SCRIPT_DIR}/Dockerfile.${DISTRO}"

# Check if Dockerfile exists
if [[ ! -f "${DOCKERFILE}" ]]; then
    echo "Error: Dockerfile ${DOCKERFILE} not found"
    exit 1
fi

# Build the image
docker build \
    --network=host \
    --force-rm \
    --pull \
    --no-cache \
    --file "${DOCKERFILE}" \
    --build-arg PROJECT_REF="${PROJECT_REF}" \
    --build-arg http_proxy="${http_proxy}" \
    --build-arg https_proxy="${https_proxy}" \
    --build-arg HTTP_PROXY="${HTTP_PROXY}" \
    --build-arg HTTPS_PROXY="${HTTPS_PROXY}" \
    --build-arg no_proxy="${no_proxy}" \
    --build-arg NO_PROXY="${NO_PROXY}" \
    --tag "${REGISTRY}/${IMAGE_PREFIX}/ovn-bgp-agent:${IMAGE_TAG}" \
    "${SCRIPT_DIR}"

echo "Successfully built: ${REGISTRY}/${IMAGE_PREFIX}/ovn-bgp-agent:${IMAGE_TAG}"

# Optionally push the image
if [[ "${PUSH}" == "true" ]]; then
    docker push "${REGISTRY}/${IMAGE_PREFIX}/ovn-bgp-agent:${IMAGE_TAG}"
    echo "Successfully pushed: ${REGISTRY}/${IMAGE_PREFIX}/ovn-bgp-agent:${IMAGE_TAG}"
fi