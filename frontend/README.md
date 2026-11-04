# 山行前端

## 启动

```bash
cd frontend
npm install
npm run dev
```

默认使用 Mock Data，启动后打开 <http://127.0.0.1:5173> 即可查看四个一级页面。

## 接入 FastAPI

复制 `.env.example` 为 `.env`，填写后端 Token，并将 `VITE_USE_MOCKS` 改为 `false`：

```env
VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
VITE_USE_MOCKS=false
VITE_ACCESS_TOKEN=登录接口返回的 token
```

当前前端已经通过统一 API Client 接入登录、行程、成员、活动、版本记录、AI 重排/应用、地图和天气接口。后端未提供的功能入口会保留页面提示，具体清单见 `docs/前端联调需要后端补充或确认.md`。
