# 行伴前端

## 启动

```bash
cd frontend
npm install
npm run dev
```

启动后打开 <http://localhost:5173>。前端默认连接本机 FastAPI，后端未启动时会给出明确的连接提示。

## 接入 FastAPI

如需修改后端地址，复制 `.env.example` 为 `.env.local`：

```env
VITE_API_BASE_URL=auto
```

`auto` 会自动使用当前网页的主机名连接 `8000` 端口：电脑打开 localhost 时连接本机，手机通过局域网 IP 或 Tailscale 打开时连接同一地址下的后端。

行程工作台中的网页地图使用高德 JS API。需要在高德开放平台创建一个“Web端（JS API）”应用 Key，并将 Key 和安全密钥填入 `.env.local`：

```env
VITE_AMAP_JS_KEY=你的Web端Key
VITE_AMAP_SECURITY_CODE=你的安全密钥
```

这组凭据与后端调用 POI/路径规划所用的“Web服务”Key不是同一种 Key；修改环境变量后需要重新启动前端开发服务器。

通常不需要填写 `VITE_ACCESS_TOKEN`：使用页面内登录或注册后，Token 会安全地保存在当前浏览器的本地存储中。

统一 API Client 已覆盖当前 FastAPI OpenAPI 中的认证、行程、成员、活动、AI、地图天气、需求、协作消息、费用、手帐记录、记忆和用户设置接口。页面不再加载 Mock 行程数据。
