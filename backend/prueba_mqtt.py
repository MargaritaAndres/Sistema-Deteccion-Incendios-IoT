import json
import paho.mqtt.client as mqtt

c = mqtt.Client()
c.connect("localhost", 1883, 60)
c.loop_start()
msg = {"sequence_id": 1, "timestamp_ms": 0,
    "data": {"temp": 30, "hum": 50, "mq7_raw": 900, "mq7_filt": 900}}
info = c.publish("sensores/incendios/telemetria", json.dumps(msg))
info.wait_for_publish()
c.loop_stop()
print("Lectura de prueba enviada")