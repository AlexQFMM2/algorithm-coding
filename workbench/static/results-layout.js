// Owns result height, drag/keyboard controls, persistence and collapse state.
export class ResultsLayout {
  constructor(shell, desktop) {
    this.shell = shell;
    this.desktop = desktop;
    this.workspace = document.querySelector('.workspace');
    this.panel = document.querySelector('#results-panel');
    this.handle = document.querySelector('#results-resizer');
    this.preferredHeight = null;
    this.drag = null;
    this.collapsed = false;
    try {
      const saved = Number(localStorage.getItem('acwing.results-height'));
      if (Number.isFinite(saved) && saved >= 180 && saved <= 2000) this.preferredHeight = saved;
    } catch { /* Height can still be adjusted without browser storage. */ }

    this.handle.addEventListener('pointerdown', event => {
      if (event.button !== 0 || !event.isPrimary || !this.desktop.matches || this.collapsed) return;
      event.preventDefault();
      this.handle.focus();
      this.drag = { y: event.clientY, height: this.currentHeight, pointer: event.pointerId };
      this.handle.setPointerCapture(event.pointerId);
      this.shell.dataset.resizing = 'rows';
    });
    this.handle.addEventListener('pointermove', event => {
      if (this.drag) this.setHeight(this.drag.height + this.drag.y - event.clientY);
    });
    for (const event of ['pointerup', 'pointercancel', 'lostpointercapture']) {
      this.handle.addEventListener(event, () => this.finishDrag());
    }
    window.addEventListener('blur', () => this.finishDrag());
    window.addEventListener('resize', () => { this.finishDrag(); this.syncHeight(); });
    this.handle.addEventListener('dblclick', () => this.resetHeight());
    this.handle.addEventListener('keydown', event => {
      if (event.key === 'Escape' && this.drag) {
        this.setHeight(this.drag.height); this.finishDrag(); return;
      }
      if (event.key === 'Enter') { event.preventDefault(); this.resetHeight(); return; }
      const values = { ArrowUp: this.currentHeight + 20, ArrowDown: this.currentHeight - 20,
        Home: 180, End: this.maxHeight };
      if (!(event.key in values)) return;
      event.preventDefault(); this.setHeight(values[event.key]); this.rememberHeight();
    });
    document.querySelector('#results-taller').addEventListener('click', () => this.resizeBy(40));
    document.querySelector('#results-shorter').addEventListener('click', () => this.resizeBy(-40));
    document.querySelector('#toggle-results').addEventListener('click', () => this.expand(this.collapsed));
    this.observer = new ResizeObserver(() => this.syncHeight());
    for (const element of [this.workspace, ...this.workspace.querySelectorAll('.workspace__header, .workspace__footer, #notice')]) {
      this.observer.observe(element);
    }
    this.syncHeight();
  }

  get defaultHeight() { return Math.round(Math.max(180, Math.min(230, innerHeight * .23))); }

  get maxHeight() {
    const style = getComputedStyle(this.workspace);
    const children = [...this.workspace.children].filter(child => getComputedStyle(child).display !== 'none');
    let reserved = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom)
      + parseFloat(style.rowGap) * (children.length - 1);
    for (const child of children) {
      if (child === this.panel || child.classList.contains('workspace__panels')) continue;
      const childStyle = getComputedStyle(child);
      reserved += child.getBoundingClientRect().height + parseFloat(childStyle.marginTop) + parseFloat(childStyle.marginBottom);
    }
    // Reserve enough room for the editor and its controls, including at smaller window heights.
    return Math.max(180, Math.min(2000, Math.floor(this.workspace.clientHeight - reserved - 280)));
  }

  setHeight(value) {
    const maximum = this.maxHeight;
    this.currentHeight = Math.round(Math.max(180, Math.min(maximum, value)));
    this.panel.style.setProperty('--results-panel-height', `${this.currentHeight}px`);
    this.handle.setAttribute('aria-valuenow', this.currentHeight);
    this.handle.setAttribute('aria-valuemax', maximum);
    this.handle.setAttribute('aria-valuetext', `${this.currentHeight} 像素`);
    document.querySelector('#results-taller').disabled = this.currentHeight >= maximum;
    document.querySelector('#results-shorter').disabled = this.currentHeight <= 180;
  }

  syncHeight() {
    if (!this.desktop.matches || this.collapsed || this.drag) return;
    this.setHeight(this.preferredHeight ?? this.defaultHeight);
  }

  rememberHeight() {
    this.preferredHeight = this.currentHeight;
    try { localStorage.setItem('acwing.results-height', this.currentHeight); } catch { /* Optional preference. */ }
  }

  finishDrag() {
    if (!this.drag) return;
    const pointer = this.drag.pointer;
    this.drag = null;
    delete this.shell.dataset.resizing;
    if (this.handle.hasPointerCapture(pointer)) this.handle.releasePointerCapture(pointer);
    this.rememberHeight();
  }

  resizeBy(delta) { this.setHeight(this.currentHeight + delta); this.rememberHeight(); }

  resetHeight() {
    this.preferredHeight = null;
    try { localStorage.removeItem('acwing.results-height'); } catch { /* Optional preference. */ }
    this.syncHeight();
  }

  expand(expand = true) {
    this.finishDrag();
    this.collapsed = !expand;
    document.querySelector('#results-body').hidden = !expand;
    this.panel.classList.toggle('results-panel--collapsed', !expand);
    this.handle.hidden = !expand;
    document.querySelector('#results-size-controls').hidden = !expand;
    const button = document.querySelector('#toggle-results');
    button.setAttribute('aria-expanded', String(expand));
    button.textContent = expand ? '收起' : '展开';
    this.syncHeight();
  }
}
