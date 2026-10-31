import { ResultsLayout } from './results-layout.js';

// Owns navigation presentation and sidebar sizing; composes the result layout.
// The shell exposes --app-shell-sidebar-width; child panels own their internals.
export class WorkspaceLayout {
  constructor() {
    this.shell = document.querySelector('.app-shell');
    this.splitter = document.querySelector('#sidebar-resizer');
    this.toggle = document.querySelector('#sidebar-toggle');
    this.desktop = matchMedia('(min-width: 821px)');
    this.details = false;
    this.hasDetails = false;
    this.preferredWidth = 360;
    this.drag = null;
    try {
      const saved = Number(localStorage.getItem('acwing.sidebar-width'));
      if (Number.isFinite(saved) && saved >= 260 && saved <= 720) this.preferredWidth = saved;
    } catch { /* Resizing still works for this session. */ }

    this.toggle.addEventListener('click', () => this.showDetails(!this.details, true));
    this.widthControl = document.querySelector('#sidebar-width');
    this.widthControl.addEventListener('input', () => {
      this.setWidth(Number(this.widthControl.value)); this.rememberWidth();
    });
    document.querySelector('#sidebar-width-reset').addEventListener('click', () => {
      this.setWidth(360); this.rememberWidth();
    });
    this.splitter.addEventListener('pointerdown', event => {
      if (event.button !== 0 || !event.isPrimary || !this.desktop.matches) return;
      event.preventDefault();
      this.splitter.focus();
      this.drag = { x: event.clientX, width: this.currentWidth, pointer: event.pointerId };
      this.splitter.setPointerCapture(event.pointerId);
      this.shell.dataset.resizing = 'columns';
    });
    this.splitter.addEventListener('pointermove', event => {
      if (this.drag) this.setWidth(this.drag.width + event.clientX - this.drag.x);
    });
    const finish = () => {
      if (!this.drag) return;
      this.drag = null;
      delete this.shell.dataset.resizing;
      this.rememberWidth();
    };
    for (const event of ['pointerup', 'pointercancel', 'lostpointercapture']) this.splitter.addEventListener(event, finish);
    window.addEventListener('blur', finish);
    this.splitter.addEventListener('dblclick', () => { this.setWidth(360); this.rememberWidth(); });
    this.splitter.addEventListener('keydown', event => {
      const values = { ArrowLeft: this.currentWidth - 20, ArrowRight: this.currentWidth + 20,
        Home: 260, End: this.maxWidth, Enter: 360 };
      if (event.key === 'Escape' && this.drag) {
        this.setWidth(this.drag.width); finish(); return;
      }
      if (!(event.key in values)) return;
      event.preventDefault(); this.setWidth(values[event.key]); this.rememberWidth();
    });
    window.addEventListener('resize', () => {
      finish(); this.setWidth(this.preferredWidth);
    });
    this.setWidth(this.preferredWidth);
    this.results = new ResultsLayout(this.shell, this.desktop);
  }

  get maxWidth() { return Math.max(260, Math.min(720, innerWidth - 500, Math.floor(innerWidth * .55))); }

  setWidth(value) {
    this.currentWidth = Math.round(Math.max(260, Math.min(this.maxWidth, value)));
    this.shell.style.setProperty('--app-shell-sidebar-width', `${this.currentWidth}px`);
    this.splitter.setAttribute('aria-valuenow', this.currentWidth);
    this.splitter.setAttribute('aria-valuemax', this.maxWidth);
    this.splitter.setAttribute('aria-valuetext', `${this.currentWidth} 像素`);
    this.widthControl.max = this.maxWidth;
    this.widthControl.value = this.currentWidth;
    this.widthControl.setAttribute('aria-valuetext', `${this.currentWidth} 像素`);
  }

  rememberWidth() {
    this.preferredWidth = this.currentWidth;
    try { localStorage.setItem('acwing.sidebar-width', this.currentWidth); } catch { /* Optional preference. */ }
  }

  showDetails(show = true, focus = false) {
    this.details = show;
    this.hasDetails ||= show;
    this.toggle.disabled = !this.hasDetails;
    document.querySelector('#sidebar-list-view').hidden = show;
    document.querySelector('#sidebar-detail-view').hidden = !show;
    document.querySelector('#sidebar-toggle-label').textContent = show ? '返回列表' : '题目详情';
    document.querySelector('#sidebar-toggle-icon').setAttribute('href', show ? '#i-left' : '#i-right');
    if (focus) {
      const target = show ? document.querySelector('[role="tab"][tabindex="0"]') : document.querySelector('.sidebar__item[aria-current="page"]');
      (target || document.querySelector('#search')).focus();
    }
  }

  expandResults(expand = true) {
    this.results.expand(expand);
  }
}
