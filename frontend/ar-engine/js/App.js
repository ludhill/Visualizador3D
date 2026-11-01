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

  // 1. Bloqueia imediatamente se não houver token na URL
  if (!token) {
    if (deniedModal) deniedModal.style.display = 'flex';
    return;
  }

  try {
    // 2. Valida o token com a API Backend
    const response = await fetch('/api/config', {
      headers: {
        'X-App-Token': token
      }
    });

    if (response.status === 403 || !response.ok) {
      if (deniedModal) deniedModal.style.display = 'flex';
      return;
    }

    // 3. Inicializa a Telemetria e registra o início da sessão
    telemetry = new TelemetryTracker(token);
    telemetry.track('session_start');

    // 4. Mascara o token da URL para não ficar visível na barra do navegador
    const cleanUrl = window.location.protocol + "//" + window.location.host + window.location.pathname;
    window.history.replaceState({ path: cleanUrl }, '', cleanUrl);

    // 5. Configura e carrega os modelos 3D na cena
    const config = await response.json();
    setupARScene(config.items, sleepModal, btnReconectar);

    // 6. Inicia a câmera e o rastreamento MindAR somente agora que tudo foi validado
    const arSystem = scene.systems['mindar-image-system'];
    if (arSystem) {
      arSystem.start();
    }

  } catch (error) {
    console.error("[AR Engine] Erro ao carregar dados:", error);
    if (deniedModal) deniedModal.style.display = 'flex';
  }
});

// Registra a saída do usuário
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

    const modelEntity = document.createElement('a-gltf-model');
    const modelUrl = `/storage/models/${item.modelFile}?token=${encodeURIComponent(token)}`;
    
    modelEntity.setAttribute('src', modelUrl);
    modelEntity.setAttribute('scale', item.scale || '1 1 1');
    modelEntity.setAttribute('rotation', item.rotation || '0 0 0');

    targetEntity.appendChild(modelEntity);
    scene.appendChild(targetEntity);

    // Evento de reconhecimento do marcador
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