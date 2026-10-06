import json
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import paho.mqtt.client as mqtt

app = FastAPI(title="IoT Middleware - Sistema Detección de Incendios")

MQTT_BROKER = "localhost"
MQTT_TOPIC = "sensores/incendios/telemetria"

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
            await connection.send_text(message)

manager = ConnectionManager()
loop = None

def on_message(client, userdata, msg):
    payload = msg.payload.decode('utf-8')
    print(f"[MQTT Inbox - ESP32]: {payload}")
    if loop and loop.is_running():
        asyncio.run_coroutine_threadsafe(manager.broadcast(payload), loop)

mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
mqtt_client.on_message = on_message

@app.on_event("startup")
def startup_event():
    global loop
    loop = asyncio.get_event_loop()
    mqtt_client.connect(MQTT_BROKER, 1883, 60)
    mqtt_client.subscribe(MQTT_TOPIC)
    mqtt_client.loop_start()

@app.on_event("shutdown")
def shutdown_event():
    mqtt_client.loop_stop()
    mqtt_client.disconnect()

@app.websocket("/ws/telemetria")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
