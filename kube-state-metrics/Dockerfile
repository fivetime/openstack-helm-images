# kube-state-metrics for the kube-prometheus-stack release. Built from the
# fivetime fork: upstream v2.20.0 plus kube_daemonset_spec_update_strategy
# (kubernetes/kube-state-metrics#3186), which lets KubeDaemonSetRolloutStuck
# skip OnDelete DaemonSets (kubernetes-sigs/kubernetes-mixin#1318). Drop this
# image once an upstream release carries the metric.
ARG GOLANG_VERSION=1.26
FROM docker.io/library/golang:${GOLANG_VERSION} AS build
ARG KUBE_STATE_METRICS_REPO=https://github.com/fivetime/kube-state-metrics.git
ARG KUBE_STATE_METRICS_REF=1f1aa3cc20c90ff005c5950d43c774432321189d
RUN git init /src && git -C /src remote add origin "${KUBE_STATE_METRICS_REPO}" \
 && git -C /src fetch --depth=1 origin "${KUBE_STATE_METRICS_REF}" \
 && git -C /src checkout --detach FETCH_HEAD
WORKDIR /src
# make build-local stamps the version from VERSION and the commit from git,
# like the upstream image.
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    make build-local \
 && ./kube-state-metrics version 2>&1 | grep -q "revision: $(git rev-parse --short HEAD)" \
 && mkdir -p /out/etc/image_info && echo "${KUBE_STATE_METRICS_REF}" > /out/etc/image_info/kube-state-metrics.txt

FROM gcr.io/distroless/static-debian13:latest
COPY --from=build /src/kube-state-metrics /
COPY --from=build /out/etc/image_info /etc/image_info
USER nobody
ENTRYPOINT ["/kube-state-metrics", "--port=8080", "--telemetry-port=8081"]
EXPOSE 8080 8081
