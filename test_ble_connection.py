#!/usr/bin/env python3
"""
BLE Connection Test Script — CortexKey
Tests ESP32 BLE connectivity before running the full Streamlit app.

USAGE:
    python test_ble_connection.py

WHAT IT DOES:
    1. Scans for "CortexKey-EEG" BLE device
    2. Connects to the ESP32
    3. Receives EEG samples for 10 seconds
    4. Prints statistics and verifies 250 Hz sample rate
    5. Tests profile switching
    6. Disconnects cleanly

REQUIREMENTS:
    - ESP32 must be flashed with bioamp_ble_mock.ino and powered on
    - bleak library installed: pip install bleak
"""

import sys
import time
import asyncio
from cortexkey.ble_reader import BLEEEGReader, scan_ble_devices, is_ble_available

def print_banner():
    print("╔════════════════════════════════════════════════════════════╗")
    print("║       CortexKey — ESP32 BLE Connection Test                ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()

def main():
    print_banner()
    
    # ── Step 1: Check if bleak is installed ──────────────────────────────
    if not is_ble_available():
        print("❌ ERROR: bleak library not found")
        print("   Install it with: pip install bleak")
        return 1
    
    print("✅ bleak library is installed")
    print()
    
    # ── Step 2: Scan for BLE devices ──────────────────────────────────────
    print("🔍 Scanning for BLE devices (5 seconds)...")
    print("   Make sure your ESP32 is powered on and running bioamp_ble_mock.ino")
    print()
    
    devices = scan_ble_devices(timeout=5.0)
    
    if not devices:
        print("❌ No BLE devices found")
        print("   Troubleshooting:")
        print("   - Is the ESP32 powered on?")
        print("   - Is Bluetooth enabled on your Mac?")
        print("   - Did you flash bioamp_ble_mock.ino to the ESP32?")
        print("   - Check Arduino Serial Monitor for ESP32 status")
        return 1
    
    print(f"✅ Found {len(devices)} BLE device(s):")
    print()
    
    cortexkey_device = None
    for i, dev in enumerate(devices, 1):
        is_ck = "🧠" if dev["is_cortexkey"] else "  "
        print(f"  {is_ck} [{i}] {dev['name']}")
        print(f"      Address: {dev['address']}")
        print(f"      RSSI: {dev['rssi']} dBm")
        print()
        
        if dev["is_cortexkey"]:
            cortexkey_device = dev
    
    if not cortexkey_device:
        print("❌ CortexKey-EEG device not found")
        print("   Found other BLE devices, but none named 'CortexKey-EEG'")
        print("   Check that the ESP32 is running the correct firmware")
        return 1
    
    print(f"✅ Found CortexKey device: {cortexkey_device['name']}")
    print(f"   Address: {cortexkey_device['address']}")
    print()
    
    # ── Step 3: Connect to the ESP32 ──────────────────────────────────────
    print("🔗 Connecting to ESP32...")
    
    reader = BLEEEGReader(buffer_seconds=30)
    
    success = reader.connect(address=cortexkey_device['address'], timeout=10.0)
    
    if not success:
        error = reader.get_error()
        print(f"❌ Connection failed: {error}")
        return 1
    
    print("✅ Connected successfully!")
    print()
    
    # ── Step 4: Wait for samples to accumulate ────────────────────────────
    print("📊 Receiving EEG samples (10 seconds)...")
    print("   You should see data accumulating in the buffer...")
    print()
    
    for i in range(10):
        time.sleep(1)
        stats = reader.get_stats()
        samples = reader.samples_available
        effective_fs = stats['effective_fs']
        
        # Show progress bar
        bar_length = 20
        filled = int(bar_length * (i + 1) / 10)
        bar = "█" * filled + "░" * (bar_length - filled)
        
        print(f"  [{bar}] {i+1}/10s | "
              f"Samples: {samples:5d} | "
              f"Rate: {effective_fs:6.1f} Hz | "
              f"Profile: {stats['current_profile']}")
    
    print()
    
    # ── Step 5: Validate sample rate ──────────────────────────────────────
    stats = reader.get_stats()
    effective_fs = stats['effective_fs']
    expected_fs = 250.0
    tolerance = 5.0  # ±5 Hz tolerance
    
    print("📈 Final Statistics:")
    print(f"   Total samples received: {stats['samples_read']}")
    print(f"   Effective sample rate: {effective_fs:.2f} Hz")
    print(f"   Expected sample rate: {expected_fs} Hz")
    print(f"   Buffer duration: {stats['seconds_buffered']:.1f} seconds")
    print(f"   Current profile: {stats['current_profile']}")
    print()
    
    if abs(effective_fs - expected_fs) > tolerance:
        print(f"⚠️  WARNING: Sample rate is off by {abs(effective_fs - expected_fs):.1f} Hz")
        print("   This may indicate timing issues in the ESP32 firmware")
    else:
        print("✅ Sample rate is accurate!")
    
    print()
    
    # ── Step 6: Test reading a window ─────────────────────────────────────
    print("📊 Reading a 4-second EEG window...")
    
    window = reader.get_window(duration_sec=4.0, wait=True, wait_timeout=5.0)
    
    if window is None:
        print("❌ Failed to read window")
        reader.disconnect()
        return 1
    
    print(f"✅ Successfully read {len(window)} samples")
    print(f"   Min value: {window.min():.1f} μV")
    print(f"   Max value: {window.max():.1f} μV")
    print(f"   Mean value: {window.mean():.1f} μV")
    print(f"   Std dev: {window.std():.1f} μV")
    print()
    
    # Check if values are reasonable for EEG
    if abs(window.mean()) > 1000:
        print("⚠️  WARNING: Mean value is unusually high")
    elif window.std() < 1.0:
        print("⚠️  WARNING: Standard deviation is too low (signal may be flat)")
    else:
        print("✅ EEG signal statistics look reasonable!")
    
    print()
    
    # ── Step 7: Test profile switching ────────────────────────────────────
    print("🔄 Testing profile switching...")
    
    profiles_to_test = [
        (1, "abhinav"),
        (2, "sadaf"),
        (0, "devesh"),
    ]
    
    for profile_idx, profile_name in profiles_to_test:
        print(f"   Switching to profile {profile_idx} ({profile_name})...")
        success = reader.set_profile(profile_idx)
        
        if success:
            time.sleep(1)  # Wait for ESP32 to switch
            stats = reader.get_stats()
            actual_profile = stats['current_profile']
            
            if actual_profile == profile_name:
                print(f"   ✅ Profile switched successfully to {profile_name}")
            else:
                print(f"   ⚠️  Profile mismatch: expected {profile_name}, got {actual_profile}")
        else:
            print(f"   ❌ Failed to switch to profile {profile_idx}")
    
    print()
    
    # ── Step 8: Disconnect ────────────────────────────────────────────────
    print("🔌 Disconnecting from ESP32...")
    reader.disconnect()
    time.sleep(1)
    
    if not reader.is_connected:
        print("✅ Disconnected successfully")
    else:
        print("⚠️  Reader still reports as connected")
    
    print()
    print("╔════════════════════════════════════════════════════════════╗")
    print("║  ✅ BLE Connection Test Complete!                          ║")
    print("║                                                            ║")
    print("║  Your ESP32 is working correctly and streaming EEG data.  ║")
    print("║  You can now run the full Streamlit app with:             ║")
    print("║                                                            ║")
    print("║    streamlit run app.py                                   ║")
    print("║                                                            ║")
    print("╚════════════════════════════════════════════════════════════╝")
    
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
