export const STATUS = { PASS: '本地通过', OK: '运行完成', WA: '答案错误', CE: '编译失败', RE: '运行出错', TLE: '运行超时', OLE: '输出过多', ERROR: '工具出错', RUNNING: '运行中' };
export const MODE = { sample: '运行样例', manual: '手动运行', check: '检查全部' };

function node(tag, className, text) {
  const element = document.createElement(tag); element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

export function resetResult(container, running = false) {
  const empty = node('div', 'results-panel__empty');
  empty.append(node('strong', '', running ? '正在编译并运行…' : '写一点，跑一下。'));
  empty.append(node('span', '', running ? '结果和输入输出会自动保存到题目目录。' : '运行样例，或用自己的数据验证思路。'));
  container.replaceChildren(empty);
  container.setAttribute('aria-busy', String(running));
}

export function renderResult(container, result) {
  container.replaceChildren(); container.setAttribute('aria-busy', 'false');
  const summary = node('div', 'result__summary');
  const status = node('strong', 'result__status', STATUS[result.status] || result.status);
  status.dataset.failed = String(!['PASS', 'OK', 'RUNNING'].includes(result.status));
  summary.append(status, node('span', 'result__detail', `${MODE[result.mode] || result.mode} · ${result.passed} / ${result.total} ${result.mode === 'manual' ? '次执行' : '个用例'} · ${(result.duration_ms / 1000).toFixed(2)} s · ${result.attempt}`));
  container.append(summary);
  const log = node('p', 'result__log', `日志：${result.log_path}/`); container.append(log);
  if (result.mode === 'manual') container.append(node('p', 'result__message', '手动输入只执行程序，不判断答案是否正确。'));
  if (result.status === 'TLE') container.append(node('p', 'result__message', `单个用例超过 ${result.time_limit_seconds} 秒，已停止程序。检查循环和递归结束条件。`));
  if (result.status === 'RE') container.append(node('p', 'result__message', '程序异常退出。请检查数组越界、递归深度和除零等问题。'));
  if (result.status === 'OLE') container.append(node('p', 'result__message', '输出达到 4 MB 上限。请检查是否在循环中持续打印。'));
  if (result.status === 'RUNNING') container.append(node('p', 'result__message', '这次运行尚未完成；若应用曾被关闭，这是一条中断记录。'));
  if (result.error) container.append(node('p', 'result__message', result.error));
  if (result.compiler) {
    const compiler = node('details', 'result__compiler'); compiler.open = result.status === 'CE';
    compiler.append(node('summary', '', result.status === 'CE' ? '编译错误' : '编译提示'), node('pre', 'result__code', result.compiler)); container.append(compiler);
  }
  for (const [index, record] of result.cases.entries()) {
    const details = node('details', 'result__case');
    details.open = !['PASS', 'OK'].includes(record.status) || result.cases.length === 1;
    details.append(node('summary', '', `${String(index + 1).padStart(2, '0')}  ${record.name} · ${STATUS[record.status] || record.status} · ${record.duration_ms} ms`));
    const columns = node('div', 'result__columns');
    const fields = [['输入', record.input], ['实际输出', record.stdout]];
    if (record.expected !== null) fields.push(['预期输出', record.expected]);
    if (record.stderr) fields.push(['标准错误', record.stderr]);
    for (const [label, value] of fields) {
      const column = node('div', ''); column.append(node('span', 'result__label', label), node('pre', 'result__code', value || '（空）')); columns.append(column);
    }
    details.append(columns, node('p', 'result__log', `${record.file_prefix} · 退出码 ${record.exit_code}`)); container.append(details);
    if (record.source?.kind === 'file') details.append(node('p', 'result__log', `用例来源：${record.source.input} → ${record.source.output}`));
    else if (record.source?.kind === 'sample') details.append(node('p', 'result__log', `用例来源：${record.source.path} · 样例 ${record.source.index + 1}`));
  }
  if (result.cases.length && result.cases.length < result.total) container.append(node('p', 'result__message', '遇到首个失败用例后停止；其余用例尚未运行。'));
}

export function historyOptions(select, runs, selected = '') {
  select.replaceChildren(new Option('历史运行日志', ''));
  for (const run of runs) {
    const time = new Date(run.created_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
    select.add(new Option(`${time} · ${MODE[run.mode]} · ${STATUS[run.status] || run.status}`, run.id));
  }
  select.value = selected;
}
