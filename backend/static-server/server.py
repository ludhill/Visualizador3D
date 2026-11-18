import os
import re
import sys
import time
import hmac
import json
import ssl
import shutil
import struct
import socket
import threading
import subprocess
import unicodedata
import webbrowser
import urllib.request
from datetime import datetime
from urllib.parse import unquote
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

# ==============================================================================
# CONFIGURAÇÕES GERAIS, PORTAS E SEGURANÇA
# ==============================================================================
API_TOKEN = "WEBAR_2026"
ADMIN_PIN = "2026"
MDNS_HOSTNAME = "cvtespacial.local"

CANDIDATE_PORTS = [8080, 8443, 8081, 8888]
ACTIVE_PORT = 8080
ACTIVE_PROTOCOL = "https"
SELECTED_IP = None  # Definido via UI (/api/select-ip) ou argumento --ip

MAX_GLB_BYTES = 25 * 1024 * 1024          # 25 MB
MAX_MIND_BYTES = 15 * 1024 * 1024         # 15 MB
MIN_FREE_DISK_BYTES = 100 * 1024 * 1024   # 100 MB livres exigidos para upload

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
JSON_PATH = os.path.join(BASE_DIR, 'storage', 'db', 'data.json')
TELEMETRY_PATH = os.path.join(BASE_DIR, 'storage', 'db', 'telemetry.json')
MODELS_DIR = os.path.join(BASE_DIR, 'storage', 'models')
TARGETS_DIR = os.path.join(BASE_DIR, 'storage', 'targets')

# Locks globais para escrita atômica e controle de tentativas administrativas
config_file_lock = threading.Lock()
telemetry_file_lock = threading.Lock()
upload_file_lock = threading.Lock()
admin_lock = threading.Lock()

SERVER_PAUSED = False
httpd_instance = None

# Controle de tentativas de PIN por IP: { ip: {"fails": int, "locked_until": float} }
admin_attempts = {}

# Caminhos e extensões bloqueados para leitura direta via navegador
BLOCKED_PREFIXES = ('/backend', '/storage/db', '/.git', '/.vscode')
BLOCKED_EXTENSIONS = ('.py', '.pem', '.key', '.sh', '.bat', '.md', '.gitignore', '.bak', '.tmp')


# ==============================================================================
# UTILITÁRIOS DE REDE (MULTI-IPV4), SSL E PERSISTÊNCIA RESILIENTE
# ==============================================================================
def is_valid_ipv4(ip_str):
    """Valida se a string possui formato estrito A.B.C.D de IPv4."""
    if not ip_str or len(ip_str.split('.')) != 4:
        return False
    try:
        socket.inet_aton(ip_str)
        return True
    except OSError:
        return False


def get_available_interfaces():
    """
    Lista todas as interfaces IPv4 ativas da máquina (ex: Wi-Fi e Ethernet 2),
    ignorando loopback (127.*) e endereço automático sem roteador (169.254.*),
    priorizando adaptadores sem fio (Wi-Fi / WLAN).
    """
    interfaces = []
    seen_ips = set()

    # 1. Windows: captura nome amigável do adaptador + IPv4 via ipconfig
    if os.name == 'nt':
        try:
            out = subprocess.check_output(['ipconfig'], stderr=subprocess.DEVNULL)
            text = out.decode('cp850', errors='replace')
            current_adapter = "Adaptador de Rede"

            for line in text.splitlines():
                stripped = line.strip()
                if line and not line.startswith(' ') and stripped.endswith(':'):
                    current_adapter = stripped[:-1]
                elif 'IPv4' in stripped and ':' in stripped:
                    ip = stripped.split(':', 1)[1].strip()
                    ip = re.sub(r'\(.*?\)', '', ip).strip()
                    if is_valid_ipv4(ip) and not ip.startswith(('127.', '169.254.')) and ip not in seen_ips:
                        seen_ips.add(ip)
                        interfaces.append({"name": current_adapter, "ip": ip})
        except Exception:
            pass

    # 2. Fallback multiplataforma (Linux / macOS / Windows) via socket
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if is_valid_ipv4(ip) and not ip.startswith(('127.', '169.254.')) and ip not in seen_ips:
                seen_ips.add(ip)
                interfaces.append({"name": "Interface Local", "ip": ip})
    except Exception:
        pass

    # 3. Garante detecção via rota padrão caso nenhuma interface tenha sido listada
    if not interfaces:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('10.255.255.255', 1))
            ip = s.getsockname()[0]
            if is_valid_ipv4(ip) and not ip.startswith(('127.', '169.254.')):
                interfaces.append({"name": "Rede Principal", "ip": ip})
        except Exception:
            pass
        finally:
            s.close()

    # Ordena: Wi-Fi primeiro (0), Ethernet/cabo depois (1), adaptadores virtuais por último (2)
    def sort_priority(item):
        label = item["name"].lower()
        if any(k in label for k in ('wi-fi', 'wifi', 'wlan', 'sem fio', 'wireless')):
            return 0
        if any(k in label for k in ('vethernet', 'wsl', 'virtual', 'vmware', 'docker', 'loopback', 'hyper-v')):
            return 2
        return 1

    interfaces.sort(key=sort_priority)
    return interfaces


def get_local_ip():
    """Retorna o IP selecionado manualmente ou o primeiro adaptador prioritário."""
    if SELECTED_IP and is_valid_ipv4(SELECTED_IP):
        return SELECTED_IP

    interfaces = get_available_interfaces()
    if interfaces:
        return interfaces[0]["ip"]
    return '127.0.0.1'


def read_json_resilient(file_path, default_factory):
    """
    Lê um arquivo JSON com recuperação automática via .bak caso o principal
    esteja corrompido (JSONDecodeError).
    """
    bak_path = f"{file_path}.bak"

    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as err:
            print(f" [AVISO] Falha ao ler {os.path.basename(file_path)} ({err}). Tentando restaurar backup...")

    if os.path.exists(bak_path):
        try:
            with open(bak_path, 'r', encoding='utf-8') as f:
                recovered = json.load(f)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            shutil.copy2(bak_path, file_path)
            print(f" [RECUPERADO] {os.path.basename(file_path)} restaurado a partir do .bak.")
            return recovered
        except Exception:
            pass

    return default_factory()


def write_json_atomic(file_path, payload):
    """
    Grava JSON de forma atômica (.tmp -> os.replace) preservando cópia .bak
    da última versão íntegra.
    """
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    bak_path = f"{file_path}.bak"
    tmp_path = f"{file_path}.tmp"

    if os.path.exists(file_path):
        try:
            shutil.copy2(file_path, bak_path)
        except Exception:
            pass

    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())

    os.replace(tmp_path, file_path)


def generate_self_signed_cert(cert_file, key_file):
    """
    Tenta gerar cert.pem e key.pem via OpenSSL com SAN para localhost e mDNS.
    """
    cmd = [
        'openssl', 'req', '-x509', '-newkey', 'rsa:2048',
        '-keyout', key_file, '-out', cert_file,
        '-days', '365', '-nodes',
        '-subj', f'/CN={MDNS_HOSTNAME}',
        '-addext', f'subjectAltName=DNS:{MDNS_HOSTNAME},DNS:localhost,IP:127.0.0.1'
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
        if res.returncode == 0 and os.path.exists(cert_file) and os.path.exists(key_file):
            return True
    except Exception:
        pass
    return False


def configure_ssl_with_recovery(httpd):
    """
    Ativa HTTPS no socket do servidor. Se cert.pem/key.pem estiverem ausentes
    ou corrompidos (ssl.SSLError), tenta regenerar automaticamente via OpenSSL
    antes de recorrer ao fallback HTTP.
    """
    cert_file = os.path.join(BASE_DIR, 'cert.pem')
    key_file = os.path.join(BASE_DIR, 'key.pem')

    for attempt in range(2):
        if os.path.exists(cert_file) and os.path.exists(key_file):
            try:
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                context.load_cert_chain(certfile=cert_file, keyfile=key_file)
                httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
                return "https"
            except (ssl.SSLError, OSError) as err:
                print(f" [AVISO] Certificado SSL inválido ou corrompido ({err}). Isolando arquivos...")
                for broken in (cert_file, key_file):
                    if os.path.exists(broken):
                        try:
                            os.replace(broken, f"{broken}.broken")
                        except Exception:
                            pass

        if attempt == 0:
            print(" [SSL] Tentando gerar certificado autoassinado via OpenSSL...")
            if generate_self_signed_cert(cert_file, key_file):
                print(" [SSL] Novo par cert.pem / key.pem gerado com sucesso.")
                continue
        break

    print(" [AVISO] OpenSSL indisponível ou falha no certificado. Iniciando em HTTP (câmera móvel exige HTTPS).")
    return "http"


def is_webar_already_running(port):
    """
    Verifica se a porta ocupada já pertence a uma instância ativa do WebAR-CMS.
    """
    ctx = ssl._create_unverified_context()
    for scheme in ('https', 'http'):
        try:
            url = f"{scheme}://127.0.0.1:{port}/api/server-info"
            with urllib.request.urlopen(url, timeout=0.8, context=ctx) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                if 'webArUrl' in data:
                    return scheme
        except Exception:
            continue
    return None


def bind_available_port(handler_cls):
    """
    Tenta subir na porta 8080; se já houver um WebAR ativo, reaproveita-o;
    se estiver ocupada por outro serviço, chaveia automaticamente para a próxima.
    """
    ThreadingHTTPServer.allow_reuse_address = True

    for port in CANDIDATE_PORTS:
        try:
            server = ThreadingHTTPServer(('', port), handler_cls)
            return server, port, None
        except OSError:
            existing_scheme = is_webar_already_running(port)
            if existing_scheme:
                return None, port, existing_scheme
            print(f" [AVISO] Porta {port} ocupada por outro processo. Tentando próxima...")

    raise RuntimeError(f"Nenhuma porta disponível entre {CANDIDATE_PORTS}.")


def slugify_filename(raw_name, expected_ext):
    """
    Remove acentos, espaços e caracteres inválidos para gerar nomes seguros em URL.
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


# ==============================================================================
# HANDLER HTTP/HTTPS MULTITHREAD
# ==============================================================================
class CMSRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def handle(self):
        """
        Suprime erros de socket quando smartphones bloqueiam a tela ou saem do
        alcance do Wi-Fi no meio da transferência de arquivos 3D.
        """
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError, ssl.SSLEOFError, ssl.SSLError):
            pass

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

        # 3. Healthcheck Leve para Sonda de Rede / Canal Duplo
        if clean_path == '/api/ping':
            self.send_json(200, {"status": "ok", "port": ACTIVE_PORT})
            return

        # 4. Rota de Descoberta de Interfaces IPv4, Porta Ativa e URL do QR Code
        if clean_path == '/api/server-info':
            interfaces = get_available_interfaces()
            local_ip = get_local_ip()
            network_online = local_ip != '127.0.0.1'
            webar_url = f"{ACTIVE_PROTOCOL}://{local_ip}:{ACTIVE_PORT}/frontend/ar-engine/index.html?token={API_TOKEN}"
            mdns_url = f"{ACTIVE_PROTOCOL}://{MDNS_HOSTNAME}:{ACTIVE_PORT}/frontend/ar-engine/index.html?token={API_TOKEN}"

            client_ip = self.client_address[0]
            now = time.time()
            locked_seconds = 0

            with admin_lock:
                record = admin_attempts.get(client_ip)
                if record and record.get("locked_until", 0) > now:
                    locked_seconds = int(record["locked_until"] - now) + 1

            self.send_json(200, {
                "ip": local_ip,
                "interfaces": interfaces,
                "port": ACTIVE_PORT,
                "protocol": ACTIVE_PROTOCOL,
                "networkOnline": network_online,
                "token": API_TOKEN,
                "paused": SERVER_PAUSED,
                "adminLockedSeconds": locked_seconds,
                "webArUrl": webar_url,
                "mdnsUrl": mdns_url
            })
            return

        # 5. Rota de Analytics: Agregação Estatística (com recuperação de JSON)
        if clean_path == '/api/analytics':
            with telemetry_file_lock:
                telemetry_store = read_json_resilient(
                    TELEMETRY_PATH,
                    lambda: {"totalSessions": 0, "targetViews": {}, "logs": []}
                )

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
            return

        # 6. Inventário de Ativos (.glb e targets.mind) para o CMS (Admin)
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

        # 7. Proteção por Token nas APIs e Modelos 3D (.glb)
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

            with config_file_lock:
                if not os.path.exists(JSON_PATH) and not os.path.exists(f"{JSON_PATH}.bak"):
                    self.send_json(404, {"status": "error", "message": "Arquivo data.json não encontrado."})
                    return
                config_data = read_json_resilient(JSON_PATH, lambda: {"version": "1.0.0", "items": []})

            self.send_json(200, config_data)
            return

        if clean_path == '/api/telemetry':
            with telemetry_file_lock:
                telemetry_data = read_json_resilient(
                    TELEMETRY_PATH,
                    lambda: {"totalSessions": 0, "targetViews": {}, "logs": []}
                )
            self.send_json(200, telemetry_data)
            return

        # 8. Entrega de Arquivos Estáticos Públicos
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

            try:
                free_bytes = shutil.disk_usage(BASE_DIR).free
                if free_bytes < (content_length + MIN_FREE_DISK_BYTES):
                    self.send_json(507, {
                        "status": "error",
                        "message": "Espaço insuficiente em disco no servidor para armazenar o ativo."
                    })
                    return
            except Exception:
                pass

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
                        f.flush()
                        os.fsync(f.fileno())
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
        # Seleção Manual de Interface / IPv4 Ativo (para máquinas multi-placa)
        # ----------------------------------------------------------------------
        if clean_path == '/api/select-ip':
            global SELECTED_IP
            try:
                body = json.loads(post_data.decode('utf-8')) if post_data else {}
                chosen_ip = str(body.get("ip", "")).strip()
                if not is_valid_ipv4(chosen_ip) or chosen_ip.startswith(('127.', '169.254.')):
                    raise ValueError("IPv4 inválido.")

                SELECTED_IP = chosen_ip
                new_url = f"{ACTIVE_PROTOCOL}://{SELECTED_IP}:{ACTIVE_PORT}/frontend/ar-engine/index.html?token={API_TOKEN}"
                print(f" [Rede] IPv4 ativo selecionado: {SELECTED_IP}")
                self.send_json(200, {
                    "status": "success",
                    "ip": SELECTED_IP,
                    "webArUrl": new_url
                })
            except Exception:
                self.send_json(400, {"status": "error", "message": "Endereço IPv4 inválido."})
            return

        # ----------------------------------------------------------------------
        # Validação do PIN Administrativo (com limite de tentativas por IP)
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
        # Telemetria dos Visitantes (gravação atômica + backup)
        # ----------------------------------------------------------------------
        if clean_path == '/api/telemetry':
            try:
                event_data = json.loads(post_data.decode('utf-8'))

                with telemetry_file_lock:
                    telemetry_store = read_json_resilient(
                        TELEMETRY_PATH,
                        lambda: {"totalSessions": 0, "targetViews": {}, "logs": []}
                    )

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

                    write_json_atomic(TELEMETRY_PATH, telemetry_store)

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
                with config_file_lock:
                    write_json_atomic(JSON_PATH, parsed_json)

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


def open_presenter_panel(protocol, port):
    url = f"{protocol}://localhost:{port}/frontend/cms/qrcode.html"
    try:
        webbrowser.open(url)
    except Exception:
        pass


if __name__ == '__main__':
    # Suporte opcional a fixação de IP via terminal: python server.py --ip 192.168.0.27
    if '--ip' in sys.argv:
        idx = sys.argv.index('--ip')
        if idx + 1 < len(sys.argv):
            cli_ip = sys.argv[idx + 1].strip()
            if is_valid_ipv4(cli_ip):
                SELECTED_IP = cli_ip

    try:
        httpd, bound_port, existing_scheme = bind_available_port(CMSRequestHandler)
    except RuntimeError as err:
        print(f" [ERRO CRÍTICO] {err}")
        sys.exit(1)

    ACTIVE_PORT = bound_port

    if httpd is None and existing_scheme:
        print(f" [INFO] Servidor WebAR-CMS já está ativo na porta {ACTIVE_PORT}. Abrindo painel...")
        open_presenter_panel(existing_scheme, ACTIVE_PORT)
        sys.exit(0)

    httpd_instance = httpd
    ACTIVE_PROTOCOL = configure_ssl_with_recovery(httpd)

    interfaces = get_available_interfaces()
    local_ip = get_local_ip()

    print(f" Servidor {ACTIVE_PROTOCOL.upper()} WebAR-CMS ativo na porta {ACTIVE_PORT}...")
    if local_ip == '127.0.0.1':
        print(" [AVISO] Nenhuma rede Wi-Fi/Ethernet ativa detectada (IP 127.0.0.1). Conecte-se ao Wi-Fi do evento.")
    else:
        print(f" IPv4 Principal selecionado: {local_ip}")
        if len(interfaces) > 1:
            others = ", ".join(f"{i['name']} ({i['ip']})" for i in interfaces)
            print(f" Interfaces disponíveis: {others}")
    print(f" Painel QR Code: {ACTIVE_PROTOCOL}://localhost:{ACTIVE_PORT}/cms")

    timer = threading.Timer(1.2, open_presenter_panel, args=[ACTIVE_PROTOCOL, ACTIVE_PORT])
    timer.daemon = True
    timer.start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n Servidor finalizado.")
    finally:
        httpd.server_close()