// Configuration
const CHANNEL_KEYS = ['a1', 'b1', 'c1', 'a2', 'b2', 'c2'];
const ENERGY_FIELDS = [
    'total_consumption_kwh',
    'total_production_kwh',
    ...CHANNEL_KEYS.flatMap((key) => [`${key}_consumption_kwh`, `${key}_production_kwh`]),
];
const CONFIG = {
    API_BASE: '',
    REFRESH_INTERVAL: 5000,
    CHART_HOURS: 24,
    CHART_REFRESH_INTERVAL: 60000,
    CHART_MAX_SAMPLE_LIMIT: 3000,
    CLIMATE_MAX_SAMPLE_LIMIT: 3000,
    TODAY_ENERGY_REFRESH_MS: 45000,
    POWER_INTERVAL_SECONDS: 20,
    REALTIME_FILTER_ALPHA: 0.1,
    CHART_RESAMPLE_MINUTES: 5,
    CHART_AXIS_LABEL_MINUTES: 15,
    CHART_MOVING_AVERAGE_WINDOW: 3,
    HISTORY_LIMIT: 100,
    HISTORY_SUMMARY_REFRESH_MS: 24 * 60 * 60 * 1000,
    QUALITY_REFRESH_MS: 5 * 60 * 1000,
    HISTORY_PAGE_SIZE: 31,
    BUY_PRICE_KWH: 0.25,
    SURPLUS_PRICE_KWH: 0,
    SELL_PRICE_KWH: 0.011,
    HAS_RESALE_CONTRACT: false,
    UNIFIED_CHART_MODE: 'power_temp',
    GRAPH_SERIES: {
        consumption: true,
        temperature: true,
        humidity: true,
    },
    SENSORS: {},
    CHANNELS: {
        a1: { name: 'Canal A1', type: 'unused', graph: true },
        b1: { name: 'Canal B1', type: 'unused', graph: true },
        c1: { name: 'Consommation totale EDF (C1)', type: 'edf_total', graph: true },
        a2: { name: 'Photovoltaïque (A2)', type: 'generator', graph: true },
        b2: { name: 'Consommation B2', type: 'consumption', graph: true },
        c2: { name: 'Consommation C2', type: 'consumption', graph: true },
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
    selectedGraphChannels: new Set(),
    latestTemperature: null,
    latestTemperatureAgeSeconds: null,
    climateSeries: [],
    lastClimateRefreshMs: 0,
    lastTodayEnergyRefreshMs: 0,
    lastHistorySummaryRefreshMs: 0,
    lastQualityRefreshMs: 0,
    historySummaryChart: null,
    dataQuality: null,
    knownSensors: new Set(),
    unifiedHiddenDatasets: {},
    dailyEnergySeries: [],
    todayEnergy: null,
};

function getDefaultSelectedGraphChannels() {
    const keys = ['total'];
    getUsedChannelKeys().forEach((key) => {
        if (getChannelConfig(key).graph !== false) {
            keys.push(key);
        }
    });
    return new Set(keys);
}

// Initialize app
let appInitialized = false;

function startApp() {
    if (appInitialized) return;
    appInitialized = true;

    try {
        initializeNavigation();
        initializeDatepickers();
        initializeChartContainer();
        initializeGraphSeriesControls();
        initializeExpandableChannels();
        loadSettings();
        updateAllData();
        scheduleBootHeavyLoads();

        setInterval(updateAllData, CONFIG.REFRESH_INTERVAL);
        setInterval(() => refreshTodayEnergy(false), CONFIG.TODAY_ENERGY_REFRESH_MS);
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
    // On slow devices, deferred script downloads can delay DOMContentLoaded.
    // Ensure core polling starts anyway after a short grace period.
    window.setTimeout(startApp, 1500);
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

function fmtKwh(value, digits = 3) {
    if (!Number.isFinite(value)) return '-- kWh';
    return `${Number(value).toFixed(digits)} kWh`;
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

function fmtPct(value) {
    if (!Number.isFinite(value)) return '-- %';
    return `${Number(value).toFixed(1)} %`;
}

function getLocalDayStartIso() {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), now.getDate()).toISOString();
}

function localDateStringToUtcIso(dateStr, endOfDay = false) {
    if (!dateStr) return '';
    const parts = String(dateStr).split('-').map(Number);
    if (parts.length !== 3 || parts.some((n) => !Number.isFinite(n))) return '';
    const [year, month, day] = parts;
    const dt = endOfDay
        ? new Date(year, month - 1, day, 23, 59, 59, 999)
        : new Date(year, month - 1, day, 0, 0, 0, 0);
    return dt.toISOString();
}

function computeEnergyMetrics(c1NetKwh, a2ProdKwh) {
    const c1 = toNumber(c1NetKwh, 0);
    const a2 = Math.max(0, toNumber(a2ProdKwh, 0));
    const consoReelle = c1 + a2;
    const consoFact = Math.max(0, c1);
    const surplus = c1 < 0 ? Math.abs(c1) : 0;
    const autoconso = a2 - surplus;
    const tauxAutoconso = a2 > 0 ? (autoconso / a2) * 100 : NaN;
    const tauxAutoproduction = consoReelle > 0 ? (autoconso / consoReelle) * 100 : NaN;
    return {
        c1NetKwh: c1,
        a2ProdKwh: a2,
        consoReelle,
        consoFact,
        surplus,
        autoconso,
        tauxAutoconso,
        tauxAutoproduction,
    };
}

function computeDayBillEur(consoFact, surplus) {
    const buyPrice = Number(CONFIG.BUY_PRICE_KWH) || 0;
    const surplusPrice = Number(CONFIG.SURPLUS_PRICE_KWH) || 0;
    return consoFact * buyPrice - surplus * surplusPrice;
}

function monthKeyFromDate(dateObj) {
    return `${dateObj.getFullYear()}-${String(dateObj.getMonth() + 1).padStart(2, '0')}`;
}

function formatMonthLabel(monthKey) {
    if (!monthKey) return '--';
    const [year, month] = String(monthKey).split('-');
    if (!year || !month) return monthKey;
    return `${month}/${year}`;
}

function sumMonthBillEur(series, monthKey) {
    return (Array.isArray(series) ? series : [])
        .filter((row) => String(row.date_utc || '').startsWith(`${monthKey}-`))
        .reduce((sum, row) => {
            const metrics = computeEnergyMetrics(row.c1_net_kwh, row.pv_production_kwh);
            return sum + computeDayBillEur(metrics.consoFact, metrics.surplus);
        }, 0);
}

function getChannelConfig(key) {
    const fallback = { name: `Canal ${key.toUpperCase()}`, type: 'consumption', graph: true };
    return { ...fallback, ...(CONFIG.CHANNELS[key] || {}) };
}

function getSensorKey(row) {
    if (!row || typeof row !== 'object') return '';
    const mac = String(row.device_mac || '').trim();
    if (mac) return mac;

    const deviceId = String(row.device_id || '').trim();
    if (!deviceId) return '';

    const mapped = (appState.climateSeries || []).find((item) => {
        if (!item || typeof item !== 'object') return false;
        return String(item.device_id || '').trim() === deviceId && String(item.device_mac || '').trim();
    });

    if (mapped && mapped.device_mac) {
        return String(mapped.device_mac).trim();
    }
    return deviceId;
}

function getSensorConfig(sensorKey) {
    const key = String(sensorKey || '').trim();
    const saved = (CONFIG.SENSORS && CONFIG.SENSORS[key]) || {};
    return {
        name: typeof saved.name === 'string' ? saved.name.trim() : '',
        type: saved.type === 'exterieur' ? 'exterieur' : 'interieur',
        graph: typeof saved.graph === 'boolean' ? saved.graph : true,
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
        const normalized = String(key || '').trim();
        if (normalized) keys.add(normalized);
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
            if (cfg.type === 'edf_total') {
                point[`${key}_signed_w`] = consumptionW - productionW;
            } else if (cfg.type === 'generator') {
                point[`${key}_signed_w`] = -productionW;
            } else {
                point[`${key}_signed_w`] = consumptionW;
            }
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

function applyGraphSeriesControlValues() {
    const consumptionInput = document.getElementById('graph-show-consumption');
    const temperatureInput = document.getElementById('graph-show-temperature');
    const humidityInput = document.getElementById('graph-show-humidity');
    if (consumptionInput) consumptionInput.checked = CONFIG.GRAPH_SERIES.consumption !== false;
    if (temperatureInput) temperatureInput.checked = CONFIG.GRAPH_SERIES.temperature !== false;
    if (humidityInput) humidityInput.checked = CONFIG.GRAPH_SERIES.humidity !== false;
}

function initializeGraphSeriesControls() {
    const consumptionInput = document.getElementById('graph-show-consumption');
    const temperatureInput = document.getElementById('graph-show-temperature');
    const humidityInput = document.getElementById('graph-show-humidity');

    applyGraphSeriesControlValues();

    const onChange = () => {
        CONFIG.GRAPH_SERIES.consumption = !consumptionInput || consumptionInput.checked;
        CONFIG.GRAPH_SERIES.temperature = !temperatureInput || temperatureInput.checked;
        CONFIG.GRAPH_SERIES.humidity = !humidityInput || humidityInput.checked;
        renderTrendChart();
    };

    if (consumptionInput) consumptionInput.addEventListener('change', onChange);
    if (temperatureInput) temperatureInput.addEventListener('change', onChange);
    if (humidityInput) humidityInput.addEventListener('change', onChange);
}

function getFixedDailySlots() {
    const now = new Date();
    const dayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0, 0);
    const slotMs = 15 * 60 * 1000;
    const slots = [];

    for (let i = 0; i < 96; i += 1) {
        const ts = new Date(dayStart.getTime() + i * slotMs);
        const hh = String(ts.getHours()).padStart(2, '0');
        const mm = String(ts.getMinutes()).padStart(2, '0');
        slots.push({ index: i, tsMs: ts.getTime(), label: `${hh}:${mm}` });
    }

    return { dayStartMs: dayStart.getTime(), slotMs, slots };
}

function aggregateByDailySlots(rows, getValue) {
    const { dayStartMs, slotMs, slots } = getFixedDailySlots();
    const sums = new Array(slots.length).fill(0);
    const counts = new Array(slots.length).fill(0);

    (rows || []).forEach((row) => {
        const ts = parseTimestampMs(row.ts_utc);
        if (!Number.isFinite(ts)) return;
        const idx = Math.floor((ts - dayStartMs) / slotMs);
        if (idx < 0 || idx >= slots.length) return;

        const value = Number(getValue(row));
        if (!Number.isFinite(value)) return;
        sums[idx] += value;
        counts[idx] += 1;
    });

    return counts.map((count, idx) => (count > 0 ? sums[idx] / count : null));
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
        ? edfKeys.reduce(
            (sum, key) => sum + toNumber(point[`${key}_consumption_w`], 0) - toNumber(point[`${key}_production_w`], 0),
            0,
        )
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
    window.__appNavReady = true;
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
        loadHistorySummary(false);
        loadHistory();
    }
    if (page === 'dashboard') {
        refreshPowerAnalytics(true);
        refreshClimateAnalytics(true);
    }
    if (page === 'settings') {
        renderSensorSettingsRows();
        refreshClimateAnalytics(true);
    }
}

/* ============ Data Loading ============ */
function scheduleBootHeavyLoads() {
    window.setTimeout(() => {
        void Promise.all([
            refreshTodayEnergy(true),
            refreshPowerAnalytics(true),
            refreshClimateAnalytics(true),
        ]);
    }, 80);
}

async function updateAllData() {
    try {
        const [status, latest, temperature] = await Promise.all([
            safeFetchJson(`${CONFIG.API_BASE}/api/status`, 4000),
            safeFetchJson(`${CONFIG.API_BASE}/api/measurements/latest`, 4000),
            safeFetchJson(`${CONFIG.API_BASE}/api/temperature/latest`, 5000),
        ]);

        appState.latestTemperature = temperature && temperature.data ? temperature.data : null;
        appState.latestTemperatureAgeSeconds = temperature && Number.isFinite(Number(temperature.data_age_seconds))
            ? Number(temperature.data_age_seconds)
            : null;

        updateStatus(status, latest);
        updateTemperatureCard();
        renderSensorSettingsRows();
        refreshQualityInfo(false);

        if (status) {
            updateSystemInfo(status);
        }

        if (latest && latest.data) {
            updateDashboard(latest.data, status || {});
        }

        updateFooter();
    } catch (error) {
        console.error('Error fetching data:', error);
        updateStatus(null, null);
    }
}

function refreshQualityInfo(force) {
    const now = Date.now();
    if (!force && now - appState.lastQualityRefreshMs < CONFIG.QUALITY_REFRESH_MS) {
        return;
    }
    appState.lastQualityRefreshMs = now;

    safeFetchJson(`${CONFIG.API_BASE}/api/quality/latest?minutes=120`, 2500)
        .then((quality) => {
            if (quality && typeof quality === 'object') {
                updateQualityInfo(quality);
            }
        })
        .catch(() => {
            // Keep previous quality info if quality API times out.
        });
}

function updateQualityInfo(quality) {
    const statusNode = document.getElementById('quality-status');
    const confNode = document.getElementById('quality-confidence');
    if (!statusNode || !confNode) return;

    if (!quality || typeof quality !== 'object') {
        statusNode.textContent = 'inconnue';
        confNode.textContent = '--';
        appState.dataQuality = null;
        return;
    }

    const status = String(quality.status || 'inconnue');
    const confidence = Number(quality.confidence_pct);
    statusNode.textContent = status;
    confNode.textContent = Number.isFinite(confidence) ? `${Math.round(confidence)} %` : '--';
    appState.dataQuality = quality;
}

async function safeFetchJson(url, timeoutMs) {
    const ms = Math.max(500, Number(timeoutMs) || 4000);
    const hasAbort = typeof AbortController !== 'undefined';
    const controller = hasAbort ? new AbortController() : null;

    const fetchPromise = fetch(url, hasAbort ? { signal: controller.signal } : undefined)
        .then((response) => (response.ok ? response.json() : null))
        .catch(() => null);

    let timeoutHandle = null;
    const timeoutPromise = new Promise((resolve) => {
        timeoutHandle = window.setTimeout(() => {
            if (controller) {
                try {
                    controller.abort();
                } catch (_) {}
            }
            resolve(null);
        }, ms);
    });

    const result = await Promise.race([fetchPromise, timeoutPromise]);
    if (timeoutHandle) window.clearTimeout(timeoutHandle);
    return result;
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
        const chartHours = Math.max(1, Math.min(Number(CONFIG.CHART_HOURS) || 24, 168));
        const minutes = chartHours * 60;
        const sampleLimit = Math.min(
            CONFIG.CHART_MAX_SAMPLE_LIMIT,
            Math.ceil((minutes * 60) / Math.max(CONFIG.REFRESH_INTERVAL, 1)) + 20,
        );
        const response = await fetch(`${CONFIG.API_BASE}/api/measurements?minutes=${minutes}&limit=${sampleLimit}`);
        if (!response.ok) throw new Error('Failed to load power analytics');

        const payload = await response.json();
        const rawSeries = buildInstantPowerSeries(payload.data || []);
        const filteredSeries = applyExponentialFilter(rawSeries, CONFIG.REALTIME_FILTER_ALPHA);

        appState.rawPowerSeries = rawSeries;
        appState.powerSeries = filteredSeries;
        appState.latestPoint = filteredSeries.length ? filteredSeries[filteredSeries.length - 1] : null;
        appState.lastPowerRefreshMs = now;

        updateChannelInstantCards();
        renderTrendChart();
    } catch (error) {
        console.error('Error loading instant analytics:', error);
    }
}

async function refreshTodayEnergy(force = false) {
    const now = Date.now();
    if (!force && now - appState.lastTodayEnergyRefreshMs < CONFIG.TODAY_ENERGY_REFRESH_MS) {
        return;
    }

    try {
        const from = encodeURIComponent(getLocalDayStartIso());
        const response = await fetch(`${CONFIG.API_BASE}/api/energy/today?from_ts_utc=${from}`);
        if (!response.ok) throw new Error('Failed to load today energy');

        const payload = await response.json();
        applyTodayEnergyPayload(payload);
        appState.lastTodayEnergyRefreshMs = now;
    } catch (error) {
        console.error('Error loading today energy:', error);
    }
}

function applyTodayEnergyPayload(payload) {
    if (!payload || typeof payload !== 'object') return;
    appState.todayEnergy = {
        c1NetKwh: toNumber(payload.c1_net_kwh, 0),
        a2ProdKwh: toNumber(payload.a2_production_kwh, 0),
        consoReelle: toNumber(payload.conso_reelle_kwh, 0),
        consoFact: toNumber(payload.conso_fact_kwh, 0),
        surplus: toNumber(payload.surplus_kwh, 0),
        autoconso: toNumber(payload.autoconso_kwh, 0),
        tauxAutoconso: toNumber(payload.taux_autoconso_pct, NaN),
        tauxAutoproduction: toNumber(payload.taux_autoproduction_pct, NaN),
    };
    updateEnergyDashboard();
}

function updateEnergyDashboard() {
    const metrics = appState.todayEnergy || {
        consoReelle: 0,
        consoFact: 0,
        surplus: 0,
        autoconso: 0,
        tauxAutoconso: NaN,
        tauxAutoproduction: NaN,
    };
    const billEur = computeDayBillEur(metrics.consoFact, metrics.surplus);

    setTextById('energy-conso-reelle', fmtKwh(metrics.consoReelle, 3));
    setTextById('energy-conso-fact', fmtKwh(metrics.consoFact, 3));
    setTextById('energy-surplus', fmtKwh(metrics.surplus, 3));
    setTextById('energy-autoconso', fmtKwh(metrics.autoconso, 3));
    setTextById('energy-taux-autoconso', fmtPct(metrics.tauxAutoconso));
    setTextById('energy-taux-autoproduction', fmtPct(metrics.tauxAutoproduction));
    setTextById('energy-facture-jour', `${billEur.toFixed(3)} EUR`);
}

function renderTrendChart() {
    if (typeof Chart === 'undefined') return;
    const canvas = document.getElementById('trend-chart');
    if (!canvas) return;

    const { slots } = getFixedDailySlots();
    const labels = slots.map((slot) => slot.label);
    const datasets = [];
    const showConsumption = CONFIG.GRAPH_SERIES.consumption !== false;
    const showTemperature = CONFIG.GRAPH_SERIES.temperature !== false;
    const showHumidity = CONFIG.GRAPH_SERIES.humidity !== false;
    syncSelectedGraphChannels();

    if (showConsumption) {
        if (appState.selectedGraphChannels.has('total')) {
            const powerData = aggregateByDailySlots(appState.powerSeries, (point) => {
                const totals = getBusinessTotals(point);
                return totals.consumptionW;
            });
            datasets.push({
                label: 'Réseau C1 net (W)',
                data: powerData,
                borderColor: '#dc2626',
                backgroundColor: 'transparent',
                borderWidth: 2.5,
                tension: 0.25,
                spanGaps: true,
                pointRadius: 1.5,
                yAxisID: 'yPower',
            });
        }

        getUsedChannelKeys().forEach((channelKey) => {
            if (getChannelConfig(channelKey).graph === false) return;
            if (!appState.selectedGraphChannels.has(channelKey)) return;
            const cfg = getChannelConfig(channelKey);
            const series = aggregateByDailySlots(appState.powerSeries, (point) => point[`${channelKey}_signed_w`]);
            if (!series.some((v) => Number.isFinite(v))) return;

            const typeLabel = cfg.type === 'generator'
                ? 'Generation'
                : cfg.type === 'edf_total'
                    ? 'Réseau net'
                    : 'Consommation';

            datasets.push({
                label: `${cfg.name} - ${typeLabel} (W signe)`,
                data: series,
                borderColor: getLineColor(channelKey, 'consumption'),
                backgroundColor: 'transparent',
                borderWidth: 1.8,
                tension: 0.25,
                spanGaps: true,
                pointRadius: 1.2,
                yAxisID: 'yPower',
            });
        });
    }

    const climateSeries = Array.isArray(appState.climateSeries) ? appState.climateSeries : [];
    const bySensor = new Map();
    climateSeries.forEach((row) => {
        const sensorKey = getSensorKey(row);
        if (!sensorKey) return;
        if (!bySensor.has(sensorKey)) bySensor.set(sensorKey, []);
        bySensor.get(sensorKey).push(row);
    });

    const palette = ['#0ea5e9', '#16a34a', '#f97316', '#a855f7', '#e11d48', '#14b8a6'];
    Array.from(bySensor.keys()).sort().forEach((sensorKey, index) => {
        const cfg = getSensorConfig(sensorKey);
        if (cfg.graph === false) return;

        const sensorRows = bySensor.get(sensorKey);
        const sensorName = getSensorDisplayName(sensorKey);
        const sensorType = getSensorTypeLabel(sensorKey);
        const color = palette[index % palette.length];

        if (showTemperature) {
            const tempLabel = `${sensorName} (${sensorType}) - Temp (deg C)`;
            const tempData = aggregateByDailySlots(sensorRows, (row) => row.temperature_c);
            if (tempData.some((v) => Number.isFinite(v))) {
                datasets.push({
                    label: tempLabel,
                    data: tempData,
                    borderColor: color,
                    backgroundColor: 'transparent',
                    borderWidth: 2,
                    tension: 0.25,
                    spanGaps: true,
                    pointRadius: 1.5,
                    yAxisID: 'yTemp',
                });
            }
        }

        if (showHumidity) {
            const humLabel = `${sensorName} (${sensorType}) - Hum (%)`;
            const humData = aggregateByDailySlots(sensorRows, (row) => row.humidity_pct);
            if (humData.some((v) => Number.isFinite(v))) {
                datasets.push({
                    label: humLabel,
                    data: humData,
                    borderColor: color,
                    backgroundColor: 'transparent',
                    borderWidth: 2,
                    borderDash: [6, 4],
                    tension: 0.25,
                    spanGaps: true,
                    pointRadius: 1.5,
                    yAxisID: 'yHum',
                });
            }
        }
    });

    if (datasets.length === 0) return;

    const hasPowerDatasets = datasets.some((dataset) => dataset.yAxisID === 'yPower');
    const hasTempDatasets = datasets.some((dataset) => dataset.yAxisID === 'yTemp');
    const hasHumDatasets = datasets.some((dataset) => dataset.yAxisID === 'yHum');

    datasets.forEach((dataset) => {
        if (appState.unifiedHiddenDatasets[dataset.label] === true) {
            dataset.hidden = true;
        }
    });

    const ctx = canvas.getContext('2d');
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
                legend: {
                    position: 'top',
                    onClick(legendEvent, legendItem, legend) {
                        const chart = legend.chart;
                        const dsIndex = legendItem.datasetIndex;
                        const dsLabel = chart.data.datasets[dsIndex].label;
                        const currentlyVisible = chart.isDatasetVisible(dsIndex);
                        chart.setDatasetVisibility(dsIndex, !currentlyVisible);
                        appState.unifiedHiddenDatasets[dsLabel] = currentlyVisible;
                        chart.update();
                    },
                },
            },
            scales: {
                x: {
                    ticks: {
                        autoSkip: false,
                        maxRotation: 0,
                        minRotation: 0,
                        callback(value, index) {
                            return index % 4 === 0 ? labels[index] : '';
                        },
                    },
                },
                yPower: {
                    display: hasPowerDatasets,
                    type: 'linear',
                    position: 'left',
                    title: {
                        display: hasPowerDatasets,
                        text: 'Puissance (W)',
                    },
                },
                yTemp: {
                    display: hasTempDatasets,
                    type: 'linear',
                    position: hasPowerDatasets ? 'right' : 'left',
                    title: {
                        display: hasTempDatasets,
                        text: 'Temperature (deg C)',
                    },
                    grid: {
                        drawOnChartArea: !hasPowerDatasets,
                    },
                },
                yHum: {
                    display: hasHumDatasets,
                    type: 'linear',
                    position: 'right',
                    suggestedMin: 0,
                    suggestedMax: 100,
                    title: {
                        display: hasHumDatasets,
                        text: 'Humidite (%)',
                    },
                    grid: {
                        drawOnChartArea: false,
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
        const limit = CONFIG.CLIMATE_MAX_SAMPLE_LIMIT;
        const response = await fetch(`${CONFIG.API_BASE}/api/temperature/history?minutes=${minutes}&limit=${limit}`);
        if (!response.ok) throw new Error('Failed to load climate analytics');

        const payload = await response.json();
        const rows = Array.isArray(payload.data) ? payload.data : [];
        const normalizedRows = rows
            .filter((row) => Number.isFinite(parseTimestampMs(row.ts_utc)))
            .sort((a, b) => parseTimestampMs(a.ts_utc) - parseTimestampMs(b.ts_utc));

        if (normalizedRows.length > 0) {
            appState.climateSeries = normalizedRows;
        } else if (appState.latestTemperature && Number.isFinite(parseTimestampMs(appState.latestTemperature.ts_utc))) {
            appState.climateSeries = [appState.latestTemperature];
        }

        appState.knownSensors = new Set(getKnownSensorKeys());
        appState.lastClimateRefreshMs = now;

        renderTrendChart();
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

        const graphSelect = document.createElement('select');
        graphSelect.className = 'sensor-graph-select';
        graphSelect.dataset.sensorKey = sensorKey;
        graphSelect.innerHTML = [
            '<option value="yes">Graph: oui</option>',
            '<option value="no">Graph: non</option>',
        ].join('');
        graphSelect.value = cfg.graph === false ? 'no' : 'yes';

        row.appendChild(keyNode);
        row.appendChild(nameInput);
        row.appendChild(typeSelect);
        row.appendChild(graphSelect);
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

/* ============ History helpers ============ */
function getHistoryDateRange() {
    const fromInput = document.getElementById('from-date');
    const toInput = document.getElementById('to-date');
    const fromStr = appState.selectedFromDate || (fromInput ? fromInput.value : '') || '';
    const toStr = appState.selectedToDate || (toInput ? toInput.value : '') || '';
    return { fromStr, toStr };
}

function filterDailySeriesByRange(series, fromStr, toStr) {
    if (!fromStr || !toStr) return Array.isArray(series) ? series : [];
    return (Array.isArray(series) ? series : []).filter((row) => {
        const day = String(row.date_utc || '');
        return day >= fromStr && day <= toStr;
    });
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
    const isFresh = latest && typeof latest.is_fresh === 'boolean' ? latest.is_fresh : null;
    const hasLatest = Boolean(latest && latest.data);

    if (!status || typeof status !== 'object') {
        // Status can lag right after a service restart while /api/measurements/latest still responds.
        if (hasLatest && isFresh !== false) {
            indicator.classList.remove('error');
            text.textContent = 'Capteur connecte';
            return;
        }
        if (hasLatest) {
            indicator.classList.add('error');
            text.textContent = 'Donnees anciennes';
            return;
        }
        indicator.classList.add('error');
        text.textContent = 'API indisponible';
        return;
    }

    const sensor = String(status.sensor || '').toLowerCase();
    const server = String(status.server || '').toLowerCase();

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
        appState.selectedGraphChannels = getDefaultSelectedGraphChannels();
    }

    appState.selectedGraphChannels.forEach((key) => {
        if (!allKeys.has(key)) {
            appState.selectedGraphChannels.delete(key);
        }
    });

    if (appState.selectedGraphChannels.size === 0) {
        appState.selectedGraphChannels = getDefaultSelectedGraphChannels();
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
    appState.selectedFromDate = fromInput.value;
    appState.selectedToDate = toInput.value;

    applyButton.addEventListener('click', () => {
        appState.selectedFromDate = fromInput.value;
        appState.selectedToDate = toInput.value;
        appState.historyPage = 0;
        loadHistory();
    });

    prevButton.addEventListener('click', () => {
        if (appState.historyPage > 0) {
            appState.historyPage -= 1;
            renderHistoryTablePage();
        }
    });

    nextButton.addEventListener('click', () => {
        const totalPages = Math.max(1, Math.ceil(appState.historyTableRows.length / CONFIG.HISTORY_PAGE_SIZE));
        if (appState.historyPage < totalPages - 1) {
            appState.historyPage += 1;
            renderHistoryTablePage();
        }
    });
}

async function loadHistory() {
    try {
        if (!appState.dailyEnergySeries.length) {
            await loadHistorySummary(true);
        }

        const { fromStr, toStr } = getHistoryDateRange();
        const filtered = filterDailySeriesByRange(appState.dailyEnergySeries, fromStr, toStr);
        appState.historyTableRows = [...filtered].reverse();
        appState.historyPage = Math.min(appState.historyPage, Math.max(0, Math.ceil(appState.historyTableRows.length / CONFIG.HISTORY_PAGE_SIZE) - 1));
        renderHistoryTablePage();
    } catch (error) {
        console.error('Error loading history:', error);
        const tbody = document.getElementById('history-tbody');
        if (tbody) tbody.innerHTML = '<tr><td colspan="8" class="loading">Erreur</td></tr>';
    }
}

function renderHistoryTablePage() {
    const tbody = document.getElementById('history-tbody');
    const pageInfo = document.getElementById('page-info');
    if (!tbody) return;

    const rows = appState.historyTableRows || [];
    const pageSize = CONFIG.HISTORY_PAGE_SIZE;
    const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
    const page = Math.min(appState.historyPage, totalPages - 1);
    const slice = rows.slice(page * pageSize, (page + 1) * pageSize);

    tbody.innerHTML = '';
    if (slice.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="loading">Aucune donnee sur cette periode</td></tr>';
        if (pageInfo) pageInfo.textContent = '0 jour(s)';
        return;
    }

    slice.forEach((dayRow) => {
        const metrics = computeEnergyMetrics(dayRow.c1_net_kwh, dayRow.pv_production_kwh);
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${fmtDate(dayRow.date_utc)}</td>
            <td>${metrics.c1NetKwh.toFixed(3)}</td>
            <td>${metrics.a2ProdKwh.toFixed(3)}</td>
            <td>${metrics.consoReelle.toFixed(3)}</td>
            <td>${metrics.consoFact.toFixed(3)}</td>
            <td>${metrics.surplus.toFixed(3)}</td>
            <td>${metrics.autoconso.toFixed(3)}</td>
            <td>${fmtPct(metrics.tauxAutoconso)}</td>
        `;
        tbody.appendChild(row);
    });

    if (pageInfo) {
        pageInfo.textContent = `Page ${page + 1}/${totalPages} — ${rows.length} jour(s)`;
    }
}

async function loadHistorySummary(force = false) {
    const now = Date.now();
    if (!force && now - appState.lastHistorySummaryRefreshMs < CONFIG.HISTORY_SUMMARY_REFRESH_MS) {
        return;
    }

    try {
        const response = await fetch(`${CONFIG.API_BASE}/api/history/daily-summary`);
        if (!response.ok) throw new Error('Failed to load history daily summary');
        const payload = await response.json();
        appState.dailyEnergySeries = Array.isArray(payload.daily_energy_series) ? payload.daily_energy_series : [];
        renderHistorySummary(payload);
        appState.lastHistorySummaryRefreshMs = now;
        if (appState.currentPage === 'history') {
            loadHistory();
        }
    } catch (error) {
        console.error('Error loading daily history summary:', error);
    }
}

function setTextById(id, text) {
    const node = document.getElementById(id);
    if (node) node.textContent = text;
}

function fmtDate(dayIso) {
    if (!dayIso) return '--';
    const ts = new Date(`${dayIso}T00:00:00Z`);
    if (!Number.isFinite(ts.getTime())) return String(dayIso);
    return ts.toLocaleDateString('fr-FR');
}

function renderHistorySummary(payload) {
    setTextById('history-month-avg', fmtKwh(Number(payload && payload.current_month_average_kwh), 3));

    const series = appState.dailyEnergySeries.length
        ? appState.dailyEnergySeries
        : (Array.isArray(payload && payload.daily_energy_series) ? payload.daily_energy_series : []);

    const now = new Date();
    const prevMonthDate = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    const prevMonthKey = monthKeyFromDate(prevMonthDate);
    const prevYearMonthKey = `${prevMonthDate.getFullYear() - 1}-${String(prevMonthDate.getMonth() + 1).padStart(2, '0')}`;

    const prevMonthBill = sumMonthBillEur(series, prevMonthKey);
    const prevYearSameMonthBill = sumMonthBillEur(series, prevYearMonthKey);

    setTextById('history-prev-month-bill', `${prevMonthBill.toFixed(2)} EUR`);
    setTextById('history-prev-month-label', formatMonthLabel(prevMonthKey));

    if (prevYearSameMonthBill > 0) {
        const pct = ((prevMonthBill - prevYearSameMonthBill) / prevYearSameMonthBill) * 100;
        const sign = pct >= 0 ? '+' : '';
        setTextById('history-bill-yoy-pct', `${sign}${pct.toFixed(1)} %`);
        setTextById(
            'history-bill-yoy-ref',
            `${formatMonthLabel(prevYearMonthKey)}: ${prevYearSameMonthBill.toFixed(2)} EUR`,
        );
    } else {
        setTextById('history-bill-yoy-pct', '--');
        setTextById('history-bill-yoy-ref', 'Reference indisponible');
    }

    const monthlyRows = Array.isArray(payload && payload.monthly_consumption_last_12)
        ? payload.monthly_consumption_last_12
        : [];
    const monthlyPv = Array.isArray(payload && payload.monthly_pv_production_last_12)
        ? payload.monthly_pv_production_last_12
        : [];
    renderHistoryYearlyChart(monthlyRows, monthlyPv);
}

function renderHistoryYearlyChart(rows, pvRows = []) {
    if (typeof Chart === 'undefined') return;
    const canvas = document.getElementById('history-yearly-chart');
    if (!canvas) return;

    const labels = rows.map((item) => {
        const raw = String(item.month || '');
        const [year, month] = raw.split('-');
        if (!year || !month) return raw;
        return `${month}/${year.slice(-2)}`;
    });
    const importData = rows.map((item) => {
        const value = Number(item.consumption_kwh);
        return Number.isFinite(value) ? value : 0;
    });
    const pvByMonth = new Map(
        (Array.isArray(pvRows) ? pvRows : []).map((item) => [String(item.month || ''), Number(item.pv_production_kwh)]),
    );
    const pvData = rows.map((item) => {
        const value = pvByMonth.get(String(item.month || ''));
        return Number.isFinite(value) ? value : 0;
    });

    const ctx = canvas.getContext('2d');
    if (appState.historySummaryChart) {
        appState.historySummaryChart.destroy();
    }

    appState.historySummaryChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [
                {
                    label: 'Prélèvement réseau C1 (kWh)',
                    data: importData,
                    backgroundColor: 'rgba(26, 95, 122, 0.75)',
                    borderColor: 'rgba(13, 61, 82, 1)',
                    borderWidth: 1,
                },
                {
                    label: 'Production PV A2 (kWh)',
                    data: pvData,
                    backgroundColor: 'rgba(234, 179, 8, 0.65)',
                    borderColor: 'rgba(161, 98, 7, 1)',
                    borderWidth: 1,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: true },
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'kWh',
                    },
                },
            },
        },
    });
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
        CONFIG.REFRESH_INTERVAL = settings.refreshInterval || 5000;
        CONFIG.CHART_HOURS = settings.chartHours || 24;
        CONFIG.BUY_PRICE_KWH = settings.buyPriceKwh ?? 0.25;
        CONFIG.SURPLUS_PRICE_KWH = settings.surplusPriceKwh ?? 0;
        CONFIG.SELL_PRICE_KWH = settings.sellPriceKwh ?? 0.011;
        CONFIG.HAS_RESALE_CONTRACT = Boolean(settings.hasResaleContract);
        CONFIG.UNIFIED_CHART_MODE = settings.unifiedChartMode === 'temp_humidity' ? 'temp_humidity' : 'power_temp';
        if (settings.graphSeries && typeof settings.graphSeries === 'object') {
            CONFIG.GRAPH_SERIES = {
                consumption: settings.graphSeries.consumption !== false,
                temperature: settings.graphSeries.temperature !== false,
                humidity: settings.graphSeries.humidity !== false,
            };
        }

        if (Array.isArray(settings.selectedGraphChannels)) {
            appState.selectedGraphChannels = new Set(
                settings.selectedGraphChannels
                    .map((v) => String(v || '').trim())
                    .filter((v) => v.length > 0)
            );
        }
        appState.unifiedHiddenDatasets =
            settings.unifiedHiddenDatasets && typeof settings.unifiedHiddenDatasets === 'object'
                ? settings.unifiedHiddenDatasets
                : {};

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
                    graph: typeof row.graph === 'boolean' ? row.graph : true,
                };
            });
            CONFIG.SENSORS = mergedSensors;
        }

        const refreshInput = document.getElementById('refresh-interval');
        const chartHoursInput = document.getElementById('chart-hours');
        const buyInput = document.getElementById('buy-price-kwh');
        const surplusInput = document.getElementById('surplus-price-kwh');
        const sellInput = document.getElementById('sell-price-kwh');
        const resaleInput = document.getElementById('has-resale-contract');
        if (refreshInput) refreshInput.value = CONFIG.REFRESH_INTERVAL / 1000;
        if (chartHoursInput) chartHoursInput.value = CONFIG.CHART_HOURS;
        if (buyInput) buyInput.value = CONFIG.BUY_PRICE_KWH;
        if (surplusInput) surplusInput.value = CONFIG.SURPLUS_PRICE_KWH;
        if (sellInput) sellInput.value = CONFIG.SELL_PRICE_KWH;
        if (resaleInput) resaleInput.checked = CONFIG.HAS_RESALE_CONTRACT;
    } else {
        const buyInput = document.getElementById('buy-price-kwh');
        const surplusInput = document.getElementById('surplus-price-kwh');
        const sellInput = document.getElementById('sell-price-kwh');
        const resaleInput = document.getElementById('has-resale-contract');
        if (buyInput) buyInput.value = CONFIG.BUY_PRICE_KWH;
        if (surplusInput) surplusInput.value = CONFIG.SURPLUS_PRICE_KWH;
        if (sellInput) sellInput.value = CONFIG.SELL_PRICE_KWH;
        if (resaleInput) resaleInput.checked = CONFIG.HAS_RESALE_CONTRACT;
    }

    if (!appState.selectedGraphChannels || appState.selectedGraphChannels.size === 0) {
        appState.selectedGraphChannels = getDefaultSelectedGraphChannels();
    }

    applyChannelSettingsToForm();
    applyGraphSeriesControlValues();
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
    const surplusInput = document.getElementById('surplus-price-kwh');
    const sellInput = document.getElementById('sell-price-kwh');
    const resaleInput = document.getElementById('has-resale-contract');

    if (!refreshInput || !chartHoursInput || !buyInput || !surplusInput || !sellInput || !resaleInput) {
        return;
    }

    const refreshInterval = parseInt(refreshInput.value, 10) * 1000;
    const chartHours = parseInt(chartHoursInput.value, 10);
    const buyPriceKwh = parseFloat(buyInput.value);
    const surplusPriceKwh = parseFloat(surplusInput.value);
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
        const graphSelect = document.querySelector(`.sensor-graph-select[data-sensor-key="${sensorKey}"]`);
        const typeValue = typeSelect ? typeSelect.value : 'interieur';
        const graphValue = graphSelect ? graphSelect.value : 'yes';
        sensors[sensorKey] = {
            name: String(input.value || '').trim(),
            type: typeValue === 'exterieur' ? 'exterieur' : 'interieur',
            graph: graphValue !== 'no',
        };
    });

    CONFIG.REFRESH_INTERVAL = Number.isFinite(refreshInterval) ? Math.max(1000, refreshInterval) : 3000;
    CONFIG.CHART_HOURS = Number.isFinite(chartHours) ? Math.max(1, Math.min(720, chartHours)) : 24;
    CONFIG.BUY_PRICE_KWH = Number.isFinite(buyPriceKwh) ? Math.max(0, buyPriceKwh) : 0.25;
    CONFIG.SURPLUS_PRICE_KWH = Number.isFinite(surplusPriceKwh) ? Math.max(0, surplusPriceKwh) : 0;
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
            surplusPriceKwh: CONFIG.SURPLUS_PRICE_KWH,
            sellPriceKwh: CONFIG.SELL_PRICE_KWH,
            hasResaleContract: CONFIG.HAS_RESALE_CONTRACT,
            unifiedChartMode: CONFIG.UNIFIED_CHART_MODE,
            graphSeries: CONFIG.GRAPH_SERIES,
            selectedGraphChannels: Array.from(appState.selectedGraphChannels),
            unifiedHiddenDatasets: appState.unifiedHiddenDatasets,
            channels: CONFIG.CHANNELS,
            sensors: CONFIG.SENSORS,
        })
    );

    refreshChartFilters();
    renderSensorSettingsRows();
    updateChannelInstantCards();
    updateTemperatureCard();
    renderTrendChart();
    updateEnergyDashboard();
    if (appState.currentPage === 'history') {
        loadHistorySummary(true);
    }

    alert('Parametres enregistres');
}

// Auto-refresh footer time display every second
setInterval(() => {
    const now = new Date();
    const time = now.toLocaleTimeString('fr-FR');
    const footerTime = document.getElementById('footer-time');
    if (footerTime) footerTime.textContent = time;
}, 1000);
