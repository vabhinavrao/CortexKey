"""
Hardware Reader — CortexKey v0.1
Real-time EEG acquisition from BioAmp EXG Pill via ESP32/Arduino over Serial.

This module is a drop-in replacement for eeg_simulator.py.
The rest of the pipeline (signal_processing, classifier, auth_engine, app.py)
requires ZERO changes — it sees the same numpy arrays regardless of source.

─────────────────────────────────────────────────────────────────────────────
HARDWARE SETUP
─────────────────────────────────────────────────────────────────────────────

  BioAmp EXG Pill                ESP32 / Arduino Uno / Nano
  ───────────────                ───────────────────────────
  OUT ──────────────────────────► A0   (Analog pin)
  GND ──────────────────────────► GND
  VCC ──────────────────────────► 3.3V (ESP32) or 5V (Arduino Uno)
                                  ↓ USB
                                  PC running Streamlit

  Electrode placement (EEG — frontal lobe):
    • REF pad → mastoid bone (behind ear) / earclip
    • EEG pad → Fp1 or Fp2 (forehead, ~2 cm above eyebrow)
    • GND pad → forehead center or opposite side

─────────────────────────────────────────────────────────────────────────────
FIRMWARE REQUIRED (see firmware/bioamp_serial/bioamp_serial.ino)
─────────────────────────────────────────────────────────────────────────────

  The ESP32/Arduino sketch must:
  1. Sample A0 at exactly 250 Hz (4 ms intervals)
  2. Send each 12-bit ADC value as a newline-terminated ASCII integer
     OR as a 4-byte little-endian binary packet (faster, less CPU)
  3. Baud rate: 115200 bps

─────────────────────────────────────────────────────────────────────────────
SERIAL DATA FORMAT (ASCII mode — default, human-readable)
─────────────────────────────────────────────────────────────────────────────

  Each line is one ADC sample:
    2048\\n          ← midpoint (12-bit: 0–4095, midpoint = 2048)
    2053\\n
    2041\\n
    ...

  Conversion to microvolts:
    V_in (V)  = (ADC_raw / ADC_MAX) * V_REF - V_REF/2
    μV        = V_in * 1_000_000

  For ESP32 (12-bit ADC, 3.3V ref):
    ADC_MAX = 4095,  V_REF = 3.3

  For Arduino Uno/Nano (10-bit ADC, 5V ref):
    ADC_MAX = 1023,  V_REF = 5.0
    (lower resolution — use ESP32 for better signal quality)

─────────────────────────────────────────────────────────────────────────────
BINARY PACKET FORMAT (optional, lower latency)
─────────────────────────────────────────────────────────────────────────────

  Header (1 byte): 0xA5
  ADC high byte (1 byte)
  ADC low byte  (1 byte)
  Checksum (1 byte): header XOR high XOR low

  Total: 4 bytes per sample → 4 × 250 = 1000 bytes/sec

References:
  - BioAmp EXG Pill datasheet: https://store.upside-downlabs.tech
  - Upside Down Labs GitHub: https://github.com/upsidedownlabs/BioAmp-EXG-Pill
  - ESP32 ADC docs: https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/peripherals/adc.html
  - Arduino Serial: https://www.arduino.cc/reference/en/language/functions/communication/serial/
"""

import numpy as np
import serial
import serial.tools.list_ports
import threading
import queue
import time
import logging
from typing import Optional, Tuple, List, Dict, Callable

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────
# CONSTANTS — match your hardware
# ─────────────────────────────────────────────────────────

SAMPLING_RATE = 250          # Hz — must match firmware
BAUD_RATE     = 115200       # bps — must match firmware
READ_TIMEOUT  = 2.0          # seconds before declaring port dead

# ESP32 (12-bit ADC, 3.3 V reference)
ADC_BITS_ESP32    = 12
ADC_MAX_ESP32     = (2 ** ADC_BITS_ESP32) - 1   # 4095
VREF_ESP32        = 3.3      # volts

# Arduino Uno / Nano (10-bit ADC, 5 V reference)
ADC_BITS_ARDUINO  = 10
ADC_MAX_ARDUINO   = (2 ** ADC_BITS_ARDUINO) - 1  # 1023
VREF_ARDUINO      = 5.0      # volts

# Default: ESP32
DEFAULT_BOARD = "esp32"


# ─────────────────────────────────────────────────────────
# ADC → MICROVOLTS CONVERSION
# ─────────────────────────────────────────────────────────

def adc_to_microvolts(
    adc_raw: float,
    board: str = DEFAULT_BOARD,
) -> float:
    """
    Convert a raw ADC reading to microvolts.

    The BioAmp EXG Pill outputs a biopotential signal centered around
    VCC/2 (mid-rail). The ADC captures this, and we subtract the midpoint
    to get a zero-centered signal in physical units.

    Parameters
    ----------
    adc_raw : float
        Raw ADC integer value
    board : str
        'esp32' or 'arduino'

    Returns
    -------
    float
        Signal amplitude in microvolts (μV)
    """
    if board == "arduino":
        adc_max = ADC_MAX_ARDUINO
        vref = VREF_ARDUINO
    else:  # esp32
        adc_max = ADC_MAX_ESP32
        vref = VREF_ESP32

    # Convert to voltage centered at 0V (remove nominal DC bias)
    # Note: the BioAmp EXG Pill may have a slight DC offset from VCC/2.
    # This is completely removed by the 1 Hz high-pass (bandpass) filter in
    # the signal processing pipeline — the exact midpoint value here does not
    # affect authentication accuracy.
    voltage = ((adc_raw - adc_max / 2.0) / adc_max) * vref

    # Convert to microvolts
    return voltage * 1_000_000.0


# ─────────────────────────────────────────────────────────
# PORT DETECTION
# ─────────────────────────────────────────────────────────

def list_serial_ports() -> List[Dict[str, str]]:
    """
    List all available serial ports with device descriptions.

    Returns
    -------
    list of dicts with keys: 'port', 'description', 'hwid'
    """
    ports = serial.tools.list_ports.comports()
    result = []
    for p in sorted(ports):
        result.append({
            "port": p.device,
            "description": p.description,
            "hwid": p.hwid,
        })
    return result


def auto_detect_port(board: str = DEFAULT_BOARD) -> Optional[str]:
    """
    Auto-detect the serial port for ESP32 or Arduino.

    Looks for common USB-to-Serial bridge chips:
    - CP210x (Silicon Labs) — common on ESP32 DevKit boards
    - CH340 / CH341 — cheap Arduino clones
    - FTDI FT232 — quality Arduino clones, some ESP32 boards
    - Prolific PL2303 — generic USB-serial

    Parameters
    ----------
    board : str
        'esp32' or 'arduino' (affects chip priority)

    Returns
    -------
    str or None
        Port name (e.g. '/dev/ttyUSB0', 'COM3') or None if not found
    """
    # Keywords to search for in port descriptions
    esp32_keywords  = ["CP210", "Silicon Labs", "UART Bridge", "ESP32", "CH340", "CH341"]
    arduino_keywords = ["Arduino", "CH340", "CH341", "FTDI", "FT232", "Prolific", "PL2303"]

    keywords = esp32_keywords if board == "esp32" else arduino_keywords

    ports = serial.tools.list_ports.comports()
    for port in sorted(ports):
        desc = port.description.upper()
        hwid = port.hwid.upper()
        for kw in keywords:
            if kw.upper() in desc or kw.upper() in hwid:
                logger.info(f"Auto-detected {board} on {port.device}: {port.description}")
                return port.device

    # Fallback — return first available port (if any)
    if ports:
        logger.warning(f"No {board} USB chip recognized. Using first port: {ports[0].device}")
        return ports[0].device

    return None


# ─────────────────────────────────────────────────────────
# RING BUFFER (thread-safe)
# ─────────────────────────────────────────────────────────

class EEGRingBuffer:
    """
    Thread-safe circular buffer for streaming EEG samples.

    The serial reader thread writes samples here continuously.
    The main thread reads windows of samples for processing.
    """

    def __init__(self, capacity: int = SAMPLING_RATE * 30):
        """
        Parameters
        ----------
        capacity : int
            Maximum number of samples to store (default: 30 seconds)
        """
        self._buf = np.zeros(capacity, dtype=np.float64)
        self._capacity = capacity
        self._write_idx = 0
        self._total_written = 0
        self._lock = threading.Lock()

    def write(self, sample: float):
        """Write a single sample to the buffer."""
        with self._lock:
            self._buf[self._write_idx % self._capacity] = sample
            self._write_idx += 1
            self._total_written += 1

    def write_batch(self, samples: np.ndarray):
        """Write a batch of samples to the buffer."""
        with self._lock:
            for s in samples:
                self._buf[self._write_idx % self._capacity] = s
                self._write_idx += 1
            self._total_written += len(samples)

    def read_latest(self, n_samples: int) -> Optional[np.ndarray]:
        """
        Read the most recent n_samples from the buffer.

        Returns None if fewer than n_samples have been written.
        """
        with self._lock:
            if self._total_written < n_samples:
                return None
            end = self._write_idx
            start = end - n_samples
            indices = np.arange(start, end) % self._capacity
            return self._buf[indices].copy()

    @property
    def n_samples_available(self) -> int:
        """Number of valid samples currently in the buffer."""
        with self._lock:
            return min(self._total_written, self._capacity)

    def clear(self):
        """Reset the buffer."""
        with self._lock:
            self._buf[:] = 0.0
            self._write_idx = 0
            self._total_written = 0


# ─────────────────────────────────────────────────────────
# SERIAL READER THREAD
# ─────────────────────────────────────────────────────────

class SerialEEGReader:
    """
    Background thread that continuously reads EEG samples from
    the serial port and stores them in a ring buffer.

    Usage:
        reader = SerialEEGReader(port='/dev/ttyUSB0', board='esp32')
        reader.start()
        ...
        signal = reader.get_window(duration_sec=4.0)
        ...
        reader.stop()
    """

    def __init__(
        self,
        port: str,
        baud: int = BAUD_RATE,
        board: str = DEFAULT_BOARD,
        on_sample: Optional[Callable[[float], None]] = None,
        buffer_seconds: int = 30,
    ):
        """
        Parameters
        ----------
        port : str
            Serial port (e.g. '/dev/ttyUSB0', 'COM3')
        baud : int
            Baud rate (must match firmware)
        board : str
            'esp32' or 'arduino'
        on_sample : callable, optional
            Callback invoked with each new sample (for live plotting)
        buffer_seconds : int
            How many seconds of data to keep in the ring buffer
        """
        self.port = port
        self.baud = baud
        self.board = board
        self.on_sample = on_sample

        self._buffer = EEGRingBuffer(capacity=SAMPLING_RATE * buffer_seconds)
        self._serial: Optional[serial.Serial] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._error_queue: queue.Queue = queue.Queue()
        self._connected = False
        self._samples_read = 0
        self._start_time: Optional[float] = None

    # ── Connection management ──────────────────────────────

    def start(self) -> bool:
        """
        Open the serial port and start the background reader thread.

        Returns
        -------
        bool
            True if connection succeeded, False otherwise
        """
        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baud,
                timeout=READ_TIMEOUT,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
            )
            # Flush stale data
            self._serial.reset_input_buffer()
            time.sleep(0.1)
            self._serial.reset_input_buffer()

            self._stop_event.clear()
            self._connected = True
            self._start_time = time.time()

            self._thread = threading.Thread(
                target=self._read_loop,
                daemon=True,
                name="SerialEEGReader",
            )
            self._thread.start()
            logger.info(f"SerialEEGReader started on {self.port} @ {self.baud} baud")
            return True

        except serial.SerialException as e:
            self._connected = False
            logger.error(f"Failed to open {self.port}: {e}")
            self._error_queue.put(str(e))
            return False

    def stop(self):
        """Stop the reader thread and close the serial port."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        if self._serial and self._serial.is_open:
            self._serial.close()
        self._connected = False
        logger.info("SerialEEGReader stopped")

    # ── Background read loop ───────────────────────────────

    def _read_loop(self):
        """Main loop running in the background thread — reads serial data."""
        while not self._stop_event.is_set():
            try:
                line = self._serial.readline()
                if not line:
                    continue  # Timeout — keep trying

                # Decode and strip whitespace
                decoded = line.decode("ascii", errors="ignore").strip()
                if not decoded:
                    continue

                # Skip comment lines (firmware may send headers like "# CortexKey EEG v1")
                if decoded.startswith("#") or decoded.startswith("//"):
                    continue

                # Parse ADC integer value
                try:
                    adc_raw = int(decoded)
                except ValueError:
                    logger.debug(f"Non-numeric serial data: {decoded!r}")
                    continue

                # Convert to microvolts
                sample_uv = adc_to_microvolts(adc_raw, self.board)

                # Store in ring buffer
                self._buffer.write(sample_uv)
                self._samples_read += 1

                # Fire callback if registered (for live Streamlit streaming)
                if self.on_sample:
                    try:
                        self.on_sample(sample_uv)
                    except Exception as e:
                        logger.warning(f"on_sample callback error: {e}")

            except serial.SerialException as e:
                logger.error(f"Serial read error: {e}")
                self._error_queue.put(str(e))
                self._connected = False
                break

            except Exception as e:
                logger.error(f"Unexpected error in read loop: {e}")
                # Don't break — keep trying

    # ── Data access ────────────────────────────────────────

    def get_window(
        self,
        duration_sec: float = 4.0,
        wait: bool = True,
        wait_timeout: float = 10.0,
    ) -> Optional[np.ndarray]:
        """
        Get a window of EEG data from the ring buffer.

        Parameters
        ----------
        duration_sec : float
            How many seconds of data to retrieve
        wait : bool
            If True, block until enough data is available
        wait_timeout : float
            Maximum seconds to wait

        Returns
        -------
        np.ndarray or None
            Signal array of shape (n_samples,) in microvolts,
            or None if not enough data available
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
        """Return the time axis matching a window of given duration."""
        n = int(SAMPLING_RATE * duration_sec)
        return np.arange(n) / SAMPLING_RATE

    # ── Status ─────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        return self._connected and (self._thread is not None) and self._thread.is_alive()

    @property
    def samples_available(self) -> int:
        return self._buffer.n_samples_available

    @property
    def seconds_buffered(self) -> float:
        return self.samples_available / SAMPLING_RATE

    def get_error(self) -> Optional[str]:
        """Return the latest error message, if any."""
        try:
            return self._error_queue.get_nowait()
        except queue.Empty:
            return None

    def get_stats(self) -> Dict:
        """Return reader statistics."""
        elapsed = time.time() - self._start_time if self._start_time else 0
        return {
            "port": self.port,
            "board": self.board,
            "connected": self.is_connected,
            "samples_read": self._samples_read,
            "effective_fs": self._samples_read / elapsed if elapsed > 0 else 0,
            "seconds_buffered": self.seconds_buffered,
            "elapsed_sec": round(elapsed, 1),
        }

    def clear_buffer(self):
        """Discard all buffered data (e.g. between enrollment trials)."""
        self._buffer.clear()


# ─────────────────────────────────────────────────────────
# HIGH-LEVEL API — mirrors eeg_simulator.generate_eeg_signal()
# ─────────────────────────────────────────────────────────

# Global singleton reader — managed by the Streamlit session
_active_reader: Optional[SerialEEGReader] = None


def connect_hardware(
    port: Optional[str] = None,
    board: str = DEFAULT_BOARD,
    baud: int = BAUD_RATE,
) -> Tuple[bool, str, Optional[SerialEEGReader]]:
    """
    Connect to the BioAmp EXG Pill hardware.

    Drop-in counterpart to initializing the simulator.
    Called once from the Streamlit UI when the user clicks "Connect Hardware".

    Parameters
    ----------
    port : str, optional
        Serial port. If None, auto-detect.
    board : str
        'esp32' or 'arduino'
    baud : int
        Baud rate

    Returns
    -------
    success : bool
    message : str
    reader : SerialEEGReader or None
    """
    global _active_reader

    # Stop existing reader
    if _active_reader is not None:
        _active_reader.stop()
        _active_reader = None

    # Auto-detect port if not specified
    if port is None:
        port = auto_detect_port(board)
        if port is None:
            return False, "No serial device found. Check USB connection.", None

    reader = SerialEEGReader(port=port, baud=baud, board=board)
    success = reader.start()

    if success:
        _active_reader = reader
        return True, f"Connected to {port} ({board.upper()}) @ {baud} baud", reader
    else:
        err = reader.get_error() or "Unknown error"
        return False, f"Failed to connect: {err}", None


def disconnect_hardware():
    """Disconnect from hardware and release the serial port."""
    global _active_reader
    if _active_reader is not None:
        _active_reader.stop()
        _active_reader = None


def acquire_eeg_signal(
    reader: SerialEEGReader,
    duration_sec: float = 4.0,
    wait_timeout: float = 10.0,
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """
    Acquire a single EEG window from the hardware reader.

    This function has the same signature as the relevant part of
    eeg_simulator.generate_eeg_signal() — the rest of the pipeline
    (signal_processing → classifier → auth_engine) is unchanged.

    Parameters
    ----------
    reader : SerialEEGReader
    duration_sec : float
    wait_timeout : float

    Returns
    -------
    t : np.ndarray — time vector (seconds)
    signal : np.ndarray — EEG in microvolts
    or None if acquisition failed
    """
    signal = reader.get_window(
        duration_sec=duration_sec,
        wait=True,
        wait_timeout=wait_timeout,
    )
    if signal is None:
        return None

    t = reader.get_time_vector(duration_sec)
    return t, signal


def get_reader() -> Optional[SerialEEGReader]:
    """Return the currently active SerialEEGReader (or None)."""
    return _active_reader
