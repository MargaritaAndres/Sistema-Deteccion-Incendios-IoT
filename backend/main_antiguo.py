import json
import time
import asyncio
import sqlite3
import joblib
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import paho.mqtt.client as mqtt

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
try:
    rf_model = joblib.load("random_forest_model.pkl")
    print("--> Modelo Random Forest cargado exitosamente desde .pkl")
except Exception as e:
    print(f"--> Aviso: No se encontró 'random_forest_model.pkl'. Usando clasificador basado en umbrales de prueba. ({e})")
    rf_model = None

def clasificar_estado(temp: float, hum: float, mq7_filt: float) -> str:
    """Aplica la inferencia del modelo Random Forest o regla heurística equivalente."""
    if rf_model is not None:
        try:
            # Entrada esperada por el modelo: [temp, hum, mq7_filt]
            input_vector = np.array([[temp, hum, mq7_filt]])
            prediction = rf_model.predict(input_vector)
            return str(prediction[0])
        except Exception as ex:
            print("Error durante la inferencia ML:", ex)
    
    # Lógica de respaldo si no hay modelo .pkl cargado
    if mq7_filt > 600 or temp > 45.0:
        return "Incendio Inminente"
    elif mq7_filt > 350 or temp > 35.0:
        return "Riesgo / Alerta"
    return "Operación Normal"

# 3. GESTIÓN DE WEBSOCKETS (CONEXIONES ACTIVAS)
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

# 4. CLIENTE MQTT (RECEPCIÓN Y CONTROL BIDIRECCIONAL)
MQTT_BROKER = "localhost" # O tu IP local
MQTT_TOPIC_TELEMETRIA = "sensores/incendios/telemetria"
MQTT_TOPIC_CONTROL = "dispositivos/incendios/control"

mqtt_client = mqtt.Client()

def on_connect(client, userdata, flags, rc):
    print(f"--> Conectado al Broker MQTT Mosquitto (Código {rc})")
    client.subscribe(MQTT_TOPIC_TELEMETRIA)

def on_message(client, userdata, msg):
    try:
        t_recepcion = int(time.time() * 1000) # Tiempo de llegada al backend en ms
        payload = json.loads(msg.payload.decode())
        
        sequence_id = payload.get("sequence_id", 0)
        timestamp_esp32 = payload.get("timestamp_ms", t_recepcion)
        data = payload.get("data", {})
        
        temp = float(data.get("temp", 0.0))
        hum = float(data.get("hum", 0.0))
        mq7_raw = float(data.get("mq7_raw", 0.0))
        mq7_filt = float(data.get("mq7_filt", 0.0))
        
        # A. Inferencia con Machine Learning
        estado_rf = clasificar_estado(temp, hum, mq7_filt)
        
        # B. Cálculo de Latencia End-to-End (L)
        latencia_ms = abs(t_recepcion - timestamp_esp32) if timestamp_esp32 > 0 else 0
        
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

# 5. ENDPOINTS HTTP Y WEBSOCKETS
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