from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from xiaoxue_api.modules.methods.hero_static import service


class ChampionStaticTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache = Path(self.temp_dir.name) / 'champions.json'
        self.cache_patch = patch.object(service, 'CACHE', self.cache)
        self.cache_patch.start()
        data = {
            'Ambessa': {'id': 'Ambessa', 'key': '799', 'name': 'Ambessa', 'title': 'War Matriarch', 'tags': ['Fighter'], 'partype': 'Energy', 'stats': {}, 'passive': {'name': 'P', 'description': 'P desc'}, 'spells': [{'name': 'Q', 'description': 'Q desc', 'effectBurn': []}], 'blurb': 'b'},
            'Cassiopeia': {'id': 'Cassiopeia', 'key': '69', 'name': 'Cassiopeia', 'title': 'Serpent', 'tags': ['Mage'], 'partype': 'Mana', 'stats': {}, 'passive': {}, 'spells': [], 'blurb': ''},
        }
        localized = {
            'Ambessa': {'name': '铁血狼母', 'title': '安蓓萨', 'passive': {'name': '被动', 'description': '被动描述'}, 'spells': [{'name': 'Q技能', 'description': 'Q描述'}], 'blurb': '简介'},
            'Cassiopeia': {'name': '魔蛇之拥', 'title': '卡西奥佩娅', 'passive': {}, 'spells': [], 'blurb': ''},
        }
        self.cache.write_text(json.dumps({'schema_version': 2, 'current_version': '16.16.1', 'versions': {'16.16.1': {'updated_at': '2026-08-18T00:00:00+00:00', 'en_us': data, 'zh_cn': localized, 'complete': True}}}, ensure_ascii=False), encoding='utf-8')

    def tearDown(self) -> None:
        self.cache_patch.stop()
        self.temp_dir.cleanup()

    def test_common_alias_returns_localized_full_skill_data(self) -> None:
        result = service.get_champion_context('狼母')
        self.assertTrue(result['ok'])
        self.assertEqual(result['source'], 'local_champion_cache')
        self.assertEqual(result['champion']['name'], '安蓓萨')
        self.assertEqual(result['champion']['spells'][0]['description'], 'Q描述')
        self.assertEqual(result['resolution']['mode'], 'exact_or_alias')

    def test_fuzzy_match_handles_single_character_typo(self) -> None:
        result = service.get_champion_context('卡西奥佩亚')
        self.assertTrue(result['ok'])
        self.assertEqual(result['champion']['id'], 'Cassiopeia')
        self.assertEqual(result['resolution']['mode'], 'fuzzy')

    def test_position_prefix_is_removed_before_lookup(self) -> None:
        result = service.get_champion_context('下路维克托')
        self.assertFalse(result['ok'])
        # The fixture intentionally has no Viktor; the important contract is
        # that the lookup reaches the champion layer with a cleaned input.
        self.assertEqual(result['reason'], 'champion_not_found')
        self.assertEqual(result['resolution']['normalized_input'], '维克托')

    def test_single_character_fuzzy_guess_is_rejected(self) -> None:
        result = service.get_champion_context('蛇')
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'champion_not_found')
        self.assertEqual(result['resolution']['mode'], 'unresolved')

    def test_common_community_aliases_resolve_without_fuzzy_guessing(self) -> None:
        data = json.loads(self.cache.read_text(encoding='utf-8'))
        champions = data['versions']['16.16.1']['en_us']
        localized = data['versions']['16.16.1']['zh_cn']
        fixtures = {
            'Kalista': ('复仇之矛', '滑板鞋'),
            'Smolder': ('炽炎雏龙', '小火龙'),
            'Maokai': ('扭曲树精', '大树'),
            'Rell': ('镕铁少女', '瑞尔'),
            'Samira': ('沙漠玫瑰', '沙弥拉'),
            'MissFortune': ('赏金猎人', '女枪'),
            'MonkeyKing': ('齐天大圣', '猴子'),
            'Renata': ('烈娜塔·戈拉斯克', '烈娜塔'),
        }
        for champion_id, (name, _) in fixtures.items():
            champions[champion_id] = {'id': champion_id, 'name': champion_id, 'title': name, 'tags': [], 'stats': {}, 'passive': {}, 'spells': []}
            localized[champion_id] = {'name': name, 'title': name, 'passive': {}, 'spells': []}
        self.cache.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        for champion_id, (_, alias) in fixtures.items():
            with self.subTest(alias=alias):
                result = service.get_champion_context(alias)
                self.assertTrue(result['ok'])
                self.assertEqual(result['champion']['id'], champion_id)
                self.assertEqual(result['resolution']['mode'], 'exact_or_alias')

    def test_unknown_name_returns_candidates_without_network(self) -> None:
        with patch.object(service, '_get', side_effect=AssertionError('read path must remain local')):
            result = service.get_champion_context('不存在英雄')
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'champion_not_found')
        self.assertIn('candidates', result['resolution'])

    def test_missing_version_does_not_fetch_during_analysis(self) -> None:
        with patch.object(service, '_get', side_effect=AssertionError('read path must remain local')):
            result = service.get_champion_context('狼母', '15.1.1')
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'champion_version_not_cached')

    def test_two_part_esports_patch_uses_equivalent_data_dragon_snapshot(self) -> None:
        result = service.get_champion_context('狼母', '16.16')
        self.assertTrue(result['ok'])
        self.assertEqual(result['version'], '16.16.1')


if __name__ == '__main__':
    unittest.main()
