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
print("raas-ui guard: %d enabled files, apps=%s" % (len(names), dict(seen)))
