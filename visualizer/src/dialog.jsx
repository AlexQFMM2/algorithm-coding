import React, {useEffect, useRef, useState} from 'react';
import {TracePlayer} from './player.js';
import './dialog.css';

const STATUSES = {READY:'已生成', RUNNING:'未完成', INPUT_ERROR:'输入错误', CE:'编译失败', RE:'运行错误', TLE:'运行超时', OLE:'输出超限', ERROR:'生成失败'};
const KINDS = {start:'开始', split:'拆分区间', single:'递归返回', merge:'开始合并', compare:'比较', count:'发现逆序对', equal:'相等不计数', take_left:'取左侧', tail:'复制剩余', write_back:'写回数组', complete:'完成'};
const display = value => typeof value === 'object' ? JSON.stringify(value) : String(value ?? '—');

function SourceView({source, line}) {
  const scroller = useRef(null);
  useEffect(() => {
    const host = scroller.current;
    const active = host?.querySelector('[data-active="true"]');
    if (!active) return;
    function reveal() {
      const top = active.offsetTop;
      if (top < host.scrollTop || top + active.offsetHeight > host.scrollTop + host.clientHeight) {
        host.scrollTop = Math.max(0, top - host.clientHeight / 3);
      }
    }
    reveal();
    const observer = new ResizeObserver(reveal);
    observer.observe(host);
    return () => observer.disconnect();
  }, [line, source]);
  return <section className="viz-source" aria-label="只读演示源码">
    <h3>演示源码 <span>只读 · 当前第 {line || '—'} 行</span></h3>
    <div className="viz-source__scroll" ref={scroller} tabIndex={0}>
      <ol>{source.split('\n').map((text, index) => <li key={index} data-active={index + 1 === line} aria-current={index + 1 === line ? 'step' : undefined}><code>{text || ' '}</code></li>)}</ol>
    </div>
  </section>;
}

export function VisualizationDialog({detail, request, close, initialInput = '', initialMode = 'sample', initialSample = 0}) {
  const [mode, setMode] = useState(detail.samples.length ? initialMode : 'manual');
  const [sample, setSample] = useState(initialSample < detail.samples.length ? initialSample : 0);
  const [manual, setManual] = useState(initialMode === 'manual' ? initialInput : detail.samples[0]?.input || '');
  const [record, setRecord] = useState(null);
  const [player, setPlayer] = useState(null);
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [history, setHistory] = useState([]);
  const alive = useRef(true);
  const historyRequest = useRef(0);
  const input = mode === 'sample' ? detail.samples[sample]?.input || '' : manual;
  const prefix = `problem=${encodeURIComponent(detail.id)}`;
  const total = player?.chunks.length || 0;
  const frame = player?.current;
  const meta = frame?.meta || {};

  async function refreshHistory() {
    const serial = ++historyRequest.current;
    const result = await request(`/api/visualizations?${prefix}`);
    if (alive.current && serial === historyRequest.current) setHistory(result.runs);
  }
  useEffect(() => {
    alive.current = true;
    refreshHistory().catch(e => { if (alive.current) setError(`历史演示读取失败：${e.message}`); });
    return () => { alive.current = false; };
  }, []);
  useEffect(() => {
    const hide = () => { if (document.hidden) setPlaying(false); };
    document.addEventListener('visibilitychange', hide);
    return () => document.removeEventListener('visibilitychange', hide);
  }, []);
  function seek(next) {
    if (!player || next < 0 || next >= total) return;
    try { player.seek(next); setCursor(next); }
    catch (e) { setPlaying(false); setPlayer(null); setError(`回放失败：${e.message}`); }
  }
  useEffect(() => {
    if (!playing || busy || !player) return;
    if (cursor >= total - 1) { setPlaying(false); return; }
    const timer = setTimeout(() => seek(cursor + 1), 1400 / speed);
    return () => clearTimeout(timer);
  }, [playing, cursor, speed, player, busy]);
  function move(next) { setPlaying(false); seek(next); }
  function togglePlay() {
    if (!player) return;
    if (!playing && cursor === total - 1) seek(0);
    setPlaying(!playing);
  }
  function loadRecord(value) {
    setRecord(value); setCursor(0); setPlaying(false);
    setPlayer(value.status === 'READY' ? new TracePlayer(value.trace) : null);
    if (value.status !== 'READY') setError(value.error || (value.status === 'RUNNING' ? '这次演示尚未完成，可能被服务关闭中断。' : '无法生成完整演示。'));
  }
  async function generate(event) {
    event.preventDefault();
    if (busy) return;
    setBusy(true); setError(''); setPlaying(false); setPlayer(null); setRecord(null);
    try {
      const result = await request('/api/visualizations', {problem: detail.id, input_mode: mode, input, sample});
      if (!alive.current) return;
      loadRecord(result);
      await refreshHistory();
    } catch (e) { if (alive.current) {setPlayer(null); setError(e.message);} }
    finally { if (alive.current) setBusy(false); }
  }
  async function selectHistory(id) {
    if (!id || busy) return;
    setBusy(true); setError(''); setPlaying(false); setPlayer(null); setRecord(null);
    try {
      const result = await request(`/api/visualization?${prefix}&run=${encodeURIComponent(id)}`);
      if (!alive.current) return;
      setMode('manual'); setManual(result.input); loadRecord(result);
    } catch (e) { if (alive.current) setError(e.message); }
    finally { if (alive.current) setBusy(false); }
  }
  function keyboard(event) {
    if (!player || busy) return;
    if (event.key === 'ArrowLeft') {event.preventDefault();move(cursor - 1);}
    if (event.key === 'ArrowRight') {event.preventDefault();move(cursor + 1);}
    if (event.key === 'Home') {event.preventDefault();move(0);}
    if (event.key === 'End') {event.preventDefault();move(total - 1);}
    if (event.key === ' ') {event.preventDefault();togglePlay();}
  }
  const countStep = player?.nextCount() ?? -1;
  return <div className="viz-dialog__shell">
    <header className="viz-dialog__header">
      <div><span className="viz-dialog__eyebrow">参考算法演示</span><h2 id="viz-title">{detail.visualization.title}</h2></div>
      <button type="button" className="button button--secondary" onClick={close} aria-label="关闭算法演示">关闭 <span aria-hidden="true">×</span></button>
    </header>
    <form className="viz-input" onSubmit={generate}>
      <div className="viz-input__selectors">
        <label>输入来源<select id="viz-mode" value={mode} onChange={e=>setMode(e.target.value)} disabled={busy}>
          {!!detail.samples.length && <option value="sample">题目样例</option>}<option value="manual">手动输入</option>
        </select></label>
        {mode === 'sample' && <label>样例<select id="viz-sample" value={sample} onChange={e=>setSample(Number(e.target.value))} disabled={busy}>
          {detail.samples.map((_,i)=><option key={i} value={i}>样例 {i+1}</option>)}
        </select></label>}
        <button id="viz-generate" className="button button--primary" disabled={busy}>{busy ? '正在生成…' : '生成演示'}</button>
      </div>
      <label className="viz-input__text">标准输入<textarea id="viz-input" value={input} onChange={e=>setManual(e.target.value)} readOnly={mode==='sample' || busy} rows={3} aria-describedby="viz-input-hint" /></label>
      <div className="viz-input__help"><p id="viz-input-hint">{detail.visualization.input_hint}</p>
        <label>历史演示<select id="viz-history" value={record?.id || ''} onChange={e=>selectHistory(e.target.value)} disabled={busy}>
          <option value="">选择一次记录</option>{history.map(run=><option value={run.id} key={run.id}>{new Date(run.created_at).toLocaleString('zh-CN',{hour12:false})} · {STATUSES[run.status] || run.status}{run.steps ? ` · ${run.steps} 步` : ''}</option>)}
        </select></label>
      </div>
    </form>
    {error && <div className="viz-error" role="alert">{error}</div>}
    {record && input !== record.input && <div className="viz-dialog__hint" role="status">输入已修改。当前仍是上次生成的回放，点击“生成演示”后更新。</div>}
    <div className="viz-dialog__body" aria-busy={busy}>
      {player && !busy ? <>
        <div className="viz-reading">
          <section className="viz-lesson" aria-live={playing ? 'off' : 'polite'}>
            <div className="viz-lesson__heading"><span className="tag">{KINDS[meta.kind] || '执行一步'}</span><span className="viz-lesson__count">cnt <strong>{meta.after ?? '—'}</strong>{meta.kind === 'count' && <b>+{meta.after-meta.before}</b>}</span></div>
            <p id="viz-explanation">{meta.message || '观察本步数组与状态的变化。'}</p>
            {!!meta.pairs?.length && <div className="viz-pairs"><span>本步新增：</span>{meta.pairs.map((pair,i)=><span className="viz-pairs__item" key={i}>({display(pair[0])}, {display(pair[1])})</span>)}<strong>{meta.before} → {meta.after}</strong></div>}
          </section>
          <dl className="viz-state">{Object.entries(meta.state || {}).map(([key,value])=><div key={key}><dt>{key}</dt><dd>{display(value)}</dd></div>)}</dl>
          <div className="viz-legend"><span>下划线：左侧待处理区域 / tmp 已写区域</span><span>黄色边框：当前右侧元素</span></div>
          <div id="viz-stage" className="av-stage" tabIndex={0} aria-label="演示画布，方向键逐步查看，空格播放或暂停" onKeyDown={keyboard}>{player.render()}</div>
        </div>
        <SourceView source={record.source} line={frame.lineNumber} />
      </> : <div className="viz-empty" role="status"><strong>{busy ? '正在准备参考算法的执行过程…' : record ? STATUSES[record.status] || '没有可播放的步骤' : '让每一次比较和计数，都看得见。'}</strong>
        <p>{busy ? '编译并运行参考演示代码，随后停在第一步。' : record ? '查看下方错误信息，修改输入或演示资料后重新生成。' : '选择样例或输入一组小数组，点击“生成演示”。逐步观察左边剩余元素为什么能一次计数。'}</p>
        {record?.stderr && <pre>{record.stderr}</pre>}{record?.compiler && <details open={record.status==='CE'}><summary>编译信息</summary><pre>{record.compiler}</pre></details>}
      </div>}
    </div>
    <footer className="viz-controls">
      <div className="viz-controls__buttons">
        <button id="viz-restart" className="button button--secondary" disabled={!player || busy} onClick={()=>move(0)}>重新开始</button>
        <button id="viz-prev" className="button button--secondary" disabled={!player || busy || cursor===0} onClick={()=>move(cursor-1)}>上一步</button>
        <button id="viz-play" className="button button--primary" disabled={!player || busy} onClick={togglePlay}>{playing ? '暂停' : '播放'}</button>
        <button id="viz-next" className="button button--secondary" disabled={!player || busy || cursor===total-1} onClick={()=>move(cursor+1)}>下一步</button>
        <button id="viz-next-count" className="button button--secondary" disabled={!player || busy || countStep<0} onClick={()=>move(countStep)}>下一次计数</button>
      </div>
      <div className="viz-controls__progress"><label htmlFor="viz-progress">步骤 <span id="viz-step">{player ? cursor+1 : 0} / {total}</span></label>
        <input id="viz-progress" aria-label="演示进度" type="range" min="0" max={Math.max(total-1,0)} value={cursor} disabled={!player || busy} onChange={e=>move(Number(e.target.value))}/>
        <label>速度<select id="viz-speed" value={speed} onChange={e=>setSpeed(Number(e.target.value))}>{[.5,1,2,4].map(x=><option key={x} value={x}>{x}×</option>)}</select></label>
      </div>
      <div className="viz-controls__footnote"><span>{record ? `记录：${record.log_path}/` : '参考演示不计入练习、通过或失败次数。'}</span><a href="https://github.com/algorithm-visualizer/algorithm-visualizer" target="_blank" rel="noreferrer">Algorithm Visualizer · MIT</a></div>
    </footer>
  </div>;
}
