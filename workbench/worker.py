"""Apply Linux resource limits in a fresh process, before executing user code.

This is a local runner for the user's own code, not an untrusted-code sandbox.
"""
import os
import resource
import signal
import sys

# Python ignores SIGXFSZ; restore it so a C++ output flood stops at the limit.
signal.signal(signal.SIGXFSZ, signal.SIG_DFL)
signal.signal(signal.SIGXCPU, signal.SIG_DFL)
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
# Emit SIGXCPU at 3 CPU seconds so callers can distinguish a timeout from a
# crash. Equal soft/hard limits emit SIGKILL instead, racing the 3-second wall
# watchdog. The hard cap only backs up the soft limit; the wall limit stays 3s.
resource.setrlimit(resource.RLIMIT_CPU, (3, 4))
resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_FSIZE, (4 * 1024 * 1024, 4 * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
os.execv(sys.argv[1], [sys.argv[1]])
