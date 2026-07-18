export function createTeamsView(doc = document) {
  const root = doc.getElementById('card-fundamentals');
  if (!root) throw new Error('队伍资料入口不存在');
  const listeners = [];
  let saveTimer = null;

  function listen(element, eventName, listener) {
    if (!element) return;
    element.addEventListener(eventName, listener);
    listeners.push(() => element.removeEventListener(eventName, listener));
  }

  return {
    bind(handlers) {
      const teamButton = doc.getElementById('sel-team');
      removeLegacyHandler(teamButton, 'onclick');
      listen(teamButton, 'click', (event) => {
        event.preventDefault();
        handlers.onToggleTeams?.();
      });
      doc.querySelectorAll('.scope-btn').forEach((button) => {
        removeLegacyHandler(button, 'onclick');
        listen(button, 'click', (event) => {
          event.preventDefault();
          handlers.onScope?.(button.dataset.scope || 'all');
        });
      });
      const saveButton = doc.getElementById('btn-save');
      removeLegacyHandler(saveButton, 'onclick');
      listen(saveButton, 'click', (event) => {
        event.preventDefault();
        handlers.onSave?.();
      });
      listen(doc.getElementById('profile-toggle'), 'click', () => handlers.onToggleProfile?.());
      listen(doc.querySelector('[data-teams-action="refresh-fundamentals"]'), 'click', () => handlers.onScope?.('all'));
      listen(doc.querySelector('[data-teams-action="refresh-version"]'), 'click', () => handlers.onRefreshVersion?.());
      ['d1-val', 'd2-val', 'd3-val', 'notes-area', 'version-area'].forEach((id) => {
        const input = doc.getElementById(id);
        removeLegacyHandler(input, 'onchange');
        listen(input, 'change', () => handlers.onDirty?.());
      });
      listen(doc, 'click', (event) => {
        const dropdown = doc.getElementById('team-dropdown');
        const button = doc.getElementById('sel-team');
        if (dropdown && button && !dropdown.contains(event.target) && !button.contains(event.target)) {
          dropdown.style.display = 'none';
        }
      });
      listen(doc, 'keydown', (event) => {
        if (event.ctrlKey && event.key.toLowerCase() === 's') {
          event.preventDefault();
          handlers.onSave?.();
        }
        if (event.key === 'Escape') handlers.onEscape?.();
      });
    },
    unbind() {
      listeners.splice(0).forEach((dispose) => dispose());
      if (saveTimer) clearTimeout(saveTimer);
    },
    markStatus(status, message = '') {
      root.dataset.moduleId = 'teams';
      root.dataset.moduleStatus = status;
      root.dataset.moduleMessage = message;
    },
    showOverview() {
      doc.getElementById('content-area')?.classList.remove('team-selected');
      this.updateTopBar('');
    },
    showTeamDetails() {
      doc.getElementById('content-area')?.classList.add('team-selected');
    },
    setTeams(teams, onSelectTeam) {
      renderTeamDropdown(doc, teams, onSelectTeam);
    },
    toggleTeamDropdown(teams, onSelectTeam) {
      const dropdown = doc.getElementById('team-dropdown');
      if (!dropdown) return;
      if (!dropdown.childElementCount) renderTeamDropdown(doc, teams, onSelectTeam);
      dropdown.style.display = dropdown.style.display === 'block' ? 'none' : 'block';
      if (dropdown.style.display === 'block') positionDropdown(doc, dropdown);
    },
    closeTeamDropdown() {
      const dropdown = doc.getElementById('team-dropdown');
      if (dropdown) dropdown.style.display = 'none';
    },
    toggleProfile() {
      const column = doc.getElementById('col-profile');
      const button = doc.getElementById('profile-toggle');
      column?.classList.toggle('collapsed');
      if (button && column) button.textContent = column.classList.contains('collapsed') ? '▶' : '◀';
    },
    applyEditCommand(field, value, rawCommand = '') {
      const fixed = { '操稳': 'd1-val', '血腥': 'd1-val', '运营': 'd2-val' };
      const labels = [1, 2, 3].map((index) => ({
        label: doc.getElementById(`d${index}-label`)?.textContent || '', id: `d${index}-val`,
      }));
      const matched = labels.find((item) => item.label && field.includes(item.label));
      const id = matched?.id || Object.entries(fixed).find(([name]) => field.includes(name))?.[1];
      if (id) {
        const input = doc.getElementById(id);
        if (input) { input.value = value; input.focus(); return true; }
      }
      const notes = doc.getElementById('notes-area');
      if (notes) {
        const text = rawCommand.replace(/^改\s*/, '');
        notes.value += `${notes.value ? '\n' : ''}${text}`;
        notes.focus();
        return true;
      }
      return false;
    },
    updateTopBar(team) {
      setText(doc, 'sel-team-label', team || '选择队伍…');
      setText(doc, 'sel-team-code', team || '');
      const display = team ? 'flex' : 'none';
      const graph = doc.getElementById('btn-graph');
      if (graph) graph.style.display = display;
      this.closeTeamDropdown();
    },
    loadingTeam(team) {
      const profile = doc.getElementById('profile-content');
      if (profile) profile.innerHTML = `<div class="tk-empty">加载 ${escapeHtml(team)} 队伍资料中…</div>`;
    },
    renderProfile(profile, team) { renderProfile(profile, team, doc); },
    render3D(data) { render3D(data, doc); this.setDirty(false); },
    loadingFundamentals(scope) {
      doc.querySelectorAll('.scope-btn').forEach((button) => button.classList.toggle('active', button.dataset.scope === scope));
      const table = doc.getElementById('fundamentals-table');
      if (table) table.innerHTML = '<div class="tk-empty">加载横向基本面中…</div>';
    },
    renderFundamentals(rows, onSelectTeam) { renderFundamentalsTable(rows, onSelectTeam, doc); },
    errorFundamentals() {
      const table = doc.getElementById('fundamentals-table');
      if (table) table.innerHTML = '<div class="tk-empty" style="color:var(--red)">横向基本面加载失败</div>';
    },
    loadingVersion() {
      const list = doc.getElementById('version-understanding-list');
      const meta = doc.getElementById('version-understanding-meta');
      if (list) list.innerHTML = '<div class="tk-empty">加载版本理解中…</div>';
      if (meta) meta.textContent = '同步中…';
    },
    renderVersion(data, team) { renderVersionUnderstanding(data, team, doc); },
    errorVersion() {
      const list = doc.getElementById('version-understanding-list');
      const meta = doc.getElementById('version-understanding-meta');
      if (list) list.innerHTML = '<div class="tk-empty" style="color:var(--red)">版本理解加载失败</div>';
      if (meta) meta.textContent = '接口失败；不影响三维和TK主链路';
    },
    read3D() {
      return {
        dim_1_value: valueOf(doc, 'd1-val'), dim_2_value: valueOf(doc, 'd2-val'),
        dim_3_value: valueOf(doc, 'd3-val'), notes: valueOf(doc, 'notes-area'),
        version_understanding: valueOf(doc, 'version-area'),
      };
    },
    setDirty(dirty) {
      const button = doc.getElementById('btn-save');
      if (!button) return;
      button.classList.toggle('saved', !dirty);
      button.disabled = !dirty;
    },
    saving() { showSaveMessage(doc, '保存中…', 'save-msg show'); },
    saved() {
      this.setDirty(false);
      showSaveMessage(doc, '✅ 已保存', 'save-msg show');
      saveTimer = setTimeout(() => doc.getElementById('save-msg')?.classList.remove('show'), 2000);
    },
    saveFailed() {
      showSaveMessage(doc, '❌ 保存失败', 'save-msg show err');
      const button = doc.getElementById('btn-save');
      if (button) button.disabled = false;
    },
  };
}

export function markTeamsModule(root, status, message = '') {
  if (!root) return;
  root.dataset.moduleStatus = status;
  root.dataset.moduleMessage = message;
}

export function renderFundamentalsTable(rows, onSelectTeam, doc = document) {
  const element = doc.getElementById('fundamentals-table');
  if (!element) return;
  if (!rows.length) {
    element.innerHTML = '<div class="tk-empty">暂无横向基本面数据</div>';
    return;
  }
  const head = '<div class="fund-row fund-head"><span>队伍</span><span>赛区</span><span>赔率</span><span>mu</span><span>σ</span><span>TS</span><span>版本/风格摘要</span><span>首发/关键选手</span><span>资料</span></div>';
  element.innerHTML = head + rows.map((team) => {
    const quality = team.data_quality === '完整' ? 'good' : (team.data_quality === '部分' ? 'mid' : 'low');
    const summary = team.version_summary || team.notes_summary || '暂无摘要，待补画像/TK';
    const number = (value) => Number(value ?? 0).toFixed(1);
    const odds = team.odds ? Number(team.odds).toFixed(1) : '-';
    return `<div class="fund-row" data-team="${escapeAttr(team.short_name)}">
      <span class="fund-team">${escapeHtml(team.short_name)}</span><span>${escapeHtml(team.region || '-')}</span>
      <span>${escapeHtml(odds)}</span><span>${number(team.seed_mu ?? team.mu)}</span>
      <span>${number(team.seed_sigma ?? team.sigma)}</span><span>${number(team.seed_ts ?? team.ts_score)}</span>
      <span>${escapeHtml(summary)}</span><span class="player-cards">${renderPlayerCards(team.players || [], team.players_note)}</span>
      <span class="quality ${quality}">${escapeHtml(team.data_quality || '资料不足')}</span></div>`;
  }).join('');
  element.querySelectorAll('[data-team]').forEach((row) => {
    row.addEventListener('click', () => onSelectTeam?.(row.dataset.team));
  });
}

export function renderVersionUnderstanding(data, fallbackTeam = '', doc = document) {
  const element = doc.getElementById('version-understanding-list');
  const meta = doc.getElementById('version-understanding-meta');
  if (!element) return;
  const blocks = [`<div class="version-card primary"><b>三维版本理解</b><span>${escapeHtml(data.version_understanding || '暂无三维版本理解；保留空值，不自动补写。')}</span>${data.notes_summary ? `<em>战术笔记摘要：${escapeHtml(data.notes_summary)}</em>` : ''}</div>`];
  if (data.tk_items?.length) {
    data.tk_items.forEach((item) => blocks.push(`<div class="version-card"><b>${escapeHtml(item.title || 'TK条目')}</b><span>${escapeHtml(item.summary || '暂无摘要')}</span><em>${escapeHtml([item.date, item.source, item.filename].filter(Boolean).join(' · '))}</em></div>`));
  } else {
    blocks.push('<div class="version-card"><b>TK版本条目</b><span>未找到该队版本理解 TK；不从搜索结果外推。</span></div>');
  }
  element.innerHTML = blocks.join('');
  if (meta) meta.textContent = `${data.team || fallbackTeam} · ${data.boundary || '只读聚合'}${data.updated_at ? ` · 三维更新 ${data.updated_at}` : ''}`;
}

function renderProfile(profile, team, doc) {
  const element = doc.getElementById('profile-content');
  if (!element) return;
  element.innerHTML = profile?.found ? profile.html : `<div style="padding:20px;color:var(--ink-3);text-align:center">
    <div style="font-size:32px;margin-bottom:8px">📄</div>暂无 ${escapeHtml(team)} 的完整画像<br>
    <span style="font-size:12px">（SKILL.md 不存在）</span></div>`;
}

function render3D(data, doc) {
  const values = data || {};
  setText(doc, 'd1-label', values.dim_1_name || '---');
  setValue(doc, 'd1-val', data ? values.dim_1_value || '-' : '-');
  setText(doc, 'd2-label', values.dim_2_name || '---');
  setValue(doc, 'd2-val', data ? values.dim_2_value || '-' : '-');
  setText(doc, 'd3-label', values.dim_3_name || '---');
  setValue(doc, 'd3-val', data ? values.dim_3_value || '-' : '-');
  setValue(doc, 'notes-area', values.notes || '');
  setValue(doc, 'version-area', values.version_understanding || '');
  setText(doc, 'dim-updated', values.updated_at ? ` · 更新于 ${values.updated_at}` : '');
}

function renderTeamDropdown(doc, teams, onSelectTeam) {
  const dropdown = doc.getElementById('team-dropdown');
  if (!dropdown) return;
  const groups = [['LPL', '--pink-light'], ['LCK', '--blue-light']];
  dropdown.innerHTML = groups.map(([region], index) => {
    const border = index ? 'border-top:1px solid var(--line);' : '';
    const items = teams.filter((team) => team.region === region).map((team) => `
      <div class="dd-item" data-team="${escapeAttr(team.short_name)}" style="padding:8px 16px;cursor:pointer;font-size:14px;font-weight:600;transition:background 100ms">
        <span style="font-family:var(--mono);font-size:12px;color:var(--ink-2);margin-right:8px">${escapeHtml(team.short_name)}</span>${escapeHtml(team.name)}
      </div>`).join('');
    return `<div style="padding:8px 16px;font-size:11px;color:var(--ink-3);font-weight:600;${border}">${region}</div>${items}`;
  }).join('');
  dropdown.querySelectorAll('[data-team]').forEach((item) => {
    item.addEventListener('mouseenter', () => { item.style.background = 'var(--pink-light)'; });
    item.addEventListener('mouseleave', () => { item.style.background = ''; });
    item.addEventListener('click', () => {
      dropdown.style.display = 'none';
      onSelectTeam?.(item.dataset.team);
    });
  });
}

function positionDropdown(doc, dropdown) {
  const button = doc.getElementById('sel-team');
  if (!button) return;
  const rect = button.getBoundingClientRect();
  dropdown.style.top = `${rect.bottom + 4}px`;
  dropdown.style.left = `${rect.left}px`;
}

function renderPlayerCards(players, note) {
  if (!players.length) return `<span class="player-card gap">${escapeHtml(note || '资料缺口/暂无数据')}</span>`;
  return players.map((player) => `<span class="player-card" title="${escapeAttr(player.status || '资料缺口')}"><b>${escapeHtml(player.role || '位置暂无数据')}</b>${escapeHtml(player.name || '暂无数据')}</span>`).join('');
}

function showSaveMessage(doc, text, className) {
  const message = doc.getElementById('save-msg');
  if (!message) return;
  message.textContent = text;
  message.className = className;
}

function setText(doc, id, value) { const element = doc.getElementById(id); if (element) element.textContent = value; }
function setValue(doc, id, value) { const element = doc.getElementById(id); if (element) element.value = value; }
function valueOf(doc, id) { return doc.getElementById(id)?.value || ''; }
function removeLegacyHandler(element, attribute) {
  if (!element) return;
  element.removeAttribute(attribute);
  element[attribute] = null;
}
function escapeHtml(value) { return String(value || '').replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]); }
function escapeAttr(value) { return escapeHtml(value); }
