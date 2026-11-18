let apiToken = '';
let adminPin = sessionStorage.getItem('webar_admin_pin') || '';
let captchaExpected = 0;
let lockoutTimer = null;

let cmsData = { version: '1.0.0', items: [] };
let availableModels = [];
let targetBundleInfo = { exists: false, sizeBytes: 0, updatedAt: null };
let analyticsData = {
  totalSessions: 0,
  averageSessionSeconds: 0,
  viewsByTarget: {},
  hourlyActivity: new Array(24).fill(0)
};
let fontSizePx = 16;

document.addEventListener('DOMContentLoaded', async () => {
  generateHumanChallenge();
  bindAuthEvents();
  bindToolbarEvents();
  bindUploadEvents();
  await initDashboard();
});

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return '0 KB';
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function setAuthFormDisabled(disabled, btnText = 'Desbloquear Painel') {
  const captchaInput = document.getElementById('captcha-input');
  const pinInput = document.getElementById('admin-pin-input');
  const submitBtn = document.getElementById('btn-unlock-cms');

  if (captchaInput) captchaInput.disabled = disabled;
  if (pinInput) pinInput.disabled = disabled;
  if (submitBtn) {
    submitBtn.disabled = disabled;
    submitBtn.innerText = btnText;
  }
}

function startLockoutCountdown(seconds) {
  if (lockoutTimer) clearInterval(lockoutTimer);
  let remaining = Math.max(1, Number(seconds) || 30);

  const errorEl = document.getElementById('auth-error-msg');
  const updateUI = () => {
    setAuthFormDisabled(true, `Bloqueado (${remaining}s)`);
    if (errorEl) {
      errorEl.innerText = `IP bloqueado por excesso de tentativas. Aguarde ${remaining}s para tentar novamente.`;
    }
  };

  updateUI();

  lockoutTimer = setInterval(() => {
    remaining -= 1;
    if (remaining <= 0) {
      clearInterval(lockoutTimer);
      lockoutTimer = null;
      setAuthFormDisabled(false, 'Desbloquear Painel');
      if (errorEl) errorEl.innerText = '';
      generateHumanChallenge();
    } else {
      updateUI();
    }
  }, 1000);
}

function generateHumanChallenge() {
  const a = Math.floor(Math.random() * 9) + 2;
  const b = Math.floor(Math.random() * 9) + 1;
  captchaExpected = a + b;

  const label = document.getElementById('captcha-label');
  const input = document.getElementById('captcha-input');
  if (label) label.innerText = `Verificação Humana: quanto é ${a} + ${b}?`;
  if (input) input.value = '';
}

function lockDashboard(message = '') {
  adminPin = '';
  sessionStorage.removeItem('webar_admin_pin');
  document.body.classList.add('cms-locked');

  const pinInput = document.getElementById('admin-pin-input');
  const errorEl = document.getElementById('auth-error-msg');
  if (pinInput) pinInput.value = '';
  if (errorEl) errorEl.innerText = message;

  generateHumanChallenge();
}

function unlockDashboard(verifiedPin) {
  adminPin = verifiedPin;
  sessionStorage.setItem('webar_admin_pin', verifiedPin);
  document.body.classList.remove('cms-locked');

  const errorEl = document.getElementById('auth-error-msg');
  if (errorEl) errorEl.innerText = '';
}

function bindAuthEvents() {
  const form = document.getElementById('admin-auth-form');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (lockoutTimer) return;

    const errorEl = document.getElementById('auth-error-msg');
    const captchaVal = Number(document.getElementById('captcha-input').value);
    const pinVal = document.getElementById('admin-pin-input').value.trim();

    if (captchaVal !== captchaExpected) {
      errorEl.innerText = 'Resposta da verificação humana incorreta.';
      generateHumanChallenge();
      return;
    }

    try {
      const res = await fetch('/api/admin/verify-pin', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-App-Token': apiToken
        },
        body: JSON.stringify({ pin: pinVal })
      });

      const data = await res.json();
      if (res.ok && data.status === 'authorized') {
        unlockDashboard(pinVal);
        await initDashboard();
      } else if (res.status === 429) {
        startLockoutCountdown(data.retryAfter || 30);
      } else {
        errorEl.innerText = data.message || 'PIN administrativo incorreto.';
        generateHumanChallenge();
      }
    } catch (err) {
      errorEl.innerText = 'Erro de comunicação com o servidor.';
    }
  });
}

function bindUploadEvents() {
  const glbInput = document.getElementById('glb-file-input');
  const sizePill = document.getElementById('glb-size-pill');

  if (glbInput && sizePill) {
    glbInput.addEventListener('change', () => {
      const file = glbInput.files[0];
      if (!file) {
        sizePill.className = 'size-pill';
        sizePill.innerText = 'Selecione um arquivo .glb para avaliar o peso.';
        return;
      }

      const mb = file.size / (1024 * 1024);
      if (mb <= 5) {
        sizePill.className = 'size-pill ok';
        sizePill.innerText = `🟢 ${mb.toFixed(2)} MB — Leve: abertura instantânea no celular.`;
      } else if (mb <= 10) {
        sizePill.className = 'size-pill warn';
        sizePill.innerText = `🟡 ${mb.toFixed(2)} MB — Moderado: pode levar alguns segundos no Wi-Fi.`;
      } else if (mb <= 25) {
        sizePill.className = 'size-pill danger';
        sizePill.innerText = `🔴 ${mb.toFixed(2)} MB — Pesado: risco de lentidão em celulares antigos.`;
      } else {
        sizePill.className = 'size-pill danger';
        sizePill.innerText = `⛔ ${mb.toFixed(2)} MB — Excede o limite máximo de 25 MB do servidor.`;
      }
    });
  }

  document.getElementById('btn-upload-glb')?.addEventListener('click', () => uploadAsset('model'));
  document.getElementById('btn-upload-mind')?.addEventListener('click', () => uploadAsset('target'));
}

async function uploadAsset(uploadType) {
  const isModel = uploadType === 'model';
  const input = document.getElementById(isModel ? 'glb-file-input' : 'mind-file-input');
  const statusEl = document.getElementById(isModel ? 'glb-upload-status' : 'mind-upload-status');
  const file = input?.files[0];

  if (!file) {
    statusEl.innerText = `Selecione primeiro um arquivo ${isModel ? '.glb' : '.mind'}.`;
    return;
  }

  if (!isModel && !confirm('Substituir o targets.mind atual? Certifique-se de que os índices dos alvos na tabela abaixo correspondem à ordem compilada.')) {
    return;
  }

  statusEl.innerText = 'Enviando e validando cabeçalho binário...';

  try {
    const res = await fetch('/api/upload', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/octet-stream',
        'X-App-Token': apiToken,
        'X-Admin-Pin': adminPin,
        'X-Upload-Type': uploadType,
        'X-File-Name': encodeURIComponent(file.name)
      },
      body: file
    });

    if (res.status === 401) {
      lockDashboard('Sessão expirada. Informe o PIN novamente.');
      return;
    }

    const result = await res.json();
    if (!res.ok) {
      statusEl.innerText = `Erro: ${result.message || 'Falha no envio.'}`;
      return;
    }

    statusEl.innerText = result.message;
    input.value = '';

    if (isModel) {
      const assignVal = document.getElementById('glb-target-assign')?.value;
      if (assignVal === 'NEW') {
        const nextIdx = cmsData.items.length > 0
          ? Math.max(...cmsData.items.map(i => Number(i.targetIndex))) + 1
          : 0;
        cmsData.items.push({
          id: `item-${nextIdx + 1}`,
          name: result.fileName.replace('.glb', ''),
          targetIndex: nextIdx,
          modelFile: result.fileName,
          scale: '0.25 0.25 0.25',
          rotation: '0 0 0',
          active: true
        });
        await saveConfig(true);
      } else if (assignVal !== '') {
        const idx = Number(assignVal);
        if (cmsData.items[idx]) {
          cmsData.items[idx].modelFile = result.fileName;
          await saveConfig(true);
        }
      }
    }

    await refreshAssets();
    renderModelsTable();
  } catch (err) {
    statusEl.innerText = 'Erro de rede durante o upload.';
  }
}

function bindToolbarEvents() {
  document.getElementById('btn-theme').addEventListener('click', () => {
    const html = document.documentElement;
    const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
  });

  document.getElementById('btn-font-inc').addEventListener('click', () => {
    fontSizePx = Math.min(20, fontSizePx + 1);
    document.documentElement.style.setProperty('--base-font', `${fontSizePx}px`);
  });

  document.getElementById('btn-font-dec').addEventListener('click', () => {
    fontSizePx = Math.max(13, fontSizePx - 1);
    document.documentElement.style.setProperty('--base-font', `${fontSizePx}px`);
  });

  document.getElementById('btn-refresh').addEventListener('click', initDashboard);
  document.getElementById('btn-export-csv').addEventListener('click', exportCSV);
  document.getElementById('btn-print').addEventListener('click', () => {
    document.getElementById('report-meta').innerText = `Gerado em: ${new Date().toLocaleString('pt-BR')}`;
    window.print();
  });
  document.getElementById('btn-save-config').addEventListener('click', () => saveConfig(false));

  document.getElementById('btn-add-target')?.addEventListener('click', () => {
    const nextIdx = cmsData.items.length > 0
      ? Math.max(...cmsData.items.map(i => Number(i.targetIndex))) + 1
      : 0;
    const defaultModel = availableModels[0]?.name || `modelo_${nextIdx + 1}.glb`;

    cmsData.items.push({
      id: `item-${nextIdx + 1}`,
      name: `Novo Alvo #${nextIdx}`,
      targetIndex: nextIdx,
      modelFile: defaultModel,
      scale: '0.25 0.25 0.25',
      rotation: '0 0 0',
      active: true
    });

    renderModelsTable();
    renderAssignDropdown();
  });

  const lockBtn = document.getElementById('btn-lock-cms');
  if (lockBtn) {
    lockBtn.addEventListener('click', () => {
      lockDashboard('Painel bloqueado manualmente.');
    });
  }

  const pauseBtn = document.getElementById('btn-toggle-pause');
  if (pauseBtn) {
    pauseBtn.addEventListener('click', async () => {
      try {
        const res = await fetch('/api/toggle-pause', {
          method: 'POST',
          headers: {
            'X-App-Token': apiToken,
            'X-Admin-Pin': adminPin
          }
        });

        if (res.status === 401) {
          lockDashboard('Sessão expirada. Informe o PIN novamente.');
          return;
        }

        const data = await res.json();
        pauseBtn.innerText = data.paused ? 'Retomar AR' : 'Pausar AR';
        alert(data.message);
      } catch (err) {
        alert('Erro ao alternar pausa da exposição.');
      }
    });
  }

  const shutdownBtn = document.getElementById('btn-shutdown');
  if (shutdownBtn) {
    shutdownBtn.addEventListener('click', async () => {
      if (!confirm('Deseja realmente encerrar o servidor WebAR? Os celulares conectados perderão acesso até que ele seja iniciado novamente.')) {
        return;
      }
      try {
        const res = await fetch('/api/shutdown', {
          method: 'POST',
          headers: {
            'X-App-Token': apiToken,
            'X-Admin-Pin': adminPin
          }
        });

        if (res.status === 401) {
          lockDashboard('Sessão expirada. Informe o PIN novamente.');
          return;
        }

        const data = await res.json();
        document.body.classList.remove('cms-locked');
        document.body.innerHTML = `
          <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;text-align:center;gap:12px;padding:24px;">
            <h1 style="color:#f87171;">Servidor Encerrado</h1>
            <p style="color:#94a3b8;">${data.message} Você já pode fechar esta aba.</p>
          </div>
        `;
      } catch (err) {
        alert('Não foi possível encerrar o servidor.');
      }
    });
  }
}

async function refreshAssets() {
  const res = await fetch('/api/assets', {
    headers: {
      'X-App-Token': apiToken,
      'X-Admin-Pin': adminPin
    }
  });
  if (!res.ok) return;

  const data = await res.json();
  availableModels = data.models || [];
  targetBundleInfo = data.targetBundle || { exists: false };

  const countBadge = document.getElementById('assets-count-badge');
  if (countBadge) {
    countBadge.innerText = `${availableModels.length} modelo(s) .glb no disco`;
  }

  const mindInfoEl = document.getElementById('mind-current-info');
  if (mindInfoEl) {
    if (targetBundleInfo.exists) {
      mindInfoEl.className = 'size-pill ok';
      mindInfoEl.innerText = `Ativo: targets.mind (${formatBytes(targetBundleInfo.sizeBytes)}) — Atualizado em ${targetBundleInfo.updatedAt}`;
    } else {
      mindInfoEl.className = 'size-pill danger';
      mindInfoEl.innerText = 'Nenhum targets.mind encontrado em storage/targets/.';
    }
  }
}

async function initDashboard() {
  try {
    const infoRes = await fetch('/api/server-info');
    if (infoRes.ok) {
      const info = await infoRes.json();
      apiToken = info.token || '';

      if (info.adminLockedSeconds > 0) {
        lockDashboard('');
        startLockoutCountdown(info.adminLockedSeconds);
        return;
      }

      const testLink = document.getElementById('link-test-ar');
      if (testLink && info.webArUrl) testLink.href = info.webArUrl;

      const pauseBtn = document.getElementById('btn-toggle-pause');
      if (pauseBtn) {
        pauseBtn.innerText = info.paused ? 'Retomar AR' : 'Pausar AR';
      }
    }

    if (adminPin) {
      const verifyRes = await fetch('/api/admin/verify-pin', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-App-Token': apiToken
        },
        body: JSON.stringify({ pin: adminPin })
      });

      if (verifyRes.ok) {
        unlockDashboard(adminPin);
      } else {
        lockDashboard('');
        return;
      }
    } else {
      lockDashboard('');
      return;
    }

    const [analyticsRes, configRes] = await Promise.all([
      fetch('/api/analytics'),
      fetch('/api/config?dashboard=1', { headers: { 'X-App-Token': apiToken } }),
      refreshAssets()
    ]);

    if (analyticsRes.ok) analyticsData = await analyticsRes.json();
    if (configRes.ok) cmsData = await configRes.json();

    renderKPIs();
    renderTargetsChart();
    renderHourlyChart();
    renderAssignDropdown();
    renderModelsTable();
  } catch (err) {
    console.error('[Dashboard] Falha ao carregar dados:', err);
  }
}

function renderAssignDropdown() {
  const select = document.getElementById('glb-target-assign');
  if (!select) return;

  const options = [
    '<option value="">Apenas salvar na pasta storage/models</option>',
    ...(cmsData.items || []).map((item, idx) =>
      `<option value="${idx}">Substituir modelo do Alvo #${item.targetIndex} (${item.name})</option>`
    ),
    '<option value="NEW">+ Criar novo índice de alvo na tabela</option>'
  ];
  select.innerHTML = options.join('');
}

function formatDuration(seconds) {
  if (!seconds || seconds <= 0) return '0s';
  if (seconds < 60) return `${seconds}s`;
  const min = Math.floor(seconds / 60);
  const sec = seconds % 60;
  return `${min}m ${sec}s`;
}

function renderKPIs() {
  const viewsMap = analyticsData.viewsByTarget || {};
  const totalViews = Object.values(viewsMap).reduce((acc, v) => acc + Number(v || 0), 0);

  document.getElementById('kpi-sessions').innerText = analyticsData.totalSessions || 0;
  document.getElementById('kpi-duration').innerText = formatDuration(analyticsData.averageSessionSeconds);
  document.getElementById('kpi-views').innerText = totalViews;

  let topIndex = null;
  let topViews = 0;

  Object.entries(viewsMap).forEach(([idx, count]) => {
    if (Number(count) > topViews) {
      topViews = Number(count);
      topIndex = idx;
    }
  });

  const topTargetEl = document.getElementById('kpi-top-target');
  const topCountEl = document.getElementById('kpi-top-count');

  if (topIndex !== null && topViews > 0) {
    const matched = (cmsData.items || []).find(i => String(i.targetIndex) === String(topIndex));
    topTargetEl.innerText = matched ? matched.name : `Alvo #${topIndex}`;
    topCountEl.innerText = `${topViews} visualizações registradas`;
  } else {
    topTargetEl.innerText = '—';
    topCountEl.innerText = 'Aguardando leituras';
  }
}

function renderTargetsChart() {
  const container = document.getElementById('targets-chart');
  const items = cmsData.items || [];
  const viewsMap = analyticsData.viewsByTarget || {};

  if (!items.length) {
    container.innerHTML = '<p class="empty-msg">Nenhum modelo cadastrado em data.json.</p>';
    return;
  }

  const rows = items.map(item => ({
    label: `#${item.targetIndex} — ${item.name}`,
    views: Number(viewsMap[String(item.targetIndex)] || 0)
  }));

  const maxViews = Math.max(1, ...rows.map(r => r.views));

  container.innerHTML = rows.map(row => {
    const pct = Math.round((row.views / maxViews) * 100);
    return `
      <div class="bar-row">
        <div class="bar-meta">
          <span>${row.label}</span>
          <span>${row.views} views</span>
        </div>
        <div class="bar-track">
          <div class="bar-fill" style="width: ${pct}%"></div>
        </div>
      </div>
    `;
  }).join('');
}

function renderHourlyChart() {
  const container = document.getElementById('hourly-chart');
  const hours = analyticsData.hourlyActivity || new Array(24).fill(0);
  const maxVal = Math.max(1, ...hours);

  container.innerHTML = hours.map((count, hour) => {
    const heightPct = Math.round((count / maxVal) * 100);
    const label = hour % 3 === 0 ? `${String(hour).padStart(2, '0')}h` : '';
    return `
      <div class="hour-col" title="${String(hour).padStart(2, '0')}:00 — ${count} eventos">
        <div class="hour-bar" style="height: ${Math.max(4, heightPct)}%"></div>
        <span class="hour-label">${label}</span>
      </div>
    `;
  }).join('');
}

function buildModelSelectOptions(currentFile) {
  const names = new Set(availableModels.map(m => m.name));
  if (currentFile) names.add(currentFile);

  return Array.from(names).sort().map(fname => {
    const found = availableModels.find(m => m.name === fname);
    const label = found ? `${fname} (${formatBytes(found.sizeBytes)})` : fname;
    const selected = fname === currentFile ? 'selected' : '';
    return `<option value="${fname}" ${selected}>${label}</option>`;
  }).join('');
}

function renderModelsTable() {
  const tbody = document.getElementById('models-tbody');
  const items = cmsData.items || [];
  const viewsMap = analyticsData.viewsByTarget || {};

  tbody.innerHTML = items.map((item, idx) => {
    const views = viewsMap[String(item.targetIndex)] || 0;
    return `
      <tr>
        <td><strong>#${item.targetIndex}</strong></td>
        <td><input type="text" data-idx="${idx}" data-field="name" value="${item.name}"></td>
        <td>
          <select class="cms-select" data-idx="${idx}" data-field="modelFile">
            ${buildModelSelectOptions(item.modelFile)}
          </select>
        </td>
        <td><input type="text" data-idx="${idx}" data-field="scale" value="${item.scale || '0.25 0.25 0.25'}"></td>
        <td><input type="text" data-idx="${idx}" data-field="rotation" value="${item.rotation || '0 0 0'}"></td>
        <td>${views}</td>
        <td><input type="checkbox" data-idx="${idx}" data-field="active" ${item.active ? 'checked' : ''}></td>
      </tr>
    `;
  }).join('');

  tbody.querySelectorAll('input, select').forEach(el => {
    el.addEventListener('change', (e) => {
      const idx = Number(e.target.getAttribute('data-idx'));
      const field = e.target.getAttribute('data-field');
      cmsData.items[idx][field] = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
      if (field === 'name') renderAssignDropdown();
    });
  });
}

async function saveConfig(silent = false) {
  try {
    const res = await fetch('/api/config', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-App-Token': apiToken,
        'X-Admin-Pin': adminPin
      },
      body: JSON.stringify(cmsData)
    });

    if (res.status === 401) {
      lockDashboard('Sessão expirada. Informe o PIN novamente para salvar.');
      return;
    }

    const result = await res.json();
    if (!silent) alert(result.message || 'Configurações salvas!');
    renderTargetsChart();
    renderAssignDropdown();
  } catch (err) {
    if (!silent) alert('Erro ao salvar alterações no servidor.');
  }
}

function exportCSV() {
  const viewsMap = analyticsData.viewsByTarget || {};
  const lines = [
    ['Indice', 'Nome do Modelo', 'Arquivo GLB', 'Status', 'Visualizacoes'].join(';')
  ];

  (cmsData.items || []).forEach(item => {
    lines.push([
      item.targetIndex,
      `"${item.name}"`,
      item.modelFile,
      item.active ? 'Ativo' : 'Inativo',
      viewsMap[String(item.targetIndex)] || 0
    ].join(';'));
  });

  lines.push('');
  lines.push(`Total de Sessoes;${analyticsData.totalSessions || 0}`);
  lines.push(`Duracao Media (s);${analyticsData.averageSessionSeconds || 0}`);

  const blob = new Blob(['\uFEFF' + lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = `relatorio-webar-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
}