// A deliberately small Markdown renderer. Raw HTML is always treated as text.
function inline(text) {
  const fragment = document.createDocumentFragment();
  const expression = /(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\((?:<[^>]+>|[^)]+)\))/g;
  let cursor = 0;
  for (const match of text.matchAll(expression)) {
    fragment.append(text.slice(cursor, match.index));
    const token = match[0];
    if (token.startsWith('`')) {
      const code = document.createElement('code'); code.textContent = token.slice(1, -1); fragment.append(code);
    } else if (token.startsWith('**')) {
      const strong = document.createElement('strong'); strong.append(inline(token.slice(2, -2))); fragment.append(strong);
    } else {
      const parts = token.match(/^\[([^\]]+)\]\((.+)\)$/);
      const target = parts[2].replace(/^<|>$/g, '');
      const link = document.createElement('a'); link.textContent = parts[1];
      if (/^https?:\/\//i.test(target)) { link.href = target; link.target = '_blank'; link.rel = 'noopener noreferrer'; }
      else if (!/^[a-z][a-z\d+.-]*:/i.test(target) && !target.startsWith('//')) { link.href = '#'; link.dataset.documentLink = target; }
      fragment.append(link);
    }
    cursor = match.index + token.length;
  }
  fragment.append(text.slice(cursor));
  return fragment;
}

function cellParts(line) { return line.trim().replace(/^\||\|$/g, '').split('|').map(cell => cell.trim()); }

export function renderMarkdown(container, text, isCode = false) {
  container.replaceChildren();
  if (isCode) {
    const pre = document.createElement('pre'); const code = document.createElement('code'); code.textContent = text;
    pre.append(code); container.append(pre); return;
  }
  const lines = text.replace(/\r\n/g, '\n').split('\n');
  for (let index = 0; index < lines.length;) {
    const line = lines[index];
    if (!line.trim()) { index++; continue; }
    if (line.trimStart().startsWith('```')) {
      const contents = []; index++;
      while (index < lines.length && !lines[index].trimStart().startsWith('```')) contents.push(lines[index++]);
      index++;
      const pre = document.createElement('pre'); const code = document.createElement('code'); code.textContent = contents.join('\n'); pre.append(code); container.append(pre); continue;
    }
    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) { const element = document.createElement(`h${Math.min(heading[1].length + 1, 6)}`); element.append(inline(heading[2])); container.append(element); index++; continue; }
    if (index + 1 < lines.length && line.includes('|') && /^\|?\s*:?-{3,}/.test(lines[index + 1].trim())) {
      const wrap = document.createElement('div'); wrap.className = 'markdown__table';
      const table = document.createElement('table'); const head = document.createElement('thead'); const row = document.createElement('tr');
      for (const value of cellParts(line)) { const th = document.createElement('th'); th.append(inline(value)); row.append(th); }
      head.append(row); table.append(head); const body = document.createElement('tbody'); index += 2;
      while (index < lines.length && lines[index].includes('|') && lines[index].trim()) {
        const tr = document.createElement('tr');
        for (const value of cellParts(lines[index++])) { const td = document.createElement('td'); td.append(inline(value)); tr.append(td); }
        body.append(tr);
      }
      table.append(body); wrap.append(table); container.append(wrap); continue;
    }
    const listMatch = line.match(/^\s*(?:([-*])|\d+\.)\s+(.+)$/);
    if (listMatch) {
      const list = document.createElement(listMatch[1] ? 'ul' : 'ol');
      while (index < lines.length) {
        const item = lines[index].match(/^\s*(?:([-*])|\d+\.)\s+(.+)$/);
        if (!item || Boolean(item[1]) !== Boolean(listMatch[1])) break;
        const li = document.createElement('li'); li.append(inline(item[2])); list.append(li); index++;
      }
      container.append(list); continue;
    }
    // The original problem files use plain labels and unfenced sample data.
    if (/^(输入格式|输出格式|数据范围|输入样例|输出样例|输入|输出)[：:]?$/.test(line.trim())) {
      const heading = document.createElement('h3'); heading.textContent = line.trim().replace(/[：:]$/, ''); container.append(heading); index++; continue;
    }
    if (/^\s*\d[\d\s]*$/.test(line)) {
      const sample = [];
      while (index < lines.length && /^\s*\d[\d\s]*$/.test(lines[index]) && lines[index].trim()) sample.push(lines[index++].trim());
      const pre = document.createElement('pre'); pre.textContent = sample.join('\n'); container.append(pre); continue;
    }
    const paragraph = document.createElement(line.startsWith('> ') ? 'blockquote' : 'p');
    paragraph.append(inline(line.replace(/^> /, ''))); container.append(paragraph); index++;
  }
}
