/*
 * ESP8266 IR Decoder with MQTT
 * Decodes IR signals from a 38kHz IR receiver on GPIO5 (D1 on NodeMCU)
 * Sends MQTT commands to control Sonos/radio
 */

#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <IRremoteESP8266.h>
#include <IRrecv.h>
#include <IRutils.h>
#include "config.h"

// IR Receiver pin
const uint16_t kRecvPin = 5; // GPIO5 (D1 on NodeMCU)

// Buffer size for capturing IR signals
const uint16_t kCaptureBufferSize = 1024;

// Timeout for IR signals (milliseconds)
const uint8_t kTimeout = 50;

// IR receiver object with larger buffer and timeout
IRrecv irrecv(kRecvPin, kCaptureBufferSize, kTimeout, true);

// Decode results
decode_results results;

// Last valid code received (for filtering repeats)
uint64_t lastCode = 0;
unsigned long lastCodeTime = 0;

// WiFi and MQTT clients
WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);

// Function to connect to WiFi
void setupWiFi() {
  Serial.println();
  Serial.print("Connecting to WiFi: ");
  Serial.println(WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.println("WiFi connected!");
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());
}

// Function to connect to MQTT broker
void reconnectMQTT() {
  while (!mqttClient.connected()) {
    Serial.print("Attempting MQTT connection...");

    if (mqttClient.connect("ESP8266_IR_Remote")) {
      Serial.println("connected!");
    } else {
      Serial.print("failed, rc=");
      Serial.print(mqttClient.state());
      Serial.println(" retrying in 5 seconds");
      delay(5000);
    }
  }
}

// Function to send MQTT command
void sendMQTTCommand(const char* cmd) {
  if (!mqttClient.connected()) {
    reconnectMQTT();
  }

  String payload = "{\"cmd\":\"";
  payload += cmd;
  payload += "\",\"room\":\"";
  payload += SONOS_ROOM;
  payload += "\"}";

  Serial.print("Publishing MQTT: ");
  Serial.println(payload);

  mqttClient.publish(MQTT_TOPIC, payload.c_str());
}

// Function to send station selection
void sendStationCommand(int stationIndex) {
  if (!mqttClient.connected()) {
    reconnectMQTT();
  }

  String payload = "{\"station\":";
  payload += stationIndex;
  payload += ",\"room\":\"";
  payload += SONOS_ROOM;
  payload += "\"}";

  Serial.print("Publishing MQTT: ");
  Serial.println(payload);

  mqttClient.publish(MQTT_TOPIC, payload.c_str());
}

void setup() {
  Serial.begin(115200);

  // Wait for serial to initialize
  delay(500);

  Serial.println();
  Serial.println("ESP8266 IR to MQTT Controller");
  Serial.println("==============================");

  // Connect to WiFi
  setupWiFi();

  // Setup MQTT
  mqttClient.setServer(MQTT_SERVER, MQTT_PORT);
  reconnectMQTT();

  Serial.println("Listening for IR signals on GPIO5 (D1)...");
  Serial.println();

  // Start the IR receiver
  irrecv.enableIRIn();
}

void loop() {
  // Check if an IR signal has been received
  if (irrecv.decode(&results)) {
    // Filter out invalid signals
    bool isValid = true;

    // Ignore UNKNOWN protocols (often noise)
    if (results.decode_type == UNKNOWN) {
      Serial.println("[Filtered: UNKNOWN protocol - likely noise]");
      isValid = false;
    }

    // Ignore repeat codes (0xFFFFFFFF or 0xFFFFFFFFFFFFFFFF)
    if (results.value == 0xFFFFFFFF || results.value == 0xFFFFFFFFFFFFFFFF) {
      Serial.println("[Filtered: Repeat code]");
      isValid = false;
    }

    // Debounce: Ignore same code within 200ms
    unsigned long now = millis();
    if (results.value == lastCode && (now - lastCodeTime) < 200) {
      Serial.println("[Filtered: Duplicate within 200ms]");
      isValid = false;
    }

    // Only print valid codes
    if (isValid) {
      // Update last code tracking
      lastCode = results.value;
      lastCodeTime = now;

      // Print a separator
      Serial.println("---");
      Serial.println("IR SIGNAL DETECTED!");

      // Print timestamp
      Serial.print("Timestamp: ");
      Serial.println(now);

      // Print protocol
      Serial.print("Protocol: ");
      Serial.println(typeToString(results.decode_type));

      // Print the hex code
      Serial.print("Code: 0x");
      serialPrintUint64(results.value, HEX);
      Serial.println();

      // Print bit count
      Serial.print("Bits: ");
      Serial.println(results.bits);

      // Map code to button name and send MQTT commands
      Serial.print("Button: ");
      switch(results.value) {
        case 0xFFA25D:
          Serial.println("1 - Station 0");
          sendStationCommand(0);
          break;
        case 0xFF629D:
          Serial.println("2 - Station 1");
          sendStationCommand(1);
          break;
        case 0xFFE21D:
          Serial.println("3 - Station 2");
          sendStationCommand(2);
          break;
        case 0xFF22DD:
          Serial.println("4 - Station 3");
          sendStationCommand(3);
          break;
        case 0xFF02FD:
          Serial.println("5 - Station 4");
          sendStationCommand(4);
          break;
        case 0xFFC23D:
          Serial.println("6 - Station 5");
          sendStationCommand(5);
          break;
        case 0xFFE01F:
          Serial.println("7 - Station 6");
          sendStationCommand(6);
          break;
        case 0xFFA857:
          Serial.println("8 - Station 7");
          sendStationCommand(7);
          break;
        case 0xFF906F:
          Serial.println("9 - Station 8");
          sendStationCommand(8);
          break;
        case 0xFF6897:
          Serial.println("* - Station 9");
          sendStationCommand(9);
          break;
        case 0xFF9867:
          Serial.println("0 - Station 10");
          sendStationCommand(10);
          break;
        case 0xFFB04F:
          Serial.println("# - Station 11");
          sendStationCommand(11);
          break;
        case 0xFF10EF: Serial.println("L (Left)"); break;
        case 0xFF5AA5: Serial.println("R (Right)"); break;
        case 0xFF18E7:
          Serial.println("U (Up) - Volume Up");
          sendMQTTCommand("vup");
          break;
        case 0xFF4AB5:
          Serial.println("D (Down) - Volume Down");
          sendMQTTCommand("vdown");
          break;
        case 0xFF38C7:
          Serial.println("O (OK/Enter) - Stop");
          sendMQTTCommand("stop");
          break;
        default: Serial.println("UNKNOWN BUTTON"); break;
      }

      // Print raw timing data (optional, useful for debugging)
      Serial.print("Raw (");
      Serial.print(results.rawlen - 1);
      Serial.print("): ");

      for (uint16_t i = 1; i < results.rawlen; i++) {
        Serial.print(results.rawbuf[i] * kRawTick);
        if (i < results.rawlen - 1) {
          Serial.print(", ");
        }
      }
      Serial.println();
      Serial.println();
    }

    // Resume receiving for the next signal
    irrecv.resume();
  }

  // Keep MQTT connection alive
  if (!mqttClient.connected()) {
    reconnectMQTT();
  }
  mqttClient.loop();

  // Debug: Print a dot every 5 seconds to show we're alive
  static unsigned long lastDebug = 0;
  if (millis() - lastDebug > 5000) {
    Serial.print(".");
    Serial.flush();
    lastDebug = millis();
  }
}
