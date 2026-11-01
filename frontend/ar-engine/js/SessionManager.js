export class SessionManager {
  constructor(timeoutMs = 180000, onSleepCallback = () => {}) {
    this.timeoutMs = timeoutMs;
    this.onSleep = onSleepCallback;
    this.timer = null;
    this.isSleeping = false;

    this.initListeners();
    this.resetTimer();
  }

  initListeners() {
    // Pausa imediatamente se o usuário mudar de aba ou minimizar o navegador
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) {
        this.sleep("Aba minimizada");
      }
    });

    // Eventos de toque na tela redefinem o contador de inatividade
    window.addEventListener('touchstart', () => this.resetTimer(), { passive: true });
  }

  resetTimer() {
    if (this.isSleeping) return;
    clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.sleep("Tempo limite de inatividade atingido (3 min)");
    }, this.timeoutMs);
  }

  sleep(reason) {
    if (this.isSleeping) return;
    this.isSleeping = true;
    clearTimeout(this.timer);
    
    // Interrompe o fluxo da câmera no smartphone
    const video = document.querySelector('video');
    if (video && video.srcObject) {
      video.srcObject.getTracks().forEach(track => track.stop());
    }

    // Pausa o loop de renderização do A-Frame
    const scene = document.querySelector('a-scene');
    if (scene) scene.pause();

    console.warn(`[SessionManager] Câmera e WebGL pausados. Motivo: ${reason}`);
    this.onSleep(reason);
  }

  wakeUp() {
    window.location.reload(); // Recarrega a página de forma limpa para reiniciar a câmera
  }
}