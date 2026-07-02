#include <Arduino.h>

const uint32_t SERIAL_BAUD = 115200;

// Pin map
const uint8_t PIN_TOUCH = 12;
const uint8_t PIN_PHOTO = 3;
const uint8_t PIN_BUZZER = 8;

// Protocol constants
const uint8_t START_BYTE = 0xAA;
const uint8_t END_BYTE_1 = 0xAA;
const uint8_t END_BYTE_2 = 0xEE;

const uint8_t PKT_SENSOR_STATE = 0x31;
const uint8_t PKT_SET_TOUCH = 0x41;
const uint8_t PKT_SET_PHOTO = 0x42;
const uint8_t PKT_SET_MELODY = 0x43;
const uint8_t PKT_SET_BUZZER = 0X44;
const uint8_t PKT_PING = 0x7F;

const uint8_t MAX_PAYLOAD_LEN = 32;

// Device states
uint8_t touch_state = 0;
uint8_t photo_state = 0;
uint8_t melody_state = 0;
uint8_t buzzer_state = 0;

uint8_t tx_sequence = 0;

// Periodic publish
unsigned long last_publish_ms = 0;
const unsigned long PUBLISH_PERIOD_MS = 100;

int KY_036_Flag = -1; // Flag initially set to (-1)

// bringup에 사용되는 음들의 주파수 정의 (Hz)
const uint16_t NOTE_E7 = 2637;
const uint16_t NOTE_C7 = 2093;
const uint16_t NOTE_G7 = 3136;
const uint16_t NOTE_G6 = 1568;

// 멜로디 배열 (총 7개의 음)
int melody[] = {NOTE_E7, NOTE_E7, 0, NOTE_E7, 0, NOTE_C7, NOTE_E7,
                0,       NOTE_G7, 0, 0,       0, NOTE_G6};

// 각 음의 박자 (밀리초 단위, ms)
// 마리오 특유의 통통 튀는 박자를 맞추기 위해 세밀하게 조정되었습니다.
int duration[] = {120, 120, 120, 120, 120, 120, 120,
                  120, 120, 120, 120, 120, 120};

int count = sizeof(melody) / sizeof(melody[0]);

// RX parser state
enum ParserState {
  WAIT_START_1,
  WAIT_START_2,
  WAIT_START_3,
  READ_PACKET_ID,
  READ_LENGTH,
  READ_SEQUENCE,
  READ_PAYLOAD,
  READ_CHECKSUM,
  READ_END_1,
  READ_END_2
};

ParserState parser_state = WAIT_START_1;

uint8_t rx_packet_id = 0;
uint8_t rx_length = 0;
uint8_t rx_sequence = 0;
uint8_t rx_payload[MAX_PAYLOAD_LEN];
uint8_t rx_payload_index = 0;
uint8_t rx_checksum = 0;

uint8_t calcChecksum(uint8_t packet_id, uint8_t length, uint8_t sequence,
                     const uint8_t *payload) {
  uint16_t sum = 0;

  sum += packet_id;
  sum += length;
  sum += sequence;

  for (uint8_t i = 0; i < length; i++) {
    sum += payload[i];
  }

  return (uint8_t)(sum & 0xFF);
}

void sendPacket(uint8_t packet_id, const uint8_t *payload, uint8_t length) {
  uint8_t checksum = calcChecksum(packet_id, length, tx_sequence, payload);

  Serial.write(START_BYTE);
  Serial.write(START_BYTE);
  Serial.write(START_BYTE);

  Serial.write(packet_id);
  Serial.write(length);
  Serial.write(tx_sequence);

  for (uint8_t i = 0; i < length; i++) {
    Serial.write(payload[i]);
  }

  Serial.write(checksum);

  Serial.write(END_BYTE_1);
  Serial.write(END_BYTE_2);

  tx_sequence++;
}

void applyTouch(uint8_t state) {
  touch_state = state ? 1 : 0;
  digitalWrite(LED_BUILTIN, touch_state ? HIGH : LOW);
}

void applyPhoto(uint8_t state) {
  photo_state = state ? 1 : 0;
  if (photo_state) {
    tone(PIN_BUZZER, 523);
   
  } else {
    noTone(PIN_BUZZER);
  }
}

void applyBuzzer(uint8_t state) {
  buzzer_state = state ? 1 : 0;
  if (buzzer_state) {
    tone(PIN_BUZZER, 523);
    
  } else {
    noTone(PIN_BUZZER);
  }
}

void readTouch() {

  int ky036_Dval = digitalRead(PIN_TOUCH); // Reads digital value
  if (ky036_Dval == HIGH) {                // Touch detected

    // Serial.print("\nky036_Dval: ");           // Uncomment the Serial.print
    // Serial.println(ky036_Dval);               // statement to see how the
    // Serial.print("KY_036_Flag pre-toggle: "); // the FLAG changes
    // Serial.println(KY_036_Flag);              // with each touch

    KY_036_Flag =
        KY_036_Flag *
        -1; // toggle the Flag from -1 to +1 with each touch of the sensor

    // Serial.print("KY_036_Flag post-toggle: "); // Uncomment these as well
    // Serial.println(KY_036_Flag);               // to see the variables change

    if (KY_036_Flag > 0) { // if the Flag is +1 (LED ON)
      touch_state = 1;
    } else { // if the flag is -1 (LED OFF)
      touch_state = 0;
    }
    delay(
        250); // The sensor bounces and we only want to capture the first touch
  }
}

void readPhoto() {
  int val = digitalRead(PIN_PHOTO);
  if (val == OUTPUT) {
    photo_state = 1;
    delay(10);
  } else {
    photo_state = 0;
  }

  delay(10);
}

void applyMelody(uint8_t state) {

  melody_state = state ? 1 : 0;

  if (melody_state != 1)
    return;

  //   int count = sizeof(melody) / sizeof(melody[0]);

  for (int i = 0; i < count; i++) {
    tone(PIN_BUZZER, melody[i], duration[i]);
    delay(duration[i] * 1.3); // 음 사이를 약간 띄움
  }

  noTone(PIN_BUZZER);
}

void sendSensorState() {
  uint8_t payload[4];

  payload[0] = touch_state;
  payload[1] = photo_state;
  payload[2] = melody_state;
  payload[3] = buzzer_state;

  sendPacket(PKT_SENSOR_STATE, payload, 4);
}

void handlePacket(uint8_t packet_id, uint8_t length, uint8_t sequence,
                  const uint8_t *payload) {
  (void)sequence;

  if (packet_id == PKT_SET_TOUCH) {
    if (length != 1) {
      return;
    }
    applyTouch(payload[0]);
    sendSensorState();
  } else if (packet_id == PKT_SET_PHOTO) {

    if (length != 1)
      return;

    applyPhoto(payload[0]);
    sendSensorState();
  } else if (packet_id == PKT_SET_MELODY) {

    if (length != 1)
      return;

    applyMelody(payload[0]);
    sendSensorState();
  } else if (packet_id == PKT_SET_BUZZER) {

    if (length != 1)
      return;

    applyBuzzer(payload[0]);
    sendSensorState();
  }
}

void resetParser() {
  parser_state = WAIT_START_1;
  rx_packet_id = 0;
  rx_length = 0;
  rx_sequence = 0;
  rx_payload_index = 0;
  rx_checksum = 0;
}

void parseByte(uint8_t byte_in) {
  switch (parser_state) {
  case WAIT_START_1:
    if (byte_in == START_BYTE) {
      parser_state = WAIT_START_2;
    }
    break;

  case WAIT_START_2:
    if (byte_in == START_BYTE) {
      parser_state = WAIT_START_3;
    } else {
      parser_state = WAIT_START_1;
    }
    break;

  case WAIT_START_3:
    if (byte_in == START_BYTE) {
      parser_state = READ_PACKET_ID;
    } else {
      parser_state = WAIT_START_1;
    }
    break;

  case READ_PACKET_ID:
    rx_packet_id = byte_in;
    parser_state = READ_LENGTH;
    break;

  case READ_LENGTH:
    rx_length = byte_in;

    if (rx_length > MAX_PAYLOAD_LEN) {
      resetParser();
      return;
    }

    rx_payload_index = 0;
    parser_state = READ_SEQUENCE;
    break;

  case READ_SEQUENCE:
    rx_sequence = byte_in;

    if (rx_length == 0) {
      parser_state = READ_CHECKSUM;
    } else {
      parser_state = READ_PAYLOAD;
    }
    break;

  case READ_PAYLOAD:
    rx_payload[rx_payload_index] = byte_in;
    rx_payload_index++;

    if (rx_payload_index >= rx_length) {
      parser_state = READ_CHECKSUM;
    }
    break;

  case READ_CHECKSUM:
    rx_checksum = byte_in;
    parser_state = READ_END_1;
    break;

  case READ_END_1:
    if (byte_in == END_BYTE_1) {
      parser_state = READ_END_2;
    } else {
      resetParser();
    }
    break;

  case READ_END_2:
    if (byte_in == END_BYTE_2) {
      uint8_t calculated =
          calcChecksum(rx_packet_id, rx_length, rx_sequence, rx_payload);

      if (calculated == rx_checksum) {
        handlePacket(rx_packet_id, rx_length, rx_sequence, rx_payload);
      }
    }

    resetParser();
    break;

  default:
    resetParser();
    break;
  }
}

void readSerial() {
  while (Serial.available() > 0) {
    uint8_t b = (uint8_t)Serial.read();
    parseByte(b);
  }
}

void setup() {
  Serial.begin(115200);

  pinMode(LED_BUILTIN, OUTPUT); // define LED_BUILTIN as output interface
  pinMode(PIN_TOUCH, INPUT);    // define digital pin as input interface
  pinMode(PIN_PHOTO, INPUT);
  pinMode(PIN_BUZZER, OUTPUT);

  applyTouch(0);
  applyPhoto(0);
  applyMelody(0);
  applyBuzzer(0);

  Serial.begin(SERIAL_BAUD);

  delay(1000);
  sendSensorState();
}

void loop() {
  readSerial();
  readTouch();
  readPhoto();
  unsigned long now = millis();

  if ((now - last_publish_ms) >= PUBLISH_PERIOD_MS) {
    last_publish_ms = now;
    sendSensorState();
  }
}
