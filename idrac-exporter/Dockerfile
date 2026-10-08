# Redfish exporter for server BMCs (HPE iLO, Dell iDRAC, Fujitsu iRMC,
# Lenovo XClarity, Supermicro, ...). Built from the fivetime fork of
# mrlhansen/idrac_exporter, which adds the sensor PhysicalContext and the
# BMC's own temperature thresholds (idrac_sensors_temperature_info /
# _threshold) so alerts do not depend on vendor sensor names.
ARG GOLANG_VERSION=1.26
ARG ALPINE_VERSION=3.22
FROM docker.io/library/golang:${GOLANG_VERSION}-alpine AS build
ARG IDRAC_EXPORTER_REPO=https://github.com/fivetime/idrac_exporter.git
ARG IDRAC_EXPORTER_REF=046cd0ec55f8467291b99484e32a1bb51892bfdb
ARG IDRAC_EXPORTER_VERSION=2.6.3-fivetime
RUN apk add --no-cache git \
 && git init /src && git -C /src remote add origin "${IDRAC_EXPORTER_REPO}" \
 && git -C /src fetch --depth=1 origin "${IDRAC_EXPORTER_REF}" \
 && git -C /src checkout --detach FETCH_HEAD
WORKDIR /src
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 go build -trimpath \
      -ldflags "-s -w -X github.com/mrlhansen/idrac_exporter/internal/version.Version=${IDRAC_EXPORTER_VERSION} -X github.com/mrlhansen/idrac_exporter/internal/version.Revision=${IDRAC_EXPORTER_REF}" \
      -o /out/idrac_exporter ./cmd/idrac_exporter

FROM docker.io/library/alpine:${ALPINE_VERSION}
ARG IDRAC_EXPORTER_REF
RUN apk add --no-cache ca-certificates tzdata \
 && mkdir -p /etc/image_info && echo "${IDRAC_EXPORTER_REF}" > /etc/image_info/idrac_exporter.txt
COPY --from=build /out/idrac_exporter /usr/local/bin/idrac_exporter
# Fails the build if the binary does not run or was built from another commit.
RUN /usr/local/bin/idrac_exporter -version | grep -qx "revision: ${IDRAC_EXPORTER_REF}"
USER 65534:65534
EXPOSE 9348
ENTRYPOINT ["/usr/local/bin/idrac_exporter"]
