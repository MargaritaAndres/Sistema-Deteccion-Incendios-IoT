#include <time.h>
#include <sys/time.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include "DHT.h"


// Configuración de red Wi-Fi y Broker MQTT
const char* ssid =TU_WIFI_SSID";            // red Wi-Fi
const char* password = "TU_WIFI_PASSWORD";    // contraseña
const char* mqtt_server = "172.20.10.3"; // IP laptop

// Tópicos MQTT
const char* topic_telemetria = "sensores/incendios/telemetria";
const char* topic_control = "dispositivos/incendios/control";

// Configuración de Pines y Sensores
#define DHTPIN 4
#define DHTTYPE DHT11
#define MQ7PIN 34
#define LED_PIN 2  // Pin del LED integrado para prueba de control bidireccional

DHT dht(DHTPIN, DHTTYPE);
WiFiClient espClient;
PubSubClient client(espClient);

// Tiempos y Secuencia (NUEVO para P3)
unsigned long previousMillis = 0;
const long interval = 500; // Envío cada 2.5 segundos
unsigned long sequence_id = 0; // Contador de mensajes para Pérdida de Paquetes (P)

// Filtro Promedio Móvil (Ventana N = 10)
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

// Función Callback para Control Bidireccional (NUEVO para P3)
void callback(char* topic, byte* payload, unsigned int length) {
  String message = "";
  for (int i = 0; i < length; i++) {
    message += (char)payload[i];
  }
  
  Serial.print("Comando recibido por MQTT [");
  Serial.print(topic);
  Serial.print("]: ");
  Serial.println(message);

  // Ejecución física de la actuación
  if (message == "ON") {
    digitalWrite(LED_PIN, HIGH);
    Serial.println("Actuador encendido!");
  } else if (message == "OFF") {
    digitalWrite(LED_PIN, LOW);
    Serial.println("Actuador apagado!");
  }
}

void setup_wifi() {
  delay(10);
  Serial.print("Conectando a ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi Conectado!");
  Serial.print("IP asignada: ");
  Serial.println(WiFi.localIP());

  // Sincroniza el reloj con internet (hora real UTC), ya con Wi-Fi conectado
  configTime(0, 0, "pool.ntp.org", "time.google.com");
  Serial.print("Sincronizando hora NTP");
  while (time(nullptr) < 1700000000) {
    delay(500);
    Serial.print(".");
  }
  Serial.println(" OK");
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Intentando conexión MQTT...");
    if (client.connect("ESP32_FIRE_DETECTOR")) {
      Serial.println("¡Conectado al Broker MQTT!");
      // Suscribirse al tópico de comandos de control (NUEVO para P3)
      client.subscribe(topic_control);
      Serial.print("Suscrito a: ");
      Serial.println(topic_control);
    } else {
      Serial.print("Fallo, rc=");
      Serial.print(client.state());
      Serial.println(" Reintentando en 2 segundos...");
      delay(2000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  
  for (int i = 0; i < WINDOW_SIZE; i++) {
    windowBuffer[i] = 0.0;
  }

  dht.begin();
  pinMode(MQ7PIN, INPUT);
  pinMode(LED_PIN, OUTPUT); // Pin de actuador configurado
  digitalWrite(LED_PIN, LOW);
  
  setup_wifi();
  client.setServer(mqtt_server, 1883);
  client.setCallback(callback); // Escuchar mensajes MQTT (NUEVO para P3)
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop(); // Necesario para procesar mensajes entrantes (control bidireccional)

  unsigned long currentMillis = millis();
  if (currentMillis - previousMillis >= interval) {
    previousMillis = currentMillis;
    sequence_id++; // Incrementar ID de secuencia

    // Lectura de variables reales
    float temp = dht.readTemperature();
    float hum = dht.readHumidity();
    float raw_mq7 = analogRead(MQ7PIN);
    float filtered_mq7 = applyMovingAverage(raw_mq7);

    // Formateo del Payload JSON paraPráctica 3
    StaticJsonDocument<512> doc;

    doc["node_id"] = "ESP32_FIRE_DETECTION";
    doc["sequence_id"] = sequence_id;
    doc["timestamp_ms"] = currentMillis;

    struct timeval tv;
    gettimeofday(&tv, NULL);
    doc["epoch_s"] = (uint32_t)tv.tv_sec;
    doc["epoch_ms"] = (int)(tv.tv_usec / 1000);
    
    JsonObject data = doc.createNestedObject("data");
    data["temp"] = isnan(temp) ? 0.0 : round(temp * 10.0) / 10.0;
    data["hum"] = isnan(hum) ? 0.0 : round(hum * 10.0) / 10.0;
    data["mq7_raw"] = raw_mq7;
    data["mq7_filt"] = round(filtered_mq7 * 10.0) / 10.0;
    
    doc["heap_free"] = ESP.getFreeHeap();

    char buffer[512];
    serializeJson(doc, buffer);

    // Publicación en el tópico MQTT
    client.publish(topic_telemetria, buffer);
    Serial.print("Mensaje publicado vía MQTT [P3 #");
    Serial.print(sequence_id);
    Serial.print("]: ");
    Serial.println(buffer);
  }
}