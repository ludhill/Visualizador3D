export class GestureController {
  constructor(targetEntity) {
    this.entity = targetEntity;
    this.isTargetVisible = true; // Inicia ativo pois é instanciado no primeiro targetFound
    this.previousTouch = null;
    this.previousMidpoint = null;
    this.initialPinchDistance = null;
    this.initialScale = { x: 0.25, y: 0.25, z: 0.25 };

    this.bindTargetVisibility();
    this.initGestures();
  }

  /**
   * Garante que apenas o modelo 3D atualmente visível na câmera responda aos toques.
   */
  bindTargetVisibility() {
    const parentTarget = this.entity.parentElement;
    if (!parentTarget) return;

    parentTarget.addEventListener('targetFound', () => {
      this.isTargetVisible = true;
    });

    parentTarget.addEventListener('targetLost', () => {
      this.isTargetVisible = false;
      this.resetTouchState();
    });
  }

  resetTouchState() {
    this.previousTouch = null;
    this.previousMidpoint = null;
    this.initialPinchDistance = null;
  }

  initGestures() {
    const scene = document.querySelector('a-scene');
    if (!scene) return;

    scene.addEventListener('touchstart', (e) => {
      if (!this.isTargetVisible) return;

      if (e.touches.length === 1) {
        this.previousTouch = {
          x: e.touches[0].clientX,
          y: e.touches[0].clientY
        };
      } else if (e.touches.length === 2) {
        this.initialPinchDistance = this.getDistance(e.touches[0], e.touches[1]);
        this.previousMidpoint = this.getMidpoint(e.touches[0], e.touches[1]);

        const currentScale = this.entity.getAttribute('scale') || { x: 0.25, y: 0.25, z: 0.25 };
        this.initialScale = {
          x: Number(currentScale.x) || 0.25,
          y: Number(currentScale.y) || 0.25,
          z: Number(currentScale.z) || 0.25
        };
      }
    }, { passive: true });

    scene.addEventListener('touchmove', (e) => {
      if (!this.isTargetVisible) return;

      // 1 Dedo: Rotação livre nos eixos X e Y
      if (e.touches.length === 1 && this.previousTouch) {
        const deltaX = e.touches[0].clientX - this.previousTouch.x;
        const deltaY = e.touches[0].clientY - this.previousTouch.y;

        const currentRotation = this.entity.getAttribute('rotation') || { x: 0, y: 0, z: 0 };
        this.entity.setAttribute('rotation', {
          x: currentRotation.x + deltaY * 0.5,
          y: currentRotation.y + deltaX * 0.5,
          z: currentRotation.z
        });

        this.previousTouch = {
          x: e.touches[0].clientX,
          y: e.touches[0].clientY
        };
      }
      // 2 Dedos: Zoom (Pinça) + Pan (Arrasto paralelo simultâneo)
      else if (e.touches.length === 2 && this.initialPinchDistance) {
        // 1. Cálculo da Pinça (Zoom ampliado: 0.05x até 6.0x)
        const currentDistance = this.getDistance(e.touches[0], e.touches[1]);
        const factor = currentDistance / this.initialPinchDistance;
        const newScale = Math.min(Math.max(this.initialScale.x * factor, 0.05), 6.0);

        this.entity.setAttribute('scale', {
          x: newScale,
          y: newScale,
          z: newScale
        });

        // 2. Cálculo do Pan (Translação X/Y pelo ponto médio entre os 2 dedos)
        const currentMidpoint = this.getMidpoint(e.touches[0], e.touches[1]);
        if (this.previousMidpoint) {
          const deltaMidX = currentMidpoint.x - this.previousMidpoint.x;
          const deltaMidY = currentMidpoint.y - this.previousMidpoint.y;

          const currentPos = this.entity.getAttribute('position') || { x: 0, y: 0, z: 0 };
          const panSensitivity = 0.0025;

          this.entity.setAttribute('position', {
            x: currentPos.x + deltaMidX * panSensitivity,
            y: currentPos.y - deltaMidY * panSensitivity,
            z: currentPos.z
          });
        }
        this.previousMidpoint = currentMidpoint;
      }
    }, { passive: true });

    scene.addEventListener('touchend', (e) => {
      if (e.touches.length === 0) {
        this.resetTouchState();
      } else if (e.touches.length === 1) {
        // Se soltou um dos dedos, retoma rotação suave sem salto
        this.initialPinchDistance = null;
        this.previousMidpoint = null;
        this.previousTouch = {
          x: e.touches[0].clientX,
          y: e.touches[0].clientY
        };
      }
    });
  }

  getDistance(t1, t2) {
    const dx = t1.clientX - t2.clientX;
    const dy = t1.clientY - t2.clientY;
    return Math.hypot(dx, dy);
  }

  getMidpoint(t1, t2) {
    return {
      x: (t1.clientX + t2.clientX) / 2,
      y: (t1.clientY + t2.clientY) / 2
    };
  }
}