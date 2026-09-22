#include "DHT.h"

// Configuración de Pines
#define DHTPIN 4          // GPIO4 para sensor DHT22 (1-Wire)
#define DHTTYPE DHT22
#define MQ2PIN 34         // GPIO34 (ADC1) para sensor MQ-2

DHT dht(DHTPIN, DHTTYPE);

void setup() {
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("\nINICIALIZANDO NODO SENSOR - ESP32     ");
  
  dht.begin();
  pinMode(MQ2PIN, INPUT);
}

void loop() {
  // Lectura del sensor DHT22
  float temp = dht.readTemperature();
  float hum = dht.readHumidity();
  
  // Lectura del sensor MQ-2 (ADC)
  int mq2_raw = analogRead(MQ2PIN);
  
  // Validación de lecturas
  if (isnan(temp) || isnan(hum)) {
    Serial.println("[ERROR] Fallo al leer sensor DHT22. Verifique conexiones.");
  } else {
    Serial.println("---- LECTURA EN TIEMPO REAL ----");
    Serial.print("Temperatura: "); Serial.print(temp); Serial.println(" °C");
    Serial.print("Humedad:     "); Serial.print(hum); Serial.println(" %");
    Serial.print("MQ-2 (ADC):  "); Serial.print(mq2_raw); Serial.println(" (Lectura cruda)");
  }
  
  delay(2000);
}
