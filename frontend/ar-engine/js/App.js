import { SessionManager } from './SessionManager.js';
import { GestureController } from './GestureController.js';

document.addEventListener('DOMContentLoaded', async () => {
  const modal = document.getElementById('sleep-modal');
  const btnReconectar = document.getElementById('btn-reconnect');

  // Inicializa o Gerenciador de Sessão (Sleep após 3 min)
  const session = new SessionManager(180000, (reason) => {
    modal.style.display = 'flex';
  });

  btnReconectar.addEventListener('click', () => session.wakeUp());

  // Consome a lista dinâmica de alvos do CMS
  try {
    const response = await fetch('/api/config');
    const config = await response.json();
    setupARScene(config.items);
  } catch (error) {
    console.error("[AR Engine] Falha ao carregar configuração dinâmica:", error);
  }
});

function setupARScene(items) {
  const scene = document.querySelector('a-scene');

  scene.addEventListener('arReady', () => {
    console.log('[AR Engine] Câmara e WebGL inicializados com sucesso.');
    
    // Ativa o temporizador de bateria apenas após a câmara arrancar
    const session = new SessionManager(180000, (reason) => {
      modal.style.display = 'flex';
    });

    btnReconectar.addEventListener('click', () => session.wakeUp());
  });

  scene.addEventListener('arError', (event) => {
    console.error('[AR Engine] Falha ao iniciar a câmara. Verifique as permissões HTTPS/IP.');
  });

  items.forEach((item) => {
    if (!item.active) return;

    // Conecta cada alvo ao índice dinâmico do data.json
    const targetEntity = document.createElement('a-entity');
    targetEntity.setAttribute('mindar-image-target', `targetIndex: ${item.targetIndex}`);

    const modelEntity = document.createElement('a-gltf-model');
    modelEntity.setAttribute('src', `/storage/models/${item.modelFile}`);
    modelEntity.setAttribute('scale', item.scale || '1 1 1');
    modelEntity.setAttribute('rotation', item.rotation || '0 0 0');

    targetEntity.appendChild(modelEntity);
    scene.appendChild(targetEntity);

    // Ativa os controles gestuais ao detectar o modelo
    targetEntity.addEventListener('targetFound', () => {
      new GestureController(modelEntity);
    });
  });
}