import asyncio
from typing import Dict

class IngestionBroadcaster:
    def __init__(self):
        # Maps job_ids to an asyncio.Queue to isolate user sessions
        self._queues: Dict[str, asyncio.Queue] = {}

    def get_queue(self, job_id: str) -> asyncio.Queue:
        if job_id not in self._queues:
            self._queues[job_id] = asyncio.Queue()
        return self._queues[job_id]

    async def publish(self, job_id: str, data: dict):
        if job_id in self._queues:
            await self._queues[job_id].put(data)

    def remove_queue(self, job_id: str):
        self._queues.pop(job_id, None)

# Global singleton instance
broadcaster = IngestionBroadcaster()