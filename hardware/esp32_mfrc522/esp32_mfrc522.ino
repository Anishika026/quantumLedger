#include <SPI.h>
#include <MFRC522.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// ESP32 DevKit + MFRC522 over the default VSPI pins.
static constexpr uint8_t RFID_SS_PIN = 5;
static constexpr uint8_t RFID_RST_PIN = 27;
static constexpr uint32_t HOST_BAUD = 115200;
static constexpr bool ENROLLMENT_MODE = false;
static constexpr uint8_t RED_LED_PIN = 25;
static constexpr uint8_t GREEN_LED_PIN = 26;
static constexpr uint8_t BLUE_LED_PIN = 32;
static constexpr uint8_t BUZZER_PIN = 13;
static constexpr uint8_t OLED_SDA_PIN = 21;
static constexpr uint8_t OLED_SCL_PIN = 22;
static constexpr uint8_t OLED_ADDRESS = 0x3C;
static constexpr uint8_t SCREEN_WIDTH = 128;
static constexpr uint8_t SCREEN_HEIGHT = 64;

// Replace these example UIDs with the values printed in enrollment mode.
static constexpr char ACTIVE_CARD_UID[] = "2189DFB0";
static constexpr char LOCKED_CARD_UID[] = "6A97A8E3";
static constexpr char LOW_BALANCE_CARD_UID[] = "REPLACE_LOW_BALANCE_UID";

MFRC522 reader(RFID_SS_PIN, RFID_RST_PIN);
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);
String lastUid;
unsigned long lastReadMs = 0;
static constexpr unsigned long DUPLICATE_WINDOW_MS = 1500;

void setLights(bool red, bool green, bool blue) {
  digitalWrite(RED_LED_PIN, red ? HIGH : LOW);
  digitalWrite(GREEN_LED_PIN, green ? HIGH : LOW);
  digitalWrite(BLUE_LED_PIN, blue ? HIGH : LOW);
}

void showStatus(const char* title, const char* detail) {
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(2);
  display.setCursor(0, 0);
  display.println(title);
  display.setTextSize(1);
  display.setCursor(0, 30);
  display.println(detail);
  display.display();
}

void beep(uint16_t frequency, uint16_t durationMs) {
  tone(BUZZER_PIN, frequency, durationMs);
  delay(durationMs);
  noTone(BUZZER_PIN);
}

void handleHostResult() {
  if (!Serial.available()) {
    return;
  }
  String command = Serial.readStringUntil('\n');
  command.trim();
  if (command == "PAYMENT_APPROVED") {
    setLights(false, true, false);
    showStatus("APPROVED", "Payment authorized");
    beep(2200, 180);
    delay(1200);
    setLights(false, false, true);
    showStatus("READY", "Tap card to pay");
  } else if (command == "PAYMENT_DECLINED") {
    setLights(true, false, false);
    showStatus("DECLINED", "Payment not approved");
    beep(500, 450);
    delay(1200);
    setLights(false, false, true);
    showStatus("READY", "Tap card to pay");
  }
}

String uidToHex() {
  String value;
  for (byte index = 0; index < reader.uid.size; index++) {
    if (reader.uid.uidByte[index] < 0x10) {
      value += "0";
    }
    value += String(reader.uid.uidByte[index], HEX);
  }
  value.toUpperCase();
  return value;
}

String tokenForUid(const String& uid) {
  if (uid == ACTIVE_CARD_UID) {
    return "RFID_TEST_001";
  }
  if (uid == LOCKED_CARD_UID) {
    return "RFID_LOCKED_001";
  }
  if (uid == LOW_BALANCE_CARD_UID) {
    return "RFID_LOW_BALANCE_001";
  }
  return "UNKNOWN_TOKEN";
}

void setup() {
  pinMode(RED_LED_PIN, OUTPUT);
  pinMode(GREEN_LED_PIN, OUTPUT);
  pinMode(BLUE_LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  setLights(false, false, true);
  Serial.begin(HOST_BAUD);
  Wire.begin(OLED_SDA_PIN, OLED_SCL_PIN);
  display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDRESS);
  showStatus("READY", "Tap card to pay");
  SPI.begin();
  reader.PCD_Init();
  delay(50);
  Serial.println("RFID_READER_READY");
}

void loop() {
  handleHostResult();
  if (!reader.PICC_IsNewCardPresent() || !reader.PICC_ReadCardSerial()) {
    delay(20);
    return;
  }

  String uid = uidToHex();
  unsigned long now = millis();
  if (uid != lastUid || now - lastReadMs > DUPLICATE_WINDOW_MS) {
    setLights(false, false, true);
    showStatus("PROCESSING", "Reading card...");
    beep(1800, 100);
    if (ENROLLMENT_MODE) {
      Serial.print("RFID_UID:");
      Serial.println(uid);
    } else {
      Serial.println(tokenForUid(uid));
    }
    lastUid = uid;
    lastReadMs = now;
  }

  reader.PICC_HaltA();
  reader.PCD_StopCrypto1();
  delay(50);
}
