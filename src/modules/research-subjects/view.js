export function createResearchSubjectsView(root) {
  if (!root) throw new Error('主体档案入口不存在');
  const body = root.querySelector('.card-body');
  body.innerHTML = `
    <div class="research-intro">从一个队伍或品种开始。资料保留来源和时间；小雪整理内容不会覆盖你的原始笔记。</div>
    <div class="research-form">
      <input id="research-domain" value="lol_team" placeholder="类别，如 lol_team / stock">
      <input id="research-key" placeholder="主体标识，如 AAPL / BLG">
      <input id="research-name" placeholder="主体名称，如 Apple / BLG">
      <button class="btn-save" data-research-action="open">打开档案</button>
    </div>
    <section class="research-directory"><div class="research-directory-head"><b>已有档案</b><button class="btn-ghost" data-research-action="list">刷新目录</button></div><div id="research-subject-list" class="research-subject-list"><div class="tk-empty">还没有主体档案。</div></div></section>
    <div class="research-message" id="research-message"></div>
    <section id="research-dossier" class="research-dossier"><div class="tk-empty">先打开一个主体档案。</div></section>
  `;
  const message = root.querySelector('#research-message');
  const dossier = root.querySelector('#research-dossier');
  return {
    values() {
      return {
        domain: root.querySelector('#research-domain')?.value || '',
        subject_key: root.querySelector('#research-key')?.value || '',
        name: root.querySelector('#research-name')?.value || '',
      };
    },
    materialValues() {
      return {
        kind: root.querySelector('#research-material-kind')?.value || 'research',
        source_name: root.querySelector('#research-material-source')?.value || '',
        source_url: root.querySelector('#research-material-url')?.value || '',
        content: root.querySelector('#research-material-content')?.value || '',
        captured_at: new Date().toISOString(),
        event_id: selectedEventId(root.querySelector('#research-material-event')?.value),
      };
    },
    noteValues() {
      return {
        content: root.querySelector('#research-note-content')?.value || '',
        kind: 'user_note',
        event_id: selectedEventId(root.querySelector('#research-note-event')?.value),
      };
    },
    eventValues() {
      return {
        kind: root.querySelector('#research-event-kind')?.value || 'event',
        title: root.querySelector('#research-event-title')?.value || '',
        occurred_at: root.querySelector('#research-event-time')?.value || new Date().toISOString(),
        details: root.querySelector('#research-event-details')?.value || '',
      };
    },
    render(payload) {
      const subject = payload?.subject;
      if (!subject) return;
      dossier.innerHTML = `
        <header class="research-subject-head"><b>${escapeHtml(subject.name)}</b><span>${escapeHtml(subject.domain)} · ${escapeHtml(subject.subject_key)}</span></header>
        <div class="research-columns">
          <section class="research-panel">
            <h3>添加事件</h3>
            <input id="research-event-kind" value="event" placeholder="事件类型，如比赛 / 财报">
            <input id="research-event-title" placeholder="事件名称，如 BLG vs T1">
            <input id="research-event-time" placeholder="事件时间（可选）">
            <textarea id="research-event-details" placeholder="只补充这件事的背景；不替代资料或你的判断。"></textarea>
            <button class="btn-save" data-research-action="event">保存事件</button>
          </section>
          <section class="research-panel">
            <h3>添加原始资料</h3>
            ${eventSelect('research-material-event', payload.events || [])}
            <input id="research-material-kind" value="research" placeholder="资料类型">
            <input id="research-material-source" placeholder="来源名称">
            <input id="research-material-url" placeholder="来源链接（可选）">
            <textarea id="research-material-content" placeholder="粘贴资料原文或自己的资料摘录；系统会保留来源与时间。"></textarea>
            <button class="btn-save" data-research-action="material">保存资料</button>
          </section>
          <section class="research-panel">
            <h3>我的笔记</h3>
            ${eventSelect('research-note-event', payload.events || [])}
            <textarea id="research-note-content" placeholder="写下你现在的理解、疑问或以后要验证的事。"></textarea>
            <button class="btn-save" data-research-action="note">保存我的笔记</button>
          </section>
        </div>
        <section class="research-panel research-digests"><h3>小雪整理</h3>${renderDigests(payload.organized_digests || [])}</section>
        <section class="research-panel research-timeline"><h3>时间线</h3>${renderTimeline(payload.timeline || [])}</section>
      `;
    },
    renderDirectory(subjects) {
      const list = root.querySelector('#research-subject-list');
      if (!list) return;
      if (!subjects.length) {
        list.innerHTML = '<div class="tk-empty">还没有匹配的主体档案。</div>';
        return;
      }
      list.innerHTML = subjects.map(subject => `
        <button class="research-subject-item" data-research-subject-id="${subject.id}">
          <b>${escapeHtml(subject.name)}</b><span>${escapeHtml(subject.domain)} · ${escapeHtml(subject.subject_key)}</span>
        </button>
      `).join('');
    },
    message(text = '', kind = '') {
      message.textContent = text;
      message.dataset.kind = kind;
    },
    bind(actions) {
      const listener = event => {
        const button = event.target.closest('[data-research-action]');
        if (button) {
          const action = button.dataset.researchAction;
          if (action === 'open') actions.open();
          if (action === 'list') actions.list();
          if (action === 'event') actions.addEvent();
          if (action === 'material') actions.addMaterial();
          if (action === 'note') actions.addNote();
          return;
        }
        const subject = event.target.closest('[data-research-subject-id]');
        if (subject) actions.openExisting(Number(subject.dataset.researchSubjectId));
      };
      root.addEventListener('click', listener);
      return () => root.removeEventListener('click', listener);
    },
  };
}

function eventSelect(id, events) {
  const options = events.map(event => `<option value="${event.id}">${escapeHtml(event.title)}</option>`).join('');
  return `<select id="${id}"><option value="">不关联具体事件</option>${options}</select>`;
}

function selectedEventId(value) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

function renderTimeline(entries) {
  if (!entries.length) return '<div class="tk-empty">还没有资料或笔记。</div>';
  return entries.map(entry => {
    const item = entry.item || {};
    const label = { event: '事件', material: '资料', note: '我的笔记', digest: '小雪整理' }[entry.entry_type] || entry.entry_type;
    const text = item.content || item.title || '';
    const source = item.source_name || item.kind || '';
    return `<article class="research-entry"><b>${escapeHtml(label)}</b><span>${escapeHtml(text)}</span><em>${escapeHtml(source)} · ${escapeHtml(entry.at)}</em></article>`;
  }).join('');
}

function renderDigests(entries) {
  if (!entries.length) return '<div class="tk-empty">小雪尚未整理资料。</div>';
  return entries.map(entry => `<article class="research-entry"><b>${escapeHtml(entry.kind)}</b><span>${escapeHtml(entry.content)}</span><em>依据资料 #${entry.source_material_ids.join('、#')}</em></article>`).join('');
}

function escapeHtml(value) {
  return String(value || '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[character]);
}
