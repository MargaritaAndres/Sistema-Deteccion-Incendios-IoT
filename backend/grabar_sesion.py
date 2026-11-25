import sys
import os
import csv
import json
import time
import paho.mqtt.client as mqtt

MQTT_BROKER = "localhost"
MQTT_TOPIC_TELEMETRIA = "sensores/incendios/telemetria"
CSV_DATASET = "dataset_real_iot.csv"

MAPA_CLASES = {
    "normal": 0,
    "advertencia": 1,
    "critico": 2,
}

if len(sys.argv) < 3 or sys.argv[1].lower() not in MAPA_CLASES:
    print("Uso: py grabar_sesion.py <normal|advertencia|critico> <segundos>")
    print("Ejemplo: py grabar_sesion.py normal 180")
    sys.exit(1)

etiqueta_str = sys.argv[1].lower()
etiqueta_num = MAPA_CLASES[etiqueta_str]
duracion_seg = int(sys.argv[2])

inicio_sesion = time.time()
fin_sesion = inicio_sesion + duracion_seg
muestras_guardadas = 0
descartadas_estabilizacion = 0
descartadas_dht = 0

existe_csv = os.path.exists(CSV_DATASET)
archivo_csv = open(CSV_DATASET, "a", newline="", encoding="utf-8")
writer = csv.DictWriter(
    archivo_csv,
    fieldnames=["timestamp", "temp", "hum", "mq7_raw", "mq7_filt", "etiqueta", "clase"],
)
if not existe_csv:
    writer.writeheader()


def on_connect(client, userdata, flags, rc):
    print(f"--> Conectado a Mosquitto. Grabando clase '{etiqueta_str.upper()}' ({etiqueta_num}) por {duracion_seg} s...")
    print("--> Los primeros 8 s se descartan para estabilizar el filtro.")
    client.subscribe(MQTT_TOPIC_TELEMETRIA)


def on_message(client, userdata, msg):
    global muestras_guardadas, descartadas_estabilizacion, descartadas_dht
    ahora = time.time()
    transcurrido = ahora - inicio_sesion

    if transcurrido < 8.0:
        descartadas_estabilizacion += 1
        return

    try:
        payload = json.loads(msg.payload.decode())
        data = payload.get("data", {})
        temp = float(data.get("temp", 0.0))
        hum = float(data.get("hum", 0.0))
        mq7_raw = float(data.get("mq7_raw", 0.0))
        mq7_filt = float(data.get("mq7_filt", 0.0))

        # Descartar lecturas inválidas del DHT11 (cuando marca 0)
        if temp == 0.0 or hum == 0.0:
            descartadas_dht += 1
            return

        writer.writerow({
            "timestamp": int(ahora * 1000),
            "temp": temp,
            "hum": hum,
            "mq7_raw": mq7_raw,
            "mq7_filt": mq7_filt,
            "etiqueta": etiqueta_num,
            "clase": etiqueta_str,
        })
        archivo_csv.flush()
        muestras_guardadas += 1
        restante = max(0, int(fin_sesion - ahora))
        print(
            f"[{restante:3d}s rest.] #{muestras_guardadas:3d} | "
            f"Gas(filt): {mq7_filt:6.1f} | Temp: {temp:4.1f}°C | Hum: {hum:4.1f}% -> {etiqueta_str}"
        )
    except Exception as e:
        print(f"Error leyendo trama: {e}")


client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect(MQTT_BROKER, 1883, 60)
client.loop_start()

try:
    while time.time() < fin_sesion:
        time.sleep(0.2)
except KeyboardInterrupt:
    print("\n--> Grabación interrumpida manualmente.")
finally:
    client.loop_stop()
    client.disconnect()
    archivo_csv.close()
    print("\n=== RESUMEN DE SESIÓN ===")
    print(f"Clase grabada: {etiqueta_str} ({etiqueta_num})")
    print(f"Muestras válidas guardadas: {muestras_guardadas}")
    print(f"Descartadas (primeros 8s): {descartadas_estabilizacion}")
    print(f"Descartadas (DHT11 en 0):  {descartadas_dht}")
    print(f"Guardado en: {CSV_DATASET}")