import asyncio

from file_swarm.lease_manager import LeaseManager


def test_lease_manager_exclusive_hold_blocks_second_worker() -> None:
    lease = LeaseManager()
    observed: list[int] = []

    async def worker() -> None:
        async with lease.hold("slot-1", 1):
            observed.append(lease.active_by_slot["slot-1"])
            await asyncio.sleep(0.05)

    async def run() -> None:
        await asyncio.gather(worker(), worker())

    asyncio.run(run())

    assert observed == [1, 1]
    assert lease.active_by_slot == {}
