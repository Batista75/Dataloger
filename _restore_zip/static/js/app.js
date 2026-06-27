// Configuration
const CONFIG = {
    API_BASE: '',
    REFRESH_INTERVAL: 3000,
    CHART_HOURS: 24,
    HISTORY_LIMIT: 100,
    BUY_PRICE_KWH: 0.25,
    SELL_PRICE_KWH: 0.011,
    HAS_RESALE_CONTRACT: false,
    CHANNELS: {
        a1: { name: 'Canal A1', type: 'unused' },
        b1: { name: 'Canal B1', type: 'unused' },
        c1: { name: 'Canal C1', type: 'edf_total' },
        a2: { name: 'Canal A2', type: 'generator' },
        b2: { name: 'Canal B2', type: 'consumption' },
        c2: { name: 'Canal C2', type: 'consumption' },
    },
};

// State
let appState = {
    currentPage: 'dashboard',
    measurements: [],
    chartInstance: null,
    lastUpdate: null,
    historyPage: 0,
    selectedFromDate: null,
    selectedToDate: null,
    selectedChartChannel: 'total',
};

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    initializeNavigation();
    initializeDatepickers();
    initializeChartContainer();
    initializeChartSelector();
    loadSettings();
    updateAllData();
    setInterval(updateAllData, CONFIG.REFRESH_INTERVAL);
});

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
    // Hide all pages
    document.querySelectorAll('.page').forEach((p) => {
        p.classList.remove('active');
    });

    // Deactivate all tabs
    document.querySelectorAll('.nav-tab').forEach((tab) => {
        tab.classList.remove('active');
    });

    // Show selected page
    document.getElementById(page).classList.add('active');

    // Activate selected tab
    document.querySelector(`[data-page="${page}"]`).classList.add('active');

    appState.currentPage = page;

    // Load data specific to page
    if (page === 'history') {
        loadHistory();
    }
}

/* ============ Data Loading ============ */
async function updateAllData() {
    try {
        const [statusRes, latestRes] = await Promise.all([
            fetch(`${CONFIG.API_BASE}/api/status`),
            fetch(`${CONFIG.API_BASE}/api/measurements/latest`),
        ]);

        if (!statusRes.ok || !latestRes.ok) {
            updateStatus('error');
            return;
        }

        const status = await statusRes.json();
        const latest = await latestRes.json();

        updateStatus(status, latest);
        updateDashboard(latest.data, status);
        updateSystemInfo(status);
        updateFooter();

        if (appState.currentPage === 'dashboard') {
            loadTrendChart();
        }
    } catch (error) {
        console.error('Error fetching data:', error);
        updateStatus(null, null);
    }
}

async function loadTrendChart() {
    try {
        const response = await fetch(
            `${CONFIG.API_BASE}/api/measurements?minutes=${CONFIG.CHART_HOURS * 60}`
        );
        if (!response.ok) throw new Error('Failed to load chart data');

        const data = await response.json();
        const measurements = data.data;

        if (measurements.length === 0) return;

        // Prepare chart data
        const labels = measurements.map((m) => {
            const date = new Date(m.ts_utc);
            return date.toLocaleTimeString('fr-FR', {
                hour: '2-digit',
                minute: '2-digit',
            });
        });

        const productionField = appState.selectedChartChannel === 'total'
            ? 'total_production_kwh'
            : `${appState.selectedChartChannel}_production_kwh`;
        const consumptionField = appState.selectedChartChannel === 'total'
            ? 'total_consumption_kwh'
            : `${appState.selectedChartChannel}_consumption_kwh`;

        const productionData = measurements.map((m) => m[productionField] || 0);
        const consumptionData = measurements.map((m) => m[consumptionField] || 0);
        const channelLabel = getChartLabelForSelection();

        // Update or create chart
        const ctx = document.getElementById('trend-chart').getContext('2d');

        if (appState.chartInstance) {
            appState.chartInstance.destroy();
        }

        appState.chartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: `Consommation ${channelLabel} (kWh)`,
                        data: consumptionData,
                        borderColor: '#dc2626',
                        backgroundColor: 'rgba(220, 38, 38, 0.1)',
                        borderWidth: 2,
                        tension: 0.4,
                        fill: true,
                        yAxisID: 'y',
                    },
                    {
                        label: `Production ${channelLabel} (kWh)`,
                        data: productionData,
                        borderColor: '#10b981',
                        backgroundColor: 'rgba(16, 185, 129, 0.1)',
                        borderWidth: 2,
                        tension: 0.4,
                        fill: true,
                        yAxisID: 'y',
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                interaction: {
                    mode: 'index',
                    intersect: false,
                },
                plugins: {
                    legend: {
                        position: 'top',
                    },
                },
                scales: {
                    y: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        title: {
                            display: true,
                            text: `Consommation / Production ${channelLabel} (kWh)`,
                        },
                    },
                },
            },
        });
    } catch (error) {
        console.error('Error loading chart:', error);
    }
}

function initializeChartSelector() {
    const selector = document.getElementById('chart-channel-select');
    if (!selector) return;

    selector.addEventListener('change', () => {
        appState.selectedChartChannel = selector.value;
        if (appState.currentPage === 'dashboard') {
            loadTrendChart();
        }
    });
}

function refreshChartSelectorOptions() {
    const selector = document.getElementById('chart-channel-select');
    if (!selector) return;

    const previous = appState.selectedChartChannel;
    selector.innerHTML = '';

    const totalOption = document.createElement('option');
    totalOption.value = 'total';
    totalOption.textContent = 'Total';
    selector.appendChild(totalOption);

    const keys = ['a1', 'b1', 'c1', 'a2', 'b2', 'c2'];
    keys.forEach((k) => {
        const cfg = CONFIG.CHANNELS[k];
        if (!cfg || cfg.type === 'unused') return;
        const option = document.createElement('option');
        option.value = k;
        option.textContent = cfg.name;
        selector.appendChild(option);
    });

    const hasPrevious = Array.from(selector.options).some((o) => o.value === previous);
    appState.selectedChartChannel = hasPrevious ? previous : 'total';
    selector.value = appState.selectedChartChannel;
}

function getChartLabelForSelection() {
    if (appState.selectedChartChannel === 'total') {
        return 'Total';
    }
    const cfg = CONFIG.CHANNELS[appState.selectedChartChannel];
    return cfg ? cfg.name : appState.selectedChartChannel.toUpperCase();
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
            // Default: last 7 days
            const now = new Date();
            const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
            const from = sevenDaysAgo.toISOString();
            const to = now.toISOString();

            url = `${CONFIG.API_BASE}/api/measurements?from_ts_utc=${from}&to_ts_utc=${to}&limit=${CONFIG.HISTORY_LIMIT}`;
        }

        const response = await fetch(url);
        if (!response.ok) throw new Error('Failed to load history');

        const data = await response.json();
        const measurements = data.data.reverse();

        // Populate table
        const tbody = document.getElementById('history-tbody');
        tbody.innerHTML = '';

        if (measurements.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="loading">Aucune donnée</td></tr>';
            return;
        }

        measurements.forEach((m) => {
            const row = document.createElement('tr');
            const date = new Date(m.ts_utc);
            const time = date.toLocaleTimeString('fr-FR');
            const prod = m.total_production_kwh || 0;
            const cons = m.total_consumption_kwh || 0;
            const voltage = m.voltage_v || 0;
            const pf = m.power_factor || 0;

            row.innerHTML = `
                <td>${time}</td>
                <td>${prod.toFixed(3)}</td>
                <td>${cons.toFixed(3)}</td>
                <td>${voltage.toFixed(1)}</td>
                <td>${pf.toFixed(3)}</td>
            `;
            tbody.appendChild(row);
        });

        document.getElementById('page-info').textContent = `${measurements.length} mesures affichées`;
    } catch (error) {
        console.error('Error loading history:', error);
        const tbody = document.getElementById('history-tbody');
        tbody.innerHTML = '<tr><td colspan="5" class="loading">Erreur</td></tr>';
    }
}

/* ============ Dashboard Updates ============ */
function updateDashboard(measurement, status) {
    if (!measurement) return;

    // Update summary totals
    const totalProd = measurement.total_production_kwh || 0;
    const totalCons = measurement.total_consumption_kwh || 0;
    const voltage = measurement.voltage_v || 0;
    const frequency = measurement.frequency_hz || 0;
    const powerFactor = measurement.power_factor || 0;

    document.getElementById('total-production').textContent = totalProd.toFixed(3) + ' kWh';
    document.getElementById('total-consumption').textContent = totalCons.toFixed(3) + ' kWh';
    document.getElementById('voltage-value').textContent = voltage.toFixed(1) + ' V';
    document.getElementById('frequency-value').textContent = frequency.toFixed(2) + ' Hz';
    document.getElementById('power-factor-value').textContent = powerFactor.toFixed(3);

    // Update 6 channel cards
    const channels = [
        { prefix: 'a1', prod: measurement.a1_production_kwh, cons: measurement.a1_consumption_kwh },
        { prefix: 'b1', prod: measurement.b1_production_kwh, cons: measurement.b1_consumption_kwh },
        { prefix: 'c1', prod: measurement.c1_production_kwh, cons: measurement.c1_consumption_kwh },
        { prefix: 'a2', prod: measurement.a2_production_kwh, cons: measurement.a2_consumption_kwh },
        { prefix: 'b2', prod: measurement.b2_production_kwh, cons: measurement.b2_consumption_kwh },
        { prefix: 'c2', prod: measurement.c2_production_kwh, cons: measurement.c2_consumption_kwh },
    ];

    channels.forEach((ch) => {
        const prodVal = ch.prod || 0;
        const consVal = ch.cons || 0;
        const channelCfg = CONFIG.CHANNELS[ch.prefix] || { name: `Canal ${ch.prefix.toUpperCase()}`, type: 'consumption' };
        
        document.getElementById(`${ch.prefix}-prod`).textContent = prodVal.toFixed(3) + ' kWh';
        document.getElementById(`${ch.prefix}-cons`).textContent = consVal.toFixed(3) + ' kWh';
        document.getElementById(`${ch.prefix}-name`).textContent = channelCfg.name;

        const typeNode = document.getElementById(`${ch.prefix}-type`);
        if (typeNode) {
            typeNode.classList.remove('consumption', 'generator', 'mixed', 'edf', 'unused');
            if (channelCfg.type === 'generator') {
                typeNode.textContent = 'Type: générateur';
                typeNode.classList.add('generator');
            } else if (channelCfg.type === 'edf_total') {
                typeNode.textContent = 'Type: consommation totale EDF';
                typeNode.classList.add('edf');
            } else if (channelCfg.type === 'unused') {
                typeNode.textContent = 'Type: non utilisé';
                typeNode.classList.add('unused');
            } else if (prodVal > 0 && consVal > 0) {
                typeNode.textContent = 'Type: mixte';
                typeNode.classList.add('mixed');
            } else {
                typeNode.textContent = 'Type: consommation';
                typeNode.classList.add('consumption');
            }
        }
    });

    // Economic estimate rules
    const netGridKwh = totalCons - totalProd;
    const buyPrice = Number(CONFIG.BUY_PRICE_KWH) || 0;
    const sellPrice = Number(CONFIG.SELL_PRICE_KWH) || 0.011;
    const hasResale = Boolean(CONFIG.HAS_RESALE_CONTRACT);

    let estimatedCostEur = 0;
    let feedInValueEur = 0;
    let note = '';

    if (netGridKwh >= 0) {
        estimatedCostEur = netGridKwh * buyPrice;
        note = `Facture estimée avec tarif achat ${buyPrice.toFixed(3)} EUR/kWh.`;
    } else {
        const exportedKwh = Math.abs(netGridKwh);
        if (hasResale) {
            feedInValueEur = exportedKwh * sellPrice;
            note = `Injection valorisée à ${sellPrice.toFixed(3)} EUR/kWh (contrat de revente actif).`;
        } else {
            note = 'Injection détectée (valeur négative EDF), hors calcul facture sans contrat de revente.';
        }
    }

    document.getElementById('billing-net-grid').textContent = `${netGridKwh.toFixed(3)} kWh`;
    document.getElementById('billing-estimated-cost').textContent = `${estimatedCostEur.toFixed(3)} EUR`;
    document.getElementById('billing-feed-in-value').textContent = `${feedInValueEur.toFixed(3)} EUR`;
    document.getElementById('billing-note').textContent = note;

    // Update last update time
    const date = new Date(measurement.ts_utc);
    const time = date.toLocaleTimeString('fr-FR');
    document.getElementById('last-update').textContent = time;

    appState.lastUpdate = measurement.ts_utc;
}

function updateSystemInfo(status) {
    document.getElementById('sensor-state').textContent = status.sensor || 'Inconnu';
    document.getElementById('em06-mode').textContent = status.em06_mode || 'Inconnu';

    // System info (settings page)
    document.getElementById('sys-server').textContent = status.server || 'Inconnu';
    document.getElementById('sys-sensor').textContent = status.sensor || 'Inconnu';
    document.getElementById('sys-mode').textContent = status.em06_mode || 'Inconnu';

    const lastTs = status.last_sample_ts_utc;
    if (lastTs) {
        const date = new Date(lastTs);
        document.getElementById('sys-last-ts').textContent = date.toLocaleString('fr-FR');
    }

    // Show error if present
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

    if (!status) {
        indicator.classList.add('error');
        text.textContent = 'API indisponible';
        return;
    }

    const sensor = String(status.sensor || '').toLowerCase();
    const isFresh = latest && typeof latest.is_fresh === 'boolean' ? latest.is_fresh : null;

    if (sensor === 'connected' && isFresh !== false) {
        indicator.classList.remove('error');
        text.textContent = 'Capteur connecté';
        return;
    }

    if (sensor === 'connected' && isFresh === false) {
        indicator.classList.add('error');
        text.textContent = 'Données anciennes';
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
        text.textContent = 'Statut inconnu';
    }
}

function updateFooter() {
    const now = new Date();
    const time = now.toLocaleTimeString('fr-FR');
    document.getElementById('footer-time').textContent = time;
    document.getElementById('footer-interval').textContent = CONFIG.REFRESH_INTERVAL / 1000;
}

/* ============ Date Pickers ============ */
function initializeDatepickers() {
    const fromInput = document.getElementById('from-date');
    const toInput = document.getElementById('to-date');

    // Set default dates (last 7 days)
    const now = new Date();
    const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);

    toInput.valueAsDate = now;
    fromInput.valueAsDate = sevenDaysAgo;

    // Apply filter button
    document.getElementById('apply-filter').addEventListener('click', () => {
        appState.selectedFromDate = fromInput.value;
        appState.selectedToDate = toInput.value;
        appState.historyPage = 0;
        loadHistory();
    });

    // Pagination
    document.getElementById('prev-page').addEventListener('click', () => {
        if (appState.historyPage > 0) {
            appState.historyPage--;
            loadHistory();
        }
    });

    document.getElementById('next-page').addEventListener('click', () => {
        appState.historyPage++;
        loadHistory();
    });
}

/* ============ Chart Container ============ */
function initializeChartContainer() {
    const container = document.querySelector('.chart-container');
    if (!container) return;

    // Ensure canvas exists
    if (!document.getElementById('trend-chart')) {
        const canvas = document.createElement('canvas');
        canvas.id = 'trend-chart';
        container.appendChild(canvas);
    }
}

/* ============ Settings ============ */
function loadSettings() {
    const stored = localStorage.getItem('datalogueur-settings');
    if (stored) {
        const settings = JSON.parse(stored);
        CONFIG.REFRESH_INTERVAL = settings.refreshInterval || 3000;
        CONFIG.CHART_HOURS = settings.chartHours || 24;
        CONFIG.BUY_PRICE_KWH = settings.buyPriceKwh ?? 0.25;
        CONFIG.SELL_PRICE_KWH = settings.sellPriceKwh ?? 0.011;
        CONFIG.HAS_RESALE_CONTRACT = Boolean(settings.hasResaleContract);
        CONFIG.CHANNELS = settings.channels || CONFIG.CHANNELS;

        document.getElementById('refresh-interval').value = CONFIG.REFRESH_INTERVAL / 1000;
        document.getElementById('chart-hours').value = CONFIG.CHART_HOURS;
        document.getElementById('buy-price-kwh').value = CONFIG.BUY_PRICE_KWH;
        document.getElementById('sell-price-kwh').value = CONFIG.SELL_PRICE_KWH;
        document.getElementById('has-resale-contract').checked = CONFIG.HAS_RESALE_CONTRACT;
    } else {
        document.getElementById('buy-price-kwh').value = CONFIG.BUY_PRICE_KWH;
        document.getElementById('sell-price-kwh').value = CONFIG.SELL_PRICE_KWH;
        document.getElementById('has-resale-contract').checked = CONFIG.HAS_RESALE_CONTRACT;
    }

    applyChannelSettingsToForm();
    refreshChartSelectorOptions();

    document.getElementById('save-settings').addEventListener('click', saveSettings);
}

function applyChannelSettingsToForm() {
    const keys = ['a1', 'b1', 'c1', 'a2', 'b2', 'c2'];
    keys.forEach((k) => {
        const cfg = CONFIG.CHANNELS[k] || { name: `Canal ${k.toUpperCase()}`, type: 'consumption' };
        document.getElementById(`cfg-${k}-name`).value = cfg.name;
        document.getElementById(`cfg-${k}-type`).value = cfg.type;
    });
}

function saveSettings() {
    const refreshInterval = parseInt(document.getElementById('refresh-interval').value) * 1000;
    const chartHours = parseInt(document.getElementById('chart-hours').value);
    const buyPriceKwh = parseFloat(document.getElementById('buy-price-kwh').value);
    const sellPriceKwh = parseFloat(document.getElementById('sell-price-kwh').value);
    const hasResaleContract = document.getElementById('has-resale-contract').checked;
    const keys = ['a1', 'b1', 'c1', 'a2', 'b2', 'c2'];

    const channels = {};
    keys.forEach((k) => {
        const name = document.getElementById(`cfg-${k}-name`).value.trim();
        const type = document.getElementById(`cfg-${k}-type`).value;
        channels[k] = {
            name: name || `Canal ${k.toUpperCase()}`,
            type,
        };
    });

    CONFIG.REFRESH_INTERVAL = refreshInterval;
    CONFIG.CHART_HOURS = chartHours;
    CONFIG.BUY_PRICE_KWH = Number.isFinite(buyPriceKwh) ? Math.max(0, buyPriceKwh) : 0.25;
    CONFIG.SELL_PRICE_KWH = Number.isFinite(sellPriceKwh) ? Math.max(0, sellPriceKwh) : 0.011;
    CONFIG.HAS_RESALE_CONTRACT = hasResaleContract;
    CONFIG.CHANNELS = channels;
    refreshChartSelectorOptions();

    localStorage.setItem(
        'datalogueur-settings',
        JSON.stringify({
            refreshInterval,
            chartHours,
            buyPriceKwh: CONFIG.BUY_PRICE_KWH,
            sellPriceKwh: CONFIG.SELL_PRICE_KWH,
            hasResaleContract: CONFIG.HAS_RESALE_CONTRACT,
            channels: CONFIG.CHANNELS,
        })
    );

    alert('Paramètres enregistrés');

    if (appState.currentPage === 'dashboard') {
        loadTrendChart();
    }
}

// Auto-refresh footer time display every second
setInterval(() => {
    const now = new Date();
    const time = now.toLocaleTimeString('fr-FR');
    document.getElementById('footer-time').textContent = time;
}, 1000);
