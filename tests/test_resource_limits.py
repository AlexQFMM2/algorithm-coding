import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from workbench.judge import execute


class ResourceLimitTest(unittest.TestCase):
    def test_kernel_cpu_timeout_is_distinguishable_from_runtime_crash(self):
        # Give the outer watchdog extra time so the kernel's CPU limit wins.
        # Equal soft/hard limits instead send SIGKILL, which looks like a crash.
        with tempfile.TemporaryDirectory(prefix="algorithm-cpu-limit-") as temp:
            directory = Path(temp)
            source = directory / "loop.cpp"
            binary = directory / "loop"
            source.write_text("int main(){while(true){}}\n")
            subprocess.run(["g++", "-O2", str(source), "-o", str(binary)],
                           check=True, capture_output=True, timeout=20)
            incoming = directory / "input.txt"
            incoming.write_text("")
            worker = Path(__file__).resolve().parent.parent / "workbench/worker.py"
            result = execute([sys.executable, str(worker), str(binary)], directory,
                             incoming, directory / "stdout.txt", directory / "stderr.txt", 10)
            self.assertFalse(result["timed_out"], result)
            self.assertEqual(result["exit_code"], -signal.SIGXCPU, result)


if __name__ == "__main__":
    unittest.main()
