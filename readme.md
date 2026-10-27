# Documentação do Projeto: WebAR Local-First MVP

Este repositório contém uma aplicação de **Realidade Aumentada para Web (WebAR)** focada em execução 100% offline e local-first. A solução utiliza **MindAR.js** para rastreamento de imagens 2D, **A-Frame (Three.js)** para renderização 3D e um servidor HTTPS em **Python** configurado com certificados autoassinados para atender às exigências de segurança de acesso à câmara nos navegadores móveis.

> ⚠️ **IMPORTANTE:** Onde encontrar a marcação `<SEU_IP_LOCAL>`, substitua pelo endereço IPv4 real da máquina que está a executar o servidor (exemplo: `192.168.1.100` ou `192.168.137.1`).

---

## 1. Estrutura de Ficheiros do Projeto

```text
/
├── index.html                # Estrutura da cena 3D e integração MindAR/A-Frame
├── server.py                 # Servidor HTTP/HTTPS local personalizado em Python
├── targets.mind              # Arquivo binário com os pontos de rastreamento da imagem 2D
├── modelo1.glb               # Modelo 3D no formato glTF Binary
├── audio.mp3                 # Arquivo de áudio para ser disparado pelo evento de AR
├── <SEU_IP_LOCAL>.pem        # Certificado SSL público (X.509) -> Ex: 192.168.1.100.pem
└── <SEU_IP_LOCAL>-key.pem    # Chave privada RSA do certificado -> Ex: 192.168.1.100-key.pem

```

---

## 2. Detalhamento de Ficheiros, Tags e Componentes

### 2.1 `index.html` (Front-end WebAR)

Ficheiro principal de visualização da aplicação. Combina HTML5 com os seletores declarativos do **A-Frame** e os atributos do **MindAR**.

#### Tags e Atributos Principais

* **`<script src="...">`**: Carrega as bibliotecas do A-Frame e do MindAR diretamente via CDN ou arquivo local.
* **`<a-scene>`**: Tag principal do A-Frame que inicializa a renderização WebGL e o ciclo de animação (*render loop*) do Three.js.
* `mindar-image="imageTargetSrc: ./targets.mind;"`: Atributo do MindAR que ativa o motor de visão computacional e indica onde está o arquivo de dados dos alvos 2D.
* `color-space="sRGB"`: Define o espaço de cores correto para evitar que modelos 3D pareçam lavados ou escuros.
* `renderer="colorManagement: true, physicallyCorrectLights"`: Ativa a iluminação baseada em física (PBR), necessária para texturas de modelos `.glb`.
* `vr-mode-ui="enabled: false"` e `device-orientation-permission-ui="enabled: false"`: Desativam os botões padrão de VR/Giroscópio para manter a interface limpa.


* **`<a-assets>`**: Bloco de pré-carregamento do A-Frame. Gerencia o download assíncrono de arquivos pesados (modelos, áudios e imagens) antes do início da cena.
* `<a-asset-item id="modelo1" src="./modelo1.glb"></a-asset-item>`: Define o recurso 3D com um identificador (`id`) único.


* **`<a-camera>`**: Define a câmara virtual.
* `position="0 0 0"` e `look-controls="enabled: false"`: Passa o controle da câmara inteiramente para o rastreamento do MindAR/câmara física do telemóvel.


* **`<a-light>`**: Adiciona iluminação virtual à cena.
* `type="ambient" intensity="1.5"`: Luz uniforme que ilumina todas as faces do modelo de forma geral.
* `type="directional" position="1 2 1"`: Luz direcionada que simula o Sol, criando sombras e destaques nos materiais 3D.


* **`<a-entity mindar-image-target="targetIndex: 0">`**: Entidade lógica vinculada a uma imagem do `targets.mind`.
* `targetIndex: 0`: Especifica que esta entidade deve aparecer apenas quando o **primeiro alvo** do arquivo `.mind` for detectado pela câmara.


* **`<a-gltf-model>`**: Elemento responsável por renderizar modelos no formato `.glb`/`.gltf`.
* `src="#modelo1"`: Aponta para o ID definido dentro de `<a-assets>`.
* `position="0 0 0"`, `scale="0.1 0.1 0.1"`, `rotation="0 0 0"`: Controlam o deslocamento, o tamanho e a orientação do objeto 3D sobre a imagem rastreada.



---

### 2.2 `server.py` (Servidor HTTPS em Python)

Script responsável por servir os arquivos estáticos da pasta e criptografar a comunicação via SSL/TLS (exigência obrigatória do WebRTC/MediaDevices para liberarem a câmara no navegador).

#### Módulos e Classes Utilizadas

* **`http.server.HTTPServer`**: Classe nativa do Python responsável por escutar em um endereço IP e porta específicos e gerenciar as requisições HTTP de entrada.
* **`http.server.SimpleHTTPRequestHandler`**: Manipulador (*handler*) padrão que lê arquivos do sistema de arquivos e os entrega como resposta (servindo `index.html`, `.glb`, `.mind`, etc.).
* **`ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)`**: Cria um contexto de segurança moderno focado na operação como servidor SSL/TLS.
* **`context.load_cert_chain(certfile, keyfile)`**: Carrega o certificado público (`.pem`) e a chave privada (`-key.pem`) necessários para estabelecer a chave de sessão com o telemóvel.
* **`context.wrap_socket(httpd.socket, server_side=True)`**: Sobrescreve o socket TCP tradicional do HTTP por um socket seguro criptografado com HTTPS.

---

### 2.3 Arquivos de Recursos (`targets.mind` e `modelo1.glb`)

* **`targets.mind`**: Arquivo binário compilado que contém os "pontos de interesse" (keypoints de alto contraste) extraídos da imagem 2D original. É gerado pela ferramenta *MindAR Image Target Compiler*.
* **`modelo1.glb`**: Formato **glTF Binary**. Agrupa malhas geométricas, esqueletos de animação, materiais e texturas (imagens) em um único arquivo binário comprimido e otimizado para a Web.

---

## 3. Guia de Configuração e Execução (Passo a Passo)

### 3.1 Identificação do Endereço IP Local

O servidor e os certificados devem estar vinculados ao IPv4 da máquina que está a executar a aplicação.

* **No Windows (CMD / PowerShell):**
```cmd
ipconfig

```


*Procure pelo **Endereço IPv4** do adaptador ativo (ex: `192.168.137.1`). Este valor será o seu `<SEU_IP_LOCAL>`.*
* **No Linux (Debian/Ubuntu):**
```bash
ip a

```


*Procure pelo endereço IPv4 da interface ativa (ex: `wlan0`, `eth0` ou `usb0`). Este valor será o seu `<SEU_IP_LOCAL>`.*

---

### 3.2 Geração dos Certificados SSL Autoassinados (OpenSSL)

Substitua `<SEU_IP_LOCAL>` pelo IP obtido no passo anterior.

#### No Linux / Terminal Padrão:

```bash
openssl req -x509 -newkey rsa:2048 -keyout <SEU_IP_LOCAL>-key.pem -out <SEU_IP_LOCAL>.pem -days 365 -nodes -subj "/CN=<SEU_IP_LOCAL>"

```

#### No Windows via Git Bash:

*(Utilizam-se duas barras `//` para impedir a conversão de caminho do Git Bash)*

```bash
openssl req -x509 -newkey rsa:2048 -keyout <SEU_IP_LOCAL>-key.pem -out <SEU_IP_LOCAL>.pem -days 365 -nodes -subj "//CN=<SEU_IP_LOCAL>"

```

#### No Windows via Prompt de Comando (CMD):

```cmd
openssl req -x509 -newkey rsa:2048 -keyout <SEU_IP_LOCAL>-key.pem -out <SEU_IP_LOCAL>.pem -days 365 -nodes -subj "/CN=<SEU_IP_LOCAL>"

```

> **Exemplo prático (Se o IP for `192.168.1.50`):**
> ```cmd
> openssl req -x509 -newkey rsa:2048 -keyout 192.168.1.50-key.pem -out 192.168.1.50.pem -days 365 -nodes -subj "/CN=192.168.1.50"
> 
> ```
> 
> 

---

### 3.3 Liberação no Firewall de Rede

Para impedir que a conexão do telemóvel seja bloqueada na porta `8080` ou no protocolo ICMP (ping):

#### No Windows (Prompt de Comando como Administrador):

```cmd
netsh advfirewall firewall add rule name="WebAR Python 8080" dir=in action=allow protocol=TCP localport=8080
netsh advfirewall firewall add rule name="Liberar Ping ICMPv4" dir=in action=allow protocol=ICMPv4

```

#### No Linux (UFW):

```bash
sudo ufw allow 8080/tcp
sudo ufw reload

```

---

### 3.4 Configuração e Execução do Servidor

1. Abra o arquivo `server.py` e configure a variável `IP` com o mesmo valor utilizado na geração do certificado:
```python
IP = '<SEU_IP_LOCAL>'  # Substitua pelo seu IPv4 real (ex: '192.168.1.50')
PORT = 8080

```


2. Execute o servidor na pasta raiz do projeto:
* **Windows:**
```cmd
python server.py

```


* **Linux:**
```bash
python3 server.py

```





---

### 3.5 Acesso e Bypass de Segurança no Dispositivo Móvel

1. Conecte o telemóvel à mesma rede Wi-Fi/Hotspot do computador.
2. Abra o navegador **Google Chrome** no telemóvel.
3. Acesse o endereço HTTPS utilizando o seu IP: `https://<SEU_IP_LOCAL>:8080` (ex: `[https://192.168.1.50:8080](https://192.168.1.50:8080)`).
4. Devido ao certificado autoassinado, o navegador exibirá o aviso *"A sua ligação não é privada"*.
5. Toque em **Avançado** $\rightarrow$ **Continuar para <SEU_IP_LOCAL> (não seguro)**.
6. Permita o acesso à câmara quando solicitado na tela.
7. Aponte a câmara para a imagem do target para carregar o modelo 3D.