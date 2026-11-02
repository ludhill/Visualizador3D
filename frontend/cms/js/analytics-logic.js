// Token oficial de acesso às APIs
const API_TOKEN = 'WEBAR_2026';

// Instâncias globais dos gráficos para permitir atualização (destroy & re-render)
let targetChartInstance = null;
let hourlyChartInstance = null;

document.addEventListener('DOMContentLoaded', () => {
  initAccessibility();
  loadAnalyticsData();

  const btnRefresh = document.getElementById('btn-refresh');
  if (btnRefresh) {
    btnRefresh.addEventListener('click', () => {
      loadAnalyticsData();
    });
  }

  // Ação de Impressão / PDF
  const btnPrint = document.getElementById('btn-print');
  if (btnPrint) {
    btnPrint.addEventListener('click', () => {
      window.print();
    });
  }
});

/**
 * Gestão de Acessibilidade (Temas e Fontes) com suporte a localStorage
 */
function initAccessibility() {
  const themeSelect = document.getElementById('theme-select');
  const fontSelect = document.getElementById('font-select');

  const savedTheme = localStorage.getItem('cms_theme') || 'dark';
  const savedFont = localStorage.getItem('cms_font') || 'normal';

  // Tema continua no body, fonte vai para o html (documentElement)
  document.body.setAttribute('data-theme', savedTheme);
  document.documentElement.setAttribute('data-font', savedFont);

  if (themeSelect) themeSelect.value = savedTheme;
  if (fontSelect) fontSelect.value = savedFont;

  themeSelect?.addEventListener('change', (e) => {
    const theme = e.target.value;
    document.body.setAttribute('data-theme', theme);
    localStorage.setItem('cms_theme', theme);
    updateChartThemeColors();
  });

  fontSelect?.addEventListener('change', (e) => {
    const font = e.target.value;
    document.documentElement.setAttribute('data-font', font);
    localStorage.setItem('cms_font', font);
  });
}

/**
 * Procura e consome os dados da API em Python (/api/analytics)
 */
async function loadAnalyticsData() {
  const btnRefresh = document.getElementById('btn-refresh');
  if (btnRefresh) {
    btnRefresh.disabled = true;
    btnRefresh.innerText = 'A carregar...';
  }

  try {
    const response = await fetch(`/api/analytics?token=${API_TOKEN}`);
    if (!response.ok) {
      throw new Error(`Status ${response.status}`);
    }

    const data = await response.json();
    updateKPIs(data);
    renderCharts(data);
  } catch (error) {
    console.error('[Analytics CMS] Erro ao carregar métricas:', error);
    showEmptyState();
  } finally {
    if (btnRefresh) {
      btnRefresh.disabled = false;
      btnRefresh.innerText = 'Atualizar Dados';
    }
  }
}

/**
 * Preenche os cartões numéricos (KPIs)
 */
function updateKPIs(data) {
  const kpiSessions = document.getElementById('kpi-sessions');
  const kpiAvgTime = document.getElementById('kpi-avg-time');
  const kpiTopTarget = document.getElementById('kpi-top-target');

  const totalSessions = data.totalSessions || 0;
  const avgSeconds = data.averageSessionSeconds || 0;
  const viewsByTarget = data.viewsByTarget || {};

  // Total de Sessões
  if (kpiSessions) kpiSessions.innerText = totalSessions.toLocaleString('pt-PT');

  // Tempo Médio Formatado
  if (kpiAvgTime) {
    if (avgSeconds >= 60) {
      const mins = Math.floor(avgSeconds / 60);
      const secs = avgSeconds % 60;
      kpiAvgTime.innerText = `${mins}m ${secs}s`;
    } else {
      kpiAvgTime.innerText = `${avgSeconds}s`;
    }
  }

  // Modelo 3D Mais Visto
  if (kpiTopTarget) {
    const targets = Object.keys(viewsByTarget);
    if (targets.length === 0) {
      kpiTopTarget.innerText = 'N/A';
    } else {
      let topTarget = targets[0];
      let maxViews = viewsByTarget[topTarget];

      for (const t of targets) {
        if (viewsByTarget[t] > maxViews) {
          maxViews = viewsByTarget[t];
          topTarget = t;
        }
      }
      kpiTopTarget.innerText = `Target ${topTarget} (${maxViews})`;
    }
  }
}

/**
 * Renderiza ou atualiza os gráficos com Chart.js
 */
function renderCharts(data) {
  const viewsByTarget = data.viewsByTarget || {};
  const hourlyActivity = data.hourlyActivity || Array(24).fill(0);

  // Destrói instâncias anteriores para evitar flickering ou duplicação no canvas
  if (targetChartInstance) targetChartInstance.destroy();
  if (hourlyChartInstance) hourlyChartInstance.destroy();

  const colors = getThemeColors();

  // --- Gráfico 1: Visualizações por Modelo (Doughnut) ---
  const ctxTargets = document.getElementById('chart-targets')?.getContext('2d');
  if (ctxTargets) {
    const labels = Object.keys(viewsByTarget).map(t => `Target ${t}`);
    const values = Object.values(viewsByTarget);

    targetChartInstance = new Chart(ctxTargets, {
      type: 'doughnut',
      data: {
        labels: labels.length > 0 ? labels : ['Sem dados'],
        datasets: [{
          data: values.length > 0 ? values : [1],
          backgroundColor: values.length > 0 
            ? ['#38bdf8', '#4ade80', '#fbbf24', '#f87171', '#c084fc']
            : ['#334155'],
          borderWidth: 2,
          borderColor: colors.cardBg
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'bottom',
            labels: { color: colors.text }
          }
        }
      }
    });
  }

  // --- Gráfico 2: Fluxo de Acessos por Horário 24h (Barra) ---
  const ctxHourly = document.getElementById('chart-hourly')?.getContext('2d');
  if (ctxHourly) {
    const hoursLabels = Array.from({ length: 24 }, (_, i) => `${String(i).padStart(2, '0')}:00`);

    hourlyChartInstance = new Chart(ctxHourly, {
      type: 'bar',
      data: {
        labels: hoursLabels,
        datasets: [{
          label: 'Acessos',
          data: hourlyActivity,
          backgroundColor: '#0284c7',
          borderRadius: 4
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: {
            ticks: { color: colors.text, font: { size: 10 } },
            grid: { color: 'transparent' }
          },
          y: {
            beginAtZero: true,
            ticks: { color: colors.text, precision: 0 },
            grid: { color: colors.grid }
          }
        },
        plugins: {
          legend: { display: false }
        }
      }
    });
  }
}

/**
 * Retorna as cores apropriadas do gráfico com base no tema ativo
 */
function getThemeColors() {
  const currentTheme = document.body.getAttribute('data-theme') || 'dark';
  if (currentTheme === 'light') {
    return { text: '#0f172a', grid: '#e2e8f0', cardBg: '#ffffff' };
  } else if (currentTheme === 'high-contrast') {
    return { text: '#ffffff', grid: '#444444', cardBg: '#121212' };
  }
  return { text: '#94a3b8', grid: '#334155', cardBg: '#1e293b' };
}

/**
 * Adapta os gráficos dinamicamente quando o utilizador muda o tema
 */
function updateChartThemeColors() {
  const colors = getThemeColors();

  if (targetChartInstance) {
    targetChartInstance.options.plugins.legend.labels.color = colors.text;
    targetChartInstance.data.datasets[0].borderColor = colors.cardBg;
    targetChartInstance.update();
  }

  if (hourlyChartInstance) {
    hourlyChartInstance.options.scales.x.ticks.color = colors.text;
    hourlyChartInstance.options.scales.y.ticks.color = colors.text;
    hourlyChartInstance.options.scales.y.grid.color = colors.grid;
    hourlyChartInstance.update();
  }
}

/**
 * Trata o estado vazio ou falhas de comunicação
 */
function showEmptyState() {
  updateKPIs({ totalSessions: 0, averageSessionSeconds: 0, viewsByTarget: {} });
  renderCharts({ totalSessions: 0, averageSessionSeconds: 0, viewsByTarget: {}, hourlyActivity: Array(24).fill(0) });
}