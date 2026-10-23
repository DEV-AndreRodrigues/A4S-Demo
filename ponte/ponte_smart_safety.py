#!/usr/bin/env python3
"""
Ponte local do gerador de demonstração Smart Safety.

Duas funções:
1. /send  – recebe o frame do Botão de Pânico e repassa à plataforma por TCP
            (mesmo protocolo do panico.py: JSON + quebra de linha, leitura de ack).
2. /api   – repassa consultas GET da página à API REST da Smart Suite. O navegador
            bloqueia a chamada direta (CORS, página aberta como arquivo local);
            daqui do Python esse bloqueio não existe.

Uso:  python3 ponte_smart_safety.py
Só stdlib. Deixe a janela aberta durante a demonstração (Ctrl+C encerra).

Configuração: ponte.config.json na mesma pasta (copie de ponte.config.example.json
e preencha com os dados recebidos pelo canal interno). Esse arquivo NÃO vai para o
GitHub. Variáveis de ambiente SS_HOST, SS_PORT, BRIDGE_PORT e BRIDGE_ALLOWED_ORIGINS
têm prioridade sobre o arquivo.
"""
import json
import os
import re
import socket
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

def _load_config():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ponte.config.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except ValueError as e:
        raise SystemExit(f"ponte.config.json inválido: {e}")


_CFG = _load_config()
TARGET_HOST = os.environ.get("SS_HOST") or _CFG.get("tcp_host") or ""
if TARGET_HOST.startswith("DEFINIR"):
    TARGET_HOST = ""
TARGET_PORT = int(os.environ.get("SS_PORT") or _CFG.get("tcp_port") or 0)
LISTEN_PORT = int(os.environ.get("BRIDGE_PORT") or _CFG.get("bridge_port") or 8765)
_env_origins = os.environ.get("BRIDGE_ALLOWED_ORIGINS")
ALLOWED_ORIGINS = set(o.strip() for o in _env_origins.split(",")) if _env_origins else set(_CFG.get("allowed_origins") or ["null"])

# Só aceita o frame do Botão de Pânico. Ampliar aqui quando outros tipos forem definidos.
ALLOWED = {(12, 100)}
KEYS = ["type", "id", "code", "data", "date", "messageId"]
RE_DATA = re.compile(r"^[0-9A-F]{16}$")
RE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
RE_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

# Proxy da API: só GET, só domínios a4s.io, só as rotas que a página usa.
RE_UPSTREAM_HOST = re.compile(os.environ.get("BRIDGE_ALLOWED_HOST_RE", r"^([a-z0-9-]+\.)*a4s\.io$"))
RE_UPSTREAM_PATH = re.compile(r"^(/api)?/(platform/(employees(/[A-Za-z0-9_-]+)?|places|devices|panic-alerts/codes)|version)(/|$)")
FORWARD_HEADERS = ("accept", "authorization")
HOP_BY_HOP = {"x-upstream-url"}


def validate(frame):
    if not isinstance(frame, dict) or sorted(frame) != sorted(KEYS):
        return "frame com campos inesperados"
    if (frame["type"], frame["code"]) not in ALLOWED:
        return "type/code não permitido pela ponte"
    if not isinstance(frame["id"], str) or not RE_ID.match(frame["id"]):
        return "id do CORE inválido"
    if not isinstance(frame["data"], str) or not RE_DATA.match(frame["data"]):
        return "data precisa ter 16 caracteres hexadecimais"
    if not isinstance(frame["date"], str) or not RE_DATE.match(frame["date"]):
        return "date fora do formato UTC"
    return None


def forward(frame):
    if not TARGET_HOST or not TARGET_PORT:
        raise OSError("destino TCP não configurado (preencha ponte.config.json)")
    ordered = {k: frame[k] for k in KEYS}  # mesma ordem do panico.py
    payload = json.dumps(ordered, separators=(",", ":"))
    with socket.create_connection((TARGET_HOST, TARGET_PORT), timeout=10) as s:
        s.sendall((payload + "\n").encode("utf-8"))
        s.settimeout(6)
        try:
            ack = s.recv(4096).decode("utf-8", "replace").strip()
        except socket.timeout:
            ack = ""
    return payload, ack


def upstream_ok(url):
    try:
        u = urlsplit(url)
    except ValueError:
        return False
    scheme_ok = u.scheme == "https" or os.environ.get("BRIDGE_ALLOW_HTTP") == "1"
    return scheme_ok and bool(RE_UPSTREAM_HOST.match(u.hostname or "")) and bool(RE_UPSTREAM_PATH.match(u.path or ""))


class Handler(BaseHTTPRequestHandler):
    server_version = "PonteSmartSafety/1.0"

    def _origin(self):
        return self.headers.get("Origin")

    def _origin_ok(self):
        # Aceita só as origens configuradas (arquivo local = "null", site do GitHub Pages)
        # ou chamadas sem Origin (curl). Bloqueia qualquer outro site.
        o = self._origin()
        return o is None or o in ALLOWED_ORIGINS

    def _cors_origin(self):
        o = self._origin()
        return o if o in ALLOWED_ORIGINS else "null"

    def _send(self, status, body):
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", self._cors_origin())
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", self._cors_origin())
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        req_h = self.headers.get("Access-Control-Request-Headers") or "Content-Type"
        self.send_header("Access-Control-Allow-Headers", req_h)
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.end_headers()

    def do_GET(self):
        if not self._origin_ok():
            return self._send(403, {"ok": False, "error": "origem não permitida"})
        if self.path == "/health":
            return self._send(200, {"ok": True, "api_proxy": True})
        if self.path == "/api":
            return self._proxy_get()
        self._send(404, {"ok": False, "error": "rota inexistente"})

    def _proxy_get(self):
        url = self.headers.get("X-Upstream-Url", "")
        if not upstream_ok(url):
            return self._send(403, {"ok": False, "error": "destino não permitido pela ponte (só GET em rotas de colaboradores, locais, dispositivos e códigos de pânico em *.a4s.io)"})
        headers = {}
        for k, v in self.headers.items():
            lk = k.lower()
            if lk in FORWARD_HEADERS or (lk.startswith("x-") and lk not in HOP_BY_HOP):
                headers[k] = v
        req = urllib.request.Request(url, headers=headers, method="GET")
        path = urlsplit(url).path
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                status, body, ctype = r.status, r.read(), r.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as e:
            status, body, ctype = e.code, e.read(), e.headers.get("Content-Type", "application/json")
        except (urllib.error.URLError, OSError) as e:
            print(f"[{datetime.now():%H:%M:%S}] API {path} FALHA: {e}")
            return self._send(502, {"ok": False, "error": f"a ponte não alcançou a API: {e}"})
        print(f"[{datetime.now():%H:%M:%S}] API GET {path} -> HTTP {status}")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", self._cors_origin())
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not self._origin_ok():
            return self._send(403, {"ok": False, "error": "origem não permitida"})
        if self.path != "/send":
            return self._send(404, {"ok": False, "error": "rota inexistente"})
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 4096:
            return self._send(400, {"ok": False, "error": "corpo vazio ou grande demais"})
        try:
            frame = json.loads(self.rfile.read(length)).get("frame")
        except (ValueError, AttributeError):
            return self._send(400, {"ok": False, "error": "JSON inválido"})
        err = validate(frame)
        if err:
            return self._send(400, {"ok": False, "error": err})
        try:
            payload, ack = forward(frame)
        except OSError as e:
            print(f"[{datetime.now():%H:%M:%S}] FALHA TCP: {e}")
            return self._send(502, {"ok": False, "error": f"falha TCP: {e}"})
        print(f"[{datetime.now():%H:%M:%S}] enviado: {payload}  ack: {ack or '(sem resposta em 6s)'}")
        self._send(200, {"ok": True, "ack": ack, "sent": payload})

    def log_message(self, *args):
        pass  # o log útil é impresso em do_POST


def main():
    bind = os.environ.get("BRIDGE_BIND", "127.0.0.1")
    srv = ThreadingHTTPServer((bind, LISTEN_PORT), Handler)
    print(f"Ponte Smart Safety ativa em http://{bind}:{LISTEN_PORT}")
    print(f"Destino TCP: {'configurado' if TARGET_HOST and TARGET_PORT else 'NÃO configurado (Botão de Pânico não envia)'}")
    print(f"Origens permitidas: {', '.join(sorted(ALLOWED_ORIGINS))}")
    print("Proxy da API REST: ativo (GET, *.a4s.io)")
    print("Deixe esta janela aberta durante a demonstração. Ctrl+C para encerrar.\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nPonte encerrada.")


if __name__ == "__main__":
    main()
