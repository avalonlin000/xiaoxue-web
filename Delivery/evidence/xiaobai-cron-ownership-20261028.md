# 2026-10-28 引用归属收口：Hermes 侧残留副本改为透明入口

## 结论

小雪两个确定性任务（日报随机抽查、开发视图同步）与结衣每日整理，Hermes 侧入口不再携带项目业务实现，只保留目标存在校验 + `execv` 转发；业务唯一实体在项目目录。

## 项目正式实体

- 日报抽查：`scripts/tasks/xiaoxue_daily_spotcheck.py` → `/home/ubuntu/lol_data/scripts/spotcheck_daily.py`
- 开发同步：`scripts/sync_development_view.py`（游标、git 读取、changelog 写入、progress 时间戳唯一实现）
- 结衣每日整理：`/home/ubuntu/life-os-frontend-v2/scripts/hermes/jieyi_daily_review_cron.py`

## Hermes 侧入口（本次改成薄转发）

- `/home/ubuntu/.hermes/profiles/xiaobai/scripts/xiaoxue_daily_spotcheck.py`（990 B，改前 540 B 且绕过项目任务入口、丢参数）
- `/home/ubuntu/.hermes/profiles/xiaobai/scripts/sync_development_view.py`（937 B，改前 6195 B 完整副本）
- `/home/ubuntu/.hermes/scripts/sync_development_view.py`（937 B，改前 6195 B 完整副本）
- `/home/ubuntu/.hermes/profiles/xiaobai/scripts/jieyi_daily_review_cron.py`（829 B，改前 1639 B 旧实现）

## 验证

- `pytest -q tests/test_sync_development_view.py` → 4 passed
- 4 个 Hermes 入口 + 两个项目实体 `py_compile` 全通过
- 日报薄入口 `--help` → 打印用法、exit 0，未执行抽查
- 目标缺失 → stderr 报错、exit 2（四个入口实测）
- 参数透传 → exit 0（进程内改目标常量，未改文件）
- `hermes cron list` 读回：`8523c336d824` active / `36e7d66fa782` active / `dfa9c93ecb56` paused，时间、投递、workdir 与改前一致，无新增调度源

## 未做

未跑生产写任务（cron run/tick）、未跑完整同步业务脚本、未删历史证据、未改页面/数据/模型/密钥/权限/网络、未 commit/push、未动既有未提交改动。

## 完整证据

`/home/ubuntu/.hermes/team/deliveries/verified-changes/decoupling-20261028/evidence/xiaobai-cron-ownership-20261028.md`

## 仍待自然验证

2026-10-29 02:00 同步任务、2026-10-29 12:00 抽查任务的真实回执。本卡不改变整体交付状态（overall_complete:false / released:false）。
