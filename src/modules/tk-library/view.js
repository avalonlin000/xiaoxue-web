import { groupLibraryItems, libraryPreview, quickEntryView } from './service.js';

export function createTKLibraryView({ root, readerRoot, editorRoot, quickSearchRoot }) {
  if (!root) throw new Error('TK资料库入口不存在');
  const library = elements(root, {
    query: 'tk-library-query', team: 'tk-library-team', month: 'tk-library-month',
    summary: 'tk-library-summary', latest: 'tk-library-latest',
    results: 'tk-library-results', more: 'tk-library-more',
  });
  const reader = elements(readerRoot, {
    heading: 'tk-reader-heading', date: 'tk-reader-date', content: 'tk-reader-content',
  });
  const editor = elements(editorRoot, {
    title: 'tk-editor-title', filename: 'tk-editor-filename', content: 'tk-editor-content',
    tags: 'tk-editor-tags', team: 'tk-editor-team', message: 'tk-editor-msg', save: 'tk-editor-save',
  });
  const quick = elements(quickSearchRoot, { query: 'tk-search', results: 'tk-results' });

  return {
    roots: { root, readerRoot, editorRoot, quickSearchRoot },
    populateTeams(teams = []) {
      if (!library.team || library.team.options.length > 1) return;
      teams.forEach((team) => {
        const option = document.createElement('option');
        option.value = team.short_name;
        option.textContent = `${team.short_name} · ${team.name}`;
        library.team.appendChild(option);
      });
    },
    readFilters() {
      return {
        query: library.query?.value.trim() || '', team: library.team?.value || '',
        month: library.month?.value || '',
      };
    },
    setPeriod(period) {
      root.querySelectorAll('.tk-period-button').forEach((button) => {
        button.classList.toggle('active', button.dataset.period === period);
      });
      if (period === 'month' && library.month && !library.month.value) {
        library.month.value = new Date().toISOString().slice(0, 7);
      }
    },
    renderLibraryLoading(reset) {
      if (reset && library.results) library.results.innerHTML = '<div class="tk-empty">读取中…</div>';
      if (library.summary) library.summary.textContent = '正在整理TK内容…';
      if (library.more) library.more.disabled = true;
    },
    renderLibrary(state, latestDate, summary) {
      if (library.latest) library.latest.textContent = latestDate || '暂无日期';
      if (library.summary) library.summary.textContent = summary;
      if (library.more) {
        library.more.style.display = state.hasMore ? '' : 'none';
        library.more.disabled = false;
      }
      if (!library.results) return;
      if (!state.results.length) {
        library.results.innerHTML = '<div class="tk-empty">这个时间段没有找到TK内容，可以切换时间、队伍或关键词。</div>';
        return;
      }
      library.results.innerHTML = groupLibraryItems(state.results).map(({ date, entries }) => {
        const cards = entries.map(({ item, index }) => {
          const chips = [item.team, item.player, ...(item.tags || [])]
            .filter(Boolean).filter((value, position, values) => values.indexOf(value) === position)
            .slice(0, 4).map((value) => `<span class="tk-context-chip">${escapeHtml(value)}</span>`).join('');
          return `<article class="tk-library-card">
            <time class="tk-library-date" datetime="${escapeAttr(item.date || '')}">${escapeHtml(item.date || '日期不明')}</time>
            <div class="tk-library-main"><h3>${escapeHtml(item.concept || '未命名TK')}</h3>
              <p>${escapeHtml(libraryPreview(item))}</p>${chips ? `<div class="tk-library-context">${chips}</div>` : ''}</div>
            <button class="tk-library-open" data-tk-action="open-reader" data-index="${index}">阅读全文</button>
          </article>`;
        }).join('');
        return `<section class="tk-date-group"><h2 class="tk-date-heading">${escapeHtml(date)} <span>${entries.length} 条</span></h2>${cards}</section>`;
      }).join('');
    },
    renderLibraryError() {
      if (library.results) library.results.innerHTML = '<div class="tk-empty" style="color:var(--red)">TK内容读取失败，请稍后刷新</div>';
      if (library.summary) library.summary.textContent = '读取失败，没有用旧内容代替';
      if (library.more) library.more.style.display = 'none';
    },
    openReader(item) {
      readerRoot?.classList.add('open');
      if (reader.heading) reader.heading.textContent = item.concept || 'TK正文';
      if (reader.date) reader.date.textContent = item.date || '日期不明';
      if (reader.content) reader.content.innerHTML = '<div class="tk-empty">正在读取完整内容…</div>';
    },
    showReader(data, fallback) {
      if (reader.heading) reader.heading.textContent = data.concept || fallback.concept || 'TK正文';
      if (reader.date) reader.date.textContent = data.date || fallback.date || '日期不明';
      if (reader.content) reader.content.innerHTML = renderTKReaderContent(data.content || '');
    },
    showReaderError() {
      if (reader.content) reader.content.innerHTML = '<div class="tk-empty" style="color:var(--red)">完整内容读取失败，请关闭后重试。</div>';
    },
    closeReader() { readerRoot?.classList.remove('open'); },
    readQuickQuery: () => quick.query?.value.trim() || '',
    setQuickQuery(value) { if (quick.query) quick.query.value = value || ''; },
    renderQuickLoading() { if (quick.results) quick.results.innerHTML = '<div class="tk-empty">搜索中…</div>'; },
    renderQuickError() { if (quick.results) quick.results.innerHTML = '<div class="tk-empty" style="color:var(--red)">搜索失败</div>'; },
    renderQuickResults(results = []) {
      if (!quick.results) return;
      if (!results.length) {
        quick.results.innerHTML = '<div class="tk-empty">未找到相关 TK</div>';
        return;
      }
      quick.results.innerHTML = results.map((raw, index) => {
        const entry = quickEntryView(raw);
        const tags = (entry.tags || []).map((tag) => `<span class="tk-tag">${escapeHtml(tag)}</span>`).join(' ');
        const priority = entry.isTradingTK ? '<span class="tk-tag" style="background:var(--orange);color:#fff">交易 TK 优先</span>' : '';
        return `<div class="tk-item${entry.isShell ? ' tk-empty-shell' : ''}${entry.isTradingTK ? ' tk-trading-priority' : ''}" data-tk-index="${index}">
          <button class="tk-title" data-tk-action="toggle-quick" data-index="${index}"><span class="tk-expand-icon">▸</span><span>${escapeHtml(entry.concept || entry.id)}</span></button>
          <div class="tk-preview">${escapeHtml(entry.preview)}${entry.hasMore ? '…' : ''}</div>
          <div class="tk-full">${escapeHtml(entry.content)}</div>
          <div class="tk-meta"><span>${escapeHtml(entry.date || '')}</span><span>${escapeHtml(entry.source || '')}</span>${entry.isShell ? '<span style="color:var(--ink-3)">⚠ 内容较少</span>' : ''}</div>
          ${priority || tags ? `<div style="margin-top:4px">${priority}${tags ? ` ${tags}` : ''}</div>` : ''}
          <div class="tk-actions"><button data-tk-action="edit-quick" data-index="${index}">✏️ 编辑</button><button class="danger" data-tk-action="delete-quick" data-index="${index}">🗑 删除</button></div>
        </div>`;
      }).join('');
    },
    toggleQuick(index) { quick.results?.querySelector(`[data-tk-index="${index}"]`)?.classList.toggle('expanded'); },
    openEditor(draft, message = '') {
      editorRoot?.classList.add('open');
      if (editor.title) editor.title.textContent = draft.filename ? '编辑 TK' : '新建 TK';
      if (editor.filename) editor.filename.value = draft.filename || '';
      if (editor.content) editor.content.value = draft.content || '';
      if (editor.tags) editor.tags.value = draft.tags || '';
      if (editor.team) editor.team.value = draft.team || '';
      if (editor.message) editor.message.textContent = message;
      setTimeout(() => editor.content?.focus(), 100);
    },
    closeEditor() { editorRoot?.classList.remove('open'); },
    readEditor() {
      return { filename: editor.filename?.value || '', content: editor.content?.value || '', tags: editor.tags?.value || '', team: editor.team?.value || '' };
    },
    setEditorMessage(message) { if (editor.message) editor.message.textContent = message || ''; },
    bind(actions) {
      const disposers = [];
      const on = (element, type, handler) => {
        if (!element) return;
        element.addEventListener(type, handler);
        disposers.push(() => element.removeEventListener(type, handler));
      };
      on(root, 'click', (event) => handleAction(event, actions));
      on(root, 'keydown', (event) => { if (event.target === library.query && event.key === 'Enter') actions.applyFilters(); });
      on(library.team, 'change', () => actions.applyFilters());
      on(library.month, 'change', () => actions.setPeriod('month'));
      on(readerRoot, 'click', (event) => {
        if (event.target === readerRoot || event.target.closest('[data-tk-action="close-reader"]')) actions.closeReader();
      });
      on(editorRoot, 'click', (event) => {
        if (event.target === editorRoot || event.target.closest('[data-tk-action="close-editor"]')) actions.closeEditor();
        if (event.target.closest('[data-tk-action="save-editor"]')) actions.saveEditor();
      });
      on(quickSearchRoot, 'click', (event) => handleAction(event, actions));
      on(quickSearchRoot, 'keydown', (event) => { if (event.target === quick.query && event.key === 'Enter') actions.quickSearch(); });
      return () => disposers.splice(0).forEach((dispose) => dispose());
    },
  };
}

export function renderTKReaderContent(raw) {
  const normalized = String(raw || '').replace(/\s*(【[^】]{1,16}】)\s*/g, '\n$1\n').trim();
  if (!normalized) return '<div class="tk-empty">这条 TK 没有可读正文。</div>';
  const blocks = [];
  let sectionOpen = false;
  let skipSection = false;
  normalized.split(/\n+/).map((line) => line.trim()).filter(Boolean).forEach((line) => {
    const section = line.match(/^【([^】]+)】$/);
    if (section) {
      if (sectionOpen) blocks.push('</section>');
      skipSection = ['来源', '标签', '文件'].includes(section[1]);
      sectionOpen = !skipSection;
      if (!skipSection) blocks.push(`<section><h3>${escapeHtml(section[1])}</h3>`);
    } else if (!skipSection && !/^(来源|标签|文件)[:：]/.test(line)) {
      const heading = line.match(/^#{1,4}\s+(.+)$/);
      if (heading) blocks.push(`<h4>${escapeHtml(heading[1])}</h4>`);
      else if (/^[-*•]\s+/.test(line)) blocks.push(`<ul><li>${escapeHtml(line.replace(/^[-*•]\s+/, ''))}</li></ul>`);
      else blocks.push(`<p>${escapeHtml(line)}</p>`);
    }
  });
  if (sectionOpen) blocks.push('</section>');
  return blocks.join('');
}

function handleAction(event, actions) {
  const target = event.target.closest('[data-tk-action]');
  if (!target) return;
  const index = Number(target.dataset.index);
  const action = target.dataset.tkAction;
  if (action === 'apply-filters') actions.applyFilters();
  if (action === 'load-more') actions.loadMore();
  if (action === 'open-reader') actions.openReader(index);
  if (action === 'new-entry') actions.openEditor();
  if (action === 'quick-search') actions.quickSearch();
  if (action === 'toggle-quick') actions.toggleQuick(index);
  if (action === 'edit-quick') actions.editQuick(index);
  if (action === 'delete-quick') actions.deleteQuick(index);
  if (action?.startsWith('period-')) actions.setPeriod(action.slice(7));
}

function elements(root, mapping) {
  return Object.fromEntries(Object.entries(mapping).map(([key, id]) => [key, root?.querySelector(`#${id}`) || null]));
}

function escapeHtml(value) {
  return String(value || '').replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]);
}

function escapeAttr(value) { return escapeHtml(value); }
