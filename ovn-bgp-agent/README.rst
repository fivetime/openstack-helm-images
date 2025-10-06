OVN BGP Agent
=============

This directory contains Dockerfiles for building OVN BGP Agent images.

Overview
--------

The OVN BGP Agent exposes VMs/Containers through BGP on OVN environments.
It supports multiple drivers for different use cases:

* BGP Driver (SB/NB): Expose VMs with FIPs or on Provider Networks
* EVPN Driver: Expose VMs on Tenant Networks through EVPN
* Stretched L2 BGP Driver: Announce networks via BGP in L2 provider networks

Building Images
---------------

To build an image for Ubuntu 24.04 (Noble):

.. code-block:: bash

    cd ovn-bgp-agent
    chmod +x build.sh
    ./build.sh

To build for Ubuntu 22.04 (Jammy):

.. code-block:: bash

    DISTRO=ubuntu_jammy ./build.sh

To build from a specific branch:

.. code-block:: bash

    PROJECT_REF=stable/2025.2 ./build.sh

To build and push to a registry:

.. code-block:: bash

    REGISTRY=quay.io \
    IMAGE_PREFIX=myorg \
    PUSH=true \
    ./build.sh

Build Arguments
---------------

The following build arguments are supported:

* ``PROJECT_REF``: Git branch/tag to build from (default: master)
* ``FROM``: Base image (default: ubuntu:24.04 or ubuntu:22.04)
* ``PIP_INDEX_URL``: PyPI index URL (default: https://pypi.python.org/simple)
* ``PIP_TRUSTED_HOST``: PyPI trusted host (default: pypi.python.org)

Environment Variables
---------------------

The build script supports the following environment variables:

* ``DISTRO``: Distribution to build (ubuntu_noble, ubuntu_jammy)
* ``PROJECT_REF``: OVN BGP Agent version/branch
* ``REGISTRY``: Docker registry (default: docker.io)
* ``IMAGE_PREFIX``: Image name prefix (default: openstackhelm)
* ``IMAGE_TAG``: Image tag (default: ${PROJECT_REF}-${DISTRO})
* ``PUSH``: Push image after build (true/false)

Image Details
-------------

Design Philosophy
~~~~~~~~~~~~~~~~~

This image follows a **minimal, single-responsibility** design principle:

**Included:**

* Python 3 runtime
* ovn-bgp-agent and its Python dependencies
* Basic networking tools: iproute2 (ip command), iptables, iputils-ping

**Not Included (assumes external deployment):**

* OVS/OVN tools - assumes OVS and OVN are already deployed
* FRR (Free Range Routing) - must be deployed separately as a sidecar or host service

This approach:

* Keeps the image minimal and focused
* Follows container best practices (single responsibility)
* Allows flexible deployment architectures
* Reduces image size and attack surface

User and Permissions
~~~~~~~~~~~~~~~~~~~~

The image runs as user ``ovn-bgp-agent`` (UID 42494) by default.

**UID/GID Allocation:**

* **UID 42494**: ovn-bgp-agent user (next available in Kolla UID registry)
* **GID 42494**: ovn-bgp-agent primary group
* **GID 42424**: openvswitch supplemental group (for OVS socket access)

The user is added to the openvswitch group (GID 42424) to access OVS database
sockets without requiring root privileges.

**Note on UID Registration:**

UID 42494 is proposed as the next available UID in the OpenStack Kolla user
registry. A formal registration request should be submitted to the Kolla project
to reserve this UID officially.

**Required Permissions:**

The agent requires these capabilities to function:

* **Read access** to OVS/OVN database sockets (via group membership)
* **Write access** to FRR control socket (vtysh.sock)
* **NET_ADMIN capability** for kernel routing operations (ip rules, routes, neighbors)
* **Access to host network** for BGP advertisement

Directories
~~~~~~~~~~~

* ``/etc/ovn-bgp-agent``: Configuration directory
* ``/var/lib/ovn-bgp-agent``: Working directory
* ``/var/log/ovn-bgp-agent``: Log directory
* ``/run/ovn-bgp-agent``: Runtime directory

All directories are owned by the ovn-bgp-agent user (42494:42494).

Required External Components
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**OVS/OVN (Required)**

Open vSwitch and OVN must be running with accessible sockets:

* ``/run/openvswitch/db.sock`` - OVSDB socket (typically owned by UID 42424)
* ``/run/ovn/ovnsb_db.sock`` - OVN Southbound DB (for SB driver)
* ``/run/ovn/ovnnb_db.sock`` - OVN Northbound DB (for NB driver)

The agent monitors these databases to detect VM and network events.

**FRR - Free Range Routing (Required)**

FRRouting must be deployed separately. The agent connects via vtysh socket to
configure BGP routing dynamically:

* ``/var/run/frr/vtysh.sock`` - FRR control socket

FRR should be configured with:

* BGP daemon (bgpd) running
* VRF support for route isolation
* Proper prefix filtering (only /32 for IPv4, /128 for IPv6)

See the official OVN BGP Agent documentation for FRR configuration examples:
https://docs.openstack.org/ovn-bgp-agent/latest/

Deployment Examples
-------------------

Kubernetes DaemonSet (Recommended)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

    apiVersion: apps/v1
    kind: DaemonSet
    metadata:
      name: ovn-bgp-agent
      namespace: openstack
    spec:
      selector:
        matchLabels:
          app: ovn-bgp-agent
      template:
        metadata:
          labels:
            app: ovn-bgp-agent
        spec:
          hostNetwork: true
          containers:
          - name: agent
            image: docker.io/openstackhelm/ovn-bgp-agent:master-ubuntu_noble
            securityContext:
              # The image runs as UID 42494 by default
              # Ensure capabilities for kernel routing
              capabilities:
                add:
                  - NET_ADMIN
            volumeMounts:
            - name: config
              mountPath: /etc/ovn-bgp-agent
              readOnly: true
            - name: ovs-run
              mountPath: /run/openvswitch
            - name: ovn-run
              mountPath: /run/ovn
              readOnly: true
            - name: frr-run
              mountPath: /var/run/frr
            - name: log
              mountPath: /var/log/ovn-bgp-agent

          volumes:
          - name: config
            configMap:
              name: ovn-bgp-agent-config
          - name: ovs-run
            hostPath:
              path: /run/openvswitch
          - name: ovn-run
            hostPath:
              path: /run/ovn
          - name: frr-run
            hostPath:
              path: /var/run/frr
          - name: log
            hostPath:
              path: /var/log/ovn-bgp-agent
              type: DirectoryOrCreate

Configuration Example
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: ovn-bgp-agent-config
    data:
      bgp-agent.conf: |
        [DEFAULT]
        debug=True
        reconcile_interval=120

        # Driver selection (choose one):
        driver=ovn_bgp_driver                # SB DB BGP Driver
        # driver=nb_ovn_bgp_driver           # NB DB BGP Driver
        # driver=ovn_evpn_driver             # EVPN Driver
        # driver=ovn_stretched_l2_bgp_driver # Stretched L2 Driver

        # BGP configuration
        bgp_AS=64999
        bgp_nic=bgp-nic
        bgp_vrf=bgp-vrf
        bgp_vrf_table_id=10

        # Tenant network exposure (optional)
        # expose_tenant_networks=True
        # expose_ipv6_gua_tenant_networks=True
        # address_scopes=UUID1,UUID2

        # OVS connection
        ovsdb_connection=unix:/run/openvswitch/db.sock

        [ovn]
        ovn_nb_connection=tcp:ovn-ovsdb-nb.openstack.svc.cluster.local:6641
        ovn_sb_connection=tcp:ovn-ovsdb-sb.openstack.svc.cluster.local:6642

Docker Standalone Example
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

    docker run -d \
      --name ovn-bgp-agent \
      --network host \
      --cap-add NET_ADMIN \
      -v /etc/ovn-bgp-agent:/etc/ovn-bgp-agent:ro \
      -v /run/openvswitch:/run/openvswitch:rw \
      -v /run/ovn:/run/ovn:ro \
      -v /var/run/frr:/var/run/frr:rw \
      openstackhelm/ovn-bgp-agent:master-ubuntu_noble

Multi-Container Pod with FRR Sidecar
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

    apiVersion: v1
    kind: Pod
    metadata:
      name: ovn-bgp-agent-with-frr
    spec:
      hostNetwork: true
      containers:
      # FRR container
      - name: frr
        image: frrouting/frr:latest
        securityContext:
          capabilities:
            add: [NET_ADMIN, NET_RAW]
        volumeMounts:
        - name: frr-config
          mountPath: /etc/frr
        - name: frr-run
          mountPath: /var/run/frr

      # OVN BGP Agent container
      - name: ovn-bgp-agent
        image: openstackhelm/ovn-bgp-agent:master-ubuntu_noble
        securityContext:
          capabilities:
            add: [NET_ADMIN]
        volumeMounts:
        - name: agent-config
          mountPath: /etc/ovn-bgp-agent
        - name: ovs-run
          mountPath: /run/openvswitch
        - name: ovn-run
          mountPath: /run/ovn
        - name: frr-run
          mountPath: /var/run/frr

      volumes:
      - name: frr-config
        configMap:
          name: frr-config
      - name: agent-config
        configMap:
          name: ovn-bgp-agent-config
      - name: frr-run
        emptyDir: {}
      - name: ovs-run
        hostPath:
          path: /run/openvswitch
      - name: ovn-run
        hostPath:
          path: /run/ovn

Troubleshooting
---------------

Permission Denied Errors
~~~~~~~~~~~~~~~~~~~~~~~~

If you see errors accessing OVS/OVN sockets:

.. code-block:: bash

    # Check socket ownership on host
    ls -la /run/openvswitch/db.sock
    # srwxrwx--- 1 42424 42424 0 db.sock

    # The container user (42494) should be in group 42424
    # This is already configured in the image

If your OVS uses a different UID/GID, you may need to:

1. Rebuild the image with matching GID
2. Or run the container with appropriate fsGroup:

.. code-block:: yaml

    securityContext:
      fsGroup: <your-ovs-gid>

FRR Connection Issues
~~~~~~~~~~~~~~~~~~~~~

If the agent cannot connect to FRR:

.. code-block:: bash

    # Verify FRR is running and socket exists
    ls -la /var/run/frr/vtysh.sock

    # Check FRR logs
    docker logs <frr-container>

    # Test vtysh connection manually
    docker exec <agent-container> ls -la /var/run/frr/

Agent Not Starting
~~~~~~~~~~~~~~~~~~

.. code-block:: bash

    # Check agent logs
    kubectl logs -n openstack <pod-name>

    # Verify configuration
    kubectl exec -n openstack <pod-name> -- cat /etc/ovn-bgp-agent/bgp-agent.conf

    # Test OVN connectivity
    kubectl exec -n openstack <pod-name> -- \
      ovn-sbctl --db=tcp:ovn-ovsdb-sb:6642 show

UID/GID Conflicts
~~~~~~~~~~~~~~~~~

If you encounter UID/GID conflicts in your environment:

.. code-block:: bash

    # Check what UIDs are in use
    ps aux | grep -E "ovs|ovn|bgp"

    # Check socket ownership
    ls -la /run/openvswitch/
    ls -la /run/ovn/

If UID 42494 is already in use, you may need to:

1. Choose a different available UID
2. Rebuild the image with your chosen UID
3. Update the Dockerfile's groupadd/useradd commands accordingly

References
----------

* **OVN BGP Agent Documentation**: https://docs.openstack.org/ovn-bgp-agent/latest/
* **Source Code**: https://opendev.org/openstack/ovn-bgp-agent
* **OpenStack Helm**: https://docs.openstack.org/openstack-helm/latest/
* **FRR Documentation**: https://docs.frrouting.org/
* **Kolla UID/GID Registry**: https://github.com/openstack/kolla/blob/master/kolla/common/users.py