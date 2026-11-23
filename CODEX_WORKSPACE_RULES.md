# 工作区行动前必须遵守

## 目录与运行环境

- WSL 仓库是主工作区：`/home/starknight/projects/软工旅行助手/travel_agent`
- D 盘副本用于手机端与 Android 构建：`/mnt/d/Projects/travel_agent_clean`
- Git、Node、npm、Python、pytest、ruff、后端命令统一在 WSL 中执行，不使用 Windows 版本。

## 同步规则

- WSL 仓库与 D 盘副本必须保持同步。任何修改后，检查并同步对应的 `backend/`、`frontend/`、`deploy/`、`docs/` 和配置文件。
- WSL 是版本控制主源；Git 提交、拉取、合并和 push 只在 WSL 仓库执行。
- 每一次完成代码修改后，都必须在回复中给出对应的 push 命令行；命令只提交本次相关文件。
- 同步前先检查 D 盘是否有本地修改；发现修改时先比较并报告，不直接覆盖。
- 不同步或覆盖本地环境内容：`.env*`、`backend/.venv/`、`frontend/node_modules/`、`frontend/dist/`、缓存目录、上传文件和个人编辑器配置。
- D 盘副本当前没有 `.git`，不能在 D 盘执行 `git pull`；需要从 WSL 主仓库同步文件。

## 安全与协作

- 不删除文件、不重置本地修改、不强制覆盖分支，除非用户明确确认。
- 不把 API Key、数据库密码、JWT、个人配置写入 Git 或同步到公开仓库。
- 修改前先检查当前分支、工作区状态和相关文件差异；修改后运行与改动相关的测试或构建。
- 后端 API 字段、数据库结构和 Agent 行为不能擅自改动；需要变更时先记录影响范围。
