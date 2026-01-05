# IR Receiver Serial Configuration & LED Feedback Design

**Date:** 2026-01-04
**Status:** Approved
**Target:** ESP8266 IR receiver (irqtt/irqtt.ino)

## Overview

Enhance the ESP8266 IR-to-MQTT controller with three new capabilities:
1. Runtime configuration of WiFi/MQTT settings via JSON over serial
2. Visual feedback using WS2812 LED strip (40 LEDs on GPIO0/D3)
3. Persistent storage of all settings across reboots using EEPROM

## Architecture

### Three Main Subsystems

**1. Persistent Configuration System**
- EEPROM-based storage using a `ConfigData` struct containing all WiFi/MQTT settings
- Magic number validation (0xCAFE) to detect first boot vs. valid saved config
- On first boot or invalid EEPROM, load defaults from config.h defines
- Settings saved immediately after any config change via serial

**2. Serial JSON Command Handler**
- Non-blocking serial input buffering (read until newline)
- ArduinoJson library for parsing (efficient for embedded)
- Command dispatch system supporting: `config`, `get_config`, `status`, `reset_config`, `restart`
- Validation of all inputs (SSID length, port ranges, etc.)
- Human-readable JSON responses for all commands

**3. WS2812 LED Feedback System**
- FastLED library for WS2812 control
- Startup sequence with non-blocking state machine (yellow→red→blue→green)
- Button press rainbow mapping using HSV color space (12 stations = 30° hue increments)
- 200ms fade-out effect using exponential decay
- Special colors: green (volume), red (stop), purple (sleep)

All three systems integrate into the existing main loop without blocking IR reception or MQTT operations.

## EEPROM Structure & Persistence

### ConfigData Struct

```cpp
struct ConfigData {
  uint16_t magic;           // 0xCAFE = valid config
  char wifi_ssid[64];       // WiFi network name
  char wifi_pass[64];       // WiFi password
  char mqtt_server[128];    // MQTT broker hostname/IP
  uint16_t mqtt_port;       // MQTT broker port
  char mqtt_topic[128];     // MQTT command topic
  char sonos_room[64];      // Sonos room/zone name
  uint16_t led_pin;         // WS2812 data pin (GPIO number)
  uint16_t led_count;       // Number of LEDs in string
  uint16_t checksum;        // Simple validation
};
```

### Persistence Flow

1. **Boot:** Read EEPROM → Check magic number → Validate checksum
2. **Valid config found:** Load into runtime variables, connect WiFi/MQTT
3. **Invalid/first boot:** Load defaults from config.h, save to EEPROM
4. **Config command received:** Parse JSON → Validate → Update struct → Save to EEPROM → Reconnect WiFi/MQTT if changed
5. **Reset command:** Restore config.h defaults → Save to EEPROM → Reboot

### Functions

- `loadConfig()` - Read from EEPROM, validate, return success/fail
- `saveConfig()` - Calculate checksum, write to EEPROM
- `resetConfig()` - Load defaults from config.h defines
- Simple CRC16 checksum to detect corruption

### EEPROM Size

Total EEPROM allocation: 512 bytes (ConfigData ~450 bytes)

## Serial JSON Command Handler

### Command Processing

- Non-blocking serial reader accumulates characters into a buffer (max 512 bytes)
- On newline, attempt JSON parse with ArduinoJson
- Dispatch based on `cmd` field to handler functions
- Always respond with JSON (success/error feedback)

### Command: `config` - Update Settings

Update any combination of settings (partial or full update).

**Request:**
```json
{
  "cmd": "config",
  "wifi_ssid": "NewNetwork",
  "wifi_pass": "password123",
  "mqtt_server": "192.168.1.100",
  "mqtt_port": 1883,
  "mqtt_topic": "claremont_NoT/cmd",
  "sonos_room": "Bedroom"
}
```

**Behavior:**
- Parse all present fields, validate each
- Update ConfigData struct for valid fields only
- Save to EEPROM
- If WiFi/MQTT changed, disconnect and reconnect
- Invalid fields are skipped with warning

**Response:**
```json
{
  "status": "ok",
  "changed": ["wifi_ssid", "mqtt_port"]
}
```

### Command: `get_config` - Query Current Settings

Returns all configuration values with passwords masked.

**Request:**
```json
{"cmd": "get_config"}
```

**Response:**
```json
{
  "status": "ok",
  "config": {
    "wifi_ssid": "NewNetwork",
    "wifi_pass": "****",
    "mqtt_server": "192.168.1.100",
    "mqtt_port": 1883,
    "mqtt_topic": "claremont_NoT/cmd",
    "sonos_room": "Bedroom",
    "led_pin": 0,
    "led_count": 40
  }
}
```

### Command: `status` - Connection Status

Returns WiFi and MQTT connection status.

**Request:**
```json
{"cmd": "status"}
```

**Response:**
```json
{
  "status": "ok",
  "wifi": "connected",
  "ip": "192.168.1.100",
  "mqtt": "connected"
}
```

### Command: `reset_config` - Restore Defaults

Reset all settings to config.h defaults and reboot.

**Request:**
```json
{"cmd": "reset_config"}
```

**Response:**
```json
{
  "status": "ok",
  "msg": "Config reset, rebooting..."
}
```

**Behavior:**
- Load config.h default values
- Save to EEPROM
- Wait 1 second
- Call `ESP.restart()`

### Command: `restart` - Reboot Device

Reboot the ESP8266.

**Request:**
```json
{"cmd": "restart"}
```

**Response:**
```json
{
  "status": "ok",
  "msg": "Rebooting..."
}
```

**Behavior:**
- Wait 1 second
- Call `ESP.restart()`

### Input Validation

- **SSID/password:** 1-63 characters
- **MQTT server:** 1-127 characters
- **MQTT port:** 1-65535
- **MQTT topic:** 1-127 characters
- **Sonos room:** 1-63 characters
- **LED pin:** Valid GPIO number (0-16)
- **LED count:** 1-1000

Invalid commands return:
```json
{
  "status": "error",
  "msg": "Unknown command"
}
```

## WS2812 LED Control System

### Library

FastLED (better performance, easier HSV color handling than Adafruit_NeoPixel)

### LED Startup State Machine

```cpp
enum BootState {
  BOOT_INIT,    // Yellow pulse - initializing
  BOOT_WIFI,    // Red pulse - connecting to WiFi
  BOOT_MQTT,    // Blue pulse - connecting to MQTT
  BOOT_READY,   // Green flash - connected successfully
  BOOT_DONE     // Off - normal operation
};
```

**State Transitions:**
1. **BOOT_INIT:** Yellow pulse (500ms period) during initialization
2. **BOOT_WIFI:** Red pulse while `WiFi.status() != WL_CONNECTED`
3. **BOOT_MQTT:** Blue pulse while `!mqttClient.connected()`
4. **BOOT_READY:** Green flash (fade out over 500ms)
5. **BOOT_DONE:** LEDs off, ready for button presses

**Pulsing Effect:** Use `beatsin8()` for smooth breathing effect on entire strip.

### Button Press Color Mapping

**Station Buttons (0-9, *, #):** HSV Rainbow
- 12 buttons mapped to hue values: `button_index * 30°`
- Saturation: 255 (fully saturated)
- Value: 255 (full brightness)
- Colors: Red → Orange → Yellow → Green → Cyan → Blue → Indigo → Violet → Magenta → Pink → Rose → Red

**Control Buttons:**
- **Volume Up/Down:** Green (HSV: 96, 255, 255)
- **Stop (OK button):** Red (HSV: 0, 255, 255)
- **Sleep (Right button):** Purple (HSV: 192, 255, 255)
- **Left button:** No LED action (unmapped)

### Fade Effect

**Implementation:**
1. On button press: Set all LEDs to mapped color at full brightness
2. Start fade timer
3. Each loop iteration: Calculate elapsed time
4. Update brightness using exponential decay: `brightness = start_brightness * (1 - elapsed/200)^2`
5. After 200ms: Set brightness to 0, clear fade state

**Non-blocking:** Uses `millis()` to track elapsed time, updates brightness each loop without delay().

**Multiple Presses:** New button press cancels current fade and starts fresh with new color.

## Configuration Changes

### config.h Updates

Add these configurable defines:

```cpp
// WS2812 LED Configuration
#define LED_PIN 0              // GPIO0 (D3 on NodeMCU)
#define LED_COUNT 40           // Number of LEDs in string
#define LED_BRIGHTNESS 128     // Max brightness (0-255)

// Serial JSON Configuration
#define SERIAL_BAUD 115200     // Serial baud rate (existing)
#define SERIAL_BUFFER_SIZE 512 // Max JSON command size
```

### Library Dependencies

Add to sketch includes:

```cpp
#include <EEPROM.h>
#include <ArduinoJson.h>  // v6.x
#include <FastLED.h>
```

**Installation via Arduino Library Manager:**
- ArduinoJson (by Benoit Blanchon)
- FastLED (by Daniel Garcia)

## Integration into Existing Code

### setup() Sequence

1. `Serial.begin(SERIAL_BAUD)`
2. `EEPROM.begin(512)` and `loadConfig()`
3. `FastLED.addLeds<WS2812, LED_PIN, GRB>(leds, LED_COUNT)` and set to yellow pulse
4. `setupWiFi()` - LED transitions to red if fails, blue when connected
5. `mqttClient.setServer()` and `reconnectMQTT()` - LED transitions to blue, then green flash when connected
6. `irrecv.enableIRIn()` - unchanged
7. Transition to `BOOT_DONE` state (LEDs off)

### loop() Flow

1. **MQTT processing:** `mqttClient.loop()` (unchanged, stays first)
2. **MQTT reconnection:** Existing logic with LED state updates
3. **NEW: Serial commands:** `processSerialCommands()` - non-blocking JSON handler
4. **NEW: Boot LED updates:** `updateBootLED()` - handle startup sequence state machine
5. **NEW: Button LED updates:** `updateButtonLED()` - handle fade effect if active
6. **IR processing:** `irrecv.decode()` and existing button mapping (unchanged)
7. **Debug heartbeat:** Existing "." print every 5 seconds (unchanged)

## Error Handling & Edge Cases

### WiFi/MQTT Reconnection with LEDs

- **WiFi drops during operation:** LED goes to red pulse, attempt reconnect every 5 seconds
- **MQTT drops:** LED goes to blue pulse, attempt reconnect
- **Reconnected:** Brief green flash, return to BOOT_DONE (off)
- IR functionality continues working during disconnections

### Serial Command Error Cases

- **Malformed JSON:** `{"status":"error","msg":"Invalid JSON"}`
- **Missing cmd field:** `{"status":"error","msg":"Missing cmd field"}`
- **Invalid values:** `{"status":"error","msg":"Invalid port: must be 1-65535"}`
- **Buffer overflow (>512 bytes):** Clear buffer, return error
- **EEPROM write failures:** Log to serial, continue with current config

### EEPROM Corruption Handling

- **Invalid magic number:** Treat as first boot, load defaults from config.h
- **Bad checksum:** Load defaults, log warning to serial
- **After any failure:** Save valid defaults immediately

### LED Edge Cases

- **Button press during fade:** Cancel current fade, start new one
- **Multiple rapid presses:** Each starts fresh fade (restart timer)
- **LED operations never block:** IR reception and MQTT continue normally
- **Invalid LED pin/count:** Disable LEDs, log error, continue operation

### Memory Management

- **Static JSON buffer:** 1KB for parsing/serialization (no dynamic allocation)
- **EEPROM size:** 512 bytes (ConfigData ~450 bytes with padding)
- **No malloc/free:** All buffers statically allocated for stability

## Implementation Notes

### Button-to-Station Mapping

Current hardcoded mapping in switch statement (lines 223-290) remains unchanged:
- Buttons 1-9 → Stations 0-8
- Button * → Station 9
- Button 0 → Station 10
- Button # → Station 11

For LED rainbow mapping, station numbers 0-11 map to hue values 0°, 30°, 60°, ..., 330°.

### CRC16 Checksum Algorithm

Use simple CRC-16-CCITT for EEPROM validation:
```cpp
uint16_t crc16(const uint8_t *data, size_t len) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < len; i++) {
    crc ^= data[i] << 8;
    for (uint8_t j = 0; j < 8; j++) {
      if (crc & 0x8000) crc = (crc << 1) ^ 0x1021;
      else crc <<= 1;
    }
  }
  return crc;
}
```

### FastLED Configuration

```cpp
CRGB leds[LED_COUNT];

void setup() {
  FastLED.addLeds<WS2812, LED_PIN, GRB>(leds, LED_COUNT);
  FastLED.setBrightness(LED_BRIGHTNESS);
}
```

## Testing Strategy

1. **EEPROM Persistence:**
   - First boot: Verify defaults loaded from config.h
   - Config change via serial: Verify saved and reloaded after reboot
   - EEPROM clear: Verify defaults restored

2. **Serial Commands:**
   - Test each command with valid inputs
   - Test error cases (malformed JSON, invalid values)
   - Verify WiFi/MQTT reconnection on config change

3. **LED Feedback:**
   - Verify startup sequence colors and timing
   - Test all button colors (rainbow + special colors)
   - Verify 200ms fade timing
   - Test rapid button presses (fade cancellation)

4. **Integration:**
   - Verify IR reception continues during LED operations
   - Verify MQTT operations continue during serial input
   - Test reconnection scenarios (WiFi drop, MQTT drop)

## Success Criteria

- ✓ All WiFi/MQTT settings configurable via serial JSON
- ✓ Settings persist across reboots (EEPROM)
- ✓ LED shows clear startup sequence (yellow→red→blue→green)
- ✓ LED flashes appropriate colors for all button types
- ✓ 200ms fade-out looks smooth
- ✓ No blocking of IR reception or MQTT operations
- ✓ All serial commands work with proper error handling
- ✓ Config can be queried and reset via serial

## Future Enhancements (Out of Scope)

- Web-based configuration interface
- OTA firmware updates
- Custom button-to-color mappings
- LED brightness adjustment via serial
- Multiple LED animation modes
