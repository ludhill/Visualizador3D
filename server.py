import http.server
import ssl
import os
from datetime import datetime

PORT = 8080
IP = 'XXX.XXX.XXX.X' # Altere aqui para o seu IP atual se mudou

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CERT_FILE = os.path.join(BASE_DIR, f'{IP}.pem')
KEY_FILE = os.path.join(BASE_DIR, f'{IP}-key.pem')

# Validação defensiva de existência dos certificados
if not os.path.exists(CERT_FILE) or not os.path.exists(KEY_FILE):
    print(f"❌ Erro: Não foram encontrados os arquivos de certificado para o IP {IP}:")
    print(f"   - Certificado: {CERT_FILE}")
    print(f"   - Chave:       {KEY_FILE}")
    print(f"\n💡 Gere os arquivos no terminal com:")
    print(f"openssl req -x509 -newkey rsa:2048 -keyout {IP}-key.pem -out {IP}.pem -days 365 -nodes -subj \"/CN={IP}\"\n")
    exit(1)

class VerboseHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.path.join(BASE_DIR, 'public'), **kwargs)

    def log_message(self, format, *args):
        now = datetime.now().strftime("%H:%M:%S")
        ip_cliente = self.client_address[0]
        requisicao = args[0]
        status = args[1]

        if status == '200':
            print(f"[{now}] 📥 200 OK | {ip_cliente} pediu: {requisicao}")
        elif status == '404':
            print(f"[{now}] ❌ 404 NOT FOUND | Arquivo não encontrado: {requisicao}")
        else:
            print(f"[{now}] ⚠️ {status} | {ip_cliente} -> {requisicao}")

httpd = http.server.HTTPServer(('0.0.0.0', PORT), VerboseHandler)

context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(certfile=CERT_FILE, keyfile=KEY_FILE)
httpd.socket = context.wrap_socket(httpd.socket, server_side=True)

print(f"\n🚀 Servidor com Logs Ativos!")
print(f"💻 No computador:  https://localhost:{PORT}")
print(f"📱 No celular:     https://{IP}:{PORT}\n")

try:
    httpd.serve_forever()
except KeyboardInterrupt:
    print("\nServidor finalizado.")