export async function mountModules(modules, context) {
  const states = {};
  const handles = {};

  for (const module of modules) {
    if (module.enabled === false) {
      states[module.id] = moduleState(module, 'disabled', module.disabledReason || '暂不启用');
      continue;
    }
    try {
      handles[module.id] = await module.mount(context) || {};
      states[module.id] = moduleState(module, 'healthy', '');
    } catch (error) {
      states[module.id] = moduleState(module, 'broken', userMessage(error));
      context?.onModuleError?.(module, error);
    }
  }

  return {
    status: Object.values(states).some((item) => item.status === 'broken') ? 'degraded' : 'healthy',
    modules: states,
    handles,
  };
}

export async function loadAndMountModules(loaders, context) {
  const loaded = [];
  const importFailures = {};

  for (const loader of loaders) {
    try {
      const imported = await loader.load();
      loaded.push(imported.default || imported.module || imported);
    } catch (error) {
      importFailures[loader.id] = moduleState(loader, 'broken', userMessage(error));
      context?.onModuleError?.(loader, error);
    }
  }

  const mounted = await mountModules(loaded, context);
  const modules = { ...importFailures, ...mounted.modules };
  return {
    status: Object.values(modules).some((item) => item.status === 'broken') ? 'degraded' : 'healthy',
    modules,
    handles: mounted.handles,
  };
}

function moduleState(module, status, message) {
  return {
    id: module.id,
    name: module.name || module.id,
    status,
    message,
  };
}

function userMessage(error) {
  if (!error) return '模块暂时不可用';
  return error.userMessage || error.message || '模块暂时不可用';
}
