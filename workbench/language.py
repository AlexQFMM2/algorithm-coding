"""Small, local clangd bridge. Drafts travel in memory; practice files stay untouched."""
import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .repository import AppError, revision

APP_ROOT = Path(__file__).resolve().parent.parent


def find_clangd():
    installed = shutil.which("clangd")
    if installed:
        return installed
    for relative in (".tools/clangd/bin/clangd", ".tools/clangd_20.1.8/bin/clangd"):
        local = APP_ROOT / relative
        if local.is_file():
            return str(local)
    for version in range(22, 17, -1):
        installed = shutil.which(f"clangd-{version}")
        if installed:
            return installed
    return None


def compiler_flags():
    """Use the same system C++ headers as the judge, even for a local clangd."""
    flags = ["-std=c++17", "-Wall", "-Wextra", "-Werror=return-type"]
    try:
        result = subprocess.run(["g++", "-E", "-x", "c++", "-", "-v"], input="",
                                text=True, capture_output=True, timeout=5,
                                env={**os.environ, "LC_ALL": "C"}, check=True)
    except (OSError, subprocess.SubprocessError) as error:
        raise AppError("无法读取 g++ 标准库路径，请确认 g++ 已安装。", 503) from error
    collecting = False
    for line in result.stderr.splitlines():
        if line.strip() == "#include <...> search starts here:":
            collecting = True
        elif collecting and line.strip() == "End of search list.":
            break
        elif collecting and Path(line.strip()).is_dir():
            flags.extend(["-isystem", line.strip()])
    return flags


class Clangd:
    """JSON-RPC over stdio, with a reader that also collects versioned diagnostics."""

    def __init__(self, binary, root):
        flags = compiler_flags()
        directory = root / ".workbench"
        directory.mkdir(exist_ok=True)
        self.logger = logging.Logger(f"clangd-{id(self)}")
        self.log = RotatingFileHandler(directory / "language.log", maxBytes=1_000_000,
                                      backupCount=2, encoding="utf-8")
        self.log.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        self.logger.addHandler(self.log)
        self.condition = threading.Condition()
        self.write_lock = threading.Lock()
        self.next_id = 0
        self.pending = {}
        self.diagnostics = {}
        self.failed = False
        self.process = subprocess.Popen(
            [binary, "--background-index=false", "--clang-tidy", "--enable-config=false",
             "--header-insertion=never", "--completion-style=detailed", "--limit-results=80",
             "--pch-storage=memory", "--log=error", "-j=2"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=root)
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.stderr_reader = threading.Thread(target=self.read_stderr, daemon=True)
        self.reader.start()
        self.stderr_reader.start()
        try:
            self.request("initialize", {
                "processId": None, "rootUri": root.as_uri(),
                "capabilities": {
                    "general": {"positionEncodings": ["utf-16"]},
                    "textDocument": {
                        "publishDiagnostics": {"versionSupport": True},
                        "completion": {"completionItem": {"snippetSupport": True,
                                                           "documentationFormat": ["plaintext"]}},
                        "hover": {"contentFormat": ["plaintext"]},
                        "signatureHelp": {"signatureInformation": {
                            "documentationFormat": ["plaintext"],
                            "parameterInformation": {"labelOffsetSupport": True}}},
                    },
                },
                "initializationOptions": {"fallbackFlags": flags},
            })
            self.send("initialized", {})
            self.logger.info("clangd started: %s", binary)
        except Exception:
            self.close()
            raise

    def write(self, message):
        data = json.dumps({"jsonrpc": "2.0", **message}, ensure_ascii=False).encode("utf-8")
        try:
            with self.write_lock:
                self.process.stdin.write(f"Content-Length: {len(data)}\r\n\r\n".encode() + data)
                self.process.stdin.flush()
        except (OSError, ValueError) as error:
            raise AppError("C++ 提示服务已断开，请点击提示状态重试。", 503) from error

    def send(self, method, params):
        self.write({"method": method, "params": params})

    def request(self, method, params):
        with self.condition:
            self.next_id += 1
            request_id = self.next_id
            self.pending[request_id] = None
        try:
            self.write({"id": request_id, "method": method, "params": params})
            with self.condition:
                ready = self.condition.wait_for(
                    lambda: self.pending[request_id] is not None or self.failed, timeout=15)
                response = self.pending[request_id]
            if not ready:
                self.send("$/cancelRequest", {"id": request_id})
                raise AppError("C++ 提示服务响应超时，请点击提示状态重试。", 503)
            if self.failed or response is None:
                raise AppError("C++ 提示服务已退出，请点击提示状态重试。", 503)
            if "error" in response:
                raise AppError("C++ 提示暂不可用：" + response["error"].get("message", "请求失败"), 503)
            return response.get("result")
        finally:
            with self.condition:
                self.pending.pop(request_id, None)

    def read(self):
        try:
            stream = self.process.stdout
            while True:
                headers = {}
                while True:
                    line = stream.readline()
                    if not line:
                        return
                    if line in (b"\r\n", b"\n"):
                        break
                    key, value = line.decode("ascii").split(":", 1)
                    headers[key.lower()] = value.strip()
                length = int(headers["content-length"])
                if not 0 < length <= 16_000_000:
                    raise ValueError("Invalid clangd message length")
                message = json.loads(stream.read(length))
                with self.condition:
                    if message.get("method") == "textDocument/publishDiagnostics":
                        params = message["params"]
                        self.diagnostics[params["uri"]] = params
                    elif "id" in message and "method" not in message:
                        if message["id"] in self.pending:
                            self.pending[message["id"]] = message
                    elif "id" in message:
                        self.write({"id": message["id"], "result": None})
                    self.condition.notify_all()
        except (OSError, ValueError, KeyError) as error:
            self.logger.error("clangd transport: %s", error)
        finally:
            with self.condition:
                self.failed = True
                self.condition.notify_all()

    def read_stderr(self):
        for line in self.process.stderr:
            self.logger.error(line.decode("utf-8", errors="replace").rstrip())

    def wait_diagnostics(self, uri, version):
        with self.condition:
            ready = self.condition.wait_for(
                lambda: self.failed or self.diagnostics.get(uri, {}).get("version") == version,
                timeout=15)
            if not ready or self.failed:
                raise AppError("C++ 诊断暂未完成，请点击提示状态重试。", 503)
            return self.diagnostics[uri].get("diagnostics", [])

    def forget(self, uri):
        self.send("textDocument/didClose", {"textDocument": {"uri": uri}})
        with self.condition:
            self.diagnostics.pop(uri, None)

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        self.reader.join(timeout=2)
        self.stderr_reader.join(timeout=2)
        for pipe in (self.process.stdin, self.process.stdout, self.process.stderr):
            pipe.close()
        self.logger.info("clangd stopped")
        self.log.close()


class LanguageService:
    def __init__(self, repository):
        self.repository = repository
        self.lock = threading.Lock()
        self.client = None
        self.documents = {}

    def status(self):
        return {"available": bool(find_clangd()), "engine": "clangd",
                "message": "未安装 C++ 提示工具，请在仓库运行 python3 setup-editor.py，然后重启应用。"}

    def close(self):
        with self.lock:
            if self.client:
                self.client.close()
                self.client = None
            self.documents.clear()

    def handle(self, payload):
        action = payload.get("action")
        if action not in ("diagnostics", "completion", "signature", "hover"):
            raise AppError("无效的 C++ 提示请求。")
        source, version, session = (payload.get(key) for key in ("source", "version", "session"))
        if not isinstance(source, str) or len(source.encode("utf-8")) > 1_000_000:
            raise AppError("提示仅支持 1 MB 以内的 C++ 草稿。", 413)
        if type(version) is not int or not 0 < version < 2**31:
            raise AppError("无效的草稿版本。")
        if not isinstance(session, str) or not re.fullmatch(r"[a-zA-Z0-9-]{16,64}", session):
            raise AppError("无效的编辑窗口标识。")
        path = self.repository.attempt_path(payload.get("problem"), payload.get("attempt"))
        if not path.is_file():
            raise AppError("练习文件不存在。", 404)
        position = payload.get("position")
        if action != "diagnostics":
            if not isinstance(position, dict) or any(type(position.get(key)) is not int or position[key] < 0
                                                     for key in ("line", "character")):
                raise AppError("无效的光标位置。")
            lines = source.split("\n")
            if position["line"] >= len(lines) or position["character"] > len(lines[position["line"]].encode("utf-16-le")) // 2:
                raise AppError("光标不在当前草稿内。")
        # One window gets one virtual document; two tabs editing the same attempt
        # never replace each other's unsaved text. No virtual source is written.
        uri = path.with_name(f".workbench-{session}.cpp").as_uri()
        with self.lock:
            if self.client and (self.client.failed or self.client.process.poll() is not None):
                self.client.close()
                self.client = None
                self.documents.clear()
            if self.client is None:
                binary = find_clangd()
                if not binary:
                    raise AppError(self.status()["message"], 503)
                self.client = Clangd(binary, self.repository.root)
            document = self.documents.get(session)
            if document and version < document["version"]:
                return {"stale": True, "version": version}
            digest = revision(source)
            if document and version == document["version"] and (uri != document["uri"] or digest != document["digest"]):
                raise AppError("草稿版本不一致，请刷新页面后重试。", 409)
            # Close inactive buffers and cap retention even if a tab exits abruptly.
            for key, old in list(self.documents.items()):
                if key != session and (time.monotonic() - old["used"] > 600 or len(self.documents) >= 16):
                    self.client.forget(old["uri"])
                    del self.documents[key]
            if document and document["uri"] != uri:
                self.client.forget(document["uri"])
                document = None
            if document is None:
                self.client.send("textDocument/didOpen", {"textDocument": {
                    "uri": uri, "languageId": "cpp", "version": version, "text": source}})
            elif document["version"] != version:
                self.client.send("textDocument/didChange", {
                    "textDocument": {"uri": uri, "version": version}, "contentChanges": [{"text": source}]})
            self.documents[session] = {"uri": uri, "version": version, "digest": digest, "used": time.monotonic()}
            if action == "diagnostics":
                result = self.client.wait_diagnostics(uri, version)
            else:
                # Cold completion otherwise uses clangd's lexical fallback before
                # the standard-library preamble exists (e.g. vector.push_back).
                if document is None:
                    self.client.wait_diagnostics(uri, version)
                method = {"completion": "completion", "signature": "signatureHelp", "hover": "hover"}[action]
                result = self.client.request("textDocument/" + method,
                                             {"textDocument": {"uri": uri}, "position": position})
            return {"version": version, "result": result}
