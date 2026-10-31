Documentação do Projeto: WebAR Local-First MVP
Este repositório contém a versão evoluída da aplicação de Realidade Aumentada para Web (WebAR) com execução 100% offline e local-first. Esta atualização inclui interface dinâmica (UI) para alternância de modelos 3D, controle por gestos nativos (rotação e zoom) e suporte a carregamento otimizado de arquivos sem necessidade de alterar regras de servidor ou rede.
> ⚠️ REGRAS DE IP: Onde encontrar a marcação <SEU_IP_LOCAL>, substitua pelo endereço IPv4 da máquina servidora (exemplo: 192.168.1.100 ou 192.168.137.1).
> 
1. Estrutura de Diretórios e Onde Organizar os Arquivos
Todos os arquivos da aplicação devem ser mantidos na raiz da pasta servida (ou diretório public/).
/
├── index.html                # Aplicação WebAR (UI, Gestos, A-Frame e Lógica de Modelos)
├── server.py                 # Servidor HTTPS local em Python (SSL/TLS)
├── targets.mind              # Arquivo compilado com os alvos 2D para rastreamento
├── audio.mp3                 # Som opcional disparado em eventos de AR
│
├── modelos/                  # Pasta recomendada para organização de objetos 3D
│   ├── modelo1.glb           # Modelo 3D Principal
│   ├── modelo2.glb           # Modelo 3D Secundário
│   └── modeloN.glb           # Novos modelos adicionados
│
├── <SEU_IP_LOCAL>.pem        # Certificado SSL público (X.509)
└── <SEU_IP_LOCAL>-key.pem    # Chave privada RSA do certificado

Onde colocar e como registrar novos modelos 3D (.glb)
 * Localização do Arquivo: Copie seus arquivos .glb para a pasta raiz ou para a subpasta modelos/.
 * Registro no index.html: Abra o index.html e insira o caminho do novo arquivo dentro da lista window.MODELOS presente no script do cabeçalho:
// Exemplo de registro no index.html
window.MODELOS = [
  './modelos/modelo1.glb',
  './modelos/modelo2.glb',
  './modelos/modelo3.glb' // <-- Adicione novos arquivos aqui
];

Não é necessário criar tags <a-asset-item> adicionais para cada modelo. A alternância é feita de forma assíncrona ao clicar nos botões da interface.
2. Novas Funcionalidades e Interações (UI & Gestos)
 * Rotação Livre (1 Dedo): Arraste o dedo em qualquer direção sobre a tela do celular para girar o objeto 3D nos eixos X e Y.
 * Zoom / Escala (2 Dedos): Utilize o movimento de "pinça" (pinch-to-zoom) para expandir ou diminuir o tamanho do objeto 3D.
 * Barra de Controle Flutuante (UI):
   * ◀ Anterior / Próximo ▶: Alterna instantaneamente o arquivo .glb exibido sobre o mesmo marcador 2D.
   * 🔄 180°: Gira o objeto em 180° para visualização imediata da parte traseira.
   * 🎯 Reset: Restaura a rotação, escala e posição originais do modelo.
3. Estimativas de Tempo de Carregamento e Desempenho
As estimativas abaixo consideram a execução em uma Rede Local Offline (Hotspot Windows ou Roteador Wi-Fi local sem acesso à internet) acessada por um smartphone intermediário/avançado.
3.1 Ciclo de Vida e Etapas de Execução
| Etapa | Ação Realizada | Tempo Estimado | Observações |
|---|---|---|---|
| 1. Conexão SSL / TLS | Handshake HTTPS local | 100ms - 300ms | Depende apenas da latência da Wi-Fi local. |
| 2. Parse Inicial (DOM + Libs) | Carregamento do A-Frame e MindAR | 1.0s - 2.0s | Executado uma única vez na abertura da página. |
| 3. Acesso à Câmera | Permissão do sistema e stream de vídeo | 500ms - 1.5s | Solicitação do sistema operacional na primeira visita. |
| 4. Leitura do Target (.mind) | Leitura e compilação dos pontos de contraste | 200ms - 600ms | Executado ao carregar a cena; dependente da CPU do celular. |
| 5. Reconhecimento da Imagem | Detecção da imagem impressa/tela pela câmera | 100ms - 500ms | Depende da iluminação do ambiente e contraste do marcador. |
3.2 Desempenho por Tamanho de Arquivo .glb (Troca de Modelos)
| Tamanho do Arquivo .glb | Download via Wi-Fi Local | Processamento GPU / WebGL | Experiência do Usuário (UX) |
|---|---|---|---|
| Pequeno (< 2 MB) | ~ 0.1s - 0.3s | ~ 0.1s | Instantâneo. Troca imperceptível sem engasgos. |
| Médio (2 MB a 8 MB) | ~ 0.3s - 1.0s | ~ 0.2s - 0.5s | Fluida. Transição suave em menos de 2 segundos. |
| Grande (8 MB a 20 MB) | ~ 1.0s - 3.0s | ~ 0.5s - 1.5s | Aceitável. Pode causar uma leve pausa (frame drop) na câmera durante o parse do modelo. |
| Muito Grande (> 20 MB) | > 3.0s | > 2.0s | Não recomendado. Pode causar travamento temporário no navegador do celular por estouro de memória RAM/GPU. |
> 💡 Dica de Otimização: Mantenha os modelos abaixo de 8 MB utilizando textura comprimida (PNG/JPG até 2048x2048) e aplicando otimização de malha no Blender (Decimate modifier).
> 
4. Guia de Execução Rápida
4.1 Identificar o IP e Gerar Certificado SSL
 * Descubra o IPv4 no Windows (ipconfig) ou Linux (ip a).
 * Gere os certificados no diretório do projeto:
 * Windows (Git Bash):
   openssl req -x509 -newkey rsa:2048 -keyout <SEU_IP_LOCAL>-key.pem -out <SEU_IP_LOCAL>.pem -days 365 -nodes -subj "//CN=<SEU_IP_LOCAL>"

 * Windows (CMD) / Linux Terminal:
   openssl req -x509 -newkey rsa:2048 -keyout <SEU_IP_LOCAL>-key.pem -out <SEU_IP_LOCAL>.pem -days 365 -nodes -subj "/CN=<SEU_IP_LOCAL>"

4.2 Iniciar o Servidor HTTPS
Altere a variável IP no server.py com o seu <SEU_IP_LOCAL> e execute:
 * Windows: python server.py
 * Linux: python3 server.py
4.3 Acessar no Dispositivo Móvel
 * Conecte o celular na mesma rede do computador.
 * Acesse no Chrome: https://<SEU_IP_LOCAL>:8080.
 * Aceite o aviso de certificado autoassinado (Avançado \rightarrow Continuar para <SEU_IP_LOCAL>).
 * Permita a câmera e aponte para a imagem do target.
