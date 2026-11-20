# 免费部署操作说明

这套项目不是只上传前端就结束了，还需要数据库和后端。免费方案分成三部分：

```text
Supabase       = 云端 PostgreSQL 数据库
Render         = 云端 FastAPI 后端
Cloudflare Pages = 云端 React 前端网页
```

三者都是网站服务，不需要下载 App，也不需要在 WSL 安装它们。只需要浏览器、GitHub
账号和对应网站账号。

## 总顺序

必须按这个顺序操作：

```text
1. Supabase 创建数据库
2. Render 部署后端
3. Cloudflare Pages 部署前端
4. 把 Cloudflare Pages 地址填回 Render
5. 浏览器测试注册、登录和行程功能
```

本地的 `render.yaml` 和 `backend/Dockerfile` 只是部署配置。Render 从 GitHub 读取它们，
所以真正开始部署前，需要先把这些文件提交并 push 到 GitHub。

## 一、Supabase：创建云端数据库

### 1. 打开网站

浏览器打开：

```text
https://supabase.com/dashboard
```

点击 `Sign in`，可以使用 GitHub 登录。Supabase 是数据库托管网站，不是需要安装的软件。

### 2. 创建项目

登录后：

1. 点击 `New project`。
2. 选择自己的 Organization；如果没有，就按提示创建一个。
3. `Name` 填：`travel-agent`。
4. 设置一个数据库密码，并保存到本地安全位置。
5. Region 选择离用户较近的区域；有 Singapore 就可以选择 Singapore。
6. 点击 `Create new project`，等待项目变成可用状态。

### 3. 复制数据库连接串

进入项目后：

1. 点击页面顶部的 `Connect`。
2. 选择 `Session pooler`，不要手动拼主机名。
3. 复制 PostgreSQL 连接串。

复制出来的内容通常类似：

```text
postgresql://postgres.项目编号:数据库密码@...pooler.supabase.com:5432/postgres
```

本项目使用 `asyncpg`，因此只需要把开头改成：

```text
postgresql+asyncpg://postgres.项目编号:数据库密码@...pooler.supabase.com:5432/postgres
```

其他部分不要改。如果数据库密码中有 `@`、`#`、`?`、空格等特殊字符，连接串可能需要
编码；最简单的做法是使用只包含英文、数字的数据库密码。

这个连接串后面要填到 Render 的 `DATABASE_URL`，不要发到群里，也不要提交到 GitHub。

Supabase Free 目前适合课程演示和测试，数据库容量有限，长期低活跃时可能暂停项目；
项目重新使用时可以在 Supabase 控制台恢复。

## 二、Render：部署 FastAPI 后端

### 1. 打开网站

浏览器打开：

```text
https://dashboard.render.com
```

点击 `Get Started` 或 `Sign in`，使用 GitHub 登录。Render 也是网站服务，不需要下载。

### 2. 连接 GitHub 仓库

登录后：

1. 点击右上角 `New`。
2. 选择 `Blueprint`。
3. 授权 Render 访问 GitHub。
4. 找到 `Charlie9929/travel_agent`，点击 `Connect`。
5. 分支选择 `main`。
6. Render 会自动读取仓库根目录的 `render.yaml`。

### 3. 填写后端变量

创建 Blueprint 时，重点填写：

| 变量 | 填什么 |
|---|---|
| `DATABASE_URL` | 刚才从 Supabase 复制并改好前缀的连接串 |
| `JWT_SECRET` | Render 会自动生成，不要手动改 |
| `DEEPSEEK_API_KEY` | 暂时没有就留空 |
| `AMAP_API_KEY` | 暂时没有就留空 |
| `QWEATHER_API_HOST` | 暂时没有就留空 |
| `QWEATHER_API_KEY` | 暂时没有就留空 |
| `QWEATHER_JWT_TOKEN` | 暂时没有就留空 |

`LLM_USE_FAKE` 已经设置为 `true`。没有 DeepSeek Key 时，后端仍能启动，但 Agent 使用
的是 Fake 模式，不能生成真实 AI 行程。

填写完后点击 `Apply` 或 `Deploy Blueprint`，等待 Render 完成构建。

### 4. 找到后端网址

部署成功后，在 Render 服务页面找到 `URL`，格式类似：

```text
https://travel-agent-api.onrender.com
```

在浏览器或 WSL 中检查：

```bash
curl https://travel-agent-api.onrender.com/health
```

返回包含 `"service":"ok"` 和 `"database":"ok"`，说明后端和数据库连接成功。

如果第一次访问很慢，这是免费 Render 服务休眠后的正常启动过程，等待约一分钟再试。

## 三、Cloudflare Pages：部署 React 前端

### 1. 打开网站

浏览器打开：

```text
https://dash.cloudflare.com
```

登录或注册 Cloudflare 账号。Cloudflare Pages 用来托管前端网页，不需要下载。

### 2. 创建 Pages 项目

登录后：

1. 进入 `Workers & Pages`。
2. 点击 `Create application`。
3. 选择 `Pages`。
4. 选择 `Connect to Git`，连接 GitHub。
5. 选择 `Charlie9929/travel_agent`。
6. 生产分支选择 `main`。

构建设置填写：

```text
Root directory: frontend
Build command: npm ci && npm run build
Build output directory: dist
```

### 3. 添加前端环境变量

在环境变量区域添加：

```text
VITE_API_BASE_URL=https://travel-agent-api.onrender.com/api/v1
```

把域名替换成你在 Render 页面看到的真实后端地址。

如果暂时没有高德前端 Key，可以先不填；但地图显示和部分地图跳转功能可能不可用。
有 Key 时再添加：

```text
VITE_AMAP_JS_KEY=<高德 Web 端 JS API Key>
VITE_AMAP_SECURITY_CODE=<高德 JS API 安全密钥>
```

注意：`VITE_AMAP_JS_KEY` 是前端 JS 地图 Key，和 Render 中的 `AMAP_API_KEY` 不是同一个
配置项。

点击 `Save and Deploy`，等待构建完成。成功后 Cloudflare 会给一个类似这样的地址：

```text
https://travel-agent.pages.dev
```

## 四、把前端地址填回后端

回到 Render：

1. 打开 `travel-agent-api` 服务。
2. 进入 `Environment`。
3. 找到 `CORS_ORIGINS`。
4. 填入 Cloudflare Pages 的完整地址，必须是 JSON 数组：

```json
["https://你的项目.pages.dev"]
```

5. 保存并重新部署后端。

不要写成下面这样：

```text
https://你的项目.pages.dev
```

也不要在地址末尾加 `/`。

## 五、最后测试

1. 打开 Cloudflare Pages 地址。
2. 注册或登录账号。
3. 创建一个简单行程。
4. 检查页面是否能请求后端。
5. 如果页面报 CORS 错误，优先检查 Render 的 `CORS_ORIGINS`。
6. 如果页面打开但 Agent 没有真实回答，检查 `DEEPSEEK_API_KEY` 和 `LLM_USE_FAKE`。

## API Key 由其他组员保管时怎么做

这不会阻止前端和后端部署。其他组员可以直接在 Render 的 `Environment` 中填写：

- `DEEPSEEK_API_KEY`
- `AMAP_API_KEY`
- `QWEATHER_API_HOST`
- `QWEATHER_API_KEY`

高德前端 Key 则填写到 Cloudflare Pages 的环境变量中。修改环境变量后需要重新部署对应服务。

Key 不要写到代码、`.env`、`render.yaml` 或 GitHub 仓库里。

## 免费方案限制

- Render Free 后端闲置 15 分钟后会休眠，首次访问会慢。
- Render 的本地上传目录不是永久存储，头像和旅行照片重启后可能丢失。
- Supabase Free 数据库容量有限，低活跃时可能暂停。
- 没有 DeepSeek Key 时只能使用 Fake Agent。
- 没有高德或和风天气 Key 时，对应地图、路线、天气功能不能完整使用。
