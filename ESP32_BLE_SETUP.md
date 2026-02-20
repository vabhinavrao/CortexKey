# ESP32 BLE Setup Guide — CortexKey

Complete guide for flashing and testing the ESP32 BLE mock EEG firmware.

---

## 📋 Requirements

### Hardware
- **ESP32 development board** (any variant with BLE support)
- USB cable (data-capable, not charge-only)
- Computer with Bluetooth (BLE 4.0+)

### Software
- **Arduino IDE** (1.8.x or 2.x)
- **ESP32 board support** installed in Arduino IDE
- **Python 3.9+** with `bleak` library

---

## 🔧 Step 1: Install ESP32 Board Support in Arduino IDE

### Arduino IDE 1.8.x:
1. Open Arduino IDE
2. Go to **File → Preferences**
3. In "Additional Boards Manager URLs", add:
   ```
   https://dl.espressif.com/dl/package_esp32_index.json
   ```
4. Go to **Tools → Board → Boards Manager**
5. Search for "esp32"
6. Install **"esp32 by Espressif Systems"** (version 2.0.x or later)

### Arduino IDE 2.x:
1. Open Arduino IDE 2
2. Click the board selector dropdown (top left)
3. Click **"Select other board and port..."**
4. Search for "ESP32 Dev Module"
5. If not found, install ESP32 platform:
   - Go to **File → Preferences**
   - Add the ESP32 URL (see above)
   - Go to **Tools → Board Manager**
   - Install "esp32 by Espressif Systems"

---

## 📦 Step 2: Flash the ESP32

1. **Connect the ESP32** to your computer via USB

2. **Open the firmware** in Arduino IDE:
   ```
   File → Open → firmware/bioamp_ble_mock/bioamp_ble_mock.ino
   ```

3. **Configure the board settings**:
   - **Board:** "ESP32 Dev Module"
   - **Upload Speed:** 115200
   - **CPU Frequency:** 240 MHz
   - **Flash Frequency:** 80 MHz
   - **Flash Mode:** QIO
   - **Flash Size:** 4MB (32Mb)
   - **Partition Scheme:** Default 4MB
   - **Port:** Select your ESP32's serial port (e.g., `/dev/cu.usbserial-0001` on macOS)

4. **Compile and verify** (optional):
   - Click the ✓ (Verify) button to check for compilation errors
   - Should show: "Sketch uses XXXXX bytes" (success)

5. **Upload**:
   - Click the → (Upload) button
   - Wait for "Connecting........" message
   - You may need to press the **BOOT button** on the ESP32 when you see "Connecting"
   - Upload takes ~30 seconds
   - Should end with: "Hard resetting via RTS pin..."

6. **Verify the upload**:
   - Open **Tools → Serial Monitor**
   - Set baud rate to **115200**
   - Press the **RST button** on the ESP32
   - You should see:
     ```
     # ══════════════════════════════════════════
     # CortexKey — Mock EEG over BLE
     # ESP32 Firmware v1.0
     # ══════════════════════════════════════════
     # Sample rate: 250 Hz
     # Samples per BLE packet: 10
     # BLE notification rate: 25 Hz
     # Profile changed to: devesh (59 components)
     # Starting profile: devesh
     # BLE advertising started — device name: CortexKey-EEG
     # Waiting for connection...
     ```

7. **LED Behavior**:
   - **Slow blinking (1 Hz):** Not connected, advertising
   - **3 quick blinks at startup:** Firmware booted successfully
   - **Solid ON:** BLE client connected
   - **OFF → Blinking:** Client disconnected, re-advertising

---

## 🧪 Step 3: Test the BLE Connection (Python)

### Install Dependencies
```bash
cd /Users/abhinavrao/coding/hackathon/CortexKey
pip install bleak
```

### Run the Test Script
```bash
python test_ble_connection.py
```

**Expected output:**
```
╔════════════════════════════════════════════════════════════╗
║       CortexKey — ESP32 BLE Connection Test                ║
╚════════════════════════════════════════════════════════════╝

✅ bleak library is installed

🔍 Scanning for BLE devices (5 seconds)...

✅ Found 3 BLE device(s):

  🧠 [1] CortexKey-EEG
      Address: XX:XX:XX:XX:XX:XX
      RSSI: -45 dBm

✅ Found CortexKey device: CortexKey-EEG
   Address: XX:XX:XX:XX:XX:XX

🔗 Connecting to ESP32...
✅ Connected successfully!

📊 Receiving EEG samples (10 seconds)...

  [████████████████████] 10/10s | Samples:  2500 | Rate:  250.0 Hz | Profile: devesh

📈 Final Statistics:
   Total samples received: 2500
   Effective sample rate: 250.00 Hz
   Expected sample rate: 250 Hz
   Buffer duration: 10.0 seconds
   Current profile: devesh

✅ Sample rate is accurate!

📊 Reading a 4-second EEG window...
✅ Successfully read 1000 samples
   Min value: -85.3 μV
   Max value: 142.7 μV
   Mean value: 2.4 μV
   Std dev: 35.2 μV

✅ EEG signal statistics look reasonable!

🔄 Testing profile switching...
   Switching to profile 1 (abhinav)...
   ✅ Profile switched successfully to abhinav
   Switching to profile 2 (sadaf)...
   ✅ Profile switched successfully to sadaf
   Switching to profile 0 (devesh)...
   ✅ Profile switched successfully to devesh

🔌 Disconnecting from ESP32...
✅ Disconnected successfully

╔════════════════════════════════════════════════════════════╗
║  ✅ BLE Connection Test Complete!                          ║
║                                                            ║
║  Your ESP32 is working correctly and streaming EEG data.  ║
║  You can now run the full Streamlit app with:             ║
║                                                            ║
║    streamlit run app.py                                   ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
```

### Troubleshooting

#### "No BLE devices found"
- **Check Bluetooth:** Make sure Bluetooth is enabled in System Preferences (macOS) or Settings (Windows/Linux)
- **Check ESP32 power:** LED should be blinking
- **Check Serial Monitor:** Verify the ESP32 is advertising
- **Range:** Move the ESP32 closer to your computer (within 5 meters)
- **Permissions:** On macOS, make sure Terminal has Bluetooth permission (System Preferences → Security & Privacy → Bluetooth)

#### "Connection failed"
- **Try again:** BLE connections can be flaky. Run the test script again.
- **Reset ESP32:** Press the RST button and wait 3 seconds, then retry
- **Check Serial Monitor:** Look for "# BLE client connected" message
- **Other devices:** Make sure no other app is connected to the ESP32 (check macOS Bluetooth settings)

#### "Sample rate is off"
- **ESP32 busy:** The ESP32 is trying to do too much. Check if Serial Monitor is printing too frequently (should be ~1 line/sec)
- **BLE congestion:** Too many BLE devices nearby. Try in a quieter environment.
- **Normal:** ±5 Hz is acceptable. ±20 Hz indicates a problem.

#### "Profile switching failed"
- **Wait longer:** Add a 2-second delay after connecting before switching
- **Check write permissions:** Verify the profile characteristic has WRITE property (check Serial Monitor)
- **Firmware issue:** Re-flash the ESP32

---

## 🚀 Step 4: Run the Full Streamlit App

Once the test script passes, you're ready for the full app!

### Local Testing (Recommended First)
```bash
streamlit run app.py
```

The app will open at `http://localhost:8501`

### Using the App with BLE

1. **Go to Hardware Setup page** (sidebar)

2. **Select the "BLE Wireless" tab**

3. **Scan for devices:**
   - Click **"Scan for BLE Devices"**
   - Wait 5 seconds
   - "CortexKey-EEG" should appear in green

4. **Connect:**
   - Click **"Connect to CortexKey-EEG"**
   - Status should change to "🟢 Connected"
   - Live EEG preview starts streaming

5. **Test profile switching:**
   - Use the dropdown: "Select mock user profile"
   - Choose different profiles (devesh, abhinav, sadaf, impostor, devesh_coerced)
   - The waveform shape should change visually
   - The ESP32 LED will blink briefly during the switch

6. **Go to Enrollment:**
   - Select a user (e.g., "devesh")
   - Click **"Start Enrollment"**
   - The app will use BLE data automatically (no code changes needed!)
   - After 4 seconds, enrollment completes

7. **Go to Authentication:**
   - Select the enrolled user
   - Click **"Start Authentication"**
   - Should authenticate successfully with the correct profile
   - Switch to "impostor" profile on Hardware Setup and try again — should reject

---

## 🌐 Step 5: Deploy to Streamlit Cloud (Later)

Once local testing is complete:

1. **Commit and push** all changes to GitHub
2. **Deploy on Streamlit Cloud:**
   - Go to https://share.streamlit.io/
   - Connect your GitHub repo
   - Deploy `app.py`

3. **Important:** BLE won't work on Streamlit Cloud (no direct Bluetooth access). You have two options:
   - **Use the simulator mode** (already built-in, no hardware needed)
   - **Use USB Serial mode** (requires the BioAmp EXG Pill connected to a local machine)

For demos on Streamlit Cloud, the simulator is perfect — it uses the same profiles as the ESP32.

---

## 📊 BLE Performance Specs

| Metric | Value |
|--------|-------|
| **Sample Rate** | 250 Hz (4000 μs interval) |
| **Data Format** | int16 little-endian (microvolts) |
| **Batch Size** | 10 samples per BLE notification |
| **Notification Rate** | 25 Hz (40 ms between packets) |
| **Throughput** | 500 bytes/sec (well within BLE limits) |
| **Latency** | ~50-80 ms end-to-end |
| **Range** | ~10 meters (typical for BLE) |
| **Power** | ~100 mA (ESP32 active) → 5 hours with 500 mAh LiPo |

---

## 🔄 Switching to Real EEG (When BioAmp EXG Pill Arrives)

### Option 1: USB Serial (Recommended for Real Hardware)
Use `firmware/bioamp_serial/bioamp_serial.ino` — already built, just flash and select "USB Serial" tab in the app.

### Option 2: Keep BLE, Swap Mock Signal for Real ADC
In `bioamp_ble_mock.ino`, replace the `generateSample()` function:

```cpp
int16_t generateSample() {
  // Read from ADC (ESP32 built-in)
  int rawADC = analogRead(34);  // GPIO34 = ADC1_CH6
  
  // BioAmp EXG Pill outputs 0-3.3V centered at 1.65V
  // ESP32 ADC is 12-bit (0-4095)
  int16_t sample = (int16_t)(rawADC - 2048);  // Center at 0
  
  // Scale to microvolts (adjust based on your BioAmp gain)
  // Typical gain: 1100x, so 1 ADC count ≈ 0.8 μV
  sample = sample * 0.8;
  
  globalSampleCount++;
  return sample;
}
```

Wire the BioAmp:
- **OUT** → ESP32 GPIO34 (ADC1_CH6)
- **GND** → ESP32 GND
- **3.3V** → ESP32 3.3V

---

## 📝 Notes

- **BLE vs USB Serial:** BLE is wireless and great for demos. USB Serial has lower latency and is more reliable for production.
- **Multiple ESP32s:** You can run multiple ESP32s simultaneously — each will advertise with the same name. The app connects to the strongest signal (highest RSSI).
- **Battery Power:** Add a 3.7V LiPo to the ESP32 JST connector for wireless operation. Make sure to use a battery protection circuit.
- **Firmware Updates:** Re-flashing the ESP32 preserves no state. All profiles reset to default.

---

## ✅ Success Checklist

- [ ] ESP32 board support installed in Arduino IDE
- [ ] Firmware flashed successfully (no errors)
- [ ] Serial Monitor shows "BLE advertising started"
- [ ] LED blinks slowly (heartbeat)
- [ ] `test_ble_connection.py` passes all tests
- [ ] Sample rate is 250 Hz ± 5 Hz
- [ ] Profile switching works
- [ ] Streamlit app connects and shows live preview
- [ ] Enrollment and authentication work with BLE data
- [ ] Ready for demos!

---

**Questions? Issues?** Check the Arduino Serial Monitor for ESP32 debug messages. All status updates are prefixed with `#`.
