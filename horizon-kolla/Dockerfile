# syntax=docker/dockerfile:1
# Fork-only: kolla horizon + zun-ui.
# The kolla 2026.1 horizon image bundles most dashboard plugins but not
# zun-ui; the airshipit (loci) horizon image bundles none at all. Add the
# missing plugin on top of the kolla base so conf.horizon.extra_panels can
# enable it (the chart start script symlinks enabled/ files and runs
# collectstatic+compress at startup, so no other build step is needed).
ARG BASE=quay.io/openstack.kolla/horizon:2026.1-ubuntu-noble
FROM ${BASE}

ARG RELEASE=2026.1

USER root
RUN /var/lib/kolla/venv/bin/pip install --no-cache-dir \
        -c https://releases.openstack.org/constraints/upper/${RELEASE} \
        zun-ui \
    && /var/lib/kolla/venv/bin/pip show zun-ui | head -2 \
    # zun-ui (master included) still references Bootstrap-3-era $gray-lighter,
    # undefined in current horizon themes -> 'manage.py compress' aborts and
    # the pod crash-loops. Inline its Bootstrap 3 value. Fail the build if the
    # pattern count changes so a fixed/changed upstream gets noticed.
    && cnt=$(grep -rl '\$gray-lighter' /var/lib/kolla/venv/lib/python3*/site-packages/zun_ui/static | wc -l) \
    && test "$cnt" -ge 1 \
    && grep -rl '\$gray-lighter' /var/lib/kolla/venv/lib/python3*/site-packages/zun_ui/static \
       | xargs sed -i 's/\$gray-lighter/#eee/g'
USER horizon
