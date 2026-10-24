from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.ai_service import _mark_run_failed


@pytest.mark.asyncio
async def test_failed_run_is_reloaded_by_saved_id_after_rollback() -> None:
    failed_run = SimpleNamespace(
        status="running",
        error_code=None,
        retry_count=0,
        candidate_output=None,
    )
    session = SimpleNamespace(
        rollback=AsyncMock(),
        get=AsyncMock(return_value=failed_run),
        commit=AsyncMock(),
    )

    await _mark_run_failed(  # type: ignore[arg-type]
        session,
        run_id=4,
        error_code="AGENT_OUTPUT_INVALID",
        retry_count=2,
        candidate={"days": []},
        validation_errors=[{"path": "days", "message": "invalid"}],
    )

    session.get.assert_awaited_once()
    assert failed_run.status == "failed"
    assert failed_run.retry_count == 2
    assert failed_run.candidate_output["validation_errors"][0]["path"] == "days"
