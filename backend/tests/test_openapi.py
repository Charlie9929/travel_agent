from app.main import app


def test_expected_routes_are_registered() -> None:
    paths = app.openapi()["paths"]
    assert "/health" in paths
    assert "/api/v1/auth/register" in paths
    assert "/api/v1/trips" in paths
    assert "/api/v1/trips/{trip_id}/activities/reorder" in paths
    assert "/api/v1/ai/generate" in paths
    assert "/api/v1/ai/runs/{ai_run_id}/confirm" not in paths
    assert "/api/v1/ai/runs/{ai_run_id}/retry-apply" in paths
    assert "/api/v1/map/poi" in paths
    assert "/api/v1/weather" in paths


def test_trip_detail_includes_days_and_activities() -> None:
    openapi = app.openapi()
    trip_detail = openapi["components"]["schemas"]["TripDetail"]
    trip_day = openapi["components"]["schemas"]["TripDayRead"]

    assert "days" in trip_detail["required"]
    assert "activities" in trip_day["required"]
