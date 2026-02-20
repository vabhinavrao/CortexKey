"""
BLE EEG Reader — CortexKey v0.1
Receives EEG data from the ESP32 over Bluetooth Low Energy (BLE).

This module connects to the "CortexKey-EEG" BLE peripheral (ESP32 running
bioamp_ble_mock.ino) and receives a continuous stream of EEG samples via
GATT notifications. Samples are stored in the same EEGRingBuffer used by
the serial reader, so the rest of the pipeline is identical.

─────────────────────────────────────────────────────────────────────────────
BLE ARCHITECTURE (matches the ESP32 firmware)
─────────────────────────────────────────────────────────────────────────────

  Service UUID:  0000181a-0000-1000-8000-00805f9b34fb
  
  Characteristics:
  ┌─────────────────────────────────────────────────────────────────────────┐
  │ EEG Stream   (NOTIFY)  00002a59-...                                   │
  │   → 20 bytes per notification = 10 × int16_t little-endian samples    │
  │   → 25 notifications/sec = 250 samples/sec                            │
  │                                                                        │
  │ Profile Sel. (R/W)     00002a58-...                                   │
  │   → Write 1 byte (0-4) to switch mock user profile on-chip            │
  │   → 0=devesh, 1=abhinav, 2=sadaf, 3=impostor, 4=devesh_coerced       │
  └─────────────────────────────────────────────────────────────────────────┘

─────────────────────────────────────────────────────────────────────────────
DATA FORMAT
─────────────────────────────────────────────────────────────────────────────

  Each BLE notification payload is 20 bytes:
    [sample0_lo, sample0_hi, sample1_lo, sample1_hi, ... sample9_lo, sample9_hi]

  Each sample is a signed 16-bit little-endian integer in MICROVOLTS.
  No ADC conversion needed — the ESP32 firmware already generates μV values.

─────────────────────────────────────────────────────────────────────────────
DEPENDENCIES
─────────────────────────────────────────────────────────────────────────────

  pip install bleak

  bleak is a cross-platform BLE library (macOS, Windows, Linux) that uses
  the native Bluetooth stack (CoreBluetooth on macOS, WinRT on Windows).

─────────────────────────────────────────────────────────────────────────────
USAGE
─────────────────────────────────────────────────────────────────────────────

  from cortexkey.ble_reader import BLEEEGReader, scan_ble_devices
  
  # Scan for the ESP32
  devices = await scan_ble_devices()
  
  # Connect
  reader = BLEEEGReader()
  await reader.connect()  # auto-finds "CortexKey-EEG"
  
  # Read data
  signal = reader.get_window(duration_sec=4.0)
  
  # Switch profile (remote control of the ESP32)
  await reader.set_profile(1)  # switch to "abhinav"
  
  # Disconnect
  await reader.disconnect()
"""

import numpy as np
import asyncio
import struct
import threading
import time
import logging
from typing import Optional, Tuple, List, Dict

# Import bleak (BLE library) — installed via: pip install bleak
try:
    from bleak import BleakClient, BleakScanner
    BLEAK_AVAILABLE = True
except ImportError:
    BLEAK_AVAILABLE = False

# Reuse the same ring buffer from the serial reader
from .hardware_reader import EEGRingBuffer, SAMPLING_RATE

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────
# BLE UUIDs — must match the ESP32 firmware exactly
# ─────────────────────────────────────────────────────────

SERVICE_UUID             = "0000181a-0000-1000-8000-00805f9b34fb"
CHAR_EEG_STREAM_UUID     = "00002a59-0000-1000-8000-00805f9b34fb"
CHAR_PROFILE_SELECT_UUID = "00002a58-0000-1000-8000-00805f9b34fb"

# The advertised device name set in the ESP32 firmware
DEVICE_NAME = "CortexKey-EEG"

# Number of int16 samples per BLE notification (set in firmware)
SAMPLES_PER_PACKET = 10

# Profile names — index matches the byte written to the profile characteristic
PROFILE_NAMES = ["devesh", "abhinav", "sadaf", "impostor", "devesh_coerced"]


# ─────────────────────────────────────────────────────────
# BLE SCANNER — discover nearby CortexKey devices
# ─────────────────────────────────────────────────────────

async def _scan_ble_devices_async(timeout: float = 5.0) -> List[Dict]:
    """
    Scan for nearby BLE devices and return a list of discovered peripherals.

    Parameters
    ----------
    timeout : float
        How long to scan (seconds). 5s is usually enough for nearby devices.

    Returns
    -------
    list of dicts with keys: 'name', 'address', 'rssi', 'is_cortexkey'
    """
    if not BLEAK_AVAILABLE:
        return []

    devices = await BleakScanner.discover(timeout=timeout)
    result = []
    for d in devices:
        result.append({
            "name": d.name or "(unknown)",
            "address": d.address,
            "rssi": d.rssi,
            # Flag CortexKey devices for easy identification
            "is_cortexkey": (d.name or "").startswith("CortexKey"),
        })
    # Sort: CortexKey devices first, then by signal strength
    result.sort(key=lambda x: (not x["is_cortexkey"], -x["rssi"]))
    return result


def scan_ble_devices(timeout: float = 5.0) -> List[Dict]:
    """
    Synchronous wrapper for BLE scanning (safe to call from Streamlit).

    Runs the async scanner in a new event loop on a background thread
    so it doesn't conflict with Streamlit's own event loop.
    """
    if not BLEAK_AVAILABLE:
        return []

    result = []

    def _run():
        nonlocal result
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_scan_ble_devices_async(timeout))
        finally:
            loop.close()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=timeout + 2)
    return result


# ─────────────────────────────────────────────────────────
# BLE EEG READER
# ─────────────────────────────────────────────────────────

class BLEEEGReader:
    """
    Receives EEG samples from the CortexKey-EEG ESP32 over BLE.

    The reader runs a background asyncio event loop that:
    1. Connects to the ESP32 via BLE
    2. Subscribes to notifications on the EEG stream characteristic
    3. Parses incoming int16 samples from each notification
    4. Stores samples in a thread-safe EEGRingBuffer

    The main Streamlit thread can then call get_window() to retrieve
    signal data — identical API to SerialEEGReader.
    """

    def __init__(self, buffer_seconds: int = 30):
        """
        Parameters
        ----------
        buffer_seconds : int
            How many seconds of EEG to keep in the ring buffer
        """
        # Ring buffer — shared between the BLE notification handler and main thread
        self._buffer = EEGRingBuffer(capacity=SAMPLING_RATE * buffer_seconds)

        # BLE client (bleak)
        self._client: Optional[BleakClient] = None
        self._address: Optional[str] = None
        self._device_name: Optional[str] = None

        # Background thread running the asyncio event loop for BLE
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_event = threading.Event()

        # Connection state
        self._connected = False
        self._samples_received = 0
        self._start_time: Optional[float] = None
        self._current_profile = 0
        self._last_error: Optional[str] = None

    # ── Connection ─────────────────────────────────────────

    def connect(self, address: Optional[str] = None, timeout: float = 10.0) -> bool:
        """
        Connect to the CortexKey-EEG ESP32 over BLE.

        Parameters
        ----------
        address : str, optional
            BLE MAC address. If None, scans and auto-connects to "CortexKey-EEG".
        timeout : float
            Connection timeout in seconds.

        Returns
        -------
        bool
            True if connected successfully
        """
        if not BLEAK_AVAILABLE:
            self._last_error = "bleak library not installed. Run: pip install bleak"
            return False

        self._address = address
        self._stop_event.clear()
        self._connected = False
        self._last_error = None

        # Run the async BLE connection in a background thread
        # (Streamlit's main thread can't run asyncio directly)
        connect_result = {"success": False, "error": None}

        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            try:
                loop.run_until_complete(self._async_connect(address, timeout, connect_result))
                if connect_result["success"]:
                    # Keep the loop running to receive BLE notifications
                    loop.run_until_complete(self._async_run_forever())
            except Exception as e:
                logger.error(f"BLE thread error: {e}")
                connect_result["error"] = str(e)
            finally:
                loop.close()
                self._connected = False

        self._thread = threading.Thread(target=_run, daemon=True, name="BLEEEGReader")
        self._thread.start()

        # Wait for the connection to be established
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._connected:
                return True
            if connect_result.get("error"):
                self._last_error = connect_result["error"]
                return False
            time.sleep(0.1)

        self._last_error = "Connection timed out"
        return False

    async def _async_connect(self, address: Optional[str], timeout: float, result: dict):
        """Async coroutine: scan for device, connect, subscribe to notifications."""
        try:
            # If no address provided, scan for the CortexKey device
            if address is None:
                logger.info(f"Scanning for {DEVICE_NAME}...")
                devices = await BleakScanner.discover(timeout=5.0)
                for d in devices:
                    if (d.name or "").startswith("CortexKey"):
                        address = d.address
                        self._device_name = d.name
                        logger.info(f"Found {d.name} at {d.address} (RSSI: {d.rssi})")
                        break

                if address is None:
                    result["error"] = (
                        f"Could not find '{DEVICE_NAME}'. "
                        "Make sure the ESP32 is powered on and running the BLE firmware."
                    )
                    result["success"] = False
                    return

            self._address = address

            # Connect to the ESP32
            logger.info(f"Connecting to {address}...")
            self._client = BleakClient(address, timeout=timeout)
            await self._client.connect()

            if not self._client.is_connected:
                result["error"] = f"Failed to connect to {address}"
                result["success"] = False
                return

            logger.info(f"Connected to {address}")

            # Subscribe to EEG stream notifications
            # The _on_notification callback fires every time the ESP32 sends a packet
            await self._client.start_notify(CHAR_EEG_STREAM_UUID, self._on_notification)
            logger.info("Subscribed to EEG stream notifications")

            # Read the current profile
            profile_bytes = await self._client.read_gatt_char(CHAR_PROFILE_SELECT_UUID)
            if profile_bytes:
                self._current_profile = profile_bytes[0]
                logger.info(f"Current profile: {PROFILE_NAMES[self._current_profile]}")

            self._connected = True
            self._start_time = time.time()
            result["success"] = True

        except Exception as e:
            logger.error(f"BLE connect error: {e}")
            result["error"] = str(e)
            result["success"] = False

    async def _async_run_forever(self):
        """Keep the event loop alive to receive BLE notifications until stopped."""
        while not self._stop_event.is_set():
            # Check if still connected
            if self._client and not self._client.is_connected:
                logger.warning("BLE connection lost")
                self._connected = False
                break
            await asyncio.sleep(0.1)

        # Clean up
        if self._client and self._client.is_connected:
            try:
                await self._client.stop_notify(CHAR_EEG_STREAM_UUID)
                await self._client.disconnect()
            except Exception:
                pass

    def _on_notification(self, sender, data: bytearray):
        """
        BLE notification handler — called by bleak each time the ESP32
        sends a batch of EEG samples.

        The payload is SAMPLES_PER_PACKET × int16_t (little-endian).
        Each sample is in microvolts (signed).
        """
        # Parse the raw bytes into int16 samples
        # '<' = little-endian, 'h' = signed 16-bit
        n_samples = len(data) // 2
        if n_samples == 0:
            return

        # Unpack all samples at once
        fmt = f"<{n_samples}h"
        try:
            samples = struct.unpack(fmt, data[:n_samples * 2])
        except struct.error as e:
            logger.warning(f"BLE packet parse error: {e}, len={len(data)}")
            return

        # Write each sample to the ring buffer as float64 (microvolts)
        for s in samples:
            self._buffer.write(float(s))
            self._samples_received += 1

    # ── Disconnection ──────────────────────────────────────

    def disconnect(self):
        """Disconnect from the BLE device and stop the background thread."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self._connected = False
        logger.info("BLEEEGReader disconnected")

    # ── Profile switching ──────────────────────────────────

    def set_profile(self, profile_index: int) -> bool:
        """
        Switch the mock EEG profile on the ESP32.

        Parameters
        ----------
        profile_index : int
            0=devesh, 1=abhinav, 2=sadaf, 3=impostor, 4=devesh_coerced

        Returns
        -------
        bool
            True if the write succeeded
        """
        if not self._connected or not self._client:
            return False

        if profile_index < 0 or profile_index >= len(PROFILE_NAMES):
            return False

        result = {"success": False}

        def _do_write():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(
                    self._client.write_gatt_char(
                        CHAR_PROFILE_SELECT_UUID,
                        bytes([profile_index]),
                        response=True,
                    )
                )
                self._current_profile = profile_index
                result["success"] = True
                logger.info(f"Profile switched to: {PROFILE_NAMES[profile_index]}")
            except Exception as e:
                logger.error(f"Profile write error: {e}")
            finally:
                loop.close()

        # Write from a separate thread to avoid event loop conflicts
        t = threading.Thread(target=_do_write, daemon=True)
        t.start()
        t.join(timeout=3.0)

        return result["success"]

    # ── Data access (same API as SerialEEGReader) ──────────

    def get_window(
        self,
        duration_sec: float = 4.0,
        wait: bool = True,
        wait_timeout: float = 10.0,
    ) -> Optional[np.ndarray]:
        """
        Get a window of EEG data from the ring buffer.

        Identical API to SerialEEGReader.get_window() —
        the rest of the pipeline doesn't care whether data came via
        USB serial or BLE.
        """
        n_needed = int(SAMPLING_RATE * duration_sec)
        deadline = time.time() + wait_timeout

        while True:
            window = self._buffer.read_latest(n_needed)
            if window is not None:
                return window
            if not wait or time.time() >= deadline:
                return None
            time.sleep(0.1)

    def get_time_vector(self, duration_sec: float = 4.0) -> np.ndarray:
        """Return time axis matching a window of the given duration."""
        n = int(SAMPLING_RATE * duration_sec)
        return np.arange(n) / SAMPLING_RATE

    # ── Status ─────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def samples_available(self) -> int:
        return self._buffer.n_samples_available

    @property
    def seconds_buffered(self) -> float:
        return self.samples_available / SAMPLING_RATE

    @property
    def current_profile_name(self) -> str:
        if 0 <= self._current_profile < len(PROFILE_NAMES):
            return PROFILE_NAMES[self._current_profile]
        return "unknown"

    def get_error(self) -> Optional[str]:
        return self._last_error

    def get_stats(self) -> Dict:
        """Return reader statistics (same shape as SerialEEGReader.get_stats)."""
        elapsed = time.time() - self._start_time if self._start_time else 0
        return {
            "port": f"BLE ({self._address or 'N/A'})",
            "board": "esp32-ble",
            "connected": self.is_connected,
            "device_name": self._device_name or DEVICE_NAME,
            "samples_read": self._samples_received,
            "effective_fs": self._samples_received / elapsed if elapsed > 0 else 0,
            "seconds_buffered": self.seconds_buffered,
            "elapsed_sec": round(elapsed, 1),
            "current_profile": self.current_profile_name,
        }

    def clear_buffer(self):
        """Discard all buffered data."""
        self._buffer.clear()


# ─────────────────────────────────────────────────────────
# MODULE-LEVEL CONVENIENCE FUNCTIONS
# ─────────────────────────────────────────────────────────

def is_ble_available() -> bool:
    """Check if the bleak BLE library is installed."""
    return BLEAK_AVAILABLE
