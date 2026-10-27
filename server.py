import http.server
import ssl
import os

PORT = 8080
IP = '0.0.0.0'

CERT_FILE = f'./{IP}.pem'
KEY_FILE = f'./{IP}-key.pem'

# 1. Verifica existência e tamanho dos arquivos
for file_path in [CERT_FILE, KEY_FILE]:
    if not os.path.exists(file_path):
        print(f"❌ Erro: O arquivo {file_path} não existe!")
        exit(1)
    if os.path.getsize(file_path) == 0:
        print(f"❌ Erro: O arquivo {file_path} está vazio (0 bytes)!")
        exit(1)

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.path.join(os.path.dirname(__file__), 'public'), **kwargs)

# 2. Configura o Servidor e o SSL
httpd = http.server.HTTPServer(('0.0.0.0', PORT), CustomHandler)

context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
try:
    context.load_cert_chain(certfile=CERT_FILE, keyfile=KEY_FILE)
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    
    print(f"\n🚀 MVP WebAR Rodando via Python HTTPS!")
    print(f"💻 No computador:  https://localhost:{PORT}")
    print(f"📱 No celular:     https://{IP}:{PORT}\n")
    
    httpd.serve_forever()
except Exception as e:
    print(f"\n❌ Erro de SSL ao iniciar: {e}")