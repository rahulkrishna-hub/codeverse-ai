"""resource module stub for Windows.

Provides the same constants the real resource module exposes on Unix so that
runner.py and worker.py can import resource_stub instead of failing on
``No module named 'resource'``.

The setrlimit / getrlimit codepaths are guarded with try/except in the caller
anyway, and the calls are best-effort on Linux, so the stub simply defines the
constants and no-op functions.  Worker.py's apply_limits() calls
resource.setrlimit on every constant in a try/except, so nothing breaks.
"""

from __future__ import annotations

import sys as _sys

if _sys.platform == "win32":

    RLIMIT_CPU = 0
    RLIMIT_FSIZE = 1
    RLIMIT_DATA = 2
    RLIMIT_STACK = 3
    RLIMIT_RSS = 4
    RLIMIT_NPROC = 6
    RLIMIT_NOFILE = 7
    RLIMIT_AS = 9
    RLIMIT_CORE = 5

    def getrlimit(resource):
        return (0, 0)

    def setrlimit(resource, limits):
        pass

else:
    # On non-Windows, re-export the real module's symbols so runner.py's
    # conditional import behaves identically to ``import resource``.
    import resource as _resource

    RLIMIT_CPU = _resource.RLIMIT_CPU
    RLIMIT_FSIZE = _resource.RLIMIT_FSIZE
    RLIMIT_DATA = _resource.RLIMIT_DATA
    RLIMIT_STACK = _resource.RLIMIT_STACK
    RLIMIT_RSS = _resource.RLIMIT_RSS
    RLIMIT_NPROC = _resource.RLIMIT_NPROC
    RLIMIT_NOFILE = _resource.RLIMIT_NOFILE
    RLIMIT_AS = _resource.RLIMIT_AS
    RLIMIT_CORE = _resource.RLIMIT_CORE

    getrlimit = _resource.getrlimit
    setrlimit = _resource.setrlimit
