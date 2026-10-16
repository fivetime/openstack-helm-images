#!/usr/bin/env python3
"""Stop osprofiler trace contexts from outliving the work they belong to.

Run with the image's venv interpreter after the service is installed:

    PYTHONDONTWRITEBYTECODE=1 /var/lib/openstack/bin/python3 patch_rpc_context.py

osprofiler keeps the current trace in a thread local, and profiler.init()
returns the profiler a thread already has instead of starting the new
trace. The RPC serializers (nova.rpc, neutron_lib.rpc, cinder.rpc) call
init() for every message that carries trace_info and nothing ever cleans
up, so a pooled thread that once handled a traced message records every
later message it handles into that trace (and passes the trace on in its
own RPC and HTTP calls), and ignores the trace of the next traced message.
This matters with native threads, whose executors reuse their threads.

It patches, in place:

1. oslo_messaging/rpc/dispatcher.py: RPCDispatcher._do_dispatch cleans the
   thread's profiler before the message is deserialized and after it has
   been handled.

2. nova/thread_pool_factory.py, when nova is installed: the wrapper that
   carries the caller's trace into a pooled thread cleans the profiler
   before taking the caller's trace and after the task.

Both look the profiler up in sys.modules: a process that never imported
osprofiler has no trace to clean. The script asserts the layout it expects,
so a release that changes it fails the image build instead of shipping
unpatched.
"""

import importlib
import importlib.util
import sys

MARK = '# fivetime: clean the osprofiler trace'

DISPATCH_OLD = '''\
    def _do_dispatch(self, endpoint, method, ctxt, args):
        ctxt = self.serializer.deserialize_context(ctxt)
'''
DISPATCH_NEW = '''\
    def _do_dispatch(self, endpoint, method, ctxt, args):
        ''' + MARK + ''' of the previous message this
        # thread handled before deserializing this one, and this message's
        # after it: profiler.init() keeps a profiler the thread already has,
        # and pooled threads would otherwise carry one trace forever.
        profiler = sys.modules.get('osprofiler.profiler')
        if profiler is None:
            return self._dispatch_to_endpoint(endpoint, method, ctxt, args)
        profiler.clean()
        try:
            return self._dispatch_to_endpoint(endpoint, method, ctxt, args)
        finally:
            profiler.clean()

    def _dispatch_to_endpoint(self, endpoint, method, ctxt, args):
        ctxt = self.serializer.deserialize_context(ctxt)
'''

POOL_OLD = '''\
        if profiler_info and profiler:
            profiler.init(**profiler_info)
        return func(*args, **kwargs)
'''
POOL_NEW = '''\
        ''' + MARK + ''' a pooled thread kept from its
        # previous task before taking the caller's, and this task's after it.
        if profiler:
            profiler.clean()
            if profiler_info:
                profiler.init(**profiler_info)
        try:
            return func(*args, **kwargs)
        finally:
            if profiler:
                profiler.clean()
'''


def patch(module, old, new):
    path = importlib.util.find_spec(module).origin
    with open(path) as f:
        src = f.read()
    if MARK not in src:
        if src.count(old) != 1:
            sys.exit('%s layout changed, expected once: %r' % (path, old[:70]))
        with open(path, 'w') as f:
            f.write(src.replace(old, new, 1))
    return path


def installed(module):
    try:
        spec = importlib.util.find_spec(module)
    except ModuleNotFoundError:
        return False
    return spec is not None and spec.origin is not None


def main():
    if not installed('oslo_messaging.rpc.dispatcher'):
        sys.exit('oslo.messaging is not installed; this image has no RPC')
    patched = [patch('oslo_messaging.rpc.dispatcher', DISPATCH_OLD,
                     DISPATCH_NEW)]
    if installed('nova.thread_pool_factory'):
        patched.append(patch('nova.thread_pool_factory', POOL_OLD, POOL_NEW))

    # find_spec imported the packages, and with them the unpatched modules.
    for name in [n for n in sys.modules
                 if n.startswith(('oslo_messaging', 'nova'))]:
        del sys.modules[name]
    dispatcher = importlib.import_module('oslo_messaging.rpc.dispatcher')
    assert hasattr(dispatcher.RPCDispatcher, '_dispatch_to_endpoint')
    for path in patched:
        with open(path) as f:
            assert MARK in f.read(), path
    print('osprofiler trace cleaned per RPC message and pooled task: %s'
          % ' '.join(patched))


if __name__ == '__main__':
    main()
