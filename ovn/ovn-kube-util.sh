#!/bin/sh
# ovn-kube-util 替代脚本
# 用法: ovn-kube-util readiness-probe -t <target>

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
        exec ovn-appctl -t /var/run/ovn/ovnnb_db.ctl ovsdb-server/list-dbs
        ;;
    ovnsb-db|ovnsb-db-raft)
        exec ovn-appctl -t /var/run/ovn/ovnsb_db.ctl ovsdb-server/list-dbs
        ;;
    ovn-northd)
        exec ovn-appctl -t /var/run/ovn/ovn-northd.ctl version
        ;;
    ovn-controller)
        exec ovn-appctl -t /var/run/ovn/ovn-controller.ctl version
        ;;
    *)
        echo "Unknown target: $TARGET"
        exit 1
        ;;
esac