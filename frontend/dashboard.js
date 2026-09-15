// ============================================
// DASHBOARD - ESTADÍSTICAS Y GRÁFICOS
// ============================================

let historyChart = null;
let districtChart = null;

// ============================================
// INICIALIZAR GRÁFICOS
// ============================================

function initCharts() {
    console.log('📊 Inicializando gráficos...');

    // Verificar que Chart.js está disponible
    if (typeof Chart === 'undefined') {
        console.warn('⚠️ Chart.js no está cargado. Asegúrate de incluir la librería.');
        return;
    }

    // --- Gráfico de historial de precios (línea) ---
    const ctx = document.getElementById('history-chart');
    if (!ctx) {
        console.warn('⚠️ No se encontró el canvas #history-chart');
        return;
    }

    if (historyChart) {
        historyChart.destroy();
        historyChart = null;
    }

    historyChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Precio Predicho (S/)',
                data: [],
                borderColor: '#6c5ce7',
                backgroundColor: 'rgba(108, 92, 231, 0.1)',
                fill: true,
                tension: 0.4,
                pointBackgroundColor: '#6c5ce7',
                pointBorderColor: '#fff',
                pointBorderWidth: 2,
                pointRadius: 4,
                pointHoverRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    display: true,
                    labels: {
                        font: { size: 11 },
                        padding: 10
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return '$ ' + context.parsed.y.toLocaleString('en-US', { maximumFractionDigits: 0 });
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: function(value) {
                            return '$ ' + value.toLocaleString('en-US', { maximumFractionDigits: 0 });
                        }
                    }
                },
                x: {
                    ticks: {
                        maxRotation: 45,
                        minRotation: 30,
                        font: { size: 9 }
                    }
                }
            }
        }
    });

    console.log('✅ Gráfico de historial inicializado');

    // --- Gráfico de precios por distrito (barra) ---
    const ctx2 = document.getElementById('district-chart');
    if (!ctx2) {
        console.warn('⚠️ No se encontró el canvas #district-chart');
        return;
    }

    if (districtChart) {
        districtChart.destroy();
        districtChart = null;
    }

    districtChart = new Chart(ctx2, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [{
                label: 'Precio Promedio (S/)',
                data: [],
                backgroundColor: [
                    'rgba(108, 92, 231, 0.8)',
                    'rgba(0, 184, 148, 0.8)',
                    'rgba(253, 203, 110, 0.8)',
                    'rgba(225, 112, 85, 0.8)',
                    'rgba(116, 185, 255, 0.8)',
                    'rgba(162, 155, 254, 0.8)',
                    'rgba(85, 239, 196, 0.8)',
                    'rgba(253, 121, 168, 0.8)'
                ],
                borderColor: [
                    '#6c5ce7',
                    '#00b894',
                    '#fdcb6e',
                    '#e17055',
                    '#74b9ff',
                    '#a29bfe',
                    '#55efc4',
                    '#fd79a8'
                ],
                borderWidth: 2,
                borderRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return '$ ' + context.parsed.y.toLocaleString('en-US', { maximumFractionDigits: 0 });
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: function(value) {
                            return '$ ' + value.toLocaleString('en-US', { maximumFractionDigits: 0 });
                        }
                    }
                }
            }
        }
    });

    console.log('✅ Gráfico de distritos inicializado');
}

// ============================================
// CARGAR DASHBOARD
// ============================================

async function loadDashboard() {
    console.log('📊 Cargando dashboard...');

    // Obtener token desde localStorage
    const token = localStorage.getItem('authToken');
    if (!token) {
        console.warn('⚠️ No hay token de autenticación');
        updateStatsEmpty();
        showEmptyCharts();
        return;
    }

    try {
        // 1. Cargar estadísticas
        const statsResponse = await fetch(`${API_URL}/predictions/stats/me`, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            }
        });

        if (!statsResponse.ok) {
            if (statsResponse.status === 401) {
                // Se delega en el manejador central: limpia también las
                // variables de sesión de script.js, no solo localStorage.
                if (typeof window.manejarSesionExpirada === 'function') {
                    window.manejarSesionExpirada();
                } else {
                    localStorage.removeItem('authToken');
                    localStorage.removeItem('currentUser');
                    if (typeof showUnauthenticated === 'function') {
                        showUnauthenticated();
                    }
                }
                return;
            }
            throw new Error(`Error ${statsResponse.status}: ${statsResponse.statusText}`);
        }

        const stats = await statsResponse.json();
        console.log('📊 Estadísticas recibidas:', stats);

        // Actualizar tarjetas de estadísticas
        updateStats(stats);

        // 2. Cargar historial para gráficos
        await loadHistoryForCharts();

        // 3. Actualizar barrios desde stats si hay datos
        if (stats.top_neighborhoods && stats.top_neighborhoods.length > 0) {
            updateNeighborhoodData(stats.top_neighborhoods);
        }

        console.log('✅ Dashboard cargado correctamente');

    } catch (error) {
        console.error('❌ Error cargando dashboard:', error);
        updateStatsEmpty();
        showEmptyCharts();
    }
}

// ============================================
//  ACTUALIZAR ESTADÍSTICAS
// ============================================

function updateStats(stats) {
    const totalEl = document.getElementById('stat-total');
    const avgEl = document.getElementById('stat-avg-price');
    const maxEl = document.getElementById('stat-max-price');
    const minEl = document.getElementById('stat-min-price');

    if (totalEl) totalEl.textContent = stats.total_predictions || 0;

    const avg = stats.avg_predicted_price || 0;
    if (avgEl) avgEl.textContent = formatearPrecio(avg);

    const max = stats.max_predicted_price || 0;
    if (maxEl) maxEl.textContent = formatearPrecio(max);

    const min = stats.min_predicted_price || 0;
    if (minEl) minEl.textContent = formatearPrecio(min);
}

function updateStatsEmpty() {
    const totalEl = document.getElementById('stat-total');
    const avgEl = document.getElementById('stat-avg-price');
    const maxEl = document.getElementById('stat-max-price');
    const minEl = document.getElementById('stat-min-price');

    if (totalEl) totalEl.textContent = '0';
    if (avgEl) avgEl.textContent = formatearPrecio(0);
    if (maxEl) maxEl.textContent = formatearPrecio(0);
    if (minEl) minEl.textContent = formatearPrecio(0);
}

// ============================================
//  CARGAR HISTORIAL PARA GRÁFICOS
//  ============================================

async function loadHistoryForCharts() {
    const token = localStorage.getItem('authToken');
    if (!token) {
        console.warn('⚠️ No hay token para cargar historial');
        showEmptyCharts();
        return;
    }

    try {
        const response = await fetch(`${API_URL}/predictions/history?limit=30`, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            if (response.status === 401) {
                if (typeof window.manejarSesionExpirada === 'function') {
                    window.manejarSesionExpirada();
                }
                return;
            }
            throw new Error(`Error ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        console.log('📊 Historial recibido:', data.items?.length || 0, 'registros');

        if (data.items && data.items.length > 0) {
            // ✅ CORREGIDO: Usar updateHistoryChart en lugar de updateCharts
            updateHistoryChart(data.items);
            updateDistrictChartFromHistory(data.items);
        } else {
            console.log('📊 No hay datos para mostrar en gráficos');
            showEmptyCharts();
        }

    } catch (error) {
        console.error('❌ Error cargando historial para gráficos:', error);
        showEmptyCharts();
    }
}

// ============================================
//  ACTUALIZAR GRÁFICO DE HISTORIAL
//  ============================================

function updateHistoryChart(historyData) {
    if (!historyChart) {
        console.warn('⚠️ historyChart no inicializado');
        return;
    }

    if (!historyData || historyData.length === 0) {
        console.log('📊 No hay datos para el gráfico de historial');
        showEmptyHistoryChart();
        return;
    }

    // Ordenar por fecha (ascendente)
    const sorted = [...historyData].sort((a, b) =>
        new Date(a.created_at) - new Date(b.created_at)
    );

    const labels = sorted.map(item => {
        const date = new Date(item.created_at);
        return date.toLocaleDateString('es-PE', { day: '2-digit', month: 'short' });
    });

    const prices = sorted.map(item => Math.round(item.predicted_price));

    historyChart.data.labels = labels;
    historyChart.data.datasets[0].data = prices;
    reactivarTooltip(historyChart);   // pudo desactivarse en el estado vacío
    historyChart.update();

    console.log('📊 Gráfico de historial actualizado con', labels.length, 'puntos');
}

// ============================================
//  ACTUALIZAR GRÁFICO DE DISTRITOS DESDE HISTORIAL
//  ============================================

function updateDistrictChartFromHistory(historyData) {
    if (!districtChart) {
        console.warn('⚠️ districtChart no inicializado');
        return;
    }

    if (!historyData || historyData.length === 0) {
        console.log('📊 No hay datos para el gráfico de distritos');
        showEmptyDistrictChart();
        return;
    }

    // Agrupar por barrio de Ames
    const barrioMap = {};
    historyData.forEach(item => {
        const barrio = item.neighborhood || 'No especificado';
        if (!barrioMap[barrio]) {
            barrioMap[barrio] = { total: 0, count: 0 };
        }
        barrioMap[barrio].total += item.predicted_price;
        barrioMap[barrio].count += 1;
    });

    // Calcular promedios y ordenar
    const barrios = Object.keys(barrioMap);
    const promedios = barrios.map(barrio => ({
        barrio: barrio,
        avg: Math.round(barrioMap[barrio].total / barrioMap[barrio].count),
        count: barrioMap[barrio].count
    }));

    // Ordenar por promedio (descendente)
    promedios.sort((a, b) => b.avg - a.avg);

    // Tomar top 10
    const topBarrios = promedios.slice(0, 10);

    districtChart.data.labels = topBarrios.map(d => d.barrio);
    districtChart.data.datasets[0].data = topBarrios.map(d => d.avg);

    // El tooltip lee SIEMPRE del gráfico actual. Antes usaba un closure sobre el
    // array de la primera carga, así que mostraba datos obsoletos al recargar.
    districtChart.options.plugins.tooltip.callbacks.label = function(context) {
        const etiqueta = context.chart.data.labels[context.dataIndex];
        const valor = context.parsed.y ?? context.parsed;
        return `${etiqueta}: ${formatearPrecio(valor)}`;
    };

    districtChart.update();
    reactivarTooltip(districtChart);   // pudo desactivarse en el estado vacío

    console.log('📊 Gráfico de barrios actualizado con', topBarrios.length, 'barrios');
}

// ============================================
//  ACTUALIZAR DATOS DE DISTRITOS (desde stats)
//  ============================================

function updateNeighborhoodData(topNeighborhoods) {
    if (!districtChart) return;
    if (!topNeighborhoods || topNeighborhoods.length === 0) {
        showEmptyDistrictChart();
        return;
    }

    // Se usa la etiqueta en español que ya calcula la API, con el código del
    // barrio como respaldo.
    const labels = topNeighborhoods.map(d => d.label || d.neighborhood);
    const prices = topNeighborhoods.map(d => Math.round(d.avg_price));

    districtChart.data.labels = labels;
    districtChart.data.datasets[0].data = prices;

    districtChart.options.plugins.tooltip.callbacks.label = function(context) {
        const valor = context.parsed.y ?? context.parsed;
        return `${context.chart.data.labels[context.dataIndex]}: ${formatearPrecio(valor)}`;
    };

    districtChart.update();
    reactivarTooltip(districtChart);

    console.log('📊 Gráfico de barrios actualizado desde stats');
}

// ============================================
// MOSTRAR GRÁFICOS VACÍOS
//  ============================================

function showEmptyCharts() {
    showEmptyHistoryChart();
    showEmptyDistrictChart();
}

/**
 * Deja un gráfico en estado "sin datos".
 *
 * Ojo con `tooltip.enabled`: al desactivarlo hay que VOLVER A ACTIVARLO cuando
 * lleguen datos, porque Chart.js no lo restaura solo. Antes se apagaba aquí y no
 * se encendía en ningún sitio, así que tras el primer estado vacío los gráficos
 * se quedaban sin tooltips para siempre (hasta recargar la página).
 */
function marcarGraficoVacio(grafico) {
    if (!grafico) return;
    grafico.data.labels = ['Sin datos'];
    grafico.data.datasets[0].data = [0];
    grafico.options.plugins.tooltip.enabled = false;
    grafico.update();
}

function reactivarTooltip(grafico) {
    if (grafico && grafico.options && grafico.options.plugins) {
        grafico.options.plugins.tooltip.enabled = true;
    }
}

function showEmptyHistoryChart() {
    marcarGraficoVacio(historyChart);
}

function showEmptyDistrictChart() {
    marcarGraficoVacio(districtChart);
}

// ============================================
//  INICIALIZACIÓN AUTOMÁTICA
//  ============================================

// Inicializar gráficos cuando el DOM esté listo
document.addEventListener('DOMContentLoaded', function() {
    console.log('📊 Inicializando dashboard automáticamente...');

    setTimeout(() => {
        if (typeof initCharts === 'function') {
            initCharts();
        }
    }, 600);
});

// ============================================
//  EXPORTAR FUNCIONES
//  ============================================

window.loadDashboard = loadDashboard;
window.initCharts = initCharts;
window.updateHistoryChart = updateHistoryChart;
window.updateDistrictChartFromHistory = updateDistrictChartFromHistory;
window.showEmptyCharts = showEmptyCharts;
window.updateStats = updateStats;
window.updateStatsEmpty = updateStatsEmpty;

console.log('📊 Módulo dashboard cargado correctamente');