# 🔌 ESP32 BLE Connection Architecture

Visual guide to how the ESP32 connects to your app.

---

## 📡 System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         YOUR COMPUTER                               │
│                                                                     │
│  ┌──────────────────────┐         ┌──────────────────────────┐    │
│  │   Streamlit App      │         │  Python Test Script      │    │
│  │   (app.py)           │         │  (test_ble_connection.py)│    │
│  └──────────┬───────────┘         └──────────┬───────────────┘    │
│             │                                 │                     │
│             │ Uses                            │ Uses                │
│             ▼                                 ▼                     │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │         BLE Reader Module (ble_reader.py)                  │   │
│  │  • BLEEEGReader class                                       │   │
│  │  • EEGRingBuffer (thread-safe)                             │   │
│  │  • Uses 'bleak' library for BLE communication              │   │
│  └────────────────────────┬───────────────────────────────────┘   │
│                           │                                         │
│                           │ Bluetooth LE (BLE)                     │
│                           │ • Service UUID: 0000181a-...           │
│                           │ • GATT notifications                   │
│                           │ • 250 Hz sample stream                 │
└───────────────────────────┼─────────────────────────────────────────┘
                            │
                   ╔════════▼═════════╗
                   ║                  ║
                   ║  🔷 ESP32 Board  ║
                   ║                  ║
                   ║  BLE Server      ║
                   ║  "CortexKey-EEG" ║
                   ║                  ║
                   ╚══════════════════╝
```

---

## 🔄 Data Flow (Real-Time)

### Step 1: ESP32 Generation (250 Hz)
```
ESP32 Firmware (bioamp_ble_mock.ino)
    │
    ├─ generateSample() called every 4000 μs (250 Hz)
    │   ├─ Sum 59 sinusoidal components (delta, theta, alpha, beta)
    │   ├─ Add 50 Hz powerline noise
    │   ├─ Add Gaussian white noise
    │   ├─ Add blink artifacts (every 3.5 sec)
    │   └─ Return int16_t sample in microvolts (μV)
    │
    ├─ Batch 10 samples into 20-byte packet
    │
    └─ Send BLE GATT notification (25 Hz)
         └─ Characteristic: 00002a59-...
```

### Step 2: Python Reception (bleak)
```
BLEEEGReader (ble_reader.py)
    │
    ├─ _on_notification() callback triggered by bleak
    │   ├─ Parse 20 bytes → 10 × int16_t samples
    │   └─ Write to EEGRingBuffer (thread-safe)
    │
    └─ Background thread runs asyncio event loop
         └─ Keeps BLE connection alive
```

### Step 3: App Consumption (Streamlit)
```
Streamlit App (app.py)
    │
    ├─ Hardware Setup page:
    │   ├─ Connect button → reader.connect()
    │   ├─ Live preview → reader.get_window(4.0 sec)
    │   └─ Profile switcher → reader.set_profile(idx)
    │
    ├─ Enrollment page:
    │   ├─ _acquire_eeg() → prioritizes BLE
    │   └─ signal_processing.extract_features()
    │
    └─ Authentication page:
        └─ Same pipeline, zero code changes!
```

---

## 🔢 Data Format

### BLE Notification Payload
```
┌────────────────────────────────────────────────────────┐
│  Byte Offset   │  Data Type  │  Value                  │
├────────────────┼─────────────┼─────────────────────────┤
│  0-1           │  int16_le   │  Sample 0 (μV)          │
│  2-3           │  int16_le   │  Sample 1 (μV)          │
│  4-5           │  int16_le   │  Sample 2 (μV)          │
│  6-7           │  int16_le   │  Sample 3 (μV)          │
│  8-9           │  int16_le   │  Sample 4 (μV)          │
│  10-11         │  int16_le   │  Sample 5 (μV)          │
│  12-13         │  int16_le   │  Sample 6 (μV)          │
│  14-15         │  int16_le   │  Sample 7 (μV)          │
│  16-17         │  int16_le   │  Sample 8 (μV)          │
│  18-19         │  int16_le   │  Sample 9 (μV)          │
└────────────────┴─────────────┴─────────────────────────┘

Total: 20 bytes per notification
Rate: 25 notifications/second = 250 samples/second
```

### Example Values (devesh profile)
```
Sample values in microvolts (typical range: -200 to +200 μV)

Time (ms)   Value (μV)   Explanation
─────────   ──────────   ──────────────────────────────────
    0.0       +42.3      Baseline (mostly alpha band)
    4.0       +58.1      Alpha oscillation peak
    8.0       +35.7      
   12.0        +8.4      Alpha trough
  ...
 1200.0      +145.8      ← Blink artifact starts
 1240.0      +187.2      ← Blink peak (~120 μV added)
 1280.0      +152.1      ← Blink decay
```

---

## 🧪 Testing Workflow

### Phase 1: Verify ESP32 (Arduino Serial Monitor)
```
You should see:
✅ "BLE advertising started — device name: CortexKey-EEG"
✅ LED blinking slowly (1 Hz heartbeat)
✅ No error messages

If you see errors:
❌ "BLE init failed" → Re-flash firmware
❌ Watchdog timer reset → Remove delays in code
❌ No output → Check baud rate (115200)
```

### Phase 2: Verify Python (test_ble_connection.py)
```bash
python test_ble_connection.py
```

```
Expected timeline:
[0-5s]    Scanning for BLE devices
[5-10s]   Connecting to ESP32
[10-20s]  Receiving samples (watch progress bar)
[20-25s]  Testing profile switching
[25-26s]  Disconnecting

Success indicators:
✅ Sample rate: 250.0 Hz (±5 Hz is OK)
✅ Min/max values: -200 to +200 μV (typical)
✅ Profile switching: 3/3 tests pass
```

### Phase 3: Verify Streamlit (local app)
```bash
streamlit run app.py
```

```
Go to: Hardware Setup → BLE Wireless tab

Actions:
1. Scan → Should find "CortexKey-EEG" in <5 seconds
2. Connect → Status changes to "🟢 Connected"
3. Live preview → Chart updates every second
4. Switch profile → Select "abhinav", click "Switch Profile"
5. Verify → Chart waveform should look different

Success indicators:
✅ Connection is stable (doesn't drop)
✅ Sample rate shows ~250 Hz
✅ Waveform is smooth (not choppy)
✅ Profile switching works without disconnecting
```

---

## 🔧 Connection States

### ESP32 States
| State | LED | Serial Monitor | BLE Status |
|-------|-----|----------------|------------|
| **Booting** | 3× blink | "Initializing..." | Not advertising |
| **Advertising** | Slow blink (1 Hz) | "Waiting for connection..." | Discoverable |
| **Connected** | Solid ON | "BLE client connected" | Streaming data |
| **Disconnected** | Blink resumes | "Re-advertising..." | Back to advertising |
| **Error** | OFF or rapid blink | Error message | Check firmware |

### Python BLE Reader States
| State | `is_connected` | `samples_available` | Action |
|-------|----------------|---------------------|--------|
| **Idle** | `False` | `0` | Call `connect()` |
| **Connecting** | `False` | `0` | Wait... |
| **Connected** | `True` | Increasing | Call `get_window()` |
| **Streaming** | `True` | ~250/sec | Normal operation |
| **Disconnected** | `False` | Stale data | Reconnect |

---

## 🐛 Troubleshooting Decision Tree

```
Is the ESP32 powered on?
    NO → Plug in USB cable
    YES ↓

Does Arduino Serial Monitor show "BLE advertising started"?
    NO → Re-flash firmware
    YES ↓

Does the LED blink slowly?
    NO → Press RST button
    YES ↓

Does `python test_ble_connection.py` find the device?
    NO → Check Bluetooth is enabled on Mac
    YES ↓

Does the connection succeed?
    NO → Try again (BLE can be flaky on first attempt)
    YES ↓

Is the sample rate ~250 Hz?
    NO → Close Arduino Serial Monitor (it slows ESP32)
    YES ↓

Does profile switching work?
    NO → Check firmware has ProfileWriteCallback
    YES ↓

Does Streamlit app connect?
    NO → Make sure test script is not running (only 1 connection at a time)
    YES ↓

Does live preview show a waveform?
    NO → Check "Hardware Setup" → BLE tab shows "Connected"
    YES ↓

✅ Everything works! Ready for enrollment/authentication.
```

---

## 📊 Performance Expectations

### Timing
| Metric | Expected | Tolerance |
|--------|----------|-----------|
| **BLE scan time** | 5 seconds | ±2 seconds |
| **Connection time** | 2-3 seconds | Up to 10 seconds on first try |
| **First sample received** | <1 second after connect | <3 seconds |
| **Sample rate** | 250 Hz | 245-255 Hz |
| **Notification latency** | 40-80 ms | <200 ms |
| **Profile switch time** | 1-2 seconds | <5 seconds |

### Signal Quality
| Metric | Typical Range | Warning If |
|--------|---------------|------------|
| **Mean value** | -50 to +50 μV | > 1000 μV |
| **Std deviation** | 20-60 μV | < 1 μV (flat signal) |
| **Min/max** | -200 to +200 μV | > 500 μV (clipping) |
| **Buffer fill rate** | 250 samples/sec | < 200 or > 300 |

---

## 🚀 Ready for Testing!

Follow these documents in order:

1. **ESP32_BLE_SETUP.md** — Flash the firmware
2. **BLE_TESTING_CHECKLIST.md** — Run all tests
3. **This file** — Understand the architecture

When all tests pass, you're ready for live demos! 🎉

---

**Questions?**
- Check Arduino Serial Monitor for ESP32 logs
- Check Streamlit terminal for Python errors
- Read the comprehensive ESP32_BLE_SETUP.md guide
