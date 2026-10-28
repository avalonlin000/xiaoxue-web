#!/usr/bin/env python3
"""
Batch Video Discovery & Subtitle Extraction v3
两阶段：flat获取BVID → 逐个元数据+字幕 → 每个视频独立JSON
输出到 batch_results/ 目录
"""
import json, sys, os, re, tempfile
from datetime import datetime, timedelta

COOKIE_FILE = os.environ.get(
    'XIAOXUE_BILIBILI_COOKIES',
    '/home/ubuntu/.config/xiaoxue/bilibili_cookies.txt',
)
OUTPUT_DIR = os.path.join(tempfile.gettempdir(), 'bilibili_batch')
os.makedirs(OUTPUT_DIR, exist_ok=True)

FOLLOWED_UP = []

def _load_up_config():
    """从共享配置文件加载UP主列表"""
    config_path = os.environ.get(
        "XIAOXUE_UP_CONFIG",
        "/home/ubuntu/lol_data/shared/up_config.txt",
    )
    if not os.path.exists(config_path):
        # fallback: 旧版硬编码（逐步废弃）
        result = [
            {"name": "中年电竞人", "uid": "12893969"},
            {"name": "正在努力减肥的香猪", "uid": "326977721"},
            {"name": "心语悦无言", "uid": "523253490"},
        ]
        return result
    result = []
    with open(config_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 2 and parts[1].upper() != 'TBD':
                result.append({"name": parts[0], "uid": parts[1]})
    return result

FOLLOWED_UP = _load_up_config()

def discover_bvids(uid, max_videos=30):
    import yt_dlp
    url = f"https://space.bilibili.com/{uid}/video"
    opts = {
        'quiet': True, 'no_warnings': True,
        'extract_flat': True,
        'playlistend': max_videos,
    }
    if os.path.exists(COOKIE_FILE):
        opts['cookiefile'] = COOKIE_FILE
    
    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            return {
                'ok': True,
                'bvids': [e.get('id') for e in (info.get('entries', []) or []) if e and e.get('id')],
                'error': None,
            }
        except Exception as e:
            sys.stderr.write(f"  ERROR discover: {e}\n")
            return {'ok': False, 'bvids': [], 'error': str(e)}

def extract_video_meta(bvid):
    import yt_dlp
    url = f"https://www.bilibili.com/video/{bvid}"
    opts = {'quiet': True, 'no_warnings': True, 'skip_download': True}
    if os.path.exists(COOKIE_FILE):
        opts['cookiefile'] = COOKIE_FILE
    
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                'bvid': bvid,
                'title': info.get('title', ''),
                'upload_date': info.get('upload_date', ''),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', ''),
                'description': (info.get('description', '') or '')[:500],
            }
    except Exception as e:
        return {'bvid': bvid, 'error': str(e)}

def extract_subtitle(bvid):
    """Extract available subtitles with yt-dlp; absence remains a partial result."""
    import yt_dlp
    url = f"https://www.bilibili.com/video/{bvid}"
    with tempfile.TemporaryDirectory() as tmpdir:
        dl_opts = {
            'outtmpl': os.path.join(tmpdir, '%(id)s.%(ext)s'),
            'writesubtitles': True, 'writeautomaticsub': True,
            'subtitleslangs': ['all'], 'subtitlesformat': 'json',
            'skip_download': True, 'quiet': True, 'no_warnings': True,
        }
        if os.path.exists(COOKIE_FILE):
            dl_opts['cookiefile'] = COOKIE_FILE
        
        try:
            with yt_dlp.YoutubeDL(dl_opts) as ydl:
                ydl.download([url])
        except Exception as e:
            return {'error': str(e)}
        
        result = {}
        for f in os.listdir(tmpdir):
            fpath = os.path.join(tmpdir, f)
            if not os.path.getsize(fpath):
                continue
            try:
                with open(fpath, 'r', encoding='utf-8', errors='replace') as fp:
                    content = fp.read()
                
                text = ''
                if f.endswith('.json'):
                    try:
                        data = json.loads(content)
                        if isinstance(data, list):
                            text = '\n'.join([item.get('content', '') for item in data if isinstance(item, dict)])
                        elif isinstance(data, dict) and 'body' in data:
                            text = '\n'.join([seg.get('content', '') for seg in data['body']])
                    except:
                        pass
                elif f.endswith(('.vtt', '.srt')):
                    lines = []
                    for line in content.split('\n'):
                        line = line.strip()
                        if line and not line.startswith(('WEBVTT', 'Kind:', 'Language:', '-->', '<c>')) \
                           and not re.match(r'^\d+$', line) and not re.match(r'^\d{2}:\d{2}', line):
                            line = re.sub(r'<[^>]+>', '', line)
                            if line:
                                lines.append(line)
                    text = '\n'.join(lines) if lines else ''
                
                if text.strip():
                    key = f.replace('.json', '').replace('.srt', '').replace('.vtt', '')
                    result[key] = text
            except:
                pass
    
    # Prioritize Chinese subtitles (ai-zh > zh-Hans > zh-CN > zh > others)
    priority_order = ['ai-zh', 'zh-Hans', 'zh-CN', 'zh']
    prioritized = {}
    for lang in priority_order:
        for key, text in result.items():
            if lang in key.lower():
                prioritized[key] = text
    for key, text in result.items():
        if not any(lang in key.lower() for lang in priority_order):
            prioritized[key] = text
    
    return prioritized

def main():
    cutoff = (datetime.now() - timedelta(days=7)).strftime('%Y%m%d')
    manifest = {
        'generated_at': datetime.now().isoformat(),
        'cutoff_date': cutoff,
        'videos': [],
        'sources': [],
        '_errors': [],
    }
    
    for up in FOLLOWED_UP:
        name = up['name']; uid = up['uid']
        sys.stderr.write(f"\n{'='*60}\nUP主: {name} ({uid})\n")
        
        discovery = discover_bvids(uid)
        if not isinstance(discovery, dict):
            discovery = {'ok': False, 'bvids': [], 'error': 'invalid discovery result'}
        bvids = discovery.get('bvids', []) if discovery.get('ok') else []
        manifest['sources'].append({
            'name': name,
            'uid': uid,
            'status': 'ok' if discovery.get('ok') else 'failed',
            'discovered': len(bvids),
            'error': discovery.get('error'),
        })
        if not discovery.get('ok'):
            manifest['_errors'].append(f"{name}({uid}): {discovery.get('error') or 'discovery failed'}")
        sys.stderr.write(f"  Phase1: {len(bvids)} BVIDs\n")
        
        if not bvids: continue
        
        recent_count = 0
        for bvid in bvids:
            meta = extract_video_meta(bvid)
            if 'error' in meta:
                sys.stderr.write(f"    {bvid}: ERROR - {meta['error']}\n")
                continue
            
            upload_date = meta.get('upload_date', '')
            if upload_date < cutoff:
                sys.stderr.write(f"    {bvid}: {upload_date} - outside window\n")
                break
            
            recent_count += 1
            title_short = meta.get('title', '')[:60]
            sys.stderr.write(f"    [{upload_date}] {bvid}: {title_short}...\n")
            
            # Extract subtitles (Chinese priority already in extract_subtitle)
            subs = extract_subtitle(bvid)
            subtitle_text = ''
            sub_source = 'none'
            # Chinese-first: check ai-zh then zh-Hans etc.
            for lang_prio in ['ai-zh', 'zh-Hans', 'zh-CN', 'zh']:
                for k, txt in subs.items():
                    if lang_prio in k.lower() and txt:
                        subtitle_text = txt
                        sub_source = k
                        break
                if subtitle_text:
                    break
            # Fallback to any language if no Chinese
            if not subtitle_text:
                for k, txt in subs.items():
                    if k != 'error' and txt:
                        subtitle_text = txt
                        sub_source = k
                        break
            
            # Save individual video JSON
            video_data = {
                **meta,
                'up_name': name, 'up_uid': uid,
                'subtitle_source': sub_source,
                'subtitle_text': subtitle_text,
                'has_subtitle': bool(subtitle_text),
                'url': f"https://www.bilibili.com/video/{bvid}",
            }
            
            out_file = os.path.join(OUTPUT_DIR, f"{bvid}.json")
            with open(out_file, 'w', encoding='utf-8') as fp:
                json.dump(video_data, fp, ensure_ascii=False)
            
            manifest['videos'].append({
                'bvid': bvid, 'up_name': name, 'up_uid': uid,
                'title': meta.get('title', ''), 'upload_date': upload_date,
                'duration': meta.get('duration', 0),
                'has_subtitle': bool(subtitle_text),
                'subtitle_length': len(subtitle_text),
                'file': out_file,
            })
        
        sys.stderr.write(f"  最近7天: {recent_count} videos\n")
    
    manifest['total'] = len(manifest['videos'])
    manifest['with_subtitles'] = sum(1 for v in manifest['videos'] if v['has_subtitle'])
    
    manifest_file = os.path.join(OUTPUT_DIR, 'manifest.json')
    with open(manifest_file, 'w', encoding='utf-8') as fp:
        json.dump(manifest, fp, ensure_ascii=False, indent=2)
    
    # Also output to stdout for piping
    print(json.dumps(manifest, ensure_ascii=False))
    attempted = len(manifest['sources'])
    succeeded = sum(item['status'] == 'ok' for item in manifest['sources'])
    return 2 if attempted and succeeded == 0 else 0

if __name__ == '__main__':
    raise SystemExit(main())
