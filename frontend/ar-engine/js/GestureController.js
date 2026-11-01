export class GestureController {
  constructor(targetEntity) {
    this.entity = targetEntity;
    this.previousTouch = null;
    this.initialPinchDistance = null;
    this.initialScale = { x: 1, y: 1, z: 1 };

    this.initGestures();
  }

  initGestures() {
    const scene = document.querySelector('a-scene');

    scene.addEventListener('touchstart', (e) => {
      if (e.touches.length === 1) {
        this.previousTouch = { x: e.touches[0].clientX, y: e.touches[0].clientY };
      } else if (e.touches.length === 2) {
        this.initialPinchDistance = this.getDistance(e.touches[0], e.touches[1]);
        const currentScale = this.entity.getAttribute('scale') || { x: 1, y: 1, z: 1 };
        this.initialScale = { ...currentScale };
      }
    }, { passive: true });

    scene.addEventListener('touchmove', (e) => {
      // Dedo: Rotação nos eixos X e Y
      if (e.touches.length === 1 && this.previousTouch) {
        const deltaX = e.touches[0].clientX - this.previousTouch.x;
        const deltaY = e.touches[0].clientY - this.previousTouch.y;

        const currentRotation = this.entity.getAttribute('rotation') || { x: 0, y: 0, z: 0 };
        this.entity.setAttribute('rotation', {
          x: currentRotation.x + deltaY * 0.5,
          y: currentRotation.y + deltaX * 0.5,
          z: currentRotation.z
        });

        this.previousTouch = { x: e.touches[0].clientX, y: e.touches[0].clientY };
      } 
      // Dedos: Zoom (Pinch-to-scale)
      else if (e.touches.length === 2 && this.initialPinchDistance) {
        const currentDistance = this.getDistance(e.touches[0], e.touches[1]);
        const factor = currentDistance / this.initialPinchDistance;

        // Limita a escala entre 0.1x e 3.0x para evitar estouro visual
        const newScale = Math.min(Math.max(this.initialScale.x * factor, 0.1), 3.0);
        this.entity.setAttribute('scale', { x: newScale, y: newScale, z: newScale });
      }
    }, { passive: true });

    scene.addEventListener('touchend', () => {
      this.previousTouch = null;
      this.initialPinchDistance = null;
    });
  }

  getDistance(t1, t2) {
    const dx = t1.clientX - t2.clientX;
    const dy = t1.clientY - t2.clientY;
    return Math.sqrt(dx * dx + dy * dy);
  }
}