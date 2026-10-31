// Ace owns the edit buffer; clangd only supplies advice about a versioned snapshot.
const Range = window.ace.require('ace/range').Range;
const kinds = { 2: '方法', 3: '函数', 4: '构造函数', 5: '成员', 6: '变量', 7: '类', 9: '模块', 10: '属性', 12: '值', 14: '关键字', 21: '常量', 22: '结构体' };
const rangeOf = range => new Range(range.start.line, range.start.character, range.end.line, range.end.character);
const plainText = content => typeof content === 'string' ? content : Array.isArray(content) ? content.map(plainText).join('\n\n') : content?.value || '';

export class CppIntelligence {
  constructor(editor, request) {
    this.editor = editor;
    this.request = request;
    this.session = crypto.randomUUID();
    this.version = 0;
    this.markers = [];
    this.diagnostics = [];
    this.available = false;
    this.hintGeneration = 0;
    this.hoverGeneration = 0;
    this.status = document.querySelector('#cpp-status');
    this.problems = document.querySelector('#cpp-problems');
    this.tooltip = document.querySelector('#cpp-tooltip');
    this.status.addEventListener('click', () => {
      if (this.failed || !this.available) return this.retry();
      this.problems.hidden = !this.problems.hidden;
      this.status.setAttribute('aria-expanded', String(!this.problems.hidden));
    });
    editor.setOptions({ enableBasicAutocompletion: true, enableLiveAutocompletion: true,
      liveAutocompletionDelay: 220, liveAutocompletionThreshold: 2 });
    // Keep Ace's keyword/text fallback when clangd has not been installed.
    this.fallbackCompleters = [...editor.completers];
    this.completer = {
      id: 'cpp-clangd', triggerCharacters: ['.', '>', ':'],
      getCompletions: (_editor, _session, position, _prefix, callback) => this.complete(position, callback),
    };
    editor.commands.addCommand({ name: 'cppSignature', bindKey: { win: 'Ctrl-Shift-Space', mac: 'Command-Shift-Space' },
      exec: () => this.signature(), readOnly: true });
    editor.commands.addCommand({ name: 'cppNextProblem', bindKey: 'F8', exec: () => this.nextProblem(1), readOnly: true });
    editor.commands.addCommand({ name: 'cppPreviousProblem', bindKey: 'Shift-F8', exec: () => this.nextProblem(-1), readOnly: true });
    editor.selection.on('changeCursor', () => {
      clearTimeout(this.signatureTimer);
      clearTimeout(this.hoverTimer);
      const position = editor.getCursorPosition();
      const before = editor.session.getLine(position.row).slice(0, position.column);
      const active = this.tooltipKind === 'signature' && !this.tooltip.hidden;
      this.hideTooltip();
      if (active || before.includes('(')) this.signatureTimer = setTimeout(() => this.signature(), 350);
    });
    editor.on('mousemove', event => {
      clearTimeout(this.hoverTimer);
      this.hoverGeneration++;
      if (this.tooltipKind === 'signature' && !this.tooltip.hidden) return;
      const position = event.getDocumentPosition();
      this.hoverTimer = setTimeout(() => this.hover(position), 650);
    });
    editor.container.addEventListener('mouseleave', () => { clearTimeout(this.hoverTimer); this.hoverGeneration++; if (this.tooltipKind === 'hover') this.hideTooltip(); });
    editor.on('blur', () => { clearTimeout(this.signatureTimer); this.hideTooltip(); });
    editor.session.on('changeScrollTop', () => this.hideTooltip());
    editor.session.on('changeScrollLeft', () => this.hideTooltip());
    window.addEventListener('resize', () => this.hideTooltip());
  }

  configure(capability) {
    const wasAvailable = this.available;
    this.available = Boolean(capability?.available);
    this.unavailableMessage = capability?.message || '请先保存代码，重启 ./start.sh 并刷新页面，以启用新版 C++ 提示。';
    this.editor.completers = this.available ? [this.completer] : this.fallbackCompleters;
    if (!this.available) this.setStatus('基础补全 · 语义提示未启用', this.unavailableMessage);
    else if (!wasAvailable && this.document) this.schedule();
  }

  open(problem, attempt) {
    this.document = { problem, attempt };
    this.version++;
    this.editor.completer?.detach();
    this.hideTooltip();
    this.clearDiagnostics();
    this.problems.hidden = true;
    this.status.setAttribute('aria-expanded', 'false');
    this.schedule();
  }

  changed() {
    this.version++;
    this.clearDiagnostics();
    this.hideTooltip();
    this.schedule();
  }

  schedule() {
    clearTimeout(this.diagnosticTimer);
    if (!this.available || !this.document) return;
    this.failed = false;
    this.setStatus('C++ 分析中…', '停止输入后自动检查当前草稿');
    this.diagnosticTimer = setTimeout(() => this.check(), 700);
  }

  setStatus(text, title = '', failed = false) {
    this.status.textContent = text;
    this.status.title = title;
    this.status.dataset.state = failed ? 'error' : '';
  }

  async retry() {
    try {
      const state = await this.request('/api/state');
      this.configure(state.language);
      if (this.available) this.schedule();
    } catch (error) { this.fail(error); }
  }

  fail(error) {
    this.failed = true;
    this.setStatus('C++ 提示中断 · 点击重试', error.message, true);
    this.problems.replaceChildren();
    const message = document.createElement('p');
    message.textContent = error.message;
    this.problems.append(message);
    this.problems.hidden = false;
    this.status.setAttribute('aria-expanded', 'true');
  }

  async ask(action, position) {
    if (!this.available || !this.document) return null;
    const version = this.version;
    const response = await this.request('/api/language', {
      ...this.document, session: this.session, version, source: this.editor.getValue(), action,
      ...(position && { position: { line: position.row, character: position.column } }),
    });
    return version === this.version && !response.stale ? response : null;
  }

  async check() {
    if (this.checking) return; // The in-flight request will schedule the newest version.
    this.checking = true;
    const version = this.version;
    try {
      const response = await this.ask('diagnostics');
      if (!response) return;
      this.failed = false;
      this.showDiagnostics(response.result || []);
    } catch (error) { if (version === this.version) this.fail(error); }
    finally {
      this.checking = false;
      if (version !== this.version) this.schedule();
    }
  }

  clearDiagnostics() {
    this.editor.session.clearAnnotations();
    for (const marker of this.markers) this.editor.session.removeMarker(marker);
    this.markers = [];
    this.diagnostics = [];
    this.problems.replaceChildren();
  }

  showDiagnostics(diagnostics) {
    this.clearDiagnostics();
    this.diagnostics = diagnostics.filter(diagnostic => diagnostic.range).sort((a, b) =>
      a.range.start.line - b.range.start.line || a.range.start.character - b.range.start.character);
    this.editor.session.setAnnotations(this.diagnostics.map(diagnostic => ({
      row: diagnostic.range.start.line, column: diagnostic.range.start.character,
      text: diagnostic.message, type: diagnostic.severity === 1 ? 'error' : diagnostic.severity === 2 ? 'warning' : 'info',
    })));
    for (const diagnostic of this.diagnostics) {
      const range = rangeOf(diagnostic.range);
      if (range.isEmpty()) range.end.column++;
      this.markers.push(this.editor.session.addMarker(range,
        diagnostic.severity === 1 ? 'editor-diagnostic--error' : 'editor-diagnostic--warning', 'text', false));
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = `第 ${range.start.row + 1} 行 · ${diagnostic.severity === 1 ? '错误' : diagnostic.severity === 2 ? '警告' : '提示'}：${diagnostic.message}`;
      button.addEventListener('click', () => this.goTo(diagnostic));
      this.problems.append(button);
    }
    const errors = this.diagnostics.filter(diagnostic => diagnostic.severity === 1).length;
    const warnings = this.diagnostics.filter(diagnostic => diagnostic.severity === 2).length;
    this.setStatus(`C++ 提示 · ${errors} 错误 / ${warnings} 警告`, '点击展开问题列表 · F8 定位下一处 · 最终以 g++ 编译和运行结果为准');
    if (!this.diagnostics.length) {
      const empty = document.createElement('p');
      empty.textContent = '当前草稿未发现静态问题，仍需运行用例验证逻辑。';
      this.problems.append(empty);
    }
  }

  goTo(diagnostic) {
    const start = diagnostic.range.start;
    this.editor.gotoLine(start.line + 1, start.character, true);
    this.editor.focus();
  }

  nextProblem(direction) {
    if (!this.diagnostics.length) return;
    const cursor = this.editor.getCursorPosition();
    const ordered = direction > 0 ? this.diagnostics : [...this.diagnostics].reverse();
    const target = ordered.find(({ range: { start } }) => direction * (start.line - cursor.row || start.character - cursor.column) > 0) || ordered[0];
    this.goTo(target);
  }

  async complete(position, callback) {
    const version = this.version;
    try {
      const response = await this.ask('completion', position);
      if (!response || this.editor.getReadOnly()) return callback(null, []);
      const items = Array.isArray(response.result) ? response.result : response.result?.items || [];
      callback(null, items.map((item, index) => {
        const insertion = item.textEdit?.newText ?? item.insertText ?? item.label.trim();
        return { caption: item.label.trim(), value: insertion,
          ...(item.insertTextFormat === 2 && { snippet: insertion }),
          ...(item.textEdit?.range && { range: rangeOf(item.textEdit.range) }),
          meta: item.detail || kinds[item.kind] || 'C++', score: items.length - index,
          docText: [item.detail, plainText(item.documentation)].filter(Boolean).join('\n'),
        };
      }));
    } catch (error) {
      callback(null, []);
      if (version === this.version) this.fail(error);
    }
  }

  sameCursor(position) {
    const current = this.editor.getCursorPosition();
    return current.row === position.row && current.column === position.column;
  }

  async signature() {
    if (!this.editor.isFocused()) return;
    const position = this.editor.getCursorPosition();
    const generation = this.hintGeneration;
    try {
      const response = await this.ask('signature', position);
      if (!response || generation !== this.hintGeneration || !this.sameCursor(position) || !this.editor.isFocused()) return;
      const help = response.result;
      const signature = help?.signatures?.[help.activeSignature || 0];
      if (!signature) return this.hideTooltip();
      const parameter = signature.parameters?.[signature.activeParameter ?? help.activeParameter ?? 0];
      this.tooltip.replaceChildren();
      const code = document.createElement('code');
      const label = signature.label;
      const bounds = Array.isArray(parameter?.label) ? parameter.label : null;
      if (bounds) {
        const active = document.createElement('strong');
        active.textContent = label.slice(...bounds);
        code.append(label.slice(0, bounds[0]), active, label.slice(bounds[1]));
      } else code.textContent = label;
      this.tooltip.append(code);
      const hint = document.createElement('small');
      hint.textContent = signature.parameters?.length
        ? `参数 ${(signature.activeParameter ?? help.activeParameter ?? 0) + 1} / ${signature.parameters.length} · Esc 关闭`
        : '无参数 · Esc 关闭';
      this.tooltip.append(hint);
      this.showTooltip('signature', position);
    } catch { /* Diagnostics owns service-error feedback; hints must not interrupt typing. */ }
  }

  async hover(position) {
    const generation = this.hoverGeneration;
    const hintGeneration = this.hintGeneration;
    try {
      const response = await this.ask('hover', position);
      if (!response || generation !== this.hoverGeneration || hintGeneration !== this.hintGeneration) return;
      const text = plainText(response.result?.contents);
      if (!text) { if (this.tooltipKind === 'hover') this.hideTooltip(); return; }
      this.tooltip.textContent = text;
      this.showTooltip('hover', position);
    } catch { /* Hover is optional; the status remains the recovery entry point. */ }
  }

  showTooltip(kind, position) {
    this.tooltipKind = kind;
    this.tooltip.hidden = false;
    const point = this.editor.renderer.textToScreenCoordinates(position.row, position.column);
    const box = this.tooltip.getBoundingClientRect();
    const x = point.pageX - scrollX;
    const y = point.pageY - scrollY;
    this.tooltip.style.left = `${Math.max(8, Math.min(x, innerWidth - box.width - 8))}px`;
    this.tooltip.style.top = `${Math.max(8, y - box.height - 8)}px`;
  }

  hideTooltip() {
    this.hintGeneration++;
    const visible = !this.tooltip.hidden;
    this.tooltip.hidden = true;
    return visible;
  }
}
