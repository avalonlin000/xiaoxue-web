import { fetchDailyContent } from './api.js';
import { buildPreMatchContentView } from './model.js';


export async function loadDailyView(date = 'today') {
  return buildPreMatchContentView(await fetchDailyContent(date));
}
