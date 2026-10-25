import { addToBasket, loadProjectCenter, sendDeliveryFeedback, updateBasket } from './service.js';


const VIEWS = [
  ['book', '项目开发书'],
  ['architecture', '系统结构图'],
  ['objects', '交易对象目录'],
  ['modules', '开发模块'],
  ['requests', '待修改与处理'],
  ['deliveries', '当前交付'],
  ['manual', '使用说明书'],
];


export function createProjectCenterView({ root, events }) {
  const state = {
    root,
    events,
    view: 'book',
    loaded: false,
    loading: false,
    drawerOpen: false,
    selectedIds: new Set(),
    notice: '',
    records: {},
    lastFocusKey: '',
    expandedNodes: new Set(),
    expandedBookChapters: new Set(),
    currentBookChapterId: '',
    bookInitialized: false,
  };

  root.addEventListener('click', event => onClick(event, state));
  root.addEventListener('toggle', event => onBookChapterToggle(event, state), true);
  root.addEventListener('keydown', event => {
    if (event.key === 'Escape' && state.drawerOpen) closeDrawer(state);
  });
  events.on('project-center:shown', ({ view }) => {
    state.view = validView(view) ? view : state.view;
    render(state);
  });
  events.on('project-center:refresh', () => refresh(state));

  refresh(state);
  return {
    refresh: () => refresh(state),
    openView: view => {
      state.view = validView(view) ? view : 'book';
      render(state);
    },
  };
}


async function refresh(state) {
  if (state.loading) return;
  state.loading = true;
  render(state);
  try {
    state.records = await loadProjectCenter();
  } catch (error) {
    const message = error?.userMessage || error?.message || '项目中心暂时无法读取';
    state.records = Object.fromEntries(['overview', 'modules', 'manual', 'basket', 'requests', 'deliveries', 'versionUnderstanding']
      .map(key => [key, { data: null, error: message }]));
  }
  state.loaded = true;
  state.loading = false;
  render(state);
}


function render(state) {
  const records = state.records;
  const overview = records.overview?.data?.data || null;
  const moduleData = records.modules?.data?.data || {};
  const modules = moduleData.tree || moduleData.items || [];
  const objectCatalog = moduleData.object_catalog || overview?.object_catalog || {};
  const manual = records.manual?.data?.data?.manual || null;
  const basket = records.basket?.data?.data || { items: [], count: 0, focus: null };
  const requests = records.requests?.data?.data?.items || [];
  const deliveries = records.deliveries?.data?.data?.items || [];
  const versionUnderstanding = records.versionUnderstanding?.data?.data || null;
  const versionUnderstandingError = records.versionUnderstanding?.error || '';
  const readError = firstError(records);
  const body = state.loading && !state.loaded
    ? loadingHtml()
    : pageHtml(state, { overview, modules, objectCatalog, manual, basket, requests, deliveries, versionUnderstanding, versionUnderstandingError, readError });
  state.root.innerHTML = body;
  if (state.drawerOpen) focusDrawer(state);
  revealCurrentTab(state);
}


function pageHtml(state, data) {
  const { overview, modules, objectCatalog, manual, basket, requests, deliveries, versionUnderstanding, versionUnderstandingError, readError } = data;
  const projectName = overview?.project?.name || '小雪项目中心';
  const main = {
    book: bookHtml(state, overview, deliveries),
    architecture: architectureHtml(),
    objects: objectsHtml(objectCatalog),
    modules: modulesHtml(modules, state, versionUnderstanding, versionUnderstandingError),
    requests: requestsHtml(basket, requests, state.selectedIds),
    deliveries: deliveriesHtml(deliveries),
    manual: manualHtml(manual),
  }[state.view];
  return `
    <section class="pc-shell" aria-labelledby="project-center-title">
      <header class="pc-header">
        <div>
          <span class="pc-eyebrow">${escapeHtml(projectName)}</span>
          <h1 id="project-center-title">${escapeHtml(overview?.book?.headline || '看清现在，再决定哪里值得改。')}</h1>
          <p>${escapeHtml(overview?.project?.summary || '正在读取项目中心…')}</p>
        </div>
        <div class="pc-header-actions">
          <button class="pc-btn pc-btn-quiet" data-pc-action="refresh">刷新状态</button>
          <button class="pc-btn pc-btn-primary" data-pc-action="open-basket" data-pc-focus-key="header-basket" aria-controls="pc-change-basket" aria-expanded="${state.drawerOpen}">待修改 <span class="pc-count">${basket.count || 0}</span></button>
        </div>
      </header>
      <div class="pc-tabs-wrap">
        <nav class="pc-tabs" aria-label="项目中心内容，可左右滑动查看全部标签">
          ${VIEWS.map(([id, label]) => `<button class="pc-tab ${state.view === id ? 'active' : ''}" data-pc-action="view" data-view="${id}" ${state.view === id ? 'aria-current="page"' : ''}>${label}</button>`).join('')}
        </nav>
        <span class="pc-tab-scroll-hint" aria-hidden="true">左右滑动查看全部标签 →</span>
      </div>
      ${state.notice ? `<p class="pc-notice" role="status">${escapeHtml(state.notice)}</p>` : ''}
      ${readError ? `<div class="pc-state pc-state-warning"><b>有一部分状态暂时读不到</b><span>${escapeHtml(readError)}，不影响你查看其他已加载内容。</span></div>` : ''}
      ${quickStartHtml()}
      ${state.drawerOpen ? basketDrawerHtml(basket, state.selectedIds) : ''}
      <main class="pc-main">${main}</main>
    </section>`;
}


function architectureHtml() {
  const steps = [
    ['人', '定边界、看信息、做判断、决定是否写入'],
    ['小雪', '整理信息、调用方法、找反证、指出缺口'],
    ['信息', '比赛、赔率、伤停、版本、舆情、赛果和用户材料'],
    ['普通 TK', '长期知识、规律、画像、方法和对象理解'],
    ['交易 TK', '带适用条件、交易含义和失效条件的交易认识'],
    ['当前判断', '本场或当前对象的临时解释与决定依据'],
    ['结果 / 复盘', '回看当时依据，决定保留、修订或暂停'],
  ];
  return `<section class="pc-architecture" aria-label="交易信息系统结构图">
    <div class="pc-section-heading"><div><span class="pc-kicker">系统结构图</span><h2>人和小雪共同维护的一条主线</h2><p>这张图来自项目统一骨架，不是 TK 关系图；新增对象只接入对象适配层，不改公共主线。</p></div><button class="pc-text-action" data-pc-action="view" data-view="objects">查看交易对象目录 →</button></div>
    <div class="pc-flow">${steps.map(([title, detail], index) => `<div class="pc-flow-step"><div class="pc-flow-node pc-flow-${index}"><b>${title}</b><span>${detail}</span></div>${index < steps.length - 1 ? '<span class="pc-flow-arrow" aria-hidden="true">↓</span>' : ''}</div>`).join('')}</div>
    <div class="pc-architecture-notes"><article><b>唯一载体</b><p>普通 TK 和交易 TK 都是长期内容，但交易 TK 不等于自动交易指令。</p></article><article><b>不自动升级</b><p>当前判断、临场记录、结果和外部资料不会自动变成长期 TK。</p></article><article><b>可插拔对象</b><p>LOL、CS、足球等只需补主体、事件、信息源、结果源和方法。</p></article></div>
  </section>`;
}


function objectsHtml(catalog) {
  const objects = catalog?.objects || {};
  const entries = Object.entries(objects);
  if (!entries.length) return unavailableHtml('对象目录暂时读不到', '稍后刷新项目中心。');
  const labels = { active: '主业务已接入', partial: '部分可用', planned: '计划接入', blocked: '暂时阻塞' };
  return `<section class="pc-objects" aria-label="交易对象目录">
    <div class="pc-section-heading"><div><span class="pc-kicker">交易对象目录</span><h2>每个对象，现在能用到哪一步</h2><p>接入程度不等于今天运行正常。这里说明对象范围；日报和自动化等当下状态请看开发模块。</p></div><button class="pc-text-action" data-pc-action="view" data-view="modules">查看当前模块状态 →</button></div>
    <div class="pc-object-grid">${entries.map(([id, item]) => `<article class="pc-object-card"><div class="pc-object-top"><h3>${escapeHtml(item.display_name || id)}</h3><span class="pc-status ${escapeAttr(item.status || 'partial')}">${escapeHtml(labels[item.status] || '状态待确认')}</span></div>${[['现在能做什么', item.current_capability], ['现在不能保证什么', item.limitations], ['从哪里用', item.entry], ['下一步补什么', item.next_step]].map(([label, value]) => `<div><b>${label}</b><p>${escapeHtml(value || '尚未核实，不视为可用。')}</p></div>`).join('')}${item.known_gaps?.length ? `<div class="pc-object-gaps"><b>当前缺口</b><ul>${item.known_gaps.map(gap => `<li>${escapeHtml(gap)}</li>`).join('')}</ul></div>` : '<p>尚未登记具体缺口，不代表已全面验收。</p>'}</article>`).join('')}</div>
    <div class="pc-object-contract"><b>新增对象要补齐的内容</b><span>主体与事件 · 信息与结果来源 · 专业方法 · 普通知识与交易认识 · 判断内容 · 展示入口</span></div>
  </section>`;
}


function quickStartHtml() {
  return `<section class="pc-start-panel" aria-label="从这里开始">
    <div class="pc-start-heading"><span class="pc-kicker">从这里开始</span><b>不用先理解整个系统，按你现在的问题选一条</b></div>
    <div class="pc-start-actions">
      <button class="pc-start-card" data-pc-action="copy-chat" data-copy-recipient="小雪" data-prompt="聊聊我现在最想解决的问题"><strong>先问小雪</strong><span>有比赛、BP、交易或复盘问题，直接说现在想弄清什么。</span></button>
      <button class="pc-start-card" data-pc-action="open-entry" data-page="teams"><strong>先看资料</strong><span>横向看队伍、TS、画像、首发和长期资料。</span></button>
      <button class="pc-start-card" data-pc-action="view" data-view="manual"><strong>先看怎么用</strong><span>按场景查看去哪、怎么说、能得到什么。</span></button>
    </div>
  </section>`;
}


function bookHtml(state, overview, deliveries) {
  if (!overview) return unavailableHtml('项目全貌暂时读不到', '稍后刷新；其他工作台入口不受影响。');
  const runtime = overview.runtime || {};
  const daily = overview.daily || {};
  const book = overview.book || {};
  const chapters = book.chapters || [];
  if (!state.bookInitialized && chapters[0]) {
    state.bookInitialized = true;
    state.currentBookChapterId = chapters[0].id;
    state.expandedBookChapters.add(chapters[0].id);
  }
  return `
    <section class="pc-overview-grid">
      <article class="pc-hero-card">
        <span class="pc-kicker">现在到底怎样</span>
        <h2>${escapeHtml(runtime.label || '状态待确认')}</h2>
        <p>${escapeHtml(runtime.reason || '正在读取当前运行状态。')}</p>
        <div class="pc-live-row"><span class="pc-live-dot ${escapeHtml(runtime.status || 'degraded')}"></span><span>${escapeHtml(daily.label || '今天内容状态待确认')}</span><small>${escapeHtml(dailyNextStep(daily))}</small></div>
        <button class="pc-text-action" data-pc-action="view" data-view="manual">按使用说明选择入口 →</button>
        <button class="pc-why" data-pc-action="why" data-prompt="${escapeAttr(`为什么小雪现在显示「${runtime.label || '状态待确认'}」？请用人话说明它对今天使用有什么影响。`)}">问问为什么</button>
      </article>
      <article class="pc-boundary-card">
        <span class="pc-kicker">小雪负责什么</span>
        <p>${escapeHtml(overview.project?.boundary || '')}</p>
        <button class="pc-text-action" data-pc-action="view" data-view="manual">查看使用说明书 →</button>
      </article>
    </section>
    <section class="pc-section pc-book-directory" aria-label="项目开发书目录">
      <div class="pc-section-heading"><div><span class="pc-kicker">${escapeHtml(book.directory_label || '项目开发书目录')}</span><h2>从这里看懂整个项目</h2><p>按章节阅读，或直接跳到对应模块和使用场景。</p></div><button class="pc-text-action" data-pc-action="view" data-view="manual">按场景看使用说明 →</button></div>
      <div class="pc-directory-list">${chapters.map((chapter, index) => bookDirectoryItemHtml(chapter, index, state.currentBookChapterId === chapter.id)).join('')}</div>
    </section>
    <section class="pc-book-chapters">${chapters.map((chapter, index) => bookChapterHtml(chapter, index, state.expandedBookChapters.has(chapter.id), state.currentBookChapterId === chapter.id)).join('')}</section>
    <section class="pc-section pc-two-columns">
      <article class="pc-list-card pc-status-guide"><span class="pc-kicker">当前状态怎样读</span>${(book.status_guide || []).map(item => `<p><b>${escapeHtml(item.label)}</b><span>${escapeHtml(item.meaning)}</span></p>`).join('')}<button class="pc-text-action" data-pc-action="jump-module" data-module-tree-id="daily-and-automation">看状态相关模块 →</button></article>
      <article class="pc-list-card"><span class="pc-kicker">最近交付</span>${deliveryMiniList(deliveries)}<button class="pc-text-action" data-pc-action="view" data-view="deliveries">查看当前交付 →</button><p class="pc-muted">${escapeHtml(book.not_now || '')}</p></article>
    </section>`;
}


function bookDirectoryItemHtml(chapter, index, isCurrent) {
  return `<button class="${isCurrent ? 'is-current' : ''}" data-pc-action="jump-book" data-book-id="${escapeAttr(chapter.id)}" ${isCurrent ? 'aria-current="location"' : ''}><span>${String(index + 1).padStart(2, '0')}</span><b>${escapeHtml(chapter.title)}</b><small>${escapeHtml(chapter.summary)}</small><em class="pc-directory-current ${isCurrent ? 'is-visible' : ''}">正在阅读</em></button>`;
}


function bookChapterHtml(chapter, index, isOpen, isCurrent) {
  return `<details id="pc-book-${escapeAttr(chapter.id)}" data-book-id="${escapeAttr(chapter.id)}" class="pc-book-chapter ${isCurrent ? 'is-current' : ''}"${isOpen ? ' open' : ''}><summary class="pc-book-chapter-title"><span>${String(index + 1).padStart(2, '0')}</span><div><div class="pc-book-heading"><h2>${escapeHtml(chapter.title)}</h2><em class="pc-book-current ${isCurrent ? 'is-visible' : ''}">正在阅读</em></div><p>${escapeHtml(chapter.summary)}</p></div></summary><div class="pc-book-copy">${(chapter.paragraphs || []).map(paragraph => `<p>${escapeHtml(bookParagraph(paragraph))}</p>`).join('')}</div><div class="pc-link-row">${(chapter.module_tree_ids || []).map(id => `<button class="pc-link-chip" data-pc-action="jump-module" data-module-tree-id="${escapeAttr(id)}">查看对应模块</button>`).join('')}<button class="pc-back-link" data-pc-action="scroll-top">返回目录 ↑</button></div></details>`;
}


function modulesHtml(modules, state, versionUnderstanding, versionUnderstandingError) {
  if (!modules.length) return unavailableHtml('开发模块还没读到', '稍后刷新；这不会影响原有工作台。');
  return `
    <section class="pc-section-heading pc-module-heading"><div><span class="pc-kicker">开发模块</span><h2>按问题展开，不用记技术名</h2><p>先看一级概览，需要时展开二级能力。每一块都说明现在怎样、从哪里用和不能越过的边界。</p></div><button class="pc-btn pc-btn-quiet" data-pc-action="open-basket" data-pc-focus-key="modules-basket" aria-controls="pc-change-basket" aria-expanded="false">打开待修改</button></section>
    ${[
      { key: 'mainline', label: '每天的主线', hint: '日报 → 比赛 → 临场 → 复盘，按时间往前走。' },
      { key: 'foundation', label: '支撑你的底座', hint: '资料、方法、数据、工具和对话边界，按需查。' },
    ].map(group => {
      const items = modules.filter(module => (module.group || 'foundation') === group.key);
      if (!items.length) return '';
      return `<div class="pc-module-group"><h3 class="pc-module-group-title">${group.label}<small>${group.hint}</small></h3><div class="pc-module-tree">${items.map(module => moduleNodeHtml(module, state, 1, versionUnderstanding, versionUnderstandingError)).join('')}</div></div>`;
    }).join('')}`;
}


function moduleNodeHtml(module, state, level, versionUnderstanding, versionUnderstandingError) {
  const entry = module.entry || {};
  const entryAction = entryActionHtml(entry);
  const open = state.expandedNodes.has(module.id) ? ' open' : '';
  const children = (module.children || []).map(child => moduleNodeHtml(child, state, level + 1, versionUnderstanding, versionUnderstandingError)).join('');
  const versionBody = module.id === 'version-understanding'
    ? globalVersionUnderstandingHtml(versionUnderstanding, versionUnderstandingError)
    : '';
  return `
    <details id="pc-module-${escapeAttr(module.id)}" class="pc-module-node pc-level-${level}"${open}>
      <summary><span class="pc-tree-mark">${level === 1 ? '模块' : '能力'}</span><span class="pc-tree-summary"><b>${escapeHtml(module.name)}</b><small>${escapeHtml(module.purpose)}</small></span><span class="pc-status ${escapeAttr(module.runtime?.status || 'degraded')}">${escapeHtml(module.runtime?.label || '状态待确认')}</span></summary>
      <div class="pc-module-body">
        <div class="pc-module-current"><span>当前状态与限制</span><p>${escapeHtml(module.runtime?.label || '状态待确认')}：${escapeHtml(module.runtime?.reason || '尚未核实当前运行结果。')}</p>${(module.runtime_details || []).map(item => `<p>${escapeHtml(item.name)}：${escapeHtml(item.label)}，${escapeHtml(item.reason)}。</p>`).join('')}<p>入口正常只说明可以进入，不代表资料齐全或整条对话已验收。</p></div>
        <div class="pc-module-current"><span>当前能做什么</span><p>${escapeHtml(module.current_capability || '')}</p></div>
        ${versionBody}
        <dl class="pc-module-facts"><div><dt>什么时候用</dt><dd>${escapeHtml(module.when_to_use)}</dd></div><div><dt>从哪里进入</dt><dd>${escapeHtml(entryWhere(entry))}</dd></div><div><dt>下一步</dt><dd>${module.runtime?.status === 'broken' ? '先核对上面列出的异常部分，其他可用入口可继续使用。' : ''}${escapeHtml(module.next_step || '')}</dd></div></dl>
        <details class="pc-boundary-details"><summary>关联与使用边界</summary>${module.related_modules?.length ? `<p><b>和这些地方有关：</b>${escapeHtml(module.related_modules.join('、'))}</p>` : ''}<p><b>使用边界：</b>${escapeHtml(module.boundaries || '')}</p><p><b>资料还缺什么：</b>${escapeHtml(module.known_gap || '资料不足时会明确说明')}</p></details>
        <div class="pc-card-actions">${entryAction}<button class="pc-btn pc-btn-primary" data-pc-action="add-basket" data-module-id="${escapeAttr(module.basket_module_id || module.id)}" data-pc-focus-key="module-${escapeAttr(module.id)}">加入待修改</button></div>
        <input class="pc-note-input" data-note-module="${escapeAttr(module.basket_module_id || module.id)}" aria-label="给${escapeAttr(module.name)}补一句" placeholder="可补一句：哪里不顺（不填也行）">
        ${children ? `<div class="pc-module-children">${children}</div>` : ''}
      </div>
    </details>`;
}


function entryActionHtml(entry) {
  if (entry.type === 'web') return `<button class="pc-btn pc-btn-quiet" data-pc-action="open-entry" data-page="${escapeAttr(entry.page)}">${escapeHtml(entry.label)}</button>`;
  if (entry.type === 'project' || entry.type === 'status') return `<button class="pc-btn pc-btn-quiet" data-pc-action="view" data-view="book">${escapeHtml(entry.label)}</button>`;
  return `<button class="pc-btn pc-btn-quiet" data-pc-action="copy-chat" data-copy-recipient="小雪" data-prompt="${escapeAttr(entry.chat_prompt)}">${escapeHtml(entry.action_label || '复制发给小雪的话')}</button>`;
}


function globalVersionUnderstandingHtml(versionUnderstanding, error) {
  const item = versionUnderstanding?.item;
  if (!item) {
    const reason = error || '统一版本理解对象暂时没有可展示的正文。';
    return `<div class="pc-module-current"><span>当前版本正文</span><p>当前版本正文暂时读不到</p><small>${escapeHtml(reason)}</small></div>`;
  }
  return `<div class="pc-module-current"><span>当前版本理解状态</span><p><b>${escapeHtml(item.topic || '统一版本理解')}</b> · 更新于 ${escapeHtml(formatVersionTime(item.created_at))}</p><small>正文已接入当前赛事页，项目中心只保留开发状态和入口说明。</small></div>`;
}


function formatVersionTime(value) {
  const text = String(value || '').trim();
  return text || '时间暂未记录';
}


function versionContentHtml(content) {
  const lines = String(content || '').trim().split('\n').map(line => line.trim());
  if (!lines.some(Boolean)) return '<p>当前版本正文暂时读不到</p>';
  const output = [];
  for (let index = 0; index < lines.length;) {
    const line = lines[index];
    if (!line) { index += 1; continue; }
    if (/^(#{1,6})\s+/.test(line)) {
      output.push(`<h4>${versionInlineHtml(line.replace(/^#{1,6}\s+/, ''))}</h4>`);
      index += 1;
      continue;
    }
    const listMatch = line.match(/^([-*]|\d+\.)\s+(.+)/);
    if (listMatch) {
      const ordered = /^\d+\.$/.test(listMatch[1]);
      const items = [];
      while (index < lines.length) {
        const item = lines[index].match(ordered ? /^\d+\.\s+(.+)/ : /^[-*]\s+(.+)/);
        if (!item) break;
        items.push(`<li>${versionInlineHtml(item[1])}</li>`);
        index += 1;
      }
      output.push(`<${ordered ? 'ol' : 'ul'}>${items.join('')}</${ordered ? 'ol' : 'ul'}>`);
      continue;
    }
    if (/^>\s?/.test(line)) {
      const quotes = [];
      while (index < lines.length && /^>\s?/.test(lines[index])) {
        quotes.push(versionInlineHtml(lines[index].replace(/^>\s?/, '')));
        index += 1;
      }
      output.push(`<blockquote>${quotes.join('<br>')}</blockquote>`);
      continue;
    }
    const paragraph = [];
    while (index < lines.length && lines[index] && !/^(#{1,6})\s+|^[-*]\s+|^\d+\.\s+|^>\s?/.test(lines[index])) {
      paragraph.push(versionInlineHtml(lines[index]));
      index += 1;
    }
    output.push(`<p>${paragraph.join('<br>')}</p>`);
  }
  return output.join('');
}


function versionInlineHtml(value) {
  return escapeHtml(value)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>');
}


function entryWhere(entry) {
  if (entry.type === 'web') return entry.label || '在工作台打开对应页面';
  if (entry.type === 'project' || entry.type === 'status') return entry.label || '在项目中心查看当前状态';
  return '回飞书和小雪说';
}


function requestsHtml(basket, requests, selectedIds) {
  return `
    <section class="pc-section-heading"><div><span class="pc-kicker">待修改与处理</span><h2>先收集感觉，再让小白把它变成一件值得做的事</h2><p>待修改不代表已经承诺施工；飞书聊清楚以后，才会进入正式处理。</p></div><button class="pc-btn pc-btn-primary" data-pc-action="open-basket" data-pc-focus-key="requests-basket" aria-controls="pc-change-basket" aria-expanded="false">查看待修改 ${basket.count || 0}</button></section>
    <section class="pc-request-layout">
      <article class="pc-list-card"><div class="pc-card-title-row"><h3>当前待修改</h3><span class="pc-count-inline">${basket.count || 0}</span></div>${basketMiniList(basket.items || [], selectedIds)}<button class="pc-text-action" data-pc-action="open-basket" data-pc-focus-key="requests-list-basket" aria-controls="pc-change-basket" aria-expanded="false">展开待修改 →</button></article>
      <article class="pc-list-card"><h3>处理中与待体验</h3>${requestList(requests)}<p class="pc-muted">这里的状态只说明处理进度，不会替代当前运行状态。</p></article>
    </section>`;
}


function deliveriesHtml(deliveries) {
  return `
    <section class="pc-section-heading"><div><span class="pc-kicker">当前交付</span><h2>看这次哪里变了，到哪里体验</h2><p>只展示可感知的变化、验证结果和仍需留意的地方。</p></div></section>
    ${deliveries.length ? `<div class="pc-delivery-list">${deliveries.map(deliveryCardHtml).join('')}</div>` : emptyHtml('还没有正在体验的交付', '交付进入体验后，会在这里告诉你改了什么、去哪里试。')}`;
}


function deliveryCardHtml(item) {
  const evidence = Array.isArray(item.verification_evidence) ? item.verification_evidence : [];
  const feedback = item.status === 'Released' || item.status === 'Verified'
    ? `<div class="pc-feedback"><button class="pc-btn pc-btn-quiet" data-pc-action="delivery-feedback" data-delivery-id="${escapeAttr(item.id)}" data-feedback="archive" data-revision="${item.revision}">好用，归档</button><button class="pc-btn pc-btn-primary" data-pc-action="delivery-feedback" data-delivery-id="${escapeAttr(item.id)}" data-feedback="return_to_basket" data-revision="${item.revision}" data-pc-focus-key="delivery-${escapeAttr(item.id)}">还不对，放回待修改</button></div>`
    : '';
  return `
    <article class="pc-delivery-card"><div class="pc-card-top"><span class="pc-status ${statusTone(item.status)}">${escapeHtml(item.status_label || item.status)}</span><button class="pc-why" data-pc-action="why" data-prompt="${escapeAttr(`为什么「${item.title}」现在是${item.status_label || item.status}？请结合本次改变和下一步解释。`)}">问问为什么</button></div>
      <h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.user_visible_change)}</p>
      ${item.user_validation_path ? `<div class="pc-try-path"><b>去这里体验</b><span>${escapeHtml(item.user_validation_path)}</span></div>` : ''}
      ${evidence.length ? `<details><summary>这次怎么确认的</summary>${evidence.map(entry => `<p><b>${escapeHtml(entry.entry)}</b>：${escapeHtml(entry.result)}<small>${escapeHtml(entry.risk && entry.risk !== '无' ? `仍需留意：${entry.risk}` : '没有额外风险')}</small></p>`).join('')}</details>` : ''}
      ${item.known_risks ? `<p class="pc-risk">仍需留意：${escapeHtml(item.known_risks)}</p>` : ''}${feedback}
    </article>`;
}


function manualHtml(manual) {
  if (!manual) return unavailableHtml('使用说明书暂时读不到', '稍后刷新；原有工作台入口不受影响。');
  const sections = manual.sections || [];
  const byId = Object.fromEntries(sections.map(section => [section.id, section]));
  return `<section class="pc-manual"><div class="pc-section-heading"><div><span class="pc-kicker">使用说明书</span><h2>${escapeHtml(manual.headline || '不需要记流程，按当下的问题开始就行')}</h2><p>每个场景都写清去哪、怎么说、会得到什么和什么时候不该用。</p></div><button class="pc-text-action" data-pc-action="view" data-view="modules">先看模块树 →</button></div><div class="pc-manual-jumps">${(manual.quick_jumps || []).map(jump => `<button data-pc-action="jump-manual" data-manual-id="${escapeAttr(jump.scenario_id)}">${escapeHtml(byId[jump.scenario_id]?.title || jump.label)}</button>`).join('')}</div><div class="pc-manual-list">${sections.map((section, index) => manualSectionHtml(section, index)).join('')}</div>${manualExtrasHtml(manual.extras)}</section>`;
}


function manualExtrasHtml(extras) {
  const groups = (extras || []).filter(group => group && (group.say || []).length);
  if (!groups.length) return '';
  const rows = groups.map(group => `<span class="pc-kicker">${escapeHtml(group.label || '')}</span><div class="pc-example-list">${(group.say || []).map(example => `<button data-pc-action="copy-chat" data-copy-recipient="小雪" data-prompt="${escapeAttr(example)}"><b>复制这句话</b><span>${escapeHtml(example)}</span></button>`).join('')}</div>`).join('');
  return `<div class="pc-manual-extras"><p class="pc-manual-extras-lead">说明书之外，这些说法小雪同样认得（和小雪的菜单来自同一份内容，改这里两边一起变）。</p>${rows}</div>`;
}


function manualSectionHtml(section, index) {
  return `<details id="pc-manual-${escapeAttr(section.id)}" class="pc-manual-section"${index === 0 ? ' open' : ''}><summary><span>${String(index + 1).padStart(2, '0')}</span><b>${escapeHtml(section.title)}</b><small>${escapeHtml(section.what)}</small></summary><div class="pc-manual-body"><dl><div><dt>此刻做什么</dt><dd>${escapeHtml(section.what)}</dd></div><div><dt>去哪里</dt><dd>${escapeHtml(section.where)}</dd></div><div><dt>能得到什么</dt><dd>${escapeHtml(section.get)}</dd></div><div><dt>何时不要这样用</dt><dd>${escapeHtml(section.not_for)}</dd></div></dl><div class="pc-example-list">${(section.say || []).map(example => `<button data-pc-action="copy-chat" data-copy-recipient="小雪" data-prompt="${escapeAttr(example)}"><b>复制这句话</b><span>${escapeHtml(example)}</span></button>`).join('')}</div><div class="pc-link-row"><button class="pc-link-chip" data-pc-action="jump-module" data-module-tree-id="${escapeAttr(section.module_tree_id)}">查看对应模块</button><button class="pc-back-link" data-pc-action="scroll-top">返回目录 ↑</button></div></div></details>`;
}


function basketDrawerHtml(basket, selectedIds) {
  const items = basket.items || [];
  const selected = items.filter(item => selectedIds.has(item.id));
  const prompts = selected.length ? `我想聊聊待修改里的这些内容：${selected.map(item => item.module_name).join('、')}` : '我想聊聊待修改。';
  return `<aside id="pc-change-basket" class="pc-drawer" role="region" aria-label="待修改" tabindex="-1"><div class="pc-drawer-head"><div><span class="pc-kicker">待修改</span><h2>${basket.count || 0} 条正在等你和小白聊</h2><p>${basket.focus ? `当前焦点：${escapeHtml(basket.focus.module_name)}` : '还没有当前焦点，挑一条开始就好。'}</p></div><button class="pc-icon-btn" data-pc-action="close-basket" aria-label="关闭待修改">×</button></div><button class="pc-drawer-back" data-pc-action="close-basket">← 返回项目中心</button>
    <div class="pc-drawer-actions"><button class="pc-btn pc-btn-primary" data-pc-action="copy-chat" data-copy-recipient="小白" data-prompt="${escapeAttr(prompts)}">${selected.length ? `复制这 ${selected.length} 条发给小白的话` : '复制发给小白的话'}</button><button class="pc-btn pc-btn-quiet" data-pc-action="new-idea">记录一个还没归类的想法</button></div>
    <div class="pc-idea-box" hidden><input data-pc-new-idea placeholder="一句话记下哪里不顺"><button class="pc-btn pc-btn-primary" data-pc-action="save-idea">加入待修改</button></div>
    <div class="pc-basket-list">${items.length ? items.map(item => basketItemHtml(item, selectedIds)).join('') : emptyHtml('待修改框还是空的', '从任意模块点“加入待修改”，不需要先写完整需求。')}</div>
  </aside>`;
}


function basketItemHtml(item, selectedIds) {
  const snapshot = item.context_snapshot || {};
  const paused = item.status === 'paused';
  return `<article class="pc-basket-item ${selectedIds.has(item.id) ? 'selected' : ''}"><div class="pc-basket-top"><label><input type="checkbox" data-pc-action="select-basket" data-item-id="${escapeAttr(item.id)}" ${selectedIds.has(item.id) ? 'checked' : ''}><span>${escapeHtml(item.module_name)}</span></label>${item.is_focus ? '<span class="pc-focus">当前焦点</span>' : ''}</div>${item.optional_note ? `<p>${escapeHtml(item.optional_note)}</p>` : `<p class="pc-muted">还没补充描述，直接聊感觉也可以。</p>`}<small>${escapeHtml(snapshot.runtime?.reason || snapshot.purpose || '')}</small><div class="pc-basket-actions"><button data-pc-action="basket-focus" data-item-id="${escapeAttr(item.id)}" data-revision="${item.revision}" ${item.is_focus || item.status === 'paused' ? 'disabled' : ''}>设为焦点</button><button data-pc-action="basket-status" data-item-id="${escapeAttr(item.id)}" data-status="${paused ? 'pending' : 'paused'}" data-revision="${item.revision}">${paused ? '继续聊' : '暂放'}</button><button data-pc-action="basket-status" data-item-id="${escapeAttr(item.id)}" data-status="removed" data-revision="${item.revision}">移除</button><button class="pc-why" data-pc-action="why" data-prompt="${escapeAttr(`为什么「${item.module_name}」值得现在聊？请结合当前状态和待修改内容解释。`)}">问问为什么</button></div></article>`;
}


function basketMiniList(items, selectedIds) {
  if (!items.length) return emptyHtml('待修改框还是空的', '从模块卡片点一下就能留下。');
  return `<ul class="pc-mini-list">${items.slice(0, 5).map(item => `<li><span>${item.is_focus ? '当前焦点 · ' : ''}${escapeHtml(item.module_name)}</span><small>${escapeHtml(item.optional_note || '等你和小白聊聊')}</small></li>`).join('')}</ul>`;
}


function requestList(items) {
  if (!items.length) return emptyHtml('还没有正式处理事项', '飞书讨论后，小白会把已确认的目标放到这里。');
  return `<ul class="pc-mini-list">${items.slice(0, 7).map(item => `<li><span><i class="pc-mini-status ${statusTone(item.status)}"></i>${escapeHtml(item.module_name)} · ${escapeHtml(item.status_label || item.status)}</span><small>${escapeHtml(item.user_problem)}</small><button class="pc-why" data-pc-action="why" data-prompt="${escapeAttr(`为什么「${item.module_name}」现在是${item.status_label || item.status}？请结合已确认的目标和下一步用人话说明。`)}">问问为什么</button></li>`).join('')}</ul>`;
}


function deliveryMiniList(items) {
  if (!items.length) return `<p class="pc-muted">还没有可体验的交付；改动进入体验后会在这里出现。</p>`;
  return `<ul class="pc-mini-list">${items.slice(0, 3).map(item => `<li><span><i class="pc-mini-status ${statusTone(item.status)}"></i>${escapeHtml(item.title)}</span><small>${escapeHtml(item.user_visible_change)}</small></li>`).join('')}</ul>`;
}


async function onClick(event, state) {
  const target = event.target.closest('[data-pc-action]');
  if (!target || target.disabled) return;
  const action = target.dataset.pcAction;
  if (action === 'view') {
    state.view = target.dataset.view;
    state.events.emit('project-center:navigate', { view: state.view });
    return;
  }
  if (action === 'jump-book') return openBookChapter(state, target.dataset.bookId);
  if (action === 'jump-manual') return openManualSection(state, target.dataset.manualId);
  if (action === 'jump-module') return jumpToModule(state, target.dataset.moduleTreeId);
  if (action === 'scroll-top') return scrollToTop(state);
  if (action === 'refresh') return refresh(state);
  if (action === 'open-basket') {
    state.lastFocusKey = target.dataset.pcFocusKey || 'header-basket';
    state.drawerOpen = true;
    render(state);
    return;
  }
  if (action === 'close-basket') return closeDrawer(state);
  if (action === 'open-entry') {
    state.events.emit('project-center:open-entry', { page: target.dataset.page });
    return;
  }
  if (action === 'copy-chat') return copyPrompt(state, target.dataset.prompt || '聊聊待修改', target.dataset.copyRecipient || '小雪');
  if (action === 'why') return copyPrompt(state, target.dataset.prompt || '聊聊待修改', '小雪');
  if (action === 'add-basket') return addModuleToBasket(state, target);
  if (action === 'basket-status') return patchBasketItem(state, target, { status: target.dataset.status });
  if (action === 'basket-focus') return patchBasketItem(state, target, { is_focus: true });
  if (action === 'select-basket') {
    toggleSelection(state, target.dataset.itemId, target.checked);
    render(state);
    return;
  }
  if (action === 'new-idea') {
    const box = state.root.querySelector('.pc-idea-box');
    if (box) { box.hidden = false; box.querySelector('input')?.focus(); }
    return;
  }
  if (action === 'save-idea') return saveIdea(state);
  if (action === 'delivery-feedback') return feedbackDelivery(state, target);
}


async function addModuleToBasket(state, target) {
  const moduleId = target.dataset.moduleId;
  const note = state.root.querySelector(`[data-note-module="${CSS.escape(moduleId)}"]`)?.value || '';
  state.lastFocusKey = target.dataset.pcFocusKey || 'header-basket';
  state.drawerOpen = true;
  await mutate(state, () => addToBasket({ module_id: moduleId, optional_note: note, idempotency_key: idempotencyKey() }), '已加入待修改；需要讨论时复制发给小白的话就行。');
}


async function patchBasketItem(state, target, changes) {
  await mutate(state, () => updateBasket(target.dataset.itemId, { ...changes, revision: Number(target.dataset.revision), owner: '钧钧' }), changes.status === 'removed' ? '已从当前待修改里移除。' : changes.status === 'paused' ? '已暂放，以后随时可以继续聊。' : '已设为当前焦点。');
}


async function saveIdea(state) {
  const input = state.root.querySelector('[data-pc-new-idea]');
  const note = input?.value || '';
  await mutate(state, () => addToBasket({ optional_note: note, idempotency_key: idempotencyKey() }), '已记下这个还没归类的想法。');
}


async function feedbackDelivery(state, target) {
  const action = target.dataset.feedback;
  const note = action === 'return_to_basket' ? '体验后仍想换一种做法' : '';
  if (action === 'return_to_basket') {
    state.lastFocusKey = target.dataset.pcFocusKey || 'header-basket';
    state.drawerOpen = true;
  }
  await mutate(state, () => sendDeliveryFeedback(target.dataset.deliveryId, { revision: Number(target.dataset.revision), feedback_action: action, feedback_note: note, owner: '钧钧' }), action === 'archive' ? '已归档这次体验。' : '已放回待修改，等你和小白换一种做法。');
}


async function mutate(state, operation, success) {
  try {
    await operation();
    state.notice = success;
  } catch (error) {
    state.notice = error?.userMessage || error?.message || '这次没有保存成功，请稍后再试。';
  }
  await refresh(state);
}


function copyPrompt(state, prompt, recipient) {
  const text = String(prompt || '').trim();
  if (navigator.clipboard?.writeText) navigator.clipboard.writeText(text).catch(() => {});
  state.notice = `已复制这句话，回飞书发给${recipient}就行。`;
  render(state);
}


function openBookChapter(state, chapterId) {
  if (!chapterId) return;
  state.currentBookChapterId = chapterId;
  state.expandedBookChapters = new Set([chapterId]);
  render(state);
  requestAnimationFrame(() => state.root.querySelector(`#pc-book-${CSS.escape(chapterId)}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
}


function openManualSection(state, sectionId) {
  if (!sectionId) return;
  const section = state.root.querySelector(`#pc-manual-${CSS.escape(sectionId)}`);
  if (!section) return;
  section.open = true;
  section.scrollIntoView({ behavior: 'smooth', block: 'start' });
}


function onBookChapterToggle(event, state) {
  const chapter = event.target;
  if (!(chapter instanceof HTMLDetailsElement) || !chapter.classList.contains('pc-book-chapter')) return;
  const chapterId = chapter.dataset.bookId;
  if (!chapterId) return;
  if (chapter.open) {
    state.expandedBookChapters.add(chapterId);
    state.currentBookChapterId = chapterId;
  } else {
    state.expandedBookChapters.delete(chapterId);
    if (state.currentBookChapterId === chapterId) {
      state.currentBookChapterId = state.root.querySelector('.pc-book-chapter[open]')?.dataset.bookId || '';
    }
  }
  syncBookCurrentState(state);
}


function syncBookCurrentState(state) {
  const current = state.currentBookChapterId;
  state.root.querySelectorAll('.pc-directory-list [data-book-id]').forEach(item => {
    const isCurrent = item.dataset.bookId === current;
    item.classList.toggle('is-current', isCurrent);
    item.toggleAttribute('aria-current', isCurrent);
    item.querySelector('.pc-directory-current')?.classList.toggle('is-visible', isCurrent);
  });
  state.root.querySelectorAll('.pc-book-chapter').forEach(item => {
    const isCurrent = item.dataset.bookId === current;
    item.classList.toggle('is-current', isCurrent);
    item.querySelector('.pc-book-current')?.classList.toggle('is-visible', isCurrent);
  });
}


function revealCurrentTab(state) {
  requestAnimationFrame(() => state.root.querySelector('.pc-tab.active')?.scrollIntoView({ block: 'nearest', inline: 'nearest' }));
}


function dailyNextStep(daily) {
  if (daily?.status === 'ready') return '今天内容已就绪，可按使用说明选择入口。';
  return daily?.reason || '';
}


function bookParagraph(paragraph) {
  return String(paragraph || '').replace('有准备好的内容时可以从日报开始；', '有准备好的内容时会明确说明；');
}


function jumpToModule(state, moduleId) {
  if (!moduleId) return;
  state.view = 'modules';
  state.expandedNodes.add(moduleId);
  render(state);
  requestAnimationFrame(() => state.root.querySelector(`#pc-module-${CSS.escape(moduleId)}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
}


function jumpToElement(state, selector) {
  state.root.querySelector(selector)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}


function scrollToTop(state) {
  state.root.querySelector('.pc-header')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}


function closeDrawer(state) {
  state.drawerOpen = false;
  render(state);
  state.root.querySelector(`[data-pc-focus-key="${CSS.escape(state.lastFocusKey || 'header-basket')}"]`)?.focus();
}


function focusDrawer(state) {
  requestAnimationFrame(() => state.root.querySelector('.pc-drawer')?.focus());
}


function toggleSelection(state, id, checked) {
  if (checked) state.selectedIds.add(id);
  else state.selectedIds.delete(id);
}


function validView(view) {
  return VIEWS.some(([id]) => id === view);
}


function firstError(records) {
  return Object.values(records).map(item => item?.error).find(Boolean) || '';
}


function statusTone(status) {
  return ({ Released: 'healthy', Verified: 'healthy', Implemented: 'degraded', 'In Progress': 'degraded', Planned: 'degraded', Blocked: 'broken', Abandoned: 'disabled' })[status] || 'degraded';
}


function loadingHtml() {
  return `<section class="pc-shell"><div class="pc-loading"><span></span><b>正在整理小雪项目中心…</b><p>项目目标、当前状态和交付进度会分开显示。</p></div></section>`;
}


function unavailableHtml(title, hint) {
  return `<div class="pc-state"><b>${escapeHtml(title)}</b><span>${escapeHtml(hint)}</span></div>`;
}


function emptyHtml(title, hint) {
  return `<div class="pc-empty"><b>${escapeHtml(title)}</b><span>${escapeHtml(hint)}</span></div>`;
}


function idempotencyKey() {
  return globalThis.crypto?.randomUUID?.() || `pc-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}


function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[char]);
}


function escapeAttr(value) {
  return escapeHtml(value).replace(/`/g, '&#96;');
}
