#!/usr/bin/env python3
"""检查镜像里钉的 Go 版本 >= 源码 go.mod 要求的版本。

这两处会各自漂移,而且**只有 CI 才暴露**:本地 Go 通常更新,所以抬高
go.mod 的 go 指令之后本地照样编得过,镜像里却钉死了旧版,报的是

    go: go.mod requires go >= 1.26.0 (running go 1.25.14; GOTOOLCHAIN=local)

2026-08-27 就这么撞过一次:接 fleeting 依赖时 `go mod tidy` 把 go 指令从
1.25.0 抬到 1.26.0,两个镜像一起构建失败。

用法(在 openstack-raas 的检出旁边跑):
    check_go_pins.py --source /path/to/openstack-raas
"""
import argparse
import pathlib
import re
import sys


def go_directive(gomod: pathlib.Path) -> tuple[int, ...]:
    for line in gomod.read_text().splitlines():
        m = re.match(r"^go\s+(\d+)\.(\d+)(?:\.(\d+))?", line.strip())
        if m:
            return tuple(int(g or 0) for g in m.groups())
    raise SystemExit(f"{gomod}: 找不到 go 指令")


def pinned(dockerfile: pathlib.Path) -> list[tuple[str, tuple[int, ...]]]:
    out = []
    for m in re.finditer(r"^ARG\s+(\w*GOLANG_VERSION)=(\d+)\.(\d+)(?:\.(\d+))?",
                         dockerfile.read_text(), re.M):
        name = m.group(1)
        out.append((name, tuple(int(g or 0) for g in m.groups()[1:])))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True,
                    help="openstack-raas 的检出路径")
    ap.add_argument("--images", default=".", help="本仓库路径")
    args = ap.parse_args()

    want = go_directive(pathlib.Path(args.source) / "go.mod")
    root = pathlib.Path(args.images)

    bad = []
    for ctx in ("raas", "raas-gitlab-runner"):
        df = root / ctx / "Dockerfile"
        if not df.exists():
            continue
        for name, got in pinned(df):
            # runner 那一段跟的是 gitlab-runner 的 go.mod,不是我们的 ——
            # 它只会更高,不该被我们的版本拉低,所以只查不低于。
            if got < want[:len(got)]:
                bad.append(f"{ctx}/Dockerfile {name}="
                           f"{'.'.join(map(str, got))} < go.mod 的 "
                           f"{'.'.join(map(str, want))}")

    if bad:
        print("❌ 镜像钉的 Go 版本低于源码要求:")
        for b in bad:
            print("   ", b)
        print("   这会在构建时报 `go.mod requires go >= X (running go Y)`。")
        return 1
    print(f"✅ Go 版本一致(go.mod 要求 {'.'.join(map(str, want))})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
