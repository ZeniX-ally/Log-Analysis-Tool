# Monolith 黑碑 — FCT 测试日志分析平台 Code Wiki

> G4.9 FCT XML 测试日志看板 / TE_NEXUS

---

## 目录

- [1. 项目概述](#1-项目概述)
- [2. 整体架构](#2-整体架构)
- [3. 目录结构](#3-目录结构)
- [4. 核心模块详解](#4-核心模块详解)
  - [4.1 后端服务 (app.py)](#41-后端服务-apppy)
  - [4.2 XML 解析器 (fct_parser.py)](#42-xml-解析器-fct_parserpy)
  - [4.3 数据库层 (database.py)](#43-数据库层-databasepy)
  - [4.4 数据模型 (data_model.py)](#44-数据模型-data_modelpy)
  - [4.5 规则引擎 (fail_rules.py / station_risk_rules.py / limit_compare.py)](#45-规则引擎-fail_rulespy--station_risk_rulespy--limit_comparepy)
  - [4.6 知识库 (knowledge/)](#46-知识库-knowledge)
  - [4.7 前端 (index.html)](#47-前端-indexhtml)
- [5. 边缘机与数据采集](#5-边缘机与数据采集)
  - [5.1 边缘机代理脚本](#51-边缘机代理脚本)
  - [5.2 Mock 测试代理](#52-mock-测试代理)
- [6. API 接口文档](#6-api-接口文档)
  - [6.1 日志分析接口](#61-日志分析接口)
  - [6.2 机台遥测接口](#62-机台遥测接口)
  - [6.3 数据库查询接口](#63-数据库查询接口)
  - [6.4 规格书管理接口](#64-规格书管理接口)
  - [6.5 页面路由](#65-页面路由)
- [7. 依赖关系](#7-依赖关系)
- [8. 数据流与处理管线](#8-数据流与处理管线)
- [9. 部署与运行方式](#9-部署与运行方式)
  - [9.1 开发环境 (Windows)](#91-开发环境-windows)
  - [9.2 生产环境 (Ubuntu)](#92-生产环境-ubuntu)
  - [9.3 Systemd 服务](#93-systemd-服务)
- [10. 核心设计决策与优化](#10-核心设计决策与优化)
- [11. 状态归一化体系](#11-状态归一化体系)

---

## 1. 项目概述

**Monolith 黑碑** 是一套用于解析、监控和排查 FCT（Functional Circuit Test）测试 XML 日志的轻量级 Web 工具。

| 项目 | 说明 |
|------|------|
| **项目名称** | Monolith / 黑碑 / TE_NEXUS |
| **核心技术** | Python 3 + Flask + SQLite + ECharts |
| **UI 风格** | Tesla Flat Dark UI（黑色极简平面风格） |
| **核心目标** | 自动解析 FCT XML 文件，将关键信息整理成可视化看板，使工程师无需手动打开超长 XML 文件即可定位问题 |
| **适用场景** | 产线 FCT 测试站（如 FCT6、DB FCT1/2）、多台机台并行监控 |
| **支持的测试站** | G4.9 PEU / G32 XPT 等多型号产品 |

**关键能力：**

- 自动扫描并解析 XML 测试日志（支持递归子目录）
- SN 自动识别与多别名匹配
- PASS / FAIL / 中断 三类业务状态归一化
- TOP FAIL 统计与预警等级
- CPK 过程能力预警（Cpk < 1.33）
- 机台遥测心跳监控（ONLINE / STALE / OFFLINE）
- SPC 统计过程控制散点图
- 原始测试项明细弹窗查看

---

## 2. 整体架构

```
┌──────────────────────────────────────────────────────────────────┐
│                        产线 FCT 机台                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │
│  │  Edge Agent  │  │  Edge Agent  │  │  Edge Agent  │  ...       │
│  │  (Python)    │  │  (Python)    │  │  (Python)    │            │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘            │
│         │ XML Upload      │ Telemetry        │ XML Scan           │
│         │ Push            │ Push             │ (Local Dir)        │
└─────────┼─────────────────┼──────────────────┼────────────────────┘
          │                 │                  │
          ▼                 ▼                  ▼
┌──────────────────────────────────────────────────────────────────┐
│                     Ubuntu 服务器 (Flask Backend)                 │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                      Flask App (app.py)                      │  │
│  │  ┌────────────┐  ┌────────────┐  ┌───────────────────────┐  │  │
│  │  │ FCT Parser │  │  Rule      │  │  Knowledge Base       │  │  │
│  │  │ (XML)      │  │  Engine    │  │  (Instrument/Context) │  │  │
│  │  └────────────┘  └────────────┘  └───────────────────────┘  │  │
│  │                                                             │  │
│  │  ┌──────────────────────────────────────────────────────┐   │  │
│  │  │ SQLite Database (log_analysis.db)                    │   │  │
│  │  │  - telemetry    - log_files  - test_items            │   │  │
│  │  │  - fail_statistics                                   │   │  │
│  │  └──────────────────────────────────────────────────────┘   │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                             ▲                                     │
│                             │ REST API                            │
│                             ▼                                     │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  Frontend (Jinja2 + ECharts)                                │  │
│  │  - 效能监控面板  - 日志检索  - SPC 矩阵  - 机台遥测          │  │
│  └─────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    浏览器访问 (http://host:5000)
```

**架构特点：**

- **单层 Web 架构**：Flask 同时承担 REST API 服务和页面渲染
- **双通道数据源**：内存缓存（telemetry_cache.json） + SQLite 持久化（log_analysis.db）
- **双写模式**：遥测数据同时写入 JSON 缓存和 SQLite
- **Lru_cache 优化**：XML 解析结果使用目录 mtime 作为缓存 key，避免重复解析
- **SQLite WAL 模式**：提升并发读性能

---

## 3. 目录结构

```
Log-Analysis-Tool/
├── backend/                        # 后端服务核心
│   ├── __init__.py
│   ├── app.py                      # Flask 主应用 + API 路由
│   ├── database.py                 # SQLite 数据库操作层
│   ├── models/                     # 数据模型
│   │   ├── __init__.py
│   │   └── data_model.py           # TestItem, TestRecord, MachineStatus
│   ├── parser/                     # XML 解析器
│   │   ├── __init__.py
│   │   └── fct_parser.py           # FCT XML 文件解析
│   ├── rules/                      # 规则引擎
│   ├── __init__.py
│   ├── fail_rules.py           # Top Fail 统计与预警
│   ├── limit_compare.py        # 机台限值比对 & 规格书合规矩阵
│   └── station_risk_rules.py   # 机台风险窗口分析
│   └── knowledge/                  # 工程知识库
│       ├── test_context.py         # 仪表识别、工程提示、名称解析
│       ├── instrument_knowledge.py # (预留)
│       ├── spec_knowledge.py       # (预留)
│       └── testpoint_knowledge.py  # (预留)
├── frontend/
│   └── templates/
│       └── index.html              # 单页应用 (SPA) 前端
├── data/
│   ├── logs/                       # XML 日志存放目录
│   └── telemetry_cache.json        # 机台遥测内存缓存持久化
├── tools/
│   └── mock_machine_agent.py       # Mock 机台遥测推送工具
├── Ubuntu server/                  # Ubuntu 生产部署脚本
│   ├── nexus-fct.service           # systemd 服务配置
│   ├── setup_production.sh         # 生产环境一键部署
│   └── start_server.sh             # Gunicorn 调试启动
├── 边缘机脚本/
│   ├── fct_agent_12.py             # 边缘机代理 V1.2
│   └── fct_agent_16.py             # 边缘机代理 V1.6
├── fct_ipc_agent（边缘机脚本）.py   # 边缘机采集引擎（本地版）
├── requirements.txt                # Python 依赖
└── README.md                       # 项目说明
```

---

## 4. 核心模块详解

### 4.1 后端服务 (app.py)

[app.py](file:///C:/Log-Analysis-Tool/backend/app.py) 是整个应用的入口，承载 Flask 应用、API 路由、业务聚合和性能优化。

#### 4.1.1 核心全局变量

| 变量 | 类型 | 说明 |
|------|------|------|
| `TELEMETRY_CACHE` | `Dict[str, dict]` | 机台遥测数据内存缓存（key = machine_id） |
| `TELEMETRY_HISTORY` | `Dict` | 机台历史数据（预留） |
| `DB_AVAILABLE` | `bool` | SQLite 数据库模块是否可用 |
| `LOG_DIR` | `str` | XML 日志根目录路径 |
| `CACHE_FILE` | `str` | telemetry_cache.json 路径 |

#### 4.1.2 关键函数

| 函数 | 行号 | 职责 |
|------|------|------|
| `get_dir_mtime()` | L159-L164 | 获取目录最后修改时间戳 |
| `_cached_load_records()` | L167-L176 | LRU 缓存的解析函数（maxsize=1），以目录 mtime 作为缓存 key |
| `safe_load_records()` | L178-L182 | 代理函数，将目录 mtime 传入缓存系统 |
| `sync_records_to_db()` | L189-L202 | 将内存解析记录批量同步到 SQLite |
| `get_db_sync_status()` | L204-L220 | 返回 DB 同步状态（日志文件数 vs DB 记录数） |
| `normalize_result()` | L224-L234 | 将原始状态归一化为 PASS / FAIL / 中断 |
| `fallback_build_top_fail()` | L236-L284 | 兜底 TOP FAIL 统计（当 rules 模块不可用时） |
| `get_top_fail_records()` | L286-L292 | 优先使用 rules 模块，兜底 fallback |
| `build_stats()` | L294-L310 | 构建测试统计摘要（总数/通过/失败/FPY/TOP FAIL） |
| `build_analysis()` | L357-L395 | 构建完整分析数据（统计+TOP FAIL+型号汇总+SPC 矩阵） |
| `build_engineering_insights()` | L397-L469 | 工程洞察：连续 FAIL 检测 + CPK 预警 |

#### 4.1.3 排序与时间处理

| 函数 | 行号 | 说明 |
|------|------|------|
| `parse_time_to_timestamp()` | L101-L119 | 支持三种时间格式解析 |
| `parse_filename_time_to_timestamp()` | L121-L131 | 从文件名提取时间戳 |
| `get_record_sort_timestamp()` | L139-L150 | 多字段回退排序时间提取 |
| `sort_records_latest_first()` | L152-L153 | 按时间倒序排列记录 |

#### 4.1.4 API 路由列表

详见 [API 接口文档](#6-api-接口文档) 章节。

#### 4.1.5 性能优化策略

1. **Lru_cache + 目录 mtime**：避免每次请求都重新解析 XML（`_cached_load_records`，L167）
2. **Flask JSON 压缩**：关闭 `JSONIFY_PRETTYPRINT_REGULAR` 减少网络 I/O（L48）
3. **多线程模式**：`app.run(threaded=True)` 支持并发请求（L662）
4. **懒加载模块导入**：parser / rules / database 模块均使用 try/except 导入，单一模块异常不影响整体服务（L49-L96）

---

### 4.2 XML 解析器 (fct_parser.py)

[fct_parser.py](file:///C:/Log-Analysis-Tool/backend/parser/fct_parser.py) 负责解析真实 FTS / FCT XML 测试日志文件。

#### 4.2.1 核心函数

| 函数 | 行号 | 返回值 | 说明 |
|------|------|--------|------|
| `parse_fct_xml()` | L385-L536 | `dict` | 解析单个 XML 文件，返回完整 TestRecord 字典 |
| `load_all_fct_records()` | L539-L548 | `list[dict]` | 递归扫描目录下所有 XML 并批量解析 |
| `find_latest_record_by_sn()` | L555-L597 | `dict \| None` | 按 SN 精确/模糊/后缀/文件名匹配查找 |
| `parse_test_nodes()` | L263-L308 | `list[dict]` | 遍历 XML 中所有 `<TEST>` 节点，提取测项 |
| `parse_abnormal_groups()` | L311-L319 | `list[dict]` | 提取状态异常（中断）的 `<GROUP>` 节点 |
| `get_station_from_xml()` | L322-L335 | `tuple` | 从 `<FACTORY>` 和 `<PRODUCT>` 提取工站信息 |

#### 4.2.2 XML 结构解析策略

```
BATCH (批次级)
  └── PANEL (面板级)
        └── DUT (被测设备级)
              └── TEST (单个测试项)
                    └── GROUP (测试分组)
```

- **SN 提取**：优先从 `<DUT id="...">` 获取，失败则从文件名正则提取
- **型号识别**：路径元数据 > SN 中的 `E\d{7}` 模式
- **整体状态判定**：`decide_overall_result()` (L356-L382)，综合考虑 total/passed/failed/interrupted/skipped
- **容错处理**：解析异常时返回 `PARSE_ERROR` 状态记录，不中断批量加载

#### 4.2.3 辅助函数

| 函数 | 行号 | 说明 |
|------|------|------|
| `local_name()` | L77-L80 | 去除 XML namespace 获取 tag 名 |
| `iter_by_tag()` | L83-L87 | 忽略 namespace 遍历指定 tag |
| `find_first()` | L90-L93 | 查找第一个匹配节点 |
| `get_attr()` | L96-L111 | 多候选名获取 XML 属性（大小写兼容） |
| `normalize_raw_status()` | L114-L120 | 状态归一化 |
| `format_timestamp()` | L127-L142 | 紧凑时间格式转可读格式 |
| `build_parent_map()` | L233-L238 | 构建子→父映射，用于查找父 GROUP |
| `get_parent_group()` | L241-L247 | 获取直接父 GROUP 名 |
| `get_path_groups()` | L250-L260 | 获取完整 GROUP 路径层级 |
| `build_sn_aliases()` | L338-L353 | 构建 SN 多别名（完整/大写/后8/后10/后12位） |

---

### 4.3 数据库层 (database.py)

[database.py](file:///C:/Log-Analysis-Tool/backend/database.py) 提供 SQLite 持久化层，替代纯 JSON 缓存方案。

#### 4.3.1 数据库表结构

| 表名 | 说明 | 核心字段 |
|------|------|----------|
| `telemetry` | 机台遥测数据 | machine_id(UNIQUE), status, payload_json, last_heartbeat |
| `log_files` | 日志文件元数据 | filename(UNIQUE), sn, test_station, overall_status, parsed_at |
| `test_items` | 单个测试项明细 | log_id(FK), test_name, result, value, lower_limit, upper_limit |
| `fail_statistics` | TOP FAIL 统计缓存 | stat_date, fail_item, count, station |

#### 4.3.2 核心函数

| 函数 | 行号 | 说明 |
|------|------|------|
| `get_db()` | L8-L14 | 获取数据库连接，自动创建目录，启用 WAL 模式 |
| `init_db()` | L16-L70 | 初始化所有表结构 |
| `save_telemetry()` | L72-L114 | 保存或更新机台遥测记录（UPSERT 模式） |
| `get_all_telemetry()` | L116-L144 | 获取所有在线机台最新遥测 |
| `get_telemetry_summary()` | L146-L190 | 构建机台摘要（与 app.py 语义对齐） |
| `mark_telemetry_offline()` | L192-L200 | 将超时机台标记为离线 |
| `save_log_records_batch()` | L206-L277 | 批量将解析记录存入 log_files + test_items |
| `get_logs_by_sn()` | L307-L312 | 按 SN 后缀查询日志 |
| `get_log_detail()` | L314-L325 | 获取日志详情及所有测试项 |
| `get_top_fail()` | L327-L358 | 从统计表或实时查询获取 TOP FAIL |
| `update_fail_statistics()` | L360-L373 | 每日汇总统计（可被定时任务调用） |

---

### 4.4 数据模型 (data_model.py)

[data_model.py](file:///C:/Log-Analysis-Tool/backend/models/data_model.py) 使用 Python dataclass 定义三种核心数据模型。

#### 4.4.1 TestItem — 单个测试项

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | str | `""` | 测试项名称 |
| `status` | str | `""` | 原始状态 |
| `business_status` | str | `"中断"` | 业务状态 (PASS/FAIL/中断) |
| `value` | str | `""` | 测量值 |
| `unit` | str | `""` | 单位 |
| `lolim` / `hilim` | str | `""` | 下限 / 上限 |
| `instrument` | str | `""` | 仪表类型 (DMM/OSC/XCP/CAN/LIN/ETH/POWER) |
| `section` / `signal` | str | `""` | 章节号 / 信号名 |
| `engineering_hint` | str | `""` | 工程风险提示 |

#### 4.4.2 TestRecord — 完整测试记录

| 字段 | 类型 | 说明 |
|------|------|------|
| `sn` | str | 序列号 |
| `model` | str | 产品型号（如 E3002781） |
| `test_mode` | str | 测试模式 (Online/Offline) |
| `station` | str | 工站（如 FCT6） |
| `business_result` | str | 业务结果 |
| `fail_items` | list | 失败项列表 |
| `raw_items` | list | 所有测试项明细 |
| `total_tests` / `passed_tests` / `failed_tests` | int | 测试计数 |

#### 4.4.3 MachineStatus — 机台状态

| 字段 | 类型 | 说明 |
|------|------|------|
| `machine_id` | str | 机台唯一标识 |
| `online_status` | str | ONLINE / STALE / OFFLINE |
| `machine_state` | str | IDLE / RUNNING / WARNING |
| `current_sn` | str | 当前测试的 SN |
| `measurements` | dict | 实时测量值 |
| `instruments` | dict | 仪表在线状态 |
| `alarms` | list | 告警列表 |

---

### 4.5 规则引擎 (fail_rules.py / station_risk_rules.py)

#### 4.5.1 fail_rules.py — Top Fail 统计

[fail_rules.py](file:///C:/Log-Analysis-Tool/backend/rules/fail_rules.py)

| 函数 | 行号 | 说明 |
|------|------|------|
| `normalize_fail_name()` | L12-L15 | 从字典或对象标准化失败项名称 |
| `build_top_fail()` | L18-L68 | 统计 TOP N 失败项，包含型号/模式/工站/示例 |
| `warning_level_by_count()` | L71-L76 | 根据计数返回预警等级 (HIGH >= 5, MEDIUM >= 3, LOW) |
| `build_fail_summary()` | L79-L84 | 构建完整失败摘要 |

#### 4.5.2 station_risk_rules.py — 机台风险窗口分析

[station_risk_rules.py](file:///C:/Log-Analysis-Tool/backend/rules/station_risk_rules.py)

**核心算法**：按时间窗口（默认 30 分钟）+ 测试项 + 仪表进行分组，当同一窗口内多个不同 SN 出现相同 FAIL 项时，判定为系统性风险。

| 函数 | 行号 | 说明 |
|------|------|------|
| `parse_dt()` | L8-L34 | 多格式日期时间解析 |
| `time_bucket()` | L37-L43 | 时间分桶（按窗口分钟取整） |
| `build_station_risk()` | L46-L151 | 风险窗口分析主函数 |

**风险判定阈值**：
- `min_fail_count >= 3`：至少 3 次失败
- `min_sn_count >= 3`：至少 3 台不同机台
- `fail_count >= 5`：HIGH 等级

#### 4.5.3 limit_compare.py — 限值比对与规格书合规矩阵

[limit_compare.py](file:///C:/Log-Analysis-Tool/backend/rules/limit_compare.py) 提供两种限值比对模式：

1. **机台对比矩阵 (Machine Matrix)** — 在不依赖外部规格书的情况下，对比不同工站/机台之间同一测项的限值是否一致
2. **规格书合规矩阵 (Spec Compliance Matrix)** — 以上传的规格书 JSON 为基准，逐项比对各机台限值是否符合规格

| 函数 | 行号 | 返回值 | 说明 |
|------|------|--------|------|
| `load_spec()` | L9-L16 | `dict \| None` | 从 JSON 文件加载规格书 |
| `find_model_in_record()` | L19-L26 | `str` | 从记录中提取产品型号 |
| `spec_limits_for_model()` | L29-L44 | `dict \| None` | 查询指定型号在规格书中的限值 |
| `resolve_model_group()` | L47-L54 | `str` | 将型号映射到型号组（model group） |
| `build_station_profile()` | L57-L83 | `dict` | 按工站聚合限值信息 |
| `build_machine_matrix()` | L86-L195 | `dict` | 构建机台限值对比矩阵 |
| `build_spec_compliance_matrix()` | L198-L293 | `dict` | 构建规格书合规矩阵 |
| `compare_limits()` | L296-L302 | `dict` | 统一入口：根据是否有 spec 返回不同对比结果 |

**机台对比矩阵核心逻辑**：

```
build_machine_matrix()
  ├── build_station_profile()        → 按工站聚合测项限值
  ├── 遍历所有测项，对每个测项:
  │     ├── 按限值分组 → limit_groups
  │     ├── 按型号分组 → model_consistency
  │     ├── 判断是否所有机台一致 → all_same
  │     ├── 识别偏离机台 → deviant_stations
  │     └── 判断差异是否因型号不同导致 → model_diff
  └── 排序：不一致的排前面
```

**规格书 JSON 格式**：

```json
{
  "spec_name": "G4.9_FCT_Spec_V2.9",
  "pcba_models": ["E3002609", "E3002781"],
  "model_groups": {
    "A": ["E3002609"],
    "B": ["E3002781"]
  },
  "items": {
    "测项名": {
      "unit": "V",
      "limits": [
        {"models": "*", "lo": "0", "hi": "5"},
        {"models": ["E3002609"], "lo": "0", "hi": "3.3"}
      ]
    }
  }
}
```

- `models="*"` 表示所有型号共用此限值
- `model_groups` 支持将多个型号归为一组，简化限值定义
- 前端支持上传 JSON 文件到 `/api/spec/upload`

---

### 4.6 知识库 (knowledge/)

#### 4.6.1 test_context.py — 工程上下文知识

[test_context.py](file:///C:/Log-Analysis-Tool/backend/knowledge/test_context.py)

| 函数/常量 | 行号 | 说明 |
|-----------|------|------|
| `INSTRUMENT_DEVICE_MAPPING` | L18-L27 | 仪表类型到实际设备的映射 |
| `ENGINEERING_HINTS` | L30-L39 | 各仪表类型的工程排查提示 |
| `detect_instrument()` | L42-L61 | 根据测试项名称识别仪表类型 |
| `get_instrument_device()` | L64-L65 | 获取仪表设备全称 |
| `get_engineering_hint()` | L68-L69 | 获取对应仪表的工程提示 |
| `extract_section()` | L72-L76 | 提取章节号（如 `6.1.1.2.24`） |
| `extract_signal()` | L79-L90 | 提取信号/点位名 |
| `build_nominal_range()` | L93-L104 | 构建标称范围显示（`lo ~ hi unit`） |

#### 4.6.2 预留知识文件

以下文件当前为空，预留用于后续扩展：

- `instrument_knowledge.py` — 仪表详细知识库
- `spec_knowledge.py` — 测试规格知识
- `testpoint_knowledge.py` — 测试点位知识

---

### 4.7 前端 (index.html)

[index.html](file:///C:/Log-Analysis-Tool/frontend/templates/index.html) — 单文件 SPA，Jinja2 模板 + Vanilla JS + ECharts。

#### 4.7.1 四个功能面板

| 面板 | ID | 说明 |
|------|----|------|
| 效能监控 | `overviewPanel` | 核心指标卡片 + TOP FAIL Pareto + CPK 预警 + 实时流水线 |
| 日志检索 | `failCenterPanel` | SN 搜索 + 非 PASS 记录列表 |
| 统计矩阵 | `spcPanel` | SPC 散点图矩阵（带 USL/LSL 规格线） |
| 机台遥测 | `machinePanel` | 机台状态卡片网格 |

#### 4.7.2 前端关键技术点

- **CSS 变量主题**：`--bg-base: #000000`, `--tesla-red: #E31937`
- **动画系统**：`panelFadeIn`, `modalMaskIn`, `modalWindowScale`
- **悬浮光晕引擎**：`.hover-invert-float` — hover 时 invert + drop-shadow 白光效果
- **图表库**：ECharts 5.5.0（CDN 加载）
- **数据刷新**：`setInterval` 每 5 秒刷新看板数据，机台面板每 3 秒刷新
- **缓存机制**：`__RECENT_RECORD_CACHE__` 和 `__SPC_MATRIX_CACHE__` 前端缓存

---

## 5. 边缘机与数据采集

### 5.1 边缘机代理脚本

项目提供多种边缘机采集脚本，用于从产线工控机采集 XML 日志并推送到中心服务器。

#### fct_ipc_agent（边缘机脚本）.py

- **部署位置**：产线工控机（Windows）
- **扫描目录**：`D:\Results`（可配置）
- **工作模式**：轮询 + 账本防重传
- **核心特性**：
  - 递归扫描 XML 文件
  - 内存 + 文件双账本防重传机制
  - 后台心跳线程推送遥测数据
  - 自动处理 0 字节文件和权限冲突
  - 禁用系统代理确保直连

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `SERVER_IP` | `192.168.x.x` | Ubuntu 服务器 IP |
| `MACHINE_ID` | `PEU_G49_FCT6_01` | 机台唯一标识 |
| `LOCAL_LOG_DIR` | `D:\Results` | XML 日志目录 |
| `POLL_INTERVAL` | `5` 秒 | 轮询间隔 |
| `LEDGER_FILE` | 脚本同级 `uploaded_registry.txt` | 防重传账本 |

#### 边缘机脚本版本

- `fct_agent_12.py` — V1.2 版本
- `fct_agent_16.py` — V1.6 版本

### 5.2 Mock 测试代理

[mock_machine_agent.py](file:///C:/Log-Analysis-Tool/tools/mock_machine_agent.py) 用于开发调试阶段模拟机台行为。

**功能**：模拟 3 台 FCT 机台，每 2 秒推送一次遥测数据，包含：

- 随机 SN 生成
- 模拟仪表在线状态（DMM/Power/Eload）
- 模拟电压/电流测量值
- 随机告警生成（电子负载离线、VIN 偏低）

**启动方式**：
```bash
cd D:\Log-Analysis-Tool
python tools/mock_machine_agent.py
```

---

## 6. API 接口文档

### 6.1 日志分析接口

| 端点 | 方法 | 参数 | 说明 |
|------|------|------|------|
| `/api/health` | GET | — | 服务健康检查 |
| `/api/all` | GET | — | 获取所有解析记录 |
| `/api/recent` | GET | `limit` (默认 50) | 获取最新 N 条记录 |
| `/api/search` | GET | `sn` | 按 SN 查询最新匹配记录 |
| `/api/record_detail` | GET | `index` | 按数组索引获取记录详情 |
| `/api/stats` | GET | — | 获取测试统计摘要 |
| `/api/top_fail` | GET | `limit` (默认 10) | 获取 TOP FAIL 列表 |
| `/api/analysis` | GET | — | 获取完整分析数据（含 SPC 矩阵） |
| `/api/engineering_insights` | GET | — | 获取工程洞察（连续 FAIL + CPK 预警） |

### 6.2 机台遥测接口

| 端点 | 方法 | 参数 | 说明 |
|------|------|------|------|
| `/api/telemetry/push` | POST | JSON body | 推送机台遥测数据 |
| `/api/telemetry/latest` | GET | — | 获取最新机台摘要 |

### 6.3 数据库查询接口

| 端点 | 方法 | 参数 | 说明 |
|------|------|------|------|
| `/api/db/status` | GET | — | 数据库同步状态 |
| `/api/db/sync` | POST | — | 手动触发日志同步到 DB |
| `/api/db/search` | GET | `sn` | 从 DB 按 SN 查询 |
| `/api/db/log_detail` | GET | `id` | 从 DB 获取日志详情（含 test_items） |
| `/api/db/top_fail` | GET | `limit`, `station` | 从 DB 获取 TOP FAIL 统计 |
| `/api/db/telemetry` | GET | — | 从 DB 获取机台遥测摘要 |

### 6.4 规格书管理接口

| 端点 | 方法 | 参数 | 说明 |
|------|------|------|------|
| `/api/limit/compare` | GET | `use_spec` (可选 true/false) | 限值比对：机台对比矩阵 或 Spec 合规矩阵 |
| `/api/spec/current` | GET | — | 查询当前已上传的规格书信息 |
| `/api/spec/upload` | POST | JSON body | 上传规格书 JSON |

**`/api/spec/upload` 请求体格式**：
```json
{
  "spec_name": "G4.9_FCT_Spec_V2.9",
  "items": {
    "1.1.1 P1V2_PHY_AVDD(DMM)": {"lo": "0", "hi": "5"}
  }
}
```

### 6.5 页面路由

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 首页（等同于 /dashboard） |
| `/dashboard` | GET | 看板页面 |
| `/analysis` | GET | 分析页面 |
| `/machine` | GET | 机台页面 |

---

## 7. 依赖关系

### 7.1 Python 依赖

| 包 | 版本 | 用途 |
|----|------|------|
| Flask | >= 3.0.0 | Web 框架 |
| gunicorn | == 20.1.0 | 生产 WSGI 服务器 |

### 7.2 前端 CDN 依赖

| 资源 | 版本 | 用途 |
|------|------|------|
| Google Fonts (Inter) | — | UI 字体 |
| Google Fonts (JetBrains Mono) | — | 数字/代码字体 |
| ECharts | 5.5.0 | 图表渲染 |

### 7.3 系统依赖

| 组件 | 用途 |
|------|------|
| Python 3.10+ | 运行时环境 |
| SQLite 3 | 数据持久化（Python 内置，无需额外安装） |
| systemd (Ubuntu) | 生产服务管理 |
| UFW (Ubuntu) | 防火墙配置 |

### 7.4 模块依赖关系图

```
app.py
  ├── parser/fct_parser.py
  │     ├── knowledge/test_context.py
  │     └── (xml.etree.ElementTree)
  ├── rules/fail_rules.py
  ├── rules/station_risk_rules.py
  ├── rules/limit_compare.py
  │     └── (json, os, re)
  ├── database.py
  │     └── (sqlite3, json)
  └── models/data_model.py

knowledge/test_context.py
  └── (独立模块，无内部依赖)

tools/mock_machine_agent.py
  └── (独立脚本，无内部依赖)

fct_ipc_agent.py
  └── (独立脚本，无内部依赖)
```

---

## 8. 数据流与处理管线

### 8.1 XML 日志处理流

```
产线 FCT 测试完成
       │
       ▼
XML 文件生成 (如 F_Fts_PEU_G49_FCT6_xxx.xml)
       │
       ▼
边缘机 Agent 轮询扫描 (D:\Results)
       │
       ▼
XML 文件上传/同步到 data/logs/
       │
       ▼
load_all_fct_records(LOG_DIR)
       │
       ├── parse_fct_xml(xml_path)
       │     ├── extract_path_metadata()     → model, test_mode
       │     ├── get_file_time()              → file_mtime
       │     ├── ET.parse()                   → XML 解析
       │     ├── get_station_from_xml()       → station, tester
       │     ├── parse_test_nodes()           → raw_items
       │     ├── decide_overall_result()      → business_result
       │     └── build_sn_aliases()           → sn_aliases
       │
       └── sort_records_latest_first()        → 按时间倒序
              │
              ▼
       safe_load_records() ← LRU cache
              │
              ├──→ API 响应 (JSON)
              ├──→ build_stats()
              ├──→ build_analysis()
              ├──→ build_engineering_insights()
              └──→ sync_records_to_db()
                      ├──→ log_files 表
                      └──→ test_items 表
```

### 8.2 机台遥测流

```
边缘机 Agent 心跳线程
       │
       ▼
push_telemetry_builtin(URL_TELEMETRY, payload)
       │
       ▼
POST /api/telemetry/push
       │
       ├── normalize_machine_payload()
       ├── TELEMETRY_CACHE[machine_id] = data
       ├── save_telemetry_cache()          → telemetry_cache.json
       │
       └── save_telemetry()                → SQLite telemetry 表
```

### 8.3 CPK 计算流

```
build_engineering_insights()
       │
       ├── 收集前 200 条 PASS 记录的 raw_items
       ├── 筛选有 hi/lo 界限的数值型测试项
       │
       └── 对每个测试项 (样本量 >= 10):
              ├── 计算 mean, std_dev
              ├── CPU = (Hi - mean) / (3 * std)
              ├── CPL = (mean - Lo) / (3 * std)
              ├── CPK = min(CPU, CPL)
              │
              └── 若 CPK < 1.33 → 加入预警列表
                     ├── CPK < 1.0 → CRITICAL
                     └── CPK >= 1.0 → WARNING
```

---

## 9. 部署与运行方式

### 9.1 开发环境 (Windows)

```powershell
# 1. 安装依赖
pip install Flask

# 2. 启动服务
cd D:\Log-Analysis-Tool
python -m backend.app

# 3. (可选) 启动 Mock 机台代理
python tools/mock_machine_agent.py

# 4. 访问浏览器
# http://localhost:5000
```

**开发环境特性**：
- 默认监听 `0.0.0.0:5000`
- `debug=False`（安全考虑）
- `threaded=True`（支持并发）

### 9.2 生产环境 (Ubuntu)

```bash
# 1. 进入项目目录
cd /path/to/Log-Analysis-Tool

# 2. 创建并激活虚拟环境
python3 -m venv venv
source venv/bin/activate

# 3. 安装依赖
pip install Flask gunicorn==20.1.0

# 4. 一键部署（防火墙、权限、systemd）
bash "Ubuntu server/setup_production.sh"

# 或使用调试启动
bash "Ubuntu server/start_server.sh"
```

### 9.3 Systemd 服务

服务配置文件位于 [nexus-fct.service](file:///C:/Log-Analysis-Tool/Ubuntu%20server/nexus-fct.service)。

**配置要点**：
- 工作目录：需替换 `/path/to/Log-Analysis-Tool`
- 运行用户：需替换 `user_name`
- Worker 数量：4（适配 R5 处理器）
- Timeout：120s（防止大 XML 解析超时）
- 崩溃自动重启：`Restart=always`

**常用管理命令**：
```bash
# 查看服务状态
sudo systemctl status nexus-fct

# 查看实时日志
sudo journalctl -u nexus-fct -f

# 重启服务
sudo systemctl restart nexus-fct
```

---

## 10. 核心设计决策与优化

### 10.1 状态归一化体系

项目采用三层状态体系：

```
原始状态 (raw_status)        →  业务状态 (business_status)
PASS / PASSED / OK / SUCCESS     PASS
FAIL / FAILED / NG / FALSE       FAIL
中断 / PAUSED / ERROR / SKIP     中断
UNKNOWN / 其他                   中断
```

**归一化函数**：
- `normalize_raw_status()` — XML 解析层 ([fct_parser.py L114-L120](file:///C:/Log-Analysis-Tool/backend/parser/fct_parser.py#L114-L120))
- `normalize_result()` — API 聚合层 ([app.py L215-L225](file:///C:/Log-Analysis-Tool/backend/app.py#L215-L225))
- `normalizeResult()` — 前端层 (JS)

### 10.2 双通道数据源

| 通道 | 存储方式 | 用途 | 优势 |
|------|----------|------|------|
| **内存 + JSON** | `TELEMETRY_CACHE` + `telemetry_cache.json` | 实时遥测、快速查询 | 低延迟、无 DB 依赖 |
| **SQLite** | `log_analysis.db` | 持久化存储、历史查询 | 持久化、可 SQL 查询、统计优化 |

双写模式确保两个通道数据一致性，单一通道故障不影响主流程。

### 10.3 性能优化

| 优化项 | 实现位置 | 效果 |
|--------|----------|------|
| LRU Cache | `_cached_load_records()` (L158) | 目录未变化时零解析开销 |
| 目录 mtime 检测 | `get_dir_mtime()` (L150) | 快速判断是否需要重新解析 |
| JSON 压缩 | `JSONIFY_PRETTYPRINT_REGULAR = False` (L47) | 减少 API 响应体积 |
| 多线程 | `threaded=True` (L605) | 支持并发请求 |
| SQLite WAL | `PRAGMA journal_mode=WAL` | 提升并发读性能 |
| 懒加载导入 | try/except 导入各模块 (L49-L87) | 单一模块异常不影响整体 |

### 10.4 SN 匹配策略

支持多种 SN 匹配方式（`find_latest_record_by_sn`）：

1. 完整 SN 精确匹配
2. SN 别名匹配（后8位/后10位/后12位）
3. SN 后缀匹配（`endswith`）
4. 文件名包含匹配
5. 相对路径包含匹配

---

## 11. 状态归一化体系详细表

| 场景 | 可能值 | 归一化后 |
|------|--------|----------|
| 通过 | PASS, PASSED, OK, SUCCESS, TRUE | `PASS` |
| 失败 | FAIL, FAILED, NG, FALSE | `FAIL` |
| 中断/异常 | 中断, PAUSED, ERROR, SKIP, SKIPPED, UNKNOWN | `中断` |
| 解析异常 | PARSE_ERROR | `中断` (记录 parse_error 字段) |

---

> **文档版本**: 1.0
> **生成日期**: 2026-05-14
> **适用范围**: 完整项目源码分析
