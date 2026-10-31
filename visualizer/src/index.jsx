import React from 'react';
import {createRoot} from 'react-dom/client';
import {TracePlayer} from './player.js';
export {TracePlayer};
export function mountPlayback(container, trace) {
  const root = createRoot(container);
  const player = new TracePlayer(trace);
  const render = () => root.render(<div className="av-stage">{player.render()}</div>);
  render();
  return {player, seek(cursor) { player.seek(cursor); render(); }, destroy() { root.unmount(); }};
}

import {VisualizationDialog} from './dialog.jsx';
export function mountVisualization(container, options) {
  const root = createRoot(container);
  root.render(<VisualizationDialog {...options}/>);
  return () => root.unmount();
}
