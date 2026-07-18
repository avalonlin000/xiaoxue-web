export function createEventBus() {
  const listeners = new Map();
  return Object.freeze({
    on(eventName, listener) {
      const group = listeners.get(eventName) || new Set();
      group.add(listener);
      listeners.set(eventName, group);
      return () => group.delete(listener);
    },
    emit(eventName, payload) {
      for (const listener of listeners.get(eventName) || []) {
        try {
          listener(payload);
        } catch (error) {
          console.warn(`event listener failed: ${eventName}`, error);
        }
      }
    },
  });
}
