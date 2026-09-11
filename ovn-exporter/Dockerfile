# Prometheus exporter for OVN. Built from the fivetime fork, which adds
# -collector.components/-collector.topology so a remote, topology-only
# exporter does not report the local daemons as down.
ARG GOLANG_VERSION=1.26
ARG ALPINE_VERSION=3.22
FROM docker.io/library/golang:${GOLANG_VERSION}-alpine AS build
ARG OVN_EXPORTER_REPO=https://github.com/fivetime/ovn_exporter.git
ARG OVN_EXPORTER_REF=37a6c153dc42412b1fa1c9e89d88aad31f425c47
RUN apk add --no-cache git \
 && git init /src && git -C /src remote add origin "${OVN_EXPORTER_REPO}" \
 && git -C /src fetch --depth=1 origin "${OVN_EXPORTER_REF}" \
 && git -C /src checkout --detach FETCH_HEAD
WORKDIR /src
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 go build -trimpath -ldflags "-s -w" -o /out/ovn_exporter ./cmd/ovn_exporter

FROM docker.io/library/alpine:${ALPINE_VERSION}
ARG OVN_EXPORTER_REF
RUN apk add --no-cache ca-certificates tzdata \
 && mkdir -p /etc/image_info && echo "${OVN_EXPORTER_REF}" > /etc/image_info/ovn_exporter.txt
COPY --from=build /out/ovn_exporter /usr/local/bin/ovn_exporter
# Fails the build if the binary does not run or is not the fork build
# (upstream has no collector switches).
RUN /usr/local/bin/ovn_exporter -h 2>&1 | grep -q -- '-collector.components'
EXPOSE 9476
ENTRYPOINT ["/usr/local/bin/ovn_exporter"]
