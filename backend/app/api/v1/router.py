from fastapi import APIRouter

from app.api.v1.endpoints import (
    activities,
    ai,
    auth,
    collaboration,
    expenses,
    highlights,
    map,
    members,
    memories,
    requirements,
    trips,
    users,
    weather,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(trips.router)
api_router.include_router(members.router)
api_router.include_router(activities.router)
api_router.include_router(ai.router)
api_router.include_router(ai.trip_ai_router)
api_router.include_router(map.router)
api_router.include_router(weather.router)
api_router.include_router(users.router)
api_router.include_router(collaboration.router)
api_router.include_router(requirements.router)
api_router.include_router(memories.router)
api_router.include_router(expenses.router)
api_router.include_router(highlights.router)
