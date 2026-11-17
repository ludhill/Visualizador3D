import { SessionManager } from './SessionManager.js';
import { GestureController } from './GestureController.js';
import { TelemetryTracker } from './TelemetryTracker.js';

const urlParams = new URLSearchParams(window.location.search);
const token = (urlParams.get('token') || urlParams.get('Token') || '').trim();
let telemetry = null;

function showErrorModal(title, message) {
  const deniedModal = document.getElementById('denied-modal');
  if (!deniedModal) return;
  const h1 = deniedModal.querySelector('h1');
  const p = deniedModal.querySelector('p');
  if (h1 && title) h1.innerText = title;
  if (p && message) p.innerText = message;
  deniedModal.style.display = 'flex';
}

document.addEventListener('DOMContentLoaded', async () => {
  const sleepModal = document.getElementById('sleep-modal');
  const btnReconectar = document.getElementById('btn-reconnect');
  const scene = document.querySelector('a-scene');

  if (!token) {
    showErrorModal();
    return;
  }

  try {
    const response = await fetch('/api/config', {
      headers: {
        'X-App-Token': token
      }
    });

    if (response.status === 403 || !response.ok) {
      showErrorModal();
      return;
    }

    // Valida o JSON antes de iniciar telemetria e limpar a URL
    const config = await response.json();

    telemetry = new TelemetryTracker(token);
    telemetry.track('session_start');

    const cleanUrl = window.location.protocol + "//" + window.location.host + window.location.pathname;
    window.history.replaceState({ path: cleanUrl }, '', cleanUrl);

    setupARScene(config.items, sleepModal, btnReconectar);

    const arSystem = scene.systems['mindar-image-system'];
    if (arSystem) {
      arSystem.start();
    }

  } catch (error) {
    console.error("[AR Engine] Erro ao carregar dados:", error);
    showErrorModal(
      "Erro na Configuração 3D",
      `Falha ao ler data.json: ${error.message}`
    );
  }
});

window.addEventListener('beforeunload', () => {
  if (telemetry) {
    telemetry.track('session_end');
  }
});

function setupARScene(items, modal, btnReconectar) {
  const scene = document.querySelector('a-scene');

  scene.addEventListener('arReady', () => {
    console.log('[AR Engine] Câmera e WebGL inicializados com sucesso.');
    
    const session = new SessionManager(180000, () => {
      if (modal) modal.style.display = 'flex';
      if (telemetry) telemetry.track('session_sleep');
    });

    if (btnReconectar) {
      btnReconectar.addEventListener('click', () => {
        if (modal) modal.style.display = 'none';
        session.wakeUp();
        if (telemetry) telemetry.track('session_wake');
      });
    }
  });

  items.forEach((item) => {
    if (!item.active) return;

    const targetEntity = document.createElement('a-entity');
    targetEntity.setAttribute('mindar-image-target', `targetIndex: ${item.targetIndex}`);
    scene.appendChild(targetEntity);

    let isModelLoaded = false;
    let modelEntity = null;

    targetEntity.addEventListener('targetFound', () => {
      if (!isModelLoaded) {
        console.log(`[AR Engine] Alvo ${item.targetIndex} detectado. Iniciando download do modelo 3D...`);
        
        modelEntity = document.createElement('a-gltf-model');
        const modelUrl = `/storage/models/${item.modelFile}?token=${encodeURIComponent(token)}`;
        
        modelEntity.setAttribute('src', modelUrl);
        modelEntity.setAttribute('scale', item.scale || '1 1 1');
        modelEntity.setAttribute('rotation', item.rotation || '0 0 0');

        targetEntity.appendChild(modelEntity);
        new GestureController(modelEntity);
        isModelLoaded = true;
      }

      if (telemetry) {
        telemetry.track('target_found', { 
          targetIndex: item.targetIndex,
          modelName: item.name || item.modelFile
        });
      }
    });

    targetEntity.addEventListener('targetLost', () => {
      if (telemetry) {
        telemetry.track('target_lost', { 
          targetIndex: item.targetIndex 
        });
      }
    });
  });
}