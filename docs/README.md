# 小雪工作台 — 来源规格归档说明

> 状态：来源文档 / 历史基线
> 归档说明时间：2026-06-28
> 新文档位置：`/home/ubuntu/life-os-frontend-v2/docs/products/xiaoxue-esports-life/`

---

## 说明

`SPEC.md` 是小雪主工作台早期功能规格，仍然是重要来源文档。

现在用户侧产品名已明确为：**小雪电竞人生**。

Life OS 不再作为用户侧单一产品名，而是内部工程母项目；用户侧拆分为：

- 小雪电竞人生
- 结衣知行合一

---

## 新文档入口

| 类型 | 新文件 |
|------|--------|
| 产品定位 | `docs/products/xiaoxue-esports-life/PRD/00-overview.md` |
| 功能需求 | `docs/products/xiaoxue-esports-life/PRD/01-features.md` |
| 路线图 | `docs/products/xiaoxue-esports-life/PRD/02-roadmap.md` |
| 系统语义 | `docs/products/xiaoxue-esports-life/SSD/00-system-semantics.md` |
| 技术规格 | `docs/products/xiaoxue-esports-life/SSD/01-technical-spec.md` |
| 数据接口 | `docs/products/xiaoxue-esports-life/SSD/02-data-and-api.md` |
| 界面规格 | `docs/products/xiaoxue-esports-life/SSD/03-ui-spec.md` |
| 数据映射 | `docs/products/xiaoxue-esports-life/SSD/04-schema-mapping.md` |
| 验收清单 | `docs/products/xiaoxue-esports-life/ACCEPTANCE.md` |
| 任务清单 | `docs/products/xiaoxue-esports-life/BACKLOG.md` |

---

## 后续维护规则

- `SPEC.md` 保留为来源基线，不直接承载新路线图。
- 新需求、新规格、新验收项写到 `life-os-frontend-v2/docs/products/xiaoxue-esports-life/`。
- 当前可运行主工作台仍在 `/home/ubuntu/xiaoxue-web/`。

---

## MemPalace TK 适配器部署

仓库内的 `deploy/xiaoxue-tk-mempalace.service.example` 是脱敏的 user systemd 模板。部署时复制到 `~/.config/systemd/user/xiaoxue-tk-mempalace.service`，并创建仅保存在服务器上的 `~/.config/xiaoxue/mempalace.env`：

```ini
XIAOXUE_MEMPALACE_SITE_PACKAGES=/实际的/mempalace/site-packages
XIAOXUE_MEMPALACE_PALACE=/实际的/palace
XIAOXUE_TK_SOURCE_DIR=/实际的/小雪TK目录
XIAOXUE_MEMPALACE_WING=xiaoxue-tk
```

然后执行：

```bash
systemctl --user daemon-reload
systemctl --user enable --now xiaoxue-tk-mempalace.service
curl -fsS http://127.0.0.1:8770/api/health
```

路径由环境文件提供；仓库代码不绑定服务器用户名、Python 小版本或知识库绝对路径。
