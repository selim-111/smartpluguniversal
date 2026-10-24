"""
Polling engine for TP-Link HS110 device.
Periodically queries the device and invokes a callback with the latest status.
"""

import logging
import threading
import time
from typing import Callable, Optional

from core.device import HS110Device
from core.models import DeviceStatus

logger = logging.getLogger(__name__)


class DevicePoller:
    """
    Periodically polls an HS110 device for status updates.

    Runs in a separate daemon thread. Provides the latest data
    via the `latest_data` property and optional callback.

    Usage:
        device = HS110Device("192.168.1.100")

        def on_update(status: DeviceStatus):
            print(status.to_dict())

        poller = DevicePoller(device, interval=5.0, callback=on_update)
        poller.start()

        # ... later
        poller.stop()
    """

    def __init__(
        self,
        device: HS110Device,
        interval: float = 5.0,
        callback: Optional[Callable[[DeviceStatus], None]] = None,
    ):
        """
        Initialize the poller.

        Args:
            device: HS110Device instance to poll.
            interval: Polling interval in seconds (default 5.0).
            callback: Optional function called with DeviceStatus on each poll.
        """
        self.device = device
        self.interval = interval
        self.callback = callback

        self._latest_data: Optional[DeviceStatus] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

    @property
    def latest_data(self) -> Optional[DeviceStatus]:
        """Get the most recent device status snapshot (thread-safe)."""
        with self._lock:
            return self._latest_data

    @property
    def is_running(self) -> bool:
        """Whether the poller is currently running."""
        return self._running

    def start(self):
        """Start the polling loop in a background daemon thread."""
        if self._running:
            logger.warning("Poller is already running")
            return

        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_loop,
            name=f"poller-{self.device.ip}",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            f"Polling started for {self.device.ip} "
            f"every {self.interval}s"
        )

    def stop(self):
        """Stop the polling loop and wait for the thread to finish."""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self.interval + 2)

        logger.info(f"Polling stopped for {self.device.ip}")

    def _poll_loop(self):
        """Internal polling loop — runs in background thread."""
        while self._running and not self._stop_event.is_set():
            try:
                status = self.device.get_device_status()

                with self._lock:
                    self._latest_data = status

                if self.callback:
                    try:
                        self.callback(status)
                    except Exception as cb_err:
                        logger.error(f"Callback error: {cb_err}")

            except Exception as e:
                logger.error(f"Poll error for {self.device.ip}: {e}")
                error_status = DeviceStatus(online=False, error=str(e))

                with self._lock:
                    self._latest_data = error_status

                if self.callback:
                    try:
                        self.callback(error_status)
                    except Exception:
                        pass

            # Wait for interval or until stop is requested
            self._stop_event.wait(timeout=self.interval)

    def __enter__(self):
        """Context manager support — start on enter."""
        self.start()
        return self

    def __exit__(self, *args):
        """Context manager support — stop on exit."""
        self.stop()
