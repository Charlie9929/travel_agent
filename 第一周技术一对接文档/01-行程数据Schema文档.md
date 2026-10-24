# 行程数据 Schema 文档 v1.0

> 项目：AI 多人旅行规划助手 ｜ 负责人：技术1（Agent 核心）｜ 版本：v1.0（2026-10-17）｜ 状态：待周日评审
>
> 配套文件：[itinerary.schema.json](./schemas/itinerary.schema.json)（机器可校验的 JSON Schema，draft 2020-12）
>
> 阅读对象：技术2（数据库/后端校验据此设计）、技术3（前端渲染据此取数）、设计组（交互稿据此理解数据形态）

---

## 1. 文档目的

本 Schema 是**全项目最核心的数据契约**：Agent 生成、后端存储校验、前端渲染都围绕它对齐。它回答一个问题——"一份行程在系统里长什么样"。

使用方式：

| 使用方 | 用途 |
|---|---|
| 技术1（Agent） | LLM 输出必须符合本 Schema，作为修复循环的校验基准 |
| 技术2（后端） | ① 数据库表结构设计参考（见 §8 映射建议）② Agent 输出的 JSON 校验 ③ 地图/天气 API 回填数据的目标结构 |
| 技术3（前端） | TypeScript 类型定义据此手写生成（或用 quicktype 转换） |
| 设计组 | 低保真原型中行程卡片、时间轴、修改记录页的字段依据 |

## 2. 设计原则

1. **单一契约**：Agent 输出、后端存储快照、前端取数共用同一结构，避免三套类型互相翻译。
2. **估算与报价强制分离**（Baseline 第 4 条）：所有金额走 `money` 结构，`price_type=estimate | quoted`；LLM 只允许产生 `estimate`，`quoted` 只能由地图 API 查询回填，且强制携带 `source` + `fetched_at`（信息采集模块的"来源+时间戳"硬要求）。
3. **POI 不可编造**（模块② 不靠 LLM 瞎编）：`location.poi_id` 只允许由地图 API 回填，LLM 产出的占位 POI 标记 `poi_source=llm`，由规则引擎校验后替换或标注。
4. **User Control 内建于结构**：AI 产出的修改一律先落为 `revisions[]` 中 `status=pending_confirmation` 的记录，用户预览确认后才覆盖行程。行程本体永远可回溯。
5. **多人协同字段前置预留**：`version`、`members`、`permissions`、`revisions`、`conflict 所需的 activity_id 稳定性` 都在第 1 周定死，第 2-3 周只填值不改结构，避免联调期改契约。
6. **activity_id 是协同锚点**：重排/编辑时未变更的活动必须保持原 `activity_id` 不变——这是 A2 轮询冲突检测、修改差异对比、地图 marker 联动的共同基础，写进修复循环规则。

## 3. 顶层结构总览

```jsonc
{
  "schema_version": "1.0",
  "trip_id": "uuid",
  "version": 3,                          // 每次保存 +1，多人冲突检测依据
  "city": { "name": "成都", "adcode": "510100" },   // 单城市限定
  "meta": {                              // 模块① 需求理解的结构化约束
    "date_start": "2026-10-20", "date_end": "2026-10-22",
    "traveler_count": 4,
    "budget_total": { "amount": 1500, "currency": "CNY", "price_type": "estimate" },
    "preferences": ["美食优先", "少走路"],
    "pace": "relaxed",
    "special_constraints": ["有老人同行"]
  },
  "members": [ /* 预留：成员 */ ],
  "permissions": { /* 预留：协同模式、编辑策略、邀请码、编辑锁 */ },
  "days": [
    {
      "date": "2026-10-20", "day_index": 1, "theme": "老城区美食 citywalk",
      "weather": null,                   // 预留：天气快照（附加B）
      "activities": [ /* 景点/餐饮/住宿/交通条目 */ ],
      "transfers": [ /* 预留：两点间四种出行方式缓存（附加C） */ ]
    }
  ],
  "cost_summary": { "total_estimate": { }, "by_day": [ ], "budget_status": "within" },
  "revisions": [ /* 预留：修改记录 + 结构化 diff + 确认状态 */ ],
  "candidates": [ /* 预留：攻略导入候选条目（附加E） */ ]
}
```

## 4. 字段字典

### 4.1 顶层

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `schema_version` | string | ✅ | 固定 `"1.0"`，结构变更时递增 |
| `trip_id` | string | ✅ | 行程唯一 ID，后端生成；Agent 首次生成时传空串占位 |
| `version` | integer ≥1 | ✅ | 行程版本号，每次保存 +1。编辑请求携带的 `base_version` 与当前值不一致即冲突（附加A） |
| `created_at` / `updated_at` | date-time? | ❌ | 后端维护 |
| `city` | object | ✅ | `name` 必填；`adcode`/`province` 由地图 API 回填。**一份行程只允许一个城市，不跨市** |
| `meta` | object | ✅ | 出行约束（见 4.2） |
| `members[]` | array | ❌ | 预留成员（见 4.3） |
| `permissions` | object | ❌ | 预留权限（见 4.3） |
| `days[]` | array | ✅ | 按天分组的活动（见 4.4） |
| `cost_summary` | object | ✅ | 费用汇总（见 4.5） |
| `revisions[]` | array | ❌ | 预留修改记录（见 4.6） |
| `candidates[]` | array | ❌ | 预留攻略候选（见 4.7） |

### 4.2 meta（出行约束，源自模块①）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `title` | string | ❌ | 行程标题 |
| `date_start` / `date_end` | date | ✅ | 起止日期 |
| `traveler_count` | integer 1–20 | ✅ | 出行人数 |
| `budget_total` | money | ✅ | **预算总额**。用户说"人均"时由需求理解模块换算为总额并标注 |
| `preferences[]` | string[] | ❌ | 偏好标签，如「美食优先」「少走路」 |
| `pace` | relaxed/normal/intense/null | ❌ | 节奏，约束每日活动数量 |
| `party_type` | solo/couple/family/friends/other/null | ❌ | 出行组成 |
| `special_constraints[]` | string[] | ❌ | 自然语言补充约束 |

### 4.3 members / permissions（预留，第 2 周启用）

- `members[]`：`user_id`、`nickname`、`role`（owner / editor / viewer）、`joined_at`。
- `permissions`：`collab_mode`（**A1_edit_lock 编辑锁 / A2_poll 轮询**，组内二选一后只填一种）、`edit_policy`（owner_only / all_members）、`invite_code`、`invite_expires_at`、`locked_by`（A1 模式下持锁人，null=无人持锁）。
- 字段含义对齐技术2 的数据库设计文档（users / trip_members / 角色位）。

### 4.4 days[] → activities[]

**day**：`date`、`day_index`（从 1 起）、`theme`、`weather`（预留：summary / rain_prob / source / fetched_at，支撑附加B 降雨替换）、`activities[]`、`transfers[]`。

**activity**（核心条目）：

| 字段 | 必填 | 说明 |
|---|---|---|
| `activity_id` | ✅ | 格式 `act-<序号>`。**重排时未变更条目必须保持原 ID**（协同/对比/地图联动的锚点） |
| `type` | ✅ | poi / meal / hotel / transport / free_time |
| `title` | ✅ | 名称 |
| `time_slot` | ✅ | `{start, end}`，HH:MM 24 小时制 |
| `location` | ❌ | `name` 必填；`lng/lat/poi_id/poi_source` 由地图 API 回填；LLM 不得编造 poi_id |
| `cost` | ❌ | money 结构，LLM 产出必为 estimate |
| `note` | ❌ | AI 备注（如"需预约"） |
| `open_hours_hint` | ❌ | 开放时间常识参考；准确值以地图 API 查询为准 |
| `status` | ❌ | planned / confirmed / done / replaced / removed（removed 保留供 diff） |
| `replaced_reason` | ❌ | 行中替换原因（下雨/闭馆/排队），附加B |

**transfers[]**（附加C，地图 API 生成，LLM 不生成）：`from_activity_id`、`to_activity_id`、`options[]`（mode=walk/bike/drive/transit、distance_km、duration_min、transit_count、source、fetched_at）。不做路径渲染，只出小卡片数据。

### 4.5 cost_summary

- `total_estimate`：总估算（money）。
- `by_day[]`：每日小计。
- `budget_status`：within / over；`over_by`：超支金额。**由规则引擎（模块④）计算，不信任 LLM 汇总**。

### 4.6 revisions[]（预留，第 3 周启用；模块⑤ 与附加B 核心）

| 字段 | 说明 |
|---|---|
| `revision_id` / `seq` | `rev-<seq>`；seq 全局递增，applied 时与行程 version 联动 |
| `actor` | `source` = human / ai / system + `user_id` |
| `action` | create / constraint_change（行前改约束）/ replan_midtrip（行中重排）/ member_edit / guide_import |
| `summary` | 一句话说明（用户可见），如"预算从 1500 降到 1000，替换了 2 个高价景点" |
| `constraint_snapshot` | 触发修改的约束快照 |
| `diff[]` | 结构化差异：`op`（add/replace/remove/move）+ `path`（JSON Pointer）+ `old_value/new_value` + `reason`（AI 解释为什么改）。前端"新旧方案对比展示"直接消费此字段 |
| `status` | **AI 产出默认 pending_confirmation → 用户预览确认 applied / 拒绝 rejected**（User Control 硬要求） |
| `confirmed_by` / `confirmed_at` | 多人下任何 editor 可确认 |

### 4.7 candidates[]（预留，第 3 周启用；附加E）

LLM 从用户**主动粘贴**的游记文本提取的候选条目：`candidate_id`（cand-N）、`title`、`type`、`suggested_day_index`、`time_slot`、`location`、`cost`、`excerpt`（原文摘录溯源）、`selected`（用户勾选）。确认导入时后端只处理 `selected=true`，转换为 activity 追加到对应 day 并生成 guide_import 修订记录。红线：不爬虫、不自动读链接。

## 5. money 结构详解（Baseline 第 4 条的落地点）

```jsonc
// AI 估算（LLM 生成时唯一允许的形态）
{ "amount": 50, "currency": "CNY", "price_type": "estimate", "source": "llm" }

// 真实报价（仅地图/第三方 API 查询后回填，source + fetched_at 强制）
{ "amount": 55, "currency": "CNY", "price_type": "quoted", "source": "amap",
  "fetched_at": "2026-10-17T10:00:00+08:00" }
```

Schema 用 `if/then` 强制：`price_type=quoted` 时 `source` 与 `fetched_at` 必填。前端据此渲染"估算价"与"查询价"两种标签，绝不混排。

## 6. 预留字段与启用周次对照

| 字段/结构 | 状态 | 启用周次 | 对应功能 |
|---|---|---|---|
| `version`、`days[].activities[].activity_id` 稳定性 | **第 1 周即生效** | 第 1 周 | 多人冲突检测基础 |
| `members[]`、`permissions` | 预留 | 第 2 周 | 附加A 多人协同、邀请链接 |
| `days[].weather` | 预留 | 第 2 周 | 附加B 降雨替换景点 |
| `revisions[]`（diff + 确认状态） | 预留 | 第 3 周 | 模块⑤ 交互式修改、附加B、多人编辑记录 |
| `candidates[]` | 预留 | 第 3 周 | 附加E 攻略导入 |
| `days[].transfers[]` | 预留 | 第 2-3 周 | 附加C 点对点出行方式 |
| 附加D AA 分账 | 独立模块 | 第 2-3 周 | 通过 `trip_id` 关联，不进行程 JSON |
| 附加F 大交通班次 | 待组内讨论 | — | 若做，在 day 下新增预留 `intercity[]`，本期不动 |
| 附加G 照片回忆报告 | 排最后 | — | 独立模块，不进行程 JSON |

## 7. 校验层次（与接口契约 §修复循环 对齐）

| 层级 | 内容 | 执行方 | 工具 |
|---|---|---|---|
| L0 | JSON 语法合法（含 markdown 代码块剥离、尾随逗号清洗） | 技术2 的修复循环 | 程序清洗 |
| L1 | 符合 `itinerary.schema.json`（必填、枚举、类型、quoted 条件必填） | 技术2 的修复循环 | jsonschema |
| L2 | 业务规则：时间不重叠且 time_slot 有序、日期覆盖 date_start..date_end、城市唯一、总估算 vs 预算、activity_id 唯一 | 技术2 规则引擎（模块④） | 纯代码计算 |
| L3 | 事实抽检：POI 存在性/坐标/开放时间/票价，用地图 API 校验，带时间戳回填 | 技术2 信息采集（模块②） | 高德 Web 服务 API |

LLM 只负责"提出方案"；L2/L3 不过 = 方案不合格，进入修复循环或回填修正。

## 8. 对技术2 数据库设计的映射建议（仅供对齐，非强制）

- `trip` 表主档：`trip_id` PK、`version`、`city`、`date_start/date_end`、`owner_id`、`schema_version`；行程完整 JSON 存 `JSONB` 列作为"当前快照"，便于整存整取与版本对比。
- 提升为独立表的关系数据（利于多人查询与冲突检测）：`trip_members`（user_id, role, joined_at）、`trip_revisions`（seq, actor, action, diff JSONB, status, confirmed_by）、`trip_candidates`、`trip_expenses`（附加D，独立模块）。
- `version` 用乐观锁：更新时 `WHERE trip_id=? AND version=<base_version>`，影响行数为 0 即返回 409 冲突（附加A 的 A2 方案）。

## 9. 版本管理规则

- 结构性变更（新增必填、删除/改名、枚举收窄）→ `schema_version` 升小版本并知会全员；可选新增字段尽量保持向后兼容（旧快照仍能通过校验）。
- Prompt 输出契约引用本 Schema 的固定版本号（如 "itinerary.schema.json v1.0"），Prompt 升级时同步检查。

## 10. 待评审确认项（周日评审需拍板）

1. **协同方案 A1（编辑锁）vs A2（轮询+冲突弹窗）**：本 Schema 两者字段都已预留，定案后在 `permissions.collab_mode` 落值。建议 A2（作业性价比最高，写报告时注明"简化协同，工业级 CRDT 留作 future work"）。
2. **日历导出 .ics 是否做**：不影响本 Schema，仅影响行程页动作按钮。
3. **预算人均/总额的换算口径**：当前约定"统一存总额，需求理解模块换算并标注"，组内确认。
