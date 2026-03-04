/* ===================================================================
   Crypto CEO Tracker — Static Frontend (GitHub Pages edition)
   All data loaded from ./data/articles.json — no backend needed.
   =================================================================== */

'use strict';

// ---- State ----
const state = {
  ceos: {},
  allArticles: [],    // full dataset from JSON
  filtered: [],       // after CEO + search + tag filters
  currentCEO: 'all',
  searchTerm: '',
  tagFilter: '',
  pageSize: 40,
  shownCount: 0,
};

// ---- DOM refs ----
const $ = id => document.getElementById(id);
const timeline      = $('timeline');
const loadingEl     = $('loadingState');
const emptyEl       = $('emptyState');
const loadMoreWrap  = $('loadMoreWrap');
const searchInput   = $('searchInput');
const searchClear   = $('searchClear');
const ceoTabsEl     = $('ceoTabs');
const statTotal     = $('statTotal');
const lastUpdatedEl = $('lastUpdated');
const ceoStatsBar   = $('ceoStatsBar');
const toastEl       = $('toast');
const activeTagBar  = $('activeTagBar');
const activeTagLabel = $('activeTagLabel');

// ---- Init ----
async function init() {
  try {
    // Load CEO definitions and article data in parallel
    const [ceosRes, dataRes] = await Promise.all([
      fetch('./data/ceos.json'),
      fetch('./data/articles.json'),
    ]);

    state.ceos = await ceosRes.json();
    const data = await dataRes.json();
    state.allArticles = data.articles || [];

    // Show last updated time
    if (data.updated_at) {
      lastUpdatedEl.textContent = formatDate(data.updated_at);
    }

    // Stats total
    statTotal.querySelector('.stat-num').textContent =
      (data.total || state.allArticles.length).toLocaleString();

    renderCEOTabs();
    renderCEOStats(data.by_ceo || {});
    applyFilters();
    renderTimeline();
  } catch (e) {
    console.error('Failed to load data:', e);
    loadingEl.innerHTML = `
      <span class="empty-icon">⚠️</span>
      <p>数据加载失败。如果是本地预览请使用服务器方式打开，<br>
         或访问 GitHub Pages 地址查看。</p>`;
  }
}

// ---- CEO tabs ----
function renderCEOTabs() {
  ceoTabsEl.querySelectorAll('.ceo-tab[data-ceo]:not([data-ceo="all"])').forEach(el => el.remove());
  Object.entries(state.ceos).forEach(([name, info]) => {
    const btn = document.createElement('button');
    btn.className = 'ceo-tab';
    btn.dataset.ceo = name;
    btn.innerHTML = `
      <span style="display:inline-block;width:8px;height:8px;border-radius:50%;
                   background:${info.color};margin-right:5px;"></span>${name}`;
    btn.onclick = () => filterByCEO(name, btn);
    ceoTabsEl.appendChild(btn);
  });
}

function renderCEOStats(byCeo) {
  ceoStatsBar.innerHTML = '';
  Object.entries(byCeo).forEach(([name, cnt]) => {
    const info = state.ceos[name] || {};
    const pill = document.createElement('div');
    pill.className = 'ceo-stat-pill';
    pill.innerHTML = `
      <span class="ceo-dot" style="background:${info.color || '#888'}"></span>
      <strong>${escHtml(name)}</strong>
      <span>(${cnt})</span>`;
    ceoStatsBar.appendChild(pill);
  });
}

// ---- Filtering (all client-side) ----
function applyFilters() {
  let list = state.allArticles;

  // CEO filter
  if (state.currentCEO !== 'all') {
    list = list.filter(a => a.ceo_name === state.currentCEO);
  }

  // Search filter
  if (state.searchTerm.trim()) {
    const q = state.searchTerm.toLowerCase();
    list = list.filter(a =>
      (a.title || '').toLowerCase().includes(q) ||
      (a.key_quote || '').toLowerCase().includes(q) ||
      (a.tags || []).join(' ').toLowerCase().includes(q) ||
      (a.source || '').toLowerCase().includes(q)
    );
  }

  // Tag filter
  if (state.tagFilter) {
    list = list.filter(a => (a.tags || []).includes(state.tagFilter));
  }

  state.filtered = list;
  state.shownCount = 0;
}

function filterByCEO(ceo, btn) {
  state.currentCEO = ceo;
  ceoTabsEl.querySelectorAll('.ceo-tab').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  applyFilters();
  renderTimeline();
}

function onSearch() {
  state.searchTerm = searchInput.value;
  searchClear.style.display = state.searchTerm ? 'block' : 'none';
  clearTimeout(state._searchTimer);
  state._searchTimer = setTimeout(() => { applyFilters(); renderTimeline(); }, 250);
}

function clearSearch() {
  searchInput.value = '';
  state.searchTerm = '';
  searchClear.style.display = 'none';
  applyFilters();
  renderTimeline();
}

function filterByTag(tag) {
  state.tagFilter = tag;
  activeTagBar.style.display = 'flex';
  activeTagLabel.textContent = tag;
  document.querySelectorAll('.tag').forEach(el => {
    el.classList.toggle('active-tag-pill', el.textContent.trim() === tag);
  });
  applyFilters();
  renderTimeline();
}

function clearTagFilter() {
  state.tagFilter = '';
  activeTagBar.style.display = 'none';
  document.querySelectorAll('.tag').forEach(el => el.classList.remove('active-tag-pill'));
  applyFilters();
  renderTimeline();
}

// ---- Render ----
function renderTimeline() {
  loadingEl.style.display = 'none';
  timeline.innerHTML = '';
  state.shownCount = 0;

  if (state.filtered.length === 0) {
    emptyEl.style.display = 'block';
    loadMoreWrap.style.display = 'none';
    return;
  }
  emptyEl.style.display = 'none';
  appendCards();
}

function appendCards() {
  const slice = state.filtered.slice(state.shownCount, state.shownCount + state.pageSize);
  let lastDate = '';

  slice.forEach(article => {
    const dateKey = formatDateKey(article.published_at);
    if (dateKey !== lastDate) {
      lastDate = dateKey;
      const sep = document.createElement('div');
      sep.className = 'date-separator';
      sep.textContent = dateKey;
      timeline.appendChild(sep);
    }
    timeline.appendChild(createCard(article));
  });

  state.shownCount += slice.length;
  loadMoreWrap.style.display = state.shownCount < state.filtered.length ? 'block' : 'none';
}

function showMore() {
  appendCards();
}

function createCard(article) {
  const info  = state.ceos[article.ceo_name] || {};
  const color = info.color || '#5b8ef0';
  const twitter = info.twitter || '';

  const item = document.createElement('div');
  item.className = 'tl-item';

  const dot = document.createElement('div');
  dot.className = 'tl-dot';
  dot.style.background = color;

  const card = document.createElement('div');
  card.className = 'tl-card';

  const tagsHtml = (article.tags || [])
    .map(t => `<span class="tag" onclick="filterByTag('${escHtml(t)}')">${escHtml(t)}</span>`)
    .join('');

  const quoteHtml = article.key_quote
    ? `<div class="card-quote">${escHtml(truncate(article.key_quote, 180))}</div>`
    : '';

  const twitterHtml = twitter
    ? `<a class="twitter-link" href="https://twitter.com/${twitter}"
          target="_blank" rel="noopener">
         <svg width="13" height="13" viewBox="0 0 24 24" fill="#1d9bf0">
           <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.744l7.73-8.835L1.254 2.25H8.08l4.259 5.633zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
         </svg>
         @${twitter}
       </a>`
    : '';

  card.innerHTML = `
    <div class="card-accent-bar" style="background:${color}"></div>
    <div class="card-header">
      <div class="card-title">
        <a href="${escHtml(article.url)}" target="_blank" rel="noopener">${escHtml(article.title)}</a>
      </div>
      <div class="card-meta">
        <span class="ceo-badge" style="background:${color}20;color:${color};border:1px solid ${color}40;">
          <span class="ceo-badge-dot" style="background:${color}"></span>
          ${escHtml(article.ceo_name)}
          <span style="opacity:.65;font-weight:400;font-size:10px;">${escHtml(article.exchange)}</span>
        </span>
        <span class="card-date">${formatDate(article.published_at)}</span>
      </div>
    </div>
    ${quoteHtml}
    <div class="card-footer">
      <div class="card-tags">${tagsHtml}</div>
      <div style="display:flex;align-items:center;gap:10px;">
        ${twitterHtml}
        <span class="card-source">
          <span class="source-dot"></span>
          ${escHtml(article.source || '')}
        </span>
      </div>
    </div>`;

  item.appendChild(dot);
  item.appendChild(card);
  return item;
}

// ---- Utilities ----
function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function truncate(str, max) {
  if (!str || str.length <= max) return str || '';
  return str.slice(0, max) + '…';
}
function formatDate(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('zh-CN', {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
}
function formatDateKey(iso) {
  if (!iso) return '未知日期';
  try {
    return new Date(iso).toLocaleDateString('zh-CN', {
      year: 'numeric', month: 'long', day: 'numeric', weekday: 'short',
    });
  } catch { return iso.slice(0, 10); }
}
function showToast(msg) {
  toastEl.textContent = msg;
  toastEl.classList.add('show');
  clearTimeout(state._toastTimer);
  state._toastTimer = setTimeout(() => toastEl.classList.remove('show'), 3000);
}

// ---- Expose for HTML onclick ----
window.filterByCEO   = filterByCEO;
window.onSearch      = onSearch;
window.clearSearch   = clearSearch;
window.filterByTag   = filterByTag;
window.clearTagFilter = clearTagFilter;
window.showMore      = showMore;

// ---- Boot ----
window.addEventListener('DOMContentLoaded', init);
