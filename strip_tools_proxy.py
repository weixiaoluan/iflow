"""轻量 HTTP 反向代理：剥离请求中的 tools/tool_choice 参数后转发到 CLIProxyAPI。

iFlow API 不支持 OpenAI function-calling (tools) 参数，会返回 406。
本模块在用户端口与 CLIProxyAPI 之间架设一层代理，自动清除这些字段。
"""

import http.client
import http.server
import json
import socketserver
import threading


class StripToolsHandler(http.server.BaseHTTPRequestHandler):
    """剥离 tools 参数的 HTTP 请求处理器"""

    backend_port = 8318  # 运行时由 start_proxy() 覆盖

    # ------------------------------------------------------------------ #
    #  核心转发逻辑
    # ------------------------------------------------------------------ #
    def _forward(self, method):
        # 读取请求体
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length > 0 else None

        # 对 chat/completions 请求剥离 tools / tool_choice
        if method == "POST" and body and "/chat/completions" in self.path:
            try:
                data = json.loads(body)
                changed = False
                if "tools" in data:
                    del data["tools"]
                    changed = True
                if "tool_choice" in data:
                    del data["tool_choice"]
                    changed = True
                if changed:
                    body = json.dumps(data).encode("utf-8")
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

        # 转发头部（跳过 hop-by-hop）
        fwd = {}
        for k, v in self.headers.items():
            if k.lower() not in ("host", "content-length", "transfer-encoding"):
                fwd[k] = v
        if body is not None:
            fwd["Content-Length"] = str(len(body))

        try:
            conn = http.client.HTTPConnection(
                "127.0.0.1", self.backend_port, timeout=300
            )
            conn.request(method, self.path, body=body, headers=fwd)
            resp = conn.getresponse()

            # 回写状态码
            self.send_response_only(resp.status)
            for k, v in resp.getheaders():
                if k.lower() not in ("transfer-encoding",):
                    self.send_header(k, v)
            self.end_headers()

            # 流式转发响应体
            while True:
                chunk = resp.read(4096)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()

            conn.close()
        except Exception as e:
            try:
                self.send_error(502, f"Backend error: {e}")
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    #  HTTP 方法映射
    # ------------------------------------------------------------------ #
    def do_GET(self):
        self._forward("GET")

    def do_POST(self):
        self._forward("POST")

    def do_OPTIONS(self):
        self._forward("OPTIONS")

    def do_PUT(self):
        self._forward("PUT")

    def do_DELETE(self):
        self._forward("DELETE")

    def log_message(self, format, *args):
        """静默日志"""
        pass


class _ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def start_strip_proxy(listen_port, backend_port):
    """在后台线程启动 strip-tools 代理，返回 HTTPServer 实例（可调用 .shutdown()）"""
    StripToolsHandler.backend_port = backend_port
    server = _ThreadedServer(("127.0.0.1", listen_port), StripToolsHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server
