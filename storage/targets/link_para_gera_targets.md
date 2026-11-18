https://hiukim.github.io/mind-ar-js-doc/tools/compile/



### Windows (PowerShell como Administrador)

Abra o **Terminal (Admin)** ou **PowerShell (Admin)** no PC Host e execute os três comandos abaixo:

```powershell
# 1. Garante que a rede conectada esteja como "Privada" (obrigatório para liberar tráfego local)
Set-NetConnectionProfile -NetworkCategory Private

# 2. Libera o tráfego HTTPS/HTTP de entrada na porta 8080 (ou inclua as portas de fallback: 8080,8443,8081,8888)
New-NetFirewallRule -DisplayName "WebAR Direct 8080" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8080

# 3. Libera respostas de PING (ICMPv4) para diagnósticos de rede a partir do celular
New-NetFirewallRule -DisplayName "Liberar PING ICMPv4" -Direction Inbound -Action Allow -Protocol ICMPv4

```

* **Alternativa restrita (opcional — vinculada apenas ao `python.exe` e à sub-rede local):**
*(Atenção: se alternar entre Python global, Venv ou Anaconda no VS Code, o caminho do executável muda e a regra abaixo passa a bloquear; nesse caso, prefira a regra `WebAR Direct 8080` acima).*

```powershell
$pythonExe = (Get-Command python).Source

New-NetFirewallRule -DisplayName "WebAR Server (Exclusivo Python)" `
                    -Direction Inbound `
                    -Action Allow `
                    -Protocol TCP `
                    -LocalPort 8080 `
                    -Program $pythonExe `
                    -RemoteAddress "192.168.0.0/24" `
                    -Profile Private

```

* **Comandos rápidos de verificação ou limpeza (Windows):**

```powershell
# Conferir perfil de rede e regras ativas do WebAR
Get-NetConnectionProfile
Get-NetFirewallRule -DisplayName "*WebAR*"

# Remover regras antigas, se precisar recriar
Remove-NetFirewallRule -DisplayName "WebAR Direct 8080" -ErrorAction SilentlyContinue

```

---

### Linux (Debian / Ubuntu — UFW)

```bash
# Libera a porta 8080 TCP (o PING/ICMP já vem liberado por padrão no UFW)
sudo ufw allow 8080/tcp
sudo ufw reload

```

---

### macOS

1. Acesse **Ajustes do Sistema > Rede > Firewall**.
2. Clique em **Opções** e defina o executável do **Python** como **"Permitir conexões de entrada"**.


1. O notebook novo subiu em http:// em vez de https:// (Mais Provável)Como os arquivos cert.pem e key.pem ficam no .gitignore, eles não vieram no git pull para o notebook novo. Se o openssl não estiver no PATH do Windows, o server.py caiu para HTTP, e o Chrome bloqueia a câmera em qualquer conexão http:// via IP.   Como conferir: Olhe no terminal do notebook ou na URL abaixo do QR Code se aparece http:// em vez de https://.Como resolver (no notebook novo):Abra o Git Bash (ou PowerShell) na raiz Visualizador3D/ e gere o certificado:Bash# No Git Bash:
openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes -subj "//CN=cvtespacial.local"
PowerShell# Ou no PowerShell (usando o OpenSSL do Git):
& "C:\Program Files\Git\usr\bin\openssl.exe" req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes -subj "/CN=cvtespacial.local"
Reinicie o servidor (python server.py) e confirme no terminal a mensagem Servidor HTTPS WebAR-CMS ativo.Escaneie o novo QR Code (https://...) e aceite o aviso "Avançado $\rightarrow$ Continuar para <IP> (não seguro)".   