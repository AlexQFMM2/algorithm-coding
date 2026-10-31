// Owns the native modal and lazy loading; the player never owns the practice editor.
export class Visualization {
  constructor(request) { this.request = request; this.dialog = null; }
  async open(detail, initial, returnFocus = document.activeElement) {
    if (this.dialog?.open) return;
    const previous = returnFocus;
    const dialog = document.createElement('dialog');
    dialog.className = 'viz-dialog'; dialog.setAttribute('aria-labelledby', 'viz-title');
    const host = document.createElement('div'); host.className = 'viz-dialog__mount';
    const title = document.createElement('h2'); title.id = 'viz-title'; title.textContent = '正在打开参考算法演示…';
    host.append(title); dialog.append(host); document.body.append(dialog); this.dialog = dialog;
    dialog.addEventListener('keydown', event => {
      event.stopPropagation();
      if ((event.ctrlKey || event.metaKey) && ['s', 'Enter'].includes(event.key)) event.preventDefault();
    });
    let destroy = null;
    dialog.addEventListener('close', () => {
      destroy?.(); dialog.remove();
      if (this.dialog === dialog) this.dialog = null;
      if (previous?.isConnected) previous.focus({preventScroll:true});
    }, {once:true});
    dialog.showModal();
    try {
      const {mountVisualization} = await import('/vendor/algorithm-visualizer/player.js');
      if (!dialog.open) return;
      host.replaceChildren();
      destroy = mountVisualization(host, {detail, request:this.request, close:()=>dialog.close(), ...initial});
    } catch (error) {
      dialog.close(); throw new Error(`无法加载算法演示：${error.message}。请刷新页面重试。`);
    }
  }
  close() { this.dialog?.close(); }
}
