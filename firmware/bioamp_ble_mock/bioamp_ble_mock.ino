/**
 * ═══════════════════════════════════════════════════════════════════════════
 * CortexKey — Mock EEG over Bluetooth Low Energy (BLE)
 * ESP32 Only — Generates realistic EEG waveforms and streams them via BLE
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * PURPOSE:
 *   This firmware makes the ESP32 act as a wireless EEG sensor by generating
 *   realistic mock brainwave signals on-chip and streaming them over BLE.
 *   Use this to test the full CortexKey pipeline wirelessly before the
 *   BioAmp EXG Pill arrives. When the chip arrives, swap to the real ADC
 *   firmware (bioamp_serial.ino) — the Python side is identical.
 *
 * BLE ARCHITECTURE:
 *   ┌──────────────────────────────────────────────────────────────────┐
 *   │  GATT Server (ESP32)                                            │
 *   │                                                                  │
 *   │  Service: CortexKey EEG Service                                 │
 *   │  UUID: 0000181a-0000-1000-8000-00805f9b34fb  (Environmental)    │
 *   │                                                                  │
 *   │  Characteristic: EEG Sample Stream                              │
 *   │  UUID: 00002a59-0000-1000-8000-00805f9b34fb                     │
 *   │  Properties: NOTIFY                                             │
 *   │  Format: 2 bytes little-endian int16 (microvolts, signed)       │
 *   │                                                                  │
 *   │  Characteristic: User Profile Selector                          │
 *   │  UUID: 00002a58-0000-1000-8000-00805f9b34fb                     │
 *   │  Properties: READ | WRITE                                       │
 *   │  Format: 1 byte — user profile index (0-4)                      │
 *   │    0 = devesh, 1 = abhinav, 2 = sadaf,                          │
 *   │    3 = impostor, 4 = devesh_coerced                             │
 *   └──────────────────────────────────────────────────────────────────┘
 *
 * DATA FORMAT (per BLE notification):
 *   Each notification carries a batch of 10 samples (20 bytes total),
 *   each sample as a signed 16-bit little-endian integer in microvolts.
 *   At 250 Hz / 10 samples per packet = 25 notifications per second.
 *   This keeps BLE overhead low and fits within the default MTU.
 *
 * HOW TO USE:
 *   1. Flash this sketch to an ESP32 via Arduino IDE
 *   2. The ESP32 will advertise as "CortexKey-EEG"
 *   3. Run the Streamlit app → Hardware Setup → Connect via BLE
 *   4. The Python BLE reader (ble_reader.py) connects and receives samples
 *   5. To change the mock user profile, write a byte (0-4) to the
 *      profile selector characteristic from the app
 *
 * SIGNAL GENERATION:
 *   Identical to the Python eeg_simulator.py — sum of sinusoids per band
 *   with per-user amplitude profiles, 50 Hz powerline noise, and blink
 *   artifacts. The same profiles that the SVM was trained on.
 *
 * REQUIRES:
 *   - ESP32 board package in Arduino IDE
 *   - No external libraries needed — uses built-in ESP32 BLE stack
 */

#include <BLEDevice.h>      // ESP32 BLE core library
#include <BLEServer.h>       // GATT server
#include <BLEUtils.h>        // Utility classes
#include <BLE2902.h>         // Client Characteristic Configuration Descriptor (for notifications)

// ═══════════════════════════════════════════════════════════════════════════
// BLE SERVICE & CHARACTERISTIC UUIDs
// ═══════════════════════════════════════════════════════════════════════════

// Service UUID — using the standard "Environmental Sensing" service as a base
// (0x181A). In production you'd register a custom 128-bit UUID.
#define SERVICE_UUID              "0000181a-0000-1000-8000-00805f9b34fb"

// EEG data stream — client subscribes to notifications on this characteristic
// to receive a continuous flow of EEG samples
#define CHAR_EEG_STREAM_UUID      "00002a59-0000-1000-8000-00805f9b34fb"

// User profile selector — write a byte (0-4) to switch the mock EEG profile
// so you can test different users from the Streamlit UI without re-flashing
#define CHAR_PROFILE_SELECT_UUID  "00002a58-0000-1000-8000-00805f9b34fb"

// ═══════════════════════════════════════════════════════════════════════════
// SAMPLING CONFIGURATION
// ═══════════════════════════════════════════════════════════════════════════

#define SAMPLE_RATE_HZ     250       // Must match Python SAMPLING_RATE
#define SAMPLES_PER_PACKET 10        // 10 × int16 = 20 bytes per BLE notification
#define SAMPLE_INTERVAL_US (1000000 / SAMPLE_RATE_HZ)  // 4000 μs

// BLE notification interval = SAMPLES_PER_PACKET / SAMPLE_RATE_HZ
// = 10 / 250 = 0.04 seconds = 40 ms between notifications (25 per second)

// LED pin for heartbeat indicator
#define LED_PIN 2

// ═══════════════════════════════════════════════════════════════════════════
// MOCK EEG USER PROFILES
// Exact same profiles as Python eeg_simulator.py USER_PROFILES dict.
// Each profile defines the amplitude (in μV) for delta/theta/alpha/beta
// bands, plus the individual alpha frequency (IAF) peak.
// ═══════════════════════════════════════════════════════════════════════════

// Number of user profiles available
#define NUM_PROFILES 5

// Profile names (for serial debug output)
const char* profileNames[NUM_PROFILES] = {
  "devesh",           // 0
  "abhinav",          // 1
  "sadaf",            // 2
  "impostor",         // 3
  "devesh_coerced"    // 4
};

// Band amplitude lookup [profile][band]
// Bands: 0=delta(0.5-4), 1=theta(4-8), 2=alpha(8-13), 3=beta(13-30)
const float bandAmplitudes[NUM_PROFILES][4] = {
  // delta, theta, alpha, beta
  { 15.0, 22.0, 35.0, 12.0 },   // devesh — strong alpha, moderate theta
  { 12.0, 18.0, 28.0, 20.0 },   // abhinav — higher beta (analytical)
  { 10.0, 30.0, 22.0,  8.0 },   // sadaf — dominant theta (emotional)
  { 20.0, 10.0, 18.0, 25.0 },   // impostor — high beta, low theta
  { 10.0,  8.0, 12.0, 38.0 },   // devesh_coerced — beta surge, alpha collapse
};

// Individual Alpha Frequency (IAF) peak — unique per person
const float alphaPeakHz[NUM_PROFILES] = {
  10.2,   // devesh
  11.0,   // abhinav
   9.2,   // sadaf
  10.8,   // impostor
  10.2,   // devesh_coerced (same IAF as devesh — it's the same brain)
};

// Gaussian noise floor (μV) — sensor + environmental noise
const float noiseLevel[NUM_PROFILES] = {
  3.0, 3.5, 2.5, 4.0, 5.0
};

// Band frequency ranges [4 bands × 2 (low, high)]
const float bandRanges[4][2] = {
  { 0.5,  4.0 },   // delta
  { 4.0,  8.0 },   // theta
  { 8.0, 13.0 },   // alpha
  {13.0, 30.0 },   // beta
};

// Number of sinusoidal components to sum per band
// More components = richer, more realistic spectral shape
const int bandComponents[4] = { 7, 8, 10, 34 };
// delta: 3.5Hz range × 2 = 7, theta: 4Hz × 2 = 8, etc.

// ═══════════════════════════════════════════════════════════════════════════
// SIGNAL GENERATION STATE
// Each band is generated as a sum of sinusoids with fixed random phases.
// Phases are re-randomized when the profile changes (simulating a new person).
// ═══════════════════════════════════════════════════════════════════════════

// Maximum total components across all bands
#define MAX_COMPONENTS 80

// Per-component state: frequency (Hz), phase (rad), amplitude scale factor
float compFreqs[MAX_COMPONENTS];       // fixed frequencies for each sinusoid
float compPhases[MAX_COMPONENTS];      // random initial phases (0 to 2π)
float compAmplitudes[MAX_COMPONENTS];  // per-component amplitude scaling
int   compBand[MAX_COMPONENTS];        // which band each component belongs to
int   totalComponents = 0;             // total active components

// ═══════════════════════════════════════════════════════════════════════════
// GLOBAL STATE
// ═══════════════════════════════════════════════════════════════════════════

// Currently active user profile index (0-4)
volatile uint8_t currentProfile = 0;

// Time counter for continuous waveform generation
// Using a global sample counter instead of micros() for deterministic frequency
unsigned long globalSampleCount = 0;

// BLE objects
BLEServer*         pServer          = NULL;
BLECharacteristic* pEEGStreamChar   = NULL;
BLECharacteristic* pProfileChar     = NULL;
bool               deviceConnected  = false;
bool               oldDeviceState   = false;

// Timing for the 250 Hz sample loop
unsigned long lastSampleTime = 0;

// Sample batch buffer — accumulates SAMPLES_PER_PACKET samples before
// sending a BLE notification (reduces BLE overhead)
int16_t sampleBatch[SAMPLES_PER_PACKET];
int     batchIndex = 0;

// 50 Hz powerline noise amplitude (μV) — India mains frequency
const float powerlineAmplitude = 8.0;

// ═══════════════════════════════════════════════════════════════════════════
// INITIALIZE WAVEFORM COMPONENTS FOR A GIVEN PROFILE
// Called at startup and whenever the user profile changes.
// Generates random frequencies within each band and random phases.
// ═══════════════════════════════════════════════════════════════════════════

void initWaveformComponents(uint8_t profileIdx) {
  totalComponents = 0;

  // Seed the random number generator for reproducible demo
  // Different seed per profile so each user has unique random phases
  randomSeed(profileIdx * 1337 + 42);

  // For each EEG frequency band...
  for (int b = 0; b < 4; b++) {
    float bandLow  = bandRanges[b][0];    // Lower edge of band (Hz)
    float bandHigh = bandRanges[b][1];    // Upper edge of band (Hz)
    float amp      = bandAmplitudes[profileIdx][b];  // Target amplitude (μV)
    int   nComp    = bandComponents[b];   // Number of sinusoidal components

    for (int c = 0; c < nComp; c++) {
      if (totalComponents >= MAX_COMPONENTS) break;

      // For the alpha band, cluster frequencies around the IAF peak
      // (this creates the characteristic alpha "bump" in the PSD)
      float freq;
      if (b == 2) {  // alpha band
        // Gaussian-like distribution around the individual alpha frequency
        float peak = alphaPeakHz[profileIdx];
        // Box-Muller approximation: sum of randoms → normal-ish distribution
        float r = ((float)random(0, 1000) / 1000.0 +
                   (float)random(0, 1000) / 1000.0 +
                   (float)random(0, 1000) / 1000.0 - 1.5) * 0.67;
        freq = peak + r;
        // Clamp to band edges
        if (freq < bandLow)  freq = bandLow;
        if (freq > bandHigh) freq = bandHigh;
      } else {
        // Uniform distribution across the band
        freq = bandLow + ((float)random(0, 10000) / 10000.0) * (bandHigh - bandLow);
      }

      // Random initial phase (0 to 2π) — makes each "person" unique
      float phase = ((float)random(0, 10000) / 10000.0) * 2.0 * PI;

      // Per-component amplitude with slight randomization
      // Scaled by 1/sqrt(nComp) so total band power matches the target amplitude
      float ampScale = (0.3 + ((float)random(0, 7000) / 10000.0)) / sqrt((float)nComp);

      // Store component parameters
      compFreqs[totalComponents]      = freq;
      compPhases[totalComponents]     = phase;
      compAmplitudes[totalComponents] = amp * ampScale;
      compBand[totalComponents]       = b;
      totalComponents++;
    }
  }

  Serial.print("# Profile changed to: ");
  Serial.print(profileNames[profileIdx]);
  Serial.print(" (");
  Serial.print(totalComponents);
  Serial.println(" components)");
}

// ═══════════════════════════════════════════════════════════════════════════
// GENERATE ONE EEG SAMPLE
// Evaluates all sinusoidal components at the current time step,
// adds powerline noise (50 Hz) and Gaussian sensor noise.
// Returns the sample in microvolts as a signed 16-bit integer.
// ═══════════════════════════════════════════════════════════════════════════

int16_t generateSample() {
  // Current time in seconds (floating-point, from the global sample counter)
  float t = (float)globalSampleCount / (float)SAMPLE_RATE_HZ;

  float sample = 0.0;

  // ── Sum all sinusoidal components (the "neural oscillations") ──────────
  for (int i = 0; i < totalComponents; i++) {
    sample += compAmplitudes[i] * sin(2.0 * PI * compFreqs[i] * t + compPhases[i]);
  }

  // ── Add 50 Hz powerline noise (India mains frequency) ─────────────────
  // This is the same interference that the real BioAmp EXG Pill picks up.
  // The Python notch filter removes it, proving the DSP pipeline works.
  sample += powerlineAmplitude * sin(2.0 * PI * 50.0 * t);
  // 100 Hz harmonic (weaker)
  sample += (powerlineAmplitude * 0.3) * sin(2.0 * PI * 100.0 * t + 0.5);

  // ── Add Gaussian white noise (sensor/environmental noise floor) ────────
  // Approximate Gaussian using Central Limit Theorem: sum of 4 uniform randoms
  float noise = 0.0;
  for (int j = 0; j < 4; j++) {
    noise += (float)random(-1000, 1000) / 1000.0;
  }
  noise *= noiseLevel[currentProfile] * 0.5;  // Scale to the profile's noise level
  sample += noise;

  // ── Occasional blink artifact (~every 3-4 seconds) ─────────────────────
  // Blinks appear as large (~120 μV) slow Gaussian-shaped deflections
  // lasting ~250 ms. They're most prominent in frontal electrodes (Fp1/Fp2).
  // The bandpass filter will largely remove these.
  {
    // Modulo to create periodic blink windows
    float cycleTime = fmod(t, 3.5);  // ~1 blink every 3.5 seconds
    float blinkCenter = 1.2;         // Blink occurs at t=1.2s within each cycle
    float blinkSigma  = 0.08;        // ~250ms blink duration (3σ ≈ 240ms)
    float blinkAmp    = 120.0;       // Peak amplitude in μV
    float dt = cycleTime - blinkCenter;
    float blink = blinkAmp * exp(-0.5 * (dt / blinkSigma) * (dt / blinkSigma));
    sample += blink;
  }

  // ── Clamp to int16 range ───────────────────────────────────────────────
  // EEG signals from the BioAmp EXG Pill are typically ±200 μV after
  // amplification, but blink artifacts can hit ±500 μV. int16 covers
  // ±32,767 μV — more than enough headroom.
  if (sample > 32767.0)  sample = 32767.0;
  if (sample < -32767.0) sample = -32767.0;

  // Increment the global sample counter (wraps after ~24 hours at 250 Hz)
  globalSampleCount++;

  return (int16_t)sample;
}

// ═══════════════════════════════════════════════════════════════════════════
// BLE CALLBACKS
// ═══════════════════════════════════════════════════════════════════════════

// Called when a BLE client (the Streamlit app) connects or disconnects
class ServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer* pServer) {
    deviceConnected = true;
    Serial.println("# BLE client connected");
    // Light the LED solid while connected
    digitalWrite(LED_PIN, HIGH);
  }

  void onDisconnect(BLEServer* pServer) {
    deviceConnected = false;
    Serial.println("# BLE client disconnected");
    digitalWrite(LED_PIN, LOW);
    // Restart advertising so the client can reconnect
    pServer->startAdvertising();
    Serial.println("# Advertising restarted");
  }
};

// Called when the client writes to the Profile Selector characteristic
// Allows switching the mock user profile from the Streamlit UI
class ProfileWriteCallback : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic* pCharacteristic) {
    // Read the single byte written by the client
    uint8_t* data = pCharacteristic->getData();
    size_t   len  = pCharacteristic->getLength();

    if (len >= 1 && data[0] < NUM_PROFILES) {
      uint8_t newProfile = data[0];
      if (newProfile != currentProfile) {
        currentProfile = newProfile;
        // Re-initialize waveform components for the new profile
        initWaveformComponents(currentProfile);
        // Reset sample counter so the waveform starts fresh
        globalSampleCount = 0;
      }
    } else {
      Serial.println("# Invalid profile index received");
    }
  }
};

// ═══════════════════════════════════════════════════════════════════════════
// SETUP — Initialize BLE GATT server and start advertising
// ═══════════════════════════════════════════════════════════════════════════

void setup() {
  // ── Serial for debug output ─────────────────────────────────────────────
  Serial.begin(115200);
  while (!Serial) { delay(10); }

  // ── LED for visual feedback ─────────────────────────────────────────────
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  // ── Print firmware banner ───────────────────────────────────────────────
  Serial.println("# ══════════════════════════════════════════");
  Serial.println("# CortexKey — Mock EEG over BLE");
  Serial.println("# ESP32 Firmware v1.0");
  Serial.println("# ══════════════════════════════════════════");
  Serial.print("# Sample rate: ");
  Serial.print(SAMPLE_RATE_HZ);
  Serial.println(" Hz");
  Serial.print("# Samples per BLE packet: ");
  Serial.println(SAMPLES_PER_PACKET);
  Serial.print("# BLE notification rate: ");
  Serial.print(SAMPLE_RATE_HZ / SAMPLES_PER_PACKET);
  Serial.println(" Hz");

  // ── Initialize the waveform generator with the default profile ──────────
  initWaveformComponents(currentProfile);
  Serial.print("# Starting profile: ");
  Serial.println(profileNames[currentProfile]);

  // ── Initialize BLE ──────────────────────────────────────────────────────
  // The device name appears in the Bluetooth settings and in bleak scans
  BLEDevice::init("CortexKey-EEG");

  // Create GATT server
  pServer = BLEDevice::createServer();
  pServer->setCallbacks(new ServerCallbacks());

  // Create the EEG service
  BLEService* pService = pServer->createService(SERVICE_UUID);

  // ── EEG Stream characteristic (NOTIFY) ──────────────────────────────────
  // The Python client subscribes to notifications on this characteristic.
  // Each notification is a batch of 10 × int16_t samples (20 bytes).
  pEEGStreamChar = pService->createCharacteristic(
    CHAR_EEG_STREAM_UUID,
    BLECharacteristic::PROPERTY_NOTIFY
  );
  // Add the standard Client Characteristic Configuration Descriptor (CCCD)
  // so clients can enable/disable notifications
  pEEGStreamChar->addDescriptor(new BLE2902());

  // ── Profile Selector characteristic (READ + WRITE) ──────────────────────
  // Write a byte 0-4 to switch mock user profiles from the app
  pProfileChar = pService->createCharacteristic(
    CHAR_PROFILE_SELECT_UUID,
    BLECharacteristic::PROPERTY_READ |
    BLECharacteristic::PROPERTY_WRITE
  );
  pProfileChar->setCallbacks(new ProfileWriteCallback());
  // Set initial value to the default profile index
  uint8_t initProfile = currentProfile;
  pProfileChar->setValue(&initProfile, 1);

  // ── Start the service ───────────────────────────────────────────────────
  pService->start();

  // ── Start advertising ───────────────────────────────────────────────────
  BLEAdvertising* pAdvertising = BLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(SERVICE_UUID);
  // Set advertising parameters for fast discovery
  pAdvertising->setScanResponse(true);
  pAdvertising->setMinPreferred(0x06);   // 7.5ms connection interval (iOS hint)
  pAdvertising->setMinPreferred(0x12);   // 22.5ms (Android hint)
  BLEDevice::startAdvertising();

  Serial.println("# BLE advertising started — device name: CortexKey-EEG");
  Serial.println("# Waiting for connection...");

  // Blink LED 3 times to signal ready
  for (int i = 0; i < 3; i++) {
    digitalWrite(LED_PIN, HIGH); delay(100);
    digitalWrite(LED_PIN, LOW);  delay(100);
  }

  lastSampleTime = micros();
}

// ═══════════════════════════════════════════════════════════════════════════
// MAIN LOOP — Generate samples at 250 Hz and send BLE notifications
// ═══════════════════════════════════════════════════════════════════════════

void loop() {
  unsigned long now = micros();

  // ── Generate a sample every 4000 μs (250 Hz) ───────────────────────────
  if ((now - lastSampleTime) >= SAMPLE_INTERVAL_US) {
    lastSampleTime = now;

    // Generate one mock EEG sample (microvolts, signed 16-bit)
    int16_t sample = generateSample();

    // Accumulate samples into a batch packet
    sampleBatch[batchIndex] = sample;
    batchIndex++;

    // ── When batch is full, send a BLE notification ─────────────────────
    if (batchIndex >= SAMPLES_PER_PACKET) {
      if (deviceConnected) {
        // Set the characteristic value to the batch buffer
        // 10 × int16_t = 20 bytes, transmitted as raw little-endian bytes
        pEEGStreamChar->setValue((uint8_t*)sampleBatch, SAMPLES_PER_PACKET * 2);
        // Send the notification to all subscribed clients
        pEEGStreamChar->notify();
      }
      batchIndex = 0;  // Reset batch for next packet

      // ── Also print to serial for debugging ──────────────────────────
      // Print the first sample of each batch (one per 40ms = 25 lines/sec)
      // This is handy for monitoring in the Arduino Serial Monitor
      static unsigned long serialPrintCount = 0;
      serialPrintCount++;
      if (serialPrintCount % 25 == 0) {  // Print once per second
        Serial.print("# Tx: ");
        Serial.print(sampleBatch[0]);
        Serial.print(" μV | Profile: ");
        Serial.print(profileNames[currentProfile]);
        Serial.print(" | Samples: ");
        Serial.println(globalSampleCount);
      }
    }

    // ── LED heartbeat: toggle every second ───────────────────────────────
    // Only blink when NOT connected (solid LED = connected)
    if (!deviceConnected && (globalSampleCount % SAMPLE_RATE_HZ == 0)) {
      digitalWrite(LED_PIN, !digitalRead(LED_PIN));
    }
  }

  // ── Handle BLE disconnection → reconnection ───────────────────────────
  // If the client just disconnected, restart advertising after a short delay
  if (!deviceConnected && oldDeviceState) {
    delay(500);   // Give the BLE stack time to clean up
    pServer->startAdvertising();
    Serial.println("# Re-advertising after disconnect");
    oldDeviceState = deviceConnected;
  }

  // Track connection state transitions
  if (deviceConnected && !oldDeviceState) {
    oldDeviceState = deviceConnected;
  }

  // Yield to the ESP32 RTOS (prevents watchdog timer resets)
  yield();
}

// ═══════════════════════════════════════════════════════════════════════════
// NOTES
// ═══════════════════════════════════════════════════════════════════════════
//
// BLE THROUGHPUT:
//   250 samples/sec × 2 bytes/sample = 500 bytes/sec
//   Batched into 25 notifications/sec × 20 bytes each
//   This is well within BLE 4.2 throughput limits (~1 KB/s at default MTU)
//
// LATENCY:
//   Batch latency: 10 samples / 250 Hz = 40 ms per notification
//   BLE connection interval: 7.5–22.5 ms (negotiated with OS)
//   Total end-to-end latency: ~50-80 ms (acceptable for 4-second auth windows)
//
// POWER:
//   ESP32 BLE active: ~100 mA (can be reduced with light sleep between samples)
//   With a 500 mAh LiPo: ~5 hours continuous streaming
//
// SWITCHING TO REAL ADC:
//   When the BioAmp EXG Pill arrives, change generateSample() to:
//     return (int16_t)(analogRead(34) - 2048);
//   Or better: use bioamp_serial.ino for USB, or keep this BLE sketch and
//   just swap the mock signal for analogRead.
