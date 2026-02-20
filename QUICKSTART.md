# 🚀 Quick Start — ESP32 BLE Testing

**Goal:** Test the ESP32 BLE connection locally before deploying to Streamlit Cloud.

---

## ⚡ TL;DR — 3 Commands

**IMPORTANT:** You need an ESP32 board for this. If you don't have one yet:
- Skip to "Option B" below (use the simulator)
- Or wait for your ESP32 to arrive

---

## Option A: Test with Real ESP32 Hardware

### Prerequisites
- ✅ ESP32 board connected via USB
- ✅ Arduino IDE installed with ESP32 board support
- ✅ Python environment activated (`.venv`)

### Step 1: Flash the ESP32 (Arduino IDE)
```
1. Open: firmware/bioamp_ble_mock/bioamp_ble_mock.ino
2. Tools → Board → ESP32 Dev Module
3. Tools → Port → (select your ESP32)
4. Click Upload (→)
5. Wait for "Hard resetting via RTS pin..."
```

**Verify:** Open Serial Monitor (115200 baud) and press RST. You should see:
```
# BLE advertising started — device name: CortexKey-EEG
```

### Step 2: Test BLE Connection (Python)
```bash
cd /Users/abhinavrao/coding/hackathon/CortexKey
source .venv/bin/activate  # If not already activated
python test_ble_connection.py
```

**Expected:** All tests pass, sample rate is ~250 Hz, final message says:
```
✅ BLE Connection Test Complete!
```

### Step 3: Run Streamlit Locally
```bash
streamlit run app.py
```

**Test in the app:**
1. Hardware Setup → BLE Wireless tab
2. Scan → Find "CortexKey-EEG"
3. Connect → See live preview
4. Enroll a user → Authentication works!

---

## Option B: Test Without ESP32 (Simulator Mode)

If you don't have the ESP32 yet, the app already has a built-in simulator:

### Run Streamlit
```bash
cd /Users/abhinavrao/coding/hackathon/CortexKey
source .venv/bin/activate  # If not already activated
streamlit run app.py
```

### Use Simulator
1. Hardware Setup → **Simulator** tab (not BLE)
2. Select a user profile (devesh, abhinav, sadaf, etc.)
3. Go to Enrollment → Enroll users
4. Go to Authentication → Test authentication

**Note:** The simulator generates the **exact same EEG profiles** as the ESP32. The ML pipeline can't tell the difference!

---

## 📋 Detailed Documentation

If you need more help, read these in order:

| Document | Purpose |
|----------|---------|
| **ESP32_BLE_SETUP.md** | Complete ESP32 setup guide (Arduino IDE config, troubleshooting) |
| **BLE_TESTING_CHECKLIST.md** | Step-by-step testing checklist with expected outputs |
| **BLE_CONNECTION_GUIDE.md** | Architecture diagrams and data flow visualization |

---

## 🎯 What You're Testing

The ESP32 firmware (`bioamp_ble_mock.ino`) generates realistic mock EEG signals:
- **5 user profiles:** devesh, abhinav, sadaf, impostor, devesh_coerced
- **250 Hz sampling rate** (same as real BioAmp EXG Pill)
- **Wireless streaming** over Bluetooth Low Energy (BLE)
- **Remote profile switching** from the Streamlit app

This lets you test the **entire authentication pipeline** before the real hardware arrives.

---

## ✅ Success Criteria

You'll know it's working when:

### ESP32 (if using hardware)
- ✅ Arduino Serial Monitor shows "BLE advertising started"
- ✅ LED on ESP32 blinks slowly
- ✅ `test_ble_connection.py` passes all tests
- ✅ Sample rate is 250 Hz ± 5 Hz

### Streamlit App (local)
- ✅ BLE tab shows "🟢 Connected" (or Simulator tab is selected)
- ✅ Live preview shows waveform
- ✅ Enrollment works (creates template files in `data/templates/`)
- ✅ Authentication accepts enrolled user
- ✅ Authentication rejects impostor

---

## 🚫 What NOT to Do (Yet)

**DON'T deploy to Streamlit Cloud yet!**

Why?
- BLE requires **local Bluetooth hardware** (not available on cloud servers)
- Test everything **locally first** to make sure it works
- When ready for cloud demos, use the **Simulator mode** (no hardware needed)

---

## 🐛 Quick Troubleshooting

### "No module named 'bleak'"
```bash
pip install bleak
```

### "No BLE devices found"
- Enable Bluetooth on your Mac (System Preferences)
- Make sure ESP32 is powered on (LED blinking)
- Check Arduino Serial Monitor shows "BLE advertising started"

### "Connection failed"
- Press RST button on ESP32
- Wait 3 seconds
- Run `test_ble_connection.py` again

### Streamlit uses simulator instead of BLE
- Make sure BLE tab shows "🟢 Connected" **before** going to Enrollment/Authentication
- The `_acquire_eeg()` helper prioritizes: BLE → USB Serial → Simulator

---

## 🎉 Next Steps After Testing

Once local testing is complete:

1. **Keep Streamlit running locally** for live demos (if using ESP32 hardware)
2. **Or deploy to Streamlit Cloud** using Simulator mode (no hardware needed)
3. **When BioAmp EXG Pill arrives**, switch to USB Serial mode for real EEG

---

## 📞 Questions?

- **ESP32 issues:** Check Arduino Serial Monitor logs
- **Python/BLE issues:** Read `ESP32_BLE_SETUP.md` troubleshooting section
- **Streamlit issues:** Check terminal output for errors

All code is committed and pushed to GitHub. Ready to test! 🚀
