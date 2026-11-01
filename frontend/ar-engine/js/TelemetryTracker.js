/**
 * Módulo responsável por capturar eventos de sessão e interação WebAR localmente.
 */
export class TelemetryTracker {
  constructor(token) {
    this.token = token;
    this.sessionStartTime = Date.now();
  }

  /**
   * Dispara o evento de telemetria para a API local
   */
  async track(eventType, details = {}) {
    const payload = {
      event: eventType,
      timestamp: new Date().toISOString(),
      sessionDurationSeconds: Math.floor((Date.now() - this.sessionStartTime) / 1000),
      ...details
    };

    try {
      await fetch('/api/telemetry', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-App-Token': this.token
        },
        body: JSON.stringify(payload),
        keepalive: true // Garante o envio mesmo se a aba for fechada
      });
    } catch (err) {
      console.warn('[Telemetry] Falha ao registrar evento:', err);
    }
  }
}