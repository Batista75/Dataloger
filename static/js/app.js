// Configuration
const CHANNEL_KEYS = ['a1', 'b1', 'c1', 'a2', 'b2', 'c2'];
const ENERGY_FIELDS = [
    'total_consumption_kwh',
    'total_production_kwh',
    ...CHANNEL_KEYS.flatMap((key) => [`${key}_consumption_kwh`, `${key}_production_kwh`]),
];
const CONFIG = {
    API_BASE: '',
    REFRESH_INTERVAL: 3000,
    CHART_HOURS: 24,
    CHART_REFRESH_INTERVAL: 30000,
    POWER_INTERVAL_SECONDS: 20,
    REALTIME_FILTER_ALPHA: 0.1,
    CHART_RESAMPLE_MINUTES: 5,
    CHART_AXIS_LABEL_MINUTES: 15,
    CHART_MOVING_AVERAGE_WINDOW: 3,
    HISTORY_LIMIT: 100,
    BUY_PRICE_KWH: 0.25,
    SELL_PRICE_KWH: 0.011,
    HAS_RESALE_CONTRACT: false,
    SENSORS: {},
    CHANNELS: {
        a1: { name: 'Canal A1', type: 'unused', graph: true },
        b1: { name: 'Canal B1', type: 'unused', graph: true },
        c1: { name: 'Canal C1', type: 'edf_total', graph: true },
        a2: { name: 'Canal A2', type: 'generator', graph: true },
        b2: { name: 'Canal B2', type: 'consumption', graph: true },
        c2: { name: 'Canal C2', type: 'consumption', graph: true },
    },
};

// State
let appState = {
    currentPage: 'dashboard',
    chartInstance: null,
    climateChartInstance: null,
    lastUpdate: null,
    historyPage: 0,
    selectedFromDate: null,
    selectedToDate: null,
    rawPowerSeries: [],
    powerSeries: [],
    latestPoint: null,
    lastPowerRefreshMs: 0,
    selectedGraphChannels: new Set(['total']),
    latestTemperature: null,
    latestTemperatureAgeSeconds: null,
    climateSeries: [],
    lastClimateRefreshMs: 0,
    knownSensors: new Set(),
};

// Initialize app
let appInitialized = false;

function startApp() {
    if (appInitialized) return;
    appInitialized = true;

    try {
        initializeNavigation();
        initializeDatepickers();
        initializeChartContainer();
        initializeExpandableChannels();
        loadSettings();
        updateAllData();

        setInterval(updateAllData, CONFIG.REFRESH_INTERVAL);
        setInterval(() => refreshPowerAnalytics(false), CONFIG.CHART_REFRESH_INTERVAL);
        setInterval(() => refreshClimateAnalytics(false), CONFIG.CHART_REFRESH_INTERVAL);
    } catch (error) {
        console.error('Bootstrap error:', error);
        const statusText = document.getElementById('status-text');
        const statusIndicator = document.getElementById('status-indicator');
        if (statusText) statusText.textContent = 'Erreur interface';
        if (statusIndicator) statusIndicator.classList.add('error');
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startApp);
} else {
    startApp();
}

/* ============ Utilities ============ */
function toNumber(value, fallback = 0) {
    const n = Number(value);
    return Number.isFinite(n) ? n : fallback;
}

function fmtW(value) {
    if (!Number.isFinite(value)) return '-- W';
    const rounded = Math.round(value);
    const normalized = Object.is(rounded, -0) ? 0 : rounded;
    return `${normalized.toLocaleString('fr-FR')} W`;
}

function fmtTrend(current, previous) {
    if (!Number.isFinite(current) || !Number.isFinite(previous) || previous <= 0) {
        return 'Tendance: --';
    }

    const ratio = current / previous;
    if (ratio >= 1.05) return 'Tendance: ↑ hausse';
    if (ratio <= 0.95) return 'Tendance: ↓ baisse';
    return 'Tendance: → stable';
}

function getChannelConfig(key) {
    const fallback = { name: `Canal ${key.toUpperCase()}`, type: 'consumption', graph: true };
    return { ...fallback, ...(CONFIG.CHANNELS[key] || {}) };
}

function getSensorKey(row) {
    if (!row || typeof row !== 'object') return '';
    return String(row.device_mac || row.device_id || '').trim();
}

function getSensorConfig(sensorKey) {
    const key = String(sensorKey || '').trim();
    const saved = (CONFIG.SENSORS && CONFIG.SENSORS[key]) || {};
    return {
        name: typeof saved.name === 'string' ? saved.name.trim() : '',
        type: saved.type === 'exterieur' ? 'exterieur' : 'interieur',
    };
}

function getSensorDisplayName(sensorKey) {
    const key = String(sensorKey || '').trim();
    const cfg = getSensorConfig(key);
    return cfg.name || key || 'Sonde inconnue';
}

function getSensorTypeLabel(sensorKey) {
    const cfg = getSensorConfig(sensorKey);
    return cfg.type === 'exterieur' ? 'exterieur' : 'interieur';
}

function getKnownSensorKeys() {
    const keys = new Set();

    Object.keys(CONFIG.SENSORS || {}).forEach((key) => {
        if (key) keys.add(key);
    });

    (appState.climateSeries || []).forEach((row) => {
        const key = getSensorKey(row);
        if (key) keys.add(key);
    });

    const latestKey = getSensorKey(appState.latestTemperature);
    if (latestKey) keys.add(latestKey);

    return Array.from(keys).sort();
}

function getUsedChannelKeys() {
    return CHANNEL_KEYS.filter((key) => getChannelConfig(key).type !== 'unused');
}

function clampPower(value) {
    if (!Number.isFinite(value) || value < 0) return 0;
    return Math.min(value, 2_000_000);
}

function deltaKwhToW(previous, current, deltaSeconds) {
    if (deltaSeconds <= 0) return NaN;
    const deltaKwh = toNumber(current) - toNumber(previous);
    if (!Number.isFinite(deltaKwh) || deltaKwh < 0) return 0;
    return clampPower((deltaKwh * 3600000) / deltaSeconds);
}

function buildUniformEnergySeries(rows, intervalSeconds) {
    if (!Array.isArray(rows) || rows.length === 0) return [];

    const bucketMs = Math.max(1, intervalSeconds) * 1000;
    const bucketRows = new Map();

    rows.forEach((row) => {
        const ts = parseTimestampMs(row.ts_utc);
        if (!Number.isFinite(ts)) return;

        const bucketTs = Math.floor(ts / bucketMs) * bucketMs;
        const current = bucketRows.get(bucketTs);
        if (!current || ts > current.__tsMs) {
            bucketRows.set(bucketTs, { ...row, __tsMs: ts });
        }
    });

    const bucketKeys = Array.from(bucketRows.keys()).sort((a, b) => a - b);
    if (bucketKeys.length === 0) return [];

    const minBucket = bucketKeys[0];
    const maxBucket = bucketKeys[bucketKeys.length - 1];
    const result = [];
    let lastKnown = null;

    for (let bucketTs = minBucket; bucketTs <= maxBucket; bucketTs += bucketMs) {
        if (bucketRows.has(bucketTs)) {
            lastKnown = bucketRows.get(bucketTs);
        }
        if (!lastKnown) continue;

        const point = { ts_utc: new Date(bucketTs).toISOString() };
        ENERGY_FIELDS.forEach((field) => {
            point[field] = toNumber(lastKnown[field], 0);
        });
        result.push(point);
    }

    return result;
}

function buildInstantPowerSeries(rows) {
    const series = [];
    const energySeries = buildUniformEnergySeries(rows, CONFIG.POWER_INTERVAL_SECONDS);
    if (energySeries.length < 2) return series;

    for (let i = 1; i < energySeries.length; i += 1) {
        const prev = energySeries[i - 1];
        const cur = energySeries[i];
        const prevTs = new Date(prev.ts_utc);
        const curTs = new Date(cur.ts_utc);
        const deltaSeconds = (curTs.getTime() - prevTs.getTime()) / 1000;
        if (!Number.isFinite(deltaSeconds) || deltaSeconds <= 0 || deltaSeconds > 900) {
            continue;
        }

        const point = {
            ts_utc: cur.ts_utc,
            total_consumption_w: deltaKwhToW(prev.total_consumption_kwh, cur.total_consumption_kwh, deltaSeconds),
            total_production_w: deltaKwhToW(prev.total_production_kwh, cur.total_production_kwh, deltaSeconds),
        };
        point.total_net_w = toNumber(point.total_consumption_w, 0) - toNumber(point.total_production_w, 0);

        CHANNEL_KEYS.forEach((key) => {
            const consumptionW = deltaKwhToW(prev[`${key}_consumption_kwh`], cur[`${key}_consumption_kwh`], deltaSeconds);
            const productionW = deltaKwhToW(prev[`${key}_production_kwh`], cur[`${key}_production_kwh`], deltaSeconds);

            point[`${key}_consumption_w`] = consumptionW;
            point[`${key}_production_w`] = productionW;

            const cfg = getChannelConfig(key);
            point[`${key}_signed_w`] = cfg.type === 'generator' ? -productionW : consumptionW;
        });

        series.push(point);
    }

    return series;
}

function applyExponentialFilter(series, alpha = 0.1) {
    if (!Array.isArray(series) || series.length === 0) return [];

    const a = Math.min(1, Math.max(0, Number(alpha)));
    if (a <= 0) return series.map((point) => ({ ...point }));

    const filtered = [];

    for (const point of series) {
        const previous = filtered.length > 0 ? filtered[filtered.length - 1] : null;
        const out = { ts_utc: point.ts_utc };

        Object.entries(point).forEach(([key, value]) => {
            if (key === 'ts_utc') return;

            const current = Number(value);
            const prev = previous ? Number(previous[key]) : NaN;

            if (!Number.isFinite(current)) {
                out[key] = Number.isFinite(prev) ? prev : null;
                return;
            }

            if (!Number.isFinite(prev)) {
                out[key] = current;
                return;
            }

            out[key] = a * current + (1 - a) * prev;
        });

        filtered.push(out);
    }

    return filtered;
}

function findClosestReferencePoint(series, latestTs, dayOffset) {
    if (!Array.isArray(series) || series.length === 0 || !(latestTs instanceof Date)) return null;

    const target = latestTs.getTime() - dayOffset * 24 * 3600 * 1000;
    let closest = null;
    let closestDist = Number.POSITIVE_INFINITY;

    for (const point of series) {
        const ts = new Date(point.ts_utc).getTime();
        const dist = Math.abs(ts - target);
        if (dist < closestDist) {
            closestDist = dist;
            closest = point;
        }
    }

    if (closestDist > 2 * 3600 * 1000) {
        return null;
    }
    return closest;
}

function getLineColor(key, type) {
    const palette = {
        total: { consumption: '#dc2626', production: '#16a34a' },
        a1: { consumption: '#e11d48', production: '#10b981' },
        b1: { consumption: '#f97316', production: '#22c55e' },
        c1: { consumption: '#ef4444', production: '#14b8a6' },
        a2: { consumption: '#f59e0b', production: '#0ea5e9' },
        b2: { consumption: '#d946ef', production: '#059669' },
        c2: { consumption: '#6366f1', production: '#84cc16' },
    };

    return (palette[key] && palette[key][type]) || '#334155';
}

function parseTimestampMs(value) {
    const ts = new Date(value).getTime();
    return Number.isFinite(ts) ? ts : NaN;
}

function formatChartTime(value) {
    const date = new Date(value);
    return date.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
}

function resamplePowerSeries(series, intervalMinutes, mode = 'average') {
    if (!Array.isArray(series) || series.length === 0) return [];

    const bucketMs = Math.max(1, intervalMinutes) * 60 * 1000;
    const buckets = new Map();
    let minBucket = Number.POSITIVE_INFINITY;
    let maxBucket = Number.NEGATIVE_INFINITY;

    for (const point of series) {
        const ts = parseTimestampMs(point.ts_utc);
        if (!Number.isFinite(ts)) continue;

        const bucketTs = Math.floor(ts / bucketMs) * bucketMs;
        minBucket = Math.min(minBucket, bucketTs);
        maxBucket = Math.max(maxBucket, bucketTs);

        if (!buckets.has(bucketTs)) {
            buckets.set(bucketTs, {
                ts_utc: new Date(bucketTs).toISOString(),
                __counts: {},
                __sums: {},
                __maxs: {},
            });
        }

        const bucket = buckets.get(bucketTs);
        Object.entries(point).forEach(([key, value]) => {
            if (key === 'ts_utc') return;
            const numeric = Number(value);
            if (!Number.isFinite(numeric)) return;

            bucket.__counts[key] = (bucket.__counts[key] || 0) + 1;
            bucket.__sums[key] = (bucket.__sums[key] || 0) + numeric;
            bucket.__maxs[key] = bucket.__maxs[key] === undefined ? numeric : Math.max(bucket.__maxs[key], numeric);
        });
    }

    if (!Number.isFinite(minBucket) || !Number.isFinite(maxBucket)) return [];

    const resampled = [];
    for (let bucketTs = minBucket; bucketTs <= maxBucket; bucketTs += bucketMs) {
        const bucket = buckets.get(bucketTs);
        const point = { ts_utc: new Date(bucketTs).toISOString() };

        if (bucket) {
            Object.keys(bucket.__counts).forEach((key) => {
                if (mode === 'max') {
                    point[key] = bucket.__maxs[key];
                    return;
                }

                const count = bucket.__counts[key] || 0;
                point[key] = count > 0 ? bucket.__sums[key] / count : null;
            });
        }

        resampled.push(point);
    }

    return resampled;
}

function applyMovingAverage(series, windowSize) {
    if (!Array.isArray(series) || series.length === 0) return [];
    if (!Number.isFinite(windowSize) || windowSize <= 1) return series.map((point) => ({ ...point }));

    const keys = new Set();
    series.forEach((point) => {
        Object.keys(point).forEach((key) => {
            if (key !== 'ts_utc') keys.add(key);
        });
    });

    return series.map((point, index) => {
        const start = Math.max(0, index - windowSize + 1);
        const smoothed = { ts_utc: point.ts_utc };

        keys.forEach((key) => {
            let sum = 0;
            let count = 0;

            for (let i = start; i <= index; i += 1) {
                const value = Number(series[i][key]);
                if (!Number.isFinite(value)) continue;
                sum += value;
                count += 1;
            }

            smoothed[key] = count > 0 ? sum / count : null;
        });

        return smoothed;
    });
}

function prepareChartSeries(series) {
    return Array.isArray(series) ? series : [];
}

function isQuarterHourLabel(value) {
    const date = new Date(value);
    return Number.isFinite(date.getTime()) && date.getMinutes() % CONFIG.CHART_AXIS_LABEL_MINUTES === 0;
}

function isHalfHourLabel(value) {
    const date = new Date(value);
    return Number.isFinite(date.getTime()) && date.getMinutes() % (CONFIG.CHART_AXIS_LABEL_MINUTES * 2) === 0;
}

function getBusinessTotals(point) {
    if (!point || typeof point !== 'object') {
        return {
            consumptionW: NaN,
            generatorAbsW: NaN,
            generatorSignedW: NaN,
        };
    }

    const activeKeys = CHANNEL_KEYS.filter((key) => getChannelConfig(key).type !== 'unused');
    const edfKeys = activeKeys.filter((key) => getChannelConfig(key).type === 'edf_total');
    const generatorKeys = activeKeys.filter((key) => getChannelConfig(key).type === 'generator');
    const consumptionKeys = activeKeys.filter((key) => {
        const type = getChannelConfig(key).type;
        return type === 'consumption' || type === 'edf_total';
    });

    const consumptionW = edfKeys.length > 0
        ? edfKeys.reduce((sum, key) => sum + toNumber(point[`${key}_consumption_w`], 0), 0)
        : consumptionKeys.reduce((sum, key) => sum + toNumber(point[`${key}_consumption_w`], 0), 0);

    const generatorAbsW = generatorKeys.reduce((sum, key) => sum + toNumber(point[`${key}_production_w`], 0), 0);

    return {
        consumptionW,
        generatorAbsW,
        generatorSignedW: Number.isFinite(generatorAbsW) ? -generatorAbsW : NaN,
    };
}

/* ============ Navigation ============ */
function initializeNavigation() {
    document.querySelectorAll('.nav-tab').forEach((tab) => {
        tab.addEventListener('click', () => {
            const page = tab.dataset.page;
            switchPage(page);
        });
    });
}

function switchPage(page) {
    document.querySelectorAll('.page').forEach((p) => p.classList.remove('active'));
    document.querySelectorAll('.nav-tab').forEach((tab) => tab.classList.remove('active'));

    document.getElementById(page).classList.add('active');
    document.querySelector(`[data-page="${page}"]`).classList.add('active');

    appState.currentPage = page;

    if (page === 'history') {
        loadHistory();
    }
    if (page === 'dashboard') {
        refreshPowerAnalytics(true);
        refreshClimateAnalytics(true);
    }
}

/* ============ Data Loading ============ */
async function updateAllData() {
    try {
        const [statusRes, latestRes, tempRes] = await Promise.all([
            fetch(`${CONFIG.API_BASE}/api/status`),
            fetch(`${CONFIG.API_BASE}/api/measurements/latest`),
            fetch(`${CONFIG.API_BASE}/api/temperature/latest`),
        ]);

        const status = statusRes.ok ? await statusRes.json() : null;
        const latest = latestRes.ok ? await latestRes.json() : null;
        const temperature = tempRes.ok ? await tempRes.json() : null;

        appState.latestTemperature = temperature && temperature.data ? temperature.data : null;
        appState.latestTemperatureAgeSeconds = temperature && Number.isFinite(Number(temperature.data_age_seconds))
            ? Number(temperature.data_age_seconds)
            : null;

        updateStatus(status, latest);
        updateTemperatureCard();

        if (status) {
            updateSystemInfo(status);
        }

        if (latest && latest.data) {
            updateDashboard(latest.data, status || {});
        }

        await refreshPowerAnalytics(false);
        await refreshClimateAnalytics(false);
        updateFooter();
    } catch (error) {
        console.error('Error fetching data:', error);
        updateStatus(null, null);
    }
}

function formatAge(ageSeconds) {
    if (!Number.isFinite(ageSeconds) || ageSeconds < 0) return '--';
    if (ageSeconds < 60) return `${Math.round(ageSeconds)} s`;
    if (ageSeconds < 3600) return `${Math.round(ageSeconds / 60)} min`;
    return `${(ageSeconds / 3600).toFixed(1)} h`;
}

function updateTemperatureCard() {
    const valueNode = document.getElementById('temperature-value');
    const humidityNode = document.getElementById('humidity-value');
    const sensorsNode = document.getElementById('temperature-sensors-count');
    const macNode = document.getElementById('temperature-mac');
    const ageNode = document.getElementById('temperature-age');
    if (!valueNode || !humidityNode || !sensorsNode || !macNode || !ageNode) return;

    const activeSensors = new Set(getKnownSensorKeys());
    sensorsNode.textContent = activeSensors.size > 0 ? String(activeSensors.size) : '--';

    const payload = appState.latestTemperature;
    if (!payload) {
        valueNode.textContent = '-- deg C';
        humidityNode.textContent = '-- %';
        macNode.textContent = '--';
        ageNode.textContent = '--';
        return;
    }

    const temp = Number(payload.temperature_c);
    const humidity = Number(payload.humidity_pct);
    const sensorKey = getSensorKey(payload);
    const sensorName = getSensorDisplayName(sensorKey);
    const sensorType = getSensorTypeLabel(sensorKey);
    valueNode.textContent = Number.isFinite(temp) ? `${temp.toFixed(1)} deg C` : '-- deg C';
    humidityNode.textContent = Number.isFinite(humidity) ? `${humidity.toFixed(1)} %` : '-- %';
    macNode.textContent = sensorKey ? `${sensorName} (${sensorType})` : '--';
    ageNode.textContent = formatAge(appState.latestTemperatureAgeSeconds);
}

async function refreshPowerAnalytics(force) {
    const now = Date.now();
    if (!force && now - appState.lastPowerRefreshMs < CONFIG.CHART_REFRESH_INTERVAL - 2000) {
        return;
    }

    try {
        const minutes = Math.max(CONFIG.CHART_HOURS, 50) * 60;
        const response = await fetch(`${CONFIG.API_BASE}/api/measurements?minutes=${minutes}&limit=10000`);
        if (!response.ok) throw new Error('Failed to load power analytics');

        const payload = await response.json();
        const rawSeries = buildInstantPowerSeries(payload.data || []);
        const filteredSeries = applyExponentialFilter(rawSeries, CONFIG.REALTIME_FILTER_ALPHA);

        appState.rawPowerSeries = rawSeries;
        appState.powerSeries = filteredSeries;
        appState.latestPoint = filteredSeries.length ? filteredSeries[filteredSeries.length - 1] : null;
        appState.lastPowerRefreshMs = now;

        updateInstantSummary();
        updateChannelInstantCards();
        renderTrendChart();
    } catch (error) {
        console.error('Error loading instant analytics:', error);
    }
}

function renderTrendChart() {
    const series = appState.powerSeries;
    if (!Array.isArray(series) || series.length === 0) return;

    const cutoff = Date.now() - CONFIG.CHART_HOURS * 3600 * 1000;
    const windowed = series.filter((p) => parseTimestampMs(p.ts_utc) >= cutoff);
    if (windowed.length === 0) return;

    const chartSeries = prepareChartSeries(windowed);
    if (chartSeries.length === 0) return;

    const labels = chartSeries.map((p) => formatChartTime(p.ts_utc));

    const selected = Array.from(appState.selectedGraphChannels);
    const datasets = [];

    const appendChannelDataset = (key, label, cfg) => {
        const isGenerator = cfg && cfg.type === 'generator';
        datasets.push({
            label: `${label} (W)`,
            data: chartSeries.map((p) => {
                const value = Number(p[`${key}_signed_w`]);
                return Number.isFinite(value) ? value : null;
            }),
            borderColor: getLineColor(key, isGenerator ? 'production' : 'consumption'),
            backgroundColor: 'transparent',
            borderWidth: 2,
            borderDash: isGenerator ? [8, 4] : [],
            tension: 0.25,
            fill: false,
        });
    };

    selected.forEach((key) => {
        if (key === 'total') {
            datasets.push({
                label: 'Total consommation (W)',
                data: chartSeries.map((p) => {
                    const totals = getBusinessTotals(p);
                    return Number.isFinite(totals.consumptionW) ? totals.consumptionW : null;
                }),
                borderColor: getLineColor('total', 'consumption'),
                borderWidth: 2.5,
                tension: 0.25,
                fill: false,
            });
            return;
        }

        const cfg = getChannelConfig(key);
        if (cfg.type === 'unused') return;
        appendChannelDataset(key, cfg.name, cfg);
    });

    const ctx = document.getElementById('trend-chart').getContext('2d');

    if (appState.chartInstance) {
        appState.chartInstance.destroy();
    }

    appState.chartInstance = new Chart(ctx, {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { position: 'top' },
            },
            scales: {
                x: {
                    ticks: {
                        autoSkip: false,
                        maxRotation: 0,
                        minRotation: 0,
                        callback(value, index) {
                            const label = labels[index];
                            return isHalfHourLabel(chartSeries[index].ts_utc) ? label : '';
                        },
                    },
                    grid: {
                        color(context) {
                            return isQuarterHourLabel(chartSeries[context.index].ts_utc)
                                ? 'rgba(148, 163, 184, 0.35)'
                                : 'rgba(148, 163, 184, 0.08)';
                        },
                    },
                },
                y: {
                    beginAtZero: false,
                    title: {
                        display: true,
                        text: 'Puissance signee (W)',
                    },
                },
            },
        },
    });
}

async function refreshClimateAnalytics(force) {
    const now = Date.now();
    if (!force && now - appState.lastClimateRefreshMs < CONFIG.CHART_REFRESH_INTERVAL - 2000) {
        return;
    }

    try {
        const minutes = Math.max(CONFIG.CHART_HOURS, 1) * 60;
        const response = await fetch(`${CONFIG.API_BASE}/api/temperature/history?minutes=${minutes}&limit=10000`);
        if (!response.ok) throw new Error('Failed to load climate analytics');

        const payload = await response.json();
        const rows = Array.isArray(payload.data) ? payload.data : [];
        appState.climateSeries = rows
            .filter((row) => Number.isFinite(parseTimestampMs(row.ts_utc)))
            .sort((a, b) => parseTimestampMs(a.ts_utc) - parseTimestampMs(b.ts_utc));
        appState.knownSensors = new Set(getKnownSensorKeys());
        appState.lastClimateRefreshMs = now;

        renderClimateChart();
        renderSensorSettingsRows();
        updateTemperatureCard();
    } catch (error) {
        console.error('Error loading climate analytics:', error);
    }
}

function renderSensorSettingsRows() {
    const grid = document.getElementById('sensor-settings-grid');
    if (!grid) return;

    const sensorKeys = getKnownSensorKeys();
    if (sensorKeys.length === 0) {
        grid.innerHTML = '<div class="sensor-setting-empty">Aucune sonde detectee pour le moment.</div>';
        return;
    }

    grid.innerHTML = '';
    sensorKeys.forEach((sensorKey) => {
        const cfg = getSensorConfig(sensorKey);
        const row = document.createElement('div');
        row.className = 'sensor-setting-row';

        const keyNode = document.createElement('div');
        keyNode.className = 'sensor-setting-key';
        keyNode.textContent = sensorKey;

        const nameInput = document.createElement('input');
        nameInput.type = 'text';
        nameInput.className = 'sensor-name-input';
        nameInput.dataset.sensorKey = sensorKey;
        nameInput.placeholder = 'Nom de la sonde';
        nameInput.value = cfg.name;

        const typeSelect = document.createElement('select');
        typeSelect.className = 'sensor-type-select';
        typeSelect.dataset.sensorKey = sensorKey;
        typeSelect.innerHTML = [
            '<option value="interieur">Sonde interieur</option>',
            '<option value="exterieur">Sonde exterieur</option>',
        ].join('');
        typeSelect.value = cfg.type;

        row.appendChild(keyNode);
        row.appendChild(nameInput);
        row.appendChild(typeSelect);
        grid.appendChild(row);
    });
}

function renderClimateChart() {
    const canvas = document.getElementById('climate-chart');
    if (!canvas) return;

    const series = Array.isArray(appState.climateSeries) ? appState.climateSeries : [];
    const cutoff = Date.now() - CONFIG.CHART_HOURS * 3600 * 1000;
    const windowed = series.filter((p) => parseTimestampMs(p.ts_utc) >= cutoff);

    if (windowed.length === 0) {
        if (appState.climateChartInstance) {
            appState.climateChartInstance.destroy();
            appState.climateChartInstance = null;
        }
        return;
    }

    const timeKeys = Array.from(new Set(windowed.map((p) => p.ts_utc))).sort((a, b) => parseTimestampMs(a) - parseTimestampMs(b));
    const labels = timeKeys.map((ts) => formatChartTime(ts));

    const bySensor = new Map();
    windowed.forEach((row) => {
        const sensorKey = String(row.device_mac || row.device_id || 'unknown');
        if (!bySensor.has(sensorKey)) bySensor.set(sensorKey, new Map());
        bySensor.get(sensorKey).set(row.ts_utc, row);
    });

    const palette = ['#dc2626', '#f97316', '#0ea5e9', '#16a34a', '#a855f7', '#e11d48'];
    const sensorKeys = Array.from(bySensor.keys()).sort();
    const datasets = [];

    sensorKeys.forEach((sensorKey, index) => {
        const color = palette[index % palette.length];
        const sensorName = getSensorDisplayName(sensorKey);
        const sensorType = getSensorTypeLabel(sensorKey);
        const rowMap = bySensor.get(sensorKey);
        const tempData = timeKeys.map((ts) => {
            const value = Number(rowMap.get(ts)?.temperature_c);
            return Number.isFinite(value) ? value : null;
        });
        const humData = timeKeys.map((ts) => {
            const value = Number(rowMap.get(ts)?.humidity_pct);
            return Number.isFinite(value) ? value : null;
        });

        if (tempData.some((value) => Number.isFinite(value))) {
            datasets.push({
                label: `${sensorName} (${sensorType}) - Temp (deg C)`,
                data: tempData,
                borderColor: color,
                backgroundColor: 'transparent',
                borderWidth: 2.5,
                tension: 0.25,
                spanGaps: true,
                pointRadius: 2,
                fill: false,
                yAxisID: 'yTemp',
            });
        }

        if (humData.some((value) => Number.isFinite(value))) {
            datasets.push({
                label: `${sensorName} (${sensorType}) - Hum (%)`,
                data: humData,
                borderColor: color,
                backgroundColor: 'transparent',
                borderWidth: 2,
                borderDash: [6, 4],
                tension: 0.25,
                spanGaps: true,
                pointRadius: 2,
                fill: false,
                yAxisID: 'yHum',
            });
        }
    });

    if (datasets.length === 0) return;

    const ctx = canvas.getContext('2d');
    if (appState.climateChartInstance) {
        appState.climateChartInstance.destroy();
    }

    appState.climateChartInstance = new Chart(ctx, {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { position: 'top' },
            },
            scales: {
                x: {
                    ticks: {
                        autoSkip: false,
                        maxRotation: 0,
                        minRotation: 0,
                        callback(value, index) {
                            const label = labels[index];
                            return isHalfHourLabel(timeKeys[index]) ? label : '';
                        },
                    },
                    grid: {
                        color(context) {
                            return isQuarterHourLabel(timeKeys[context.index])
                                ? 'rgba(148, 163, 184, 0.35)'
                                : 'rgba(148, 163, 184, 0.08)';
                        },
                    },
                },
                yTemp: {
                    type: 'linear',
                    position: 'left',
                    title: {
                        display: true,
                        text: 'Temperature (deg C)',
                    },
                },
                yHum: {
                    type: 'linear',
                    position: 'right',
                    suggestedMin: 0,
                    suggestedMax: 100,
                    grid: {
                        drawOnChartArea: false,
                    },
                    title: {
                        display: true,
                        text: 'Humidite (%)',
                    },
                },
            },
        },
    });
}

/* ============ Dashboard Updates ============ */
function updateDashboard(measurement) {
    if (!measurement) return;

    const voltage = toNumber(measurement.voltage_v, 0);
    const frequency = toNumber(measurement.frequency_hz, 0);
    const powerFactor = toNumber(measurement.power_factor, 0);

    document.getElementById('voltage-value').textContent = `${voltage.toFixed(1)} V`;
    document.getElementById('frequency-value').textContent = `${frequency.toFixed(2)} Hz`;
    document.getElementById('power-factor-value').textContent = powerFactor.toFixed(3);

    const date = new Date(measurement.ts_utc);
    document.getElementById('last-update').textContent = date.toLocaleTimeString('fr-FR');

    appState.lastUpdate = measurement.ts_utc;
}

function updateInstantSummary() {
    const point = appState.latestPoint;
    if (!point) return;

    const latestTs = new Date(point.ts_utc);
    const yesterday = findClosestReferencePoint(appState.powerSeries, latestTs, 1);
    const dayBefore = findClosestReferencePoint(appState.powerSeries, latestTs, 2);

    const currentTotals = getBusinessTotals(point);
    const yesterdayTotals = getBusinessTotals(yesterday);
    const dayBeforeTotals = getBusinessTotals(dayBefore);

    const currentCons = currentTotals.consumptionW;
    const yCons = yesterdayTotals.consumptionW;
    const d2Cons = dayBeforeTotals.consumptionW;

    const currentGenSigned = currentTotals.generatorSignedW;
    const yGenSigned = yesterdayTotals.generatorSignedW;
    const d2GenSigned = dayBeforeTotals.generatorSignedW;

    document.getElementById('total-consumption-w').textContent = fmtW(currentCons);
    document.getElementById('total-production-w').textContent = fmtW(currentGenSigned);

    document.getElementById('consumption-yesterday').textContent = fmtW(yCons);
    document.getElementById('consumption-daybefore').textContent = fmtW(d2Cons);
    document.getElementById('production-yesterday').textContent = fmtW(yGenSigned);
    document.getElementById('production-daybefore').textContent = fmtW(d2GenSigned);

    document.getElementById('consumption-trend').textContent = fmtTrend(currentCons, yCons);
    document.getElementById('production-trend').textContent = fmtTrend(Math.abs(currentGenSigned), Math.abs(yGenSigned));

    updateBillingEstimate(currentCons, currentTotals.generatorAbsW);
}

function updateChannelInstantCards() {
    const point = appState.latestPoint;
    if (!point) return;

    const latestTs = new Date(point.ts_utc);
    const yesterday = findClosestReferencePoint(appState.powerSeries, latestTs, 1);

    CHANNEL_KEYS.forEach((key) => {
        const cfg = getChannelConfig(key);
        const card = document.getElementById(`${key}-name`)?.closest('.channel-card');
        if (!card) return;

        document.getElementById(`${key}-name`).textContent = cfg.name;

        const typeNode = document.getElementById(`${key}-type`);
        typeNode.classList.remove('consumption', 'generator', 'mixed', 'edf', 'unused');
        if (cfg.type === 'generator') {
            typeNode.textContent = 'Type: generateur';
            typeNode.classList.add('generator');
        } else if (cfg.type === 'edf_total') {
            typeNode.textContent = 'Type: consommation totale EDF';
            typeNode.classList.add('edf');
        } else if (cfg.type === 'unused') {
            typeNode.textContent = 'Type: non utilise';
            typeNode.classList.add('unused');
        } else {
            typeNode.textContent = 'Type: consommation';
            typeNode.classList.add('consumption');
        }

        if (cfg.type === 'unused') {
            card.classList.add('hidden');
            return;
        }

        card.classList.remove('hidden');

        const signed = toNumber(point[`${key}_signed_w`], NaN);
        const ySigned = toNumber(yesterday ? yesterday[`${key}_signed_w`] : NaN, NaN);

        const consNode = document.getElementById(`${key}-cons-w`);
        const consLabel = consNode?.closest('.channel-row')?.querySelector('.channel-label');
        if (consLabel) consLabel.textContent = 'Puissance:';
        if (consNode) consNode.textContent = fmtW(signed);

        const prodNode = document.getElementById(`${key}-prod-w`);
        const prodRow = prodNode?.closest('.channel-row');
        if (prodRow) prodRow.style.display = 'none';

        document.getElementById(`${key}-trend`).textContent = fmtTrend(Math.abs(signed), Math.abs(ySigned)).replace('Tendance: ', '');
    });
}

function updateBillingEstimate(totalConsW, totalProdW) {
    const totalConsKwh = totalConsW / 1000;
    const totalProdKwh = totalProdW / 1000;

    const netGridKwh = totalConsKwh - totalProdKwh;
    const buyPrice = Number(CONFIG.BUY_PRICE_KWH) || 0;
    const sellPrice = Number(CONFIG.SELL_PRICE_KWH) || 0.011;
    const hasResale = Boolean(CONFIG.HAS_RESALE_CONTRACT);

    let estimatedCostEur = 0;
    let feedInValueEur = 0;
    let note = '';

    if (netGridKwh >= 0) {
        estimatedCostEur = netGridKwh * buyPrice;
        note = `Facture estimee avec tarif achat ${buyPrice.toFixed(3)} EUR/kWh.`;
    } else {
        const exportedKwh = Math.abs(netGridKwh);
        if (hasResale) {
            feedInValueEur = exportedKwh * sellPrice;
            note = `Injection valorisee a ${sellPrice.toFixed(3)} EUR/kWh (contrat de revente actif).`;
        } else {
            note = 'Injection detectee hors calcul facture sans contrat de revente.';
        }
    }

    document.getElementById('billing-net-grid').textContent = `${netGridKwh.toFixed(3)} kWh`;
    document.getElementById('billing-estimated-cost').textContent = `${estimatedCostEur.toFixed(3)} EUR`;
    document.getElementById('billing-feed-in-value').textContent = `${feedInValueEur.toFixed(3)} EUR`;
    document.getElementById('billing-note').textContent = note;
}

function updateSystemInfo(status) {
    document.getElementById('sensor-state').textContent = status.sensor || 'Inconnu';
    document.getElementById('em06-mode').textContent = status.em06_mode || 'Inconnu';

    document.getElementById('sys-server').textContent = status.server || 'Inconnu';
    document.getElementById('sys-sensor').textContent = status.sensor || 'Inconnu';
    document.getElementById('sys-mode').textContent = status.em06_mode || 'Inconnu';

    const lastTs = status.last_sample_ts_utc;
    if (lastTs) {
        const date = new Date(lastTs);
        document.getElementById('sys-last-ts').textContent = date.toLocaleString('fr-FR');
    }

    if (status.last_error) {
        document.getElementById('last-error-row').style.display = 'flex';
        document.getElementById('sys-error').textContent = status.last_error;
    } else {
        document.getElementById('last-error-row').style.display = 'none';
    }
}

function updateStatus(status, latest) {
    const indicator = document.getElementById('status-indicator');
    const text = document.getElementById('status-text');

    if (!status || typeof status !== 'object') {
        indicator.classList.add('error');
        text.textContent = 'API indisponible';
        return;
    }

    const sensor = String(status.sensor || '').toLowerCase();
    const server = String(status.server || '').toLowerCase();
    const isFresh = latest && typeof latest.is_fresh === 'boolean' ? latest.is_fresh : null;

    if (!sensor && server === 'running') {
        indicator.classList.remove('error');
        text.textContent = 'API connectee';
        return;
    }

    if (sensor === 'connected' && isFresh !== false) {
        indicator.classList.remove('error');
        text.textContent = 'Capteur connecte';
        return;
    }

    if (sensor === 'connected' && isFresh === false) {
        indicator.classList.add('error');
        text.textContent = 'Donnees anciennes';
        return;
    }

    if (sensor === 'starting' || sensor === 'connecting') {
        indicator.classList.remove('error');
        text.textContent = 'Connexion capteur...';
        return;
    }

    if (sensor === 'error') {
        indicator.classList.add('error');
        text.textContent = 'Capteur en erreur';
    } else {
        indicator.classList.add('error');
        text.textContent = 'API statut inconnu';
    }
}

function updateFooter() {
    const now = new Date();
    const time = now.toLocaleTimeString('fr-FR');
    document.getElementById('footer-time').textContent = time;
    document.getElementById('footer-interval').textContent = CONFIG.REFRESH_INTERVAL / 1000;
}

/* ============ Chart Filters ============ */
function initializeChartContainer() {
    const container = document.querySelector('.chart-container');
    if (!container) return;

    if (!document.getElementById('trend-chart')) {
        const canvas = document.createElement('canvas');
        canvas.id = 'trend-chart';
        container.appendChild(canvas);
    }
}

function syncSelectedGraphChannels() {
    const used = getUsedChannelKeys().filter((key) => getChannelConfig(key).graph !== false);
    const allKeys = new Set(['total', ...used]);

    if (!appState.selectedGraphChannels || appState.selectedGraphChannels.size === 0) {
        appState.selectedGraphChannels = new Set(['total']);
    }

    appState.selectedGraphChannels.forEach((key) => {
        if (!allKeys.has(key)) {
            appState.selectedGraphChannels.delete(key);
        }
    });

    if (appState.selectedGraphChannels.size === 0) {
        appState.selectedGraphChannels.add('total');
    }
}

function refreshChartFilters() {
    syncSelectedGraphChannels();

    const wrap = document.getElementById('chart-filters');
    if (!wrap) return;

    wrap.innerHTML = '';

    const addCheckbox = (key, label) => {
        const item = document.createElement('label');
        item.className = 'chart-filter-item';

        const input = document.createElement('input');
        input.type = 'checkbox';
        input.checked = appState.selectedGraphChannels.has(key);
        input.addEventListener('change', () => {
            if (input.checked) {
                appState.selectedGraphChannels.add(key);
            } else {
                appState.selectedGraphChannels.delete(key);
            }
            if (appState.selectedGraphChannels.size === 0) {
                appState.selectedGraphChannels.add('total');
                refreshChartFilters();
            }
            renderTrendChart();
        });

        const text = document.createElement('span');
        text.textContent = label;

        item.appendChild(input);
        item.appendChild(text);
        wrap.appendChild(item);
    };

    addCheckbox('total', 'Total');

    getUsedChannelKeys().forEach((key) => {
        const cfg = getChannelConfig(key);
        if (cfg.graph === false) return;
        addCheckbox(key, cfg.name);
    });
}

/* ============ Expandable Channels ============ */
function initializeExpandableChannels() {
    const toggle = document.getElementById('channels-toggle');
    const content = document.getElementById('channels-content');
    const icon = document.getElementById('channels-toggle-icon');
    if (!toggle || !content || !icon) return;

    toggle.addEventListener('click', () => {
        const isOpen = content.classList.toggle('open');
        toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
        icon.textContent = isOpen ? '▾' : '▸';
    });
}

/* ============ Date Pickers ============ */
function initializeDatepickers() {
    const fromInput = document.getElementById('from-date');
    const toInput = document.getElementById('to-date');
    const applyButton = document.getElementById('apply-filter');
    const prevButton = document.getElementById('prev-page');
    const nextButton = document.getElementById('next-page');

    if (!fromInput || !toInput || !applyButton || !prevButton || !nextButton) {
        return;
    }

    const now = new Date();
    const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);

    toInput.valueAsDate = now;
    fromInput.valueAsDate = sevenDaysAgo;

    applyButton.addEventListener('click', () => {
        appState.selectedFromDate = fromInput.value;
        appState.selectedToDate = toInput.value;
        appState.historyPage = 0;
        loadHistory();
    });

    prevButton.addEventListener('click', () => {
        if (appState.historyPage > 0) {
            appState.historyPage -= 1;
            loadHistory();
        }
    });

    nextButton.addEventListener('click', () => {
        appState.historyPage += 1;
        loadHistory();
    });
}

async function loadHistory() {
    try {
        let url = `${CONFIG.API_BASE}/api/measurements?limit=${CONFIG.HISTORY_LIMIT}`;

        if (appState.selectedFromDate && appState.selectedToDate) {
            const from = new Date(appState.selectedFromDate).toISOString();
            const to = new Date(appState.selectedToDate);
            to.setHours(23, 59, 59, 999);
            const toIso = to.toISOString();
            url = `${CONFIG.API_BASE}/api/measurements?from_ts_utc=${from}&to_ts_utc=${toIso}&limit=${CONFIG.HISTORY_LIMIT}`;
        } else {
            const now = new Date();
            const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
            url = `${CONFIG.API_BASE}/api/measurements?from_ts_utc=${sevenDaysAgo.toISOString()}&to_ts_utc=${now.toISOString()}&limit=${CONFIG.HISTORY_LIMIT}`;
        }

        const response = await fetch(url);
        if (!response.ok) throw new Error('Failed to load history');

        const data = await response.json();
        const measurements = (data.data || []).reverse();

        const tbody = document.getElementById('history-tbody');
        tbody.innerHTML = '';

        if (measurements.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="loading">Aucune donnee</td></tr>';
            return;
        }

        measurements.forEach((m) => {
            const row = document.createElement('tr');
            const date = new Date(m.ts_utc);
            const time = date.toLocaleTimeString('fr-FR');
            const prod = toNumber(m.total_production_kwh, 0);
            const cons = toNumber(m.total_consumption_kwh, 0);
            const voltage = toNumber(m.voltage_v, 0);
            const pf = toNumber(m.power_factor, 0);

            row.innerHTML = `
                <td>${time}</td>
                <td>${prod.toFixed(3)}</td>
                <td>${cons.toFixed(3)}</td>
                <td>${voltage.toFixed(1)}</td>
                <td>${pf.toFixed(3)}</td>
            `;
            tbody.appendChild(row);
        });

        document.getElementById('page-info').textContent = `${measurements.length} mesures affichees`;
    } catch (error) {
        console.error('Error loading history:', error);
        const tbody = document.getElementById('history-tbody');
        tbody.innerHTML = '<tr><td colspan="5" class="loading">Erreur</td></tr>';
    }
}

/* ============ Settings ============ */
function loadSettings() {
    const stored = localStorage.getItem('datalogueur-settings');
    let settings = null;
    if (stored) {
        try {
            settings = JSON.parse(stored);
        } catch (error) {
            console.warn('Invalid datalogueur-settings in localStorage, reset to defaults.', error);
            localStorage.removeItem('datalogueur-settings');
        }
    }

    if (settings) {
        CONFIG.REFRESH_INTERVAL = settings.refreshInterval || 3000;
        CONFIG.CHART_HOURS = settings.chartHours || 24;
        CONFIG.BUY_PRICE_KWH = settings.buyPriceKwh ?? 0.25;
        CONFIG.SELL_PRICE_KWH = settings.sellPriceKwh ?? 0.011;
        CONFIG.HAS_RESALE_CONTRACT = Boolean(settings.hasResaleContract);

        if (settings.channels && typeof settings.channels === 'object') {
            const merged = {};
            CHANNEL_KEYS.forEach((key) => {
                const base = getChannelConfig(key);
                const saved = settings.channels[key] || {};
                merged[key] = {
                    name: saved.name || base.name,
                    type: saved.type || base.type,
                    graph: typeof saved.graph === 'boolean' ? saved.graph : true,
                };
            });
            CONFIG.CHANNELS = merged;
        }

        if (settings.sensors && typeof settings.sensors === 'object') {
            const mergedSensors = {};
            Object.entries(settings.sensors).forEach(([key, raw]) => {
                if (!key) return;
                const row = raw && typeof raw === 'object' ? raw : {};
                mergedSensors[key] = {
                    name: typeof row.name === 'string' ? row.name : '',
                    type: row.type === 'exterieur' ? 'exterieur' : 'interieur',
                };
            });
            CONFIG.SENSORS = mergedSensors;
        }

        const refreshInput = document.getElementById('refresh-interval');
        const chartHoursInput = document.getElementById('chart-hours');
        const buyInput = document.getElementById('buy-price-kwh');
        const sellInput = document.getElementById('sell-price-kwh');
        const resaleInput = document.getElementById('has-resale-contract');
        if (refreshInput) refreshInput.value = CONFIG.REFRESH_INTERVAL / 1000;
        if (chartHoursInput) chartHoursInput.value = CONFIG.CHART_HOURS;
        if (buyInput) buyInput.value = CONFIG.BUY_PRICE_KWH;
        if (sellInput) sellInput.value = CONFIG.SELL_PRICE_KWH;
        if (resaleInput) resaleInput.checked = CONFIG.HAS_RESALE_CONTRACT;
    } else {
        const buyInput = document.getElementById('buy-price-kwh');
        const sellInput = document.getElementById('sell-price-kwh');
        const resaleInput = document.getElementById('has-resale-contract');
        if (buyInput) buyInput.value = CONFIG.BUY_PRICE_KWH;
        if (sellInput) sellInput.value = CONFIG.SELL_PRICE_KWH;
        if (resaleInput) resaleInput.checked = CONFIG.HAS_RESALE_CONTRACT;
    }

    applyChannelSettingsToForm();
    refreshChartFilters();
    renderSensorSettingsRows();

    const saveButton = document.getElementById('save-settings');
    if (saveButton) {
        saveButton.addEventListener('click', saveSettings);
    }
}

function applyChannelSettingsToForm() {
    CHANNEL_KEYS.forEach((key) => {
        const cfg = getChannelConfig(key);
        const nameInput = document.getElementById(`cfg-${key}-name`);
        const typeInput = document.getElementById(`cfg-${key}-type`);
        const graphInput = document.getElementById(`cfg-${key}-graph`);
        if (nameInput) nameInput.value = cfg.name;
        if (typeInput) typeInput.value = cfg.type;
        if (graphInput) graphInput.value = cfg.graph === false ? 'no' : 'yes';
    });
}

function saveSettings() {
    const refreshInput = document.getElementById('refresh-interval');
    const chartHoursInput = document.getElementById('chart-hours');
    const buyInput = document.getElementById('buy-price-kwh');
    const sellInput = document.getElementById('sell-price-kwh');
    const resaleInput = document.getElementById('has-resale-contract');

    if (!refreshInput || !chartHoursInput || !buyInput || !sellInput || !resaleInput) {
        return;
    }

    const refreshInterval = parseInt(refreshInput.value, 10) * 1000;
    const chartHours = parseInt(chartHoursInput.value, 10);
    const buyPriceKwh = parseFloat(buyInput.value);
    const sellPriceKwh = parseFloat(sellInput.value);
    const hasResaleContract = resaleInput.checked;

    const channels = {};
    CHANNEL_KEYS.forEach((key) => {
        const nameInput = document.getElementById(`cfg-${key}-name`);
        const typeInput = document.getElementById(`cfg-${key}-type`);
        const graphInput = document.getElementById(`cfg-${key}-graph`);
        const name = nameInput ? nameInput.value.trim() : '';
        const type = typeInput ? typeInput.value : 'consumption';
        const graph = graphInput ? graphInput.value === 'yes' : true;

        channels[key] = {
            name: name || `Canal ${key.toUpperCase()}`,
            type,
            graph,
        };
    });

    const sensors = {};
    document.querySelectorAll('.sensor-name-input').forEach((input) => {
        const sensorKey = String(input.dataset.sensorKey || '').trim();
        if (!sensorKey) return;
        const typeSelect = document.querySelector(`.sensor-type-select[data-sensor-key="${sensorKey}"]`);
        const typeValue = typeSelect ? typeSelect.value : 'interieur';
        sensors[sensorKey] = {
            name: String(input.value || '').trim(),
            type: typeValue === 'exterieur' ? 'exterieur' : 'interieur',
        };
    });

    CONFIG.REFRESH_INTERVAL = Number.isFinite(refreshInterval) ? Math.max(1000, refreshInterval) : 3000;
    CONFIG.CHART_HOURS = Number.isFinite(chartHours) ? Math.max(1, Math.min(720, chartHours)) : 24;
    CONFIG.BUY_PRICE_KWH = Number.isFinite(buyPriceKwh) ? Math.max(0, buyPriceKwh) : 0.25;
    CONFIG.SELL_PRICE_KWH = Number.isFinite(sellPriceKwh) ? Math.max(0, sellPriceKwh) : 0.011;
    CONFIG.HAS_RESALE_CONTRACT = hasResaleContract;
    CONFIG.CHANNELS = channels;
    CONFIG.SENSORS = sensors;

    localStorage.setItem(
        'datalogueur-settings',
        JSON.stringify({
            refreshInterval: CONFIG.REFRESH_INTERVAL,
            chartHours: CONFIG.CHART_HOURS,
            buyPriceKwh: CONFIG.BUY_PRICE_KWH,
            sellPriceKwh: CONFIG.SELL_PRICE_KWH,
            hasResaleContract: CONFIG.HAS_RESALE_CONTRACT,
            channels: CONFIG.CHANNELS,
            sensors: CONFIG.SENSORS,
        })
    );

    refreshChartFilters();
    renderSensorSettingsRows();
    updateChannelInstantCards();
    updateTemperatureCard();
    renderTrendChart();
    renderClimateChart();

    alert('Parametres enregistres');
}

// Auto-refresh footer time display every second
setInterval(() => {
    const now = new Date();
    const time = now.toLocaleTimeString('fr-FR');
    const footerTime = document.getElementById('footer-time');
    if (footerTime) footerTime.textContent = time;
}, 1000);
