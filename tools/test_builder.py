"""Offline test publication: reference execution + independent expected answers.

The web application never imports or executes this tool. Problem-specific scripts
provide cases; this module only compiles, verifies, and publishes ordinary files.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from workbench.judge import OUTPUT_LIMIT, TIMEOUT, execute

WORKER = Path(__file__).resolve().parent.parent / "workbench/worker.py"


def build_suite(problem, cases, output, seed):
    problem = Path(problem).resolve()
    output = Path(output).absolute()
    if output.is_symlink():
        raise ValueError("输出目录不能是符号链接。")
    output = output.resolve()
    if output == problem or problem.is_relative_to(output):
        raise ValueError("输出目录不能覆盖题目目录或它的父目录。")
    if not cases:
        raise ValueError("至少需要一组额外测试。")
    output.parent.mkdir(parents=True, exist_ok=True)
    lock = output.with_name(f".{output.name}.build.lock")
    try:
        descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise ValueError(f"测试数据正在生成；若上次进程异常退出，请确认后移除 {lock}。") from error
    os.close(descriptor)
    try:
        if output.exists():
            if not output.is_dir():
                raise ValueError("输出路径必须是目录。")
            for path in output.iterdir():
                if path.is_symlink() or not path.is_file() or (path.suffix not in (".in", ".out") and path.name != "generation.json"):
                    raise ValueError(f"输出目录包含非测试文件 {path.name}，不会覆盖。")
        source = (problem / "main.cpp").read_bytes()
        config = json.loads((problem / "practice.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(prefix=f".{output.name}-build-", dir=output.parent) as temporary:
            working = Path(temporary)
            candidate = working / "candidate"
            candidate.mkdir()
            reference = working / "source.cpp"
            reference.write_bytes(source)
            incoming, outgoing, errors = (working / name for name in ("input", "output", "stderr"))
            incoming.write_text("")
            binary = working / "reference"
            compiled = execute(["g++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror=return-type",
                                str(reference), "-o", str(binary)], working, incoming, outgoing, errors, 20)
            if compiled["timed_out"] or compiled["exit_code"]:
                raise ValueError("参考代码编译失败：" + errors.read_text(encoding="utf-8", errors="replace"))
            samples = [{"name": f"原题样例 {index + 1}", **sample}
                       for index, sample in enumerate(config.get("samples", []))]
            for index, case in enumerate(samples + cases):
                text, expected = case["input"], case["output"]
                if not isinstance(text, str) or not isinstance(expected, str):
                    raise ValueError("输入和独立预期答案必须为字符串。")
                if len(text.encode()) > 2_000_000 or len(expected.encode()) > OUTPUT_LIMIT:
                    raise ValueError(f"{case['name']} 超过输入或答案大小限制。")
                incoming.write_text(text, encoding="utf-8")
                result = execute([sys.executable, str(WORKER), str(binary)], working, incoming, outgoing, errors, TIMEOUT)
                if result["timed_out"] or result["exit_code"]:
                    raise ValueError(f"参考程序运行失败：{case['name']}，退出码 {result['exit_code']}。")
                actual = outgoing.read_bytes()
                if actual.split() != expected.encode().split():
                    raise ValueError(f"参考程序与独立答案不一致：{case['name']}，停止发布测试。")
                if index < len(samples):
                    continue
                label = re.sub(r"[^\w=-]+", "-", case["name"], flags=re.UNICODE).strip("-") or "用例"
                stem = f"{index - len(samples) + 1:03}-{label}"
                (candidate / f"{stem}.in").write_text(text, encoding="utf-8")
                (candidate / f"{stem}.out").write_bytes(actual)
            metadata = {"seed": seed, "reference_sha256": hashlib.sha256(source).hexdigest(),
                        "sample_count": len(samples), "file_count": len(cases),
                        "verification": "reference execution matched independent oracle for every case"}
            (candidate / "generation.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            # Keep recovery data outside TemporaryDirectory even if publication
            # is interrupted. Never overwrite a previous recovery directory.
            backup = output.with_name(f".{output.name}.previous")
            if backup.exists():
                raise ValueError(f"发现上次发布的恢复目录 {backup}，请核对后再生成。")
            try:
                if output.exists():
                    output.rename(backup)
                candidate.rename(output)
            except BaseException:
                if backup.exists() and not output.exists():
                    backup.rename(output)
                raise
            if backup.exists():
                try:
                    shutil.rmtree(backup)
                except OSError as error:
                    print(f"新测试已发布；旧数据恢复目录未能清理，请稍后核对 {backup}：{error}", file=sys.stderr)
            return metadata
    finally:
        lock.unlink(missing_ok=True)


def main(problem, factory):
    parser = argparse.ArgumentParser(description="离线生成并验证本题测试数据，不修改练习和运行历史")
    parser.add_argument("--seed", type=int, default=788)
    parser.add_argument("--output", type=Path, default=Path(problem) / "tests")
    args = parser.parse_args()
    try:
        result = build_suite(problem, factory(args.seed), args.output, args.seed)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"生成失败，未发布新测试：{error}\n")
    print(f"已验证 {result['sample_count']} 个原题样例和 {result['file_count']} 个额外用例；"
          f"测试保存到 {args.output.resolve()}，种子 {args.seed}。")
