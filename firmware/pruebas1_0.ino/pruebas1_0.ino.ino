#include <WiFi.h>
#include <MQTT.h>
#include <ArduinoJson.h>
#include "DHT.h"

const char* ssid = "Andres";
const char* password = "Mimillita.";
const char* mqtt_server = "172.20.10.3";   // IP actual de tu PC

#define DHTPIN 4
#define DHTTYPE DHT11
#define MQ7PIN 34

// ===== CESTO ENTRE PRUEBAS: 0 o 1 =====
const int QOS_LEVEL = 1;
// ============================================

DHT dht(DHTPIN, DHTTYPE);
WiFiClient net;
MQTTClient client(512);

unsigned long previousMillis = 0;
const long interval = 500;
unsigned long seq = 0;
float lastTemp = 0.0, lastHum = 0.0;
unsigned long lastDht = 0;

void connectMQTT() {
  while (WiFi.status() != WL_CONNECTED) { delay(500); }
  while (!client.connect("ESP32_FIRE_DETECTOR")) { delay(1000); }
  Serial.println("Conectado al broker");
}

void setup() {
  Serial.begin(115200);
  dht.begin();
  pinMode(MQ7PIN, INPUT);
  WiFi.begin(ssid, password);
  client.begin(mqtt_server, 1883, net);
  connectMQTT();
}

void loop() {
  client.loop();
  if (!client.connected()) connectMQTT();

  unsigned long now = millis();

  if (now - lastDht >= 2500) {
    lastDht = now;
    float t = dht.readTemperature();
    float h = dht.readHumidity();
    if (!isnan(t)) lastTemp = t;
    if (!isnan(h)) lastHum = h;
  }

  if (now - previousMillis >= interval) {
    previousMillis = now;
    seq++;

    StaticJsonDocument<384> doc;
    doc["node_id"] = "ESP32_FIRE_DETECTION";
    doc["seq"] = seq;
    JsonObject data = doc.createNestedObject("data");
    data["temp"] = round(lastTemp * 10.0) / 10.0;
    data["hum"] = round(lastHum * 10.0) / 10.0;
    data["mq7_raw"] = analogRead(MQ7PIN);
    doc["heap_free"] = ESP.getFreeHeap();

    char buffer[384];
    serializeJson(doc, buffer);

    unsigned long t0 = micros();
    bool ok = client.publish("sensores/incendios/telemetria", buffer, false, QOS_LEVEL);
    unsigned long dt = micros() - t0;

    Serial.print("QoS=");  Serial.print(QOS_LEVEL);
    Serial.print(" seq="); Serial.print(seq);
    Serial.print(" ok=");  Serial.print(ok);
    Serial.print(" publish_us="); Serial.println(dt);
  }
}