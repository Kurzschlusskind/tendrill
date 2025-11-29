// Tendrill Dashboard
const API_BASE = 'http://127.0.0.1:8000/api/v1';
const WS_URL = 'ws://127.0.0.1:8000/ws';
const DEBUG = false;

// Debug logging
const log = (...args) => DEBUG && console.log(...args);
const warn = (...args) => console.warn(...args);

// State
let ws = null;
let currentPhase = 'vegetative_early';
let phaseTargets = {};
let lastUpdate = null;
let demoMode = false;
let demoInterval = null;

// Phase name mapping
const PHASE_NAMES = {
    'germination': 'Keimung',
    'seedling': 'Sämling',
    'vegetative_early': 'Veg (früh)',
    'vegetative_late': 'Veg (spät)',
    'transition': 'Übergang',
    'flowering_early': 'Blüte (früh)',
    'flowering_mid': 'Blüte (mitte)',
    'flowering_late': 'Blüte (spät)',
    'flush': 'Spülung',
    'drying': 'Trocknung',
    'curing': 'Aushärtung'
};

const PHASE_ORDER = [
    'germination', 'seedling', 'vegetative_early', 'vegetative_late',
    'transition', 'flowering_early', 'flowering_mid', 'flowering_late',
    'flush', 'drying', 'curing'
];

// Initialize
document.addEventListener('DOMContentLoaded', init);

async function init() {
    log('[Init] Dashboard startet...');

    // Render timeline first
    renderTimeline();

    // Update phase display
    updatePhaseDisplay(currentPhase, 7, 21);

    // Load phase data from API
    await loadPhases();

    // Load targets for current phase
    await loadPhaseTargets(currentPhase);

    // Start demo mode immediately for sensor values
    startDemoMode();

    // Connect WebSocket for live data (will override demo when data comes)
    connectWebSocket();

    // Check for stale data every 30s
    setInterval(checkDataFreshness, 30000);
}

// API calls
async function loadPhases() {
    try {
        log('[API] Lade Phasen...');
        const res = await fetch(`${API_BASE}/knowledge/phases`);
        if (res.ok) {
            phaseTargets = await res.json();
            log('[API] Phasen geladen:', Object.keys(phaseTargets).length);
        } else {
            warn('[API] Phasen Fehler:', res.status);
        }
    } catch (e) {
        warn('[API] Phasen konnten nicht geladen werden:', e.message);
    }
}

async function loadPhaseTargets(phase) {
    if (!phase) return;

    try {
        log('[API] Lade Zielwerte für:', phase);
        const res = await fetch(`${API_BASE}/knowledge/phases/${phase}`);
        if (res.ok) {
            const data = await res.json();
            log('[API] Zielwerte erhalten:', data);
            updateTargets(data);
            return;
        }
    } catch (e) {
        warn('[API] Zielwerte konnten nicht geladen werden, nutze Fallback:', e.message);
    }

    // Fallback: Simulierte Zielwerte pro Phase
    const PHASE_TARGETS = {
        'germination': {
            environment: { temperature_day_c: [20, 25], humidity_percent: [70, 90], vpd_kpa: [0.4, 0.8], co2_ppm: [400, 600], light_schedule: '0/24' },
            nutrients: { ph: [6.0, 6.5], ec_ms: [0.0, 0.0] }
        },
        'seedling': {
            environment: { temperature_day_c: [22, 26], humidity_percent: [65, 75], vpd_kpa: [0.5, 0.8], co2_ppm: [400, 600], light_schedule: '18/6' },
            nutrients: { ph: [5.8, 6.2], ec_ms: [0.4, 0.8] }
        },
        'vegetative_early': {
            environment: { temperature_day_c: [22, 28], humidity_percent: [55, 70], vpd_kpa: [0.8, 1.1], co2_ppm: [400, 800], light_schedule: '18/6' },
            nutrients: { ph: [5.8, 6.2], ec_ms: [0.8, 1.2] }
        },
        'vegetative_late': {
            environment: { temperature_day_c: [22, 28], humidity_percent: [50, 65], vpd_kpa: [0.9, 1.2], co2_ppm: [600, 1000], light_schedule: '18/6' },
            nutrients: { ph: [5.8, 6.2], ec_ms: [1.2, 1.6] }
        },
        'transition': {
            environment: { temperature_day_c: [20, 26], humidity_percent: [45, 55], vpd_kpa: [1.0, 1.3], co2_ppm: [600, 1000], light_schedule: '12/12' },
            nutrients: { ph: [6.0, 6.5], ec_ms: [1.4, 1.8] }
        },
        'flowering_early': {
            environment: { temperature_day_c: [20, 26], humidity_percent: [40, 50], vpd_kpa: [1.0, 1.4], co2_ppm: [800, 1200], light_schedule: '12/12' },
            nutrients: { ph: [6.0, 6.5], ec_ms: [1.6, 2.0] }
        },
        'flowering_mid': {
            environment: { temperature_day_c: [20, 26], humidity_percent: [40, 50], vpd_kpa: [1.0, 1.5], co2_ppm: [800, 1200], light_schedule: '12/12' },
            nutrients: { ph: [6.0, 6.5], ec_ms: [1.8, 2.2] }
        },
        'flowering_late': {
            environment: { temperature_day_c: [18, 24], humidity_percent: [35, 45], vpd_kpa: [1.2, 1.5], co2_ppm: [600, 1000], light_schedule: '12/12' },
            nutrients: { ph: [6.0, 6.5], ec_ms: [1.4, 1.8] }
        },
        'flush': {
            environment: { temperature_day_c: [18, 24], humidity_percent: [35, 45], vpd_kpa: [1.2, 1.5], co2_ppm: [400, 600], light_schedule: '12/12' },
            nutrients: { ph: [6.0, 6.5], ec_ms: [0.0, 0.2] }
        },
        'drying': {
            environment: { temperature_day_c: [18, 21], humidity_percent: [55, 65], vpd_kpa: [0.6, 0.9], co2_ppm: [400, 600], light_schedule: '0/24' },
            nutrients: { ph: [0, 0], ec_ms: [0, 0] }
        },
        'curing': {
            environment: { temperature_day_c: [18, 21], humidity_percent: [58, 65], vpd_kpa: [0.5, 0.8], co2_ppm: [400, 600], light_schedule: '0/24' },
            nutrients: { ph: [0, 0], ec_ms: [0, 0] }
        }
    };

    const fallback = PHASE_TARGETS[phase] || PHASE_TARGETS['vegetative_early'];
    log('[Fallback] Nutze simulierte Zielwerte für:', phase);
    updateTargets(fallback);
}

function checkDataFreshness() {
    if (!lastUpdate) return;

    const age = Date.now() - lastUpdate;
    if (age > 60000) { // Älter als 60 Sekunden
        setConnectionStatus(false, 'Keine Daten');
    }
}

// WebSocket
function connectWebSocket() {
    try {
        log('[WS] Verbinde zu', WS_URL);
        ws = new WebSocket(WS_URL);

        ws.onopen = () => {
            log('[WS] Verbunden');
            setConnectionStatus(true, 'Live');
            // Demo-Modus weiterlaufen lassen bis echte Daten kommen
        };

        ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            handleMessage(msg);
        };

        ws.onclose = () => {
            log('[WS] Verbindung getrennt');
            setConnectionStatus(false, 'Getrennt');
            startDemoMode();
            // Reconnect after 5s
            setTimeout(connectWebSocket, 5000);
        };

        ws.onerror = (e) => {
            warn('[WS] Fehler:', e);
            setConnectionStatus(false, 'Fehler');
            startDemoMode();
        };
    } catch (e) {
        warn('[WS] Konnte nicht verbinden:', e);
        setConnectionStatus(false, 'Offline');
        startDemoMode();
    }
}

// Demo Mode - simuliert Sensordaten wenn kein WebSocket
function startDemoMode() {
    if (demoMode) return;
    demoMode = true;
    log('[Demo] Demo-Modus aktiviert');
    setConnectionStatus(true, 'Demo');

    // Sensor-Basiswerte
    let temp = 24.5;
    let humidity = 62;
    let co2 = 580;

    // Sofort erste Werte setzen
    updateSensorValue('temperature', temp);
    updateSensorValue('humidity', humidity);
    updateSensorValue('co2', co2);
    updateSensorValue('vpd', 0.95);
    updateSensorValue('ph', 6.0);
    updateSensorValue('ec', 1.0);
    updateSensorValue('water_temperature', 19.5);
    lastUpdate = Date.now();

    demoInterval = setInterval(() => {
        // Kleine Schwankungen
        temp = temp * 0.95 + (25 + Math.random() * 2 - 1) * 0.05;
        humidity = humidity * 0.9 + (62 + Math.random() * 4 - 2) * 0.1;
        co2 = co2 * 0.95 + (600 + Math.random() * 60 - 30) * 0.05;

        // VPD berechnen
        const svp = 0.6108 * Math.exp((17.27 * temp) / (temp + 237.3));
        const avp = svp * (humidity / 100);
        const vpd = Math.max(0.1, svp - avp);

        // Werte updaten
        updateSensorValue('temperature', temp);
        updateSensorValue('humidity', humidity);
        updateSensorValue('vpd', vpd);
        updateSensorValue('co2', co2);
        updateSensorValue('ph', 6.0 + Math.random() * 0.1);
        updateSensorValue('ec', 1.0 + Math.random() * 0.1);
        updateSensorValue('water_temperature', 19.5 + Math.random() * 0.5);

        lastUpdate = Date.now();
    }, 2000);
}

function stopDemoMode() {
    if (demoInterval) {
        clearInterval(demoInterval);
        demoInterval = null;
    }
    demoMode = false;
}

function setConnectionStatus(connected, text) {
    const dot = document.getElementById('connection-status');
    const textEl = document.getElementById('connection-text');

    if (connected) {
        dot.className = 'dot connected';
    } else {
        dot.className = 'dot';
    }
    textEl.textContent = text || (connected ? 'Live' : 'Offline');
}

function handleMessage(msg) {
    log('[WS] Message:', msg.type);

    if (msg.type === 'reading') {
        lastUpdate = Date.now();
        setConnectionStatus(true, 'Live');
        updateSensorValue(msg.data.sensor_type, msg.data.value);
    } else if (msg.type === 'alert') {
        addAlert(msg.data);
    } else if (msg.type === 'phase_change') {
        currentPhase = msg.data.new_phase;
        loadPhaseTargets(currentPhase);
        renderTimeline();
    }
}

// Update UI
function updateTargets(data) {
    log('[UI] Update Targets:', data);
    const env = data.environment || {};
    const nut = data.nutrients || {};

    // Temperatur
    if (env.temperature_day_c && Array.isArray(env.temperature_day_c)) {
        document.getElementById('temp-target').textContent =
            `Ziel: ${env.temperature_day_c[0]}–${env.temperature_day_c[1]}°C`;
    }

    // Luftfeuchtigkeit
    if (env.humidity_percent && Array.isArray(env.humidity_percent)) {
        document.getElementById('humidity-target').textContent =
            `Ziel: ${env.humidity_percent[0]}–${env.humidity_percent[1]}%`;
    }

    // VPD
    if (env.vpd_kpa && Array.isArray(env.vpd_kpa)) {
        document.getElementById('vpd-target').textContent =
            `Ziel: ${env.vpd_kpa[0]}–${env.vpd_kpa[1]} kPa`;
    }

    // CO2
    if (env.co2_ppm && Array.isArray(env.co2_ppm)) {
        document.getElementById('co2-target').textContent =
            `Ziel: ${env.co2_ppm[0]}–${env.co2_ppm[1]} ppm`;
    }

    // pH
    if (nut.ph && Array.isArray(nut.ph)) {
        document.getElementById('ph-target').textContent =
            `Ziel: ${nut.ph[0]}–${nut.ph[1]}`;
    }

    // EC
    if (nut.ec_ms && Array.isArray(nut.ec_ms)) {
        document.getElementById('ec-target').textContent =
            `Ziel: ${nut.ec_ms[0]}–${nut.ec_ms[1]} mS/cm`;
    }

    // Licht
    if (env.light_schedule) {
        updateLightDisplay(env.light_schedule);
    }
}

// Licht-Anzeige mit Timeline
let lightSchedule = { onHours: 18, offHours: 6, startHour: 6 };

function updateLightDisplay(schedule) {
    const parts = schedule.split('/');
    lightSchedule.onHours = parseInt(parts[0]) || 18;
    lightSchedule.offHours = parseInt(parts[1]) || 6;
    lightSchedule.startHour = 6; // Licht geht um 6:00 an

    document.getElementById('light-schedule').textContent = schedule;

    // Light-On Periode berechnen
    const startPercent = (lightSchedule.startHour / 24) * 100;
    const widthPercent = (lightSchedule.onHours / 24) * 100;

    const onPeriod = document.getElementById('light-on-period');
    onPeriod.style.left = `${startPercent}%`;
    onPeriod.style.width = `${widthPercent}%`;

    // Zeiten anzeigen
    const endHour = (lightSchedule.startHour + lightSchedule.onHours) % 24;
    document.getElementById('light-on-time').textContent =
        `${String(lightSchedule.startHour).padStart(2, '0')}:00 – ${String(endHour).padStart(2, '0')}:00`;

    // Initiales Update
    updateLightMarker();

    // Jede Sekunde aktualisieren
    setInterval(updateLightMarker, 1000);
}

function updateLightMarker() {
    const now = new Date();
    const hours = now.getHours();
    const minutes = now.getMinutes();
    const seconds = now.getSeconds();

    // Aktuelle Zeit als Prozent des Tages
    const currentTimePercent = ((hours + minutes / 60 + seconds / 3600) / 24) * 100;

    // Marker positionieren
    const marker = document.getElementById('light-marker');
    marker.style.left = `${currentTimePercent}%`;

    // Aktuelle Uhrzeit anzeigen
    document.getElementById('light-time').textContent =
        `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;

    // Prüfen ob Licht an ist
    const endHour = lightSchedule.startHour + lightSchedule.onHours;
    let isLightOn;
    if (endHour <= 24) {
        isLightOn = hours >= lightSchedule.startHour && hours < endHour;
    } else {
        // Licht geht über Mitternacht
        isLightOn = hours >= lightSchedule.startHour || hours < (endHour % 24);
    }

    // Status aktualisieren
    const statusEl = document.getElementById('light-status');
    statusEl.textContent = isLightOn ? 'AN' : 'AUS';
    statusEl.className = 'light-status ' + (isLightOn ? 'on' : 'off');

    // Verbleibende Zeit berechnen
    let remaining;
    if (isLightOn) {
        // Zeit bis Licht aus
        let hoursUntilOff = (endHour % 24) - hours;
        if (hoursUntilOff <= 0) hoursUntilOff += 24;
        const minutesUntilOff = 60 - minutes;
        remaining = `Aus in ${hoursUntilOff}h ${minutesUntilOff}m`;
    } else {
        // Zeit bis Licht an
        let hoursUntilOn = lightSchedule.startHour - hours;
        if (hoursUntilOn <= 0) hoursUntilOn += 24;
        const minutesUntilOn = 60 - minutes;
        remaining = `An in ${hoursUntilOn}h ${minutesUntilOn}m`;
    }
    document.getElementById('light-remaining').textContent = remaining;
}

function updateSensorValue(type, value) {
    const mapping = {
        'temperature': 'temp-value',
        'humidity': 'humidity-value',
        'vpd': 'vpd-value',
        'co2': 'co2-value',
        'ph': 'ph-value',
        'ec': 'ec-value',
        'water_temperature': 'water-temp-value'
    };

    const elementId = mapping[type];
    if (elementId) {
        const el = document.getElementById(elementId);
        if (el) {
            if (typeof value === 'number') {
                el.textContent = value.toFixed(1);
            } else {
                el.textContent = value;
            }
        }
    }

    // Update status colors
    checkValueStatus(type, value);
}

function checkValueStatus(type, value) {
    // Simplified status check
    const cards = document.querySelectorAll('.env-card');
    const cardMapping = {
        'temperature': 0,
        'humidity': 1,
        'vpd': 2,
        'co2': 3
    };

    const idx = cardMapping[type];
    if (idx !== undefined && cards[idx]) {
        cards[idx].classList.remove('ok', 'warning', 'critical');
        // Could add actual range checking here
    }
}

function updatePhaseDisplay(phase, dayInPhase, totalDays) {
    document.getElementById('current-phase').textContent = PHASE_NAMES[phase] || phase;
    document.getElementById('phase-day').textContent = `Tag ${dayInPhase}`;

    const progress = Math.min((dayInPhase / totalDays) * 100, 100);
    document.getElementById('phase-progress').style.width = `${progress}%`;

    const remaining = Math.max(totalDays - dayInPhase, 0);
    document.getElementById('phase-remaining').textContent = `${remaining} Tage verbleibend`;

    currentPhase = phase;
    renderTimeline();
}

function renderTimeline() {
    const container = document.getElementById('phase-timeline');
    if (!container) return;

    container.innerHTML = '';

    const currentIdx = PHASE_ORDER.indexOf(currentPhase);

    PHASE_ORDER.forEach((phase, idx) => {
        const item = document.createElement('div');
        item.className = 'timeline-item';

        if (idx < currentIdx) {
            item.classList.add('completed');
        } else if (idx === currentIdx) {
            item.classList.add('current');
        }

        // Short name for timeline
        const shortNames = {
            'germination': 'Keim',
            'seedling': 'Säml',
            'vegetative_early': 'Veg I',
            'vegetative_late': 'Veg II',
            'transition': 'Trans',
            'flowering_early': 'Blü I',
            'flowering_mid': 'Blü II',
            'flowering_late': 'Blü III',
            'flush': 'Flush',
            'drying': 'Trock',
            'curing': 'Cure'
        };

        item.textContent = shortNames[phase] || phase;
        container.appendChild(item);
    });
}

function addAlert(alert) {
    const list = document.getElementById('alerts-list');
    const empty = list.querySelector('.alert-empty');
    if (empty) empty.remove();

    const item = document.createElement('div');
    item.className = `alert-item ${alert.severity || 'warning'}`;
    item.innerHTML = `
        <span class="alert-dot"></span>
        <span class="alert-message">${alert.message}</span>
        <span class="alert-time">jetzt</span>
    `;

    list.insertBefore(item, list.firstChild);

    // Keep max 5 alerts
    while (list.children.length > 5) {
        list.removeChild(list.lastChild);
    }
}

// ============================================
// TAB NAVIGATION
// ============================================

document.querySelectorAll('.tabs .tab').forEach(tab => {
    tab.addEventListener('click', () => {
        const targetTab = tab.dataset.tab;

        // Update active tab button
        document.querySelectorAll('.tabs .tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');

        // Show target content
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.remove('active');
        });
        document.getElementById(`tab-${targetTab}`).classList.add('active');

        // Load wiki content if needed
        if (targetTab === 'wiki') {
            loadWikiSection('overview');
        }
    });
});

// ============================================
// WIKI CONTENT
// ============================================

const WIKI_CONTENT = {
    overview: `
        <h1>Wachstumsphasen Übersicht</h1>
        <p>Der Lebenszyklus einer Pflanze durchläuft mehrere kritische Phasen, die jeweils spezifische Umweltbedingungen erfordern.</p>

        <h2>Die Phasen im Überblick</h2>
        <table class="param-table">
            <tr><th>Phase</th><th>Dauer</th><th>Licht</th><th>Temp.</th><th>Feuchtigkeit</th></tr>
            <tr><td>Keimung</td><td>3-7 Tage</td><td>0/24</td><td>20-25°C</td><td>70-90%</td></tr>
            <tr><td>Sämling</td><td>7-14 Tage</td><td>18/6</td><td>22-26°C</td><td>65-75%</td></tr>
            <tr><td>Vegetativ (früh)</td><td>14-21 Tage</td><td>18/6</td><td>22-28°C</td><td>55-70%</td></tr>
            <tr><td>Vegetativ (spät)</td><td>14-28 Tage</td><td>18/6</td><td>22-28°C</td><td>50-65%</td></tr>
            <tr><td>Übergang</td><td>7-14 Tage</td><td>12/12</td><td>20-26°C</td><td>45-55%</td></tr>
            <tr><td>Blüte (früh)</td><td>14-21 Tage</td><td>12/12</td><td>20-26°C</td><td>40-50%</td></tr>
            <tr><td>Blüte (mitte)</td><td>21-35 Tage</td><td>12/12</td><td>20-26°C</td><td>40-50%</td></tr>
            <tr><td>Blüte (spät)</td><td>14-21 Tage</td><td>12/12</td><td>18-24°C</td><td>35-45%</td></tr>
            <tr><td>Spülung</td><td>7-14 Tage</td><td>12/12</td><td>18-24°C</td><td>35-45%</td></tr>
            <tr><td>Trocknung</td><td>7-14 Tage</td><td>0/24</td><td>18-21°C</td><td>55-65%</td></tr>
            <tr><td>Aushärtung</td><td>14+ Tage</td><td>0/24</td><td>18-21°C</td><td>58-65%</td></tr>
        </table>

        <div class="info-box tip">
            <strong>Tipp:</strong> Die Übergänge zwischen den Phasen sollten graduell erfolgen, um Stress für die Pflanzen zu minimieren.
        </div>
    `,

    germination: `
        <h1>Keimung</h1>
        <p>Die Keimungsphase ist der Beginn des Lebenszyklus. In dieser Phase benötigt der Samen Feuchtigkeit, Wärme und Dunkelheit.</p>

        <h2>Optimale Bedingungen</h2>
        <table class="param-table">
            <tr><th>Parameter</th><th>Zielwert</th></tr>
            <tr><td>Temperatur</td><td>20-25°C</td></tr>
            <tr><td>Luftfeuchtigkeit</td><td>70-90%</td></tr>
            <tr><td>Licht</td><td>Dunkel (0/24)</td></tr>
            <tr><td>VPD</td><td>0.4-0.8 kPa</td></tr>
            <tr><td>pH</td><td>6.0-6.5</td></tr>
            <tr><td>EC</td><td>0.0 mS/cm (nur Wasser)</td></tr>
        </table>

        <h2>Methoden</h2>
        <ul>
            <li><strong>Papiertuch-Methode:</strong> Samen zwischen feuchten Papiertüchern, warm und dunkel lagern</li>
            <li><strong>Direkte Aussaat:</strong> Samen 1-2cm tief in feuchtes Medium setzen</li>
            <li><strong>Wasserglas:</strong> Samen 12-24h in Wasser einweichen, dann pflanzen</li>
        </ul>

        <div class="info-box warning">
            <strong>Achtung:</strong> Zu viel Feuchtigkeit kann zu Schimmelbildung führen. Das Medium sollte feucht, aber nicht nass sein.
        </div>

        <h2>Dauer</h2>
        <p>Die Keimung dauert typischerweise 3-7 Tage. Ein weißer Keimling (Radikula) erscheint zuerst, gefolgt von den Keimblättern.</p>
    `,

    seedling: `
        <h1>Sämling</h1>
        <p>Nach der Keimung entwickelt sich der Sämling. Die ersten echten Blätter erscheinen und die Pflanze beginnt Photosynthese.</p>

        <h2>Optimale Bedingungen</h2>
        <table class="param-table">
            <tr><th>Parameter</th><th>Zielwert</th></tr>
            <tr><td>Temperatur</td><td>22-26°C</td></tr>
            <tr><td>Luftfeuchtigkeit</td><td>65-75%</td></tr>
            <tr><td>Licht</td><td>18/6</td></tr>
            <tr><td>PPFD</td><td>100-300 µmol/m²/s</td></tr>
            <tr><td>VPD</td><td>0.5-0.8 kPa</td></tr>
            <tr><td>pH</td><td>5.8-6.2</td></tr>
            <tr><td>EC</td><td>0.4-0.8 mS/cm</td></tr>
        </table>

        <h2>Entwicklung</h2>
        <ul>
            <li>Keimblätter (rund) erscheinen zuerst</li>
            <li>Erste echte Blätter (gezackt) folgen nach 3-5 Tagen</li>
            <li>Wurzelsystem entwickelt sich aktiv</li>
        </ul>

        <div class="info-box tip">
            <strong>Tipp:</strong> Sämlinge sind empfindlich. Leichte Nährstofflösungen und sanftes Licht verwenden.
        </div>
    `,

    vegetative: `
        <h1>Vegetative Phase</h1>
        <p>Die vegetative Phase ist die Hauptwachstumsphase. Die Pflanze entwickelt Struktur, Blätter und ein starkes Wurzelsystem.</p>

        <h2>Frühe vegetative Phase</h2>
        <table class="param-table">
            <tr><th>Parameter</th><th>Zielwert</th></tr>
            <tr><td>Temperatur</td><td>22-28°C</td></tr>
            <tr><td>Luftfeuchtigkeit</td><td>55-70%</td></tr>
            <tr><td>Licht</td><td>18/6</td></tr>
            <tr><td>PPFD</td><td>300-600 µmol/m²/s</td></tr>
            <tr><td>VPD</td><td>0.8-1.1 kPa</td></tr>
            <tr><td>pH</td><td>5.8-6.2</td></tr>
            <tr><td>EC</td><td>0.8-1.2 mS/cm</td></tr>
            <tr><td>CO₂</td><td>400-800 ppm</td></tr>
        </table>

        <h2>Späte vegetative Phase</h2>
        <table class="param-table">
            <tr><th>Parameter</th><th>Zielwert</th></tr>
            <tr><td>Temperatur</td><td>22-28°C</td></tr>
            <tr><td>Luftfeuchtigkeit</td><td>50-65%</td></tr>
            <tr><td>VPD</td><td>0.9-1.2 kPa</td></tr>
            <tr><td>EC</td><td>1.2-1.6 mS/cm</td></tr>
            <tr><td>CO₂</td><td>600-1000 ppm</td></tr>
        </table>

        <h2>Training-Techniken</h2>
        <ul>
            <li><strong>Topping:</strong> Haupttrieb schneiden für buschigeres Wachstum</li>
            <li><strong>LST (Low Stress Training):</strong> Zweige sanft biegen und fixieren</li>
            <li><strong>Defoliation:</strong> Überschüssige Blätter entfernen für bessere Lichtdurchdringung</li>
        </ul>

        <div class="info-box tip">
            <strong>Tipp:</strong> Die vegetative Phase bestimmt die spätere Erntegröße. Eine gesunde, kräftige Pflanze produziert mehr Ertrag.
        </div>
    `,

    flowering: `
        <h1>Blütephase</h1>
        <p>Die Blütephase wird durch den 12/12 Lichtzyklus eingeleitet. Die Pflanze konzentriert ihre Energie auf die Blütenbildung.</p>

        <h2>Übergangsphase (Stretch)</h2>
        <p>In den ersten 2 Wochen nach der Umstellung verdoppelt oder verdreifacht die Pflanze oft ihre Höhe.</p>
        <table class="param-table">
            <tr><th>Parameter</th><th>Zielwert</th></tr>
            <tr><td>Temperatur</td><td>20-26°C</td></tr>
            <tr><td>Luftfeuchtigkeit</td><td>45-55%</td></tr>
            <tr><td>VPD</td><td>1.0-1.3 kPa</td></tr>
            <tr><td>EC</td><td>1.4-1.8 mS/cm</td></tr>
        </table>

        <h2>Frühe Blüte</h2>
        <p>Erste Blütenansätze erscheinen. Erhöhter Phosphor- und Kaliumbedarf.</p>
        <table class="param-table">
            <tr><th>Parameter</th><th>Zielwert</th></tr>
            <tr><td>Temperatur</td><td>20-26°C</td></tr>
            <tr><td>Luftfeuchtigkeit</td><td>40-50%</td></tr>
            <tr><td>PPFD</td><td>600-900 µmol/m²/s</td></tr>
            <tr><td>VPD</td><td>1.0-1.4 kPa</td></tr>
            <tr><td>EC</td><td>1.6-2.0 mS/cm</td></tr>
            <tr><td>CO₂</td><td>800-1200 ppm</td></tr>
        </table>

        <h2>Mittlere Blüte</h2>
        <p>Blüten entwickeln sich weiter und werden dichter. Peak der Nährstoffaufnahme.</p>

        <h2>Späte Blüte</h2>
        <p>Blüten reifen, Trichome entwickeln sich. Nährstoffe werden reduziert.</p>
        <table class="param-table">
            <tr><th>Parameter</th><th>Zielwert</th></tr>
            <tr><td>Temperatur</td><td>18-24°C</td></tr>
            <tr><td>Luftfeuchtigkeit</td><td>35-45%</td></tr>
            <tr><td>VPD</td><td>1.2-1.5 kPa</td></tr>
            <tr><td>EC</td><td>1.4-1.8 mS/cm</td></tr>
        </table>

        <div class="info-box warning">
            <strong>Achtung:</strong> Hohe Luftfeuchtigkeit in der Blüte kann zu Schimmel führen. Gute Luftzirkulation ist essentiell.
        </div>
    `,

    harvest: `
        <h1>Ernte & Trocknung</h1>

        <h2>Spülung (Flush)</h2>
        <p>7-14 Tage vor der Ernte nur noch reines Wasser geben, um Nährstoffreste auszuspülen.</p>
        <table class="param-table">
            <tr><th>Parameter</th><th>Zielwert</th></tr>
            <tr><td>pH</td><td>6.0-6.5</td></tr>
            <tr><td>EC</td><td>0.0-0.2 mS/cm</td></tr>
        </table>

        <h2>Erntezeitpunkt</h2>
        <ul>
            <li>Trichome zu 70-80% milchig, 20-30% bernsteinfarben</li>
            <li>Blütenstempel zu 70-90% braun/orange</li>
            <li>Blätter beginnen zu vergilben</li>
        </ul>

        <h2>Trocknung</h2>
        <table class="param-table">
            <tr><th>Parameter</th><th>Zielwert</th></tr>
            <tr><td>Temperatur</td><td>18-21°C</td></tr>
            <tr><td>Luftfeuchtigkeit</td><td>55-65%</td></tr>
            <tr><td>Licht</td><td>Dunkel</td></tr>
            <tr><td>Dauer</td><td>7-14 Tage</td></tr>
        </table>
        <p>Langsame Trocknung (10-14 Tage) ergibt bessere Qualität als schnelle Trocknung.</p>

        <h2>Aushärtung (Curing)</h2>
        <table class="param-table">
            <tr><th>Parameter</th><th>Zielwert</th></tr>
            <tr><td>Temperatur</td><td>18-21°C</td></tr>
            <tr><td>Luftfeuchtigkeit</td><td>58-65%</td></tr>
            <tr><td>Dauer</td><td>2-8 Wochen</td></tr>
        </table>
        <p>In luftdichten Gläsern lagern, täglich kurz öffnen ("Burpen") für Luftaustausch.</p>

        <div class="info-box tip">
            <strong>Tipp:</strong> Boveda-Packs (62% RH) können helfen, die optimale Feuchtigkeit während des Curings zu halten.
        </div>
    `,

    vpd: `
        <h1>VPD erklärt</h1>
        <p><strong>Vapor Pressure Deficit (VPD)</strong> beschreibt die Differenz zwischen dem Wasserdampfdruck in der Luft und dem maximal möglichen Wasserdampfdruck bei Sättigung.</p>

        <h2>Warum ist VPD wichtig?</h2>
        <p>VPD beeinflusst direkt die Transpirationsrate der Pflanze:</p>
        <ul>
            <li><strong>Niedriger VPD (&lt;0.4 kPa):</strong> Geringe Transpiration, Nährstoffaufnahme reduziert, Schimmelgefahr</li>
            <li><strong>Optimaler VPD (0.8-1.2 kPa):</strong> Gesunde Transpiration und Nährstofftransport</li>
            <li><strong>Hoher VPD (&gt;1.5 kPa):</strong> Stress, Stomata schließen, Wachstum verlangsamt</li>
        </ul>

        <h2>Optimale VPD-Werte</h2>
        <table class="param-table">
            <tr><th>Phase</th><th>VPD (kPa)</th></tr>
            <tr><td>Keimung</td><td>0.4-0.8</td></tr>
            <tr><td>Sämling</td><td>0.5-0.8</td></tr>
            <tr><td>Vegetativ</td><td>0.8-1.2</td></tr>
            <tr><td>Blüte (früh)</td><td>1.0-1.4</td></tr>
            <tr><td>Blüte (spät)</td><td>1.2-1.5</td></tr>
        </table>

        <h2>VPD-Berechnung</h2>
        <p>VPD = SVP × (1 - RH/100)</p>
        <p>Wobei SVP = 0.6108 × e^((17.27 × T) / (T + 237.3))</p>
        <ul>
            <li>T = Temperatur in °C</li>
            <li>RH = Relative Luftfeuchtigkeit in %</li>
        </ul>

        <div class="info-box tip">
            <strong>Tipp:</strong> Tendrill berechnet den VPD automatisch basierend auf Temperatur und Luftfeuchtigkeit.
        </div>
    `,

    'ec-ph': `
        <h1>EC & pH</h1>

        <h2>pH-Wert</h2>
        <p>Der pH-Wert bestimmt die Verfügbarkeit von Nährstoffen für die Pflanze.</p>

        <h3>Optimale pH-Bereiche</h3>
        <table class="param-table">
            <tr><th>Medium</th><th>pH-Bereich</th></tr>
            <tr><td>Hydroponik/Kokosfaser</td><td>5.5-6.5</td></tr>
            <tr><td>Erde</td><td>6.0-7.0</td></tr>
        </table>

        <h3>pH-Drift</h3>
        <ul>
            <li><strong>pH steigt:</strong> Pflanze nimmt mehr Anionen auf (NO₃⁻, PO₄³⁻)</li>
            <li><strong>pH sinkt:</strong> Pflanze nimmt mehr Kationen auf (K⁺, Ca²⁺, Mg²⁺)</li>
        </ul>

        <h2>EC (Electrical Conductivity)</h2>
        <p>EC misst die Gesamtkonzentration gelöster Salze (Nährstoffe) in der Lösung.</p>

        <h3>EC-Richtwerte</h3>
        <table class="param-table">
            <tr><th>Phase</th><th>EC (mS/cm)</th></tr>
            <tr><td>Sämling</td><td>0.4-0.8</td></tr>
            <tr><td>Vegetativ (früh)</td><td>0.8-1.2</td></tr>
            <tr><td>Vegetativ (spät)</td><td>1.2-1.6</td></tr>
            <tr><td>Blüte (früh)</td><td>1.6-2.0</td></tr>
            <tr><td>Blüte (mitte)</td><td>1.8-2.2</td></tr>
            <tr><td>Blüte (spät)</td><td>1.4-1.8</td></tr>
            <tr><td>Flush</td><td>0.0-0.2</td></tr>
        </table>

        <div class="info-box warning">
            <strong>Achtung:</strong> Zu hohe EC kann zu Nährstoffverbrennung führen (braune Blattspitzen).
        </div>
    `,

    light: `
        <h1>Licht & PPFD</h1>

        <h2>Lichtzyklus</h2>
        <table class="param-table">
            <tr><th>Phase</th><th>Zyklus</th><th>Erklärung</th></tr>
            <tr><td>Vegetativ</td><td>18/6</td><td>18h Licht, 6h Dunkel</td></tr>
            <tr><td>Blüte</td><td>12/12</td><td>12h Licht, 12h Dunkel (löst Blüte aus)</td></tr>
            <tr><td>Autoflower</td><td>18-24/0-6</td><td>Kann durchgehend beleuchtet werden</td></tr>
        </table>

        <h2>PPFD (Photosynthetic Photon Flux Density)</h2>
        <p>PPFD misst die Anzahl der Photonen im photosynthetisch aktiven Bereich (400-700nm), die pro Sekunde auf einen Quadratmeter treffen.</p>

        <h3>Optimale PPFD-Werte</h3>
        <table class="param-table">
            <tr><th>Phase</th><th>PPFD (µmol/m²/s)</th></tr>
            <tr><td>Sämling</td><td>100-300</td></tr>
            <tr><td>Vegetativ</td><td>300-600</td></tr>
            <tr><td>Blüte</td><td>600-900</td></tr>
            <tr><td>Blüte (mit CO₂)</td><td>900-1500</td></tr>
        </table>

        <h2>DLI (Daily Light Integral)</h2>
        <p>DLI = PPFD × Stunden × 0.0036</p>
        <p>Optimaler DLI für die Blütephase: 40-60 mol/m²/Tag</p>

        <h2>Lichtspektrum</h2>
        <ul>
            <li><strong>Blau (400-500nm):</strong> Kompaktes Wachstum, vegetative Phase</li>
            <li><strong>Rot (600-700nm):</strong> Streckung, Blütenentwicklung</li>
            <li><strong>Far-Red (700-780nm):</strong> Beeinflusst Stretch und Blüteninduktion</li>
        </ul>

        <div class="info-box tip">
            <strong>Tipp:</strong> Moderne Vollspektrum-LEDs liefern alle benötigten Wellenlängen und sind energieeffizienter als HPS/MH-Lampen.
        </div>
    `,

    intelligence: `
        <h1>KI & Automatisierung</h1>
        <p>Tendrill nutzt künstliche Intelligenz und maschinelles Lernen, um den Anbau zu optimieren und autonom zu steuern.</p>

        <h2>Kernfunktionen der KI</h2>

        <h3>1. Prädiktive Analyse</h3>
        <ul>
            <li><strong>Trendvorhersage:</strong> Erkennt Muster in Sensordaten und sagt Entwicklungen voraus</li>
            <li><strong>Anomalie-Erkennung:</strong> Identifiziert ungewöhnliche Abweichungen bevor sie kritisch werden</li>
            <li><strong>Wachstumsprognose:</strong> Schätzt optimale Erntezeitpunkte basierend auf historischen Daten</li>
        </ul>

        <h3>2. Autonome Regelung</h3>
        <table class="param-table">
            <tr><th>System</th><th>Steuerung</th><th>Optimierung</th></tr>
            <tr><td>Klimaanlage</td><td>PID + ML</td><td>Energieeffizienz, VPD-Optimierung</td></tr>
            <tr><td>Belüftung</td><td>Dynamisch</td><td>CO₂-Level, Luftaustausch</td></tr>
            <tr><td>Bewässerung</td><td>Bedarfsgesteuert</td><td>EC/pH-Anpassung, Wasserverbrauch</td></tr>
            <tr><td>Beleuchtung</td><td>Zeitgesteuert + PPFD</td><td>DLI-Optimierung, Spektrum</td></tr>
        </table>

        <h3>3. Lernende Optimierung</h3>
        <p>Das System lernt kontinuierlich aus:</p>
        <ul>
            <li><strong>Eigene Grows:</strong> Jeder Zyklus verbessert die Vorhersagemodelle</li>
            <li><strong>Umweltdaten:</strong> Korrelation zwischen Bedingungen und Pflanzenwachstum</li>
            <li><strong>Interventionen:</strong> Welche Anpassungen zu welchen Ergebnissen führen</li>
        </ul>

        <h2>VPD-Regelkreis</h2>
        <p>Tendrill optimiert automatisch Temperatur und Luftfeuchtigkeit für den idealen VPD:</p>
        <div class="info-box">
            <strong>Beispiel:</strong> Bei steigender Temperatur erhöht das System die Luftfeuchtigkeit, um den VPD im Zielbereich zu halten. Gleichzeitig wird die Lüftung angepasst, um Schimmelbildung zu verhindern.
        </div>

        <h2>Phasen-Erkennung</h2>
        <p>Die KI kann anhand von Wachstumsmustern automatisch erkennen, wann die Pflanze in eine neue Phase eintritt:</p>
        <ul>
            <li>Analyse der Wachstumsgeschwindigkeit</li>
            <li>Erkennung von Blütenansätzen (mit optionalem Kamera-Modul)</li>
            <li>Automatische Anpassung der Zielparameter</li>
        </ul>

        <h2>Energiemanagement</h2>
        <p>Intelligente Steuerung für minimalen Energieverbrauch:</p>
        <ul>
            <li><strong>Peak-Shaving:</strong> Vermeidung von Lastspitzen</li>
            <li><strong>Nacht-Modus:</strong> Nutzung günstiger Stromtarife</li>
            <li><strong>Wärmerückgewinnung:</strong> Koordination von Heizung und Kühlung</li>
        </ul>

        <div class="info-box tip">
            <strong>Tipp:</strong> Die KI-Funktionen verbessern sich mit der Zeit. Je mehr Daten gesammelt werden, desto präziser werden die Vorhersagen.
        </div>
    `,

    sensors: `
        <h1>Sensoren & Hardware</h1>
        <p>Tendrill unterstützt eine Vielzahl von Sensoren und Aktoren für die vollständige Kontrolle der Wachstumsumgebung.</p>

        <h2>Unterstützte Sensoren</h2>
        <table class="param-table">
            <tr><th>Sensor</th><th>Typ</th><th>Messbereich</th><th>Genauigkeit</th></tr>
            <tr><td>BME280</td><td>Temp/Humidity</td><td>-40 bis 85°C, 0-100%</td><td>±0.5°C, ±3%</td></tr>
            <tr><td>SHT31</td><td>Temp/Humidity</td><td>-40 bis 125°C, 0-100%</td><td>±0.2°C, ±2%</td></tr>
            <tr><td>SCD40/41</td><td>CO₂</td><td>400-5000 ppm</td><td>±50 ppm</td></tr>
            <tr><td>MH-Z19B</td><td>CO₂</td><td>0-5000 ppm</td><td>±50 ppm</td></tr>
            <tr><td>Atlas pH</td><td>pH</td><td>0-14 pH</td><td>±0.01 pH</td></tr>
            <tr><td>Atlas EC</td><td>EC</td><td>0.07-500 mS/cm</td><td>±2%</td></tr>
            <tr><td>DS18B20</td><td>Wassertemp</td><td>-55 bis 125°C</td><td>±0.5°C</td></tr>
        </table>

        <h2>ESP32 Integration</h2>
        <p>Die Sensorknoten basieren auf ESP32 Mikrocontrollern:</p>
        <ul>
            <li><strong>WiFi & MQTT:</strong> Drahtlose Kommunikation mit dem Backend</li>
            <li><strong>Deep Sleep:</strong> Energieeffizient für Batteriebetrieb</li>
            <li><strong>OTA Updates:</strong> Firmware-Updates über WiFi</li>
            <li><strong>Watchdog:</strong> Automatischer Neustart bei Problemen</li>
        </ul>

        <h2>Aktoren</h2>
        <table class="param-table">
            <tr><th>Aktor</th><th>Steuerung</th><th>Protokoll</th></tr>
            <tr><td>LED-Lampen</td><td>PWM / 0-10V</td><td>MQTT</td></tr>
            <tr><td>Lüfter</td><td>PWM / Relais</td><td>MQTT</td></tr>
            <tr><td>Luftbefeuchter</td><td>Relais</td><td>MQTT</td></tr>
            <tr><td>Heizung</td><td>Relais / PWM</td><td>MQTT</td></tr>
            <tr><td>Dosierpumpen</td><td>Peristaltik</td><td>MQTT</td></tr>
            <tr><td>Magnetventile</td><td>Relais</td><td>MQTT</td></tr>
        </table>

        <h2>Kommunikation</h2>
        <div class="info-box">
            <strong>MQTT-Topics:</strong>
            <ul>
                <li><code>tendrill/sensors/{device_id}/data</code> - Sensordaten</li>
                <li><code>tendrill/sensors/{device_id}/status</code> - Gerätestatus</li>
                <li><code>tendrill/actuators/{device_id}/command</code> - Steuerbefehle</li>
            </ul>
        </div>

        <h2>Kalibrierung</h2>
        <p>Für präzise Messungen müssen einige Sensoren regelmäßig kalibriert werden:</p>
        <ul>
            <li><strong>pH-Sensor:</strong> 2-Punkt-Kalibrierung mit pH 4.0 und 7.0 Lösungen</li>
            <li><strong>EC-Sensor:</strong> Kalibrierung mit Referenzlösung (z.B. 1.413 mS/cm)</li>
            <li><strong>CO₂-Sensor:</strong> Automatische Kalibrierung an Frischluft (400 ppm)</li>
        </ul>

        <div class="info-box warning">
            <strong>Achtung:</strong> pH- und EC-Sensoren regelmäßig in Aufbewahrungslösung lagern, um die Elektroden zu schonen.
        </div>
    `,

    alerts: `
        <h1>Alert-System</h1>
        <p>Tendrill überwacht kontinuierlich alle Parameter und warnt bei Abweichungen.</p>

        <h2>Alert-Stufen</h2>
        <table class="param-table">
            <tr><th>Stufe</th><th>Farbe</th><th>Bedeutung</th><th>Aktion</th></tr>
            <tr><td>Info</td><td>Blau</td><td>Informativ</td><td>Keine</td></tr>
            <tr><td>Warning</td><td>Gelb</td><td>Aufmerksamkeit erforderlich</td><td>Prüfen</td></tr>
            <tr><td>Critical</td><td>Rot</td><td>Sofortiges Handeln nötig</td><td>Eingreifen</td></tr>
        </table>

        <h2>Automatische Alerts</h2>
        <h3>Umwelt-Alerts</h3>
        <ul>
            <li><strong>Temperatur:</strong> Über/unter Zielbereich (±2°C Warning, ±5°C Critical)</li>
            <li><strong>Luftfeuchtigkeit:</strong> Zu hoch (Schimmelgefahr) oder zu niedrig (Stress)</li>
            <li><strong>VPD:</strong> Außerhalb des optimalen Bereichs für die aktuelle Phase</li>
            <li><strong>CO₂:</strong> Zu hoch (Sicherheit) oder zu niedrig (Wachstum)</li>
        </ul>

        <h3>Nährstoff-Alerts</h3>
        <ul>
            <li><strong>pH-Drift:</strong> Warnung wenn pH sich zu schnell ändert</li>
            <li><strong>EC-Spitzen:</strong> Plötzlicher Anstieg = mögliche Überdüngung</li>
            <li><strong>Wassertemperatur:</strong> Zu warm fördert Wurzelfäule</li>
        </ul>

        <h3>System-Alerts</h3>
        <ul>
            <li><strong>Sensor offline:</strong> Keine Daten seit X Minuten</li>
            <li><strong>Aktor-Fehler:</strong> Gerät reagiert nicht</li>
            <li><strong>Verbindungsverlust:</strong> MQTT/WiFi Probleme</li>
        </ul>

        <h2>Debouncing</h2>
        <p>Um Alert-Flut zu vermeiden:</p>
        <ul>
            <li>Alerts werden erst nach 60 Sekunden kontinuierlicher Abweichung ausgelöst</li>
            <li>Wiederholte Alerts frühestens nach 30 Minuten</li>
            <li>Automatische Auflösung wenn Wert wieder im Zielbereich</li>
        </ul>

        <h2>Benachrichtigungen</h2>
        <p>Alerts können über verschiedene Kanäle zugestellt werden:</p>
        <ul>
            <li><strong>Dashboard:</strong> Live-Anzeige im Browser</li>
            <li><strong>Push-Notifications:</strong> Browser/Mobile (geplant)</li>
            <li><strong>Telegram:</strong> Sofortige Nachricht (geplant)</li>
            <li><strong>E-Mail:</strong> Tägliche Zusammenfassung (geplant)</li>
        </ul>

        <div class="info-box tip">
            <strong>Tipp:</strong> Die Alert-Schwellwerte können pro Zone individuell angepasst werden.
        </div>
    `,

    architecture: `
        <h1>System-Architektur</h1>
        <p>Tendrill ist als modulares, skalierbares System aufgebaut.</p>

        <h2>Komponenten-Übersicht</h2>
        <div class="info-box">
            <pre style="font-family: monospace; font-size: 0.8rem; line-height: 1.4;">
┌─────────────────────────────────────────────────────────────┐
│                      Dashboard (Web UI)                      │
│                    JavaScript + WebSocket                    │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTP/WS
┌─────────────────────────▼───────────────────────────────────┐
│                    FastAPI Backend                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ REST API │  │WebSocket │  │  Alert   │  │Knowledge │    │
│  │          │  │ Manager  │  │ Engine   │  │  Base    │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
└─────────────────────────┬───────────────────────────────────┘
                          │ MQTT
┌─────────────────────────▼───────────────────────────────────┐
│                    MQTT Broker (Mosquitto)                   │
└─────────────────────────┬───────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   ESP32      │  │   ESP32      │  │   ESP32      │
│ Sensor Node  │  │ Sensor Node  │  │Actuator Node │
└──────────────┘  └──────────────┘  └──────────────┘
            </pre>
        </div>

        <h2>Backend-Stack</h2>
        <table class="param-table">
            <tr><th>Komponente</th><th>Technologie</th><th>Zweck</th></tr>
            <tr><td>Web Framework</td><td>FastAPI</td><td>REST API + WebSocket</td></tr>
            <tr><td>Datenbank</td><td>PostgreSQL</td><td>Persistente Speicherung</td></tr>
            <tr><td>Cache</td><td>Redis</td><td>Session, Pub/Sub</td></tr>
            <tr><td>MQTT Client</td><td>paho-mqtt</td><td>Sensor-Kommunikation</td></tr>
            <tr><td>ORM</td><td>SQLAlchemy</td><td>Datenbankzugriff</td></tr>
            <tr><td>Validation</td><td>Pydantic</td><td>Datenvalidierung</td></tr>
        </table>

        <h2>Datenfluss</h2>
        <ol>
            <li><strong>Sensor → MQTT:</strong> ESP32 sendet Messwerte an Broker</li>
            <li><strong>MQTT → Backend:</strong> Python-Client empfängt und validiert</li>
            <li><strong>Backend → DB:</strong> Werte werden in PostgreSQL gespeichert</li>
            <li><strong>Backend → WebSocket:</strong> Live-Updates an Dashboard</li>
            <li><strong>Backend → Alert Engine:</strong> Prüfung auf Grenzwerte</li>
        </ol>

        <h2>Zonen-Konzept</h2>
        <p>Tendrill unterstützt mehrere unabhängige Zonen:</p>
        <ul>
            <li>Jede Zone hat eigene Sensoren und Aktoren</li>
            <li>Unabhängige Phasen-Steuerung pro Zone</li>
            <li>Separate Alert-Konfiguration</li>
            <li>Ermöglicht unterschiedliche Grows parallel</li>
        </ul>

        <h2>Skalierbarkeit</h2>
        <ul>
            <li><strong>Horizontal:</strong> Mehrere ESP32-Nodes pro Zone</li>
            <li><strong>Vertikal:</strong> Mehrere Zonen pro Instanz</li>
            <li><strong>Multi-Site:</strong> Mehrere Standorte mit zentralem Dashboard (geplant)</li>
        </ul>

        <div class="info-box tip">
            <strong>Tipp:</strong> Die modulare Architektur ermöglicht es, mit wenigen Sensoren zu starten und das System nach Bedarf zu erweitern.
        </div>
    `
};

// Wiki Navigation
document.querySelectorAll('.wiki-link').forEach(link => {
    link.addEventListener('click', (e) => {
        e.preventDefault();
        const section = link.dataset.section;
        loadWikiSection(section);

        // Update active link
        document.querySelectorAll('.wiki-link').forEach(l => l.classList.remove('active'));
        link.classList.add('active');
    });
});

function loadWikiSection(section) {
    const content = WIKI_CONTENT[section];
    const container = document.getElementById('wiki-content');

    if (content) {
        container.innerHTML = content;
    } else {
        container.innerHTML = '<p>Inhalt wird geladen...</p>';
    }
}
