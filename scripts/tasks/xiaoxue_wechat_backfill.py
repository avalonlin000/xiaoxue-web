#!/usr/bin/env python3
"""补跑历史公众号导入。

历史 manifest 里的搜狗跳转链接已被反爬拦住；这里按文章标题回查微信读书（批量搜索），
拿到真实 mp.weixin.qq.com 链接后构建新 manifest，交给 apply_knowledge_import 重新抓正文并提炼。
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

LOL_DATA = Path("/home/ubuntu/lol_data")
SCRIPTS = LOL_DATA / "scripts"
BATCH = Path(__file__).resolve().with_name("weread_batch_search.py")
APPLY = SCRIPTS / "apply_knowledge_import.py"


def norm(value) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", str(value or "").lower())


def collect(days: list[str]) -> list[dict]:
    seen: dict[str, dict] = {}
    for day in days:
        path = SCRIPTS / f"knowledge_import_manifest_{day}.json"
        if not path.is_file():
            print(f"跳过 {day}: manifest 不存在", flush=True)
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        items = ((data.get("sources") or {}).get("wechat") or {}).get("items") or []
        print(f"{day}: {len(items)} 条候选", flush=True)
        for item in items:
            title = str(item.get("title") or "").strip()
            key = norm(title)
            if title and key and key not in seen:
                seen[key] = {"title": title, "summary": item.get("summary") or "", "source_day": day}
    return list(seen.values())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", nargs="+", required=True)
    ap.add_argument("--search-only", action="store_true")
    ap.add_argument("--manifest", default="")
    args = ap.parse_args()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.manifest:
        manifest_path = Path(args.manifest)
        resolved = json.loads(manifest_path.read_text(encoding="utf-8"))["sources"]["wechat"]["items"]
        print(f"沿用已有 manifest：{manifest_path}（{len(resolved)} 条）", flush=True)
    else:
        candidates = collect(args.days)
        print(f"去重后 {len(candidates)} 条，开始批量回查微信读书", flush=True)
        query_file = Path(f"/tmp/wechat_backfill_queries_{stamp}.txt")
        query_file.write_text("\n".join(c["title"] for c in candidates), encoding="utf-8")
        result_file = Path(f"/tmp/wechat_backfill_search_{stamp}.json")
        proc = subprocess.run([sys.executable, str(BATCH), str(query_file), "-o", str(result_file)],
                              capture_output=True, text=True, timeout=7200)
        print(proc.stdout[-3000:], flush=True)
        if proc.returncode != 0:
            print("批量搜索失败:", (proc.stderr or "")[-2000:], flush=True)
            return 1
        hits = json.loads(result_file.read_text(encoding="utf-8"))

        resolved, failed = [], []
        for candidate in candidates:
            matched = next(
                (row for row in hits.get(candidate["title"], [])
                 if "mp.weixin.qq.com" in (row.get("url") or "")
                 and norm(row.get("title")) == norm(candidate["title"])),
                None,
            )
            if matched:
                url = matched["url"]
                resolved.append({
                    "title": candidate["title"],
                    "url": url,
                    "summary": candidate["summary"] or matched.get("desc") or "",
                    "desc": matched.get("desc") or candidate["summary"] or "",
                    "source": matched.get("source") or "",
                    "date": matched.get("date") or "",
                    "item_id": f"wechat:{url}",
                    "status": "pending",
                    "source_day": candidate["source_day"],
                })
            else:
                failed.append(candidate)
        print(f"命中 {len(resolved)} / {len(candidates)}；未命中 {len(failed)}", flush=True)
        for row in failed[:10]:
            print("  未命中:", row["title"][:50], "|", row["source_day"], flush=True)

        manifest = {
            "schema": "xiaoxue-knowledge-import-discovery-v1",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "status": "ok",
            "sources": {"wechat": {"status": "ok", "error": None, "items": resolved}},
            "requested_source": "wechat",
            "failed_titles": [row["title"] for row in failed],
        }
        manifest_path = SCRIPTS / f"knowledge_import_backfill_{stamp}.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print("manifest:", manifest_path, flush=True)

    if args.search_only:
        return 0

    print("开始 apply（抓正文 + TK 提炼，耗时较长）", flush=True)
    proc = subprocess.run([sys.executable, str(APPLY), "--manifest", str(manifest_path), "--source", "wechat"],
                          capture_output=True, text=True, timeout=14400)
    print(proc.stdout[-6000:] if proc.stdout else "", flush=True)
    if proc.returncode != 0:
        print("apply stderr:", (proc.stderr or "")[-3000:], flush=True)
    print("apply exit:", proc.returncode, flush=True)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
