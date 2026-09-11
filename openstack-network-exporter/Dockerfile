# openstack-network-exporter (openstack-k8s-operators) for OVN raft, northd
# and ovn-controller metrics. Upstream ships a UBI image; this builds the
# same source statically on Alpine to match the other exporter images.
ARG GOLANG_VERSION=1.26
ARG ALPINE_VERSION=3.22
FROM docker.io/library/golang:${GOLANG_VERSION}-alpine AS build
ARG NETWORK_EXPORTER_REPO=https://github.com/fivetime/openstack-network-exporter.git
ARG NETWORK_EXPORTER_REF=80735ae4d9573b559af164f4de63cf645381d428
RUN apk add --no-cache git \
 && git init /src && git -C /src remote add origin "${NETWORK_EXPORTER_REPO}" \
 && git -C /src fetch --depth=1 origin "${NETWORK_EXPORTER_REF}" \
 && git -C /src checkout --detach FETCH_HEAD
WORKDIR /src
# go generate writes ovsdb/ovs/model.go from the bundled OVS schema.
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    go generate ./... \
 && CGO_ENABLED=0 go build -trimpath -ldflags "-s -w" -o /out/openstack-network-exporter .

FROM docker.io/library/alpine:${ALPINE_VERSION}
ARG NETWORK_EXPORTER_REF
RUN apk add --no-cache ca-certificates tzdata \
 && mkdir -p /etc/image_info && echo "${NETWORK_EXPORTER_REF}" > /etc/image_info/openstack-network-exporter.txt
COPY --from=build /src/etc/openstack-network-exporter.yaml /etc/openstack-network-exporter.yaml
COPY --from=build /out/openstack-network-exporter /usr/local/bin/openstack-network-exporter
# Fails the build if the binary does not run, lacks the raft collector, or was
# built without the fork's OVSDB reconnect fix and exporter health counters.
RUN /usr/local/bin/openstack-network-exporter -l text | grep -q '^ovn_raft_cluster_term ' \
 && grep -q openstack_network_exporter_ovsdb_reconnects_total /usr/local/bin/openstack-network-exporter
EXPOSE 1981
ENTRYPOINT ["/usr/local/bin/openstack-network-exporter"]
