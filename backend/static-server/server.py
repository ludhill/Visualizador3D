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
        # Separa o caminho do arquivo dos parâmetros de URL (?token=...)
        clean_path = self.path.split('?')[0]

        # ----------------------------------------------------------------------
        # 1. Proteção de Segurança: APIs e Modelos 3D (.glb)
        # ----------------------------------------------------------------------
        # Mantém a extensão .mind livre para inicialização imediata do MindAR no HTML
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
        # 2. Rota de API: Retorna a configuração do data.json
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
        # 3. Entrega Padrão de Arquivos Estáticos (HTML, JS, CSS, .mind, imagens)
        # ----------------------------------------------------------------------
        return super().do_GET()

    def do_POST(self):
        """
        Trata as requisições POST (Escrita no data.json pelo Dashboard CMS).
        """
        clean_path = self.path.split('?')[0]

        # Valida token também para operações de atualização na API
        if clean_path.startswith('/api/'):
            if not self.check_authorization():
                self.send_response(403)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                response = {"status": "error", "message": "Acesso não autorizado."}
                self.wfile.write(json.dumps(response).encode('utf-8'))
                return

        # Rota para salvar novas configurações enviadas pelo CMS
        if clean_path == '/api/config':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)

            try:
                parsed_json = json.loads(post_data.decode('utf-8'))

                # Garante que a pasta storage/db/ exista antes de gravar
                os.makedirs(os.path.dirname(JSON_PATH), exist_ok=True)

                with open(JSON_PATH, 'w', encoding='utf-8') as f:
                    json.dump(parsed_json, f, indent=2, ensure_ascii=False)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "message": "Configuração salva com sucesso!"}).encode('utf-8'))
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