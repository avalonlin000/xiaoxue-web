export function summarizeModuleHealth(backend = {}, frontend = {}) {
  const backendItems = Object.values(backend.modules || {});
  const frontendFailures = Object.values(frontend.modules || {})
    .filter((item) => item.status === 'broken');
  const items = [...backendItems, ...frontendFailures];
  const healthy = items.filter((item) => item.status === 'healthy').length;
  const broken = items.filter((item) => item.status === 'broken');
  const disabled = items.filter((item) => item.status === 'disabled');
  const status = backend.status === 'broken'
    ? 'broken'
    : broken.length > 0 || backend.status === 'degraded' || frontend.status === 'degraded'
      ? 'degraded'
      : 'healthy';

  const text = status === 'healthy'
    ? `${healthy} 个模块可用`
    : `${healthy} 可用 · ${broken.length} 待修`;
  const details = [
    ...broken.map((item) => `${item.name || item.id}：${item.message || '暂时不可用'}`),
    ...disabled.map((item) => `${item.name || item.id}：暂未启用`),
  ];
  return { status, text, details };
}

export function renderHealthSummary(element, summary) {
  if (!element) return;
  element.dataset.status = summary.status;
  element.textContent = summary.text;
  element.title = summary.details.join('\n') || '所有模块运行正常';
}
