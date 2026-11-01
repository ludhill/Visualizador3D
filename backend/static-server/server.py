import os
import json
import ssl
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

# ==============================================================================
# CONFIGURAÇÕES GERAIS E SEGURANÇA (MÓDULO 3)
# ==============================================================================
API_TOKEN = "WEBAR_2026"  # Token oficial exigido via QR Code
PORT = 8080

# Diretório raiz do projeto (2 níveis acima de backend/static-server)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
JSON_PATH = os.path.join(BASE_DIR, 'storage', 'db', 'data.json')
TELEMETRY_PATH = os.path.join(BASE_DIR, 'storage', 'db', 'telemetry.json')


class CMSRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # Define o BASE_DIR como a raiz de arquivos do servidor HTTP
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def check_authorization(self):
        """
        Valida se a requisição possui o token correto no cabeçalho HTTP ('X-App-Token')
        ou como parâmetro na URL (?token=...).
        """
        # Verifica token enviado pelo cabeçalho HTTP customizado (usado pelo fetch)
        client_token = self.headers.get('X-App-Token')
        
        # Se não veio no cabeçalho, tenta extrair da query string (?token=...)
        if not client_token and '?token=' in self.path:
            try:
                query = self.path.split('?', 1)[1]
                params = dict(param.split('=', 1) for param in query.split('&') if '=' in param)
                client_token = params.get('token')
            except Exception:
                client_token = None

        return client_token == API_TOKEN

    def end_headers(self):
        """
        Aplica regras otimizadas de cache para APIs e modelos 3D.
        """
        clean_path = self.path.split('?')[0]
        
        if clean_path.startswith('/api/'):
            # API sem cache para sempre entregar os dados mais recentes do CMS
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        elif clean_path.endswith(('.glb', '.mind')):
            # Ativa cache de 24h para ativos 3D pesados (economiza banda da rede local)
            self.send_header('Cache-Control', 'public, max-age=86400')
            
        super().end_headers()

    def do_GET(self):
        """
        Trata as requisições GET (APIs, ativos 3D e arquivos estáticos da interface).
        """
        clean_path = self.path.split('?')[0]

        # ----------------------------------------------------------------------
        # Proteção de Segurança: APIs e Modelos 3D (.glb)
        # ----------------------------------------------------------------------
        if clean_path.startswith('/api/') or clean_path.endswith('.glb'):
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
        # Rota de API: Retorna a configuração do data.json
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

        # ----------------------------------------------------------------------
        # Rota de API: Retorna o relatório de Telemetria (NOVO)
        # ----------------------------------------------------------------------
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
        # Entrega Padrão de Arquivos Estáticos (HTML, JS, CSS, .mind, imagens)
        # ----------------------------------------------------------------------
        return super().do_GET()

    def do_POST(self):
        """
        Trata as requisições POST (Escrita no data.json e registro de Telemetria).
        """
        clean_path = self.path.split('?')[0]

        # Exige validação de Token para chamadas de API
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

        # ----------------------------------------------------------------------
        # Rota de Atualização do CMS (/api/config)
        # ----------------------------------------------------------------------
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

        # ----------------------------------------------------------------------
        # Rota de Telemetria Local (/api/telemetry)
        # ----------------------------------------------------------------------
        if clean_path == '/api/telemetry':
            try:
                event_data = json.loads(post_data.decode('utf-8'))
                os.makedirs(os.path.dirname(TELEMETRY_PATH), exist_ok=True)

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
                if len(telemetry_store["logs"]) > 100:
                    telemetry_store["logs"] = telemetry_store["logs"][-100:]

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

        self.send_error(404, "Endpoint não encontrado")


if __name__ == '__main__':
    server_address = ('', PORT)
    httpd = ThreadingHTTPServer(server_address, CMSRequestHandler)

    # --------------------------------------------------------------------------
    # Carregamento do Certificado SSL/HTTPS Local
    # --------------------------------------------------------------------------
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