export class SignatureCanvas {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    this.ctx = this.canvas.getContext('2d');
    this.isDrawing = false;
    this.hasDrawn = false;
    this.currentColor = '#ffffff';

    this.initCanvas();
    this.bindEvents();
  }

  initCanvas() {
    this.ctx.lineWidth = 3;
    this.ctx.lineCap = 'round';
    this.ctx.lineJoin = 'round';
    this.clear();
  }

  setColor(color) {
    this.currentColor = color;
    this.ctx.strokeStyle = color;
  }

  clear() {
    this.ctx.fillStyle = '#020617'; // Slate 950
    this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
    this.ctx.strokeStyle = this.currentColor;
    this.hasDrawn = false;
  }

  getPos(e) {
    const rect = this.canvas.getBoundingClientRect();
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    
    const scaleX = this.canvas.width / rect.width;
    const scaleY = this.canvas.height / rect.height;

    return {
      x: (clientX - rect.left) * scaleX,
      y: (clientY - rect.top) * scaleY
    };
  }

  startDrawing(e) {
    e.preventDefault();
    this.isDrawing = true;
    const pos = this.getPos(e);
    this.ctx.beginPath();
    this.ctx.moveTo(pos.x, pos.y);
  }

  draw(e) {
    if (!this.isDrawing) return;
    e.preventDefault();
    const pos = this.getPos(e);
    this.ctx.lineTo(pos.x, pos.y);
    this.ctx.stroke();
    this.hasDrawn = true;
  }

  stopDrawing() {
    this.isDrawing = false;
    this.ctx.closePath();
  }

  bindEvents() {
    this.canvas.addEventListener('mousedown', (e) => this.startDrawing(e));
    this.canvas.addEventListener('mousemove', (e) => this.draw(e));
    this.canvas.addEventListener('mouseup', () => this.stopDrawing());
    this.canvas.addEventListener('mouseleave', () => this.stopDrawing());

    this.canvas.addEventListener('touchstart', (e) => this.startDrawing(e));
    this.canvas.addEventListener('touchmove', (e) => this.draw(e));
    this.canvas.addEventListener('touchend', () => this.stopDrawing());
  }

  toBase64() {
    return this.canvas.toDataURL('image/png');
  }

  isEmpty() {
    return !this.hasDrawn;
  }
}