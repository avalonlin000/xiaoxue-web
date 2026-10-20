import { groupLibraryItems, libraryPreview, libraryTitle, quickEntryView } from './service.js';

const QUICK_VIEW_LIMIT = 2;

export function createTKLibraryView({ root, readerRoot, quickReaderRoot, editorRoot, quickSearchRoot }) {
  if (!root) throw new Error('TK资料库入口不存在');
  const library = elements(root, {
    query: 'tk-library-query', team: 'tk-library-team', month: 'tk-library-month',
    summary: 'tk-library-summary', latest: 'tk-library-latest',
    results: 'tk-library-results', more: 'tk-library-more',
  });
  const reader = elements(readerRoot, {
    heading: 'tk-reader-heading', date: 'tk-reader-date', content: 'tk-reader-content',
  });
  const quickReader = elements(quickReaderRoot, {
    heading: 'tk-quick-reader-heading', date: 'tk-quick-reader-date', content: 'tk-quick-reader-content',
  });
  const quickList = quickSearchRoot?.querySelector('#tk-quick-list') || null;
  const editor = elements(editorRoot, {
    title: 'tk-editor-title', filename: 'tk-editor-filename', content: 'tk-editor-content',
    tags: 'tk-editor-tags', team: 'tk-editor-team', message: 'tk-editor-msg', save: 'tk-editor-save',
  });
  const quick = elements(quickSearchRoot, { query: 'tk-search', results: 'tk-results', count: 'tk-quick-count', toggle: 'tk-quick-toggle' });

  return {
    roots: { root, readerRoot, quickReaderRoot, editorRoot, quickSearchRoot },
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
      if (reset && library.results) library.results.innerHTML = '<div class="tk-empty">正在读取资料…</div>';
      if (library.summary) library.summary.textContent = '正在读取资料…';
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
        library.results.innerHTML = '<div class="tk-empty">这个筛选下还没有资料。试试调整时间、队伍或关键词。</div>';
        return;
      }
      library.results.innerHTML = groupLibraryItems(state.results).map(({ date, entries }) => {
        const cards = entries.map(({ item, index }) => {
          const metadata = [item.team, item.player, ...(item.tags || [])]
            .filter(Boolean).filter((value, position, values) => values.indexOf(value) === position)
            .slice(0, 4).map((value) => escapeHtml(value)).join(' · ');
          return `<article class="tk-library-card">
            <button class="tk-library-note" data-tk-action="open-reader" data-index="${index}">
              <time class="tk-library-date" datetime="${escapeAttr(item.date || '')}">${escapeHtml(item.date || '日期不明')}</time>
              <span class="tk-library-note-body"><strong class="tk-library-note-title">${escapeHtml(libraryTitle(item))}</strong>
                <span class="tk-library-note-preview">${escapeHtml(libraryPreview(item))}</span>${metadata ? `<span class="tk-library-note-meta">${metadata}</span>` : ''}</span>
              <span class="tk-library-note-arrow" aria-hidden="true">阅读</span>
            </button>
          </article>`;
        }).join('');
        return `<section class="tk-date-group"><h2 class="tk-date-heading">${escapeHtml(date)} <span>${entries.length} 条</span></h2>${cards}</section>`;
      }).join('');
    },
    renderLibraryError() {
      if (library.results) library.results.innerHTML = '<div class="tk-empty" style="color:var(--red)">暂时没能读到资料，请稍后再试。</div>';
      if (library.summary) library.summary.textContent = '暂时无法读取资料';
      if (library.more) library.more.style.display = 'none';
    },
    openReader(item) {
      root.classList.add('tk-reader-open');
      readerRoot?.classList.add('open');
      root.querySelectorAll('.tk-library-note').forEach((note) => {
        note.classList.toggle('is-active', Number(note.dataset.index) === Number(item.index));
      });
      if (reader.heading) reader.heading.textContent = libraryTitle(item) || '资料正文';
      if (reader.date) reader.date.textContent = item.date || '日期不明';
      if (reader.content) reader.content.innerHTML = '<div class="tk-empty">正在打开资料…</div>';
      setTimeout(() => reader.heading?.focus(), 0);
    },
    showReader(data, fallback) {
      if (reader.heading) reader.heading.textContent = libraryTitle({ ...fallback, ...data, preview: data.content || fallback.preview || '' }) || '资料正文';
      if (reader.date) reader.date.textContent = data.date || fallback.date || '日期不明';
      if (reader.content) reader.content.innerHTML = renderTKReaderContent(data.content || '');
    },
    showReaderError() {
      if (reader.content) reader.content.innerHTML = '<div class="tk-empty" style="color:var(--red)">暂时没能打开这条资料，请返回列表后重试。</div>';
    },
    openQuickReader(item) {
      if (!quickReaderRoot) return this.openReader(item);
      quickSearchRoot?.classList.add('is-reading');
      quickReaderRoot.classList.add('open');
      quickList?.classList.add('is-reader-open');
      if (quickReader.heading) quickReader.heading.textContent = item.concept || '资料全文';
      if (quickReader.date) quickReader.date.textContent = item.date || '日期不明';
      if (quickReader.content) quickReader.content.innerHTML = '<div class="tk-empty">正在读取完整内容…</div>';
    },
    showQuickReader(data, fallback) {
      if (!quickReaderRoot) return this.showReader(data, fallback);
      if (quickReader.heading) quickReader.heading.textContent = data.concept || fallback.concept || '资料全文';
      if (quickReader.date) quickReader.date.textContent = data.date || fallback.date || '日期不明';
      if (quickReader.content) quickReader.content.innerHTML = renderTKReaderContent(data.content || '');
    },
    showQuickReaderError() {
      if (!quickReaderRoot) return this.showReaderError();
      if (quickReader.content) quickReader.content.innerHTML = '<div class="tk-empty" style="color:var(--red)">完整内容读取失败，请返回列表后重试。</div>';
    },
    closeQuickReader() {
      quickSearchRoot?.classList.remove('is-reading');
      quickReaderRoot?.classList.remove('open');
      quickList?.classList.remove('is-reader-open');
    },
    closeReader() {
      root.classList.remove('tk-reader-open');
      readerRoot?.classList.remove('open');
      root.querySelectorAll('.tk-library-note.is-active').forEach((note) => note.classList.remove('is-active'));
      this.closeQuickReader();
    },
    readQuickQuery: () => quick.query?.value.trim() || '',
    setQuickQuery(value) { if (quick.query) quick.query.value = value || ''; },
    renderQuickLoading() {
      quickSearchRoot?.classList.remove('is-expanded');
      if (quick.count) quick.count.textContent = '正在读取…';
      if (quick.toggle) { quick.toggle.disabled = true; quick.toggle.textContent = '展开全部'; quick.toggle.setAttribute('aria-expanded', 'false'); }
      if (quick.results) quick.results.innerHTML = '<div class="tk-empty">正在读取当前队伍资料…</div>';
    },
    renderQuickError() {
      quickSearchRoot?.classList.remove('is-expanded');
      if (quick.count) quick.count.textContent = '暂时无法读取';
      if (quick.toggle) { quick.toggle.disabled = true; quick.toggle.textContent = '展开全部'; quick.toggle.setAttribute('aria-expanded', 'false'); }
      if (quick.results) quick.results.innerHTML = '<div class="tk-empty" style="color:var(--red)">暂时没能读取当前队伍资料，请稍后再试。</div>';
    },
    renderQuickResults(results = [], { total = results.length, expanded = false } = {}) {
      if (!quick.results) return;
      const readableEntries = results.map((raw, index) => ({
        entry: quickEntryView({ ...raw, content: raw.content || raw.preview || '' }), index,
      })).filter(({ entry }) => !entry.isShell);
      const hasMore = readableEntries.length > QUICK_VIEW_LIMIT;
      quickSearchRoot?.classList.toggle('is-expanded', expanded && hasMore);
      if (quick.count) quick.count.textContent = `${Math.max(0, Number(total) || 0)} 条资料`;
      if (quick.toggle) {
        quick.toggle.disabled = !hasMore;
        quick.toggle.textContent = expanded && hasMore ? '收起' : '展开全部';
        quick.toggle.setAttribute('aria-expanded', String(expanded && hasMore));
      }
      if (!readableEntries.length) {
        quick.results.innerHTML = '<div class="tk-empty">当前队伍还没有可快速阅读的资料。</div>';
        return;
      }
      const visibleEntries = expanded && hasMore ? readableEntries : readableEntries.slice(0, QUICK_VIEW_LIMIT);
      quick.results.innerHTML = visibleEntries.map(({ entry, index }) => {
        const tags = (entry.tags || []).slice(0, 4).map((tag) => `<span class="tk-tag">${escapeHtml(tag)}</span>`).join('');
        const priority = entry.isTradingTK ? '<span class="tk-tag" style="background:var(--orange);color:#fff">交易 TK 优先</span>' : '';
        return `<article class="tk-item${entry.isTradingTK ? ' tk-trading-priority' : ''}" data-tk-index="${index}">
          <button class="tk-title" data-tk-action="open-quick-reader" data-index="${index}"><span>${escapeHtml(entry.concept || entry.id)}</span></button>
          <div class="tk-preview">${escapeHtml(entry.preview)}${entry.hasMore ? '…' : ''}</div>
          <div class="tk-meta"><time>${escapeHtml(entry.date || '日期不明')}</time>${entry.isShell ? '<span>内容较少</span>' : ''}</div>
          <div class="tk-item-footer">
            ${priority || tags ? `<div class="tk-tag-list">${priority}${tags}</div>` : ''}
          </div>
        </article>`;
      }).join('');
    },
    openEditor(draft, message = '') {
      editorRoot?.classList.add('open');
      if (editor.title) editor.title.textContent = draft.filename ? '编辑资料' : '新建资料';
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
      on(quickReaderRoot, 'click', (event) => {
        if (event.target.closest('[data-tk-action="close-quick-reader"]')) actions.closeQuickReader();
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
  const normalized = String(raw || '')
    .replace(/^\s*---[\s\S]*?---\s*/m, '')
    .replace(/```ya?ml\s*[\s\S]*?```/gi, '')
    .replace(/\s*(【[^】]{1,16}】)\s*/g, '\n$1\n')
    .trim();
  if (!normalized) return '<div class="tk-empty">这条 TK 没有可读正文。</div>';
  const blocks = [];
  let sectionOpen = false;
  let skipSection = false;
  let listOpen = false;
  const closeList = () => {
    if (listOpen) blocks.push('</ul>');
    listOpen = false;
  };
  normalized.split('\n').map((line) => line.trim()).forEach((line) => {
    if (!line) {
      closeList();
      return;
    }
    const section = line.match(/^【([^】]+)】$/);
    if (section) {
      closeList();
      if (sectionOpen) blocks.push('</section>');
      skipSection = ['来源', '标签', '文件'].includes(section[1]);
      sectionOpen = !skipSection;
      if (!skipSection) blocks.push(`<section><h3>${escapeHtml(section[1])}</h3>`);
    } else if (!skipSection && !/^(来源|标签|文件)[:：]/.test(line)) {
      const heading = line.match(/^(#{2,4})\s+(.+)$/);
      const listItem = line.match(/^[-*•]\s+(.+)$/);
      const quote = line.match(/^>\s*(.+)$/);
      if (heading) {
        closeList();
        const level = Math.min(4, heading[1].length);
        blocks.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
      } else if (listItem) {
        if (!listOpen) blocks.push('<ul>');
        listOpen = true;
        blocks.push(`<li>${renderInlineMarkdown(listItem[1])}</li>`);
      } else if (quote) {
        closeList();
        blocks.push(`<blockquote>${renderInlineMarkdown(quote[1])}</blockquote>`);
      } else {
        closeList();
        blocks.push(`<p>${renderInlineMarkdown(line)}</p>`);
      }
    }
  });
  closeList();
  if (sectionOpen) blocks.push('</section>');
  return blocks.join('');
}

function renderInlineMarkdown(value) {
  return escapeHtml(value).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
}

function handleAction(event, actions) {
  const target = event.target.closest('[data-tk-action]');
  if (!target) return;
  const index = Number(target.dataset.index);
  const action = target.dataset.tkAction;
  if (action === 'apply-filters') actions.applyFilters();
  if (action === 'load-more') actions.loadMore();
  if (action === 'open-reader') actions.openReader(index);
  if (action === 'close-reader') actions.closeReader();
  if (action === 'edit-reader') actions.editReader();
  if (action === 'delete-reader') actions.deleteReader();
  if (action === 'new-entry') actions.openEditor();
  if (action === 'quick-search') actions.quickSearch();
  if (action === 'toggle-quick-list') actions.toggleQuickList();
  if (action === 'go-to-library') actions.goToLibrary();
  if (action === 'open-quick-reader') actions.openQuickReader(index);
  if (action === 'close-quick-reader') actions.closeQuickReader();
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
