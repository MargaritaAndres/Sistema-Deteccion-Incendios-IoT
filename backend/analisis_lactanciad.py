import csv
import numpy as np

# Lee el CSV generado por el backend y calcula media, mediana y P95
with open("latencias_alerta.csv", encoding="utf-8") as f:
    filas = [r for r in csv.DictReader(f) if r["http_status"] == "200"]

print(f"Pruebas válidas: {len(filas)}\n")
for col in ["esp32_a_backend_ms", "backend_a_telegram_ms", "e2e_hasta_telegram_ms"]:
    v = np.array([float(r[col]) for r in filas])
    print(f"{col}:")
    print(f"  media   = {v.mean():.1f} ms")
    print(f"  mediana = {np.median(v):.1f} ms")
    print(f"  P95     = {np.percentile(v, 95):.1f} ms")
    print(f"  min/max = {v.min():.0f} / {v.max():.0f} ms\n")