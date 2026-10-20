#!/usr/bin/env python3
"""Migrate legacy trading-TK metadata into ordinary TK labels.

The script never deletes a file. It replaces only the 19 legacy trading
representations with ordinary Markdown notes carrying directional labels. Run
with --apply only after a filesystem backup has been created.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

TK_DIR = Path('/home/ubuntu/workspace/knowledge/wiki/小雪电竞/原始资料/tk')


def frontmatter(content: str) -> tuple[dict[str, str], str]:
    if not content.startswith('---'):
        return {}, content
    parts = content.split('---', 2)
    if len(parts) < 3:
        return {}, content
    fields = {}
    for line in parts[1].splitlines():
        if ':' in line:
            key, value = line.split(':', 1)
            fields[key.strip()] = value.strip()
    return fields, parts[2].strip()


def tags(value: str) -> list[str]:
    return [item.strip() for item in value.strip().strip('[]').split(',') if item.strip()]


def value_after(text: str, label: str) -> str:
    match = re.search(rf'^{re.escape(label)}\s*[:：]\s*(.+)$', text, re.M)
    return match.group(1).strip() if match else ''


def legacy_note(body: str, fields: dict[str, str]) -> tuple[str, list[str]] | None:
    block = re.search(r'```yaml\s*(.*?)```', body, re.S)
    if not block or 'type: trading_note' not in block.group(1):
        return None
    block_fields = dict(line.split(':', 1) for line in block.group(1).splitlines() if ':' in line)
    team = (block_fields.get('team') or fields.get('team') or '').strip().upper()
    original = value_after(body[block.end():], '原话')
    hint = value_after(body[block.end():], '日报提示')
    if not original:
        return None
    content = original + (f'\n\n补充：{hint}' if hint and hint != original else '')
    return content, ['交易', *( [f'队伍:{team}'] if team else [] )]


def scoped_note(body: str, fields: dict[str, str]) -> tuple[str, list[str]] | None:
    if not fields.get('type') == 'trading_note' or not fields.get('status'):
        return None
    statement = value_after(body, '规律')
    if not statement:
        return None
    context = value_after(body, '适用范围')
    labels = ['交易']
    scope = fields.get('scope', '').lower()
    if scope == 'region' and fields.get('region'):
        labels.append(f"赛区:{fields['region']}")
    if scope == 'team' and fields.get('subject'):
        labels.append(f"队伍:{fields['subject']}")
    if scope == 'player' and fields.get('subject'):
        labels.append(f"选手:{fields['subject']}")
    if fields.get('version_context'):
        labels.append(f"版本:{fields['version_context']}")
    content = statement
    if context and context != '未限定，按具体比赛验证':
        content += f'\n\n补充：{context}'
    return content, labels


def render(content: str, labels: list[str], fields: dict[str, str]) -> str:
    date = fields.get('created', '')
    source = fields.get('source') or '钧钧口述'
    unique = list(dict.fromkeys(labels))
    return f"---\nsource: {source}\nsource_type: manual\ntags: [{', '.join(unique)}]\ncreated: {date}\n---\n\n{content.strip()}\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    changed = []
    for path in sorted(TK_DIR.glob('*.md')):
        raw = path.read_text(encoding='utf-8')
        fields, body = frontmatter(raw)
        converted = scoped_note(body, fields) or legacy_note(body, fields)
        if not converted:
            continue
        content, labels = converted
        new = render(content, labels, fields)
        if new != raw:
            changed.append(path)
            if args.apply:
                path.write_text(new, encoding='utf-8')
    print(('applied' if args.apply else 'dry-run') + f': {len(changed)} files')
    for path in changed:
        print(path.name)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
