let cmsData = { items: [] };

document.addEventListener('DOMContentLoaded', () => {
    carregarConfig();
    document.getElementById('btn-salvar').addEventListener('click', salvarAlteracoes);
});

async function carregarConfig() {
    try {
        const res = await fetch('/api/config');
        cmsData = await res.json();
        renderizarLista();
    } catch (err) {
        console.error("Falha ao carregar configuração:", err);
    }
}

function renderizarLista() {
    const container = document.getElementById('items-container');
    container.innerHTML = '';

    cmsData.items.forEach((item, index) => {
        const div = document.createElement('div');
        div.className = 'item-row';
        div.innerHTML = `
      <strong>Target #${item.targetIndex}</strong>
      <input type="text" value="${item.name}" data-index="${index}" class="input-nome">
      <span>Arquivo: <code>${item.modelFile}</code></span>
      <button onclick="previewModelo('${item.modelFile}', '${item.name}')">Ver 3D</button>
    `;
        container.appendChild(div);
    });

    // Listener para capturar edições nos inputs
    document.querySelectorAll('.input-nome').forEach(input => {
        input.addEventListener('change', (e) => {
            const idx = e.target.getAttribute('data-index');
            cmsData.items[idx].name = e.target.value;
        });
    });
}

function previewModelo(arquivo, nome) {
    const viewer = document.getElementById('viewer');
    viewer.src = `/storage/models/${arquivo}`;
    document.getElementById('preview-info').innerText = `Exibindo: ${nome} (${arquivo})`;
}

async function salvarAlteracoes() {
    try {
        const res = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(cmsData)
        });
        const result = await res.json();
        alert(result.message);
    } catch (err) {
        alert("Erro ao salvar alterações no servidor.");
    }
}