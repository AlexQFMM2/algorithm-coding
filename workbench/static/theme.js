// Apply the remembered theme before styles load, avoiding a bright first frame.
(() => {
  const storageKey = 'acwing.theme';
  let theme = 'dark';
  try {
    const saved = localStorage.getItem(storageKey);
    if (saved === 'light' || saved === 'dark') theme = saved;
  } catch { /* The workspace also works when browser storage is unavailable. */ }

  function apply() {
    document.documentElement.dataset.theme = theme;
    document.querySelector('meta[name="theme-color"]').content = theme === 'dark' ? '#21252b' : '#f6f7f9';
    const toggle = document.querySelector('#theme-toggle');
    if (!toggle) return;
    const label = theme === 'dark' ? '切换到浅色主题' : '切换到 One Dark 主题';
    toggle.title = label;
    toggle.setAttribute('aria-label', label);
    document.querySelector('#theme-icon').setAttribute('href', theme === 'dark' ? '#i-sun' : '#i-moon');
  }

  apply();
  document.addEventListener('DOMContentLoaded', () => {
    apply();
    document.querySelector('#theme-toggle').addEventListener('click', () => {
      theme = theme === 'dark' ? 'light' : 'dark';
      apply();
      try { localStorage.setItem(storageKey, theme); } catch { /* Use this session's choice. */ }
    });
  });
})();
