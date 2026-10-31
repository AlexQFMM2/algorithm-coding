#!/usr/bin/env python3
"""Install clangd locally from checked distro/release packages; no sudo needed."""
import hashlib
import os
import platform
import shlex
import shutil
import subprocess
import tempfile
import urllib.request
from urllib.parse import unquote, urlparse
import zipfile
from pathlib import Path

from workbench.language import find_clangd

VERSION = "20.1.8"
SHA256 = "98493005e2c7532e69827987d909c46295e2ee997a48228606e7777547994490"
URL = f"https://github.com/clangd/clangd/releases/download/{VERSION}/clangd-linux-{VERSION}.zip"
TOOLS = Path(__file__).resolve().parent / ".tools"


def install_apt():
    """Resolve distro dependencies read-only, then extract them under .tools."""
    destination = TOOLS / "clangd"
    executable = destination / "bin/clangd"
    if executable.is_file():
        subprocess.run([str(executable), "--version"], check=True)
        return
    command = ["apt-get", "-o", "Debug::NoLocking=true", "--print-uris", "--yes",
               "--download-only", "--no-install-recommends", "--reinstall", "install", "clangd-18"]
    plan = subprocess.check_output(command, text=True)
    packages = [shlex.split(line) for line in plan.splitlines() if line.startswith("'")]
    if not packages:
        raise OSError("APT 没有返回 clangd-18 下载信息，请更新系统软件包索引后重试。")
    print(f"下载发行版 clangd 及缺少的依赖（{sum(int(p[2]) for p in packages) / 1048576:.1f} MiB）…", flush=True)
    with tempfile.TemporaryDirectory(prefix="clangd-install-", dir=TOOLS) as temporary:
        staging = Path(temporary)
        runtime = staging / "clangd/runtime"
        runtime.mkdir(parents=True)
        for url, filename, _size, _digest in packages:
            name = unquote(filename).split("_")[0]
            metadata = subprocess.check_output(["apt-cache", "show", name], text=True)
            expected = None
            for block in metadata.split("\n\n"):
                fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line and not line.startswith(" "))
                if Path(fields.get("Filename", "")).name == unquote(Path(urlparse(url).path).name):
                    expected = fields.get("SHA256")
                    break
            if not expected:
                raise OSError(f"{name} 缺少 SHA256 校验信息，未安装。")
            archive = staging / filename
            # The repository's signed APT metadata supplies the checksum. HTTPS
            # also avoids networks which block plain-HTTP package downloads.
            if url.startswith("http://"):
                url = "https://" + url[7:]
            digest = hashlib.sha256()
            print(f"  {name}", flush=True)
            with urllib.request.urlopen(url, timeout=30) as response, archive.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
                    digest.update(chunk)
            if digest.hexdigest() != expected:
                raise OSError(f"{name} 校验失败，未安装。")
            subprocess.run(["dpkg-deb", "--extract", str(archive), str(runtime)], check=True)
        wrapper = staging / "clangd/bin/clangd"
        wrapper.parent.mkdir()
        wrapper.write_text('''#!/bin/sh
tool_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export LD_LIBRARY_PATH="$tool_dir/runtime/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$tool_dir/runtime/usr/lib/llvm-18/bin/clangd" "$@"
''', encoding="utf-8")
        wrapper.chmod(0o755)
        subprocess.run([str(wrapper), "--version"], check=True)
        os.rename(wrapper.parent.parent, destination)


def main():
    installed = find_clangd()
    if installed:
        subprocess.run([installed, "--version"], check=True)
        print("clangd 已就绪，无需重复安装。")
        return
    if platform.system() != "Linux" or platform.machine() not in ("x86_64", "amd64"):
        raise SystemExit("此安装脚本适用于 Linux / WSL x86_64；其他平台请安装系统 clangd。")
    TOOLS.mkdir(exist_ok=True)
    if shutil.which("apt-get") and shutil.which("dpkg-deb"):
        install_apt()
        print("本地 clangd 已就绪。重启 ./start.sh 并刷新页面即可；未修改系统软件包。")
        return
    binary = TOOLS / f"clangd_{VERSION}" / "bin" / "clangd"
    if binary.is_file():
        subprocess.run([str(binary), "--version"], check=True)
        print("本地 clangd 已就绪。")
        return
    TOOLS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="clangd-install-", dir=TOOLS) as temporary:
        staging = Path(temporary)
        archive = staging / "clangd.zip"
        print(f"下载官方 clangd {VERSION}（约 160 MiB，仅首次安装需要联网）…", flush=True)
        digest = hashlib.sha256()
        with urllib.request.urlopen(URL, timeout=60) as response, archive.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                digest.update(chunk)
        if digest.hexdigest() != SHA256:
            raise SystemExit("下载校验失败，未安装。请重新运行此脚本。")
        with zipfile.ZipFile(archive) as package:
            for entry in package.infolist():
                if not (staging / entry.filename).resolve().is_relative_to(staging.resolve()):
                    raise SystemExit("压缩包路径无效，未安装。")
            package.extractall(staging)
        extracted = staging / f"clangd_{VERSION}"
        executable = extracted / "bin" / "clangd"
        executable.chmod(executable.stat().st_mode | 0o111)
        subprocess.run([str(executable), "--version"], check=True)
        os.rename(extracted, binary.parent.parent)
    print("安装完成。重新启动 ./start.sh 并刷新页面即可使用；日常使用无需联网。")


if __name__ == "__main__":
    try:
        main()
    except (OSError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        raise SystemExit(f"安装失败：{error}。可重试，或安装系统 clangd。") from error
