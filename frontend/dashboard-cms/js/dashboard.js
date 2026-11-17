let apiToken = '';
let cmsData = { version: '1.0.0', items: [] };
let analyticsData = {
  totalSessions: 0,
  averageSessionSeconds: 0,
  viewsByTarget: {},
  hourlyActivity: new Array(24).fill(0)
};
let fontSizePx = 16;

document.addEventListener('DOMContentLoaded', async () => {
  bindToolbarEvents();
  await initDashboard();
});

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
  document.getElementById('btn-save-config').addEventListener('click', saveConfig);

  const pauseBtn = document.getElementById('btn-toggle-pause');
  if (pauseBtn) {
    pauseBtn.addEventListener('click', async () => {
      try {
        const res = await fetch('/api/toggle-pause', {
          method: 'POST',
          headers: { 'X-App-Token': apiToken }
        });
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
          headers: { 'X-App-Token': apiToken }
        });
        const data = await res.json();
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

async function initDashboard() {
  try {
    const infoRes = await fetch('/api/server-info');
    if (infoRes.ok) {
      const info = await infoRes.json();
      apiToken = info.token || '';

      const testLink = document.getElementById('link-test-ar');
      if (testLink && info.webArUrl) testLink.href = info.webArUrl;

      const pauseBtn = document.getElementById('btn-toggle-pause');
      if (pauseBtn) {
        pauseBtn.innerText = info.paused ? 'Retomar AR' : 'Pausar AR';
      }
    }

    const [analyticsRes, configRes] = await Promise.all([
      fetch('/api/analytics'),
      fetch('/api/config?dashboard=1', { headers: { 'X-App-Token': apiToken } })
    ]);

    if (analyticsRes.ok) analyticsData = await analyticsRes.json();
    if (configRes.ok) cmsData = await configRes.json();

    renderKPIs();
    renderTargetsChart();
    renderHourlyChart();
    renderModelsTable();
  } catch (err) {
    console.error('[Dashboard] Falha ao carregar dados:', err);
  }
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
        <td><code>${item.modelFile}</code></td>
        <td><input type="text" data-idx="${idx}" data-field="scale" value="${item.scale || '0.25 0.25 0.25'}"></td>
        <td><input type="text" data-idx="${idx}" data-field="rotation" value="${item.rotation || '0 0 0'}"></td>
        <td>${views}</td>
        <td><input type="checkbox" data-idx="${idx}" data-field="active" ${item.active ? 'checked' : ''}></td>
      </tr>
    `;
  }).join('');

  tbody.querySelectorAll('input').forEach(input => {
    input.addEventListener('change', (e) => {
      const idx = Number(e.target.getAttribute('data-idx'));
      const field = e.target.getAttribute('data-field');
      cmsData.items[idx][field] = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
    });
  });
}

async function saveConfig() {
  try {
    const res = await fetch('/api/config', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-App-Token': apiToken
      },
      body: JSON.stringify(cmsData)
    });
    const result = await res.json();
    alert(result.message || 'Configurações salvas!');
    renderTargetsChart();
  } catch (err) {
    alert('Erro ao salvar alterações no servidor.');
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