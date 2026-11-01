import { SessionManager } from './SessionManager.js';
import { GestureController } from './GestureController.js';
import { TelemetryTracker } from './TelemetryTracker.js';

const urlParams = new URLSearchParams(window.location.search);
const token = urlParams.get('token') || '';
let telemetry = null;

document.addEventListener('DOMContentLoaded', async () => {
  const deniedModal = document.getElementById('denied-modal');
  const sleepModal = document.getElementById('sleep-modal');
  const btnReconectar = document.getElementById('btn-reconnect');
  const scene = document.querySelector('a-scene');

  try {
    const response = await fetch('/api/config', {
      headers: {
        'X-App-Token': token
      }
    });

    if (response.status === 403) {
      if (deniedModal) deniedModal.style.display = 'flex';
      if (scene) scene.pause();
      return;
    }

    if (!response.ok) {
      throw new Error(`Status ${response.status}`);
    }

    // Inicializa a Telemetria e registra o início da sessão
    telemetry = new TelemetryTracker(token);
    telemetry.track('session_start');

    // Mascara o token da barra de endereço
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

// Registra quando o usuário fecha ou sai da página
window.addEventListener('beforeunload', () => {
  if (telemetry) {
    telemetry.track('session_end');
  }
});

function setupARScene(items, modal, btnReconectar) {
  const scene = document.querySelector('a-scene');

  scene.addEventListener('arReady', () => {
    console.log('[AR Engine] Câmara e WebGL inicializados.');
    
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

    const modelEntity = document.createElement('a-gltf-model');
    const modelUrl = `/storage/models/${item.modelFile}?token=${encodeURIComponent(token)}`;
    
    modelEntity.setAttribute('src', modelUrl);
    modelEntity.setAttribute('scale', item.scale || '1 1 1');
    modelEntity.setAttribute('rotation', item.rotation || '0 0 0');

    targetEntity.appendChild(modelEntity);
    scene.appendChild(targetEntity);

    // Registra na telemetria quando um marcador é reconhecido pela câmera
    targetEntity.addEventListener('targetFound', () => {
      new GestureController(modelEntity);
      if (telemetry) {
        telemetry.track('target_found', { 
          targetIndex: item.targetIndex,
          modelName: item.name || item.modelFile
        });
      }
    });
  });
}