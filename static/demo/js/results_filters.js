function initResultsFilters() {
    console.debug('Initializing results filters');
    // Collect all row elements and attach data attributes
    const rows = Array.from(document.querySelectorAll('tbody tr'));
    if (!rows.length) {
        console.debug('No result rows found');
    }

    function parsePrice(text) {
        if (!text) return Infinity;
        // Remove non-digits
        return parseFloat(text.replace(/[^0-9.-]+/g, '')) || Infinity;
    }

    function extractRowData(row) {
        // Prefer structured attributes if present
        const dataPrice = row.getAttribute('data-price');
        const dataStops = row.getAttribute('data-stops');
        const priceEl = row.querySelector('.price');
        const price = dataPrice ? parseFloat(dataPrice) : (priceEl ? parsePrice(priceEl.textContent) : Infinity);
        let stops = dataStops ? parseInt(dataStops, 10) : 0;
        // Fallback heuristic if no data-stops attribute
        if (!dataStops) {
            const hasSecond = !!row.querySelector('td:first-child p + p');
            stops = hasSecond ? 1 : 0;
        }
        const departureText = row.querySelector('td:first-child') ? row.querySelector('td:first-child').textContent : '';
        // Extract departure time (first 5 char like HH:MM)
        const timeMatch = departureText.match(/(\d{2}:\d{2})/);
        const depTime = timeMatch ? timeMatch[0] : '99:99';
        return {row, price, stops, depTime};
    }

    const data = rows.map(extractRowData);

    // Build set of airlines from data and populate airlinesContainer
    const airlinesSet = new Set();
    data.forEach(d => {
        try {
            // attempt to find carrier codes
            const rowJson = d.row.querySelector('.flight-json');
            if (rowJson) {
                const raw = rowJson.getAttribute('data-flight');
                const parsed = JSON.parse(raw.replace(/&quot;/g, '"'));
                // heuristics: carrierCode in itineraries segments
                if (parsed.itineraries) {
                    parsed.itineraries.forEach(it => it.segments.forEach(s => airlinesSet.add(s.carrierCode)));
                } else if (parsed.flightOffers) {
                    parsed.flightOffers.forEach(fo => fo.itineraries.forEach(it => it.segments.forEach(s => airlinesSet.add(s.carrierCode))));
                }
            }
        } catch (e) {
            // ignore parse errors
        }
    });

    const airlinesContainer = document.getElementById('airlinesContainer');
    if (airlinesContainer) {
        const sorted = Array.from(airlinesSet).sort();
        sorted.forEach(code => {
            const id = 'air_' + code;
            const label = document.createElement('label');
            label.className = 'd-block';
            label.innerHTML = `<input type="checkbox" value="${code}" id="${id}" class="airline-checkbox"> ${code}`;
            airlinesContainer.appendChild(label);
        });
    }

    const sortSelect = document.getElementById('sortSelect');
    const stopsFilter = document.getElementById('stopsFilter');
    const minPrice = document.getElementById('minPrice');
    const maxPrice = document.getElementById('maxPrice');
    const applyFilters = document.getElementById('applyFilters');
    const clearFilters = document.getElementById('clearFilters');
    const resultsCount = document.getElementById('resultsCount');

    if (!applyFilters || !clearFilters) {
        console.debug('Filter controls not found in DOM');
        return; // Nothing to do
    }

    function render(list) {
        const tbody = document.querySelector('tbody');
        // Remove all children
        while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
        for (const item of list) {
            tbody.appendChild(item.row);
        }
        resultsCount.textContent = list.length;
    }

    function applySort(list) {
        const mode = sortSelect.value;
        if (mode === 'cheapest') {
            list.sort((a, b) => a.price - b.price);
        } else if (mode === 'earliest') {
            list.sort((a, b) => a.depTime.localeCompare(b.depTime));
        } else {
            // default: best (keep original order)
        }
    }

    function applyFilterAndSort() {
        let filtered = data.slice();

        // Stops filter
        const stopsVal = stopsFilter.value;
        if (stopsVal !== 'any') {
            const val = parseInt(stopsVal, 10);
            if (val === 2) {
                filtered = filtered.filter(d => d.stops >= 2);
            } else {
                filtered = filtered.filter(d => d.stops === val);
            }
        }

        // Price filters
        const min = parseFloat(minPrice.value) || -Infinity;
        const max = parseFloat(maxPrice.value) || Infinity;
        filtered = filtered.filter(d => d.price >= min && d.price <= max);

        // Departure time bucket
        const depBucket = (document.getElementById('departureTime') || {}).value || 'any';
        if (depBucket && depBucket !== 'any') {
            filtered = filtered.filter(d => {
                const t = d.depTime; // 'HH:MM'
                const parts = t.split(':');
                if (parts.length < 2) return false;
                const h = parseInt(parts[0], 10);
                if (depBucket === 'morning') return h >= 4 && h <= 11;
                if (depBucket === 'afternoon') return h >= 12 && h <= 17;
                if (depBucket === 'evening') return h >= 18 && h <= 21;
                if (depBucket === 'night') return (h >= 22 || h <= 3);
                return true;
            });
        }

        // Airline checkboxes
        const checkedAirlines = Array.from(document.querySelectorAll('.airline-checkbox:checked')).map(i => i.value);
        if (checkedAirlines.length) {
            filtered = filtered.filter(d => {
                try {
                    const rowJson = d.row.querySelector('.flight-json');
                    if (!rowJson) return false;
                    const parsed = JSON.parse(rowJson.getAttribute('data-flight').replace(/&quot;/g, '"'));
                    const carriers = new Set();
                    if (parsed.itineraries) parsed.itineraries.forEach(it => it.segments.forEach(s => carriers.add(s.carrierCode)));
                    else if (parsed.flightOffers) parsed.flightOffers.forEach(fo => fo.itineraries.forEach(it => it.segments.forEach(s => carriers.add(s.carrierCode))));
                    return checkedAirlines.some(c => carriers.has(c));
                } catch (e) {
                    return false;
                }
            });
        }

        // Trip type filter
        const tripType = (document.getElementById('filterTripType') || {}).value || 'any';
        if (tripType && tripType !== 'any') {
            filtered = filtered.filter(d => {
                try {
                    const rowJson = d.row.querySelector('.flight-json');
                    if (!rowJson) return false;
                    const parsed = JSON.parse(rowJson.getAttribute('data-flight').replace(/&quot;/g, '"'));
                    // Heuristic: if there are itineraries length > 1, it's round-trip; if only 1, one-way; multi-city if more than 2 segments/itineraries
                    const itins = parsed.itineraries || (parsed.flightOffers && parsed.flightOffers[0] && parsed.flightOffers[0].itineraries) || [];
                    if (tripType === 'one-way') return itins.length === 1;
                    if (tripType === 'round-trip') return itins.length === 2;
                    if (tripType === 'multi-city') return itins.length > 2 || itins.some(it => it.segments && it.segments.length > 2);
                    return true;
                } catch (e) { return false; }
            });
        }

        // Cabin class filter
        const cabin = (document.getElementById('filterCabinClass') || {}).value || 'any';
        if (cabin && cabin !== 'any') {
            filtered = filtered.filter(d => {
                try {
                    const rowJson = d.row.querySelector('.flight-json');
                    if (!rowJson) return false;
                    const parsed = JSON.parse(rowJson.getAttribute('data-flight').replace(/&quot;/g, '"'));
                    // Search for cabin in pricing or travelerPricings if present
                    const offers = parsed.flightOffers || [parsed];
                    for (const offer of offers) {
                        const cabinInfo = offer.travelers || offer.travelerPricings || [];
                        // try to look into fare details
                        if (offer.fareDetailsBySegment) {
                            for (const key in offer.fareDetailsBySegment) {
                                const seg = offer.fareDetailsBySegment[key];
                                if (seg.cabin && seg.cabin.toLowerCase().includes(cabin.replace('_',''))) return true;
                            }
                        }
                        if (offer.class && typeof offer.class === 'string' && offer.class.toLowerCase().includes(cabin.replace('_',''))) return true;
                    }
                    return false;
                } catch (e) { return false; }
            });
        }

        // Passenger count filter (availability heuristic)
        const pax = parseInt((document.getElementById('filterPassengers') || {}).value, 10) || 1;
        if (pax > 1) {
            filtered = filtered.filter(d => {
                try {
                    const rowJson = d.row.querySelector('.flight-json');
                    if (!rowJson) return false;
                    const parsed = JSON.parse(rowJson.getAttribute('data-flight').replace(/&quot;/g, '"'));
                    // Heuristic: look for available seats or number of travelers allowed in the offer
                    if (parsed.numberOfBookableSeats && parsed.numberOfBookableSeats >= pax) return true;
                    if (parsed.travelers && parsed.travelers.length >= pax) return true;
                    // fallback: assume available
                    return true;
                } catch (e) { return false; }
            });
        }

        applySort(filtered);
        render(filtered);
    }

    applyFilters.addEventListener('click', function (e) {
        e.preventDefault();
        console.debug('Apply filters clicked');
        applyFilterAndSort();
    });

    clearFilters.addEventListener('click', function (e) {
        e.preventDefault();
        console.debug('Clear filters clicked');
        sortSelect.value = 'best';
        stopsFilter.value = 'any';
        minPrice.value = '';
        maxPrice.value = '';
        render(data.slice());
    });

    // initialize count
    render(data.slice());
}

// Init right away if the DOM is already ready, otherwise wait for DOMContentLoaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initResultsFilters);
} else {
    // DOM already ready
    initResultsFilters();
}
