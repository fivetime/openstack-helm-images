#!/usr/bin/env python3
"""Fix osprofiler's otlp driver for the services that use it.

Run with the image's venv interpreter after osprofiler and the
OpenTelemetry SDK are installed:

    PYTHONDONTWRITEBYTECODE=1 /var/lib/openstack/bin/python3 patch_otlp_driver.py

It patches the installed osprofiler/drivers/otlp.py in place:

1. Import concurrent.futures.thread before the driver creates its
   TracerProvider. OpenTelemetry SDK 1.44+ registers an after-fork hook on
   the provider that submits to a ThreadPoolExecutor in the child, which
   takes concurrent.futures.thread._global_shutdown_lock. That module's own
   hooks (take the lock before fork, reset it in the child) run after
   OpenTelemetry's when the module is imported after the provider, so the
   child waits forever for a lock nobody resets. Python runs at-fork hooks
   in the child of every Popen with a preexec_fn (processutils.execute
   always passes one), so each such call hangs before exec, with native
   threads and under eventlet alike. Upstream:
   https://github.com/open-telemetry/opentelemetry-python/issues/5789

2. Give each forked process its own TracerProvider and export thread on
   its first span. Services that set up osprofiler and then fork workers
   (oslo.service's ProcessLauncher) lose every span under eventlet: the
   batch processor restarts its export thread in its at-fork hook, on the
   parent's hub, and the launcher then gives the child a new hub
   (eventlet.hubs.use_hub()), so that thread never runs again. Upstream:
   https://review.opendev.org/c/openstack/osprofiler/+/1010850

3. Keep the open spans by osprofiler trace id instead of in one stack per
   process. A stop notification carries the same trace id as its start,
   but the driver popped whatever span was pushed last, so two traced
   requests in one process (threads of a uWSGI worker, an RPC executor's
   pool) ended each other's spans and got each other's results and errors.

4. Name function spans with removesuffix("-start"): rstrip("-start")
   strips any of those letters, so "driver" became "drive". Upstream:
   https://review.opendev.org/c/openstack/osprofiler/+/1010851

The script asserts the driver layout it expects, so an osprofiler release
that changes it fails the image build instead of shipping unpatched. Images
that use it build from the repository root. cinder/Dockerfile.alpine still
inlines 1 and 2 (it builds from cinder/).
"""

import importlib
import sys

import osprofiler.drivers.otlp as otlp

EARLY_IMPORT = ('import concurrent.futures.thread  # noqa: F401  '
                '# before TracerProvider registers its at-fork hook\n')
PER_PROCESS_MARK = '# fivetime: per-process provider'

PROVIDER_OLD = '''\
        exporter = OTLPSpanExporter(f"{parsed_url.geturl()}/v1/traces")
        self.trace_api.get_tracer_provider().add_span_processor(  # type: ignore[attr-defined]
            BatchSpanProcessor(exporter)
        )

        self.spans: collections.deque[Any] = collections.deque()
'''
PROVIDER_NEW = PROVIDER_OLD.replace(
    '        self.spans: collections.deque[Any] = collections.deque()\n', ''
) + '''\
        # fivetime: open spans by osprofiler trace id. A stop carries the
        # trace id of its start; one stack per process mixed up the spans of
        # concurrent traced requests (threads of a uWSGI worker, RPC pools).
        self._open_spans: dict[str, Any] = {}

        ''' + PER_PROCESS_MARK + '''. Services that set up osprofiler and then
        # fork their workers (oslo.service's ProcessLauncher) lose every span
        # under eventlet: the batch processor restarts its export thread in
        # its at-fork hook, on the parent's eventlet hub, and the launcher
        # then gives the child a new hub (eventlet.hubs.use_hub()), so that
        # thread never runs again. The first span of a forked process
        # therefore builds the process its own provider and export thread,
        # on the hub that is current by then.
        self._endpoint = f"{parsed_url.geturl()}/v1/traces"
        self._resource = resource
        self._pid = os.getpid()

    def _reset_after_fork(self) -> None:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=self._resource)
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(self._endpoint)))
        self.tracer = provider.get_tracer(__name__)
        # Spans the parent had open at fork time end in the parent.
        self._open_spans = {}
        self._pid = os.getpid()
'''
NOTIFY_OLD = '''\
    def notify(self, info: dict[str, Any], **kwargs: Any) -> None:
        payload = info
'''
NOTIFY_NEW = '''\
    def notify(self, info: dict[str, Any], **kwargs: Any) -> None:
        if self._pid != os.getpid():
            self._reset_after_fork()
        payload = info
'''
PUSH_OLD = '            self.spans.append(span)\n'
PUSH_NEW = '            self._open_spans[payload["trace_id"]] = span\n'
POP_OLD = '            span = self.spans.pop()\n'
POP_NEW = '''\
            span = self._open_spans.pop(payload["trace_id"], None)
            if span is None:
                return
'''
NAME_OLD = '        return str(payload["name"]).rstrip("-start")\n'
NAME_NEW = '        return str(payload["name"]).removesuffix("-start")\n'


def replace_once(src, old, new):
    if src.count(old) != 1:
        sys.exit('osprofiler otlp driver layout changed, expected once: %r'
                 % old[:70])
    return src.replace(old, new, 1)


def main():
    path = otlp.__file__
    with open(path) as f:
        src = f.read()
    orig = src
    if EARLY_IMPORT not in src:
        src = replace_once(src, 'import collections\n',
                           'import collections\n' + EARLY_IMPORT)
    if PER_PROCESS_MARK not in src:
        src = replace_once(src, 'import collections\n',
                           'import collections\nimport os\n')
        src = replace_once(src, PROVIDER_OLD, PROVIDER_NEW)
        src = replace_once(src, NOTIFY_OLD, NOTIFY_NEW)
        src = replace_once(src, PUSH_OLD, PUSH_NEW)
        src = replace_once(src, POP_OLD, POP_NEW)
    if NAME_NEW not in src:
        src = replace_once(src, NAME_OLD, NAME_NEW)
    if src != orig:
        with open(path, 'w') as f:
            f.write(src)

    for name in [n for n in sys.modules if n.startswith('osprofiler')]:
        del sys.modules[name]
    mod = importlib.import_module('osprofiler.drivers.otlp')
    with open(mod.__file__) as f:
        patched = f.read()
    assert EARLY_IMPORT in patched and 'self.spans' not in patched
    assert hasattr(mod.OTLP, '_reset_after_fork')
    print('osprofiler otlp driver: early concurrent.futures import, '
          'per-process provider after fork, open spans by trace id, '
          'span names (%s)' % path)


if __name__ == '__main__':
    main()
