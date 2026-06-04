# Vendored ovn-kubernetes runtime scripts

`ovnkube.sh` and `ovndb-raft-functions.sh` are the ovn-kubernetes container
entrypoint / RAFT-bring-up scripts that the OVN image ships under `/root/`.

They are **vendored** (frozen local copies) so the source-built image
(`Dockerfile.alpine`) no longer clones ovn-kubernetes at build time. This
decouples the OVN version from the ovn-kubernetes version: `Dockerfile.alpine`
can build OVN from `main` (latest, includes Transit Router / OVN-IC >= 26.03)
without being held back by the old `OVN_KUBERNETES_REF` the in-tree patches
were written against.

## Local robustness modifications (RAFT) -- 2026-06

The vendored RAFT bring-up had two compounding bugs that made a multi-replica
NB/SB cluster fragile (a single member restart could cascade into a wedged,
quorum-less cluster -- the reason single-replica was used as a workaround):

1. **The clustered db was not persisted.** ovn-ctl writes the db under
   `OVN_DBDIR` (see ovn-lib), which was unset -> defaulted to `/etc/ovn` (the
   ephemeral container fs), while the PVC sat unused at `/var/lib/ovn`. So every
   pod restart lost the db and re-bootstrapped instead of re-joining.
   **Fix:** `ovnkube.sh` now `export OVN_DBDIR=${OVN_DBDIR:-/var/lib/ovn}` (and
   `ovndb-raft-functions.sh` derives `ovn_db_file` from it), so the db lives on
   the volume and a restart finds its clustered db on disk -> takes the safe
   `initialize=false` re-join path. The chart must mount the data PVC at
   `OVN_DBDIR` (default `/var/lib/ovn`).
2. **Bootstrap detection was leader-gated and gave up.** A non-pod-0 member
   joined only after `wait_for_event cluster_exists`, which probes the *client*
   port (6641) -- served only once a leader exists. During a no-leader window
   it never succeeded; after 80 attempts the pod `exit 1`ed and restarted,
   looping forever and denying the cluster the members it needed to elect.
   **Fix:** `ovndb-raft-functions.sh` now waits a *bounded* time and then JOINs
   pod-0 regardless (RAFT tolerates the remote not being up yet and forms the
   cluster on the RAFT port 6643), instead of giving up and restarting.

These are the only intentional divergences from the upstream-derived files
below; everything else is unchanged. Re-vendoring upstream means re-applying
these two changes.

## Provenance (reproducible)

Apart from the **Local robustness modifications** above, these files are
derived from:

    ovn-kubernetes @ 5359e7d7f872058b6e5bf884c9f19d1922451f29
      + patches/ovn-kubernetes/0001-*.patch   (OVN_KUBERNETES_STATEFULSET)
      + patches/ovn-kubernetes/0002-*.patch   (split northd svc)
      + patches/ovn-kubernetes/0003-*.patch   (stop creating ovnkube eps)

Reproduce / re-vendor:

    REF=5359e7d7f872058b6e5bf884c9f19d1922451f29
    git -C <ovn-kubernetes> show $REF:dist/images/ovnkube.sh > ovnkube.sh
    git -C <ovn-kubernetes> show $REF:dist/images/ovndb-raft-functions.sh \
        > ovndb-raft-functions.sh
    # then apply patches/ovn-kubernetes/000{1,2,3}-*.patch (-p1)

Note: ovn-kubernetes `main` has since **removed** `ovndb-raft-functions.sh`
and reworked `ovnkube.sh`, which is the other reason floating the
ovn-kubernetes ref is not viable -- vendoring this known-good pair is.

## OVN 26.03 compatibility

No 26.03-specific edits were needed: these scripts wrap only stable OVN/OVS
CLIs (`ovn-ctl run_nb_ovsdb/run_sb_ovsdb/start_controller`, `--no-monitor`,
`--ovn-manage-ovsdb=no`, `ovsdb-tool db-is-standalone`, `ovn-nbctl
set-connection`, `ovn-appctl`/`ovs-appctl`), none of which changed in 26.03.
If a future OVN bump renames one of those, patch it here.

Verified: `Dockerfile.alpine` builds clean from `OVN_BRANCH=main` (OVN
26.03.90 at time of writing) -- `ovn-ic` / `ovn-ic-nbctl tr-add` (Transit
Router) present, both vendored scripts pass `bash -n`, and the readiness
("heartbeat") path `ovn-kube-util readiness-probe` runs.

NOT YET VERIFIED -- the **RAFT / multi-replica path** (`nb-ovsdb-raft` /
`sb-ovsdb-raft`, which pull in `ovndb-raft-functions.sh`). The default
openstack-helm chart runs single-replica (standalone), so that path is
exercised; HA (`replicas > 1`) uses RAFT. The vendored RAFT functions wrap
stable `ovsdb-tool cluster/*` / `ovs-appctl cluster/*` CLIs, but before
relying on them in production, test a multi-replica RAFT cluster on OVN
26.03 (bring-up + full-node reboot recovery).

The Dockerfile.ubuntu / Dockerfile.centos (package-based) builds still clone
ovn-kubernetes (they also build the Go `ovn-kube-util` from it); only the
source-built Alpine image uses these vendored scripts.
