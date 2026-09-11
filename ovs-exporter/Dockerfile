# Prometheus exporter for Open vSwitch (datapath, interfaces, tunnel BFD,
# ovn-controller liveness). Built from the fivetime fork, which adds BFD
# alerts and skips unset log file paths for containerized OVS.
ARG GOLANG_VERSION=1.26
ARG ALPINE_VERSION=3.22
FROM docker.io/library/golang:${GOLANG_VERSION}-alpine AS build
ARG OVS_EXPORTER_REPO=https://github.com/fivetime/ovs_exporter.git
ARG OVS_EXPORTER_REF=451d360dab8c76fa01c0c511102e3d42e16a0a92
RUN apk add --no-cache git \
 && git init /src && git -C /src remote add origin "${OVS_EXPORTER_REPO}" \
 && git -C /src fetch --depth=1 origin "${OVS_EXPORTER_REF}" \
 && git -C /src checkout --detach FETCH_HEAD
WORKDIR /src
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 go build -trimpath -ldflags "-s -w" -o /out/ovs_exporter ./cmd/ovs_exporter

FROM docker.io/library/alpine:${ALPINE_VERSION}
ARG OVS_EXPORTER_REF
RUN apk add --no-cache ca-certificates tzdata \
 && mkdir -p /etc/image_info && echo "${OVS_EXPORTER_REF}" > /etc/image_info/ovs_exporter.txt
COPY --from=build /out/ovs_exporter /usr/local/bin/ovs_exporter
# Fails the build if the binary does not run.
RUN /usr/local/bin/ovs_exporter -version | grep -q '^ovs-exporter'
EXPOSE 9475
ENTRYPOINT ["/usr/local/bin/ovs_exporter"]
