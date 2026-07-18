export function renderModuleStatus(root, status) {
  if (!root || !status) return;
  root.dataset.moduleStatus = status.status;
  const statusEl = root.querySelector('[data-module-status-message]');
  if (statusEl) {
    statusEl.textContent = status.status === 'healthy' ? '' : status.message || '该模块暂时不可用';
    statusEl.hidden = status.status === 'healthy';
  }
}
