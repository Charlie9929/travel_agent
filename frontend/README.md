# 山行前端

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
VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
```

通常不需要填写 `VITE_ACCESS_TOKEN`：使用页面内登录或注册后，Token 会安全地保存在当前浏览器的本地存储中。

统一 API Client 已覆盖当前 FastAPI OpenAPI 中的认证、行程、成员、活动、AI、地图天气、需求、协作消息、费用、手帐记录、记忆和用户设置接口。页面不再加载 Mock 行程数据。
