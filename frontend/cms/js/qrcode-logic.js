async function initQRCode() {
  try {
    const response = await fetch('/api/server-info');
    if (!response.ok) throw new Error("Erro na requisição HTTP " + response.status);

    const data = await response.json();
    document.getElementById('url-text').innerText = data.webArUrl;

    // Instancia o QRious apontando para o elemento <canvas>
    new QRious({
      element: document.getElementById('qrcode-canvas'),
      value: data.webArUrl,
      size: 250,
      level: 'H' // Nível alto de correção de erro para leitura rápida da câmera
    });
  } catch (err) {
    console.error("Erro ao gerar QR Code:", err);
    document.getElementById('url-text').innerText = 'Erro ao conectar com o servidor local.';
  }
}

document.addEventListener('DOMContentLoaded', initQRCode);