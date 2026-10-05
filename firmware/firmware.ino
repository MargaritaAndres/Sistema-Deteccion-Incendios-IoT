#include "DHT.h"

// Configuración de Pines y Tipo de Sensor
#define DHTPIN 4       // Pin de datos en GPIO 4
#define DHTTYPE DHT11     // Sensor azul DHT11
#define MQ7PIN 34         // GPIO34 para MQ-7

DHT dht(DHTPIN, DHTTYPE);

void setup() {
  Serial.begin(115200);
  
  // Tiempo de estabilización de energía para los sensores
  delay(2000); 
  
  Serial.println("\n==========================================");
  Serial.println("   INICIALIZANDO NODO SENSOR (MQ-7 + DHT11)");
  Serial.println("==========================================");
  
  dht.begin();
  pinMode(MQ7PIN, INPUT);
  
  // Pausa tras inicializar la librería DHT
  delay(1000); 
}

void loop() {
  // El DHT11 necesita al menos 2 segundos entre lecturas
  delay(2500); 

  // Lectura de temperatura y humedad
  float temp = dht.readTemperature();
  float hum = dht.readHumidity();
  
  // Lectura del MQ-7
  int mq7_raw = analogRead(MQ7PIN);
  
  Serial.println("---- LECTURA EN TIEMPO REAL ----");
  
  if (isnan(temp) || isnan(hum)) {
    Serial.println("[DHT11] Reintentando comunicación en GPIO 4...");
  } else {
    Serial.print("Temperatura: "); Serial.print(temp, 1); Serial.println(" °C");
    Serial.print("Humedad:     "); Serial.print(hum, 1); Serial.println(" %");
  }
  
  Serial.print("MQ-7 (Monóxido): "); Serial.print(mq7_raw); Serial.println(" (Valor ADC)");
  Serial.println("--------------------------------\n");
}
