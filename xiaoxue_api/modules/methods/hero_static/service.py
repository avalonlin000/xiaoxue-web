from __future__ import annotations

import difflib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import urlopen

CACHE = Path(os.environ.get('XIAOXUE_CHAMPION_CACHE', '/home/ubuntu/lol_data/champion_static_cache.json'))
BASE = 'https://ddragon.leagueoflegends.com'
# 官方中文名从本地 zh_CN 全量资料生成；此表只保存玩家高频简称。
COMMON_CHINESE_ALIASES = {
    '发条': 'Orianna', '沙皇': 'Azir', '妖姬': 'LeBlanc', '冰女': 'Lissandra',
    '卡牌': 'TwistedFate', '小炮': 'Tristana', '女警': 'Caitlyn', '轮子妈': 'Sivir',
    '大嘴': 'KogMaw', '飞机': 'Corki', 'ez': 'Ezreal', '烬': 'Jhin', '蔚': 'Vi',
    '皇子': 'JarvanIV', '猪妹': 'Sejuani', '蝎子': 'Skarner', '赵信': 'XinZhao',
    '男枪': 'Graves', '盲僧': 'LeeSin', '纳尔': 'Gnar', '武器': 'Jax', '青钢影': 'Camille',
    '剑魔': 'Aatrox', '鳄鱼': 'Renekton', '酒桶': 'Gragas', '石头人': 'Malphite',
    '牛头': 'Alistar', '锤石': 'Thresh', '泰坦': 'Nautilus', '洛': 'Rakan', '露露': 'Lulu',
    '狼母': 'Ambessa', '梦魇': 'Nocturne', '蛇女': 'Cassiopeia', '狐狸': 'Ahri',
    '萨勒芬妮': 'Seraphine', '潘森': 'Pantheon', '烈娜塔': 'Renata',
    # 职业比赛与社区中高频、但不等于官方中文名的简称/旧译。
    '滑板鞋': 'Kalista', '小火龙': 'Smolder', '龙女': 'Shyvana', '大树': 'Maokai',
    '瑞尔': 'Rell', '沙弥拉': 'Samira', '女枪': 'MissFortune', '猴子': 'MonkeyKing',
    '日女': 'Leona', '猫咪': 'Yuumi', '机器人': 'Blitzcrank', '腕豪': 'Sett', '塞恩': 'Sion',
    '炼金': 'Singed', '扎克': 'Zac', 'ksante': 'KSante', '大眼': 'Velkoz', '奥恩': 'Ornn',
    '羊': 'Ornn', '龙王': 'AurelionSol', '剑圣': 'MasterYi', '吸血鬼': 'Vladimir',
    '蚂蚱': 'Malzahar', '小法': 'Veigar', '风女': 'Janna', '寒冰': 'Ashe',
}

def _get(url: str) -> Any:
    with urlopen(url, timeout=25) as response:
        return json.load(response)


def _normalise(value: str) -> str:
    return re.sub(r'[\s\-_.·・/（）()]+', '', value.strip().casefold())


def _clean_champion_input(value: str) -> str:
    """Accept the natural BP forms users actually paste, not only bare names."""
    text = str(value or '').strip()
    text = re.sub(r'^[\[【（(\s]*(?:蓝方|红方|蓝|红)?[\]】）)\s]*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'^(?:上单|打野|中单|下路|辅助|上路|中路|ADC|AD|AP|SUP)\s*[:：|、-]?\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*(?:位|位臵)$', '', text)
    return text.strip(' \t\r\n:：|、-')


def _read_cache() -> dict:
    if not CACHE.exists():
        return {'schema_version': 2, 'current_version': '', 'versions': {}}
    try:
        payload = json.loads(CACHE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'schema_version': 2, 'current_version': '', 'versions': {}}
    # 兼容旧摘要缓存；它没有全技能数据，定时刷新后会被完整版本取代。
    if payload.get('version') and payload.get('data'):
        version = payload['version']
        return {'schema_version': 2, 'current_version': version, 'versions': {version: {
            'updated_at': payload.get('updated_at', ''), 'en_us': payload['data'], 'zh_cn': {}, 'complete': False,
        }}}
    return payload if isinstance(payload.get('versions'), dict) else {'schema_version': 2, 'current_version': '', 'versions': {}}


def refresh_champion_cache(version: str = '') -> dict:
    """Only this maintenance action uses the network; read requests stay local."""
    target = version.strip()
    if not target:
        versions = _get(f'{BASE}/api/versions.json')
        target = versions[0]
    en_us = _get(f'{BASE}/cdn/{target}/data/en_US/championFull.json')['data']
    zh_cn = _get(f'{BASE}/cdn/{target}/data/zh_CN/championFull.json')['data']
    payload = _read_cache()
    payload['schema_version'] = 2
    payload['current_version'] = target
    payload.setdefault('versions', {})[target] = {
        'updated_at': datetime.now(timezone.utc).isoformat(), 'en_us': en_us, 'zh_cn': zh_cn, 'complete': True,
    }
    # 保留最近两个快照，既支持当前版本也不让缓存无限增长。
    versions = payload['versions']
    ordered = sorted(versions, key=lambda key: versions[key].get('updated_at', ''), reverse=True)
    payload['versions'] = {key: versions[key] for key in ordered[:2]}
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    return {'ok': True, 'version': target, 'champion_count': len(en_us), 'cache': str(CACHE)}


def _entry_for_version(requested_version: str) -> tuple[str, dict | None, dict]:
    payload = _read_cache()
    requested = requested_version.strip()
    target = requested or payload.get('current_version', '')
    versions = payload.get('versions', {})
    # Esports commonly writes a patch as “16.16”, while Data Dragon caches
    # it as “16.16.1”. Treat only this two-part -> three-part spelling as an
    # equivalent version; never silently substitute a different patch.
    if requested and target not in versions and re.fullmatch(r'\d+\.\d+', target):
        matched = [version for version in versions if version.startswith(f'{target}.')]
        if len(matched) == 1:
            target = matched[0]
    return target, versions.get(target), payload


def _aliases(en_us: dict, zh_cn: dict) -> tuple[dict[str, str], dict[str, str]]:
    aliases: dict[str, str] = {}
    labels: dict[str, str] = {}
    for champion_id, item in en_us.items():
        chinese = zh_cn.get(champion_id, {})
        for value in (champion_id, item.get('id'), item.get('name'), chinese.get('name'), chinese.get('title')):
            if value:
                aliases[_normalise(str(value))] = champion_id
        labels[champion_id] = chinese.get('name') or item.get('name') or champion_id
    for alias, champion_id in COMMON_CHINESE_ALIASES.items():
        if champion_id in en_us:
            aliases[_normalise(alias)] = champion_id
    return aliases, labels


def _resolve(champion: str, en_us: dict, zh_cn: dict) -> tuple[str | None, dict]:
    cleaned = _clean_champion_input(champion)
    query = _normalise(cleaned)
    aliases, labels = _aliases(en_us, zh_cn)
    exact = aliases.get(query)
    if exact:
        return exact, {'mode': 'exact_or_alias', 'input': champion, 'normalized_input': cleaned, 'matched_name': labels[exact], 'confidence': 1.0}
    scored = sorted(
        ((difflib.SequenceMatcher(None, query, alias).ratio(), champion_id) for alias, champion_id in aliases.items()),
        reverse=True,
    )
    unique: list[tuple[float, str]] = []
    seen: set[str] = set()
    for score, champion_id in scored:
        if champion_id not in seen:
            unique.append((score, champion_id))
            seen.add(champion_id)
    candidates = [{'name': labels[item], 'id': item, 'confidence': round(score, 2)} for score, item in unique[:3]]
    # Never guess a one-character nickname. It is too easy for “蛇/鸟/枪”
    # to resolve to the wrong champion; explicit aliases remain exact matches.
    if len(query) >= 2 and unique and unique[0][0] >= 0.72 and (len(unique) == 1 or unique[0][0] - unique[1][0] >= 0.08):
        score, champion_id = unique[0]
        return champion_id, {'mode': 'fuzzy', 'input': champion, 'normalized_input': cleaned, 'matched_name': labels[champion_id], 'confidence': round(score, 2), 'candidates': candidates}
    return None, {'mode': 'unresolved', 'input': champion, 'normalized_input': cleaned, 'candidates': candidates}


def _localized_champion(detail: dict, localized: dict) -> dict:
    return {
        'id': detail.get('id'), 'key': detail.get('key'),
        'name': localized.get('title') or localized.get('name') or detail.get('name'),
        'title': localized.get('name') or detail.get('title'), 'tags': detail.get('tags', []),
        'partype': detail.get('partype'), 'stats': detail.get('stats', {}),
        'passive': {'name': localized.get('passive', {}).get('name') or detail.get('passive', {}).get('name', ''), 'description': localized.get('passive', {}).get('description') or detail.get('passive', {}).get('description', '')},
        'spells': [
            {'name': local.get('name') or spell.get('name', ''), 'description': local.get('description') or spell.get('description', ''), 'effect_burn': spell.get('effectBurn', [])}
            for spell, local in zip(detail.get('spells', []), localized.get('spells', []))
        ],
        'blurb': localized.get('blurb') or detail.get('blurb', ''),
    }


def get_champion_context(champion: str, version: str = '') -> dict:
    champion = str(champion or '').strip()
    target, entry, payload = _entry_for_version(version)
    if not entry:
        return {'ok': False, 'champion': champion, 'version': target or None, 'reason': 'champion_version_not_cached',
                'available_versions': list(payload.get('versions', {})), 'source': 'local_champion_cache',
                'action': '等待固定刷新，或由维护脚本显式拉取该版本。'}
    en_us, zh_cn = entry.get('en_us', {}), entry.get('zh_cn', {})
    if not en_us:
        return {'ok': False, 'champion': champion, 'version': target, 'reason': 'champion_cache_incomplete',
                'source': 'local_champion_cache', 'action': '运行英雄静态资料刷新后重试。'}
    champion_id, resolution = _resolve(champion, en_us, zh_cn)
    if not champion_id:
        return {'ok': False, 'champion': champion, 'version': target, 'reason': 'champion_not_found',
                'resolution': resolution, 'source': 'local_champion_cache'}
    return {'ok': True, 'version': target, 'source': 'local_champion_cache', 'cache_updated_at': entry.get('updated_at', ''),
            'resolution': resolution, 'champion': _localized_champion(en_us[champion_id], zh_cn.get(champion_id, {})),
            'boundary': '本地静态版本资料，不等于当前职业赛胜率或单场对位结论。'}
