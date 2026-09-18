import asyncio

from test_agent_runtime_phase1 import (
    FakeLLM, _URL_RESULTS, build_manager, offline_gate,
)
from services.agent_runtime.contracts.result import ResultStatus


def test_halt_cancels_model_wait_and_prevents_new_work(offline_gate):
    async def scenario():
        started = asyncio.Event()
        stopped = asyncio.Event()

        class WaitingLLM(FakeLLM):
            async def complete(self, *, system, content):
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    stopped.set()

        manager, audit, ledger, broker, registry = build_manager(
            _URL_RESULTS, WaitingLLM(), offline_gate
        )
        running = asyncio.create_task(manager.run_task("research", "compare"))
        await asyncio.wait_for(started.wait(), timeout=1)
        await manager.halt_all("user stop")
        result = await asyncio.wait_for(running, timeout=1)
        assert stopped.is_set()
        assert result.status == ResultStatus.FAILED
        assert "CANCELLED" in result.errors
        assert broker.context(result.task_id) is None
        count = len(audit.records)
        try:
            await manager.run_task("more", "work")
        except RuntimeError as error:
            assert "halted" in str(error)
        else:
            raise AssertionError("Halted manager accepted new work")
        assert len(audit.records) == count

    asyncio.run(scenario())