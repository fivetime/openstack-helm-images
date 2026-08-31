#!/bin/sh
# 把镜像里钉的源码 commit 更新到各仓库的当前 HEAD。
#
# **必须用 git -C 指定仓库。** 手敲 `cd images && SHA=$(git rev-parse HEAD)`
# 取到的是镜像仓库自己的 commit —— 我连着犯了两次。第一次靠 Dockerfile
# 先 fetch ref 才暴露成 `upload-pack: not our ref`;换成普通的
# `pip install git+@分支` 会静默复用旧层,装上旧代码还显示构建成功。
set -eu
root=$(dirname "$(dirname "$(readlink -f "$0")")")

# **逐文件按各自的旧值替换。** 旧版拿 raas/Dockerfile 的旧值去替换全部四个
# 文件 —— 一旦某文件已经不同步(2026-08-31 审计:raas-gitlab-runner 落后
# 9 个提交),它的旧值匹配不上,漂移就永久固化,而 CI 的 PINNED_BUILD_ARGS
# 校验只查 build-local.d↔同镜像 Dockerfile,跨镜像永远不报。
repin_file() { # <新值> <文件>
    new=$1; f=$2
    old=$(grep -oE '[0-9a-f]{40}' "$f" | head -1)
    if [ "$old" = "$new" ]; then echo "  $f = $new (未变)"; return 0; fi
    sed -i "s|$old|$new|g" "$f"
    echo "  $f → $new"
}

raas=$(git -C "$root/openstack-raas" rev-parse HEAD)
ui=$(git -C "$root/openstack-raas-ui" rev-parse HEAD)

echo "raas:"
for f in raas/Dockerfile build-local.d/raas.yaml \
         raas-gitlab-runner/Dockerfile build-local.d/raas-gitlab-runner.yaml; do
    repin_file "$raas" "$f"
done
echo "raas-ui:"
for f in horizon-kolla/Dockerfile build-local.d/horizon-kolla.yaml; do
    repin_file "$ui" "$f"
done
