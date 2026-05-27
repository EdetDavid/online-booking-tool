function initResultsFilters() {
    const list = document.getElementById('resultsList');
    const cards = Array.from(document.querySelectorAll('.flight-result-card, .hotel-result-card'));
    const airlinesContainer = document.getElementById('airlinesContainer');
    const sortSelect = document.getElementById('sortSelect');
    const stopsFilter = document.getElementById('stopsFilter');
    const minPrice = document.getElementById('minPrice');
    const maxPrice = document.getElementById('maxPrice');
    const departureTime = document.getElementById('departureTime');
    const cabinFilter = document.getElementById('filterCabinClass');
    const passengerFilter = document.getElementById('filterPassengers');
    const hotelSearch = document.getElementById('hotelSearch');
    const applyFilters = document.getElementById('applyFilters');
    const clearFilters = document.getElementById('clearFilters');
    const resultsCount = document.getElementById('resultsCount');
    const emptyResults = document.getElementById('emptyResults');

    if (!list || !cards.length) {
        if (resultsCount) resultsCount.textContent = '0';
        return;
    }

    const data = cards.map((card, index) => {
        const airlines = (card.dataset.airlines || '')
            .split(/\s+/)
            .map(item => item.trim())
            .filter(Boolean);
        return {
            card,
            index,
            price: parseFloat(card.dataset.price || '0') || 0,
            stops: parseInt(card.dataset.stops || '0', 10) || 0,
            departure: card.dataset.departure || '99:99',
            airlines,
            cabin: (card.dataset.cabin || '').replace('-', '_').toLowerCase(),
            seats: parseInt(card.dataset.seats || '0', 10) || 0,
            tripType: card.dataset.tripType || 'one-way',
            name: (card.dataset.name || '').toLowerCase(),
            address: (card.dataset.address || '').toLowerCase()
        };
    });

    function buildAirlineFilters() {
        if (!airlinesContainer) return;
        airlinesContainer.innerHTML = '';
        const airlineCodes = Array.from(new Set(data.flatMap(item => item.airlines))).sort();
        airlineCodes.forEach(code => {
            const id = 'airline_' + code;
            const label = document.createElement('label');
            label.setAttribute('for', id);
            label.innerHTML = `<input type="checkbox" value="${code}" id="${id}" class="airline-checkbox"> ${code}`;
            airlinesContainer.appendChild(label);
        });
    }

    function timeBucket(timeText) {
        const match = String(timeText).match(/(\d{2}):(\d{2})/);
        if (!match) return 'unknown';
        const hour = parseInt(match[1], 10);
        if (hour >= 4 && hour <= 11) return 'morning';
        if (hour >= 12 && hour <= 17) return 'afternoon';
        if (hour >= 18 && hour <= 21) return 'evening';
        return 'night';
    }

    function selectedAirlines() {
        return Array.from(document.querySelectorAll('.airline-checkbox:checked'))
            .map(input => input.value);
    }

    function applySort(items) {
        const mode = sortSelect ? sortSelect.value : 'best';
        if (mode === 'cheapest') {
            items.sort((a, b) => a.price - b.price);
            return;
        }
        if (mode === 'earliest') {
            items.sort((a, b) => a.departure.localeCompare(b.departure));
            return;
        }
        if (mode === 'name') {
            items.sort((a, b) => a.name.localeCompare(b.name));
            return;
        }
        items.sort((a, b) => {
            const aScore = a.price + (a.stops * 65000) + (a.index * 1200);
            const bScore = b.price + (b.stops * 65000) + (b.index * 1200);
            return aScore - bScore;
        });
    }

    function render(items) {
        list.innerHTML = '';
        items.forEach(item => list.appendChild(item.card));
        if (resultsCount) resultsCount.textContent = String(items.length);
        if (emptyResults) emptyResults.classList.toggle('d-none', items.length > 0);
    }

    function applyFilterAndSort() {
        let filtered = data.slice();
        const stopsValue = stopsFilter ? stopsFilter.value : 'any';
        const min = minPrice && minPrice.value ? parseFloat(minPrice.value) : -Infinity;
        const max = maxPrice && maxPrice.value ? parseFloat(maxPrice.value) : Infinity;
        const depBucket = departureTime ? departureTime.value : 'any';
        const cabin = cabinFilter ? cabinFilter.value : 'any';
        const passengers = passengerFilter ? (parseInt(passengerFilter.value, 10) || 1) : 1;
        const hotelQuery = hotelSearch ? hotelSearch.value.trim().toLowerCase() : '';
        const checkedAirlines = selectedAirlines();

        if (stopsValue !== 'any') {
            const stops = parseInt(stopsValue, 10);
            filtered = filtered.filter(item => stops === 2 ? item.stops >= 2 : item.stops === stops);
        }

        filtered = filtered.filter(item => item.price >= min && item.price <= max);

        if (depBucket !== 'any') {
            filtered = filtered.filter(item => timeBucket(item.departure) === depBucket);
        }

        if (checkedAirlines.length) {
            filtered = filtered.filter(item => checkedAirlines.some(code => item.airlines.includes(code)));
        }

        if (hotelQuery) {
            filtered = filtered.filter(item => item.name.includes(hotelQuery) || item.address.includes(hotelQuery));
        }

        if (cabin !== 'any') {
            const normalizedCabin = cabin.replace('-', '_').toLowerCase();
            filtered = filtered.filter(item => item.cabin === normalizedCabin || item.cabin.includes(normalizedCabin));
        }

        filtered = filtered.filter(item => item.seats >= passengers || item.seats === 0);
        applySort(filtered);
        render(filtered);
    }

    function clearAllFilters(event) {
        if (event) event.preventDefault();
        if (sortSelect) sortSelect.value = 'best';
        if (stopsFilter) stopsFilter.value = 'any';
        if (minPrice) minPrice.value = '';
        if (maxPrice) maxPrice.value = '';
        if (departureTime) departureTime.value = 'any';
        if (cabinFilter) cabinFilter.value = 'any';
        if (passengerFilter) passengerFilter.value = '1';
        if (hotelSearch) hotelSearch.value = '';
        document.querySelectorAll('.airline-checkbox').forEach(input => { input.checked = false; });
        applyFilterAndSort();
    }

    buildAirlineFilters();

    if (applyFilters) {
        applyFilters.addEventListener('click', event => {
            event.preventDefault();
            applyFilterAndSort();
        });
    }
    if (clearFilters) clearFilters.addEventListener('click', clearAllFilters);

    [sortSelect, stopsFilter, departureTime, cabinFilter, passengerFilter].forEach(control => {
        if (control) control.addEventListener('change', applyFilterAndSort);
    });
    [minPrice, maxPrice, hotelSearch].forEach(control => {
        if (control) control.addEventListener('input', applyFilterAndSort);
    });
    if (airlinesContainer) {
        airlinesContainer.addEventListener('change', event => {
            if (event.target.classList.contains('airline-checkbox')) applyFilterAndSort();
        });
    }

    applyFilterAndSort();
}

window.initResultsFilters = initResultsFilters;

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initResultsFilters);
} else {
    initResultsFilters();
}
