import {
  createBasket,
  getBasket,
  getDeliveries,
  getManual,
  getModules,
  getOverview,
  getRequests,
  patchBasket,
  patchDelivery,
} from './api.js';


export async function loadProjectCenter() {
  const [overview, modules, manual, basket, requests, deliveries] = await Promise.allSettled([
    getOverview(), getModules(), getManual(), getBasket(), getRequests(), getDeliveries(),
  ]);
  return {
    overview: settled(overview),
    modules: settled(modules),
    manual: settled(manual),
    basket: settled(basket),
    requests: settled(requests),
    deliveries: settled(deliveries),
  };
}


export async function addToBasket(payload) {
  return createBasket(payload);
}


export async function updateBasket(itemId, payload) {
  return patchBasket(itemId, payload);
}


export async function sendDeliveryFeedback(deliveryId, payload) {
  return patchDelivery(deliveryId, payload);
}


function settled(result) {
  return result.status === 'fulfilled'
    ? { data: result.value, error: '' }
    : { data: null, error: result.reason?.userMessage || result.reason?.message || '暂时无法读取' };
}
