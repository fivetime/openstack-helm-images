#!/bin/sh
# 把镜像里钉的源码 commit 更新到各仓库的当前 HEAD。
#
# **必须用 git -C 指定仓库。** 手敲 `cd images && SHA=$(git rev-parse HEAD)`
# 取到的是镜像仓库自己的 commit —— 我连着犯了两次。第一次靠 Dockerfile
# 先 fetch ref 才暴露成 `upload-pack: not our ref`;换成普通的
# `pip install git+@分支` 会静默复用旧层,装上旧代码还显示构建成功。
set -eu
root=$(dirname "$(dirname "$(readlink -f "$0")")")

repin() { # <当前钉的值> <新值> <文件...>
    old=$1; new=$2; shift 2
    [ "$old" = "$new" ] && { echo "  = $new (未变)"; return 0; }
    sed -i "s|$old|$new|g" "$@"
    echo "  → $new"
}

raas=$(git -C "$root/openstack-raas" rev-parse HEAD)
ui=$(git -C "$root/openstack-raas-ui" rev-parse HEAD)

echo "raas:"
repin "$(grep -oE '[0-9a-f]{40}' raas/Dockerfile | head -1)" "$raas" \
    raas/Dockerfile build-local.d/raas.yaml \
    raas-gitlab-runner/Dockerfile build-local.d/raas-gitlab-runner.yaml
echo "raas-ui:"
repin "$(grep -oE 'RAAS_UI_REF=[0-9a-f]{40}' horizon-kolla/Dockerfile | head -1 | cut -d= -f2)" "$ui" \
    horizon-kolla/Dockerfile build-local.d/horizon-kolla.yaml
