from app.main import app


def test_expected_routes_are_registered() -> None:
    paths = app.openapi()["paths"]
    expected_methods = {
        "/health": {"get"},
        "/api/v1/auth/register": {"post"},
        "/api/v1/auth/login": {"post"},
        "/api/v1/auth/me": {"get"},
        "/api/v1/trips": {"get", "post"},
        "/api/v1/trips/{trip_id}": {"get", "put", "delete"},
        "/api/v1/trips/{trip_id}/members": {"get"},
        "/api/v1/trips/{trip_id}/members/invite": {"post"},
        "/api/v1/trips/{trip_id}/members/{user_id}": {"put", "delete"},
        "/api/v1/trips/{trip_id}/members/leave": {"post"},
        "/api/v1/trips/{trip_id}/share-code": {"post"},
        "/api/v1/trips/share/{share_code}": {"get"},
        "/api/v1/trips/join": {"post"},
        "/api/v1/trips/{trip_id}/activities": {"post"},
        "/api/v1/trips/{trip_id}/activities/{activity_id}": {"put", "delete"},
        "/api/v1/trips/{trip_id}/activities/reorder": {"put"},
        "/api/v1/trips/{trip_id}/revisions": {"get"},
        "/api/v1/trips/{trip_id}/revisions/{revision_id}": {"get"},
        "/api/v1/trips/{trip_id}/validate": {"post"},
        "/api/v1/ai/generate": {"post"},
        "/api/v1/ai/replan": {"post"},
        "/api/v1/ai/revise": {"post"},
        "/api/v1/ai/explain-diff": {"post"},
        "/api/v1/ai/import-guide": {"post"},
        "/api/v1/ai/runs/{ai_run_id}": {"get"},
        "/api/v1/ai/runs/{ai_run_id}/retry-apply": {"post"},
        "/api/v1/trips/{trip_id}/ai-runs/{ai_run_id}/apply": {"post"},
        "/api/v1/map/poi": {"get"},
        "/api/v1/map/route": {"get"},
        "/api/v1/weather": {"get"},
    }
    for path, methods in expected_methods.items():
        assert path in paths
        assert methods <= set(paths[path])
    assert "/api/v1/ai/runs/{ai_run_id}/confirm" not in paths


def test_trip_detail_includes_days_and_activities() -> None:
    openapi = app.openapi()
    trip_detail = openapi["components"]["schemas"]["TripDetail"]
    trip_day = openapi["components"]["schemas"]["TripDayRead"]

    assert "days" in trip_detail["required"]
    assert "activities" in trip_day["required"]
