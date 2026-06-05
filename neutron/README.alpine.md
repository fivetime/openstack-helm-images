# neutron Alpine 镜像 —— 为什么 `FROM` OVN base 而不是 `FROM alpine` + apk

本文说明 `neutron/Dockerfile.alpine` 的 **base 镜像选型**:它 `FROM`
fork 自建的 OVN Alpine 镜像（`ghcr.io/fivetime/openstackhelm/ovn:alpine_latest`），
而**不是**更"干净"的 `FROM alpine:3.23` + `apk add openvswitch`。这是一个有意的
权衡，记录在此以免日后被当成"多余依赖"而误改。

## neutron 从 base 继承的到底是什么

openstack-helm 用**同一个 neutron 镜像**跑所有角色（chart 按 pod 改 command）：

| 角色 | 职责 | 是否需要 `ovs-vsctl` |
|---|---|---|
| `neutron-server` | API + 调度；跟 MySQL/RabbitMQ 通信，把模型写进 **OVN NB DB**（走 python `ovsdbapp`，不用 CLI） | ❌ 不需要 |
| `neutron-ovn-agent`（含 metadata，本镜像默认 `CMD`） | 跑在每个计算/网络节点上 | ✅ 需要 |

纯 OVN 下，L2/L3/安全组由 `ovn-controller` 在节点上下发流表，传统的
l3-agent/dhcp-agent/ovs-agent **都不再运行**。但 OpenStack metadata（169.254.169.254）
OVN 自己不提供，由 neutron 的 OVN metadata agent 负责：它在节点上建 netns + haproxy，
并**用 `ovs-vsctl` 往本机集成网桥 `br-int` 插一个带 `iface-id` 的 internal port**，
把 metadata 数据通路接进 OVS。neutron 的 rootwrap 过滤器也登记了 `ovs-vsctl` 供提权调用。

**所以 neutron 从 base 继承的实质只有 `ovs-vsctl`（OVS CLI）**，不需要 OVN 的
`ovn-northd`/`ovn-controller` 等守护进程。这是 OVN 架构下真实需要的工具，**不是**
传统非 OVN 网络的遗留。

## 为什么是 OVN base，而不是 `apk add openvswitch`

既然只需要 `ovs-vsctl`，理论上可以 `FROM alpine:3.23` 再 `apk add openvswitch`
（Alpine community 源自带，~1.1 MiB）。**但我们仍选择 `FROM` OVN base，核心原因是版本：**

| 来源 | `ovs-vsctl` 版本 |
|---|---|
| fork OVN base（从 OVN `main` 源码编译，OVS 子模块） | **3.7.0** |
| Alpine 3.23 community `apk add openvswitch` | **3.3.7** |

- OVN base 的 OVS 工具与部署里实际运行的 OVS/OVN **同源**（都来自 OVN main），
  client 与 server 版本对齐，避免跨版本漂移。
- Alpine community 的 `openvswitch` 落后好几个小版本（3.3.x vs 3.7.x）。
- **即便受"一轮滞后"影响**（见下）拿到的是上一轮的 `ovn:alpine_latest`，
  那份的 ovs-vsctl 仍是 3.7.x 级别，**依然比 apk 的 3.3.7 新**。

换句话说：脱钩到 apk 会把 ovs-vsctl **降级**到更旧的社区版，得不偿失。故保留 `FROM` OVN base。

## 已知权衡：构建顺序的"一轮滞后"（one-build lag）

`build-local-ovn-alpine` 与依赖它的 `build-local-neutron-alpine` **同属 service tier**，
而 GitHub Actions 的 matrix **不支持 cell 间排序**（`needs:` 只到 job 级，同一 matrix job
内的 cell 并行、互不依赖）。因此 neutron-alpine 构建时 `FROM` 的是**上一轮已发布的**
`ovn:alpine_latest`，而非本轮正在构建的那份。

**这意味着**：若某轮 ovn-alpine 引入破坏性改动，neutron-alpine 要到**下一轮**才 build
在其上、才可能暴露问题——滞后一个构建周期。

**为什么可接受**：
- neutron 只用 `ovs-vsctl`（OVSDB 是稳定的 JSON-RPC 协议），不碰 OVN 守护进程内部；
  OVS CLI 跨小版本兼容性很好，破坏性改动概率低。
- 即使真出问题，下一轮即暴露，且 OVN base 版本始终领先 apk 社区版。
- 正常每日构建总有"上一轮"的 base 可用；只有**手动删空** `ovn:alpine_latest` 时才会
  短暂出现 `FROM ... not found`（删除后第一轮的赛跑），重跑或等 ovn-alpine 先发布即可。

> 若将来要消除这个滞后：把 `build-local-ovn-alpine` 提升为 foundation tier
> （`zuul_to_matrix.py` 的 `FOUNDATION_JOB_SUFFIXES` 加 `-ovn-alpine`），让它在
> `build-foundation`/`merge-foundation` 阶段先发布，service tier 再开跑。当前**不做**，
> 因为上述版本优势 + 滞后风险低，不值得让所有 service 镜像多等一步。

## 附注：ovn-ic-central 是更强的 OVN 依赖

`ovn-ic-central/Dockerfile.alpine` 同样 `FROM` OVN base，但它的依赖**比 neutron 更硬**：
自检要 `ovn-ic-nbctl / ovn-ic-sbctl / ovn-nbctl`，运行时要 shell 出去执行 `tr-add`
建 Transit Router（OVN-IC，需要 ≥ 26.03）。这些是 OVN 客户端，apk 社区版根本没有/太旧，
**必须** `FROM` OVN base，没有脱钩选项。
