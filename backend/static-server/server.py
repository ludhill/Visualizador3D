import os
import json
import ssl
import socket
import threading  # Importação da biblioteca nativa de threads
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

# Lock global para garantir escrita segura no ficheiro de telemetria
telemetry_file_lock = threading.Lock()

# ==============================================================================
# CONFIGURAÇÕES GERAIS E SEGURANÇA (MÓDULO 3 & 4)
# ==============================================================================
API_TOKEN = "WEBAR_2026"  # Token oficial exigido via QR Code
PORT = 8080

# Diretório raiz do projeto (2 níveis acima de backend/static-server)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
JSON_PATH = os.path.join(BASE_DIR, 'storage', 'db', 'data.json')
TELEMETRY_PATH = os.path.join(BASE_DIR, 'storage', 'db', 'telemetry.json')


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


class CMSRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def check_authorization(self):
        """
        Valida se a requisição possui o token correto no cabeçalho HTTP ('X-App-Token')
        ou como parâmetro na URL (?token=...).
        """
        client_token = self.headers.get('X-App-Token')
        
        if not client_token and '?token=' in self.path:
            try:
                query = self.path.split('?', 1)[1]
                params = dict(param.split('=', 1) for param in query.split('&') if '=' in param)
                client_token = params.get('token')
            except Exception:
                client_token = None

        return client_token == API_TOKEN

    def end_headers(self):
        clean_path = self.path.split('?')[0]
        
        # APIs dinâmicas: Nunca guardar em cache
        if clean_path.startswith('/api/'):
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
            self.send_header('Pragma', 'no-cache')
            
        # O ficheiro sw.js nunca deve ser mantido em cache rígido pelo browser
        elif clean_path.endswith('sw.js'):
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            
        # Ficheiros 3D pesados (.glb) e marcadores (.mind): Cache longa de 7 dias (604800 s)
        elif clean_path.endswith(('.glb', '.mind')):
            self.send_header('Cache-Control', 'public, max-age=604800, immutable')
            
        # Scripts, folhas de estilo e imagens: Cache de 1 dia (86400 s)
        elif clean_path.endswith(('.js', '.css', '.png', '.jpg', '.jpeg', '.webp', '.svg')):
            self.send_header('Cache-Control', 'public, max-age=86400')
            
        super().end_headers()

    def do_GET(self):
        clean_path = self.path.split('?')[0]

        # ----------------------------------------------------------------------
        # Rota de Analytics: Agregação Estatística (Módulo 5 - Parte A)
        # ----------------------------------------------------------------------
        if clean_path == '/api/analytics':
            empty_analytics = {
                "totalSessions": 0,
                "averageSessionSeconds": 0,
                "viewsByTarget": {},
                "hourlyActivity": [0] * 24
            }

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()

            if not os.path.exists(TELEMETRY_PATH):
                self.wfile.write(json.dumps(empty_analytics).encode('utf-8'))
                return

            try:
                with open(TELEMETRY_PATH, 'r', encoding='utf-8') as f:
                    telemetry_store = json.load(f)

                logs = telemetry_store.get("logs", [])
                total_duration = 0
                completed_count = 0
                hourly_activity = [0] * 24

                for log in logs:
                    # 1. Agrupa os acessos por hora do dia (extraído da string ISO)
                    ts = log.get("timestamp")
                    if ts:
                        try:
                            # Trata a string "YYYY-MM-DDTHH:MM:SS.mmmZ" sem bibliotecas externas
                            time_part = ts.split('T')[1]
                            hour = int(time_part.split(':')[0])
                            if 0 <= hour < 24:
                                hourly_activity[hour] += 1
                        except Exception:
                            pass

                    # 2. Acumula o tempo de sessões finalizadas para a média
                    if log.get("event") == "session_end" and "sessionDurationSeconds" in log:
                        total_duration += log.get("sessionDurationSeconds", 0)
                        completed_count += 1

                avg_seconds = round(total_duration / completed_count) if completed_count > 0 else 0

                analytics_data = {
                    "totalSessions": telemetry_store.get("totalSessions", 0),
                    "averageSessionSeconds": avg_seconds,
                    "viewsByTarget": telemetry_store.get("targetViews", {}),
                    "hourlyActivity": hourly_activity
                }

                self.wfile.write(json.dumps(analytics_data, ensure_ascii=False).encode('utf-8'))

            except Exception as e:
                # Caso ocorra falha de leitura, retorna o estado vazio sem quebrar a API
                self.wfile.write(json.dumps(empty_analytics).encode('utf-8'))
            return

        # ----------------------------------------------------------------------
        # Proteção de Segurança: APIs Protegidas e Modelos 3D (.glb)
        # ----------------------------------------------------------------------
        if clean_path in ['/api/config', '/api/telemetry', '/api/analytics'] or clean_path.endswith('.glb'):
            if not self.check_authorization():
                self.send_response(403)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                response = {
                    "status": "error",
                    "message": "Acesso não autorizado. Token ausente ou inválido."
                }
                self.wfile.write(json.dumps(response).encode('utf-8'))
                return

        # ----------------------------------------------------------------------
        # Rotas de API protegidas
        # ----------------------------------------------------------------------
        if clean_path == '/api/config':
            if os.path.exists(JSON_PATH):
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                with open(JSON_PATH, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                response = {"status": "error", "message": "Arquivo data.json não encontrado."}
                self.wfile.write(json.dumps(response).encode('utf-8'))
            return

        if clean_path == '/api/telemetry':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            if os.path.exists(TELEMETRY_PATH):
                with open(TELEMETRY_PATH, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                empty_data = {"totalSessions": 0, "targetViews": {}, "logs": []}
                self.wfile.write(json.dumps(empty_data).encode('utf-8'))
            return

        # ----------------------------------------------------------------------
        # Arquivos Estáticos Padrão
        # ----------------------------------------------------------------------
        return super().do_GET()

    def do_POST(self):
        clean_path = self.path.split('?')[0]

        if clean_path.startswith('/api/'):
            if not self.check_authorization():
                self.send_response(403)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                response = {"status": "error", "message": "Acesso não autorizado."}
                self.wfile.write(json.dumps(response).encode('utf-8'))
                return

        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)

        if clean_path == '/api/config':
            try:
                parsed_json = json.loads(post_data.decode('utf-8'))
                os.makedirs(os.path.dirname(JSON_PATH), exist_ok=True)
                with open(JSON_PATH, 'w', encoding='utf-8') as f:
                    json.dump(parsed_json, f, indent=2, ensure_ascii=False)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "message": "Configuração salva!"}).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
            return

        if clean_path == '/api/telemetry':
            try:
                event_data = json.loads(post_data.decode('utf-8'))
                os.makedirs(os.path.dirname(TELEMETRY_PATH), exist_ok=True)

                # ==============================================================
                # OPERAÇÃO SEGURA COM FILE LOCK (THREAD-SAFETY)
                # ==============================================================
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

                    # Limita o histórico aos últimos 500 registos para evitar crescimento indefinido
                    if len(telemetry_store["logs"]) > 500:
                        telemetry_store["logs"] = telemetry_store["logs"][-500:]

                    with open(TELEMETRY_PATH, 'w', encoding='utf-8') as f:
                        json.dump(telemetry_store, f, indent=2, ensure_ascii=False)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "recorded"}).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
            return


if __name__ == '__main__':
    server_address = ('', PORT)
    httpd = ThreadingHTTPServer(server_address, CMSRequestHandler)

    cert_file = os.path.join(BASE_DIR, 'cert.pem')
    key_file = os.path.join(BASE_DIR, 'key.pem')

    if os.path.exists(cert_file) and os.path.exists(key_file):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=cert_file, keyfile=key_file)
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
        print(f" Servidor HTTPS WebAR-CMS ativo na porta {PORT}...")
    else:
        print(f" Certificados SSL não encontrados na raiz. Servidor rodando em HTTP (Porta {PORT})...")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n Servidor finalizado.")