export function createTeamsView(doc = document) {
  const root = doc.getElementById('card-fundamentals');
  if (!root) throw new Error('队伍资料入口不存在');
  const listeners = [];

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
      listen(doc.getElementById('profile-toggle'), 'click', () => handlers.onToggleProfile?.());
      listen(doc.querySelector('[data-teams-action="refresh-fundamentals"]'), 'click', () => handlers.onScope?.('lpl'));
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
        }
        if (event.key === 'Escape') handlers.onEscape?.();
      });
    },
    unbind() {
      listeners.splice(0).forEach((dispose) => dispose());
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
    loadingFundamentals(scope) {
      doc.querySelectorAll('.scope-btn').forEach((button) => button.classList.toggle('active', button.dataset.scope === scope));
      const table = doc.getElementById('fundamentals-table');
      if (table) table.innerHTML = '<div class="tk-empty">加载队伍资料中…</div>';
    },
    renderFundamentals(rows, onSelectTeam) { renderFundamentalsTable(rows, onSelectTeam, doc); },
    errorFundamentals() {
      const table = doc.getElementById('fundamentals-table');
      if (table) table.innerHTML = '<div class="tk-empty" style="color:var(--red)">队伍资料加载失败</div>';
    },
  };
}

export function markTeamsModule(root, status, message = '') {
  if (!root) return;
  root.dataset.moduleStatus = status;
  root.dataset.moduleMessage = message;
}

const FUNDAMENTALS_SORT_STATE = new WeakMap();
const FUNDAMENTALS_FOCUS_STATE = new WeakMap();
const DEFAULT_FUNDAMENTALS_SORT = Object.freeze({ key: 'power_score', direction: 'desc' });

const FUNDAMENTALS_SORTS = Object.freeze({
  team: { directions: ['asc', 'desc'] },
  power_score: { directions: ['desc', 'asc', null] },
  volatility_score: { directions: ['desc', 'asc', null] },
  trend: { directions: ['desc', 'asc', null] },
  momentum: { directions: ['desc', 'asc', null] },
  status: { directions: ['desc', 'asc'] },
});

export function renderFundamentalsTable(rows, onSelectTeam, doc = document) {
  const element = doc.getElementById('fundamentals-table');
  if (!element) return;
  if (!rows.length) {
    element.innerHTML = '<div class="tk-empty">暂无队伍资料</div>';
    return;
  }
  const sortState = FUNDAMENTALS_SORT_STATE.get(element) || { key: null, direction: null };
  const focusSignal = FUNDAMENTALS_FOCUS_STATE.get(element) || '';
  const focusRows = focusSignal
    ? rows.filter((team) => cycleFocusGroup(team.ts_display?.cycle) === focusSignal)
    : rows;
  const sortedRows = sortFundamentalsRows(focusRows, sortState);
  renderCycleFocusPanel(doc, rows, focusSignal, (nextSignal) => {
    FUNDAMENTALS_FOCUS_STATE.set(element, nextSignal);
    renderFundamentalsTable(rows, onSelectTeam, doc);
  });

  // 本表消费 TS 展示层：队伍 | 赛区 | 综合实力 | 稳定性 | 趋势 | 势头 | 走势类型 | 状态。
  element.innerHTML = renderFundamentalsHead(sortState) + sortedRows.map((team) => {
    const signedNumber = (value) => {
      const n = Number(value ?? 0);
      return `${n > 0 ? '+' : ''}${n.toFixed(1)}`;
    };
    // ts_display 的五项均是处理后的展示值；趋势/势头为 -100～+100 有向信号，原始 mu/sigma/ts 不进用户界面。
    const display = team.ts_display || {};
    const trendText = display.trend === undefined ? '-' : signedNumber(display.trend);
    const momentumText = display.momentum === undefined
      ? '-'
      : momentumPhase(display.trend, display.momentum);
    const cycleText = display.cycle
      ? `${display.cycle.cycle_type}·${display.cycle.cycle_stage}`
      : '-';
    const statusClass = statusTone(display.status);
    return `<div class="fund-row" data-team="${escapeAttr(team.short_name)}">
      <span class="fund-team">${escapeHtml(team.short_name)}</span><span class="fund-region">${escapeHtml(team.region || '-')}</span>
      <span class="fund-num">${display.power_score ?? '-'}</span>
      <span class="fund-num">${display.volatility_score ?? '-'}</span><span class="fund-num">${trendText}</span><span class="fund-num fund-momentum">${escapeHtml(momentumText)}</span>
      <span class="fund-cycle" title="${escapeAttr(display.cycle?.signal_reason || '')}">${escapeHtml(cycleText)}</span>
      <span class="fund-status"><span class="fund-status-tag ${statusClass}">${escapeHtml(display.status || '-')}</span></span>
    </div>`;
  }).join('');
  element.querySelectorAll('[data-team]').forEach((row) => {
    row.addEventListener('click', () => onSelectTeam?.(row.dataset.team));
  });
  element.querySelectorAll('[data-fundamentals-sort]').forEach((header) => {
    const applySort = () => {
      FUNDAMENTALS_SORT_STATE.set(element, nextFundamentalsSort(sortState, header.dataset.fundamentalsSort));
      renderFundamentalsTable(rows, onSelectTeam, doc);
    };
    header.addEventListener('click', applySort);
    header.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        applySort();
      }
    });
  });
}

function momentumPhase(trendValue, momentumValue) {
  const trend = Number(trendValue ?? 0);
  const momentum = Number(momentumValue ?? 0);
  if (trend > 15 && momentum > 15) return '上涨加速 ↑';
  if (trend > 15 && momentum < -15) return '上涨钝化 ↓';
  if (trend < -15 && momentum < -15) return '下跌加速 ↓';
  if (trend < -15 && momentum > 15) return '下跌钝化 ↑';
  if (trend >= 85 && momentum >= -15 && momentum <= 15) return '高位延续观察 →';
  if (trend <= -85 && momentum >= -15 && momentum <= 15) return '低位延续观察 →';
  if (Math.abs(trend) <= 15 && momentum > 15) return '上涨启动 ↑';
  if (Math.abs(trend) <= 15 && momentum < -15) return '下跌启动 ↓';
  return '变化平缓 →';
}

function cycleFocusGroup(cycle) {
  const signal = cycle?.focus_signal || '';
  if (signal === '上行启动' || signal === '强势上行') return 'up';
  if (signal === '下行启动' || signal === '强势下行') return 'down';
  if (signal === '强震荡') return 'oscillation';
  if (signal === '趋势末期') return 'late';
  return '';
}

function renderCycleFocusPanel(doc, rows, activeSignal, onSelect) {
  const panel = doc.getElementById('cycle-focus-panel');
  if (!panel) return;
  const groups = [
    ['up', '上行趋势'],
    ['down', '下行趋势'],
    ['oscillation', '强震荡'],
    ['late', '趋势末期'],
  ].map(([signal, label]) => ({
    signal,
    label,
    teams: rows.filter((team) => cycleFocusGroup(team.ts_display?.cycle) === signal),
  }));
  const activeGroups = groups.filter((group) => group.teams.length);
  panel.innerHTML = `<div class="cycle-focus-head"><b>周期重点关注</b><span>只筛已形成明显周期结构的队伍</span></div>
    <div class="cycle-focus-actions">
      <button class="cycle-filter ${activeSignal ? '' : 'active'}" data-cycle-filter="">全部队伍</button>
      ${activeGroups.map((group) => `<button class="cycle-filter ${activeSignal === group.signal ? 'active' : ''}" data-cycle-filter="${group.signal}">${group.label} <b>${group.teams.length}</b></button>`).join('')}
    </div>
    <div class="cycle-focus-list">${activeGroups.length
      ? activeGroups.map((group) => `<span><b>${group.label}</b>：${group.teams.map((team) => `${escapeHtml(team.short_name)}（${escapeHtml(team.ts_display?.cycle?.cycle_stage || '')}）`).join('、')}</span>`).join('')
      : '<span>当前没有足够明显的周期重点信号，保持观察。</span>'}</div>
    <p class="cycle-focus-help">怎么用：先点信号筛队，再点队伍看原因；上行和下行都是周期方向，强震荡不按单边趋势处理，趋势末期等待后续确认。</p>
    <details class="cycle-focus-guide"><summary>这四类重点怎么用</summary><ul><li><b>上行趋势</b>：初期重点跟踪能否连续确认；延续期可作背景，不当新机会。</li><li><b>下行趋势</b>：同样是方向结构；初期重点确认，延续期防止仍按旧印象高估。</li><li><b>强震荡</b>：不把一场赢或输当趋势反转，优先看对手和其他条件。</li><li><b>趋势末期</b>：变化持续过久或开始钝化，只做反转观察，不能直接追反转。</li></ul></details>`;
  panel.querySelectorAll('[data-cycle-filter]').forEach((button) => {
    button.addEventListener('click', () => onSelect(button.dataset.cycleFilter || ''));
  });
}

function renderFundamentalsHead(sortState) {
  return `<div class="fund-row fund-head">
    ${renderSortHeader('team', '队伍', 'fund-team', sortState)}
    <span class="fund-region">赛区</span>
    ${renderSortHeader('power_score', '综合实力', 'fund-num', sortState)}
    ${renderSortHeader('volatility_score', '稳定性', 'fund-num', sortState)}
    ${renderSortHeader('trend', '趋势', 'fund-num', sortState)}
    ${renderSortHeader('momentum', '势头', 'fund-num', sortState)}
    <span class="fund-cycle">走势类型</span>
    ${renderSortHeader('status', '状态', 'fund-status', sortState)}
  </div>`;
}

function renderSortHeader(key, label, className, sortState) {
  const active = sortState.key === key && sortState.direction;
  const direction = active ? sortState.direction : null;
  const arrow = direction === 'asc' ? '▲' : (direction === 'desc' ? '▼' : '');
  const ariaSort = direction === 'asc' ? 'ascending' : (direction === 'desc' ? 'descending' : 'none');
  const nextDirection = nextFundamentalsSort(sortState, key).direction;
  const orderText = key === 'status'
    ? (nextDirection === 'desc' ? '强到弱' : '弱到强')
    : (nextDirection === 'asc' ? '升序' : (nextDirection === 'desc' ? '降序' : '默认顺序'));
  const style = active
    ? 'cursor:pointer;color:var(--blue);background:var(--blue-light);border-radius:6px;padding:2px 4px;'
    : 'cursor:pointer;padding:2px 4px;';
  return `<span class="${className}" data-fundamentals-sort="${key}" role="button" tabindex="0" aria-sort="${ariaSort}" title="点击按${orderText}排序" style="${style}">${label}<span aria-hidden="true">${arrow ? ` ${arrow}` : ''}</span></span>`;
}

function nextFundamentalsSort(sortState, key) {
  const directions = FUNDAMENTALS_SORTS[key]?.directions || [];
  const current = sortState.key === key ? sortState.direction : null;
  const currentIndex = directions.indexOf(current);
  const direction = directions[(currentIndex + 1) % directions.length];
  return direction ? { key, direction } : { key: null, direction: null };
}

function sortFundamentalsRows(rows, sortState) {
  // 默认也固定为综合实力降序，避免后端投影顺序变化影响用户第一眼看到的强弱顺序。
  const activeSort = sortState.key && sortState.direction ? sortState : DEFAULT_FUNDAMENTALS_SORT;
  return rows.map((team, index) => ({ team, index })).sort((left, right) => {
    const compared = compareFundamentalsTeams(left.team, right.team, activeSort);
    return compared || left.index - right.index;
  }).map(({ team }) => team);
}

function compareFundamentalsTeams(left, right, sortState) {
  const { key, direction } = sortState;
  if (key === 'team') {
    const result = String(left.short_name || '').localeCompare(String(right.short_name || ''), 'en', { sensitivity: 'base' });
    return direction === 'asc' ? result : -result;
  }
  if (key === 'status') return compareStatusValues(left.ts_display?.status, right.ts_display?.status, direction);
  const leftValue = displayNumber(left.ts_display?.[key]);
  const rightValue = displayNumber(right.ts_display?.[key]);
  return compareDisplayValues(leftValue, rightValue, direction);
}

function displayNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function statusParts(status) {
  const text = String(status || '');
  if (!text) return null;
  const strength = text.includes('强') ? 2 : (text.includes('弱') ? 1 : 0);
  const trend = text.includes('上升') ? 4 : (text.includes('回升') ? 3 : (text.includes('平稳') ? 2 : (text.includes('下滑') ? 1 : 0)));
  return { strength, trend };
}

function compareStatusValues(left, right, direction) {
  const leftParts = statusParts(left);
  const rightParts = statusParts(right);
  if (!leftParts) return rightParts ? 1 : 0;
  if (!rightParts) return -1;
  const strength = direction === 'asc'
    ? leftParts.strength - rightParts.strength
    : rightParts.strength - leftParts.strength;
  // 切换只反转强/弱主序；同一档位内始终按“上升→回升→平稳→下滑”。
  return strength || rightParts.trend - leftParts.trend;
}

function compareDisplayValues(left, right, direction) {
  if (left === null) return right === null ? 0 : 1;
  if (right === null) return -1;
  return (direction === 'asc' ? 1 : -1) * (left - right);
}

function statusTone(status) {
  if (!status) return '';
  if (status.includes('上升') || status.includes('回升')) return 'tone-up';
  if (status.includes('下滑')) return 'tone-down';
  return 'tone-flat';
}

function renderProfile(profile, teamInfo, doc) {
  const element = doc.getElementById('profile-content');
  if (!element) return;
  const team = typeof teamInfo === 'string'
    ? { short_name: teamInfo, name: teamInfo }
    : (teamInfo || {});
  const shortName = team.short_name || team.name || '';
  const fullName = team.name || shortName;
  const sections = extractProfileSections(profile?.markdown || '');
  const heading = `<header class="profile-team-header">
    <span class="profile-team-code">${escapeHtml(shortName)}</span>
    <span class="profile-team-name">${escapeHtml(fullName)}</span>
  </header>`;

  element.innerHTML = profile?.found && sections.length
    ? `${heading}<div class="profile-sections">${sections.map((section) => `
      <section class="profile-section">
        <h2>${escapeHtml(section.title)}</h2>
        <div class="profile-section-body">${renderProfileMarkdown(section.content)}</div>
      </section>`).join('')}</div>`
    : `${heading}<div class="profile-empty">暂无 ${escapeHtml(shortName)} 的画像，可直接和当前接入助手说补上。</div>`;
}

const PROFILE_SECTION_TITLES = ['队伍定位', '怎么赢', '怎么输', '关键点', 'BP 倾向'];

function extractProfileSections(markdown = '') {
  const contentByTitle = new Map();
  let activeTitle = '';
  String(markdown).split('\n').forEach((rawLine) => {
    const line = rawLine.trim();
    const section = matchProfileSection(line);
    if (section) {
      activeTitle = section.title;
      contentByTitle.set(section.title, [section.content]);
      return;
    }
    // 只接收当前五项的缩进续行，避免把其他资料混入队伍画像列。
    if (activeTitle && /^\s{2,}\S/.test(rawLine) && !/^\s*#/.test(rawLine)) {
      contentByTitle.get(activeTitle).push(line);
      return;
    }
    if (line) activeTitle = '';
  });
  return PROFILE_SECTION_TITLES
    .filter((title) => contentByTitle.has(title))
    .map((title) => ({ title, content: contentByTitle.get(title).join('\n').trim() }))
    .filter((section) => section.content);
}

function matchProfileSection(line) {
  const bold = line.match(/^(?:[-*•]\s+)?\*\*([^*]+?)\*\*\s*(.*)$/);
  const plain = line.match(/^(?:[-*•]\s+)?(队伍定位|怎么赢|怎么输|关键点|BP\s*倾向)\s*[：:]\s*(.*)$/);
  const candidate = bold ? bold[1] : plain?.[1];
  const title = String(candidate || '').replace(/[：:\s]/g, '');
  const matchedTitle = PROFILE_SECTION_TITLES.find((item) => item.replace(/\s/g, '') === title);
  if (!matchedTitle) return null;
  const content = bold ? bold[2] : plain?.[2];
  return { title: matchedTitle, content: String(content || '').trim() };
}

function renderProfileMarkdown(value = '') {
  const blocks = [];
  let listOpen = false;
  const closeList = () => {
    if (listOpen) blocks.push('</ul>');
    listOpen = false;
  };
  String(value).split('\n').map((line) => line.trim()).forEach((line) => {
    if (!line) {
      closeList();
      return;
    }
    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    const listItem = line.match(/^[-*•]\s+(.+)$/);
    if (heading) {
      closeList();
      const level = Math.min(4, heading[1].length + 2);
      blocks.push(`<h${level}>${renderProfileInlineMarkdown(heading[2])}</h${level}>`);
    } else if (listItem) {
      if (!listOpen) blocks.push('<ul>');
      listOpen = true;
      blocks.push(`<li>${renderProfileInlineMarkdown(listItem[1])}</li>`);
    } else {
      closeList();
      blocks.push(`<p>${renderProfileInlineMarkdown(line)}</p>`);
    }
  });
  closeList();
  return blocks.join('');
}

function renderProfileInlineMarkdown(value) {
  return escapeHtml(value).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
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

function setText(doc, id, value) { const element = doc.getElementById(id); if (element) element.textContent = value; }
function removeLegacyHandler(element, attribute) {
  if (!element) return;
  element.removeAttribute(attribute);
  element[attribute] = null;
}
function escapeHtml(value) { return String(value || '').replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]); }
function escapeAttr(value) { return escapeHtml(value); }
