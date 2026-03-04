/* ===================================================================
   Crypto CEO Tracker — Frontend Logic
   =================================================================== */

'use strict';

// ---- State ----
const state = {
  ceos: {},           // { name: { exchange, role, color, twitter } }
  articles: [],       // all loaded articles
  filtered: [],       // after filter + search
  currentCEO: 'all',
  searchTerm: '',
  tagFilter: '',
  offset: 0,
  pageSize: 60,
  loading: false,
  hasMore: false,
  autoRefreshTimer: null,
};

// ---- DOM refs ----
const $ = id => document.getElementById(id);
const timeline   = $('timeline');
const loadingEl  = $('loadingState');
const emptyEl    = $('emptyState');
const loadMoreWrap = $('loadMoreWrap');
const searchInput  = $('searchInput');
const searchClear  = $('searchClear');
const ceoTabsEl    = $('ceoTabs');
const statTotal    = $('statTotal');
const lastUpdatedEl = $('lastUpdated');
const ceoStatsBar  = $('ceoStatsBar');
const toastEl      = $('toast');
const refreshBtn   = $('refreshBtn');
const activeTagBar = $('activeTagBar');
const activeTagLabel = $('activeTagLabel');

// ---- Init ----
async function init() {
  await loadCEOs();
  await loadArticles(true);
  await loadStats();
  startAutoRefresh();
}

// ---- CEO list ----
async function loadCEOs() {
  try {
    const res = await fetch('/api/ceos');
    const data = await res.json();
    state.ceos = data.ceos || {};
    renderCEOTabs();
  } catch (e) {
    console.error('Failed to load CEOs', e);
  }
}

function renderCEOTabs() {
  // Remove old dynamic tabs
  ceoTabsEl.querySelectorAll('.ceo-tab[data-ceo]').forEach(el => {
    if (el.dataset.ceo !== 'all') el.remove();
  });

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

// ---- Articles ----
async function loadArticles(reset = false) {
  if (state.loading) return;
  state.loading = true;

  if (reset) {
    state.offset = 0;
    state.articles = [];
    timeline.innerHTML = '';
    showLoading(true);
  }

  const params = new URLSearchParams({
    ceo: state.currentCEO,
    search: state.searchTerm,
    limit: state.pageSize,
    offset: state.offset,
  });

  try {
    const res = await fetch(`/api/articles?${params}`);
    const data = await res.json();
    const incoming = data.articles || [];

    state.hasMore = incoming.length === state.pageSize;
    state.articles = reset ? incoming : [...state.articles, ...incoming];
    state.offset += incoming.length;

    applyTagFilter();
    renderTimeline(reset ? state.filtered : state.filtered.slice(-incoming.length), !reset);
    updateLoadMore();
  } catch (e) {
    console.error('Failed to load articles', e);
    showToast('加载失败，请稍后重试。');
  } finally {
    state.loading = false;
    showLoading(false);
  }
}

// ---- Filtering ----
function applyTagFilter() {
  if (state.tagFilter) {
    state.filtered = state.articles.filter(a =>
      Array.isArray(a.tags) && a.tags.includes(state.tagFilter)
    );
  } else {
    state.filtered = [...state.articles];
  }
}

function filterByCEO(ceo, btn) {
  state.currentCEO = ceo;
  // Update active tab
  ceoTabsEl.querySelectorAll('.ceo-tab').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  loadArticles(true);
}

function onSearch() {
  const val = searchInput.value;
  state.searchTerm = val;
  searchClear.style.display = val ? 'block' : 'none';
  clearTimeout(state._searchTimer);
  state._searchTimer = setTimeout(() => loadArticles(true), 350);
}

function clearSearch() {
  searchInput.value = '';
  state.searchTerm = '';
  searchClear.style.display = 'none';
  loadArticles(true);
}

function filterByTag(tag) {
  state.tagFilter = tag;
  activeTagBar.style.display = 'flex';
  activeTagLabel.textContent = tag;
  // Highlight active tags
  document.querySelectorAll('.tag').forEach(el => {
    el.classList.toggle('active-tag-pill', el.textContent.trim() === tag);
  });
  applyTagFilter();
  renderTimeline(state.filtered, false);
}

function clearTagFilter() {
  state.tagFilter = '';
  activeTagBar.style.display = 'none';
  document.querySelectorAll('.tag').forEach(el => el.classList.remove('active-tag-pill'));
  applyTagFilter();
  renderTimeline(state.filtered, false);
}

function loadMore() {
  loadArticles(false);
}

// ---- Render ----
function renderTimeline(articles, append = false) {
  if (!append) timeline.innerHTML = '';

  emptyEl.style.display = (state.filtered.length === 0 && !state.loading) ? 'block' : 'none';

  let lastDate = '';

  (append ? articles : state.filtered).forEach(article => {
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
}

function createCard(article) {
  const info = state.ceos[article.ceo_name] || {};
  const color = info.color || '#5b8ef0';
  const twitter = info.twitter || '';
  const role = info.role || 'CEO';

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
    ? `<a class="twitter-link" href="https://twitter.com/${twitter}" target="_blank" rel="noopener">
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
    </div>
  `;

  item.appendChild(dot);
  item.appendChild(card);
  return item;
}

// ---- Stats ----
async function loadStats() {
  try {
    const res = await fetch('/api/stats');
    const data = await res.json();

    const total = data.total || 0;
    statTotal.querySelector('.stat-num').textContent = total.toLocaleString();

    if (data.last_updated) {
      lastUpdatedEl.textContent = formatDate(data.last_updated);
    }

    // CEO pills
    ceoStatsBar.innerHTML = '';
    Object.entries(data.by_ceo || {}).forEach(([name, cnt]) => {
      const info = state.ceos[name] || {};
      const pill = document.createElement('div');
      pill.className = 'ceo-stat-pill';
      pill.innerHTML = `
        <span class="ceo-dot" style="background:${info.color || '#888'}"></span>
        <strong>${escHtml(name)}</strong>
        <span>(${cnt})</span>
      `;
      ceoStatsBar.appendChild(pill);
    });
  } catch (e) {
    console.error('Failed to load stats', e);
  }
}

// ---- Refresh ----
async function triggerRefresh() {
  refreshBtn.classList.add('spinning');
  showToast('正在后台刷新数据…');
  try {
    await fetch('/api/refresh', { method: 'POST' });
    // Wait a few seconds then reload
    setTimeout(async () => {
      await loadArticles(true);
      await loadStats();
      refreshBtn.classList.remove('spinning');
      showToast('数据已更新！');
    }, 8000);
  } catch (e) {
    refreshBtn.classList.remove('spinning');
    showToast('刷新失败，请检查服务器连接。');
  }
}

function startAutoRefresh() {
  // Re-poll stats every 60 seconds; reload articles every 5 minutes
  setInterval(loadStats, 60_000);
  setInterval(() => loadArticles(true), 300_000);
}

// ---- Load More ----
function updateLoadMore() {
  loadMoreWrap.style.display = state.hasMore ? 'block' : 'none';
}

// ---- Utilities ----
function showLoading(on) {
  loadingEl.style.display = on ? 'block' : 'none';
  emptyEl.style.display = 'none';
}

function showToast(msg) {
  toastEl.textContent = msg;
  toastEl.classList.add('show');
  clearTimeout(state._toastTimer);
  state._toastTimer = setTimeout(() => toastEl.classList.remove('show'), 3000);
}

function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function truncate(str, max) {
  if (!str || str.length <= max) return str || '';
  return str.slice(0, max) + '…';
}

function formatDate(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleString('zh-CN', {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
}

function formatDateKey(iso) {
  if (!iso) return '未知日期';
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('zh-CN', {
      year: 'numeric', month: 'long', day: 'numeric', weekday: 'short',
    });
  } catch { return iso.slice(0, 10); }
}

// ---- Boot ----
window.addEventListener('DOMContentLoaded', init);

// Expose globals for HTML onclick attributes
window.filterByCEO = filterByCEO;
window.onSearch = onSearch;
window.clearSearch = clearSearch;
window.filterByTag = filterByTag;
window.clearTagFilter = clearTagFilter;
window.loadMore = loadMore;
window.triggerRefresh = triggerRefresh;
