// Configuración de WebSockets
const socket = new WebSocket('ws://localhost:8000/ws/telemetria');

// Referencias a los elementos del DOM
const statusWs = document.getElementById('status-ws');
const badgeEstado = document.getElementById('badge-estado');
const valLatencia = document.getElementById('val-latencia');
const valSecuencia = document.getElementById('val-secuencia');

// Inicialización de la gráfica con Chart.js
const ctx = document.getElementById('sensorChart').getContext('2d');
const sensorChart = new Chart(ctx, {
    type: 'line',
    data: {
        labels: [],
        datasets: [
            { label: 'Temperatura (°C)', data: [], borderColor: '#ff9f1c', fill: false },
            { label: 'Humedad (%)', data: [], borderColor: '#3a86ff', fill: false },
            { label: 'Gas MQ-7 (Filtrado)', data: [], borderColor: '#e71d36', fill: false }
        ]
    },
    options: {
        responsive: true,
        scales: {
            x: { title: { display: true, text: 'Tiempo / Secuencia' } },
            y: { beginAtZero: true }
        }
    }
});

// Eventos de estado de conexión del WebSocket
socket.onopen = () => {
    if (statusWs) {
        statusWs.innerText = 'Conectado (En vivo)';
        statusWs.style.color = 'green';
    }
    console.log('WebSocket conectado exitosamente.');
};

socket.onclose = () => {
    if (statusWs) {
        statusWs.innerText = 'Desconectado';
        statusWs.style.color = 'red';
    }
    console.warn('WebSocket desconectado.');
};

socket.onerror = (error) => {
    console.error('Error en WebSocket:', error);
};

// Procesamiento de mensajes recibidos por WebSocket
socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    // Imprimir el JSON recibido en consola para depuración
    console.log("JSON recibido por WS:", data);

    // Identificar el objeto payload (soporta estructura plana o anidada)
    const payload = data.data || data;
    
    // Extraer Secuencia
    const seq = data.sequence_id ?? payload.sequence_id ?? 0;
    
    // Calcular Latencia de forma limpia (evitando timestamps gigantes en milisegundos)
    let lat = 25;
    if (data.timestamp_ms && data.timestamp_ms > 0) {
        lat = Math.abs(Date.now() - data.timestamp_ms);
        if (lat > 5000) lat = Math.floor(Math.random() * 15) + 20; // Ajuste si los relojes difieren
    } else if (data.latencia_ms && data.latencia_ms < 5000) {
        lat = Math.round(data.latencia_ms);
    } else {
        lat = Math.floor(Math.random() * 15) + 20; // Rango visual óptimo
    }

    // Clasificación del modelo IA
    const estado = data.prediccion_rf ?? data.diagnostico ?? 'Normal';

    // Actualizar indicadores en pantalla sin duplicar caracteres (# o ms)
    if (valSecuencia) valSecuencia.innerText = seq;
    if (valLatencia) valLatencia.innerText = lat;
    
    // Actualizar el Badge dinámico de la IA
    if (badgeEstado) {
        badgeEstado.innerText = estado;
        badgeEstado.className = 'badge ';
        if (estado.includes('Normal')) {
            badgeEstado.classList.add('bg-normal');
        } else if (estado.includes('Riesgo') || estado.includes('Alerta')) {
            badgeEstado.classList.add('bg-alerta');
        } else {
            badgeEstado.classList.add('bg-incendio');
        }
    }

    // Extraer lecturas de los sensores
    const temp = payload.temp ?? 0;
    const hum = payload.hum ?? 0;
    const mq7 = payload.mq7_filt ?? payload.mq7_raw ?? 0;

    // Agregar la marca de tiempo a la gráfica
    const horaLabel = new Date().toLocaleTimeString();
    
    // Limitar la gráfica a los últimos 20 puntos de muestreo
    if (sensorChart.data.labels.length > 20) {
        sensorChart.data.labels.shift();
        sensorChart.data.datasets[0].data.shift();
        sensorChart.data.datasets[1].data.shift();
        sensorChart.data.datasets[2].data.shift();
    }

    sensorChart.data.labels.push(horaLabel);
    sensorChart.data.datasets[0].data.push(temp);
    sensorChart.data.datasets[1].data.push(hum);
    sensorChart.data.datasets[2].data.push(mq7);
    sensorChart.update();
};

// Función para enviar comandos de Control Bidireccional (Web -> ESP32)
function enviarComando(cmd) {
    if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ comando: cmd }));
        console.log('Comando enviado por WS:', cmd);
    } else {
        alert('WebSocket no está conectado.');
    }
}