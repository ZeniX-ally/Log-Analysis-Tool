# NEXUS FCT Log Analysis Dashboard

**轻量级 FCT 测试日志解析 · 监控 · 预警平台**

一键解析 FCT 测试台 XML 日志，提供实时 Web 看板、智能 FAIL 分析、风险预警与飞书集成。

---

## 系统架构

```
┌─────────────────────┐     ┌───────────────────┐     ┌──────────────────────┐
│  FCT 测试台 × 6     │────▶│  Linux 服务端      │────▶│  Web Dashboard       │
│  fct_agent_*.py     │HTTP │  Flask + SQLite    │     │  单页应用            │
│  扫描 D:\Results    │XML  │  解析/存储/分析     │     │  实时展示            │
└─────────────────────┘     └───────────────────┘     └──────────────────────┘
                                     │
                                     ▼
                            ┌────────────────────┐
                            │  飞书 Bot           │
                            │  风险预警 / 日报    │
                            └────────────────────┘
```

## 核心功能

- **全自动解析** — 实时扫描 FCT 测试台上传的 XML 日志，自动识别 SN、PASS/FAIL/INTERRUPTED 等状态
- **Web 看板** — 单页应用，概览统计卡片 + 流水表格 + 详情弹窗，关键信息一目了然
- **智能 FAIL 分析** — 自动统计 TOP FAIL 项，结合规则引擎定位共性失效原因
- **风险预警系统** — 同一机台 3 次连续 FAIL 共享测项时触发 Critical 预警，铃铛图标 + 红色徽章 + 提示音
- **飞书集成** — 实时风险推送到飞书群，定时日报（08:30），Webhook 页面内配置
- **批量积压加速** — 8 线程并行 + GZip 压缩（压缩比 6%）+ 断点续传，30 万文件约 30 分钟完成
- **数据生命周期** — 自动过滤超过 365 天的历史日志，降低存储压力

## 技术栈

| 层级 | 技术 |
|------|------|
| **后端** | Python 3 + Flask + SQLite |
| **前端** | 纯 HTML/CSS/JS 单页应用（SVG 图标，无外部依赖） |
| **采集代理** | Python 脚本（HTTP POST + GZip 压缩） |
| **消息推送** | 飞书 Bot API（自定义 Webhook） |
| **部署** | Gunicorn + Systemd + Nginx（可选） |

## 快速开始

### 1. 开发环境

```bash
pip install -r requirements.txt
python backend/app.py
# → http://127.0.0.1:59488
```

### 2. Linux 生产部署

```bash
# 上传项目
scp -r /path/to/Log-Analysis-Tool user@server:/opt/nexus-fct

# 一键部署
cd /opt/nexus-fct
chmod +x deploy.sh
sudo ./deploy.sh
# → http://<server-ip>:59488
```

`deploy.sh` 自动完成：Python3 + venv + pip 依赖 → Gunicorn 启动 → Systemd 服务注册 → 防火墙放行 → 飞书 Webhook 交互配置 → Nginx 反向代理（可选）。

### 3. 批量历史数据迁移

在每台 FCT 测试台执行：

```bash
python bulk_upload.py --server http://<server-ip>:59488 --dir D:\Results
```

## 项目结构

```
backend/
├── app.py              # Flask 主服务（全部 API 端点）
├── database.py         # SQLite 数据层
├── parser/fct_parser.py    # XML 解析引擎
├── rules/
│   ├── fail_rules.py       # FAIL 分析规则
│   └── limit_compare.py    # 限值比对
├── utils/feishu_bot.py     # 飞书消息推送
└── knowledge/              # 领域知识库
    ├── test_context.py
    ├── instrument_knowledge.py
    ├── spec_knowledge.py
    └── testpoint_knowledge.py

frontend/templates/
└── index.html           # 单页 Web 应用（全部前端）

edge_scripts/
├── fct_agent_1~6.py     # 6 台 FCT 台采集代理
└── bulk_upload.py       # 批量积压上传

deploy/
├── nexus-fct.service    # Systemd 服务单元
└── nexus-fct-nginx.conf # Nginx 反向代理模板

deploy.sh                # 一键部署脚本
```

## 配置说明

| 参数 | 位置 | 说明 |
|------|------|------|
| `SERVER_IP` | `edge_scripts/fct_agent_*.py` | 指向 Linux 服务器内网 IP |
| `LOCAL_LOG_DIR` | `edge_scripts/fct_agent_*.py` | 测试台本地日志目录（默认 `D:\Results`） |
| 飞书 Webhook | Dashboard 设置面板（齿轮图标） | 飞书群机器人 Webhook URL |
| `max_age_days` | `backend/parser/fct_parser.py` | 日志保留天数（默认 365） |
| 日报定时 | SOLO 云端调度器 | 08:30 Asia/Shanghai，POST `/api/feishu/daily-report` |

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/upload_log` | 接收 agent 上传的 XML 日志 |
| `GET` | `/api/records` | 获取测试记录列表 |
| `GET` | `/api/records/<id>` | 获取单条记录详情 |
| `GET` | `/api/stats` | 获取统计概览 |
| `GET` | `/api/alerts/risk` | 获取风险预警列表 |
| `GET/PUT` | `/api/feishu/webhook` | 查看/设置飞书 Webhook |
| `POST` | `/api/feishu/test` | 测试飞书连接 |
| `POST` | `/api/feishu/daily-report` | 手动触发日报推送 |
