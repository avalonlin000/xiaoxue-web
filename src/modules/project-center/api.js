import { apiRequest } from '../../shared/api/client.js';


const ROOT = '/project-center';


export function getOverview() {
  return apiRequest(`${ROOT}/overview`);
}

export function getModules() {
  return apiRequest(`${ROOT}/modules`);
}

export function getManual() {
  return apiRequest(`${ROOT}/manual`);
}

export function getBasket() {
  return apiRequest(`${ROOT}/change-basket?status=active&limit=50`);
}

export function createBasket(payload) {
  return mutation(`${ROOT}/change-basket`, 'POST', payload);
}

export function patchBasket(itemId, payload) {
  return mutation(`${ROOT}/change-basket/${encodeURIComponent(itemId)}`, 'PATCH', payload);
}

export function getRequests() {
  return apiRequest(`${ROOT}/requests?status=active&limit=50`);
}

export function getDeliveries() {
  return apiRequest(`${ROOT}/deliveries?status=active&limit=50`);
}

export function patchDelivery(deliveryId, payload) {
  return mutation(`${ROOT}/deliveries/${encodeURIComponent(deliveryId)}`, 'PATCH', payload);
}


function mutation(path, method, payload) {
  return apiRequest(path, {
    method,
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
  });
}
