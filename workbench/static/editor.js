// Ace owns editing, selection, undo, indentation and C++ highlighting.
import { CppIntelligence } from './intelligence.js';

// Language assistance observes the buffer without owning saves or execution.
export class Editor {
  constructor(onChange, { onSave, onRun, request }) {
    this.host = document.querySelector('#code');
    this.position = document.querySelector('#cursor-position');
    this.settingSource = false;
    this.unavailable = true;
    this.locked = false;
    window.ace.config.set('basePath', '/vendor/ace');
    window.ace.config.set('useStrictCSP', true);
    this.ace = window.ace.edit(this.host, {
      mode: 'ace/mode/c_cpp',
      theme: this.themeName,
      fontFamily: getComputedStyle(document.documentElement).getPropertyValue('--font-mono').trim(),
      fontSize: 14,
      tabSize: 4,
      useSoftTabs: true,
      useWorker: false,
      showPrintMargin: false,
      highlightActiveLine: true,
      highlightSelectedWord: false,
      displayIndentGuides: true,
      animatedScroll: false,
      scrollPastEnd: .2,
      enableKeyboardAccessibility: true,
      readOnly: true,
    });
    this.ace.renderer.setPadding(12);
    this.ace.renderer.setScrollMargin(10, 10, 0, 0);
    this.input = this.ace.textInput.getElement();
    this.input.setAttribute('aria-label', 'C++ 练习代码');
    this.input.setAttribute('aria-describedby', 'editor-help');
    this.ace.session.on('change', () => {
      if (!this.settingSource) { onChange(); this.intelligence?.changed(); }
    });
    this.ace.selection.on('changeCursor', () => this.updatePosition());
    this.ace.on('focus', () => this.host.closest('.editor-panel').classList.add('editor-panel--focused'));
    this.ace.on('blur', () => this.host.closest('.editor-panel').classList.remove('editor-panel--focused'));
    this.ace.commands.addCommand({ name: 'savePractice', bindKey: { win: 'Ctrl-S', mac: 'Command-S' }, exec: onSave, readOnly: true });
    this.ace.commands.addCommand({ name: 'runPractice', bindKey: { win: 'Ctrl-Enter', mac: 'Command-Enter' }, exec: onRun, readOnly: true });
    this.ace.commands.addCommand({
      name: 'leavePracticeEditor', bindKey: { win: 'Esc', mac: 'Esc' }, readOnly: true,
      exec: () => {
        if (this.intelligence.hideTooltip()) return;
        const save = document.querySelector('#save');
        (save.disabled ? document.querySelector('#download') : save).focus();
      },
    });
    document.querySelector('.skip-link').addEventListener('click', event => { event.preventDefault(); this.focus(); });
    this.themeObserver = new MutationObserver(() => this.ace.setTheme(this.themeName));
    this.themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    this.resizeObserver = new ResizeObserver(() => this.ace.resize());
    this.resizeObserver.observe(this.host);
    this.intelligence = new CppIntelligence(this.ace, request);
    this.updateAvailability();
    this.updatePosition();
  }

  get themeName() { return document.documentElement.dataset.theme === 'dark' ? 'ace/theme/one_dark' : 'ace/theme/github_light_default'; }
  get value() { return this.ace.getValue(); }
  set value(value) {
    this.settingSource = true;
    try {
      this.ace.setValue(value, -1);
      this.ace.session.getUndoManager().reset();
      this.ace.session.setScrollTop(0);
      this.ace.session.setScrollLeft(0);
    } finally { this.settingSource = false; }
    this.updatePosition();
  }
  set disabled(value) { this.unavailable = value; this.updateAvailability(); }
  set readOnly(value) { this.locked = value; this.updateAvailability(); }
  focus() { if (!this.unavailable) this.ace.focus(); }
  setDocument(problem, attempt) { this.intelligence.open(problem, attempt); }
  configureIntelligence(capability) { this.intelligence.configure(capability); }

  updateAvailability() {
    this.ace.setReadOnly(this.unavailable || this.locked);
    this.host.setAttribute('aria-disabled', String(this.unavailable));
    this.input.setAttribute('aria-readonly', String(this.unavailable || this.locked));
    this.input.tabIndex = this.unavailable ? -1 : 0;
  }

  updatePosition() {
    const cursor = this.ace.getCursorPosition();
    this.position.textContent = `行 ${cursor.row + 1}，列 ${cursor.column + 1}`;
  }
}
