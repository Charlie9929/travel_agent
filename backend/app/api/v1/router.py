from fastapi import APIRouter

from app.api.v1.endpoints import activities, ai, auth, map, members, trips, weather

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(trips.router)
api_router.include_router(members.router)
api_router.include_router(activities.router)
api_router.include_router(ai.router)
api_router.include_router(ai.trip_ai_router)
api_router.include_router(map.router)
api_router.include_router(weather.router)
