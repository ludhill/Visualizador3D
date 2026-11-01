import { SessionManager } from './SessionManager.js';
import { GestureController } from './GestureController.js';

const urlParams = new URLSearchParams(window.location.search);
const token = urlParams.get('token') || '';

document.addEventListener('DOMContentLoaded', async () => {
  const deniedModal = document.getElementById('denied-modal');
  const sleepModal = document.getElementById('sleep-modal');
  const btnReconectar = document.getElementById('btn-reconnect');
  const scene = document.querySelector('a-scene');

  try {
    // 1. Valida o Token com a API
    const response = await fetch('/api/config', {
      headers: {
        'X-App-Token': token
      }
    });

    // 2. Se não autorizado (403): Bloqueia a interface e pausa o WebGL
    if (response.status === 403) {
      if (deniedModal) deniedModal.style.display = 'flex';
      if (scene) scene.pause();
      return;
    }

    if (!response.ok) {
      throw new Error(`Status ${response.status}`);
    }

    // 3. Se autorizado: Limpa o token da URL visual do navegador
    if (token) {
      const cleanUrl = window.location.protocol + "//" + window.location.host + window.location.pathname;
      window.history.replaceState({ path: cleanUrl }, '', cleanUrl);
    }

    const config = await response.json();
    setupARScene(config.items, sleepModal, btnReconectar);
  } catch (error) {
    console.error("[AR Engine] Erro ao carregar dados:", error);
  }
});

function setupARScene(items, modal, btnReconectar) {
  const scene = document.querySelector('a-scene');

  scene.addEventListener('arReady', () => {
    console.log('[AR Engine] Câmara e WebGL inicializados com sucesso.');
    
    const session = new SessionManager(180000, () => {
      if (modal) modal.style.display = 'flex';
    });

    if (btnReconectar) {
      btnReconectar.addEventListener('click', () => {
        if (modal) modal.style.display = 'none';
        session.wakeUp();
      });
    }
  });

  items.forEach((item) => {
    if (!item.active) return;

    const targetEntity = document.createElement('a-entity');
    targetEntity.setAttribute('mindar-image-target', `targetIndex: ${item.targetIndex}`);

    const modelEntity = document.createElement('a-gltf-model');
    // Envia o token na requisição do arquivo 3D para passar pela validação do server.py
    const modelUrl = `/storage/models/${item.modelFile}?token=${encodeURIComponent(token)}`;
    
    modelEntity.setAttribute('src', modelUrl);
    modelEntity.setAttribute('scale', item.scale || '1 1 1');
    modelEntity.setAttribute('rotation', item.rotation || '0 0 0');

    targetEntity.appendChild(modelEntity);
    scene.appendChild(targetEntity);

    targetEntity.addEventListener('targetFound', () => {
      new GestureController(modelEntity);
    });
  });
}