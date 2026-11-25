import pandas as pd
import numpy as np
import joblib
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

# 1. Cargar datos reales grabados
df_real = pd.read_csv("dataset_real_iot.csv")
df_real = df_real[(df_real["temp"] > 0) & (df_real["hum"] > 0)].copy()

print("=== DISTRIBUCIÓN DE MUESTRAS REALES BASE ===")
print(f"- normal      : {(df_real['etiqueta'] == 0).sum()} muestras")
print(f"- advertencia : {(df_real['etiqueta'] == 1).sum()} muestras")
print(f"- critico     : {(df_real['etiqueta'] == 2).sum()} muestras")
print(f"Total base: {len(df_real)} muestras\n")

# 2. Blindaje contra cambios de clima (Data Augmentation)
# Replicamos tus lecturas reales de gas en múltiples temperaturas (15°C - 38°C)
# y humedades (30% - 85%) para que el RF no dependa del microclima de grabación.
rng = np.random.default_rng(42)
dfs_aumentados = [df_real[["temp", "hum", "mq7_filt", "etiqueta"]]]

for _ in range(8):
    df_temp = df_real[["temp", "hum", "mq7_filt", "etiqueta"]].copy()
    df_temp["temp"] = rng.uniform(15.0, 38.0, size=len(df_temp)).round(1)
    df_temp["hum"] = rng.uniform(30.0, 85.0, size=len(df_temp)).round(1)
    # Pequeña variación natural de ±5 en el ADC del gas para evitar sobreajuste
    df_temp["mq7_filt"] = (df_temp["mq7_filt"] + rng.normal(0, 5.0, size=len(df_temp))).round(1)
    dfs_aumentados.append(df_temp)

# Caso físico adicional: calor extremo de incendio (> 43°C) -> Crítico aunque el gas aún sea bajo
n_calor = 120
df_calor = pd.DataFrame({
    "temp": rng.uniform(43.0, 65.0, size=n_calor).round(1),
    "hum": rng.uniform(15.0, 50.0, size=n_calor).round(1),
    "mq7_filt": rng.uniform(700.0, 1200.0, size=n_calor).round(1),
    "etiqueta": np.full(n_calor, 2)
})
dfs_aumentados.append(df_calor)

df_final = pd.concat(dfs_aumentados, ignore_index=True)

X = df_final[["temp", "hum", "mq7_filt"]]
y = df_final["etiqueta"]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.25, random_state=42, stratify=y
)

# 3. Entrenar Random Forest blindado
clf = RandomForestClassifier(
    n_estimators=120,
    max_depth=8,
    min_samples_leaf=3,
    random_state=42,
    n_jobs=-1
)
clf.fit(X_train, y_train)

# 4. Evaluar
y_pred_train = clf.predict(X_train)
y_pred_test = clf.predict(X_test)

print("=== RENDIMIENTO DEL MODELO BLINDADO ===")
print(f"Exactitud entrenamiento: {accuracy_score(y_train, y_pred_train) * 100:.2f} %")
print(f"Exactitud prueba:        {accuracy_score(y_test, y_pred_test) * 100:.2f} %\n")

print("=== IMPORTANCIA DE VARIABLES (El gas debe dominar) ===")
for nombre, imp in zip(["Temperatura (temp)", "Humedad (hum)", "Gas MQ-7 (mq7_filt)"], clf.feature_importances_):
    print(f"- {nombre:<23} : {imp * 100:5.1f} %")
print()

print("=== REPORTE POR CLASE (PRUEBA) ===")
print(classification_report(
    y_test, y_pred_test,
    target_names=["Normal (0)", "Advertencia (1)", "Crítico (2)"]
))

print("=== MATRIZ DE CONFUSIÓN ===")
print(confusion_matrix(y_test, y_pred_test))
print()

joblib.dump(clf, "modelo_rf_real.pkl")
print("--> Modelo blindado guardado exitosamente en 'modelo_rf_real.pkl'")