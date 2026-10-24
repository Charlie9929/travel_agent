# AI 多人旅行规划助手后端

本目录是技术 2 负责的 FastAPI、PostgreSQL、多人权限、外部 API 和 Agent 工程化底座。

## 当前能力

- `/api/v1` 统一版本前缀和统一响应格式。
- 用户注册、登录和 Bearer Token 鉴权。
- Trip、成员、活动 CRUD。
- `version` 乐观锁、轮询读取和冲突记录。
- DeepSeek JSON 模式基础封装及 Fake LLM。AI 结果经 Schema 校验（失败时最多自动修复 2 次）和高德 POI 回填后直接事务落库。
- 高德 POI 限流时自动节流、退避重试，并可从失败的 AI 运行继续回填，无需重新消耗 LLM 额度。
- 高德 POI、步行、骑行、驾车和公交路线适配器。
- 和风天气城市查询及每日天气适配器。
- SQLAlchemy 异步会话和 Alembic 迁移环境。
- 技术一的 Prompt 与 `itinerary.schema.json` 已纳入工程。

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
python scripts/llm_smoke.py  # 需要真实 DeepSeek Key
```

更复杂的业务规则修复、行中重排和攻略导入属于后续开发；当前已提供初次生成的 JSON 修复循环、Schema 校验、POI 回填和落库链路。
