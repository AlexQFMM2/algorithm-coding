"""Apply Linux resource limits in a fresh process, before executing user code.

This is a local runner for the user's own code, not an untrusted-code sandbox.
"""
import os
import resource
import signal
import sys

# Python ignores SIGXFSZ; restore it so a C++ output flood stops at the limit.
signal.signal(signal.SIGXFSZ, signal.SIG_DFL)
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_FSIZE, (4 * 1024 * 1024, 4 * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
os.execv(sys.argv[1], [sys.argv[1]])
