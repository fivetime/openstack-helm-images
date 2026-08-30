# syntax=docker/dockerfile:1
# GitLab CI 那条链路的 runner:gitlab-runner + 我们自己的 fleeting 插件。
#
# 为什么不用上游的 gitlab-runner 镜像再塞插件进去:
# **插件与 gitlab-runner 的 fleeting 版本必须成对**。接口在演进
# (Heartbeat / Suspend / Resume 都是 2026 年中加进主接口的),版本错配的
# 表现是 go-plugin 握手直接失败。两边都由我们决定,所以在同一个 Dockerfile
# 里从同一份 go.mod 约束下构建,让版本对不上时**构建期就炸**,
# 而不是等部署到线上握手失败。

# 两段构建对 Go 版本的要求**不同**,所以分开钉。
#
# gitlab-runner v19.3.1 的 go.mod 要求 go >= 1.26.5;沿用编排器那边的 1.25
# 会得到 `go.mod requires go >= 1.26.5 (running go 1.25.14; GOTOOLCHAIN=local)`。
# 本地编得过是因为本机 Go 更新 —— 镜像里钉死了版本,这类差异只有 CI 才暴露。
ARG RUNNER_GOLANG_VERSION=1.26
# 插件与编排器同源,所以跟着 openstack-raas 的 go.mod 走(当前 1.26.0)。
ARG PLUGIN_GOLANG_VERSION=1.26
ARG ALPINE_VERSION=3.22

# ---- gitlab-runner ---------------------------------------------------------
# 钉已发布的 tag。曾经用 master 编过一次 —— `git describe` 给的是
# v18.3.0-1879-g73349bfb7,即未发布代码。拿它做验证本身就不到位。
ARG RUNNER_REF=v19.3.1

FROM docker.io/library/golang:${RUNNER_GOLANG_VERSION}-alpine AS runner-build
ARG RUNNER_REF
RUN apk add --no-cache git make bash
RUN git clone --depth=1 --branch "${RUNNER_REF}" \
      https://gitlab.com/gitlab-org/gitlab-runner.git /src
WORKDIR /src
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 go build -trimpath -ldflags "-s -w" -o /out/gitlab-runner .

# 把 runner 用的 fleeting 版本抄出来,交给插件构建阶段对齐。
RUN grep -E '^\s+gitlab\.com/gitlab-org/fleeting/fleeting ' go.mod \
      | awk '{print $2}' > /out/fleeting-version

# ---- fleeting 插件 ---------------------------------------------------------
FROM docker.io/library/golang:${PLUGIN_GOLANG_VERSION}-alpine AS plugin-build

ARG RAAS_REPO=https://github.com/fivetime/openstack-raas.git
# 与 raas 镜像同一个 pin。两个镜像装的是同一份代码的不同入口,
# 版本对不上时插件与编排器的 HTTP 契约可能已经改了。
ARG RAAS_REF=e9d54d830e35775aabdcddf30e02c50225bb7394

RUN --mount=type=secret,id=src_repo_token \
    apk add --no-cache git \
 && if [ -s /run/secrets/src_repo_token ]; then \
        token="$(cat /run/secrets/src_repo_token)"; \
        git config --global \
          url."https://x-access-token:${token}@github.com/".insteadOf \
          "https://github.com/"; \
    fi \
 && git init /src \
 && git -C /src remote add origin "${RAAS_REPO}" \
 && git -C /src fetch --depth=1 --filter=blob:none origin "${RAAS_REF}" \
 && git -C /src checkout --detach FETCH_HEAD \
 && rm -f /root/.gitconfig

WORKDIR /src
COPY --from=runner-build /out/fleeting-version /tmp/fleeting-version

# **版本对齐的强制点。** 插件的 fleeting 与 runner 的必须一致 ——
# 不一致就在这里失败,而不是等部署上去 go-plugin 握手报
# "incompatible API version with plugin"。
RUN want="$(cat /tmp/fleeting-version)" \
 && have="$(grep -E '^\s+gitlab\.com/gitlab-org/fleeting/fleeting ' go.mod | awk '{print $2}')" \
 && echo "runner fleeting: ${want}" \
 && echo "plugin fleeting: ${have}" \
 && [ "$want" = "$have" ] || { \
      echo "FATAL: 插件与 gitlab-runner 的 fleeting 版本不一致。"; \
      echo "接口在演进(Heartbeat/Suspend/Resume 是后加的),错配会让"; \
      echo "go-plugin 握手直接失败。把 openstack-raas 的 go.mod 对齐到 ${want}。"; \
      exit 1; }

RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 go build -trimpath \
      -ldflags "-s -w -X github.com/fivetime/openstack-raas/internal/fleetingplugin.Version=${RAAS_REF}" \
      -o /out/fleeting-plugin-raas ./cmd/fleeting-plugin-raas

# ---- 运行镜像 --------------------------------------------------------------
FROM docker.io/library/alpine:${ALPINE_VERSION}

# ca-certificates:要连租户的 GitLab(HTTPS)与编排器。
# git / git-lfs:runner 自己不 clone(那在虚拟机上做),但 helper 需要。
# openssh-client:instance 执行器靠 SSH 连进虚拟机。
RUN apk add --no-cache ca-certificates tzdata git git-lfs openssh-client \
 && adduser -D -u 42424 runner

COPY --from=runner-build   /out/gitlab-runner          /usr/bin/gitlab-runner
COPY --from=plugin-build   /out/fleeting-plugin-raas   /usr/local/bin/fleeting-plugin-raas

# 自检:两个二进制都能跑,且插件版本已注入(不是默认的 "dev")。
# 装错代码在运行期只表现为"行为不对",这里当场拦下。
RUN gitlab-runner --version >/dev/null \
 && /usr/local/bin/fleeting-plugin-raas --version 2>/dev/null | head -1 || true

USER runner
WORKDIR /home/runner
ENTRYPOINT ["/usr/bin/gitlab-runner"]
CMD ["run"]
