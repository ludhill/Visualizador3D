import os
import re
import sys
import time
import hmac
import json
import ssl
import struct
import socket
import threading
import unicodedata
import webbrowser
from datetime import datetime
from urllib.parse import unquote
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

# Locks globais para escrita segura em disco e controle de tentativas de PIN
telemetry_file_lock = threading.Lock()
upload_file_lock = threading.Lock()
SERVER_PAUSED = False
httpd_instance = None

# Controle de tentativas de PIN por IP: { ip: {"fails": int, "locked_until": float} }
admin_attempts = {}
admin_lock = threading.Lock()

# ==============================================================================
# CONFIGURAÇÕES GERAIS E SEGURANÇA
# ==============================================================================
API_TOKEN = "WEBAR_2026"
ADMIN_PIN = "2026"
PORT = 8080

MAX_GLB_BYTES = 25 * 1024 * 1024   # 25 MB
MAX_MIND_BYTES = 15 * 1024 * 1024  # 15 MB

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
JSON_PATH = os.path.join(BASE_DIR, 'storage', 'db', 'data.json')
TELEMETRY_PATH = os.path.join(BASE_DIR, 'storage', 'db', 'telemetry.json')
MODELS_DIR = os.path.join(BASE_DIR, 'storage', 'models')
TARGETS_DIR = os.path.join(BASE_DIR, 'storage', 'targets')

# Caminhos e extensões bloqueados para leitura direta via navegador
BLOCKED_PREFIXES = ('/backend', '/storage/db', '/.git', '/.vscode')
BLOCKED_EXTENSIONS = ('.py', '.pem', '.key', '.sh', '.bat', '.md', '.gitignore')


def get_local_ip():
    """
    Descobre dinamicamente o IP privado da máquina host na rede local.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


def slugify_filename(raw_name, expected_ext):
    """
    Remove acentos, espaços e caracteres inválidos para gerar nomes seguros em URL.
    Ex: 'Foguete Sonda IV (Final!).glb' -> 'foguete-sonda-iv-final.glb'
    """
    base_name = os.path.basename(unquote(raw_name or '')).strip()
    stem, ext = os.path.splitext(base_name)
    if ext.lower() != expected_ext:
        return None

    normalized = unicodedata.normalize('NFKD', stem).encode('ascii', 'ignore').decode('ascii')
    slug = re.sub(r'[^a-zA-Z0-9_-]+', '-', normalized).strip('-_').lower()
    if not slug:
        slug = f"ativo-{int(time.time())}"
    return f"{slug}{expected_ext}"


def validate_binary_asset(data, upload_type):
    """
    Valida os magic bytes do arquivo enviado para impedir extensões falsificadas.
    """
    if upload_type == 'model':
        if len(data) < 12 or data[:4] != b'glTF':
            return False, "Arquivo inválido: o cabeçalho binário não corresponde a um modelo .glb (glTF 2.0)."
        version = struct.unpack('<I', data[4:8])[0]
        if version != 2:
            return False, f"Versão glTF não suportada ({version}). Exporte o modelo como glTF 2.0 (.glb)."
        return True, "OK"

    if upload_type == 'target':
        if len(data) < 64:
            return False, "Arquivo .mind vazio ou corrompido."
        if data.startswith(b'\xff\xd8\xff') or data.startswith(b'\x89PNG'):
            return False, "Você enviou uma imagem JPG/PNG renomeada. Compile as imagens no MindAR Compiler para gerar um .mind válido."
        if data[:4] in (b'glTF', b'PK\x03\x04', b'%PDF') or data.lstrip()[:1] in (b'<', b'{'):
            return False, "Arquivo inválido: o conteúdo não é um pacote compilado .mind."
        return True, "OK"

    return False, "Tipo de upload desconhecido."


class CMSRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def send_json(self, status_code, payload):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode('utf-8'))

    def check_authorization(self):
        client_token = self.headers.get('X-App-Token')

        if not client_token and '?token=' in self.path:
            try:
                query = self.path.split('?', 1)[1]
                params = dict(param.split('=', 1) for param in query.split('&') if '=' in param)
                client_token = params.get('token')
            except Exception:
                client_token = None

        return client_token == API_TOKEN

    def check_admin_authorization(self):
        client_pin = (self.headers.get('X-Admin-Pin') or '').strip()
        if not client_pin:
            return False
        return hmac.compare_digest(client_pin, ADMIN_PIN)

    def list_directory(self, path):
        self.send_json(403, {
            "status": "error",
            "message": "Acesso negado. Navegação de diretórios desativada."
        })
        return None

    def end_headers(self):
        clean_path = unquote(self.path.split('?')[0])

        if clean_path.startswith('/api/'):
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
            self.send_header('Pragma', 'no-cache')
        elif clean_path.endswith('sw.js'):
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        elif clean_path.endswith(('.glb', '.mind')):
            self.send_header('Cache-Control', 'public, max-age=0, must-revalidate')
        elif clean_path.endswith(('.js', '.css', '.png', '.jpg', '.jpeg', '.webp', '.svg')):
            self.send_header('Cache-Control', 'public, max-age=86400')

        super().end_headers()

    def do_GET(self):
        raw_path = self.path.split('?')[0]
        clean_path = unquote(raw_path).rstrip('/') or '/'
        query_string = f"?{self.path.split('?', 1)[1]}" if '?' in self.path else ''

        # 1. Redirecionamentos Inteligentes de Entrada
        if clean_path == '/':
            self.send_response(302)
            self.send_header('Location', f'/frontend/ar-engine/index.html{query_string}')
            self.end_headers()
            return

        if clean_path in ('/cms', '/qrcode', '/admin'):
            self.send_response(302)
            self.send_header('Location', '/frontend/cms/qrcode.html')
            self.end_headers()
            return

        # 2. Blindagem de Arquivos Internos e Diretórios Sensíveis
        lower_path = clean_path.lower()
        if lower_path.startswith(BLOCKED_PREFIXES) or lower_path.endswith(BLOCKED_EXTENSIONS):
            self.send_json(403, {
                "status": "error",
                "message": "Acesso proibido a recursos internos do servidor."
            })
            return

        # 3. Rota de Descoberta de IP e URL do QR Code
        if clean_path == '/api/server-info':
            local_ip = get_local_ip()
            webar_url = f"https://{local_ip}:{PORT}/frontend/ar-engine/index.html?token={API_TOKEN}"
            client_ip = self.client_address[0]
            now = time.time()
            locked_seconds = 0

            with admin_lock:
                record = admin_attempts.get(client_ip)
                if record and record.get("locked_until", 0) > now:
                    locked_seconds = int(record["locked_until"] - now) + 1

            self.send_json(200, {
                "ip": local_ip,
                "port": PORT,
                "token": API_TOKEN,
                "paused": SERVER_PAUSED,
                "adminLockedSeconds": locked_seconds,
                "webArUrl": webar_url
            })
            return

        # 4. Rota de Analytics: Agregação Estatística
        if clean_path == '/api/analytics':
            empty_analytics = {
                "totalSessions": 0,
                "averageSessionSeconds": 0,
                "viewsByTarget": {},
                "hourlyActivity": [0] * 24
            }

            if not os.path.exists(TELEMETRY_PATH):
                self.send_json(200, empty_analytics)
                return

            try:
                with open(TELEMETRY_PATH, 'r', encoding='utf-8') as f:
                    telemetry_store = json.load(f)

                logs = telemetry_store.get("logs", [])
                total_duration = 0
                completed_count = 0
                hourly_activity = [0] * 24

                for log in logs:
                    ts = log.get("timestamp")
                    if ts:
                        try:
                            time_part = ts.split('T')[1]
                            hour = int(time_part.split(':')[0])
                            if 0 <= hour < 24:
                                hourly_activity[hour] += 1
                        except Exception:
                            pass

                    if log.get("event") == "session_end" and "sessionDurationSeconds" in log:
                        total_duration += log.get("sessionDurationSeconds", 0)
                        completed_count += 1

                avg_seconds = round(total_duration / completed_count) if completed_count > 0 else 0

                self.send_json(200, {
                    "totalSessions": telemetry_store.get("totalSessions", 0),
                    "averageSessionSeconds": avg_seconds,
                    "viewsByTarget": telemetry_store.get("targetViews", {}),
                    "hourlyActivity": hourly_activity
                })
            except Exception:
                self.send_json(200, empty_analytics)
            return

        # 5. Inventário de Ativos (.glb e targets.mind) para o CMS (Admin)
        if clean_path == '/api/assets':
            if not self.check_authorization() or not self.check_admin_authorization():
                self.send_json(401, {"status": "unauthorized", "message": "Acesso administrativo necessário."})
                return

            os.makedirs(MODELS_DIR, exist_ok=True)
            os.makedirs(TARGETS_DIR, exist_ok=True)

            models = []
            for fname in sorted(os.listdir(MODELS_DIR)):
                if fname.lower().endswith('.glb'):
                    full_path = os.path.join(MODELS_DIR, fname)
                    if os.path.isfile(full_path):
                        models.append({
                            "name": fname,
                            "sizeBytes": os.path.getsize(full_path)
                        })

            mind_path = os.path.join(TARGETS_DIR, 'targets.mind')
            target_info = {"exists": False, "sizeBytes": 0, "updatedAt": None}
            if os.path.isfile(mind_path):
                stat = os.stat(mind_path)
                target_info = {
                    "exists": True,
                    "sizeBytes": stat.st_size,
                    "updatedAt": datetime.fromtimestamp(stat.st_mtime).strftime('%d/%m/%Y %H:%M:%S')
                }

            self.send_json(200, {
                "models": models,
                "targetBundle": target_info
            })
            return

        # 6. Proteção por Token nas APIs e Modelos 3D (.glb)
        if clean_path in ('/api/config', '/api/telemetry') or lower_path.endswith('.glb'):
            if not self.check_authorization():
                self.send_json(403, {
                    "status": "error",
                    "message": "Acesso não autorizado. Token ausente ou inválido."
                })
                return

        if clean_path == '/api/config':
            is_dashboard = 'dashboard=1' in self.path
            if SERVER_PAUSED and not is_dashboard:
                self.send_json(503, {
                    "status": "paused",
                    "message": "Exposição temporariamente pausada pelo apresentador."
                })
                return

            if os.path.exists(JSON_PATH):
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                with open(JSON_PATH, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_json(404, {"status": "error", "message": "Arquivo data.json não encontrado."})
            return

        if clean_path == '/api/telemetry':
            if os.path.exists(TELEMETRY_PATH):
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                with open(TELEMETRY_PATH, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_json(200, {"totalSessions": 0, "targetViews": {}, "logs": []})
            return

        # 7. Entrega de Arquivos Estáticos Públicos
        return super().do_GET()

    def do_POST(self):
        clean_path = unquote(self.path.split('?')[0]).rstrip('/')

        if clean_path.startswith('/api/'):
            if not self.check_authorization():
                self.send_json(403, {"status": "error", "message": "Acesso não autorizado."})
                return

        content_length = int(self.headers.get('Content-Length', 0))

        # ----------------------------------------------------------------------
        # Upload Dinâmico de Ativos (.glb e .mind) — Protegido por X-Admin-Pin
        # ----------------------------------------------------------------------
        if clean_path == '/api/upload':
            if not self.check_admin_authorization():
                self.send_json(401, {
                    "status": "unauthorized",
                    "message": "Ação bloqueada: PIN administrativo ausente ou expirado."
                })
                return

            upload_type = (self.headers.get('X-Upload-Type') or '').strip().lower()
            raw_filename = self.headers.get('X-File-Name') or ''

            if upload_type not in ('model', 'target'):
                self.send_json(400, {"status": "error", "message": "Cabeçalho X-Upload-Type deve ser 'model' ou 'target'."})
                return

            max_bytes = MAX_GLB_BYTES if upload_type == 'model' else MAX_MIND_BYTES
            if content_length <= 0:
                self.send_json(400, {"status": "error", "message": "Nenhum dado binário recebido."})
                return

            if content_length > max_bytes:
                limit_mb = max_bytes // (1024 * 1024)
                self.send_json(413, {
                    "status": "error",
                    "message": f"Arquivo excede o limite máximo permitido ({limit_mb} MB)."
                })
                return

            expected_ext = '.glb' if upload_type == 'model' else '.mind'
            safe_name = slugify_filename(raw_filename, expected_ext)
            if not safe_name:
                self.send_json(400, {
                    "status": "error",
                    "message": f"Extensão inválida. Envie estritamente um arquivo {expected_ext}."
                })
                return

            file_bytes = self.rfile.read(content_length)
            is_valid, reason = validate_binary_asset(file_bytes, upload_type)
            if not is_valid:
                self.send_json(400, {"status": "error", "message": reason})
                return

            try:
                with upload_file_lock:
                    if upload_type == 'model':
                        os.makedirs(MODELS_DIR, exist_ok=True)
                        final_name = safe_name
                        dest_path = os.path.join(MODELS_DIR, final_name)
                    else:
                        os.makedirs(TARGETS_DIR, exist_ok=True)
                        final_name = 'targets.mind'
                        dest_path = os.path.join(TARGETS_DIR, final_name)

                    tmp_path = f"{dest_path}.tmp"
                    with open(tmp_path, 'wb') as f:
                        f.write(file_bytes)
                    os.replace(tmp_path, dest_path)

                print(f" [CMS Upload] Ativo salvo: {final_name} ({len(file_bytes)} bytes)")
                self.send_json(200, {
                    "status": "success",
                    "uploadType": upload_type,
                    "fileName": final_name,
                    "sizeBytes": len(file_bytes),
                    "message": f"Arquivo '{final_name}' enviado e validado com sucesso!"
                })
            except Exception as e:
                self.send_json(500, {"status": "error", "message": f"Falha ao gravar arquivo: {str(e)}"})
            return

        post_data = self.rfile.read(content_length) if content_length > 0 else b''

        # ----------------------------------------------------------------------
        # Validação do PIN Administrativo (com limite de tentativas)
        # ----------------------------------------------------------------------
        if clean_path == '/api/admin/verify-pin':
            client_ip = self.client_address[0]
            now = time.time()

            with admin_lock:
                record = admin_attempts.get(client_ip, {"fails": 0, "locked_until": 0})
                if record["locked_until"] > now:
                    wait_sec = int(record["locked_until"] - now) + 1
                    self.send_json(429, {
                        "status": "locked",
                        "retryAfter": wait_sec,
                        "message": f"IP bloqueado temporariamente. Aguarde {wait_sec}s."
                    })
                    return

            try:
                body = json.loads(post_data.decode('utf-8')) if post_data else {}
                submitted_pin = str(body.get("pin", "")).strip()
            except Exception:
                submitted_pin = ""

            if submitted_pin and hmac.compare_digest(submitted_pin, ADMIN_PIN):
                with admin_lock:
                    admin_attempts.pop(client_ip, None)
                self.send_json(200, {
                    "status": "authorized",
                    "message": "Painel administrativo desbloqueado."
                })
            else:
                with admin_lock:
                    fails = record.get("fails", 0) + 1
                    if fails >= 5:
                        record["locked_until"] = now + 30
                        record["fails"] = 0
                        admin_attempts[client_ip] = record
                        self.send_json(429, {
                            "status": "locked",
                            "retryAfter": 30,
                            "message": "5 tentativas incorretas. IP bloqueado por 30s."
                        })
                        return

                    record["fails"] = fails
                    admin_attempts[client_ip] = record
                    remaining = 5 - fails

                self.send_json(401, {
                    "status": "unauthorized",
                    "remainingAttempts": remaining,
                    "message": f"PIN incorreto. Restam {remaining} tentativa(s)."
                })
            return

        # ----------------------------------------------------------------------
        # Telemetria dos Visitantes (exige apenas X-App-Token)
        # ----------------------------------------------------------------------
        if clean_path == '/api/telemetry':
            try:
                event_data = json.loads(post_data.decode('utf-8'))
                os.makedirs(os.path.dirname(TELEMETRY_PATH), exist_ok=True)

                with telemetry_file_lock:
                    telemetry_store = {
                        "totalSessions": 0,
                        "targetViews": {},
                        "logs": []
                    }

                    if os.path.exists(TELEMETRY_PATH):
                        try:
                            with open(TELEMETRY_PATH, 'r', encoding='utf-8') as f:
                                telemetry_store = json.load(f)
                        except Exception:
                            pass

                    event_type = event_data.get("event")

                    if event_type == "session_start":
                        telemetry_store["totalSessions"] = telemetry_store.get("totalSessions", 0) + 1
                    elif event_type == "target_found":
                        target_idx = str(event_data.get("targetIndex", "unknown"))
                        views = telemetry_store.get("targetViews", {})
                        views[target_idx] = views.get(target_idx, 0) + 1
                        telemetry_store["targetViews"] = views

                    telemetry_store["logs"].append(event_data)

                    if len(telemetry_store["logs"]) > 500:
                        telemetry_store["logs"] = telemetry_store["logs"][-500:]

                    with open(TELEMETRY_PATH, 'w', encoding='utf-8') as f:
                        json.dump(telemetry_store, f, indent=2, ensure_ascii=False)

                self.send_json(200, {"status": "recorded"})
            except Exception as e:
                self.send_json(500, {"status": "error", "message": str(e)})
            return

        # ----------------------------------------------------------------------
        # Rotas Administrativas Protegidas por X-Admin-Pin
        # ----------------------------------------------------------------------
        if clean_path in ('/api/config', '/api/toggle-pause', '/api/shutdown'):
            if not self.check_admin_authorization():
                self.send_json(401, {
                    "status": "unauthorized",
                    "message": "Ação bloqueada: PIN administrativo ausente ou expirado."
                })
                return

        if clean_path == '/api/config':
            try:
                parsed_json = json.loads(post_data.decode('utf-8'))
                os.makedirs(os.path.dirname(JSON_PATH), exist_ok=True)
                with open(JSON_PATH, 'w', encoding='utf-8') as f:
                    json.dump(parsed_json, f, indent=2, ensure_ascii=False)

                self.send_json(200, {"status": "success", "message": "Configuração salva!"})
            except Exception as e:
                self.send_json(500, {"status": "error", "message": str(e)})
            return

        if clean_path == '/api/toggle-pause':
            global SERVER_PAUSED
            SERVER_PAUSED = not SERVER_PAUSED
            estado = "pausada" if SERVER_PAUSED else "ativa"
            print(f" [CMS] Experiência WebAR {estado} pelo apresentador.")
            self.send_json(200, {
                "status": "success",
                "paused": SERVER_PAUSED,
                "message": f"Exposição {estado}."
            })
            return

        if clean_path == '/api/shutdown':
            print(" [CMS] Encerramento solicitado pelo Dashboard. Finalizando servidor...")
            self.send_json(200, {
                "status": "shutting_down",
                "message": "Servidor encerrado com segurança."
            })
            if httpd_instance:
                threading.Thread(target=httpd_instance.shutdown, daemon=True).start()
            return

        self.send_json(404, {"status": "error", "message": "Endpoint não encontrado."})


def open_presenter_panel(protocol):
    url = f"{protocol}://localhost:{PORT}/frontend/cms/qrcode.html"
    try:
        webbrowser.open(url)
    except Exception:
        pass


if __name__ == '__main__':
    ThreadingHTTPServer.allow_reuse_address = True
    server_address = ('', PORT)

    try:
        httpd = ThreadingHTTPServer(server_address, CMSRequestHandler)
        httpd_instance = httpd
    except OSError:
        print(f" [AVISO] A porta {PORT} já está em uso (o servidor provavelmente já está ativo).")
        sys.exit(1)

    cert_file = os.path.join(BASE_DIR, 'cert.pem')
    key_file = os.path.join(BASE_DIR, 'key.pem')

    if os.path.exists(cert_file) and os.path.exists(key_file):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=cert_file, keyfile=key_file)
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
        protocol = "https"
        print(f" Servidor HTTPS WebAR-CMS ativo na porta {PORT}...")
    else:
        protocol = "http"
        print(f" Certificados SSL não encontrados. Servidor rodando em HTTP (Porta {PORT})...")

    print(f" Painel QR Code: {protocol}://localhost:{PORT}/cms")

    timer = threading.Timer(1.2, open_presenter_panel, args=[protocol])
    timer.daemon = True
    timer.start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n Servidor finalizado.")
    finally:
        httpd.server_close()