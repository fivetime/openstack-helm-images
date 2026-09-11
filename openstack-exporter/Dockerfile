# openstack-exporter for Prometheus. Built from the fivetime fork, which
# tolerates the legacy Nova security groups endpoint being gone and string
# typed cpu_info fields (nova-incus) in the hypervisor listing.
ARG GOLANG_VERSION=1.26
ARG ALPINE_VERSION=3.22
FROM docker.io/library/golang:${GOLANG_VERSION}-alpine AS build
ARG OPENSTACK_EXPORTER_REPO=https://github.com/fivetime/openstack-exporter.git
ARG OPENSTACK_EXPORTER_REF=3a618e3477808360a09a398a418d51a93c617179
RUN apk add --no-cache git \
 && git init /src && git -C /src remote add origin "${OPENSTACK_EXPORTER_REPO}" \
 && git -C /src fetch --depth=1 origin "${OPENSTACK_EXPORTER_REF}" \
 && git -C /src checkout --detach FETCH_HEAD
WORKDIR /src
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 go build -trimpath \
      -ldflags "-s -w -X github.com/prometheus/common/version.Revision=${OPENSTACK_EXPORTER_REF}" \
      -o /out/openstack-exporter .

FROM docker.io/library/alpine:${ALPINE_VERSION}
ARG OPENSTACK_EXPORTER_REF
RUN apk add --no-cache ca-certificates tzdata \
 && mkdir -p /etc/image_info && echo "${OPENSTACK_EXPORTER_REF}" > /etc/image_info/openstack-exporter.txt \
 && adduser -D -u 65534 -H -h /nonexistent exporter 2>/dev/null || true
# The OpenStack-Helm chart runs /bin/openstack-exporter, like the upstream image.
COPY --from=build /out/openstack-exporter /bin/openstack-exporter
# Fails the build if the binary does not run or was built from another commit.
RUN /bin/openstack-exporter --version 2>&1 | grep -q "revision: ${OPENSTACK_EXPORTER_REF}"
EXPOSE 9180
ENTRYPOINT ["/bin/openstack-exporter"]
