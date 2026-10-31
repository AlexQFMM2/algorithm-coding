"""Loopback-only HTTP application, using Python's standard library."""
import argparse
import errno
import json
import mimetypes
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

from .judge import Judge
from .language import LanguageService
from .repository import AppError, Repository
from .visualization import VisualizationRunner, list_visualizations, read_visualization

PUBLIC = Path(__file__).parent / "static"


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, root, port):
        self.repository = Repository(root)
        self.judge = Judge(self.repository)
        self.visualization = VisualizationRunner(self.repository, self.judge.lock)
        self.token = secrets.token_urlsafe(32)
        super().__init__(("127.0.0.1", port), Handler)
        self.language = LanguageService(self.repository)

    def server_close(self):
        if hasattr(self, "language"):
            self.language.close()
        super().server_close()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format_string, *args):
        # The durable logs live beside each problem; keep the launch terminal quiet.
        if args and str(args[1] if len(args) > 1 else "").startswith("5"):
            super().log_message(format_string, *args)

    def respond(self, content, status=200, content_type="application/json; charset=utf-8"):
        if isinstance(content, (dict, list)):
            content = json.dumps(content, ensure_ascii=False).encode("utf-8")
        elif isinstance(content, str):
            content = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(content)

    def validate_request(self, mutation=False):
        port = self.server.server_port
        allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        host = self.headers.get("Host")
        if host not in allowed_hosts:
            raise AppError("只允许从本机地址访问。", 403)
        origin = self.headers.get("Origin")
        if origin and origin not in {f"http://{item}" for item in allowed_hosts}:
            raise AppError("不允许跨站请求。", 403)
        if mutation and not secrets.compare_digest(self.headers.get("X-Workbench-Token", ""), self.server.token):
            raise AppError("应用已重启，请刷新页面后重试。", 403)

    def handle_error(self, error):
        if isinstance(error, (BrokenPipeError, ConnectionResetError)):
            return
        status = error.status if isinstance(error, AppError) else 500
        self.respond({"error": str(error) if isinstance(error, AppError) else f"操作失败：{error}"}, status)

    def do_GET(self):
        try:
            self.validate_request()
            parsed = urlparse(self.path)
            query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            repo = self.server.repository
            if parsed.path == "/api/state":
                return self.respond({"problems": repo.list_problems(), "token": self.server.token,
                                     "root": str(repo.root), "language": self.server.language.status()})
            if parsed.path == "/api/problem":
                return self.respond(repo.detail(query.get("id")))
            if parsed.path == "/api/attempt":
                return self.respond(repo.read_attempt(query.get("problem"), query.get("attempt")))
            if parsed.path == "/api/document":
                return self.respond(repo.document(query.get("path", "")))
            if parsed.path == "/api/visualizations":
                return self.respond({"runs": list_visualizations(repo, query.get("problem"))})
            if parsed.path == "/api/visualization":
                return self.respond(read_visualization(repo, query.get("problem"), query.get("run")))
            if parsed.path == "/api/run":
                return self.respond(repo.read_run(query.get("problem"), query.get("run")))
            filename = "index.html" if parsed.path == "/" else parsed.path.removeprefix("/")
            path = (PUBLIC / filename).resolve()
            if not path.is_relative_to(PUBLIC.resolve()) or not path.is_file():
                raise AppError("页面不存在。", 404)
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self.respond(path.read_bytes(), content_type=content_type + "; charset=utf-8")
        except Exception as error:
            self.handle_error(error)

    def do_POST(self):
        try:
            self.validate_request(mutation=True)
            if self.headers.get_content_type() != "application/json":
                raise AppError("请求必须是 JSON。", 415)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 3_000_000:
                    raise AppError("请求内容为空或过大。", 413)
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("需要 JSON 对象")
            except (ValueError, UnicodeError) as error:
                raise AppError("请求内容格式错误。") from error
            repo = self.server.repository
            if self.path == "/api/language":
                return self.respond(self.server.language.handle(payload))
            if self.path == "/api/attempt/new":
                source = None
                if payload.get("from_reference"):
                    path = repo.contained(repo.problem(payload.get("problem")) / "main.cpp")
                    if path.is_file():
                        source = path.read_text(encoding="utf-8")
                return self.respond(repo.create_attempt(payload.get("problem"), source), 201)
            if self.path == "/api/attempt/save":
                return self.respond(repo.save_attempt(payload.get("problem"), payload.get("attempt"),
                                                      payload.get("source"), payload.get("revision")))
            if self.path == "/api/visualizations":
                return self.respond(self.server.visualization.run(payload.get("problem"), payload.get("input_mode", "sample"),
                                                                  payload.get("input", ""), payload.get("sample", 0)))
            if self.path == "/api/run":
                return self.respond(self.server.judge.run(payload.get("problem"), payload.get("attempt"),
                                                          payload.get("revision"), payload.get("mode"),
                                                          payload.get("input", ""), payload.get("sample", 0)))
            raise AppError("接口不存在。", 404)
        except Exception as error:
            self.handle_error(error)


def workspace_is_running(root, port):
    """Recognize an existing instance, including instances started before this fix."""
    try:
        # This local probe must not be sent through a configured HTTP proxy.
        opener = build_opener(ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{port}/api/state", timeout=2) as response:
            state = json.loads(response.read(1_000_000))
        return (isinstance(state, dict)
                and isinstance(state.get("root"), str)
                and Path(state["root"]).resolve() == Path(root).resolve()
                and isinstance(state.get("problems"), list)
                and isinstance(state.get("token"), str)
                and bool(state["token"]))
    except (OSError, URLError, ValueError, TypeError):
        return False


def main():
    parser = argparse.ArgumentParser(description="启动本地算法练习室")
    parser.add_argument("--port", type=int, default=8765, help="本机端口，默认 8765")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent,
                        help="题目仓库目录")
    args = parser.parse_args()
    try:
        server = Server(args.root, args.port)
    except OSError as error:
        if error.errno == errno.EADDRINUSE:
            if workspace_is_running(args.root, args.port):
                url = f"http://127.0.0.1:{args.port}"
                print(f"\n算法练习室已经运行：{url}\n文件目录：{args.root.resolve()}\n已使用现有服务。\n", flush=True)
                if not args.no_browser:
                    webbrowser.open(url)
                return
            next_port = args.port + 1 if args.port < 65535 else 8765
            parser.exit(1, f"端口 {args.port} 已被其他程序或其他仓库的练习室占用。\n"
                          f"请使用 ./start.sh --port {next_port} 更换端口。\n")
        parser.exit(1, f"启动失败：{error}\n")
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"\n算法练习室已启动：{url}\n文件目录：{args.root.resolve()}\n按 Ctrl+C 停止。\n", flush=True)
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
