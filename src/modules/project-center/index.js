import { createProjectCenterView } from './public.js';


export const id = 'project-center';
export const name = '项目中心';


export function mount({ events }) {
  const root = document.getElementById('project-center');
  if (!root) throw new Error('项目中心容器没有找到');
  return { actions: createProjectCenterView({ root, events }) };
}


export default { id, name, mount };
