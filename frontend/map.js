// ============================================
// MAPA - PROPIEDADES Y UBICACIONES
// ============================================

let mapPicker = null;
let mapResult = null;
let mapContainer = null;
let pickerMarker = null;
let resultMarker = null;
let markerPrice = null;
let mapMarkers = [];

// ============================================
// INICIALIZAR MAPA DEL FORMULARIO
// ============================================

function initMapPicker() {
    const container = document.getElementById('map-picker');
    if (!container) {
        console.warn('⚠️ No se encontró el contenedor #map-picker');
        return;
    }

    // Verificar que el mapa no esté ya inicializado
    if (mapPicker) {
        console.log('📍 Mapa del formulario ya inicializado');
        mapPicker.invalidateSize();
        return;
    }

    try {
        // Inicializar mapa centrado en Ames, Iowa (el dataset del modelo)
        mapPicker = L.map('map-picker', {
            center: [42.0308, -93.6319],
            zoom: 13,
            zoomControl: true,
            fadeAnimation: true,
            zoomAnimation: true,
            markerZoomAnimation: true
        });

        // Capa de OpenStreetMap
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors',
            maxZoom: 19,
            minZoom: 5
        }).addTo(mapPicker);

        // Crear marcador personalizado para el picker
        const pickerIcon = L.divIcon({
            html: '📍',
            className: 'custom-marker highlight',
            iconSize: [40, 40],
            iconAnchor: [20, 40],
            popupAnchor: [0, -40]
        });

        // Añadir marcador inicial en Ames (Iowa)
        pickerMarker = L.marker([42.0308, -93.6319], {
            icon: pickerIcon,
            draggable: true
        }).addTo(mapPicker);

        // Evento de clic en el mapa
        mapPicker.on('click', function(e) {
            const lat = e.latlng.lat;
            const lng = e.latlng.lng;
            updateMarkerPosition(lat, lng);
            updateCoordinatesDisplay(lat, lng);
            reverseGeocode(lat, lng);
        });

        // Evento de arrastre del marcador
        pickerMarker.on('dragend', function(e) {
            const lat = e.target.getLatLng().lat;
            const lng = e.target.getLatLng().lng;
            updateCoordinatesDisplay(lat, lng);
            reverseGeocode(lat, lng);
        });

        // Asegurar que el mapa se renderice correctamente
        setTimeout(() => {
            if (mapPicker) {
                mapPicker.invalidateSize();
            }
        }, 500);

        console.log('✅ Mapa del formulario inicializado');

        // Si hay token, cargar marcadores
        const token = localStorage.getItem('authToken');
        if (token && typeof loadMapMarkers === 'function') {
            setTimeout(() => {
                loadMapMarkers();
            }, 1000);
        }

    } catch (error) {
        console.error('❌ Error inicializando mapa del formulario:', error);
    }
}

// ============================================
// INICIALIZAR MAPA DE LA PESTAÑA "MAPA"
// ============================================

function initMapContainer() {
    const container = document.getElementById('map-container');
    if (!container) {
        console.warn('⚠️ No se encontró el contenedor #map-container');
        return;
    }

    // Verificar que el mapa no esté ya inicializado
    if (mapContainer) {
        console.log('📍 Mapa de contenedor ya inicializado');
        mapContainer.invalidateSize();
        return;
    }

    try {
        mapContainer = L.map('map-container', {
            center: [42.0308, -93.6319],
            zoom: 12,
            zoomControl: true,
            fadeAnimation: true,
            zoomAnimation: true
        });

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors',
            maxZoom: 19,
            minZoom: 5
        }).addTo(mapContainer);

        setTimeout(() => {
            if (mapContainer) {
                mapContainer.invalidateSize();
            }
        }, 500);

        console.log('✅ Mapa de contenedor inicializado');

        // Cargar marcadores si hay token
        const token = localStorage.getItem('authToken');
        if (token && typeof loadMapMarkers === 'function') {
            setTimeout(() => {
                loadMapMarkers();
            }, 1000);
        }

    } catch (error) {
        console.error('❌ Error inicializando mapa de contenedor:', error);
    }
}

// ============================================
// INICIALIZAR MAPA DE RESULTADOS
// ============================================

function initResultMap() {
    const container = document.getElementById('result-map');
    if (!container) {
        console.warn('⚠️ No se encontró el contenedor #result-map');
        return;
    }

    if (mapResult) {
        mapResult.invalidateSize();
        return;
    }

    try {
        mapResult = L.map('result-map', {
            center: [42.0308, -93.6319],
            zoom: 14,
            zoomControl: true
        });

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors'
        }).addTo(mapResult);

        setTimeout(() => {
            if (mapResult) {
                mapResult.invalidateSize();
            }
        }, 400);

        console.log('✅ Mapa de resultados inicializado');

    } catch (error) {
        console.error('❌ Error inicializando mapa de resultados:', error);
    }
}

// ============================================
// ACTUALIZAR POSICIÓN DEL MARCADOR
// ============================================

function updateMarkerPosition(lat, lng) {
    if (pickerMarker) {
        pickerMarker.setLatLng([lat, lng]);
    }
}

// ============================================
// ACTUALIZAR COORDENADAS EN EL FORMULARIO
// ============================================

function updateCoordinatesDisplay(lat, lng) {
    const latDisplay = document.getElementById('latitude-display');
    const lngDisplay = document.getElementById('longitude-display');

    if (latDisplay) {
        latDisplay.textContent = lat.toFixed(6);
    }
    if (lngDisplay) {
        lngDisplay.textContent = lng.toFixed(6);
    }

    // Almacenar en variables globales para usar en la predicción
    window.selectedLatitude = lat;
    window.selectedLongitude = lng;
}

// ============================================
// GEOCODIFICACIÓN INVERSA (obtener dirección)
// ============================================

/**
 * Última petición de geocodificación en curso.
 *
 * Nominatim (el servicio de OpenStreetMap) limita el uso a 1 petición por
 * segundo y pide identificar la aplicación. Aquí se aplica un retardo (debounce)
 * y se CANCELA la petición anterior, porque además de respetar el límite evita
 * que una respuesta lenta y antigua sobrescriba la dirección de un clic más
 * reciente.
 *
 * Nota: el navegador no permite fijar la cabecera User-Agent, así que Nominatim
 * identifica la aplicación por el Referer. Si esto fuese a producción, lo
 * correcto sería consultar a través del backend, con caché.
 */
let geocodificacionPendiente = null;
let controladorGeocodificacion = null;
const RETARDO_GEOCODIFICACION_MS = 1100;

function reverseGeocode(lat, lng) {
    const addressDisplay = document.getElementById('address-text');
    if (!addressDisplay) return;

    addressDisplay.textContent = 'Buscando dirección...';

    if (geocodificacionPendiente) {
        clearTimeout(geocodificacionPendiente);
    }
    if (controladorGeocodificacion) {
        controladorGeocodificacion.abort();
    }

    geocodificacionPendiente = setTimeout(
        () => consultarDireccion(lat, lng, addressDisplay),
        RETARDO_GEOCODIFICACION_MS
    );
}

async function consultarDireccion(lat, lng, addressDisplay) {
    controladorGeocodificacion = new AbortController();

    try {
        const response = await fetch(
            `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lng}&format=json&zoom=18&addressdetails=1`,
            { signal: controladorGeocodificacion.signal }
        );

        if (!response.ok) throw new Error('Error en geocodificación');

        const data = await response.json();

        if (data && data.display_name) {
            const address = data.display_name.length > 80
                ? data.display_name.substring(0, 80) + '...'
                : data.display_name;
            addressDisplay.textContent = address;
        } else {
            addressDisplay.textContent = 'Dirección no encontrada';
        }
    } catch (error) {
        if (error.name === 'AbortError') {
            return;  // la canceló un clic más reciente: no es un error
        }
        console.error('❌ Error en geocodificación inversa:', error);
        addressDisplay.textContent = 'No se pudo obtener la dirección';
    } finally {
        controladorGeocodificacion = null;
    }
}

// ============================================
// MOSTRAR PREDICCIÓN EN EL MAPA
// ============================================

function showPredictionOnMap(lat, lng, price, details) {
    // Inicializar mapa de resultados si no existe
    if (!mapResult) {
        const container = document.getElementById('result-map');
        if (container) {
            document.getElementById('result-map-container').style.display = 'block';
            initResultMap();
        }
    }

    if (!mapResult) {
        console.warn('⚠️ Mapa de resultados no disponible');
        return;
    }

    // Limpiar marcador anterior
    if (resultMarker) {
        mapResult.removeLayer(resultMarker);
        resultMarker = null;
    }
    if (markerPrice) {
        mapResult.removeLayer(markerPrice);
        markerPrice = null;
    }

    // Crear ícono con precio
    const priceIcon = L.divIcon({
        html: `
            <div style="
                background: #00b894;
                color: white;
                padding: 4px 12px;
                border-radius: 20px;
                font-weight: 700;
                font-size: 13px;
                box-shadow: 0 4px 15px rgba(0,184,148,0.4);
                border: 2px solid white;
                white-space: nowrap;
            ">
                $ ${price.toLocaleString('en-US', { maximumFractionDigits: 0 })}
            </div>
        `,
        className: 'price-marker',
        iconSize: [120, 32],
        iconAnchor: [60, 16]
    });

    // Crear marcador principal
    const mainIcon = L.divIcon({
        html: '🏠',
        className: 'custom-marker highlight',
        iconSize: [40, 40],
        iconAnchor: [20, 40]
    });

    // Añadir marcador principal
    resultMarker = L.marker([lat, lng], {
        icon: mainIcon,
        title: `💰 $ ${price.toLocaleString('en-US', { maximumFractionDigits: 0 })}`
    }).addTo(mapResult)
        .bindPopup(`
            <div style="min-width:200px;">
                <strong style="color:#00b894;font-size:1.2rem;">
                    💰 $ ${price.toLocaleString('en-US', { maximumFractionDigits: 0 })}
                </strong>
                <br/>
                ${details}
                <br/>
                <small style="color:#999;">${new Date().toLocaleString('es-PE')}</small>
            </div>
        `)
        .openPopup();

    // Añadir marcador con precio (ligeramente desplazado)
    markerPrice = L.marker([lat + 0.0003, lng], {
        icon: priceIcon
    }).addTo(mapResult);

    // Centrar el mapa en la ubicación
    mapResult.setView([lat, lng], 15, {
        animate: true,
        duration: 0.8
    });

    // Mostrar el contenedor del mapa
    document.getElementById('result-map-container').style.display = 'block';

    // Forzar actualización del tamaño del mapa
    setTimeout(() => {
        if (mapResult) mapResult.invalidateSize();
    }, 400);
}

// ============================================
// CARGAR MARCADORES DEL HISTORIAL
// ============================================

/**
 * Dibuja en el mapa de la sección "Mapa" los marcadores del historial.
 *
 * El mapa destino es SOLO `mapContainer`. Antes había un respaldo a
 * `mapResult` y `mapPicker` (`const targetMap = mapContainer || mapResult ||
 * mapPicker`), y eso provocaba dos problemas:
 *
 *   1. Si el mapa de la sección aún no se había inicializado, los marcadores del
 *      historial se dibujaban encima del mapa del formulario, que sirve para
 *      elegir una ubicación.
 *   2. `fitBounds` recentraba ese mapa, así que la ubicación que el usuario
 *      acababa de marcar se perdía.
 *
 * Si el mapa de la sección no está listo, se inicializa aquí mismo.
 */
async function loadMapMarkers() {
    console.log('📍 Cargando marcadores del mapa...');

    const token = localStorage.getItem('authToken');
    if (!token) {
        console.warn('⚠️ No hay token de autenticación');
        return;
    }

    // El mapa de la sección debe existir: se crea si hace falta.
    if (!mapContainer && typeof initMapContainer === 'function') {
        initMapContainer();
    }

    const targetMap = mapContainer;

    if (!targetMap) {
        console.warn('⚠️ El mapa de la sección no está disponible');
        return;
    }

    try {
        const response = await fetch(`${API_URL}/predictions/history?limit=50`, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            if (response.status === 401) {
                // Antes solo se escribía un aviso en la consola y la interfaz
                // seguía mostrando la sesión como activa.
                if (typeof window.manejarSesionExpirada === 'function') {
                    window.manejarSesionExpirada();
                }
                return;
            }
            throw new Error(`Error ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        console.log('📍 Marcadores recibidos:', data.items?.length || 0);

        // Limpiar marcadores existentes (excepto el picker)
        mapMarkers.forEach(marker => {
            if (targetMap && marker) {
                try {
                    targetMap.removeLayer(marker);
                } catch (e) {
                    // Ignorar errores al eliminar marcadores
                }
            }
        });
        mapMarkers = [];

        if (data.items && data.items.length > 0) {
            const validItems = data.items.filter(item =>
                item.latitude && item.longitude &&
                !isNaN(item.latitude) && !isNaN(item.longitude)
            );

            if (validItems.length > 0) {
                addMarkersToMap(validItems, targetMap);
                console.log(`📍 ${validItems.length} marcadores agregados al mapa`);
            } else {
                console.log('📍 No hay propiedades con coordenadas válidas');
            }
        } else {
            console.log('📍 No hay historial para mostrar en el mapa');
        }

    } catch (error) {
        console.error('❌ Error cargando marcadores:', error);
    }
}

// ============================================
// AÑADIR MARCADORES AL MAPA
// ============================================

function addMarkersToMap(predictions, targetMap) {
    if (!targetMap) {
        console.warn('⚠️ No hay mapa para agregar marcadores');
        return;
    }

    const customIcon = L.divIcon({
        html: '🏠',
        className: 'custom-marker',
        iconSize: [32, 32],
        iconAnchor: [16, 32],
        popupAnchor: [0, -32]
    });

    predictions.forEach(pred => {
        if (pred.latitude && pred.longitude) {
            const marker = L.marker([pred.latitude, pred.longitude], {
                icon: customIcon,
                title: `💰 $ ${Math.round(pred.predicted_price).toLocaleString('en-US')}`
            }).addTo(targetMap)
                .bindPopup(`
                    <div style="min-width:200px;">
                        <strong style="color:#00b894;font-size:1.1rem;">
                            💰 $ ${Math.round(pred.predicted_price).toLocaleString('en-US')}
                        </strong>
                        <br/>
                        🏘️ ${escapeHtml(pred.neighborhood || '—')}
                        <br/>
                        📐 ${escapeHtml(pred.gr_liv_area_m2)} m² · 🛏️ ${escapeHtml(pred.bedrooms)} dorm
                        <br/>
                        🚿 ${escapeHtml(pred.bathrooms)} baños · 🚗 ${escapeHtml(pred.garage_cars)} plazas
                        <br/>
                        ⭐ Calidad ${escapeHtml(pred.overall_qual)}/10 · 📅 ${escapeHtml(pred.year_built)}
                        <br/>
                        ${new Date(pred.created_at).toLocaleDateString('es-PE')}
                    </div>
                `);

            mapMarkers.push(marker);
        }
    });

    // Ajustar vista para mostrar todos los marcadores si hay más de 1
    if (mapMarkers.length > 1) {
        try {
            const group = L.featureGroup(mapMarkers);
            targetMap.fitBounds(group.getBounds(), { padding: [50, 50] });
        } catch (e) {
            // Si hay problema con los bounds, usar vista por defecto
            targetMap.setView([42.0308, -93.6319], 12);
        }
    } else if (mapMarkers.length === 1) {
        // Si solo hay un marcador, centrar en él
        const marker = mapMarkers[0];
        const latLng = marker.getLatLng();
        targetMap.setView([latLng.lat, latLng.lng], 14);
    }
}

// ============================================
// EXPORTAR FUNCIONES GLOBALES
//============================================

window.initMapPicker = initMapPicker;
window.initMapContainer = initMapContainer;
window.initResultMap = initResultMap;
window.loadMapMarkers = loadMapMarkers;
window.addMarkersToMap = addMarkersToMap;
window.showPredictionOnMap = showPredictionOnMap;
window.updateCoordinatesDisplay = updateCoordinatesDisplay;
window.reverseGeocode = reverseGeocode;

// NOTA: aquí estaba `showOnMapFromResult(lat, lng, price, details)`, una función
// completa que abría la pestaña Mapa y colocaba un marcador destacado. Se ha
// retirado porque NADIE la llamaba (el botón "Ver en mapa" usa `showOnMap()`,
// que despliega un mapa pequeño bajo el resultado).
//
// Se deja constancia porque hacía algo distinto y puede que se prefiera: para
// recuperarla habría que guardar la última predicción y llamarla desde el botón
// con sus coordenadas.

// ============================================
//INICIALIZACIÓN AUTOMÁTICA
// ============================================

// Inicializar mapa del formulario cuando el DOM esté listo
document.addEventListener('DOMContentLoaded', function() {
    console.log('📍 Inicializando módulo de mapas...');

    // Inicializar mapa del formulario después de un delay
    setTimeout(() => {
        if (document.getElementById('map-picker') && typeof initMapPicker === 'function') {
            initMapPicker();
        }
    }, 800);

    // NOTA: aquí había un segundo listener sobre la pestaña "Mapa" que volvía a
    // llamar a initMapContainer() y loadMapMarkers(). La carga de secciones ya la
    // centraliza `handleSectionChange()` en script.js, así que el mapa se
    // inicializaba y los marcadores se recargaban dos veces por clic.

    // Inicializar mapa de contenedor si ya está visible
    const mapSection = document.getElementById('section-map');
    if (mapSection && mapSection.classList.contains('active')) {
        setTimeout(() => {
            if (typeof initMapContainer === 'function') {
                initMapContainer();
            }
        }, 1000);
    }
});

console.log('📍 Módulo map.js cargado correctamente');