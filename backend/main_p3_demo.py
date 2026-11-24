import os
import csv
import json
import time
import asyncio
import sqlite3
import joblib
import httpx
import numpy as np
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import paho.mqtt.client as mqtt
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")

# Carga las credenciales desde el archivo .env (nunca van en el código)
load_dotenv()
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")
if not TG_TOKEN or not TG_CHAT_ID:
    print("--> Aviso: faltan TG_TOKEN o TG_CHAT_ID en el .env. No se enviarán alertas.")

app = FastAPI(title="Backend IoT Full-Stack con AI y Persistencia - Práctica 3")

# Permitir conexiones desde cualquier origen (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. BASE DE DATOS SQLITE (PERSISTENCIA MULTIVARIABLE)
DB_NAME = "telemetria_p3.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registros_telemetria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sequence_id INTEGER,
            timestamp_esp32 INTEGER,
            temp REAL,
            hum REAL,
            mq7_raw REAL,
            mq7_filt REAL,
            clase_predicha_rf TEXT,
            latencia_ms REAL,
            fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

# 2. CARGA DEL MODELO MACHINE LEARNING (RANDOM FOREST)
# El modelo se entrenó con las columnas [valor, latencia, delta_t_ms] y
# devuelve 0 = Normal, 1 = Advertencia, 2 = Crítico.
try:
    rf_model = joblib.load("modelo_random_forest_iot.pkl")
    print("--> Modelo Random Forest cargado exitosamente desde .pkl")
except Exception as e:
    print(f"--> Aviso: No se pudo cargar 'modelo_random_forest_iot.pkl'. Sin modelo NO se enviarán alertas. ({e})")
    rf_model = None

# Nombres iguales a los que ya usa el dashboard
NOMBRES_ESTADO = {0: "Operación Normal", 1: "Riesgo / Alerta", 2: "Incendio Inminente"}
ESTADO_CRITICO = 2

def clasificar_estado(temp, hum, mq7_filt, latencia_ms, delta_t_ms):
    """Devuelve (nombre_estado, codigo). El codigo es None si no hubo inferencia del modelo."""
    if rf_model is not None:
        try:
            # Mapeo: valor = mq7_filt (gas), latencia y delta_t_ms calculados en el backend
            X = np.array([[mq7_filt, latencia_ms, delta_t_ms]])
            codigo = int(rf_model.predict(X)[0])
            return NOMBRES_ESTADO.get(codigo, str(codigo)), codigo
        except Exception as ex:
            print("Error durante la inferencia ML:", ex)

    # Lógica de respaldo SOLO para mostrar algo en el dashboard (no dispara alertas)
    if mq7_filt > 600 or temp > 45.0:
        return "Incendio Inminente", None
    elif mq7_filt > 350 or temp > 35.0:
        return "Riesgo / Alerta", None
    return "Operación Normal", None

# 3. ALERTAS MÓVILES POR TELEGRAM (ASÍNCRONAS, CON COOLDOWN Y CSV DE LATENCIA)

COOLDOWN_SEG = int(os.getenv("COOLDOWN_SEG", "60"))# tiempo mínimo entre alertas
OFFSET_RELOJ_MS = int(os.getenv("OFFSET_RELOJ_MS", "0"))
ultima_alerta = 0.0                    # momento de la última alerta enviada
ultimo_arribo_ms = None                # para calcular delta_t_ms
CSV_LATENCIAS = "latencias_alerta.csv"

def registrar_csv(fila: dict):
    """Guarda cada alerta con sus tiempos para la tabla de latencia del artículo."""
    existe = os.path.exists(CSV_LATENCIAS)
    with open(CSV_LATENCIAS, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(fila.keys()))
        if not existe:
            w.writeheader()
        w.writerow(fila)

async def enviar_alerta(sequence_id, temp, hum, mq7_filt, latencia_ms, t_emision_ms, t_recepcion_ms):
    """Envía la alerta a Telegram sin bloquear el servidor (httpx asíncrono)."""
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    texto = (
        "<b>ALERTA CRÍTICA</b>\n"
        "Estado: Incendio Inminente (Random Forest)\n"
        f"Secuencia: #{sequence_id}\n"
        f"Gas MQ-7: {mq7_filt:.1f}\n"
        f"Temperatura: {temp:.1f} °C | Humedad: {hum:.1f} %\n"
        f"Latencia: {latencia_ms:.0f} ms\n"
        f"Hora: {time.strftime('%H:%M:%S')}"
    )
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                url,
                json={"chat_id": TG_CHAT_ID, "text": texto, "parse_mode": "HTML"},
            )
        t_api_ms = int(time.time() * 1000)
        print(f"--> Alerta enviada a Telegram (HTTP {r.status_code})")
        await asyncio.to_thread(registrar_csv, {
            "sequence_id": sequence_id,
            "t_emision_esp32_ms": t_emision_ms,
            "t_recepcion_backend_ms": t_recepcion_ms,
            "t_respuesta_telegram_ms": t_api_ms,

            "esp32_a_backend_ms":  t_recepcion_ms - t_emision_ms,
            "backend_a_telegram_ms": t_api_ms - t_recepcion_ms,
            "e2e_hasta_telegram_ms": t_api_ms - t_emision_ms,

            "http_status": r.status_code,
        })
    except Exception as e:
        print(f"--> Error enviando alerta a Telegram: {e}")

# 4. GESTIÓN DE WEBSOCKETS (CONEXIONES ACTIVAS)

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                pass

manager = ConnectionManager()
loop = asyncio.get_event_loop()

# 5. CLIENTE MQTT (RECEPCIÓN Y CONTROL BIDIRECCIONAL)
MQTT_BROKER = "localhost" # O tu IP local
MQTT_TOPIC_TELEMETRIA = "sensores/incendios/telemetria"
MQTT_TOPIC_CONTROL = "dispositivos/incendios/control"

mqtt_client = mqtt.Client()

def on_connect(client, userdata, flags, rc):
    print(f"--> Conectado al Broker MQTT Mosquitto (Código {rc})")
    client.subscribe(MQTT_TOPIC_TELEMETRIA)

def on_message(client, userdata, msg):
    global ultima_alerta, ultimo_arribo_ms
    try:
        t_recepcion = int(time.time() * 1000) # Tiempo de llegada al backend en ms
        payload = json.loads(msg.payload.decode())

        sequence_id = payload.get("sequence_id", 0)

        if "epoch_s" in payload:
            timestamp_esp32 = int(payload["epoch_s"]) * 1000 + int(payload.get("epoch_ms", 0))+OFFSET_RELOJ_MS
        else:
            timestamp_esp32 = payload.get("timestamp_ms", t_recepcion)
        data = payload.get("data", {})

        temp = float(data.get("temp", 0.0))
        hum = float(data.get("hum", 0.0))
        mq7_raw = float(data.get("mq7_raw", 0.0))
        mq7_filt = float(data.get("mq7_filt", 0.0))

        # Cálculo de Latencia End-to-End (L)
        latencia_ms = abs(t_recepcion - timestamp_esp32) if timestamp_esp32 > 0 else 0

        # Intervalo entre mensajes consecutivos (delta_t_ms)
        delta_t_ms = (t_recepcion - ultimo_arribo_ms) if ultimo_arribo_ms else 500.0
        ultimo_arribo_ms = t_recepcion

        # Mientras la ESP32 mande millis() (reloj sin sincronizar con la laptop),
        # la latencia calculada no es válida y no se le pasa al modelo.
        # Se corrige sincronizando la ESP32 con NTP.
        latencia_modelo = latencia_ms if latencia_ms < 5000 else 0.0

        # A. Inferencia con Machine Learning
        estado_rf, codigo = clasificar_estado(temp, hum, mq7_filt, latencia_modelo, delta_t_ms)

        # B. Alerta móvil: solo si el Random Forest predice Crítico y pasó el cooldown
        ahora = time.time()
        if codigo == ESTADO_CRITICO and (ahora - ultima_alerta) >= COOLDOWN_SEG:
            ultima_alerta = ahora
            asyncio.run_coroutine_threadsafe(
                enviar_alerta(sequence_id, temp, hum, mq7_filt, latencia_ms,
                            timestamp_esp32, t_recepcion),
                loop,
            )
        elif codigo == ESTADO_CRITICO:
            print(f"--> Crítico detectado, alerta en cooldown ({COOLDOWN_SEG - (ahora - ultima_alerta):.0f} s restantes)")

        # C. Persistencia en Base de Datos SQLite
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO registros_telemetria
            (sequence_id, timestamp_esp32, temp, hum, mq7_raw, mq7_filt, clase_predicha_rf, latencia_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (sequence_id, timestamp_esp32, temp, hum, mq7_raw, mq7_filt, estado_rf, latencia_ms))
        conn.commit()
        conn.close()

        # D. Preparar mensaje para retransmisión vía WebSocket
        ws_payload = {
            "sequence_id": sequence_id,
            "temp": temp,
            "hum": hum,
            "mq7_raw": mq7_raw,
            "mq7_filt": mq7_filt,
            "prediccion_rf": estado_rf,
            "latencia_ms": latencia_ms,
            "timestamp": t_recepcion
        }

        # Difundir por WebSocket
        asyncio.run_coroutine_threadsafe(
            manager.broadcast(json.dumps(ws_payload)), loop
        )

    except Exception as e:
        print(f"Error procesando mensaje MQTT: {e}")

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.connect(MQTT_BROKER, 1883, 60)
mqtt_client.loop_start()

# 6. ENDPOINTS HTTP Y WEBSOCKETS
@app.websocket("/ws/telemetria")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Escuchar mensajes desde el cliente Web (Control Bidireccional Web -> ESP32)
            data = await websocket.receive_text()
            # Si el cliente web envía {"comando": "ON"} o "OFF"
            try:
                comando_json = json.loads(data)
                comando = comando_json.get("comando", data)
            except:
                comando = data

            print(f"--> Acción recibida desde Dashboard Web: {comando}")
            # Publicar comando por MQTT hacia la ESP32
            mqtt_client.publish(MQTT_TOPIC_CONTROL, str(comando))

    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/api/historial")
def obtener_historial(limit: int = 50):
    """Endpoint HTTP para visualizar los últimos registros guardados en BD."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, sequence_id, temp, hum, mq7_filt, clase_predicha_rf, latencia_ms, fecha_registro
        FROM registros_telemetria ORDER BY id DESC LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return {"registros": rows}