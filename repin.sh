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
repin_file() { # <键名> <新值> <文件>
    key=$1; new=$2; f=$3
    # **按键名定位,绝不按位置。** "文件里第一个 40 位 hex"在 horizon-kolla 的
    # Dockerfile 里先命中的是 BARBICAN_UI_REF —— 2026-09-01 就这么把别的组件的
    # pin 换成了 raas-ui 的 sha,还留下键值不一致让 CI 校验器炸(幸而它炸了)。
    old=$(grep -oE "${key}=[0-9a-f]{40}" "$f" | head -1 | cut -d= -f2)
    if [ -z "$old" ]; then echo "  $f: 没找到 ${key}=<sha>,跳过"; return 1; fi
    if [ "$old" = "$new" ]; then echo "  $f ${key} = $new (未变)"; return 0; fi
    sed -i "s|${key}=${old}|${key}=${new}|g" "$f"
    echo "  $f ${key} → $new"
}

raas=$(git -C "$root/openstack-raas" rev-parse HEAD)
ui=$(git -C "$root/openstack-raas-ui" rev-parse HEAD)

echo "raas:"
for f in raas/Dockerfile build-local.d/raas.yaml \
         raas-gitlab-runner/Dockerfile build-local.d/raas-gitlab-runner.yaml; do
    repin_file RAAS_REF "$raas" "$f"
done
echo "raas-ui:"
for f in horizon-kolla/Dockerfile build-local.d/horizon-kolla.yaml; do
    repin_file RAAS_UI_REF "$ui" "$f"
done
