# 行伴后端

本目录是技术 2 负责的 FastAPI、PostgreSQL、多人权限、外部 API 和 Agent 工程化底座。

## 当前能力

- `/api/v1` 统一版本前缀和统一响应格式。
- 用户注册、登录和 Bearer Token 鉴权。
- Trip、成员、活动 CRUD。
- `version` 乐观锁、轮询读取和冲突记录。
- DeepSeek `deepseek-chat` JSON 模式基础封装及 Fake LLM。模型输出先经过常见字段别名与 JSON 包装规范化，再进行严格 Schema 校验；失败时最多自动修复 2 次。
- 技术一的行中重排、行前修订和差异说明 Prompt v0.2 已分别接入 `/api/v1/ai/replan`、`/api/v1/ai/revise` 与 `/api/v1/ai/explain-diff`。重排/修订先返回候选方案，经 Schema 和业务规则校验后保存；用户再通过 `/api/v1/trips/{trip_id}/ai-runs/{ai_run_id}/apply` 确认应用。
- 攻略抽取 Prompt v0.1 已接入 `/api/v1/ai/import-guide`；用户选择候选后，以 `append_selected` 模式调用统一 apply 接口写入活动。
- 初次生成会将高德 POI 候选预查结果按技术一 Prompt 契约传给 Agent，并在生成后再次用高德结果回填 POI ID、坐标和行政区划。
- 高德 POI 限流时自动节流、退避重试，并可从历史失败的 AI 运行继续回填，无需重新消耗 LLM 额度。
- 高德 POI、步行、骑行、驾车和公交路线适配器。
- 和风天气城市查询及每日天气适配器；生成后按天回填天气并随行程保存，支持重试、短期缓存和缓存降级。
- 高德或和风天气暂时不可用时，主行程仍可校验并落库，响应通过 `integration_warnings` 明确说明降级情况；DeepSeek 失败时不伪造结果，原有行程保持不变。
- SQLAlchemy 异步会话和 Alembic 迁移环境。
- 技术一的 Prompt 与 `itinerary.schema.json` 已纳入工程。
- 大厅消息列表、发送、轮询、未读数与已读位置；只有明确 `@Agent` 或 `ask_agent=true` 才触发 Agent，行程和成员变化使用结构化系统消息。
- 按行程隔离的 Agent 私聊会话、消息历史、回复状态和单条消息轮询；群聊 Agent 只读取群聊、当前行程和已共享需求，私聊只读取当前用户自己的需求。
- 旅行需求填写、owner 代填、共享摘要发布与撤回；成员列表已返回昵称、头像、需求状态和代填来源。
- 用户搜索与可邀请状态、个人资料和 Agent/记忆设置。
- 用户主动创建的记忆簿 CRUD，以及行程高光的创建、查询和编辑。
- 费用记录、等额或比例分摊、结算方案计算和手动结算标记；不涉及真实支付。
- 版本记录返回稳定的 `summary`、`before`、`after`、`changes` 展示字段；历史版本只读，不提供恢复接口。
- AI 修订和重排候选额外返回 `cost_info`、`changed_items`、`kept_items`，确认应用后返回最终行程与新版本号。

## 本地启动

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

打开 <http://127.0.0.1:8000/docs> 查看接口。

## 外部服务配置

在 `.env` 中填写：

- `DEEPSEEK_API_KEY`：DeepSeek API 密钥；`LLM_USE_FAKE=false` 时启用真实调用。
- `AMAP_API_KEY`：高德 Web 服务 API Key。
- `QWEATHER_API_HOST`：和风天气控制台分配的专属 API Host。
- `QWEATHER_API_KEY` 或 `QWEATHER_JWT_TOKEN`：根据 `QWEATHER_AUTH_TYPE` 二选一。

不要提交 `.env`。仓库只保留 `.env.example`。

## 验证

```bash
ruff check .
pytest

# 真实 PostgreSQL 双账号、权限、轮询、409、保存加载测试；整个事务最终回滚
RUN_DB_INTEGRATION=1 pytest -q tests/test_backend_e2e_db.py

# 真实 DeepSeek + 高德 + 和风天气测试；消耗少量额度，整个事务最终回滚
RUN_LIVE_EXTERNAL=1 pytest -q tests/test_live_external_e2e.py
```

当前已提供初次生成、行前修订、行中重排、差异说明和攻略抽取的 JSON 修复循环、Schema 校验、技术一业务校验器、候选确认应用、地图/天气回填和落库重载链路。
