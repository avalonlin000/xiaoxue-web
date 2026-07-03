# Memory-Bank 使用指南

> 一句话：**你只管说话，AI 负责匹配工具。**

## 你只需要记住这一个入口

```
开新功能 → 说「loop」→ 我跟你要需求卡
改东西   → 说「改XX」→ 我问你"不动什么"
出bug    → 说「XX崩了」→ 我问你定位词
改A炸B   → 说「改A炸B」→ 我读 modules.md 自查边界
```

## 速查：你说什么 → AI 自动做什么

| 你说 | AI 自动加载 | 会发生什么 |
|------|-----------|-----------|
| "开新功能""新模块""loop" | vibe-coding-copilot skill | 弹出需求卡模板让你填，填完开始 loop |
| "改一下XX""调整XX" | vibe-coding-copilot skill | 弹出修改工单模板，追问"不动什么" |
| "XX崩了""XX不对""报错" | vibe-coding-copilot skill | 引导你用五个定位词定位问题层 |
| "改A炸B""上次改了XX以后YY坏了" | vibe-coding-copilot skill | 读 modules.md 查模块边界，定位越界改动 |
| "做到哪了""上次做了什么" | 读 memory-bank/progress.md | 汇报当前进度 |
| "做个日报""巡检""导入B站" | 小雪 skill（已有） | 走现有 cron/管道流程 |

## Loop 怎么用（唯一需要你主动记的）

新功能开第一轮时，你会说类似这样的话：

> "loop，TK面板加一个收藏按钮"

然后我会问你四个问题：做什么、数据从哪来、长什么样、怎么验证。你口头答就行，不用自己填模板。

或者你想走就一次性贴模板也行，模板在 `loop.md`。

## 现有文件一览

```
memory-bank/
├── README.md       ← 你正在读的（唯一入口）
├── progress.md     ← 开发进度（AI 自动更新）
├── modules.md      ← 模块边界（AI 读，你不用管）
└── loop.md         ← Loop模板（想贴模板时用）
```
