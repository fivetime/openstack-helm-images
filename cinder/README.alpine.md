# cinder Alpine 镜像 —— 为什么 `FROM alpine` 而不是 `FROM` 某个 base

本文说明 `cinder/Dockerfile.alpine` 的设计：它与官方 `cinder/Dockerfile` **同源**
（opendev cinder `stable/2026.1`，装进 `/var/lib/openstack` venv，drop-in 替换 ubuntu
镜像），但走 Alpine 路线，并额外打包了 etcd / PostgreSQL / Kafka 三类可选驱动。

## 与 neutron Alpine 变体的关键差异：base 镜像

neutron 的 Alpine 变体 **必须** `FROM` 我方 OVN base，因为 `neutron-ovn-agent` 的
metadata 角色要用 `ovs-vsctl` 往本机 `br-int` 插端口（见 `neutron/README.alpine.md`）。

**cinder 不同：它是块存储服务，完全不碰 OVS/OVN。** 所以本镜像直接
`FROM alpine:3.23`，没有任何 fork base 镜像依赖。由此带来两个好处：

- **没有"一轮滞后"问题**。neutron-alpine 与 ovn-alpine 同属 service tier、`FROM` 的是
  上一轮发布的 `ovn:alpine_latest`，存在一个构建周期的滞后。cinder-alpine 的 base 是
  公共 `alpine:3.23`，与本仓库其它镜像无构建顺序耦合。
- **构建更简单**：单阶段，apk 装运行期工具 + 一次性 `--virtual` build 依赖，pip 把
  cinder 装进 venv，装完删 build 依赖。

## venv 布局对齐官方（drop-in）

官方 `cinder/Dockerfile` 用 loci `venv_builder` 把 cinder 装进 `/var/lib/openstack`
（`ENV PATH=/var/lib/openstack/bin`）。chart 的 `root_helper`、rootwrap 路径、各 bin
都按此写。本镜像照搬同一布局，因此是真正的 drop-in，无需符号链接补路径。

官方 `BASE_RUNTIME`（`airshipit/base`）自带 sudoers/privsep 配置；alpine 基底没有，故
本镜像补了两样 alpine 相对 airshipit/base 缺失的东西：

1. `/etc/sudoers.d/cinder` —— 非 root(uid 42424)经
   `sudo cinder-rootwrap … privsep-helper` 提权跑 lvm/iscsi/multipath 等特权命令。
2. GNU 兼容 `hostname` wrapper —— 官方 chart init 用 `hostname --fqdn`（GNU 长选项），
   busybox 不认；wrapper 把 `--fqdn/-f` 走 python `socket.getfqdn()`，其余透传 busybox。

## 存储后端工具（对齐官方 PROFILES）

官方 ubuntu 镜像用 bindep + `PROFILES="fluent lvm ceph qemu apache"` 拉运行期工具。
本镜像用 apk 装等价物：

| 后端 | apk 包 | 用途 |
|---|---|---|
| LVM | `lvm2` `lvm2-extra` `device-mapper` | LVM 卷驱动 |
| Ceph | `ceph-common` `py3-rados` `py3-rbd` | RBD 卷/备份驱动 |
| QEMU | `qemu-img` | image ↔ volume 格式转换 |
| iSCSI | `open-iscsi` `multipath-tools` `targetcli` | initiator / 多路径 / LIO target |
| 通用 | `cryptsetup` `util-linux` `e2fsprogs` `xfsprogs` `parted` `lsscsi` `sg3_utils` `nvme-cli` | 加密卷/文件系统/分区/SCSI 工具 |

`os-brick`（cinder 的存储连接库）运行期会 shell 出去调 `iscsiadm`/`multipath`/`lvs`
等命令，上面这些 apk 包正是为它们准备的。

### Ceph 的 `rados`/`rbd` 绑定：apk + `include-system-site-packages`

cinder 的 RBD 驱动 `import rados, rbd`。这两个是 **C 扩展模块**
（`rados.cpython-312-*-musl.so` 等），**PyPI 在 musl 上没有 wheel**，无法 pip 安装。
Alpine 把它们打成 `py3-rados19` / `py3-rbd19`（ceph 19.2.x），装在**系统** site-packages。

为让 venv 里的 cinder 能 import 到它们，又不破坏依赖解析，采用两步：

1. 先建**隔离** venv（`virtualenv /var/lib/openstack`，默认
   `include-system-site-packages = false`），pip 严格按 `upper-constraints` 干净解析
   cinder 全部依赖 —— 系统 apk 包不参与解析，避免被旧的系统包"已满足"误导。
2. 装完后把 `pyvenv.cfg` 的 `include-system-site-packages` 翻成 `true`。此时系统
   site-packages 成为 **import 期的回退**：venv 自己 pip 装的包仍排在 `sys.path` 前面、
   优先级更高，只有 venv 里没有的 `rados`/`rbd` 落到系统版。

这样 RBD 绑定可用，而 cinder 的依赖版本仍由 pip + upper-constraints 完全掌控。
该模块按 arch 自动选 amd64/arm64 的 `.so`，故多架构构建无需特殊处理。

## 我方增量：三类可选驱动

在与官方同源的基础上，额外 pip 装三样（不在 upper-constraints 约束内，单独一步装）：

| 驱动 | 包 | 用途 |
|---|---|---|
| etcd | `etcd3gw` | tooz 协调后端。cinder-volume active/active（DLM）用 tooz 选主/加锁，etcd3gw 让其后端可指向 etcd（纯 python，走 etcd gRPC-gateway 的 HTTP/JSON） |
| PostgreSQL | `psycopg2-binary` | `[database] connection = postgresql+psycopg2://…`（自带 libpq，无需系统 libpq） |
| Kafka | `confluent-kafka` | `oslo_messaging_notifications.driver = kafka`（如 redpanda）。musl 无 wheel，需对 alpine 的 `librdkafka 2.12.x` 编译，故钉 `>=2.12,<2.13` |

## 构建与验证

```sh
cd cinder
docker build -f Dockerfile.alpine -t cinder:alpine-test .
# master 源：
docker build -f Dockerfile.alpine --build-arg CINDER_REF=master -t cinder:alpine-test .

docker run --rm cinder:alpine-test cinder-manage --version
docker run --rm cinder:alpine-test python3 -c "import rados, rbd; print('rbd OK')"
```

Dockerfile 末尾的自检 RUN 已在构建期校验：cinder 在 venv 布局、各角色入口
（api/scheduler/volume/backup/manage/status）与工具（qemu-img/lvs/iscsiadm/multipath/
targetcli）齐全、`rados`/`rbd` 能 import、三类驱动能 import、`hostname --fqdn` 正常。
任一缺失即 `docker build` 失败，不会产出坏镜像。
