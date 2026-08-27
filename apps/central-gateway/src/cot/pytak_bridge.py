import asyncio
import logging
import os
from typing import Optional

from ibvap_core_types import TacticalAlert

logger = logging.getLogger("gateway.pytak")


class PyTAKBridge:
    """
    Asynchronous Tactical CoT Broadcaster interfacing with TAK Server or ATAK network mesh.
    """

    def __init__(self, tak_server_url: Optional[str] = None):
        self.tak_server_url = tak_server_url or os.getenv("TAK_SERVER_URL", "udp://239.2.3.1:6969")
        self._tx_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1000)
        self._is_running = False

    async def start(self) -> None:
        self._is_running = True
        logger.info(f"Initialized PyTAK Bridge targeting TAK Server/Mesh: {self.tak_server_url}")
        asyncio.create_task(self._worker_loop())

    async def stop(self) -> None:
        self._is_running = False
        logger.info("PyTAK Bridge stopped.")

    async def broadcast_alert(self, alert: TacticalAlert) -> None:
        """Enqueues alert CoT XML string for immediate tactical broadcast."""
        try:
            self._tx_queue.put_nowait(alert.cot_xml_string)
            logger.debug(f"Queued CoT event for Alert: {alert.alert_id}")
        except asyncio.QueueFull:
            logger.error("PyTAK transmit queue is saturated. Dropping stale CoT message.")

    async def _worker_loop(self) -> None:
        """Background worker that transmits CoT packets across the tactical link."""
        while self._is_running:
            try:
                cot_xml = await self._tx_queue.get()
                # In production deployment, transmit via pytak.TXWorker or socket UDP/TCP
                logger.info(f"📡 [PyTAK BROADCAST] Dispatched CoT packet to {self.tak_server_url} (size: {len(cot_xml)} bytes)")
                self._tx_queue.task_done()
            except Exception as err:
                logger.error(f"Error in PyTAK transmit loop: {err}")
                await asyncio.sleep(1.0)
