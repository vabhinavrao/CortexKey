/**
 * CortexKey — BioAmp EXG Pill Firmware
 * ESP32 / Arduino Uno / Nano
 *
 * Samples the BioAmp EXG Pill output at exactly 250 Hz and streams
 * raw ADC values over Serial (USB) to the host PC running CortexKey.
 *
 * ─────────────────────────────────────────────────────────────────────────
 * WIRING (EEG setup — frontal lobe authentication)
 * ─────────────────────────────────────────────────────────────────────────
 *
 *  BioAmp EXG Pill              ESP32 DevKit v1
 *  ───────────────              ─────────────────
 *  OUT (yellow) ──────────────► GPIO 34  (or any ADC1 pin — NOT GPIO 36/39)
 *  GND (black)  ──────────────► GND
 *  VCC (red)    ──────────────► 3.3V
 *
 *  BioAmp EXG Pill              Arduino Uno / Nano
 *  ───────────────              ──────────────────
 *  OUT (yellow) ──────────────► A0
 *  GND (black)  ──────────────► GND
 *  VCC (red)    ──────────────► 5V    ← use 5V for Uno/Nano (not 3.3V)
 *
 *  Electrode placement (standard EEG — Fp1/Fp2):
 *  ┌──────────────────────────────────────────────────────────┐
 *  │  REF electrode → mastoid bone (behind ear) OR earlobe    │
 *  │  SIG electrode → Fp1 or Fp2 (forehead, above eyebrow)   │
 *  │  GND electrode → other side of forehead (or chin)        │
 *  └──────────────────────────────────────────────────────────┘
 *
 * ─────────────────────────────────────────────────────────────────────────
 * CONFIGURATION — edit the defines below to match your board
 * ─────────────────────────────────────────────────────────────────────────
 */

// ── Select your board (uncomment ONE) ─────────────────────────────────────
#define BOARD_ESP32          // 12-bit ADC, 3.3V, 250 Hz
// #define BOARD_ARDUINO_UNO // 10-bit ADC, 5V, 250 Hz (lower quality)

// ── Pin configuration ──────────────────────────────────────────────────────
#ifdef BOARD_ESP32
  #define EEG_PIN          34    // GPIO 34 (ADC1_CH6) — input-only, no internal pullup
  #define LED_BUILTIN      2     // Onboard LED (GPIO 2 on most ESP32 DevKits)
  #define ADC_RESOLUTION   12    // 12-bit → 0 to 4095
#else
  #define EEG_PIN          A0    // Analog pin 0
  #define ADC_RESOLUTION   10    // 10-bit → 0 to 1023
#endif

// ── Sampling ───────────────────────────────────────────────────────────────
#define SAMPLE_RATE_HZ     250   // Must match SAMPLING_RATE in hardware_reader.py
#define SAMPLE_INTERVAL_US (1000000 / SAMPLE_RATE_HZ)  // 4000 μs = 4 ms

// ── Serial ─────────────────────────────────────────────────────────────────
#define BAUD_RATE          115200  // Must match BAUD_RATE in hardware_reader.py

// ── Data format (uncomment ONE) ────────────────────────────────────────────
#define FORMAT_ASCII       // Human-readable integers, one per line (default)
// #define FORMAT_BINARY   // 4-byte packets: 0xA5 | hi | lo | checksum

// ─────────────────────────────────────────────────────────────────────────
// GLOBALS
// ─────────────────────────────────────────────────────────────────────────

volatile unsigned long lastSampleTime = 0;
unsigned long sampleCount = 0;

// ─────────────────────────────────────────────────────────────────────────
// SETUP
// ─────────────────────────────────────────────────────────────────────────

void setup() {
  Serial.begin(BAUD_RATE);

  // Wait for Serial to be ready (especially important on Leonardo / Pro Micro)
  while (!Serial) { delay(10); }

  // Configure ADC
#ifdef BOARD_ESP32
  analogReadResolution(ADC_RESOLUTION);   // Set 12-bit resolution (default is 12 on ESP32)
  analogSetAttenuation(ADC_11db);         // Full 3.3V range (0-3.3V input range)
  // Note: ESP32 ADC has non-linearity above ~3.0V and below ~0.1V.
  // The BioAmp EXG Pill output is centered at VCC/2 (≈1.65V) with ±1V swing,
  // which keeps us in the linear region.
#endif

  // Set EEG pin as input
  pinMode(EEG_PIN, INPUT);

  // Blink LED 3 times to signal ready
  pinMode(LED_BUILTIN, OUTPUT);
  for (int i = 0; i < 3; i++) {
    digitalWrite(LED_BUILTIN, HIGH); delay(100);
    digitalWrite(LED_BUILTIN, LOW);  delay(100);
  }

  // Send firmware header as comments (Python parser ignores lines starting with #)
  Serial.println("# CortexKey EEG Firmware v1.0");
  Serial.print("# Board: ");
#ifdef BOARD_ESP32
  Serial.println("ESP32 (12-bit, 3.3V)");
#else
  Serial.println("Arduino (10-bit, 5V)");
#endif
  Serial.print("# Sample rate: ");
  Serial.print(SAMPLE_RATE_HZ);
  Serial.println(" Hz");
  Serial.print("# Baud rate: ");
  Serial.print(BAUD_RATE);
  Serial.println(" bps");
  Serial.print("# Format: ");
#ifdef FORMAT_ASCII
  Serial.println("ASCII (integer per line)");
#else
  Serial.println("Binary (4-byte packets)");
#endif
  Serial.println("# --- DATA START ---");

  lastSampleTime = micros();
}

// ─────────────────────────────────────────────────────────────────────────
// MAIN LOOP — runs as fast as possible, samples at exactly 250 Hz
// ─────────────────────────────────────────────────────────────────────────

void loop() {
  unsigned long now = micros();

  // Check if it's time to take a sample (every 4000 μs)
  if ((now - lastSampleTime) >= SAMPLE_INTERVAL_US) {
    lastSampleTime = now;

    // Read ADC
    int adcValue = analogRead(EEG_PIN);

    // Transmit
#ifdef FORMAT_ASCII
    // ASCII: one integer per line
    // Example output:  "2048\n"
    Serial.println(adcValue);

#else  // FORMAT_BINARY
    // Binary packet: 0xA5 | high_byte | low_byte | checksum
    // Faster transmission, lower CPU overhead on host
    byte hi = (adcValue >> 8) & 0xFF;
    byte lo = adcValue & 0xFF;
    byte checksum = 0xA5 ^ hi ^ lo;

    Serial.write(0xA5);    // Start byte (sync marker)
    Serial.write(hi);
    Serial.write(lo);
    Serial.write(checksum);
#endif

    sampleCount++;

    // Blink LED every 250 samples (once per second) as heartbeat
    if (sampleCount % SAMPLE_RATE_HZ == 0) {
      digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));
    }

    // Drain incoming serial (Python might send commands in future versions)
    while (Serial.available()) {
      char cmd = Serial.read();
      // Reserved for future use:
      // 'r' = reset counter
      // 'p' = pause
      // 's' = resume
      if (cmd == 'r') {
        sampleCount = 0;
        Serial.println("# Counter reset");
      }
    }
  }

  // Yield to RTOS on ESP32 (prevents watchdog resets)
#ifdef BOARD_ESP32
  yield();
#endif
}

// ─────────────────────────────────────────────────────────────────────────
// TIMING ACCURACY NOTES
// ─────────────────────────────────────────────────────────────────────────
//
// The loop() approach has ±10-50 μs jitter due to:
//   - Serial.println() blocking (takes ~0.1 ms at 115200 baud)
//   - ESP32 WiFi/BT background tasks (disable if not needed)
//
// For higher timing accuracy (optional):
//   Replace loop() with a hardware timer interrupt:
//
//   hw_timer_t* timer = NULL;
//   void IRAM_ATTR onTimer() {
//     portENTER_CRITICAL_ISR(&timerMux);
//     sampleReady = true;
//     portEXIT_CRITICAL_ISR(&timerMux);
//   }
//   // In setup():
//   timer = timerBegin(0, 80, true);          // 80 MHz / 80 = 1 MHz tick
//   timerAttachInterrupt(timer, &onTimer, true);
//   timerAlarmWrite(timer, 4000, true);        // 1 MHz / 4000 = 250 Hz
//   timerAlarmEnable(timer);
//
// For CortexKey authentication (4-second windows, PSD features), the
// ±50 μs jitter from loop() is perfectly acceptable — it does not
// meaningfully affect the PSD or band power features.
