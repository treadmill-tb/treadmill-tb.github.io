// Small progressive enhancements: copy buttons, docs search, the mobile docs
// menu and the current-section highlight in "On this page". Everything works
// without JavaScript; this only adds to it.

function initCopy() {
  document.querySelectorAll('[data-copy]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const pre = btn.closest('.codeblock')?.querySelector('pre');
      if (!pre) return;
      const clone = pre.cloneNode(true);
      clone.querySelectorAll('.prompt').forEach((n) => n.remove());
      try {
        await navigator.clipboard.writeText(clone.textContent.replace(/\n$/, ''));
        btn.textContent = 'Copied';
      } catch {
        btn.textContent = 'Press Ctrl+C';
      }
      setTimeout(() => { btn.textContent = 'Copy'; }, 1600);
    });
  });
}

function initMenu() {
  const btn = document.querySelector('.docs-menu-btn');
  const side = document.getElementById('docs-sidebar');
  const header = document.querySelector('.docs-header');
  if (!btn || !side) return;
  const setH = () => document.documentElement.style.setProperty('--docs-header-h', `${header.offsetHeight}px`);
  setH();
  window.addEventListener('resize', setH);
  const set = (open) => {
    side.classList.toggle('is-open', open);
    btn.setAttribute('aria-expanded', String(open));
    btn.setAttribute('aria-label', open ? 'Close navigation' : 'Open navigation');
  };
  btn.addEventListener('click', () => set(!side.classList.contains('is-open')));
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') set(false); });
  side.addEventListener('click', (e) => { if (e.target.closest('a')) set(false); });
}

function initToc() {
  const links = [...document.querySelectorAll('[data-toc] a')];
  if (!links.length || !('IntersectionObserver' in window)) return;
  const byId = new Map(links.map((a) => [decodeURIComponent(a.hash.slice(1)), a]));
  const targets = [...byId.keys()].map((id) => document.getElementById(id)).filter(Boolean);
  const visible = new Set();
  const update = () => {
    const first = targets.find((t) => visible.has(t));
    if (!first) return;
    links.forEach((a) => a.classList.remove('is-current'));
    byId.get(first.id)?.classList.add('is-current');
  };
  const io = new IntersectionObserver((entries) => {
    entries.forEach((e) => (e.isIntersecting ? visible.add(e.target) : visible.delete(e.target)));
    update();
  }, { rootMargin: '-72px 0px -55% 0px' });
  targets.forEach((t) => io.observe(t));
}

function initSearch() {
  const root = document.querySelector('[data-search]');
  if (!root) return;
  const input = root.querySelector('input');
  const list = root.querySelector('ul');
  let index = null;
  let active = -1;

  const load = async () => {
    if (index) return index;
    const res = await fetch(root.dataset.index);
    index = (await res.json()).map((d) => ({ ...d, tl: d.t.toLowerCase(), hay: `${d.t} ${d.d} ${d.s} ${d.b}`.toLowerCase() }));
    return index;
  };

  const score = (d, terms) => {
    let s = 0;
    for (const t of terms) {
      if (!d.hay.includes(t)) return 0;
      if (d.tl === t) s += 20;
      else if (d.tl.startsWith(t)) s += 10;
      else if (d.tl.includes(t)) s += 6;
      else if (d.d.toLowerCase().includes(t)) s += 3;
      else s += 1;
    }
    return s;
  };

  const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  const render = (results, q) => {
    active = -1;
    if (!q) { list.hidden = true; list.innerHTML = ''; return; }
    list.hidden = false;
    if (!results.length) {
      list.innerHTML = `<li class="r-empty">No results for “${esc(q)}”</li>`;
      return;
    }
    list.innerHTML = results.map((d, i) => `<li role="option" id="sr-${i}" aria-selected="false"><a href="${esc(d.u)}"><span class="r-sec">${esc(d.s)}</span><span class="r-title">${esc(d.t)}</span>${d.d ? `<span class="r-desc">${esc(d.d)}</span>` : ''}</a></li>`).join('');
  };

  const run = async () => {
    const q = input.value.trim();
    if (!q) return render([], '');
    const terms = q.toLowerCase().split(/\s+/);
    const docs = await load();
    const results = docs.map((d) => [score(d, terms), d]).filter(([s]) => s > 0)
      .sort((a, b) => b[0] - a[0]).slice(0, 12).map(([, d]) => d);
    render(results, q);
  };

  const move = (delta) => {
    const items = [...list.querySelectorAll('[role="option"]')];
    if (!items.length) return;
    active = (active + delta + items.length) % items.length;
    items.forEach((li, i) => li.setAttribute('aria-selected', String(i === active)));
    input.setAttribute('aria-activedescendant', items[active].id);
    items[active].scrollIntoView({ block: 'nearest' });
  };

  input.addEventListener('input', run);
  input.addEventListener('focus', () => { load(); if (input.value.trim()) run(); });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); move(1); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); move(-1); }
    else if (e.key === 'Enter') {
      const a = list.querySelector('[aria-selected="true"] a') || list.querySelector('a');
      if (a) { e.preventDefault(); window.location.href = a.href; }
    } else if (e.key === 'Escape') { input.value = ''; render([], ''); input.blur(); }
  });
  document.addEventListener('click', (e) => { if (!root.contains(e.target)) list.hidden = true; });
  // "/" focuses search, unless the reader is typing somewhere already.
  document.addEventListener('keydown', (e) => {
    if (e.key !== '/' || e.metaKey || e.ctrlKey || e.altKey) return;
    const t = e.target;
    if (t.closest('input, textarea, select, [contenteditable="true"]')) return;
    e.preventDefault();
    input.focus();
  });
}

initCopy();
initMenu();
initToc();
initSearch();
