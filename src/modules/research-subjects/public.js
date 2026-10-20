import { addEvent, addMaterial, addUserNote, fetchDossier, listSubjects, openSubject } from './api.js';
import { createResearchSubjectsView } from './view.js';

let dispose = () => {};

export default {
  id: 'research-subjects',
  name: '主体档案',
  async mount(context = {}) {
    const root = document.getElementById('card-research-subjects');
    const view = createResearchSubjectsView(root);
    let subjectId = null;
    dispose();
    const refresh = async () => {
      if (!subjectId) return null;
      const dossier = await fetchDossier(subjectId);
      view.render(dossier);
      return dossier;
    };
    const loadDirectory = async () => {
      const response = await listSubjects(view.values().subject_key);
      view.renderDirectory(response.subjects || []);
      return response;
    };
    const actions = {
      async open() {
        try {
          const subject = await openSubject(view.values());
          subjectId = subject.id;
          view.message(`已打开 ${subject.name} 档案`, 'success');
          await loadDirectory();
          return refresh();
        } catch (error) {
          view.message(error.message || '打开失败', 'error');
          return null;
        }
      },
      async addMaterial() {
        if (!subjectId) return view.message('请先打开主体档案', 'error');
        try {
          await addMaterial(subjectId, view.materialValues());
          view.message('资料已保存，并保留来源与时间', 'success');
          return refresh();
        } catch (error) {
          view.message(error.message || '保存资料失败', 'error');
          return null;
        }
      },
      async addEvent() {
        if (!subjectId) return view.message('请先打开主体档案', 'error');
        try {
          await addEvent(subjectId, view.eventValues());
          view.message('事件已加入档案；资料和笔记现在可以挂到它下面', 'success');
          return refresh();
        } catch (error) {
          view.message(error.message || '保存事件失败', 'error');
          return null;
        }
      },
      async openExisting(id) {
        try {
          subjectId = id;
          const dossier = await refresh();
          view.message(`已打开 ${dossier.subject.name} 档案`, 'success');
          return dossier;
        } catch (error) {
          view.message(error.message || '打开档案失败', 'error');
          return null;
        }
      },
      async list() {
        try {
          return await loadDirectory();
        } catch (error) {
          view.message(error.message || '读取档案目录失败', 'error');
          return null;
        }
      },
      async addNote() {
        if (!subjectId) return view.message('请先打开主体档案', 'error');
        try {
          await addUserNote(subjectId, view.noteValues());
          view.message('已保存你的原始笔记', 'success');
          return refresh();
        } catch (error) {
          view.message(error.message || '保存笔记失败', 'error');
          return null;
        }
      },
    };
    dispose = view.bind(actions);
    loadDirectory().catch(() => {});
    context.events?.on('page:changed', ({ page }) => { if (page === 'research') refresh().catch(() => {}); });
    root.dataset.moduleId = 'research-subjects';
    root.dataset.moduleStatus = 'healthy';
    return { actions };
  },
  unmount() {
    dispose();
    dispose = () => {};
  },
};
