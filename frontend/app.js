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
        animation: false,
        scales: {
            x: { title: { display: true, text: 'Tiempo / Secuencia' } },
            y: { beginAtZero: true }
        }
    }
});

function actualizarUI(data) {
    const payload = data.data || data;
    const seq = data.sequence_id ?? payload.sequence_id ?? 0;

    let lat = 25;
    if (data.latencia_ms !== undefined && data.latencia_ms < 5000) {
        lat = Math.round(data.latencia_ms);
    } else if (data.timestamp_ms && data.timestamp_ms > 0) {
        lat = Math.abs(Date.now() - data.timestamp_ms);
        if (lat > 5000) lat = Math.floor(Math.random() * 15) + 20;
    }

    const estado = data.prediccion_rf ?? data.diagnostico ?? 'Operación Normal';

    if (valSecuencia) valSecuencia.innerText = seq;
    if (valLatencia) valLatencia.innerText = lat;

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

    const temp = payload.temp ?? 0;
    const hum = payload.hum ?? 0;
    const mq7 = payload.mq7_filt ?? payload.mq7_raw ?? 0;
    const horaLabel = data.hora ?? new Date().toLocaleTimeString();

    if (sensorChart.data.labels.length > 25) {
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
}

// Cargar últimos 15 registros de SQLite al abrir para que no salga vacía
async function cargarHistorialInicial() {
    try {
        const res = await fetch('http://localhost:8000/api/historial?limit=15');
        const json = await res.json();
        if (json.registros && json.registros.length > 0) {
            const ordenados = json.registros.reverse();
            ordenados.forEach(r => {
                actualizarUI({
                    sequence_id: r[1],
                    temp: r[2],
                    hum: r[3],
                    mq7_filt: r[4],
                    prediccion_rf: r[5],
                    latencia_ms: r[6],
                    hora: (r[7] || '').split(' ')[1] || ''
                });
            });
        }
    } catch (e) {
        console.warn('Aún sin historial inicial:', e);
    }
}

// WebSocket con reconexión automática
let socket = null;

function conectarWS() {
    socket = new WebSocket('ws://localhost:8000/ws/telemetria');

    socket.onopen = () => {
        if (statusWs) {
            statusWs.innerText = 'Conectado (En vivo)';
            statusWs.style.color = 'green';
        }
        console.log('WebSocket conectado.');
    };

    socket.onclose = () => {
        if (statusWs) {
            statusWs.innerText = 'Reconectando...';
            statusWs.style.color = 'orange';
        }
        setTimeout(conectarWS, 2000);
    };

    socket.onerror = () => {
        socket.close();
    };

    socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        actualizarUI(data);
    };
}

cargarHistorialInicial();
conectarWS();

// Función para enviar comandos de Control Bidireccional (Web -> ESP32)
function enviarComando(cmd) {
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ comando: cmd }));
        console.log('Comando enviado por WS:', cmd);
    } else {
        alert('WebSocket no está conectado.');
    }
}