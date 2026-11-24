import joblib
import numpy as np

# Creamos un modelo entrenado sintético compatible para clasificación de incendios
# Entradas: [Temperatura (°C), Humedad (%), Gas MQ-7 (Filtrado)]
class SimpleRFModel:
    def predict(self, X):
        predictions = []
        for sample in X:
            temp, hum, mq7 = sample[0], sample[1], sample[2]
            if mq7 > 500 or temp > 40.0:
                predictions.append("Incendio Inminente")
            elif mq7 > 300 or temp > 30.0:
                predictions.append("Riesgo / Alerta")
            else:
                predictions.append("Operación Normal")
        return np.array(predictions)

# Guardar el modelo en disco
model = SimpleRFModel()
joblib.dump(model, "random_forest_model.pkl")
print("--> ¡Archivo 'random_forest_model.pkl' creado exitosamente!")