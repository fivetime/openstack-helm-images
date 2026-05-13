#!/bin/sh
# ovn-kube-util 替代脚本
# 用法: ovn-kube-util readiness-probe -t <target>

# 查找 .ctl 文件（支持带 PID 的文件名）
find_ctl() {
    local base=$1
    local dir=$2
    # 先尝试精确匹配
    if [ -S "${dir}/${base}.ctl" ]; then
        echo "${dir}/${base}.ctl"
        return 0
    fi
    # 再尝试带 PID 的模式
    local ctl=$(ls ${dir}/${base}.*.ctl 2>/dev/null | head -1)
    if [ -n "$ctl" ] && [ -S "$ctl" ]; then
        echo "$ctl"
        return 0
    fi
    return 1
}

# 解析参数
TARGET=""
while [ $# -gt 0 ]; do
    case "$1" in
        readiness-probe)
            shift
            ;;
        -t)
            shift
            TARGET="$1"
            shift
            ;;
        *)
            shift
            ;;
    esac
done

if [ -z "$TARGET" ]; then
    echo "Usage: ovn-kube-util readiness-probe -t <target>"
    exit 1
fi

case "$TARGET" in
    ovnnb-db|ovnnb-db-raft)
        CTL=$(find_ctl "ovnnb_db" "/var/run/ovn")
        [ -z "$CTL" ] && { echo "ovnnb_db.ctl not found"; exit 1; }
        exec ovn-appctl -t "$CTL" ovsdb-server/list-dbs
        ;;
    ovnsb-db|ovnsb-db-raft)
        CTL=$(find_ctl "ovnsb_db" "/var/run/ovn")
        [ -z "$CTL" ] && { echo "ovnsb_db.ctl not found"; exit 1; }
        exec ovn-appctl -t "$CTL" ovsdb-server/list-dbs
        ;;
    ovn-northd)
        CTL=$(find_ctl "ovn-northd" "/var/run/ovn")
        [ -z "$CTL" ] && { echo "ovn-northd.ctl not found"; exit 1; }
        exec ovn-appctl -t "$CTL" version
        ;;
    ovn-controller)
        CTL=$(find_ctl "ovn-controller" "/var/run/ovn")
        [ -z "$CTL" ] && { echo "ovn-controller.ctl not found"; exit 1; }
        exec ovn-appctl -t "$CTL" version
        ;;
    *)
        echo "Unknown target: $TARGET"
        exit 1
        ;;
esac