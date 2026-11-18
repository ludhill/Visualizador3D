import { SessionManager } from './SessionManager.js';
import { GestureController } from './GestureController.js';
import { TelemetryTracker } from './TelemetryTracker.js';

// Componente nativo para executar animações embutidas em arquivos .glb (glTF 2.0)
if (window.AFRAME && !AFRAME.components['glb-animator']) {
  AFRAME.registerComponent('glb-animator', {
    schema: {
      playing: { type: 'boolean', default: true },
      speed: { type: 'number', default: 1.0 }
    },

    init() {
      this.mixer = null;

      const setupAnimations = (model) => {
        if (this.mixer || !model) return;
        const clips = model.animations || [];
        if (clips.length === 0) return;

        this.mixer = new THREE.AnimationMixer(model);
        clips.forEach((clip) => {
          const action = this.mixer.clipAction(clip);
          action.setLoop(THREE.LoopRepeat);
          action.play();
        });
      };

      this.el.addEventListener('model-loaded', (e) => {
        setupAnimations(e.detail.model);
      });

      const existingMesh = this.el.getObject3D('mesh');
      if (existingMesh) {
        setupAnimations(existingMesh);
      }
    },

    tick(time, timeDelta) {
      if (this.mixer && this.data.playing) {
        this.mixer.update((timeDelta / 1000) * this.data.speed);
      }
    }
  });
}

const urlParams = new URLSearchParams(window.location.search);
const token = (urlParams.get('token') || urlParams.get('Token') || '').trim();
let telemetry = null;

const RING_CIRCUMFERENCE = 2 * Math.PI * 44; // 276.46

function showErrorModal(title, message) {
  const deniedModal = document.getElementById('denied-modal');
  if (!deniedModal) return;
  const h1 = deniedModal.querySelector('h1');
  const p = deniedModal.querySelector('p');
  if (h1 && title) h1.innerText = title;
  if (p && message) p.innerText = message;
  deniedModal.style.display = 'flex';
}

function getStageVisuals(percent) {
  if (percent >= 100) {
    return { color: '#22c55e', label: 'Modelo 3D pronto!' };
  }
  if (percent >= 75) {
    return { color: '#38bdf8', label: 'Processando malha 3D na tela...' };
  }
  if (percent >= 50) {
    return { color: '#eab308', label: 'Carregando texturas e materiais...' };
  }
  if (percent >= 25) {
    return { color: '#f97316', label: 'Baixando geometria do foguete...' };
  }
  return { color: '#ef4444', label: 'Alvo detectado — iniciando download...' };
}

function updateLoaderHUD({ visible, title, percent = 0, loadedBytes = 0, totalBytes = 0, customStatus = null }) {
  const hud = document.getElementById('loader-hud');
  const card = document.getElementById('loader-card');
  const ringFill = document.getElementById('progress-ring-fill');
  const fileLiquid = document.getElementById('file-liquid');
  const linearFill = document.getElementById('linear-fill');
  const titleEl = document.getElementById('loader-title');
  const statusEl = document.getElementById('loader-status');
  const percentEl = document.getElementById('loader-percent');
  const bytesEl = document.getElementById('loader-bytes');

  if (!hud || !card) return;

  if (!visible) {
    hud.classList.remove('visible');
    return;
  }

  hud.classList.add('visible');

  const clamped = Math.max(0, Math.min(100, Math.round(percent)));
  const stage = getStageVisuals(clamped);

  card.style.setProperty('--stage-color', stage.color);

  if (title && titleEl) titleEl.innerText = title;
  if (statusEl) statusEl.innerText = customStatus || stage.label;
  if (percentEl) percentEl.innerText = `${clamped}%`;
  if (linearFill) linearFill.style.width = `${clamped}%`;
  if (fileLiquid) fileLiquid.style.height = `${clamped}%`;

  if (ringFill) {
    const offset = RING_CIRCUMFERENCE - (clamped / 100) * RING_CIRCUMFERENCE;
    ringFill.style.strokeDashoffset = offset;
  }

  if (bytesEl) {
    const loadedMB = (loadedBytes / (1024 * 1024)).toFixed(1);
    if (totalBytes > 0) {
      const totalMB = (totalBytes / (1024 * 1024)).toFixed(1);
      bytesEl.innerText = `${loadedMB} / ${totalMB} MB`;
    } else {
      bytesEl.innerText = `${loadedMB} MB`;
    }
  }
}

async function downloadModelWithProgress(url, modelTitle) {
  updateLoaderHUD({
    visible: true,
    title: modelTitle,
    percent: 0,
    loadedBytes: 0,
    totalBytes: 0
  });

  const response = await fetch(url, {
    headers: { 'X-App-Token': token }
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  const contentLengthHeader = response.headers.get('Content-Length');
  const totalBytes = contentLengthHeader ? parseInt(contentLengthHeader, 10) : 0;

  if (!response.body || !response.body.getReader) {
    const blob = await response.blob();
    updateLoaderHUD({
      visible: true,
      title: modelTitle,
      percent: 95,
      loadedBytes: blob.size,
      totalBytes: blob.size
    });
    return URL.createObjectURL(blob);
  }

  const reader = response.body.getReader();
  const chunks = [];
  let receivedBytes = 0;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    chunks.push(value);
    receivedBytes += value.length;

    // Reserva 0% a 95% para a transferência de rede e 95% a 100% para montagem WebGL
    const networkPercent = totalBytes > 0
      ? Math.min(95, Math.round((receivedBytes / totalBytes) * 95))
      : Math.min(90, Math.round(receivedBytes / 45000));

    updateLoaderHUD({
      visible: true,
      title: modelTitle,
      percent: networkPercent,
      loadedBytes: receivedBytes,
      totalBytes
    });
  }

  updateLoaderHUD({
    visible: true,
    title: modelTitle,
    percent: 96,
    loadedBytes: receivedBytes,
    totalBytes: totalBytes || receivedBytes
  });

  const blob = new Blob(chunks, { type: 'model/gltf-binary' });
  return URL.createObjectURL(blob);
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

    if (response.status === 503) {
      showErrorModal(
        'Exposição em Pausa',
        'A apresentação está temporariamente pausada pelo monitor. Aguarde alguns instantes e recarregue.'
      );
      return;
    }

    if (response.status === 403 || !response.ok) {
      showErrorModal();
      return;
    }

    const config = await response.json();

    telemetry = new TelemetryTracker(token);
    telemetry.track('session_start');

    const cleanUrl = window.location.protocol + '//' + window.location.host + window.location.pathname;
    window.history.replaceState({ path: cleanUrl }, '', cleanUrl);

    setupARScene(config.items, sleepModal, btnReconectar);

    const arSystem = scene.systems['mindar-image-system'];
    if (arSystem) {
      arSystem.start();
    }
  } catch (error) {
    console.error('[AR Engine] Erro ao carregar dados:', error);
    showErrorModal(
      'Erro na Configuração 3D',
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
  const scanHint = document.getElementById('scan-hint');
  let activeTargetsCount = 0;

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

    let loadState = 'idle'; // 'idle' | 'loading' | 'ready'
    let modelEntity = null;
    let gestureCtrl = null;
    let isTargetVisible = false;

    targetEntity.addEventListener('targetFound', async () => {
      isTargetVisible = true;
      activeTargetsCount += 1;
      if (scanHint) scanHint.classList.add('hidden');

      if (telemetry) {
        telemetry.track('target_found', {
          targetIndex: item.targetIndex,
          modelName: item.name || item.modelFile
        });
      }

      if (loadState === 'ready') {
        if (gestureCtrl) gestureCtrl.setActive(true);
        if (modelEntity) modelEntity.setAttribute('glb-animator', 'playing: true');
        return;
      }

      if (loadState === 'loading') {
        const hud = document.getElementById('loader-hud');
        if (hud) hud.classList.add('visible');
        return;
      }

      loadState = 'loading';
      const displayName = item.name || item.modelFile;
      const modelUrl = `/storage/models/${item.modelFile}?token=${encodeURIComponent(token)}&v=2`;

      try {
        const blobUrl = await downloadModelWithProgress(modelUrl, displayName);

        modelEntity = document.createElement('a-gltf-model');
        modelEntity.setAttribute('gltf-model', blobUrl);
        modelEntity.setAttribute('scale', item.scale || '0.25 0.25 0.25');
        modelEntity.setAttribute('rotation', item.rotation || '0 0 0');
        modelEntity.setAttribute('glb-animator', 'playing: true; speed: 1');

        modelEntity.addEventListener('model-loaded', () => {
          loadState = 'ready';
          gestureCtrl = new GestureController(modelEntity);
          gestureCtrl.setActive(isTargetVisible);

          updateLoaderHUD({
            visible: true,
            title: displayName,
            percent: 100
          });

          setTimeout(() => {
            updateLoaderHUD({ visible: false });
          }, 400);
        }, { once: true });

        modelEntity.addEventListener('model-error', () => {
          loadState = 'idle';
          updateLoaderHUD({
            visible: true,
            title: displayName,
            percent: 0,
            customStatus: 'Erro ao renderizar arquivo 3D.'
          });
          setTimeout(() => updateLoaderHUD({ visible: false }), 2000);
        }, { once: true });

        targetEntity.appendChild(modelEntity);
      } catch (err) {
        console.error(`[AR Engine] Falha ao baixar ${item.modelFile}:`, err);
        loadState = 'idle';
        updateLoaderHUD({
          visible: true,
          title: displayName,
          percent: 0,
          customStatus: 'Falha no Wi-Fi. Aponte novamente para tentar.'
        });
        setTimeout(() => updateLoaderHUD({ visible: false }), 2200);
      }
    });

    targetEntity.addEventListener('targetLost', () => {
      isTargetVisible = false;
      activeTargetsCount = Math.max(0, activeTargetsCount - 1);

      if (gestureCtrl) gestureCtrl.setActive(false);
      if (modelEntity) modelEntity.setAttribute('glb-animator', 'playing: false');

      if (loadState === 'loading') {
        updateLoaderHUD({ visible: false });
      }

      if (activeTargetsCount === 0 && scanHint) {
        scanHint.classList.remove('hidden');
      }

      if (telemetry) {
        telemetry.track('target_lost', {
          targetIndex: item.targetIndex
        });
      }
    });
  });
}
