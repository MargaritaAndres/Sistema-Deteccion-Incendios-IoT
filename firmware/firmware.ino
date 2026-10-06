#include "DHT.h"
#include <ArduinoJson.h>

// Definición de pines e instancias
#define DHTPIN 4
#define DHTTYPE DHT11
#define MQ7PIN 34

DHT dht(DHTPIN, DHTTYPE);

// Muestreo no bloqueante con millis()
unsigned long previousMillis = 0;
const long interval = 2500; 

// Filtro de Promedio Móvil para la señal del MQ-7 (Ventana N = 10)
const int WINDOW_SIZE = 10;
float windowBuffer[WINDOW_SIZE];
int bufferIndex = 0;
float windowSum = 0;

float applyMovingAverage(float rawValue) {
  windowSum -= windowBuffer[bufferIndex];
  windowBuffer[bufferIndex] = rawValue;
  windowSum += rawValue;
  bufferIndex = (bufferIndex + 1) % WINDOW_SIZE;
  return windowSum / WINDOW_SIZE;
}

void setup() {
  Serial.begin(115200);
  
  // Inicialización del buffer del filtro
  for (int i = 0; i < WINDOW_SIZE; i++) {
    windowBuffer[i] = 0.0;
  }
  
  dht.begin();
  pinMode(MQ7PIN, INPUT);
}

void loop() {
  unsigned long currentMillis = millis();
  
  if (currentMillis - previousMillis >= interval) {
    previousMillis = currentMillis;

    // Lectura de variables analógicas y digitales
    float temp = dht.readTemperature();
    float hum = dht.readHumidity();
    float raw_mq7 = analogRead(MQ7PIN);
    float filtered_mq7 = applyMovingAverage(raw_mq7);

    // Construcción del Payload JSON estructurado
    StaticJsonDocument<384> doc;
    doc["node_id"] = "ESP32_FIRE_DETECTION";
    
    JsonObject data = doc.createNestedObject("data");
    data["temp"] = isnan(temp) ? 0.0 : round(temp * 10.0) / 10.0;
    data["hum"] = isnan(hum) ? 0.0 : round(hum * 10.0) / 10.0;
    data["mq7_raw"] = raw_mq7;
    data["mq7_filt"] = round(filtered_mq7 * 10.0) / 10.0;
    
    doc["heap_free"] = ESP.getFreeHeap();

    // Emisión del JSON por puerto serial
    serializeJson(doc, Serial);
    Serial.println();
  }
}
