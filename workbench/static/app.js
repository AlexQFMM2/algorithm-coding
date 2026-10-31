import { Editor } from './editor.js';
import { renderMarkdown } from './documents.js';
import { renderResult, resetResult, historyOptions } from './results.js';
import { WorkspaceLayout } from './layout.js';
import { Visualization } from './visualization.js';

const $ = selector => document.querySelector(selector);
const layout = new WorkspaceLayout();
const visualization = new Visualization(api);
const state = { problems: [], selected: null, detail: null, attempt: null, saved: '', token: '', busy: false, saveTask: null, timer: null, documentPath: '', documentRequest: 0, manualInput: new Map() };
const editor = new Editor(() => {
  saveState('尚未保存');
  clearTimeout(state.timer);
  state.timer = setTimeout(() => save().catch(showError), 600);
}, {
  onSave: () => action(save),
  onRun: () => { if (!$('#run').disabled) $('#run').click(); },
  request: api,
});

async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Workbench-Token': state.token }, body: JSON.stringify(data) });
  let body;
  try { body = await response.json(); } catch { throw new Error('应用连接中断，请确认启动终端仍在运行。'); }
  if (!response.ok) throw new Error(body.error || '请求失败，请重试。');
  return body;
}

function showError(error) {
  $('#notice').textContent = error.message || String(error); $('#notice').hidden = false;
  if (state.attempt && editor.value !== state.saved) saveState('保存失败', true);
}
function clearError() { $('#notice').hidden = true; }
function saveState(message, failed = false) { $('#save-state').textContent = message; $('#save-state').dataset.state = failed ? 'error' : ''; }
function problemDocument(name) { return `${state.detail?.path || state.selected}/${name}`; }

function updateTestSuite() {
  const suite = state.detail?.test_suite;
  const hint = $('#test-suite-state');
  let message = '选择题目后读取测试数据';
  if (state.detail && !suite) message = '服务版本较旧，请保存后重启 ./start.sh 并刷新页面。';
  else if (suite?.ready) message = `${suite.sample_count} 个样例 + ${suite.file_count} 个测试`;
  else if (suite) message = suite.error || '完整测试尚未就绪，请先运行样例。';
  hint.textContent = message;
  hint.dataset.state = state.detail && !suite?.ready ? 'error' : '';
  $('#check').title = message;
  if ($('#check-label').textContent !== '检查中…') {
    $('#check-label').textContent = suite?.ready ? `检查全部（${suite.total_count}）` : '检查全部';
  }
  if (!suite?.ready) $('#check').disabled = true;
}

function updateControls() {
  const unavailable = state.busy || !state.attempt;
  for (const id of ['new-attempt', 'attempt-select', 'run', 'check', 'save']) $(`#${id}`).disabled = unavailable;
  $('#download').disabled = !state.attempt;
  $('#sidebar-toggle').disabled = !state.selected && !layout.hasDetails;
  $('#refresh').disabled = state.busy;
  $('#run-history').disabled = state.busy;
  $('#input-mode').disabled = state.busy || !state.detail;
  $('#sample-select').disabled = state.busy;
  $('#stdin').readOnly = state.busy || $('#input-mode').value === 'sample';
  editor.disabled = !state.attempt;
  editor.readOnly = state.busy;
  if ($('#input-mode').value === 'sample' && !state.detail?.samples.length) $('#run').disabled = true;
  updateTestSuite();
  const visual = state.detail?.visualization;
  const legacyVisual = state.detail && !visual && state.detail.documents.some(doc => doc.name === "visualize.cpp");
  $("#visualize").hidden = !visual?.configured && !legacyVisual;
  $("#visualize").disabled = state.busy || !visual?.available;
  $("#visualize").title = legacyVisual ? "请保存后重启服务并刷新，以启用算法演示。" : visual?.error || "逐步观察参考算法的执行过程";
  for (const button of document.querySelectorAll('.sidebar__item')) button.disabled = state.busy;
  const index = state.problems.findIndex(problem => problem.id === state.selected);
  for (const [id, offset, label] of [['previous-problem', -1, '上一题'], ['next-problem', 1, '下一题']]) {
    const target = index >= 0 ? state.problems[index + offset] : null;
    const button = $(`#${id}`);
    button.disabled = state.busy || !target;
    button.title = target ? `${label}：${target.title}` : `${label}：${index < 0 ? '暂无题目' : offset < 0 ? '已是第一题' : '已是最后一题'}`;
    button.setAttribute('aria-label', target ? `${label}：${target.title}` : label);
  }
}

async function action(work) {
  if (state.busy) return;
  state.busy = true; clearError(); updateControls();
  try { await work(); } catch (error) { showError(error); }
  finally { state.busy = false; updateControls(); }
}

async function save() {
  clearTimeout(state.timer);
  if (state.saveTask) return state.saveTask;
  if (!state.attempt || state.saved === editor.value) return;
  state.saveTask = (async () => {
    while (state.saved !== editor.value) {
      const source = editor.value;
      saveState('保存中…');
      const saved = await api('/api/attempt/save', { problem: state.selected, attempt: state.attempt.id, source, revision: state.attempt.revision });
      state.attempt.revision = saved.revision;
      state.saved = source;
    }
    saveState('已保存');
  })();
  try { await state.saveTask; } finally { state.saveTask = null; }
}

async function refreshProblems() {
  const data = await api('/api/state');
  state.token = data.token; state.problems = data.problems;
  editor.configureIntelligence(data.language);
  $('#connection-state').textContent = '本地文件已连接';
  $('#connection-state').title = data.root;
  renderProblems();
}

function renderProblems() {
  const list = $('#problem-list'); list.replaceChildren();
  $('#problem-count').textContent = state.problems.length;
  const query = $('#search').value.trim().toLowerCase();
  state.problems.forEach((problem, index) => {
    if (![problem.title, problem.topic].some(value => value.toLowerCase().includes(query))) return;
    const button = document.createElement('button'); button.className = 'sidebar__item';
    if (problem.id === state.selected) button.setAttribute('aria-current', 'page');
    button.disabled = state.busy;
    const number = document.createElement('span'); number.className = 'sidebar__number'; number.textContent = String(index + 1).padStart(2, '0');
    const text = document.createElement('span'); const title = document.createElement('strong'); title.textContent = problem.title;
    const detail = document.createElement('small');
    detail.textContent = problem.stats
      ? `练习 ${problem.stats.practice_count} 轮 · 通过 ${problem.stats.passed_count} 次 · 失败 ${problem.stats.failed_count} 次`
      : `${problem.attempt_count} 轮练习`;
    detail.title = '通过和失败按“检查全部”的次数计算，样例和手动运行不计入。';
    text.append(title, detail); button.append(number, text);
    button.addEventListener('click', () => action(() => navigateToProblem(problem.id)));
    list.append(button);
  });
  if (!list.children.length) { const empty = document.createElement('p'); empty.className = 'muted'; empty.textContent = state.problems.length ? '没有匹配的题目。' : '在「题库/」中新建含「题目.md」的目录即可添加题目。'; list.append(empty); }
  renderStatistics(state.problems.find(problem => problem.id === state.selected));
}

function renderStatistics(problem) {
  $('#problem-stats').hidden = !problem;
  if (!problem) return;
  const values = { practices: problem.stats?.practice_count ?? problem.attempt_count,
    passed: problem.stats?.passed_count ?? '—', failed: problem.stats?.failed_count ?? '—' };
  for (const [key, value] of Object.entries(values)) {
    const counter = $(`#stat-${key}`);
    if (counter.textContent !== String(value)) counter.textContent = value;
  }
  $('#problem-stats').title = problem.stats
    ? '练习按保存的轮次计算；通过和失败按检查全部的次数计算，样例和手动运行不计入。'
    : '统计需要新版服务：请先保存代码，在启动终端 Ctrl+C 停止后重新运行 ./start.sh，再刷新页面。';
}

async function navigateToProblem(id) {
  if (id !== state.selected) {
    await save();
    await selectProblem(id);
    history.pushState(null, '', '#' + encodeURIComponent(id));
  }
  layout.showDetails(true, true);
}

function loadAttempt(attempt) {
  state.attempt = attempt; state.saved = attempt.source; editor.value = attempt.source;
  editor.setDocument(state.selected, attempt.id);
  $('#code-path').textContent = attempt.path; $('#attempt-select').value = attempt.id;
  saveState('已保存'); updateControls();
}

function attemptOptions(attempts) {
  $('#attempt-select').replaceChildren();
  for (const attempt of attempts) $('#attempt-select').add(new Option(`第 ${Number.parseInt(attempt.id, 10)} 轮 · ${attempt.id}`, attempt.id));
}

async function selectProblem(id, attemptId = null) {
  visualization.close();
  const detail = await api('/api/problem?id=' + encodeURIComponent(id));
  if (!detail.attempt) {
    detail.attempt = await api('/api/attempt/new', { problem: id, from_reference: true });
    detail.attempts = [{ id: detail.attempt.id }];
  }
  const attempt = attemptId ? await api(`/api/attempt?problem=${encodeURIComponent(id)}&attempt=${encodeURIComponent(attemptId)}`) : detail.attempt;
  state.selected = id; state.detail = detail;
  $('#problem-title').textContent = detail.title; $('#problem-topic').textContent = detail.topic;
  document.title = `${detail.title} · 算法练习室`;
  attemptOptions(detail.attempts); loadAttempt(attempt);
  const extra = $('#extra-document'); extra.replaceChildren(new Option('更多资料', ''));
  for (const doc of detail.documents.filter(doc => !['题目.md', '解析.md', 'main.cpp'].includes(doc.name))) extra.add(new Option(doc.name, doc.path));
  extra.hidden = extra.options.length < 2;
  $('#sample-select').replaceChildren();
  detail.samples.forEach((_, index) => $('#sample-select').add(new Option(`样例 ${index + 1}`, index)));
  $('#input-mode').value = detail.samples.length ? 'sample' : 'manual'; updateInput();
  historyOptions($('#run-history'), detail.runs); resetResult($('#result-content'));
  await openDocument(problemDocument('题目.md'));
  await refreshProblems();
}

async function openDocument(path) {
  layout.showDetails();
  const request = ++state.documentRequest;
  $('#document-content').setAttribute('aria-busy', 'true');
  try {
    const optionalDocuments = {
      '解析.md': '这道题还没有解析。\n\n做完后，可以在题目目录下添加「解析.md」，记录你的思路和容易写错的地方。',
      'main.cpp': '这道题还没有参考代码。\n\n可以在题目目录下添加「main.cpp」。你的练习代码会继续单独保存。',
    };
    const missing = Object.keys(optionalDocuments).find(name => path === problemDocument(name) && !state.detail.documents.some(doc => doc.name === name));
    const document = missing ? { path, content: optionalDocuments[missing], code: false } : await api('/api/document?path=' + encodeURIComponent(path));
    if (request !== state.documentRequest) return;
    state.documentPath = document.path;
    renderMarkdown($('#document-content'), document.content, document.code);
    $('#document-content').scrollTop = 0;
    $('#document-path').textContent = document.path;
    let selectedTab = false;
    for (const tab of documentTabs) {
      const selected = document.path === problemDocument(tab.dataset.document);
      tab.setAttribute('aria-selected', String(selected)); tab.tabIndex = selected ? 0 : -1;
      if (selected) { $('#document-content').setAttribute('aria-labelledby', tab.id); selectedTab = true; }
    }
    if (!selectedTab) { documentTabs[0].tabIndex = 0; $('#document-content').removeAttribute('aria-labelledby'); $('#document-content').setAttribute('aria-label', document.path); }
    else $('#document-content').removeAttribute('aria-label');
  } finally { if (request === state.documentRequest) $('#document-content').setAttribute('aria-busy', 'false'); }
}

function updateInput() {
  const manual = $('#input-mode').value === 'manual';
  $('#stdin').readOnly = !manual;
  $('#sample-select').hidden = manual || state.detail.samples.length < 2;
  $('#stdin').value = manual ? state.manualInput.get(state.selected) ?? state.detail.samples[0]?.input ?? '' : state.detail.samples[Number($('#sample-select').value)]?.input ?? '';
  $('#input-hint').textContent = manual ? '按输入格式填写数据；手动运行不判断答案。' : '运行样例会同时比较预期输出。';
  $('#run-label').textContent = manual ? '运行代码' : '运行样例';
  updateControls();
}

async function run(mode) {
  await save();
  layout.expandResults();
  resetResult($('#result-content'), true);
  $('#run-history').value = '';
  const previousLabel = mode === 'check' ? $('#check-label').textContent : $('#run-label').textContent;
  const label = mode === 'check' ? $('#check-label') : $('#run-label'); label.textContent = mode === 'check' ? '检查中…' : '运行中…';
  try {
    const result = await api('/api/run', { problem: state.selected, attempt: state.attempt.id, revision: state.attempt.revision, mode, input: $('#stdin').value, sample: Number($('#sample-select').value || 0) });
    renderResult($('#result-content'), result);
    state.detail = await api('/api/problem?id=' + encodeURIComponent(state.selected));
    historyOptions($('#run-history'), state.detail.runs, result.id);
    await refreshProblems();
  } catch (error) {
    $('#result-content').setAttribute('aria-busy', 'false');
    $('#result-content').textContent = error.message;
    throw error;
  } finally { label.textContent = previousLabel; }
}

const documentTabs = [...document.querySelectorAll('[data-document]')];
documentTabs.forEach((tab, index) => {
  tab.addEventListener('click', () => { if (state.selected) openDocument(problemDocument(tab.dataset.document)).catch(showError); });
  tab.addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? documentTabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + documentTabs.length) % documentTabs.length;
    documentTabs[next].focus(); documentTabs[next].click();
  });
});
$('#extra-document').addEventListener('change', event => { if (event.target.value) openDocument(event.target.value).catch(showError); });
$('#document-content').addEventListener('click', event => {
  const link = event.target.closest('[data-document-link]'); if (!link) return;
  event.preventDefault();
  const base = new URL(state.documentPath.split('/').map(encodeURIComponent).join('/'), location.origin + '/');
  const target = new URL(link.dataset.documentLink, base);
  if (target.origin === location.origin) openDocument(decodeURIComponent(target.pathname.slice(1))).catch(showError);
});
$('#search').addEventListener('input', renderProblems);
for (const [id, offset] of [['previous-problem', -1], ['next-problem', 1]]) {
  $(`#${id}`).addEventListener('click', () => action(async () => {
    const index = state.problems.findIndex(problem => problem.id === state.selected);
    const target = index >= 0 ? state.problems[index + offset] : null;
    if (target) await navigateToProblem(target.id);
  }));
}
$('#input-mode').addEventListener('change', updateInput);
$('#sample-select').addEventListener('change', updateInput);
$('#stdin').addEventListener('input', () => state.manualInput.set(state.selected, $('#stdin').value));
$('#save').addEventListener('click', () => action(save));
$('#run').addEventListener('click', () => action(() => run($('#input-mode').value)));
$('#check').addEventListener('click', () => action(() => run('check')));
$('#visualize').addEventListener('click', () => action(async () => {
  await save();
  await visualization.open(state.detail, {initialInput: $('#stdin').value, initialMode: $('#input-mode').value, initialSample: Number($('#sample-select').value || 0)});
}));
$('#new-attempt').addEventListener('click', () => action(async () => {
  await save(); const attempt = await api('/api/attempt/new', { problem: state.selected });
  await selectProblem(state.selected, attempt.id); editor.focus();
}));
$('#attempt-select').addEventListener('change', event => {
  const next = event.target.value;
  action(async () => { try { await save(); const attempt = await api(`/api/attempt?problem=${encodeURIComponent(state.selected)}&attempt=${encodeURIComponent(next)}`); loadAttempt(attempt); resetResult($('#result-content')); $('#run-history').value = ''; } finally { $('#attempt-select').value = state.attempt.id; } });
});
$('#refresh').addEventListener('click', () => action(async () => {
  // On a conflict the user explicitly reloads, after downloading their draft.
  if (state.attempt && editor.value !== state.saved) {
    if (!window.confirm('当前有未保存的代码。建议先「下载草稿」。现在从磁盘重新载入并放弃窗口中的修改吗？')) return;
  }
  clearTimeout(state.timer);
  if (state.saveTask) { try { await state.saveTask; } catch { /* Explicit reload resolves stale revisions. */ } }
  await refreshProblems();
  const id = state.problems.find(problem => problem.id === state.selected)?.id || state.problems[0]?.id;
  if (id) await selectProblem(id, id === state.selected ? state.attempt?.id : null);
}));
$('#download').addEventListener('click', () => {
  const url = URL.createObjectURL(new Blob([editor.value], { type: 'text/plain;charset=utf-8' }));
  const link = document.createElement('a'); link.href = url; link.download = `${state.selected}-${state.attempt.id}`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});
$('#run-history').addEventListener('change', event => action(async () => {
  layout.expandResults();
  if (!event.target.value) return resetResult($('#result-content'));
  const result = await api(`/api/run?problem=${encodeURIComponent(state.selected)}&run=${encodeURIComponent(event.target.value)}`);
  renderResult($('#result-content'), result);
}));
$('#help').addEventListener('click', () => openDocument('readme.md').catch(showError));
window.addEventListener('keydown', event => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); action(save); }
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') { event.preventDefault(); if (!$('#run').disabled) $('#run').click(); }
});
window.addEventListener('beforeunload', event => {
  if (state.attempt && editor.value !== state.saved) { event.preventDefault(); event.returnValue = ''; }
});
window.addEventListener('popstate', () => action(async () => {
  await save(); const id = decodeURIComponent(location.hash.slice(1));
  if (state.problems.some(problem => problem.id === id)) await selectProblem(id);
}));

await action(async () => {
  await refreshProblems();
  const hash = decodeURIComponent(location.hash.slice(1));
  const id = state.problems.find(problem => problem.id === hash)?.id || state.problems[0]?.id;
  if (id) { await selectProblem(id); history.replaceState(null, '', '#' + encodeURIComponent(id)); }
  else { $('#document-content').textContent = '还没有题目。在「题库/」中添加一个题目目录，再点击左侧刷新。'; resetResult($('#result-content')); }
});
