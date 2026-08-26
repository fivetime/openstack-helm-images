"""Build-time guard for the raas-ui Horizon plugin.

Runs inside the horizon-kolla image after raas-ui is installed. Fails the
build if any app is added to INSTALLED_APPS by more than one enabled file:
Django refuses to start on a duplicate label, which takes all of Horizon
down, and only a live Horizon would otherwise report it (2026-08-25).
"""
import collections
import importlib
import pkgutil
import sys

import raas_ui.enabled as pkg

seen = collections.defaultdict(list)
names = [m.name for m in pkgutil.iter_modules(pkg.__path__)]
for name in names:
    mod = importlib.import_module("raas_ui.enabled." + name)
    for app in getattr(mod, "ADD_INSTALLED_APPS", []):
        seen[app].append(name)
dup = {a: f for a, f in seen.items() if len(f) > 1}
if dup:
    sys.exit("raas-ui: ADD_INSTALLED_APPS declared in more than one enabled file: %r" % dup)
# 未定义的名字(比如用了 api.raas.* 却忘了 import api)只有**运行到那一行**
# 才会 NameError:compileall 过、导入 enabled 也过,直到租户在面板上点了按钮才炸。
# 2026-08-26 就是这样:admin 面板批量删除的 62 条全部失败,提示只有一句
# "无法执行 删除",真正的 `name 'api' is not defined` 埋在 Horizon 的 warning 日志里。
# pyflakes 不导入模块就能查出来,正好绕开"完整导入需要 Django 配好数据库"的死路。
import io
import subprocess

proc = subprocess.run([sys.executable, "-m", "pyflakes", pkg.__path__[0].rsplit("/", 1)[0]],
                      capture_output=True, text=True)
undefined = [ln for ln in proc.stdout.splitlines() if "undefined name" in ln]
if undefined:
    sys.exit("raas-ui: undefined names (would NameError at runtime):\n  " + "\n  ".join(undefined))
print("raas-ui guard: %d enabled files, apps=%s, no undefined names" % (len(names), dict(seen)))
