---

# WebAR Local-First — Ambiente de Homologação (`homolog`)

Este repositório contém a arquitetura **Local-First** para a aplicação de Realidade Aumentada baseada em Web (WebAR). O ambiente de **homologação (`homolog`)** atua como o ponto central de validação, integração e testes antes que qualquer alteração seja promovida para a ramificação de produção (`main`).

---

## 1. Importância do Ambiente de Homologação (`homolog`)

O ambiente de homologação é o "terreno seguro" da engenharia de software. Ele replica fielmente as condições de execução real (comunicação via rede local, HTTPS com SSL autoassinado, consumo de APIs e visualização em smartphones), mas sem expor o ambiente definitivo de produção (`main`) a bugs ou inconsistências durante os testes efetuados por diferentes desenvolvedores ou testadores de campo.

### Papel Estratégico no Projeto WebAR

* **Isolamento de Erros:** Evita que falhas em código recém-desenvolvido quebrem a versão estável utilizada por outros membros da equipe.
* **Validação Multi-dispositivo:** Permite testar o comportamento em diferentes smartphones físicos (Android/iOS) sob a mesma rede local.
* **Consolidação de Módulos:** Garante que o painel CMS (`frontend/dashboard-cms`), o motor 3D (`frontend/ar-engine`), a API Python (`backend/static-server`) e os ativos 3D (`storage/`) funcionem de forma integrada.

---

## 2. Fluxo de Trabalho e Ciclo de Vida das Branches (Git Workflow)

Para manter a organização do código, o desenvolvimento segue um fluxo rigoroso de ramificação (*branching model*):

```text
[ feature/webar-dashboard-cms ] ──┐
[ feature/ar-engine-gestures  ] ──┼──> ( Merge ) ──> [ homolog ] ──> ( Homologado ) ──> [ main ]
[ feature/qa-telemetry-token  ] ──┘

```

### Caminho Percorrido pelo Código

1. **`feature/*` (Branches de Funcionalidade):**
* Cada nova funcionalidade ou correção é isolada em sua própria branch (ex: `feature/ar-engine-gestures`).
* O desenvolvimento e os testes unitários ocorrem exclusivamente dentro desse escopo.


2. **`homolog` (Ambiente de Integridade e Testes de Campo):**
* Assim que os critérios de aceite da funcionalidade são atingidos, a branch `feature/*` é fundida (*merge*) na branch `homolog`.
* É nesta branch que ocorrem as baterias de testes práticos com smartphones de validadores e visitantes.


3. **`main` (Ambiente Estável / Produção):**
* Somente após a aprovação completa em `homolog` sem pendências técnicas, o código é mesclado na `main`.
* A branch `main` representa o sistema pronto para apresentação oficial ou uso contínuo no local de exposição.



---

## 3. Guia Prático de Configuração e Testes em Dispositivos Móveis

Como as validações de campo exigem o acesso por smartphones diversos (não previamente preparados ou configurados), o servidor hospedado no computador host (PC) precisa estar adequadamente visível na rede local para aceitar as conexões dos dispositivos móveis.

---

### Passo 1: Identificação do IP do Servidor Host

Abra o terminal do seu sistema operacional para descobrir o IPv4 local do computador:

* **Windows (PowerShell / CMD):**
```powershell
ipconfig

```


*(Procure a linha **Endereço IPv4** do seu adaptador físico. Ignore adaptadores virtuais como `vEthernet`)*
* **Linux (Debian / Ubuntu / Raspbian):**
```bash
hostname -I | awk '{print $1}'
# ou
ip a

```


* **macOS (Terminal):**
```bash
ipconfig getifaddr en0

```


*(Caso esteja no Wi-Fi e não retorne nada, tente `en1`)*

> **Exemplo de IP obtido:** `192.168.1.15` (Será referenciado neste guia como `<SEU-IP-LOCAL>`).

---

### Passo 2: Geração do Certificado SSL Local

Navegadores móveis exigem conexão HTTPS para liberar a câmera (`getUserMedia`). Na raiz do projeto, gere os certificados especificando o IP obtido no Passo 1:

* **Linux / macOS (Terminal):**
```bash
openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes -subj "/CN=<SEU-IP-LOCAL>"

```


* **Windows (Git Bash):**
```bash
openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes -subj "//CN=<SEU-IP-LOCAL>"

```



---

### Passo 3: Configuração do Firewall no Host

Para que os smartphones consigam conectar na porta `8080`, libere a porta no Firewall do sistema host:

#### A. Windows (PowerShell como Administrador)

```powershell
# 1. Define a rede como Privada
Set-NetConnectionProfile -NetworkCategory Private

# 2. Libera a porta 8080 (TCP) e resposta a PING (ICMPv4)
New-NetFirewallRule -DisplayName "WebAR Direct 8080" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8080
New-NetFirewallRule -DisplayName "Liberar PING ICMPv4" -Direction Inbound -Action Allow -Protocol ICMPv4

```

#### B. Linux Debian / Ubuntu (UFW - Uncomplicated Firewall)

```bash
# Libera a porta 8080 TCP
sudo ufw allow 8080/tcp

# O tráfego ICMP (PING) já vem liberado por padrão no UFW.
# Recarregue as regras:
sudo ufw reload

```

#### C. macOS (Opcional)

O macOS normalmente não bloqueia portas de desenvolvimento local. Caso o firewall interno esteja ativado:

1. Vá em **Ajustes do Sistema > Rede > Firewall**.
2. Clique em **Opções** e garanta que o executável do `Python` esteja definido para **"Permitir conexões de entrada"**.

---

### Passo 4: Conexão e Diagnóstico no Smartphone de Teste

Conecte o celular ao **mesmo Wi-Fi** em que o servidor está rodando.

#### A. Diagnóstico de Rede (Teste de PING no Celular)

Utilize qualquer aplicativo de PING no smartphone (ex: *Ping tools*):

1. Teste o IP do servidor: `<SEU-IP-LOCAL>`.
2. **Esperado:** Retorno em milissegundos (`ms`) com 0% de perda.
3. **Se der Timeout:** O celular está em rede Wi-Fi isolada (ex: "Wi-Fi de Visitantes") ou o Firewall do computador host bloqueou os pacotes.

#### B. Autorização do Certificado SSL e Liberação da Câmera

1. No navegador do celular, acesse a rota da API com `https://`:
```text
https://<SEU-IP-LOCAL>:8080/api/config

```


2. Ao receber o alerta **"Sua conexão não é privada"**, toque em **"Avançado"** e selecione **"Continuar para  (não seguro)"**.
3. Assim que o conteúdo do JSON for exibido no celular, a exceção HTTPS estará gravada para essa sessão.
4. Abra o visualizador WebAR:
```text
https://<SEU-IP-LOCAL>:8080/frontend/ar-engine/index.html

```


5. Aceite a permissão de uso da câmera.

---

## 4. Glossário para Leigos (Termos Técnicos Explicados)

| Termo | O que significa na prática? |
| --- | --- |
| **Local-First** | Arquitetura onde a aplicação funciona 100% dentro da rede local (sem depender de servidores na nuvem ou internet aberta para rodar). |
| **WebAR** | Realidade Aumentada executada diretamente pelo navegador do celular (Chrome/Safari), sem necessidade de instalar aplicativos da loja. |
| **PC Host** | O computador central no local da exposição que executa o servidor Python e armazena os modelos 3D. |
| **IP (Endereço IP)** | O "número de telefone" único que identifica o PC host dentro da rede local (ex: `192.168.1.15`). |
| **Localhost** | Termo que significa "este próprio dispositivo". Usar `localhost` no celular faz com que ele procure o servidor nele mesmo, por isso devemos usar o IP do PC. |
| **Firewall (UFW / Defender)** | O "segurança digital" do sistema operacional que decide quais conexões vindas da rede podem entrar ou sair do computador. |
| **PING (ICMP)** | Um sinal de teste enviado do celular para o computador para checar se ambos conseguem conversar na rede. |
| **SSL / HTTPS** | Protocolo de segurança que criptografa a navegação (representado pelo cadeado no navegador). É obrigatório para liberar a câmera do celular. |
| **Certificado Autoassinado** | Um certificado de segurança gerado localmente pelo projeto para liberar a câmera sem precisar pagar por um domínio na internet. |
| **MindAR / Targets** | Tecnologia que reconhece imagens físicas (marcadores/posters) capturadas pela câmera e posiciona o objeto 3D sobre elas. |
| **GLB / GLTF** | Formato de arquivo padrão para modelos 3D na web (similar ao que o PDF é para documentos ou MP3 para áudios). |

---

## 5. Próximos Passos e Documentação Modular

Com a consolidação da branch **`homolog`**, cada módulo do sistema contará com seu próprio arquivo `README.md` detalhado dentro de suas respectivas pastas:

* `frontend/ar-engine/README.md`: Detalhes do ciclo de vida do A-Frame, rotinas do `SessionManager` e `GestureController`.
* `frontend/dashboard-cms/README.md`: Manual de uso e integração da interface administrativa.
* `backend/static-server/README.md`: Estrutura das rotas REST, persistência em `data.json` e suporte a conexões HTTPS multi-thread.
* `storage/README.md`: Convenções de nomenclatura e diretrizes de otimização para arquivos `.glb` e `.mind`.