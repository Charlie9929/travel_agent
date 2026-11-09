# Week 4 技术1 · 联调契约核对与边界用例

> 负责人：技术1（庞林涛）｜ 日期：2026-11-09｜ 基线提交：`b464a97`（origin/main）
> 对应周任务：对接前后端、联调行程生成/重排/多人协同接口；修复 Prompt 与格式问题；优化极端预算、全天降雨、多人同时编辑边界
> 交付状态：**边界 Prompt v0.3 + 回归脚本已就绪；3 个 P0/P1 联调缺口已定位，其中前端缺口已修复，后端缺口待技术2 决策**

---

## 1. 结论摘要

| 项 | 状态 | 证据 |
|---|---|---|
| 前后端接口契约核对（6 个 AI 接口） | ✅ 完成 | §3 接口矩阵 |
| 前端联调缺口修复 | ✅ 已改 4 处 | `frontend/src/api/client.ts`、`types.ts` |
| 边界 case Prompt v0.3（极端预算 / 全天降雨 / 多人同时编辑） | ✅ 已交付 | `docs/prompts/*-v0.3.md` |
| 边界回归脚本 | ✅ 23/23 通过 | `python smoke_test_v04.py` |
| 后端 Prompt 输入结构不一致 | ⚠️ **P0 未解**，已加兼容层 | §4 D1 |
| replan 未预查替换候选 | ⚠️ **P0 未解** | §4 D2 |
| 真实 API + 双人联调验收 | ⏸ 需技术2/技术3 环境 | §7 |

---

## 2. 当前仓库进度（origin/main `b464a97`）

- 后端：Week 3 全部完成。`business_validation.py` 已通过 `importlib` 动态加载技术1 的两个校验器；`ai_service` 已接入 generate / replan / revise / explain-diff / import-guide；修复循环、乐观锁、replan rebase 均已实现。
- 前端：技术3 已提交 `frontend/`（Vite + React），`api/client.ts` 已有真实后端调用，默认 mock 开关 `VITE_USE_MOCKS`。
- 文档：Week 2/3 的 Prompt 与协同规则在 `docs/`；前端联调确认清单在 `docs/前端联调需要后端补充或确认.md`。
- 技术1 本轮新增：3 个 v0.3 Prompt、`smoke_test_v04.py`、本文档、前端契约修复。

---

## 3. 接口核对矩阵

| 接口 | 前端调用 | 后端契约 | 结论 |
|---|---|---|---|
| `POST /ai/generate` | `api.ai.generate` | `GenerateRequest{trip_id, additional_requirements}` | ✅ 参数对齐；⚠️ Prompt 输入结构见 D1 |
| `POST /ai/replan` | `api.ai.replan` | `ReplanRequest` 含 `after_time/trigger/candidate_replacements` | ✅ 已补齐前端缺参；⚠️ 候选预查见 D2 |
| `POST /ai/revise` | `api.ai.revise` | `ReviseRequest{trip_id, changed_constraints, user_instruction, trip_version}` | ✅ 对齐；diff/summary/retry_count 已返回 |
| `POST /ai/explain-diff` | `api.ai.explainDiff` | `ExplainDiffRequest{mode, old, new, teammate}` | ✅ 对齐，冲突模式可用 |
| `POST /ai/import-guide` | `api.ai.importGuide` + 新增 `applyGuideRun` | `apply_mode=append_selected` | ✅ 本轮补上 apply 封装 |
| `POST /trips/{id}/ai-runs/{run}/apply` | `api.ai.applyRun` | `replace_itinerary` / `append_selected` | ✅ 两种模式均已封装 |
| `GET /trips/{id}/revisions` | `api.trips.revisions` | 返回含 `diff_content` | ✅ 技术3 可渲染字段级 diff |
| `GET /ai/runs/{id}` | 未封装 | 返回 candidate_output / retry_count / error_code | ⚠️ 建议技术3 做「AI 运行详情/失败重试」时补 |

---

## 4. 联调缺陷清单

### D1（P0）generate 的 Prompt 输入结构与 Prompt 期望不一致

**现象**：`backend/app/services/ai_service.py` 的 generate 直接把 `run_input_snapshot` 作为 user_prompt，键为 `trip` / `additional_requirements`；而 Prompt v0.2/v0.3 约定输入是 `constraints` + `poi_candidates` + `member_preferences`。且 generate 流程**没有任何 POI 预查**（只有生成后的 `enrich_itinerary_pois` 回填）。

**影响**：
- 第 9 条「景点只能来自候选」实际无法执行；
- v0.3 若按「候选为空 → 全部 free_time」会误伤全部行程。

**已做（技术1）**：v0.3 增加 `B0 输入兼容`：
- 仅有 `trip` 时按字段映射为 `constraints`；
- `poi_candidates` 缺失/null → `B2b`：允许真实知名景点名，`poi_id` 必须为 null，由后端 enrich 回填；
- `poi_candidates=[]` → `B2a`：严格 free_time 降级。

**待技术2 决策（二选一）**：
- 方案 A（推荐，质量更高）：generate 前调用 `AmapClient.search_poi` 预查 3-5 个关键词（景点/博物馆/公园/美食），组装 `{constraints, poi_candidates, member_preferences}` 作为 user_prompt；无 key 或失败时降级为「不传候选」，由 B2b 兜底。
- 方案 B（成本最低）：保持现状，接受 B2b + 后置 enrich 校验（L3 只能事后告警）。

### D2（P0）replan 未预查 `candidate_replacements`

**现象**：`generate_replan_candidate` 直接使用请求里的 `candidate_replacements`，前端若不传就是 `[]`。当前前端调 replan 只传 `adjustment_requirements/after_time`。

**影响**：全天降雨场景没有室内候选，模型只能按 R2a 全部降级为 free_time，体验差。

**已做（技术1）**：
- v0.3 区分 `R2a（空数组=预查无结果）` 与 `R2b（缺失=未预查）`，未预查时允许真实室内场所名 + `poi_id=null`；
- 前端 `api.ai.replan` 已支持透传 `trigger` 与 `candidate_replacements`。

**待技术2**：在 replan 服务里按 `trigger.reason_type` 预查候选：
- `rain` → 关键词「博物馆/美术馆/商场/茶馆/室内」
- `closed` → 同类型替代
- `queue` → 同区域低排队同类
- 查询失败或无 key → 传 `[]`（触发 R2a 安全降级）

### D3（P1）后端 Prompt 版本仍为 v0.2

`ai_service.py` 中 generate / replan / revise / explain-diff 的 `prompt_version` 均为 `"v0.2"`。v0.3 已交付，需技术2 确认后切到 `v0.3`，并跑一次 `real_ai_week3_smoke.py` 对比 `retry_count`。

### D4（P1）成员接口缺昵称

`GET /trips/{id}/members` 只返回 `user_id/role`，前端 `mapApiWorkspace` 只能用 `成员 {user_id}` 占位。需技术2 补 `display_name`（join users）或在技术3 侧接 `/auth/me` 缓存。

### D5（已修复，技术1）前端契约缺口

| 缺口 | 修复 |
|---|---|
| replan 未传 `trigger` / `candidate_replacements` | 新增可选参数，透传后端 |
| replan 丢弃 `diff` / `retry_count` | 返回值与 `ReplanResult` 类型补充 |
| 攻略候选无法 apply | 新增 `api.ai.applyGuideRun(..., selectedCandidateIds)` |
| 错误无结构 | 新增 `ApiError{status, code, detail}`，409 时 `detail` 含 `submitted_version/current_version`，可直接驱动冲突弹窗 |

### D6（语义确认）预算为 0 = 未设置

`trip_validation` 仅对 `budget > 0` 做上限校验；`itinerary_snapshot` 在 `total_budget` 为空时写 0。因此 **0 统一表示「未设置预算」**，不是零元游。已在 Prompt B3/V3 固化，需技术2 在产品文案中确认。

---

## 5. 边界用例与验收标准

| 编号 | 场景 | 输入 | 期望 | 校验层 |
|---|---|---|---|---|
| B1 | 极端预算（2人3天 600 元） | 候选含付费景点 | 总估算≤600；每天≥1餐；无付费演出；days 完整 | Prompt + `BUDGET_EXCEEDED` |
| B2 | 候选不足/未提供 | 候选缺失 | 真实景点名 + `poi_id=null`；不虚构 | Prompt B2b + L3 enrich |
| B3 | 预算 0 | amount=0 | 正常生成，不压缩 | `trip_validation` |
| B4 | 多人偏好冲突 | 博物馆 vs 美食 | 每天各至少 1 项双方偏好 | Prompt B4 |
| R1 | 全天降雨 | `after_time=00:00` | 当天全换室内；其他天 ID 不变 | activity_id 校验 |
| R2 | 替换候选不足 | `[]` | free_time 补位，不编造 | Prompt R2a |
| R3 | 连续两天降雨 | weather.tomorrow 暴雨 | 只改当天 + summary 提示次日 | activity_id 校验 |
| R4 | 队友已替换目标 | target id 不存在 | 忽略该项，不报错 | Prompt R4 |
| V1 | 预算 4500→800 | 4人3天 | 不删整天；说明最低可行差额 | activity_id 校验 |
| V2 | 预算上调 | 4500→6000 | 空 diff，行程不变 | diff 校验 |
| V3 | 预算→0 | amount=0 | 不压缩 | `trip_validation` |
| V4 | 队友改过 Day3 | 仅改 Day1 预算 | Day3 完全不动 | activity_id 校验 |
| M1 | 双人改不同天 | 顺序 apply | 双方均通过 | activity_id 校验 |
| M2 | 双人改同一活动不同字段 | 合并 | ID 稳定，合并成功 | activity_id 校验 |
| M3 | 双人同删同一条 | 合并 | `ID_MISSING` 被检出，返回 409 | activity_id 校验 |

---

## 6. 本地验证

```powershell
cd "c:\Users\15898\Desktop\项目文件夹"
python smoke_test_v04.py            # 23 项：Prompt lint + 校验器边界 + 规则边界
python smoke_test_v04.py --prompt   # 只校验 v0.3 Prompt 能否被后端 loader 正则提取
```

当前结果：`23 passed, 0 failed`。

Prompt lint 使用与 `backend/app/agent_contracts/loader.py` 完全相同的正则，确保 v0.3 可被后端直接加载。

---

## 7. 剩余阻塞与分工

| 阻塞 | 归属 | 解除条件 |
|---|---|---|
| 切 v0.3 并跑真实 DeepSeek | 技术2 | 设置 `DEEPSEEK_API_KEY`，改 4 处 `prompt_version`，跑 `real_ai_week3_smoke.py`，对比 retry_count |
| POI 预查（D1/D2） | 技术2 | 按 §4 方案 A/B 定稿 |
| 双人真实联调（409、rebase、权限） | 技术1 + 技术2 | Tailscale 打通后，两个账号同时操作同一行程 |
| 前端 diff / 冲突弹窗渲染 | 技术3 | 使用 `replan.diff` / `ReviseResult.diff` / `ApiError.detail` |
| 成员昵称 | 技术2 + 技术3 | D4 方案定稿 |

---

## 8. 本轮变更文件

| 文件 | 类型 |
|---|---|
| `docs/prompts/行程生成Prompt-v0.3.md` | 新增（边界强化 + 输入兼容） |
| `docs/prompts/行中重排Prompt-v0.3.md` | 新增（全天降雨 + 候选降级 + 多人并发） |
| `docs/prompts/修订Prompt-v0.3.md` | 新增（极端预算 + 空 diff + 多人并发） |
| `smoke_test_v04.py` | 新增（23 项边界回归） |
| `frontend/src/api/client.ts` | 修改（replan 参数/返回、applyGuideRun、ApiError） |
| `frontend/src/types.ts` | 修改（ReplanResult 增加 diff / retryCount） |
| `docs/04-Week4联调核对与边界用例.md` | 新增（本文档） |
