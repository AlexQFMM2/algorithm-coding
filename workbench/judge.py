"""Compile, run and record reproducible checks without external dependencies."""
import os
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from .repository import AppError, revision, write_json

TIMEOUT = 3
OUTPUT_LIMIT = 4 * 1024 * 1024
PREVIEW_LIMIT = 6000


def preview(path):
    with path.open("rb") as stream:
        content = stream.read(PREVIEW_LIMIT + 1)
    text = content[:PREVIEW_LIMIT].decode("utf-8", errors="replace")
    return text + ("\n… 内容较长，完整内容见日志文件。" if len(content) > PREVIEW_LIMIT else "")


def execute(command, cwd, stdin, stdout, stderr, timeout):
    start = time.monotonic()
    with stdin.open("rb") as incoming, stdout.open("wb") as outgoing, stderr.open("wb") as errors:
        process = subprocess.Popen(command, cwd=cwd, stdin=incoming, stdout=outgoing, stderr=errors,
                                   start_new_session=True)
        timed_out = False
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
        finally:
            # Also remove child processes if the main program exits early.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
    return {"exit_code": process.returncode, "timed_out": timed_out,
            "duration_ms": round((time.monotonic() - start) * 1000)}


class Judge:
    def __init__(self, repository):
        self.repository = repository
        self.lock = threading.Lock()

    def run(self, name, attempt, expected_revision, mode, user_input="", sample_index=0):
        if mode not in ("sample", "manual", "check"):
            raise AppError("未知的运行方式。")
        if not isinstance(user_input, str) or len(user_input.encode("utf-8")) > 2_000_000:
            raise AppError("输入不能超过 2 MB。")
        compiler = shutil.which("g++")
        if not compiler:
            raise AppError("没有找到 g++，请安装 C++ 编译器后重试。", 503)
        if not self.lock.acquire(blocking=False):
            raise AppError("已有程序正在运行，请稍后重试。", 409)
        try:
            return self._run(name, attempt, expected_revision, mode, user_input, sample_index, compiler)
        finally:
            self.lock.release()

    def _run(self, name, attempt, expected_revision, mode, user_input, sample_index, compiler):
        repo = self.repository
        with repo.lock:
            source = repo.read_attempt(name, attempt)["source"]
            if revision(source) != expected_revision:
                raise AppError("练习文件已经改变，请重新载入后运行。", 409)
            config = repo.config(repo.problem(name))
        samples = [{"name": f"样例 {i + 1}", **sample,
                    "source": {"kind": "sample", "path": str((repo.problem(name) / "practice.json").relative_to(repo.root)), "index": i}}
                   for i, sample in enumerate(config.get("samples", []))]
        if mode == "manual":
            cases = [{"name": "手动输入", "input": user_input, "source": {"kind": "manual"}}]
        elif mode == "sample":
            if not isinstance(sample_index, int) or not 0 <= sample_index < len(samples):
                raise AppError("没有这个样例，请在 practice.json 中添加样例。")
            cases = [samples[sample_index]]
        else:
            cases = samples + repo.test_cases(name)
        now = datetime.now(timezone.utc)
        run_id = now.strftime("%Y%m%dT%H%M%S%fZ") + "-" + secrets.token_hex(4)
        directory = repo.run_path(name, run_id)
        directory.mkdir(parents=True, exist_ok=False)
        (directory / "source.cpp").write_text(source, encoding="utf-8")
        (directory / "compile-input.txt").write_text("", encoding="utf-8")
        result = {"id": run_id, "created_at": now.isoformat(), "problem": name, "attempt": attempt,
                  "source_revision": revision(source), "mode": mode, "status": "RUNNING",
                  "passed": 0, "total": len(cases), "cases": [], "compiler": "", "duration_ms": 0,
                  "log_path": str(directory.relative_to(repo.root)), "time_limit_seconds": TIMEOUT}
        # Preserve requested data even if compilation fails, or a prior case fails.
        result["case_plan"] = []
        for index, case in enumerate(cases, 1):
            prefix = f"case-{index:03}"
            (directory / f"{prefix}.in").write_text(case["input"], encoding="utf-8")
            if "output" in case:
                (directory / f"{prefix}.expected").write_text(case["output"], encoding="utf-8")
            result["case_plan"].append({"name": case["name"], "file_prefix": prefix, "source": case["source"]})
        write_json(directory / "result.json", result)
        started = time.monotonic()
        try:
            with tempfile.TemporaryDirectory(prefix="acwing-run-") as working:
                executable = Path(working) / "solution"
                command = [compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror=return-type",
                           str(directory / "source.cpp"), "-o", str(executable)]
                result["compile_command"] = command
                compiled = execute(command, working, directory / "compile-input.txt", directory / "compile.stdout.txt",
                                   directory / "compile.stderr.txt", 20)
                result["compile"] = compiled
                result["compiler"] = preview(directory / "compile.stderr.txt")
                if compiled["timed_out"] or compiled["exit_code"] != 0:
                    result["status"] = "CE"
                    if compiled["timed_out"]:
                        result["compiler"] += "\n编译超过 20 秒，已停止。"
                else:
                    result["status"] = "OK" if mode == "manual" else "PASS"
                    for index, case in enumerate(cases, 1):
                        prefix = f"case-{index:03}"
                        input_file = directory / f"{prefix}.in"
                        output_file = directory / f"{prefix}.out"
                        error_file = directory / f"{prefix}.stderr.txt"
                        execution = execute([sys.executable, str(Path(__file__).with_name("worker.py")), str(executable)],
                                            working, input_file, output_file, error_file, TIMEOUT)
                        if output_file.stat().st_size >= OUTPUT_LIMIT or error_file.stat().st_size >= OUTPUT_LIMIT:
                            status = "OLE"
                        elif execution["timed_out"] or execution["exit_code"] == -signal.SIGXCPU:
                            status = "TLE"
                        elif execution["exit_code"] != 0:
                            status = "RE"
                        elif "output" in case:
                            status = "PASS" if output_file.read_bytes().split() == case["output"].encode().split() else "WA"
                        else:
                            status = "OK"
                        record = {"name": case["name"], "status": status, **execution,
                                  "input": preview(input_file), "stdout": preview(output_file), "stderr": preview(error_file),
                                  "expected": preview(directory / f"{prefix}.expected") if "output" in case else None,
                                  "file_prefix": prefix, "source": case["source"]}
                        result["cases"].append(record)
                        if status in ("PASS", "OK"):
                            result["passed"] += 1
                        else:
                            result["status"] = status
                            break
        except Exception as error:
            result["status"] = "ERROR"
            result["error"] = f"运行工具出错：{type(error).__name__}: {error}"
        finally:
            result["duration_ms"] = round((time.monotonic() - started) * 1000)
            write_json(directory / "result.json", result)
        return result
