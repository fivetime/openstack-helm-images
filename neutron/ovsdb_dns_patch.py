# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""Make ovsdbapp/ovs connect to OVSDB by a DNS hostname (Alpine image patch).

This is the Alpine neutron image's counterpart to neutron-ovnic's
``neutron_ovnic.ovnic.ovsdb_dns`` -- shipped here as a standalone module + a
``.pth`` so it applies to *every* python process in the image (neutron-server,
neutron-ovn-agent, db-sync, ...) without touching upstream neutron code.

Why it is needed: for a non-IP host, ovs's ``socket_util._inet_parse_active``
resolves the name via ``ovs.dns_resolve.resolve()`` -- ovs's *asynchronous*
resolver, which requires the python ``unbound`` library and returns ``''`` on
the first (uncached) lookup, filling the cache only from a background thread.
A one-shot caller like ``idlutils.fetch_schema_json`` never sees the answer, so
the connection fails ("DNS support requires the python unbound library" /
"Connection refused").  That is why ``ovn_nb_connection`` had to be a bare IP
(a single LB/ClusterIP VIP) instead of a Service FQDN.

We replace ``ovs.dns_resolve.resolve`` with a *synchronous* ``getaddrinfo``
(preferring IPv4).  Because ovs re-parses the unchanged target on every
(re)connect, the name is re-resolved each reconnect -- so a per-pod StatefulSet
FQDN survives pod migration / IP change, and ``ovn_nb_connection`` can be the
full per-pod RAFT member list, letting the client follow the OVN leader.

Importing this module applies the patch (idempotently).
"""

import socket

try:
    import ovs.dns_resolve as _dns_resolve
except ImportError:  # ovs not importable -- nothing to patch
    _dns_resolve = None


def _resolve(name):
    """Synchronous name -> address (prefer IPv4); '' if it does not resolve."""
    try:
        infos = socket.getaddrinfo(name, None, 0, socket.SOCK_STREAM)
    except socket.gaierror:
        return ''
    infos.sort(key=lambda i: 0 if i[0] == socket.AF_INET else 1)
    return infos[0][4][0] if infos else ''


def apply():
    """Idempotently install the synchronous resolver."""
    if _dns_resolve is None or getattr(_dns_resolve,
                                       '_ovnic_dns_patched', False):
        return
    _dns_resolve.resolve = _resolve
    _dns_resolve._ovnic_dns_patched = True


apply()
