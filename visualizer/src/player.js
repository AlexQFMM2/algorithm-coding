/* Adapted from Algorithm Visualizer (MIT): Player.reset and
 * VisualizationViewer.reset/update/applyCommand/applyChunk.
 * Original copyright (c) 2019 Jinseo Jason Park. See ../upstream/LICENSE.
 * Redux/networking are replaced by an isolated player; rendering remains upstream.
 */
import * as Tracers from 'core/tracers';
import * as Layouts from 'core/layouts';
const constructors = {Array1DTracer: Tracers.Array1DTracer, Array2DTracer: Tracers.Array2DTracer,
  LogTracer: Tracers.LogTracer, VerticalLayout: Layouts.VerticalLayout, HorizontalLayout: Layouts.HorizontalLayout};
const methods = new Set(['set', 'patch', 'depatch', 'select', 'deselect', 'selectRow', 'deselectRow', 'selectCol', 'deselectCol', 'print', 'println']);
export class TracePlayer {
  constructor(trace) {
    this.chunks = [];
    let commands = [];
    for (const command of trace.commands) {
      if (command.key === null && command.method === 'delay') {
        this.chunks.push({commands, lineNumber: command.args[0], meta: command.args[1] || {}});
        commands = [];
      } else commands.push(command);
    }
    if (commands.length || !this.chunks.length) throw new Error('步骤记录不完整，无法播放。');
    this.cursor = -1; this.reset(); this.seek(0);
  }
  reset() { this.objects = Object.create(null); this.root = null; }
  applyCommand({key, method, args}) {
    if (key === null && method === 'setRoot') {
      this.root = this.objects[args[0]];
    } else if (Object.hasOwn(constructors, method)) {
      const Constructor = constructors[method];
      this.objects[key] = new Constructor(key, id => this.objects[id], args[0]);
    } else {
      if (!methods.has(method) || !this.objects[key] || typeof this.objects[key][method] !== 'function') throw new Error(`无法播放步骤：${method}`);
      this.objects[key][method](...args);
    }
  }
  seek(cursor) {
    if (!Number.isInteger(cursor) || cursor < 0 || cursor >= this.chunks.length) return false;
    let start = this.cursor + 1;
    if (cursor < this.cursor) { this.reset(); start = 0; }
    for (let i = start; i <= cursor; i++) this.chunks[i].commands.forEach(command => this.applyCommand(command));
    this.cursor = cursor;
    return true;
  }
  get current() { return this.chunks[this.cursor]; }
  nextCount() { return this.chunks.findIndex((chunk, index) => index > this.cursor && chunk.meta.kind === 'count'); }
  render() { return this.root?.render(); }
}
