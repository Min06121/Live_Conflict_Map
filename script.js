(function() {
    'use strict';

    // === 1. Configuration & Constants ===
    const API_BASE_URL = 'http://localhost:5001/api'; // Your Flask API server
    const NEWS_API_URL = `${API_BASE_URL}/news`;
    const COUNTRIES_GEOJSON_URL = 'countries_geo.json'; // 프로젝트 루트에 있는 파일명으로 변경
    const NEWS_ITEMS_PER_PAGE = 10;
    const USER_MARKERS_STORAGE_KEY = 'userConflictMarkers';
    const INITIAL_MAP_CENTER = [20, 0]; // Global view center
    const INITIAL_MAP_ZOOM = 2;
    const COUNTRY_FOCUS_ZOOM = 5;
    const DEFAULT_NEWS_IMAGE = 'images/placeholder-news-image.png'; // Create this placeholder image in an 'images' folder
    const US_DATE_TIME_LOCALE = 'en-US';
    const US_TIME_ZONE_DISPLAY = 'America/New_York'; // For header clock

    // === 2. DOM Element Cache ===
    const DOM = {
        dateDisplay: document.getElementById('current-date-display'),
        uiMessageArea: document.getElementById('ui-message-area'),
        mapElement: document.getElementById('map'),
        currentYearSpan: document.getElementById('current-year'),
        newsFeedItemsWrapper: document.getElementById('news-feed-items-wrapper'),
        newsDatePicker: document.getElementById('news-date-picker'),
        countrySelect: document.getElementById('country-select'),
        keywordSearchInput: document.getElementById('keyword-search-input'),
        keywordSearchButton: document.getElementById('keyword-search-btn'),
        prevNewsButton: document.getElementById('prev-news-btn'),
        nextNewsButton: document.getElementById('next-news-btn'),
        newsStatusDisplay: document.getElementById('news-status-display'),
        markerForm: {
            section: document.getElementById('add-marker-section'),
            toggle: document.getElementById('add-marker-toggle'),
            form: document.getElementById('add-marker-form'),
            name: document.getElementById('marker-name'),
            lat: document.getElementById('marker-lat'),
            lng: document.getElementById('marker-lng'),
            info: document.getElementById('marker-info'),
            clearButton: document.getElementById('clear-markers-btn')
        }
    };

    // === 3. Application State ===
    const state = {
        map: null,
        markerClusterGroup: null,
        userAddedMarkersLayer: null,
        geoJsonLayer: null,
        userAddedMarkers: [],
        currentNewsPage: 1,
        totalNewsItems: 0,
        currentSelectedNewsDateStr: '', // YYYY-MM-DD
        currentKeywordQuery: '',
        currentCountryFilterISO: null, // For filtering news by country ISO_A2 code
        isLoadingNews: false,
        countryData: null, // Cache for GeoJSON features
        headerTimeIntervalId: null
    };

    // === 4. Utility Functions ===
    /**
     * Fetches data from a URL with error handling and loading indication.
     */
    async function fetchData(url, options = {}) {
        if (state.isLoadingNews && url.startsWith(NEWS_API_URL)) return null; // Prevent concurrent news fetches

        if (url.startsWith(NEWS_API_URL)) {
            state.isLoadingNews = true;
            showLoadingIndicator(true, 'news-feed');
        }

        try {
            const response = await fetch(url, options);
            if (!response.ok) {
                let errorData = { message: `HTTP error! Status: ${response.status}` };
                try {
                    errorData = await response.json();
                } catch (e) { /* Ignore if response is not JSON */ }
                console.error(`Error fetching data from ${url}: ${response.status} ${response.statusText}`, errorData);
                showUIMessage(`Error: ${errorData.error || errorData.message || response.statusText}`, 'error');
                return null;
            }
            return await response.json();
        } catch (error) {
            console.error(`Failed to fetch data from ${url}:`, error);
            showUIMessage('Network error. The API server might be down or unreachable.', 'error');
            return null;
        } finally {
            if (url.startsWith(NEWS_API_URL)) {
                state.isLoadingNews = false;
                showLoadingIndicator(false, 'news-feed');
            }
        }
    }

    /**
     * Displays a UI message to the user.
     */
    function showUIMessage(message, type = 'info', duration = 5000) {
        if (!DOM.uiMessageArea) return;
        DOM.uiMessageArea.textContent = message;
        DOM.uiMessageArea.className = `ui-message ${type}`; // CSS classes: ui-message, info/error/success
        DOM.uiMessageArea.style.display = 'block';
        DOM.uiMessageArea.setAttribute('role', type === 'error' ? 'alert' : 'status');

        if (duration > 0) {
            setTimeout(() => {
                DOM.uiMessageArea.style.display = 'none';
                DOM.uiMessageArea.textContent = '';
            }, duration);
        }
    }

    /**
     * Shows or hides a loading indicator, typically in the news feed.
     */
    function showLoadingIndicator(isLoading, area = 'news-feed') { // area can be 'news-feed' or 'map' etc.
        const targetWrapper = area === 'news-feed' ? DOM.newsFeedItemsWrapper : DOM.mapElement;
        if (!targetWrapper) return;

        const existingLoadingMsg = targetWrapper.querySelector('.loading-message'); // Standardized class
        if (isLoading) {
            if (!existingLoadingMsg) {
                const loadingElement = document.createElement('p');
                loadingElement.className = 'loading-message'; // Use this class for styling
                loadingElement.textContent = area === 'news-feed' ? 'Loading news data...' : 'Loading map data...';
                // If news-feed, clear previous items before showing loading.
                if (area === 'news-feed') targetWrapper.innerHTML = '';
                targetWrapper.appendChild(loadingElement);
            }
        } else {
            if (existingLoadingMsg) {
                existingLoadingMsg.remove();
            }
        }
    }

    /**
     * Escapes HTML special characters in a string to prevent XSS.
     */
    function escapeHTML(str) {
        if (typeof str !== 'string') return String(str); // Ensure it's a string
        return str.replace(/[&<>"']/g, match => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
        }[match]));
    }

    // === 5. Map Initialization and Functions ===
    function initializeMap() {
        if (!DOM.mapElement) {
            console.error("Map DOM element not found. Map cannot be initialized.");
            showUIMessage("Error: Map container not found on page.", "error", 0);
            return;
        }
        try {
            state.map = L.map(DOM.mapElement, {
                // preferCanvas: true // Consider for very large number of markers/layers if performance is an issue
            }).setView(INITIAL_MAP_CENTER, INITIAL_MAP_ZOOM);

            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> contributors',
                maxZoom: 18, // Standard max zoom
                minZoom: 2   // Prevent zooming out too much
            }).addTo(state.map);

            state.markerClusterGroup = L.markerClusterGroup().addTo(state.map); // For news markers if geocoded
            state.userAddedMarkersLayer = L.layerGroup().addTo(state.map);
        } catch (error) {
            console.error("Leaflet map initialization failed:", error);
            showUIMessage("Map could not be loaded. Please try again later.", "error", 0);
        }
    }

    /**
     * Gets the fill color for a country based on its status, using CSS variables.
     */
    function getCountryFillColor(status) {
        const lowerStatus = status ? status.toLowerCase().trim() : 'unknown';
        let cssVarName;
        switch (lowerStatus) {
            case 'war': cssVarName = '--status-war-fill'; break;
            case 'danger': cssVarName = '--status-danger-fill'; break;
            case 'tension': cssVarName = '--status-tension-fill'; break;
            case 'stable': cssVarName = '--status-stable-fill'; break;
            default: cssVarName = '--status-default-country-fill';
        }
        return getComputedStyle(document.documentElement).getPropertyValue(cssVarName.trim()) || 'rgba(200,200,200,0.3)';
    }

    /**
     * Gets the stroke color for a country based on its status, using CSS variables.
     */
    function getCountryStrokeColor(status) {
        const lowerStatus = status ? status.toLowerCase().trim() : 'unknown';
        let cssVarName;
        switch (lowerStatus) {
            case 'war': cssVarName = '--status-war-stroke'; break;
            case 'danger': cssVarName = '--status-danger-stroke'; break;
            case 'tension': cssVarName = '--status-tension-stroke'; break;
            case 'stable': cssVarName = '--status-stable-stroke'; break;
            default: cssVarName = '--status-default-country-stroke';
        }
        return getComputedStyle(document.documentElement).getPropertyValue(cssVarName.trim()) || '#aaaaaa';
    }

    /**
     * Loads GeoJSON country data, styles it based on status, and adds to map.
     */
    async function loadAndAddGeoJsonLayer() {
        if (!state.map) return;
        const geoJsonData = await fetchData(COUNTRIES_GEOJSON_URL);
        if (!geoJsonData) {
            showUIMessage("Could not load country boundary data.", "error");
            return;
        }
        state.countryData = geoJsonData; // Cache data
        populateCountrySelect(geoJsonData.features);

        if (state.geoJsonLayer) {
            state.map.removeLayer(state.geoJsonLayer);
        }

        state.geoJsonLayer = L.geoJSON(geoJsonData, {
            style: feature => {
                const status = feature.properties.status; // Assumes 'status' property in GeoJSON
                return {
                    weight: 1.2,
                    opacity: 0.9,
                    color: getCountryStrokeColor(status),
                    fillOpacity: 0.7, // Adjust as needed, CSS var might have alpha
                    fillColor: getCountryFillColor(status)
                };
            },
            onEachFeature: (feature, layer) => {
                const countryName = escapeHTML(feature.properties.ADMIN || feature.properties.name || 'Unknown Country');
                const statusText = escapeHTML(feature.properties.status || 'N/A');
                const popupContent = `<strong>${countryName}</strong><br>Status: ${statusText}`;
                layer.bindPopup(popupContent);
                layer.on('click', () => handleGeoJsonFeatureClick(feature, layer));
            }
        }).addTo(state.map);
        console.log("GeoJSON layer (re)loaded with status-based styling.");
    }

    /**
     * Handles click events on a GeoJSON country feature.
     * Filters news for the clicked country.
     */
    function handleGeoJsonFeatureClick(feature, layer) {
        const countryName = feature.properties.ADMIN || feature.properties.name;
        const countryISO = feature.properties.ISO_A2; // Assumes 'ISO_A2' property
        const statusText = feature.properties.status || 'N/A';

        showUIMessage(`Filtering news for ${escapeHTML(countryName)} (Status: ${escapeHTML(statusText)})`, 'info', 3500);
        if(state.map) state.map.fitBounds(layer.getBounds());

        if (DOM.countrySelect && countryISO) {
            DOM.countrySelect.value = countryISO;
        }
        
        state.currentCountryFilterISO = countryISO || null;
        state.currentNewsPage = 1;
        state.currentKeywordQuery = ''; // Optionally clear keyword search
        if (DOM.keywordSearchInput) DOM.keywordSearchInput.value = '';
        
        updateNewsFeed();
    }

    /**
     * Populates the country select dropdown.
     */
    function populateCountrySelect(features) {
        if (!DOM.countrySelect) return;
        DOM.countrySelect.innerHTML = '<option value="world">World View</option>';
        const countries = features
            .map(f => ({ name: f.properties.ADMIN || f.properties.name, iso: f.properties.ISO_A2 }))
            .filter(c => c.name && c.iso) // Ensure valid name and ISO
            .sort((a, b) => a.name.localeCompare(b.name));

        countries.forEach(country => {
            const option = document.createElement('option');
            option.value = country.iso;
            option.textContent = country.name;
            DOM.countrySelect.appendChild(option);
        });
    }

    /**
     * Handles changes to the country select dropdown.
     */
    function handleCountryChange() {
        if (!DOM.countrySelect) return;
        const selectedISO = DOM.countrySelect.value;
        state.currentCountryFilterISO = selectedISO === 'world' ? null : selectedISO;

        if (selectedISO === 'world' && state.map) {
            state.map.setView(INITIAL_MAP_CENTER, INITIAL_MAP_ZOOM);
        } else if (state.countryData && state.geoJsonLayer && state.map) {
            state.geoJsonLayer.eachLayer(layer => {
                if (layer.feature.properties.ISO_A2 === selectedISO) {
                    state.map.fitBounds(layer.getBounds());
                }
            });
        }
        state.currentNewsPage = 1;
        state.currentKeywordQuery = '';
        if (DOM.keywordSearchInput) DOM.keywordSearchInput.value = '';
        updateNewsFeed();
    }

    // === 6. News Feed Functions ===
    /**
     * Fetches news data from the API based on current filters and page.
     */
    async function fetchNewsItems(page = 1, limit = NEWS_ITEMS_PER_PAGE, dateStr = null, keywordStr = null, countryISO = null) {
        let url = `${NEWS_API_URL}?page=${page}&limit=${limit}`;
        if (dateStr) url += `&date=${dateStr}`;
        if (keywordStr && keywordStr.trim()) url += `&keyword=${encodeURIComponent(keywordStr.trim())}`;
        if (countryISO) url += `&country_iso=${encodeURIComponent(countryISO)}`;
        
        console.log("Fetching news from API:", url);
        return await fetchData(url); // Uses the centralized fetchData utility
    }

    /**
     * Updates the news feed by fetching and displaying news items.
     */
    async function updateNewsFeed() {
        const apiResponse = await fetchNewsItems(
            state.currentNewsPage,
            NEWS_ITEMS_PER_PAGE,
            state.currentSelectedNewsDateStr,
            state.currentKeywordQuery,
            state.currentCountryFilterISO
        );

        if (apiResponse) {
            displayNewsItems(apiResponse.news || []);
            state.totalNewsItems = apiResponse.total_count || 0;
        } else {
            // If apiResponse is null (fetchData handled error message), display empty state
            displayNewsItems([]);
            state.totalNewsItems = 0;
        }
        updateNewsPaginationControls();
    }

    /**
     * Renders news items to the DOM.
     */
    function displayNewsItems(newsItems) {
        if (!DOM.newsFeedItemsWrapper) return;
        DOM.newsFeedItemsWrapper.innerHTML = ''; // Clear previous items

        if (!newsItems || newsItems.length === 0) {
            let message = 'No news articles found for the selected criteria.';
            if (state.currentKeywordQuery) message = `No news articles match '${escapeHTML(state.currentKeywordQuery)}' for the current filters.`;
            else if (state.currentSelectedNewsDateStr) message = `No news articles found for ${escapeHTML(state.currentSelectedNewsDateStr)}.`;
            else if (state.currentCountryFilterISO) {
                const selectedCountryOption = DOM.countrySelect ? DOM.countrySelect.options[DOM.countrySelect.selectedIndex] : null;
                const countryName = selectedCountryOption ? selectedCountryOption.text : state.currentCountryFilterISO;
                message = `No news articles found for ${escapeHTML(countryName)}.`;
            }
            DOM.newsFeedItemsWrapper.innerHTML = `<p class="no-news">${message}</p>`;
            return;
        }

        const fragment = document.createDocumentFragment();
        newsItems.forEach(item => {
            const newsDiv = document.createElement('div');
            newsDiv.className = 'news-item';

            const title = escapeHTML(item.title || 'Untitled News');
            const link = escapeHTML(item.link || '#');
            const description = escapeHTML(item.description || 'No description available.');
            const time = escapeHTML(item.time || 'Date N/A'); // API provides formatted US time
            const relevance = item.relevance_score ? parseFloat(item.relevance_score).toFixed(2) : null;
            const imageUrl = item.image_url;

            let imageElement = '';
            if (imageUrl) {
                imageElement = `<img src="${escapeHTML(imageUrl)}" alt="Image for: ${title}" class="news-item-image" loading="lazy" onerror="this.style.display='none'; this.parentElement.querySelector('.placeholder-image-div')?.style.display='block';">`;
                 // Fallback div if actual image fails, hidden by default.
                imageElement += `<div class="placeholder-image-div" style="display:none;"><img src="${DEFAULT_NEWS_IMAGE}" alt="Default news image" class="news-item-image placeholder"></div>`;
            } else if (DEFAULT_NEWS_IMAGE) {
                imageElement = `<div class="placeholder-image-div"><img src="${DEFAULT_NEWS_IMAGE}" alt="Default news image" class="news-item-image placeholder"></div>`;
            }


            newsDiv.innerHTML = `
                ${imageElement}
                <div class="news-item-content">
                    <div class="news-item-header"><span class="news-date">${time}</span></div>
                    <h3 class="title"><a href="${link}" target="_blank" rel="noopener noreferrer">${title}</a></h3>
                    <p class="description">${description}</p>
                    ${relevance ? `<p class="relevance">Relevance: ${relevance}</p>` : ''}
                </div>
            `;
            fragment.appendChild(newsDiv);
        });
        DOM.newsFeedItemsWrapper.appendChild(fragment);
    }

    /**
     * Updates the pagination controls (buttons and status display).
     */
    function updateNewsPaginationControls() {
        if (!DOM.newsStatusDisplay) return;
        const startIndex = state.totalNewsItems > 0 ? (state.currentNewsPage - 1) * NEWS_ITEMS_PER_PAGE + 1 : 0;
        const endIndex = Math.min(startIndex + NEWS_ITEMS_PER_PAGE - 1, state.totalNewsItems);
        DOM.newsStatusDisplay.textContent = `${startIndex}-${endIndex} of ${state.totalNewsItems}`;

        if (DOM.prevNewsButton) DOM.prevNewsButton.disabled = (state.currentNewsPage <= 1);
        const totalPages = Math.ceil(state.totalNewsItems / NEWS_ITEMS_PER_PAGE);
        if (DOM.nextNewsButton) DOM.nextNewsButton.disabled = (state.currentNewsPage >= totalPages);
    }

    function handlePrevNews() { if (state.currentNewsPage > 1) { state.currentNewsPage--; updateNewsFeed(); }}
    function handleNextNews() {
        const totalPages = Math.ceil(state.totalNewsItems / NEWS_ITEMS_PER_PAGE);
        if (state.currentNewsPage < totalPages) { state.currentNewsPage++; updateNewsFeed(); }
    }

    function handleKeywordSearch() {
        state.currentKeywordQuery = DOM.keywordSearchInput ? DOM.keywordSearchInput.value.trim() : "";
        state.currentNewsPage = 1;
        // When searching by keyword, we might want to clear the country filter
        // or keep it. For now, let's keep it.
        // If clearing: state.currentCountryFilterISO = null; if(DOM.countrySelect) DOM.countrySelect.value = 'world';
        updateNewsFeed();
    }

    // === 7. User Added Marker Functions ===
    function loadUserAddedMarkers() {
        const storedMarkers = localStorage.getItem(USER_MARKERS_STORAGE_KEY);
        if (storedMarkers) {
            try {
                state.userAddedMarkers = JSON.parse(storedMarkers);
                renderUserAddedMarkers();
            } catch (e) {
                console.error("Error parsing user markers from localStorage:", e);
                state.userAddedMarkers = [];
                localStorage.removeItem(USER_MARKERS_STORAGE_KEY); // Clear corrupted data
            }
        }
    }

    function saveUserAddedMarkers() {
        try {
            localStorage.setItem(USER_MARKERS_STORAGE_KEY, JSON.stringify(state.userAddedMarkers));
        } catch (e) {
            console.error("Error saving user markers to localStorage:", e);
            showUIMessage("Could not save your custom marker. Local storage might be full or disabled.", "error");
        }
    }

    function renderUserAddedMarkers() {
        if (!state.userAddedMarkersLayer || !state.map) return;
        state.userAddedMarkersLayer.clearLayers();
        state.userAddedMarkers.forEach(markerData => {
            if (typeof markerData.lat !== 'number' || typeof markerData.lng !== 'number') return; // Basic validation
            L.marker([markerData.lat, markerData.lng])
                .bindPopup(`<strong>${escapeHTML(markerData.name)}</strong><br>${escapeHTML(markerData.info)}`)
                .addTo(state.userAddedMarkersLayer);
        });
    }

    function handleAddNewMarkerFromForm(event) {
        event.preventDefault();
        if (!DOM.markerForm.name || !DOM.markerForm.lat || !DOM.markerForm.lng) return;

        const name = DOM.markerForm.name.value.trim();
        const lat = parseFloat(DOM.markerForm.lat.value);
        const lng = parseFloat(DOM.markerForm.lng.value);
        const info = DOM.markerForm.info.value.trim();

        if (!name) { showUIMessage('Marker name is required.', 'error'); return; }
        if (isNaN(lat) || lat < -90 || lat > 90) { showUIMessage('Invalid latitude. Must be between -90 and 90.', 'error'); return; }
        if (isNaN(lng) || lng < -180 || lng > 180) { showUIMessage('Invalid longitude. Must be between -180 and 180.', 'error'); return; }

        const newMarker = { id: Date.now().toString(), name, lat, lng, info };
        state.userAddedMarkers.push(newMarker);
        saveUserAddedMarkers();
        renderUserAddedMarkers();
        showUIMessage('New event marker added successfully!', 'success');
        if (DOM.markerForm.form) DOM.markerForm.form.reset();
        if (state.map) state.map.setView([lat, lng], COUNTRY_FOCUS_ZOOM);
    }

    function handleClearUserMarkers() {
        if (state.userAddedMarkers.length === 0) {
            showUIMessage('No user-added markers to clear.', 'info');
            return;
        }
        if (confirm('Are you sure you want to delete ALL user-added markers? This action cannot be undone.')) {
            state.userAddedMarkers = [];
            saveUserAddedMarkers();
            renderUserAddedMarkers();
            showUIMessage('All user-added markers have been cleared.', 'info');
        }
    }

    function toggleMarkerForm() {
        if (!DOM.markerForm.section || !DOM.markerForm.toggle) return;
        const isCollapsed = DOM.markerForm.section.classList.toggle('collapsed');
        const contentArea = document.getElementById('add-marker-form-content'); // HTML ID

        DOM.markerForm.toggle.textContent = isCollapsed ? 'Add New Event Marker (Click to Expand)' : 'Add New Event Marker (Click to Collapse)';
        DOM.markerForm.toggle.setAttribute('aria-expanded', String(!isCollapsed));
        if (contentArea) contentArea.setAttribute('aria-hidden', String(isCollapsed));
    }

    // === 8. General UI and Initialization ===
    /**
     * Displays the current date and time in US Eastern Time (or specified timezone).
     * Updates every minute.
     */
    function displayCurrentDateTimeInUS() {
        if (!DOM.dateDisplay) return;
        const now = new Date();
        const options = {
            weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
            hour: 'numeric', minute: '2-digit', /* second: '2-digit', */
            timeZone: US_TIME_ZONE_DISPLAY,
            hour12: true
        };
        try {
            DOM.dateDisplay.textContent = new Intl.DateTimeFormat(US_DATE_TIME_LOCALE, options).format(now);
        } catch (e) {
            console.warn(`Intl.DateTimeFormat with timezone ${US_TIME_ZONE_DISPLAY} failed. Using fallback.`, e);
            // Fallback to simpler local time display if Intl fails (e.g., unsupported timezone in very old browsers)
            DOM.dateDisplay.textContent = now.toLocaleString(US_DATE_TIME_LOCALE, {
                weekday: 'short', year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit'
            });
        }
    }

    function updateFooterYear() {
        if (DOM.currentYearSpan) {
            DOM.currentYearSpan.textContent = new Date().getFullYear();
        }
    }

    /**
     * Initializes the entire application.
     */
    function initializeApp() {
        if (!DOM.mapElement || !DOM.newsFeedItemsWrapper) {
            console.error("Essential DOM elements (map or news feed wrapper) are missing. Application cannot initialize.");
            document.body.innerHTML = '<p style="color:red; padding:20px; text-align:center;">Critical error: Page components missing. Please contact support.</p>';
            return;
        }

        // Initial UI setup
        displayCurrentDateTimeInUS();
        if (state.headerTimeIntervalId) clearInterval(state.headerTimeIntervalId);
        state.headerTimeIntervalId = setInterval(displayCurrentDateTimeInUS, 60000); // Update header time every minute
        updateFooterYear();

        // Initialize map and load geographic data
        initializeMap();
        if (state.map) { // Ensure map initialized before loading layers
            loadAndAddGeoJsonLayer().catch(err => console.error("Error during initial GeoJSON load:", err));
            loadUserAddedMarkers();
        }

        // Setup event listeners
        if (DOM.newsDatePicker) {
            DOM.newsDatePicker.addEventListener('change', (event) => {
                state.currentSelectedNewsDateStr = event.target.value;
                state.currentNewsPage = 1;
                updateNewsFeed();
            });
        }
        if (DOM.keywordSearchButton) DOM.keywordSearchButton.addEventListener('click', handleKeywordSearch);
        if (DOM.keywordSearchInput) {
            DOM.keywordSearchInput.addEventListener('keypress', e => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    handleKeywordSearch();
                }
            });
        }
        if (DOM.prevNewsButton) DOM.prevNewsButton.addEventListener('click', handlePrevNews);
        if (DOM.nextNewsButton) DOM.nextNewsButton.addEventListener('click', handleNextNews);
        if (DOM.countrySelect) DOM.countrySelect.addEventListener('change', handleCountryChange);
        
        if (DOM.markerForm.form) DOM.markerForm.form.addEventListener('submit', handleAddNewMarkerFromForm);
        if (DOM.markerForm.clearButton) DOM.markerForm.clearButton.addEventListener('click', handleClearUserMarkers);
        if (DOM.markerForm.toggle) DOM.markerForm.toggle.addEventListener('click', toggleMarkerForm);
        
        // Initial news load
        updateNewsFeed();
    }

    // --- Application Start ---
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeApp);
    } else {
        initializeApp(); // DOM already loaded
    }

})();
