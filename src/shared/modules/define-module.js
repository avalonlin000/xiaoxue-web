export function defineModule({ id, name, rootId }) {
  return {
    id,
    name,
    async mount() {
      const root = document.getElementById(rootId);
      if (!root) {
        const error = new Error(`${name}入口不存在`);
        error.userMessage = `${name}暂时不可用，其他模块可以继续使用`;
        throw error;
      }
      root.dataset.moduleId = id;
      root.dataset.moduleStatus = 'healthy';
    },
  };
}
