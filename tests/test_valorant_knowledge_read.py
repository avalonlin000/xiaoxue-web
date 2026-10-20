"""Read-only candidate helper and routing regression; fixtures are not acceptance data."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SKILLS = Path('/home/ubuntu/.agents/skills')

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

brief = load('valorant_brief', SKILLS / 'esports/other-esports-markets/scripts/valorant_brief.py')
route = load('xiaoxue_route', SKILLS / '小雪/scripts/detect_task.py')

class ValorantKnowledgeReadTests(unittest.TestCase):
    def test_game_precedes_generic_research_and_match_routes(self):
        for q in ['研究无畏契约揭幕轮规律', '瓦赛前准备', '无畏契约今天的比赛', '瓦PRX阵容强弱']:
            self.assertEqual(route.detect(q)['entry'], 'valorant', q)
        for q, target in [('把瓦这条写进TK', 'tk_write'), ('按我的交易系统看瓦', 'trading_system'), ('LOL今天的比赛', 'cycle'), ('CS2大小分', 'cs2')]:
            self.assertEqual(route.detect(q)['entry'], target)

    def test_original_restrictions_and_both_kinds_remain_read_only(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            notes = {'trading_tk_sample.md': '游戏:无畏契约\n【揭幕轮】待核；已暂停；不能支撑当前判断。',
                     'sample.md': '---\ntags: [游戏:无畏契约]\n---\n【揭幕轮】概念认识。',
                     'lol.md': '---\ntags: [游戏:LOL]\n---\n【揭幕轮】'}
            for name, text in notes.items():
                (root / name).write_text(text)
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            rows = brief.read_knowledge(root, '揭幕轮')
            self.assertEqual({r['kind'] for r in rows}, {'TK', '交易 TK'})
            self.assertEqual(len(rows), 2)
            self.assertIn('已暂停', next(r['content'] for r in rows if r['kind'] == '交易 TK'))
            self.assertEqual(len(brief.read_knowledge(root, ids=['trading_tk_sample'])), 1)
            self.assertEqual(brief.read_knowledge(root, '不存在'), [])
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})

    def test_real_observation_and_exact_source(self):
        rows = brief.read_knowledge(brief.TK_ROOT, '揭幕轮')
        self.assertEqual(len(rows), 1)
        self.assertIn('待核', rows[0]['content'])
        self.assertIn('降为背景', rows[0]['content'])
        self.assertEqual(rows, brief.read_knowledge(brief.TK_ROOT, ids=[rows[0]['id']]))
        self.assertEqual(rows[0]['content'], Path(rows[0]['source_path']).read_text())

if __name__ == '__main__':
    unittest.main()
