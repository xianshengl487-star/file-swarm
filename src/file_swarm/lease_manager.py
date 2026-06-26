from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field


@dataclass(slots=True)
class LeaseManager:
    active_by_slot: dict[str, int] = field(default_factory=dict)
    owners_by_slot: dict[str, set[str]] = field(default_factory=dict)
    _semaphores: dict[str, asyncio.Semaphore] = field(default_factory=dict, init=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    def is_leased(self, slot_id: str) -> bool:
        return self.active_by_slot.get(slot_id, 0) > 0

    def can_acquire(self, slot_id: str, max_concurrent_tasks: int) -> bool:
        return self.active_by_slot.get(slot_id, 0) < max_concurrent_tasks

    async def try_acquire(self, slot_id: str, task_id: str, max_concurrent_tasks: int = 1) -> bool:
        async with self._lock:
            if self.active_by_slot.get(slot_id, 0) >= max_concurrent_tasks:
                return False
            self.active_by_slot[slot_id] = self.active_by_slot.get(slot_id, 0) + 1
            self.owners_by_slot.setdefault(slot_id, set()).add(task_id)
            return True

    def acquire(self, slot_id: str, max_concurrent_tasks: int) -> None:
        if not self.can_acquire(slot_id, max_concurrent_tasks):
            raise RuntimeError(f"slot {slot_id} is fully leased")
        self.active_by_slot[slot_id] = self.active_by_slot.get(slot_id, 0) + 1

    def release(self, slot_id: str, task_id: str | None = None) -> None:
        current = self.active_by_slot.get(slot_id, 0)
        if current <= 0:
            return
        owners = self.owners_by_slot.get(slot_id, set())
        if task_id is not None:
            if owners and task_id not in owners:
                raise RuntimeError(f"slot {slot_id} is leased by another task")
            owners.discard(task_id)
        if current <= 1:
            self.active_by_slot.pop(slot_id, None)
            self.owners_by_slot.pop(slot_id, None)
        else:
            self.active_by_slot[slot_id] = current - 1
            if owners:
                self.owners_by_slot[slot_id] = owners

    def _semaphore(self, slot_id: str, max_concurrent_tasks: int) -> asyncio.Semaphore:
        semaphore = self._semaphores.get(slot_id)
        if semaphore is None:
            semaphore = asyncio.Semaphore(max_concurrent_tasks)
            self._semaphores[slot_id] = semaphore
        return semaphore

    @asynccontextmanager
    async def hold(self, slot_id: str, max_concurrent_tasks: int) -> None:
        semaphore = self._semaphore(slot_id, max_concurrent_tasks)
        await semaphore.acquire()
        self.active_by_slot[slot_id] = self.active_by_slot.get(slot_id, 0) + 1
        try:
            yield
        finally:
            self.release(slot_id)
            semaphore.release()
