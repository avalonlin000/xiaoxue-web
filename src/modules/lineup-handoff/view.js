export function readLineupInput(source = 'trade') {
  return {
    matchName: value('trade-match'),
    marketDirection: value('trade-winner'),
    oddsScore: value('trade-score'),
    preThought: value('trade-reason'),
    review: value('trade-review'),
    lineupText: source === 'analyst' ? value('analyst-bp-input') : '',
  };
}

export function showLineupFallback(text) {
  const output = document.getElementById('analyst-output');
  if (output) output.textContent = text;
}

export function createLineupView(root) {
  if (!root) throw new Error('阵容入口不存在');
  const input = root.querySelector('#analyst-bp-input');
  const output = root.querySelector('#analyst-output');
  return {
    readLineup: () => input?.value.trim() || '',
    show(text) { if (output) output.textContent = text || ''; },
    loading(team, analyst) { if (output) output.textContent = `正在读取 ${team} · ${analyst}…`; },
    bind(actions) {
      const disposers = [];
      root.querySelectorAll('[data-lineup-action]').forEach((button) => {
        const handler = () => {
          const action = button.dataset.lineupAction;
          if (action === 'generate') actions.generate();
          if (action === 'copy') actions.copyFromAnalyst();
          if (action === 'analyst') actions.loadAnalyst(button.dataset.analyst || '中年电竞人');
        };
        button.addEventListener('click', handler);
        disposers.push(() => button.removeEventListener('click', handler));
      });
      return () => disposers.forEach((dispose) => dispose());
    },
  };
}

function value(id) {
  return document.getElementById(id)?.value.trim() || '';
}
