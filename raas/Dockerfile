# syntax=docker/dockerfile:1
# RaaS 编排器(Runner-as-a-Service)。纯 Go 静态二进制,不是 OpenStack 的
# Python 服务,所以不走 loci/venv_builder 那套,直接两段式构建。

# 必须 ≥ openstack-raas 的 go.mod 里那条 go 指令。**这两处会各自漂移**:
# 本地 Go 通常更新,所以抬高 go.mod 之后本地照样编得过,只有 CI 才暴露
# `go.mod requires go >= X (running go Y; GOTOOLCHAIN=local)`。
# 改 go.mod 的 go 指令时,记得同步这一行。
ARG GOLANG_VERSION=1.26
ARG ALPINE_VERSION=3.22

FROM docker.io/library/golang:${GOLANG_VERSION}-alpine AS build

ARG RAAS_REPO=https://github.com/fivetime/openstack-raas.git
# 钉 commit 而不是分支。两个理由:
#   ① 源仓库是私有的,`ADD https://api.github.com/.../refs/heads/main` 那招
#      破不了缓存(匿名 404),而 RUN 层只按命令字符串缓存 —— 写分支名的话
#      命令永远不变,构建会一直复用旧代码却毫无提示。
#   ② SHA 在 build_args 里可见,部署后能直接对上跑的是哪个提交。
# 这个 ARG 在 zuul_to_matrix.py 的 PINNED_BUILD_ARGS 里,校验器会强制
# build-local.d 的 pin 与这里的默认值一致,不会各写各的。
ARG RAAS_REF=2d1f2de34460f38e17d7db75c909839646d5ebe8

# 私有仓库:CI 用 BuildKit secret(id=src_repo_token,取自仓库 secret CR_PAT)
# 注入 PAT。token 与临时的 git url 重写只存在于本 RUN,不落进任何镜像层。
# secret 缺省时(本地构建/仓库转公开)走匿名 clone,故用 `-s` 判空。
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
# CGO 关掉:依赖(pgx / kafka-go / gophercloud)都是纯 Go,静态链接后运行时
# 只需要 CA 证书,不必带 glibc。
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 go build -trimpath \
      -ldflags "-s -w -X main.version=${RAAS_REF}" \
      -o /out/raas ./cmd/raas

FROM docker.io/library/alpine:${ALPINE_VERSION}

# ca-certificates:要连 GitHub API(HTTPS)、Redpanda(SASL_SSL)、
#   OpenStack API 与 PostgreSQL(sslmode=require)。
# tzdata:计费事件的时间戳按 UTC 输出,但日志与排障看本地时区更顺手。
RUN apk add --no-cache ca-certificates tzdata \
 && adduser -D -u 42424 raas

COPY --from=build /out/raas /usr/local/bin/raas

# 自检:二进制能跑且版本号已注入(不是默认的 "dev")。
# 装错代码在运行期只表现为"行为不对",这里当场拦下。
RUN v="$(/usr/local/bin/raas -version)" \
 && [ -n "$v" ] && [ "$v" != "dev" ] \
 && echo "raas version: $v"

USER raas
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/raas"]
