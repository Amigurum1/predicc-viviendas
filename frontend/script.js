// ============================================
// CONFIGURACIÓN
// ============================================

/**
 * URL base de la API.
 *
 * Se puede cambiar sin tocar el código con una etiqueta en el HTML:
 *
 *     <meta name="api-url" content="http://mi-servidor:8000/api">
 *
 * Antes estaba fija aquí, así que desplegar en otro host o puerto obligaba a
 * editar el JavaScript (y el valor quedaba repetido en la documentación).
 */
const API_URL = (() => {
    const etiqueta = document.querySelector('meta[name="api-url"]');
    const configurada = etiqueta && etiqueta.content ? etiqueta.content.trim() : '';
    return configurada || 'http://localhost:8000/api';
})();
let authToken = null;
let currentUser = null;

// ============================================
// UTILIDADES
// ============================================

/**
 * Escapa texto antes de insertarlo con innerHTML.
 *
 * Los campos que devuelve la API (por ejemplo `neighborhood`) son cadenas que
 * en teoría controla el usuario, así que no deben inyectarse en crudo: sería
 * XSS almacenado en una página que además guarda el token en localStorage.
 */
function escapeHtml(valor) {
    if (valor === null || valor === undefined) return '';
    return String(valor)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

/** Formatea un precio en dólares (el modelo es del dataset de Ames, EE. UU.). */
function formatearPrecio(valor) {
    const numero = Number(valor) || 0;
    return '$ ' + numero.toLocaleString('en-US', {
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
    });
}

// Nombres legibles de los campos, para que los errores de validación digan algo
// comprensible ("Contraseña: ..." en vez de "password: ...").
const ETIQUETAS_DE_CAMPO = {
    password: 'Contraseña',
    new_password: 'Contraseña nueva',
    old_password: 'Contraseña actual',
    email: 'Email',
    username: 'Usuario',
    first_name: 'Nombre',
    last_name: 'Apellido',
    phone: 'Teléfono',
    neighborhood: 'Barrio',
    ms_subclass: 'Tipo de vivienda',
    gr_liv_area_m2: 'Superficie habitable',
    lot_area_m2: 'Superficie de la parcela',
    overall_qual: 'Calidad general',
    year_built: 'Año de construcción',
    bedrooms: 'Dormitorios',
    bathrooms: 'Baños',
    garage_cars: 'Plazas de garaje',
};

/**
 * Convierte el `detail` de un error de la API en un mensaje legible.
 *
 * La API devuelve dos formas distintas:
 *
 *  - **Errores de validación (422)**: `detail` es una LISTA de objetos, uno por
 *    campo. Antes se pasaba entera a `new Error(...)`, y como un array de
 *    objetos se convierte en la cadena "[object Object]", el usuario veía
 *    literalmente eso al equivocarse con la contraseña.
 *  - **Errores de negocio (400, 401, 403...)**: `detail` es una cadena.
 */
function mensajeDeError(detail, porDefecto) {
    if (!detail) return porDefecto;

    if (typeof detail === 'string') return detail;

    if (Array.isArray(detail)) {
        const partes = detail.map(item => {
            const mensaje = String(item.msg || '')
                // Pydantic antepone "Value error, " a los mensajes de un validador
                .replace(/^Value error,\s*/i, '');

            // `loc` es como ['body', 'password']: se quita 'body' y se traduce
            const campos = (item.loc || []).filter(p => p !== 'body' && p !== 'query');
            const etiqueta = campos
                .map(c => ETIQUETAS_DE_CAMPO[c] || c)
                .join(' → ');

            return etiqueta ? `${etiqueta}: ${mensaje}` : mensaje;
        }).filter(Boolean);

        return partes.join(' · ') || porDefecto;
    }

    if (typeof detail === 'object' && detail.msg) return String(detail.msg);

    return porDefecto;
}

// ============================================
// DOM REFERENCES
// ============================================

let authForms, authMessage, logoutBtn;
let historySection, resultContainer, historyContainer;
let loginForm, registerForm, predictionForm;

// ============================================
// INICIALIZACIÓN
// ============================================

document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 Inicializando aplicación...');

    // Asignar referencias DOM
    authForms = document.getElementById('auth-forms');
    authMessage = document.getElementById('auth-message');
    logoutBtn = document.getElementById('logout-btn');
    historySection = document.getElementById('section-history');
    resultContainer = document.getElementById('result-container');
    historyContainer = document.getElementById('history-container');

    loginForm = document.getElementById('login-form');
    registerForm = document.getElementById('register-form');
    predictionForm = document.getElementById('prediction-form');

    // Verificar que todos los elementos existen
    if (!authForms || !authMessage || !logoutBtn) {
        console.error('❌ Error: Elementos DOM no encontrados');
        return;
    }

    console.log('✅ DOM cargado correctamente');

    // Configurar eventos
    setupEventListeners();

    // Cargar los barrios y tipos de vivienda ANTES de nada: el formulario no se
    // puede rellenar sin ellos. Es un endpoint público, no necesita sesión.
    loadFormOptions();

    // Avisar si alguna librería de CDN no se ha podido cargar
    comprobarDependencias();

    // Menú lateral en móvil
    configurarMenuMovil();

    // Verificar sesión guardada
    checkSavedSession();

    // Inicializar gráficos si están disponibles
    setTimeout(() => {
        if (typeof initCharts === 'function') {
            console.log('📊 Inicializando gráficos...');
            initCharts();
        }
    }, 800);

    // Inicializar mapa del formulario
    setTimeout(() => {
        if (document.getElementById('map-picker') && typeof initMapPicker === 'function') {
            console.log('📍 Inicializando mapa del formulario...');
            initMapPicker();
        }
    }, 1000);
});

// ============================================
// COMPROBACIÓN DE DEPENDENCIAS EXTERNAS
// ============================================

/**
 * Comprueba que las librerías cargadas por CDN están disponibles.
 *
 * Leaflet, Chart.js y html2pdf se cargan desde CDNs, así que sin conexión (o si
 * un CDN falla) la aplicación arrancaría a medias sin decir nada: los mapas no
 * se dibujarían, los gráficos no aparecerían y el botón de PDF no haría nada.
 * Aquí se detecta y se avisa al usuario.
 */
function comprobarDependencias() {
    const faltan = [];

    if (typeof L === 'undefined') faltan.push('Leaflet (mapas)');
    if (typeof Chart === 'undefined') faltan.push('Chart.js (gráficos)');
    if (typeof html2pdf === 'undefined') faltan.push('html2pdf (exportar a PDF)');

    if (faltan.length) {
        console.warn('⚠️ Librerías no disponibles:', faltan.join(', '));
        showMessage(
            `⚠️ No se pudieron cargar: ${faltan.join(', ')}. ` +
            'Esas funciones no estarán disponibles (revisa tu conexión).',
            'error'
        );
    }

    return faltan;
}

// ============================================
// MENÚ LATERAL EN MÓVIL
// ============================================

/**
 * Prepara el botón que abre el menú lateral en pantallas pequeñas.
 *
 * En móvil el CSS esconde el sidebar fuera de la pantalla
 * (`transform: translateX(-100%)`) y solo lo muestra con la clase `.open`. Faltaba
 * el botón para activarla, así que la aplicación se quedaba sin navegación.
 */
function configurarMenuMovil() {
    const boton = document.getElementById('menu-toggle');
    const sidebar = document.getElementById('sidebar');
    const fondo = document.getElementById('sidebar-backdrop');

    if (!boton || !sidebar) {
        console.warn('⚠️ No se encontró el botón o el sidebar del menú móvil');
        return;
    }

    const abierto = () => sidebar.classList.contains('open');

    function abrirMenu() {
        sidebar.classList.add('open');
        boton.setAttribute('aria-expanded', 'true');
        boton.setAttribute('aria-label', 'Cerrar el menú de navegación');
        if (fondo) fondo.hidden = false;
    }

    function cerrarMenu() {
        sidebar.classList.remove('open');
        boton.setAttribute('aria-expanded', 'false');
        boton.setAttribute('aria-label', 'Abrir el menú de navegación');
        if (fondo) fondo.hidden = true;
    }

    boton.addEventListener('click', () => (abierto() ? cerrarMenu() : abrirMenu()));

    // Cerrar al tocar fuera (el fondo) y con la tecla Escape
    if (fondo) fondo.addEventListener('click', cerrarMenu);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && abierto()) {
            cerrarMenu();
            boton.focus();
        }
    });

    // Al elegir una sección, el menú se cierra para poder ver el contenido
    sidebar.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', cerrarMenu);
    });

    // Si la ventana crece a escritorio, quitar el estado de móvil
    window.addEventListener('resize', () => {
        if (window.innerWidth > 768 && abierto()) cerrarMenu();
    });

    // Se expone para poder cerrarlo desde otros sitios (por ejemplo al cerrar sesión)
    window.cerrarMenuMovil = cerrarMenu;
}

// ============================================
// EVENTOS
// ============================================

function setupEventListeners() {
    // Login
    if (loginForm) {
        loginForm.addEventListener('submit', handleLogin);
    }

    // Registro
    if (registerForm) {
        registerForm.addEventListener('submit', handleRegister);
    }

    // Predicción
    if (predictionForm) {
        predictionForm.addEventListener('submit', handlePrediction);
    }

    // Logout (evento global)
    window.logout = logout;
    window.clearResult = clearResult;
    window.exportPDF = exportPDF;
    window.showOnMap = showOnMap;

    // Navegación del sidebar
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.addEventListener('click', function() {
            // Remover active de todos
            navItems.forEach(n => n.classList.remove('active'));
            this.classList.add('active');

            // Mostrar sección correspondiente
            const sectionName = this.dataset.section;
            document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
            const target = document.getElementById(`section-${sectionName}`);
            if (target) target.classList.add('active');

            // Acciones específicas por sección
            handleSectionChange(sectionName);
        });
    });

    console.log('✅ Event listeners configurados');
}

// ============================================
// MANEJAR CAMBIO DE SECCIÓN
//  ============================================


function handleSectionChange(sectionName) {
    console.log(`📂 Cambiando a sección: ${sectionName}`);

    // ✅ Mostrar/ocultar historial según la sección
    const historyContainer = document.getElementById('history-container');
    const historySection = document.getElementById('section-history');
    
    if (historyContainer) {
        if (sectionName === 'history') {
            historyContainer.style.display = 'block';
        } else {
            historyContainer.style.display = 'none';
        }
    }

    // ✅ Si la sección es history, recargar historial
    if (sectionName === 'history') {
        if (authToken) {
            setTimeout(() => {
                console.log('📊 Recargando historial...');
                loadHistory();
            }, 300);
        }
    }

    // ✅ Si la sección es dashboard, cargar dashboard
    if (sectionName === 'dashboard') {
        if (authToken && typeof loadDashboard === 'function') {
            setTimeout(() => {
                console.log('📊 Cargando dashboard...');
                loadDashboard();
            }, 300);
        } else {
            console.warn('⚠️ No se puede cargar dashboard: sin token o función no disponible');
        }
    }

    // ✅ Si la sección es mapa, preparar el mapa y cargar los marcadores.
    // El orden importa: primero hay que crear el mapa (si no existe) y después
    // dibujar los marcadores sobre él. Antes esto vivía en un listener aparte en
    // map.js y la sección se cargaba dos veces por clic.
    if (sectionName === 'map') {
        setTimeout(() => {
            if (typeof initMapContainer === 'function') {
                initMapContainer();
            }
            if (authToken && typeof loadMapMarkers === 'function') {
                console.log('📍 Cargando marcadores del mapa...');
                loadMapMarkers();
            } else if (!authToken) {
                console.warn('⚠️ No se pueden cargar marcadores: sin sesión');
            }
        }, 300);
    }

    // ✅ Si la sección es predict, asegurar que el mapa se vea bien
    if (sectionName === 'predict') {
        setTimeout(() => {
            if (typeof initMapPicker === 'function') {
                initMapPicker();
            }
        }, 400);
    }
}

// ============================================
// AUTENTICACIÓN
// ============================================

async function handleLogin(e) {
    e.preventDefault();

    const email = document.getElementById('login-email').value;
    const password = document.getElementById('login-password').value;

    try {
        const response = await fetch(`${API_URL}/auth/login`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: new URLSearchParams({
                username: email,
                password: password,
            }),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(mensajeDeError(error.detail, 'Error en el login'));
        }

        const data = await response.json();
        authToken = data.access_token;
        currentUser = data.user;

        localStorage.setItem('authToken', authToken);
        localStorage.setItem('currentUser', JSON.stringify(currentUser));

        showAuthenticated();
        showMessage(`✅ Bienvenido, ${currentUser.first_name || currentUser.username}!`, 'success');

        loginForm.reset();

    } catch (error) {
        showMessage(`❌ ${error.message}`, 'error');
    }
}

async function handleRegister(e) {
    e.preventDefault();

    const userData = {
        email: document.getElementById('register-email').value,
        username: document.getElementById('register-username').value,
        password: document.getElementById('register-password').value,
        first_name: document.getElementById('register-firstname').value,
        last_name: document.getElementById('register-lastname').value,
    };

    try {
        const response = await fetch(`${API_URL}/auth/register`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(userData),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(mensajeDeError(error.detail, 'Error en el registro'));
        }

        const data = await response.json();
        showMessage(`✅ Usuario ${data.email} registrado correctamente! Ahora inicia sesión.`, 'success');
        registerForm.reset();

    } catch (error) {
        showMessage(`❌ ${error.message}`, 'error');
    }
}

// ============================================
//  ESTADO DE AUTENTICACIÓN
//  ============================================

function showAuthenticated() {
    console.log('✅ Usuario autenticado:', currentUser?.email);

    if (authForms) authForms.style.display = 'none';
    if (historySection) historySection.style.display = 'block';
    if (logoutBtn) logoutBtn.style.display = 'inline-block';
    if (authMessage) authMessage.textContent = `✅ Conectado como ${currentUser?.email}`;

    // Mostrar formulario de predicción
    const formContainer = document.getElementById('prediction-form-container');
    if (formContainer) formContainer.style.display = 'block';

    // Actualizar nombre de usuario en sidebar
    const userName = document.getElementById('user-name');
    const userEmail = document.getElementById('user-email');
    if (userName) userName.textContent = currentUser?.first_name || currentUser?.username || 'Usuario';
    if (userEmail) userEmail.textContent = currentUser?.email || '';

    console.log('🔑 Token:', localStorage.getItem('authToken') ? 'Presente' : 'Ausente');

    // Cargar datos
    loadHistory();

    setTimeout(() => {
        if (typeof loadDashboard === 'function') {
            console.log('📊 Cargando dashboard...');
            loadDashboard();
        }
        if (typeof loadMapMarkers === 'function') {
            console.log('📍 Cargando marcadores del mapa...');
            loadMapMarkers();
        }
    }, 500);
}

function showUnauthenticated() {
    if (authForms) authForms.style.display = 'grid';
    if (historySection) historySection.style.display = 'none';
    if (logoutBtn) logoutBtn.style.display = 'none';
    if (resultContainer) resultContainer.style.display = 'none';
    if (authMessage) authMessage.textContent = 'No has iniciado sesión';

    const formContainer = document.getElementById('prediction-form-container');
    if (formContainer) formContainer.style.display = 'none';
    const resultMap = document.getElementById('result-map-container');
    if (resultMap) resultMap.style.display = 'none';

    // Resetear usuario en sidebar
    const userName = document.getElementById('user-name');
    const userEmail = document.getElementById('user-email');
    if (userName) userName.textContent = 'Invitado';
    if (userEmail) userEmail.textContent = 'No autenticado';
}

function showMessage(message, type = 'info') {
    const messageEl = document.createElement('div');
    messageEl.className = `message message-${type}`;
    messageEl.textContent = message;

    const authStatus = document.getElementById('auth-status');
    if (!authStatus) return;

    const existingMessage = authStatus.querySelector('.message');
    if (existingMessage) existingMessage.remove();
    authStatus.appendChild(messageEl);

    setTimeout(() => {
        if (messageEl.parentNode) messageEl.remove();
    }, 5000);
}

// ============================================
//  LOGOUT
//  ============================================

function logout() {
    authToken = null;
    currentUser = null;
    localStorage.removeItem('authToken');
    localStorage.removeItem('currentUser');
    showUnauthenticated();
    showMessage('🔒 Sesión cerrada');

    // En móvil, cerrar el menú para que se vea la pantalla de acceso
    if (typeof window.cerrarMenuMovil === 'function') {
        window.cerrarMenuMovil();
    }
    // Limpiar gráficos si existen
    if (typeof showEmptyCharts === 'function') {
        showEmptyCharts();
    }

    // Limpiar mapa de resultados
    const resultMap = document.getElementById('result-map-container');
    if (resultMap) resultMap.style.display = 'none';
}

/**
 * Cierra la sesión cuando el servidor responde 401 (token caducado o revocado).
 *
 * Centraliza el manejo para que TODAS las llamadas autenticadas reaccionen
 * igual. Antes cada módulo lo hacía a su manera: dashboard.js borraba
 * localStorage pero dejaba las variables `authToken`/`currentUser` con valor
 * (así que el formulario seguía visible y las siguientes peticiones se enviaban
 * con un token muerto), y map.js solo escribía un aviso en la consola.
 *
 * Se expone en `window` porque la usan dashboard.js y map.js.
 */
function manejarSesionExpirada() {
    if (!authToken && !localStorage.getItem('authToken')) {
        return;  // ya está cerrada, no repetir el aviso
    }
    console.warn('🔒 Sesión expirada: se cierra y se pide volver a entrar');
    logout();
    showMessage('🔒 Tu sesión ha expirado. Vuelve a iniciar sesión.', 'error');
}

window.manejarSesionExpirada = manejarSesionExpirada;

// ============================================
//  PREDICCIÓN
//  ============================================

async function handlePrediction(e) {
    e.preventDefault();

    if (!authToken) {
        showMessage('❌ Debes iniciar sesión primero', 'error');
        return;
    }

    // Obtener coordenadas del mapa o de los inputs
    const latDisplay = document.getElementById('latitude-display');
    const lngDisplay = document.getElementById('longitude-display');

    const latitude = parseFloat(latDisplay?.textContent || '42.0308');
    const longitude = parseFloat(lngDisplay?.textContent || '-93.6319');

    // Los 9 campos del contrato nuevo. Los números se convierten aquí porque
    // los <input type="number"> devuelven cadenas.
    const features = {
        neighborhood: document.getElementById('neighborhood').value,
        ms_subclass: parseInt(document.getElementById('ms_subclass').value, 10),
        gr_liv_area_m2: parseFloat(document.getElementById('gr_liv_area_m2').value),
        lot_area_m2: parseFloat(document.getElementById('lot_area_m2').value),
        overall_qual: parseInt(document.getElementById('overall_qual').value, 10),
        year_built: parseInt(document.getElementById('year_built').value, 10),
        bedrooms: parseInt(document.getElementById('bedrooms').value, 10),
        bathrooms: parseInt(document.getElementById('bathrooms').value, 10),
        garage_cars: parseInt(document.getElementById('garage_cars').value, 10),
        latitude: latitude,
        longitude: longitude,
    };

    const submitBtn = document.getElementById('predict-btn');
    if (!submitBtn) return;

    const originalText = submitBtn.innerHTML;
    submitBtn.innerHTML = '⏳ Calculando...';
    submitBtn.disabled = true;

    try {
        const response = await fetch(`${API_URL}/predictions/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`,
            },
            body: JSON.stringify(features),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(mensajeDeError(error.detail, 'Error en la predicción'));
        }

        const data = await response.json();
        showResult(data);
        loadHistory();

    } catch (error) {
        showMessage(`❌ ${error.message}`, 'error');
    } finally {
        submitBtn.innerHTML = originalText;
        submitBtn.disabled = false;
    }
}

// ============================================
//  MOSTRAR RESULTADO
//  ============================================

function showResult(data) {
    if (!resultContainer) return;

    const priceEl = document.getElementById('predicted-price');
    const confidenceEl = document.getElementById('confidence');
    const confidenceFill = document.getElementById('confidence-fill');
    const detailsEl = document.getElementById('result-details');

    const price = data.predicted_price || 0;
    const confidence = data.confidence || 0;

    if (priceEl) {
        priceEl.textContent = formatearPrecio(price);
    }
    if (confidenceEl) {
        confidenceEl.textContent = `${(confidence * 100).toFixed(0)}%`;
    }
    if (confidenceFill) {
        confidenceFill.style.width = `${(confidence * 100).toFixed(0)}%`;
    }

    const details = `
        🏘️ ${escapeHtml(data.neighborhood || '—')} · ${escapeHtml(data.gr_liv_area_m2)} m² habitables
        <br/>
        🛏️ ${escapeHtml(data.bedrooms)} dorm · ${escapeHtml(data.bathrooms)} baños · 🚗 ${escapeHtml(data.garage_cars)} plazas
        <br/>
        ⭐ Calidad ${escapeHtml(data.overall_qual)}/10 · 📅 ${escapeHtml(data.year_built)} · 🗺️ ${escapeHtml(data.lot_area_m2)} m² de parcela
        <br/>
        ${new Date(data.created_at).toLocaleDateString('es-PE')}
    `;

    if (detailsEl) {
        detailsEl.innerHTML = details;
    }

    // Mostrar en el mapa (Ames, Iowa)
    const lat = data.latitude || 42.0308;
    const lng = data.longitude || -93.6319;

    if (typeof showPredictionOnMap === 'function') {
        setTimeout(() => {
            showPredictionOnMap(lat, lng, price, details);
        }, 300);
    }

    resultContainer.style.display = 'block';
    resultContainer.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function clearResult() {
    if (resultContainer) resultContainer.style.display = 'none';
    const resultMapContainer = document.getElementById('result-map-container');
    if (resultMapContainer) resultMapContainer.style.display = 'none';
}

// ============================================
//  HISTORIAL
//  ============================================

// ============================================
//  OPCIONES DEL FORMULARIO (barrios y tipos)
// ============================================

/**
 * Rellena los desplegables de barrio y tipo de vivienda desde la API.
 *
 * Los valores y los rangos NO están escritos en el HTML: se piden a
 * `GET /api/predictions/options`, que los deriva del contrato de características
 * del modelo. Así, si algún día se reentrena con otro dataset, la interfaz se
 * adapta sola en vez de mandar valores que el modelo no conoce.
 */
async function loadFormOptions() {
    const selectBarrio = document.getElementById('neighborhood');
    const selectTipo = document.getElementById('ms_subclass');

    if (!selectBarrio || !selectTipo) {
        console.warn('⚠️ No se encontraron los desplegables del formulario');
        return;
    }

    try {
        const response = await fetch(`${API_URL}/predictions/options`);
        if (!response.ok) {
            throw new Error(`Error ${response.status}: ${response.statusText}`);
        }

        const opciones = await response.json();

        // Barrios: se ordenan por precio mediano real, del más caro al más barato,
        // y se muestra ese precio como contexto.
        const barrios = (opciones.neighborhoods || []).slice().sort(
            (a, b) => (b.precio_mediano || 0) - (a.precio_mediano || 0)
        );
        selectBarrio.innerHTML = barrios.map(b => {
            const precio = b.precio_mediano
                ? ` — mediana ${formatearPrecio(b.precio_mediano)}`
                : '';
            return `<option value="${escapeHtml(b.valor)}">${escapeHtml(b.etiqueta)}${precio}</option>`;
        }).join('');

        // Tipos de vivienda
        selectTipo.innerHTML = (opciones.ms_subclass || []).map(t =>
            `<option value="${escapeHtml(t.valor)}">${escapeHtml(t.valor)} — ${escapeHtml(t.etiqueta)}</option>`
        ).join('');

        // Rangos reales del dataset para los campos numéricos
        aplicarRangos(opciones.rangos || {});

        const hintBarrio = document.getElementById('neighborhood-hint');
        if (hintBarrio) {
            hintBarrio.textContent = barrios.length
                ? `${barrios.length} barrios de ${opciones.dataset}. Precio mediano del conjunto: ${formatearPrecio(opciones.precio_mediano)}.`
                : '';
        }
        const hintTipo = document.getElementById('ms_subclass-hint');
        if (hintTipo) {
            hintTipo.textContent = 'Código MSSubClass del dataset de Ames.';
        }

        console.log(`✅ Opciones del formulario cargadas: ${barrios.length} barrios, ${(opciones.ms_subclass || []).length} tipos`);

    } catch (error) {
        console.error('❌ Error cargando las opciones del formulario:', error);
        selectBarrio.innerHTML = '<option value="">— Error al cargar —</option>';
        selectTipo.innerHTML = '<option value="">— Error al cargar —</option>';
    }
}

/** Aplica al HTML los límites reales del dataset (min/max de cada campo). */
function aplicarRangos(rangos) {
    Object.entries(rangos).forEach(([campo, rango]) => {
        if (!Array.isArray(rango) || rango.length !== 2) return;
        const [min, max] = rango;
        if (min === null || max === null) return;

        const input = document.getElementById(campo);
        if (!input) return;

        input.min = min;
        input.max = max;
        // Si el valor por defecto del HTML queda fuera del rango real, se ajusta.
        const valor = parseFloat(input.value);
        if (Number.isNaN(valor) || valor < min || valor > max) {
            input.value = Math.round((min + max) / 2);
        }
    });
}

// ============================================
//  HISTORIAL
// ============================================

async function loadHistory() {
    if (!historyContainer) {
        console.warn('⚠️ No se puede cargar historial: falta el contenedor');
        return;
    }

    // Sin sesión, el historial no se puede pedir. Antes se salía dejando el
    // "⏳ Cargando historial..." para siempre, porque ese texto está en el HTML
    // y nadie lo reemplazaba.
    if (!authToken) {
        historyContainer.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">🔒</div>
                <p>Inicia sesión para ver tu historial de predicciones.</p>
            </div>
        `;
        return;
    }

    historyContainer.innerHTML = '<div class="loading">⏳ Cargando historial...</div>';

    try {
        const response = await fetch(`${API_URL}/predictions/history?limit=20`, {
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            if (response.status === 401) {
                manejarSesionExpirada();
                return;
            }
            throw new Error(`Error ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();

        if (data.items && data.items.length > 0) {
            historyContainer.innerHTML = data.items.map(item => `
                <div class="history-item">
                    <div>
                        <div class="price">$ ${item.predicted_price.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</div>
                        <div class="details">
                            🏘️ ${escapeHtml(item.neighborhood || '—')}
                            · ${item.gr_liv_area_m2} m²
                            · ${item.bedrooms} dorm · ${item.bathrooms} baños
                            · calidad ${item.overall_qual}/10
                        </div>
                    </div>
                    <div class="date">${new Date(item.created_at).toLocaleDateString('es-PE')}</div>
                </div>
            `).join('');
        } else {
            historyContainer.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">📭</div>
                    <p>Aún no tienes predicciones guardadas.</p>
                    <p style="font-size:0.8rem;">¡Haz tu primera predicción!</p>
                </div>
            `;
        }

    } catch (error) {
        console.error('❌ Error cargando historial:', error);
        historyContainer.innerHTML = `<p style="color: #e17055; text-align: center;">❌ Error cargando historial</p>`;
    }
}

// ============================================
//  VERIFICAR SESIÓN GUARDADA
//  ============================================

function checkSavedSession() {
    const savedToken = localStorage.getItem('authToken');
    const savedUser = localStorage.getItem('currentUser');

    if (savedToken && savedUser) {
        try {
            authToken = savedToken;
            currentUser = JSON.parse(savedUser);
            showAuthenticated();
        } catch (e) {
            console.error('❌ Error al restaurar sesión:', e);
            localStorage.removeItem('authToken');
            localStorage.removeItem('currentUser');
        }
    } else {
        showUnauthenticated();
    }
}

// ============================================
//  EXPORTAR PDF
//  ============================================

function exportPDF() {
    const element = document.getElementById('result-container');
    if (!element || element.style.display === 'none') {
        showMessage('❌ No hay resultado para exportar', 'error');
        return;
    }

    if (typeof html2pdf === 'undefined') {
        showMessage('❌ Biblioteca PDF no cargada', 'error');
        return;
    }

    try {
        html2pdf()
            .set({
                margin: 1,
                filename: 'prediccion_vivienda.pdf',
                html2canvas: { scale: 2 },
                jsPDF: { unit: 'in', format: 'a4', orientation: 'portrait' }
            })
            .from(element)
            .save();
        showMessage('✅ PDF generado correctamente', 'success');
    } catch (error) {
        console.error('❌ Error generando PDF:', error);
        showMessage('❌ Error al generar PDF', 'error');
    }
}

// ============================================
//  VER EN MAPA
//  ============================================

function showOnMap() {
    const resultMapContainer = document.getElementById('result-map-container');
    if (!resultMapContainer) return;

    if (resultMapContainer.style.display === 'none') {
        resultMapContainer.style.display = 'block';
        // Forzar actualización del mapa
        if (typeof mapResult !== 'undefined' && mapResult) {
            setTimeout(() => {
                mapResult.invalidateSize();
            }, 300);
        }
        showMessage('📍 Mapa mostrado', 'info');
    } else {
        resultMapContainer.style.display = 'none';
    }
}

// ============================================
//  EXPORTAR FUNCIONES GLOBALES
//  ============================================

window.API_URL = API_URL;
window.authToken = authToken;
window.currentUser = currentUser;
window.logout = logout;
window.clearResult = clearResult;
window.loadHistory = loadHistory;
window.showResult = showResult;
window.showMessage = showMessage;
window.exportPDF = exportPDF;
window.showOnMap = showOnMap;
window.showAuthenticated = showAuthenticated;
window.showUnauthenticated = showUnauthenticated;

console.log('✅ script.js cargado correctamente');