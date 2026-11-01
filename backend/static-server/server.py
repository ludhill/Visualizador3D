import os
import json
import ssl
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

PORT = 8080
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
JSON_PATH = os.path.join(BASE_DIR, 'storage', 'db', 'data.json')

class CMSRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def end_headers(self):
        # Desativa cache para chamadas de API, mas ativa para assets 3D pesados
        if self.path.startswith('/api/'):
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        elif self.path.endswith(('.glb', '.mind')):
            self.send_header('Cache-Control', 'public, max-age=86400')
        super().end_headers()

    def do_GET(self):
        # Rota da API para entregar o data.json
        if self.path == '/api/config':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            with open(JSON_PATH, 'rb') as f:
                self.wfile.write(f.read())
            return
        
        # Redirecionamento padrao para arquivos estaticos
        return super().do_GET()

    def do_POST(self):
        # Rota da API para atualizar o data.json via Dashboard
        if self.path == '/api/config':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                # Valida se o dado recebido e um JSON valido
                parsed_json = json.loads(post_data.decode('utf-8'))
                
                # Salva o arquivo de forma limpa no disco
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
        
        self.send_error(404, "Endpoint não encontrado")

if __name__ == '__main__':
    server_address = ('', PORT)
    httpd = ThreadingHTTPServer(server_address, CMSRequestHandler)
    print(f"Servidor WebAR-CMS rodando na porta {PORT}...")
    
    # SSL auto-assinado (Descomentar para HTTPS em rede local)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile="cert.pem", keyfile="key.pem")
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    
    httpd.serve_forever()