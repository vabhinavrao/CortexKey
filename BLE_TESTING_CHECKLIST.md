# 🧪 ESP32 BLE Testing Checklist

Use this checklist to verify the ESP32 BLE connection before running Streamlit.

---

## ✅ Pre-Test Checklist

### Hardware
- [ ] ESP32 connected to computer via USB cable
- [ ] USB cable is data-capable (not charge-only)
- [ ] Computer has Bluetooth enabled (check System Preferences on macOS)

### Software  
- [ ] Arduino IDE installed
- [ ] ESP32 board support installed in Arduino IDE
- [ ] Python 3.9+ installed
- [ ] Virtual environment activated: `source .venv/bin/activate`
- [ ] Dependencies installed: `pip install -r requirements.txt`

---

## 🔧 Step 1: Flash the ESP32

1. **Open Arduino IDE**
   ```
   Open: firmware/bioamp_ble_mock/bioamp_ble_mock.ino
   ```

2. **Select Board Settings:**
   - Tools → Board → ESP32 Dev Module
   - Tools → Upload Speed → 115200
   - Tools → Port → (select your ESP32's port)

3. **Upload Firmware:**
   - Click Upload button (→)
   - Wait for "Connecting........" 
   - Press BOOT button if needed
   - Wait for "Hard resetting via RTS pin..."
   - [ ] Upload successful

4. **Verify Upload:**
   - Tools → Serial Monitor
   - Set baud rate to 115200
   - Press RST button on ESP32
   - [ ] See banner: "CortexKey — Mock EEG over BLE"
   - [ ] See: "BLE advertising started — device name: CortexKey-EEG"
   - [ ] LED blinks 3 times, then slow heartbeat

---

## 🧪 Step 2: Run Python BLE Test

1. **Activate Python environment:**
   ```bash
   cd /Users/abhinavrao/coding/hackathon/CortexKey
   source .venv/bin/activate  # or: .venv/bin/activate on Windows
   ```

2. **Run the test script:**
   ```bash
   python test_ble_connection.py
   ```

3. **Expected Results:**
   - [ ] "✅ bleak library is installed"
   - [ ] Scan finds devices in 5 seconds
   - [ ] "✅ Found CortexKey device: CortexKey-EEG"
   - [ ] Connection succeeds within 10 seconds
   - [ ] 2500+ samples received in 10 seconds
   - [ ] Sample rate is 250 Hz ± 5 Hz
   - [ ] Signal mean < 1000 μV
   - [ ] Signal std dev > 1 μV
   - [ ] Profile switching works (3 tests pass)
   - [ ] Disconnection succeeds
   - [ ] Final banner: "✅ BLE Connection Test Complete!"

4. **If any test fails, see ESP32_BLE_SETUP.md → Troubleshooting**

---

## 🖥️ Step 3: Run Streamlit App Locally

1. **Start the app:**
   ```bash
   streamlit run app.py
   ```

2. **Browser opens at http://localhost:8501**

3. **Test BLE Integration:**
   - [ ] Go to "Hardware Setup" in sidebar
   - [ ] Click "BLE Wireless" tab
   - [ ] Click "Scan for BLE Devices"
   - [ ] See "CortexKey-EEG" in results (green row)
   - [ ] Click "Connect to CortexKey-EEG"
   - [ ] Status changes to "🟢 Connected"
   - [ ] Live EEG preview shows waveform
   - [ ] Waveform updates in real-time (not frozen)
   - [ ] Stats show "~250 samples/sec"

4. **Test Profile Switching:**
   - [ ] Select "abhinav" from profile dropdown
   - [ ] Click "Switch Profile"
   - [ ] ESP32 LED blinks briefly
   - [ ] Waveform shape changes visually
   - [ ] Repeat for "sadaf" and "devesh"

5. **Test Enrollment (with BLE data):**
   - [ ] Go to "Enrollment" page
   - [ ] Select user "devesh"
   - [ ] Make sure BLE is connected (check Hardware Setup)
   - [ ] Click "Start Enrollment"
   - [ ] Progress bar runs for 4 seconds
   - [ ] "✅ Enrollment successful!" appears
   - [ ] Template file created in `data/templates/`

6. **Test Authentication (with BLE data):**
   - [ ] Go to "Authentication" page
   - [ ] Select user "devesh" (the enrolled one)
   - [ ] Make sure BLE is still connected
   - [ ] Click "Start Authentication"
   - [ ] Progress bar runs for 4 seconds
   - [ ] "✅ AUTHENTICATED" appears (confidence ~95%+)

7. **Test Rejection (impostor):**
   - [ ] Go back to "Hardware Setup"
   - [ ] Switch profile to "impostor"
   - [ ] Wait 2 seconds for buffer to fill with impostor data
   - [ ] Go to "Authentication"
   - [ ] Click "Start Authentication"
   - [ ] "❌ REJECTED" appears (confidence < 50%)

---

## 🎯 Success Criteria

All of the following must be true:

✅ **ESP32 Firmware:**
- Uploads without errors
- Serial Monitor shows "BLE advertising started"
- LED behavior correct (blink → solid when connected)

✅ **Python BLE Test:**
- All 8 test sections pass
- Sample rate is 250 Hz ± 5 Hz
- Profile switching works

✅ **Streamlit App:**
- BLE connection succeeds
- Live preview shows real-time waveform
- Enrollment works with BLE data
- Authentication accepts enrolled user
- Authentication rejects impostor

---

## 🐛 Common Issues

### "No BLE devices found"
- **Fix:** Enable Bluetooth in System Preferences
- **Fix:** Move ESP32 closer (< 5 meters)
- **Fix:** Check Arduino Serial Monitor shows "BLE advertising started"
- **Fix:** On macOS, grant Terminal Bluetooth permission

### "Connection failed" or "Connection timed out"
- **Fix:** Press RST button on ESP32, wait 3 seconds, retry
- **Fix:** Disconnect from ESP32 in macOS Bluetooth settings
- **Fix:** Restart Bluetooth on Mac (turn off → on)

### Sample rate is off (e.g., 230 Hz or 270 Hz)
- **Fix:** Close Arduino Serial Monitor (it slows down the ESP32)
- **Fix:** Keep only the test script or Streamlit running, not both
- **Fix:** Re-flash the firmware

### Streamlit app doesn't show BLE option
- **Fix:** Check `requirements.txt` includes `bleak`
- **Fix:** Run `pip install bleak`
- **Fix:** Restart Streamlit app

### Enrollment/Authentication uses simulator instead of BLE
- **Fix:** Check Hardware Setup → BLE tab shows "🟢 Connected"
- **Fix:** The `_acquire_eeg()` function prioritizes BLE → USB → Simulator
- **Fix:** Look at the code: it should say "Acquiring from: BLE"

---

## 📸 Expected Screenshots

### Arduino Serial Monitor (after flashing):
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

### Python Test Script (successful run):
```
✅ bleak library is installed
✅ Found CortexKey device: CortexKey-EEG
✅ Connected successfully!
[████████████████████] 10/10s | Samples:  2500 | Rate:  250.0 Hz
✅ Sample rate is accurate!
✅ Successfully read 1000 samples
✅ Profile switched successfully to abhinav
✅ BLE Connection Test Complete!
```

### Streamlit App (BLE connected):
- BLE tab shows green "🟢 Connected" badge
- Live preview chart updates every second
- Profile selector dropdown is active
- Stats show: "Samples: 2500+ | Rate: ~250 Hz"

---

## 🚀 Next Steps After Testing

Once all tests pass:

1. **Keep Streamlit running locally** for your demo
2. **Don't deploy to Streamlit Cloud yet** (BLE won't work remotely)
3. **For cloud demos**, use the Simulator mode (Hardware Setup → Simulator tab)
4. **When BioAmp EXG Pill arrives**, switch to USB Serial mode

---

## 📞 Need Help?

- **Check logs:** Arduino Serial Monitor for ESP32 status
- **Check app logs:** Streamlit terminal for Python errors
- **Read docs:** ESP32_BLE_SETUP.md (comprehensive troubleshooting)
- **Test incrementally:** Run Python test script before Streamlit
- **Isolate issues:** Test ESP32 → Python → Streamlit in order

---

**Last Updated:** February 20, 2026  
**Firmware Version:** bioamp_ble_mock v1.0  
**Python BLE Reader:** ble_reader.py v0.1  
**Streamlit App:** app.py with BLE support
