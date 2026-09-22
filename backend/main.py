from fastapi import FastAPI

app = FastAPI(title="API Monitoreo de Incendios IoT")

@app.get("/")
def read_root():
    return {"status": "API activa", "modulo": "Ingesta de Telemetría"}

@app.post("/api/v1/telemetria")
def recibir_telemetria(data: dict):
    return {"status": "ok", "datos_recibidos": data}
