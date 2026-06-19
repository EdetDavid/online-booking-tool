(function () {
    "use strict";

    var form = document.getElementById("hotelSearchForm");
    if (!form) return;

    var cityInput = document.getElementById("hotelDestination");
    var checkinInput = document.getElementById("hotelCheckin");
    var checkoutInput = document.getElementById("hotelCheckout");
    var guestInput = document.getElementById("hotelGuestCount");
    var submitButton = document.getElementById("hotelSearchSubmit");
    var summary = document.getElementById("staySummaryText");
    var today = localDateString(new Date());
    var cache = {};

    checkinInput.min = today;
    checkoutInput.min = checkinInput.value || today;

    if (window.jQuery) {
        window.jQuery(cityInput).autocomplete({
            source: function (request, response) {
                var term = request.term.trim();
                if (!term) return response([]);
                var key = term.toLowerCase();
                if (cache[key]) return response(cache[key]);
                window.jQuery.ajax({
                    url: form.dataset.cityUrl,
                    data: {term: term},
                    success: function (data) {
                        var suggestions = normalizeSuggestions(data);
                        cache[key] = suggestions;
                        response(suggestions);
                    },
                    error: function () { response([]); }
                });
            },
            minLength: 1,
            delay: 160,
            select: function (event, ui) {
                cityInput.value = cityCode(ui.item.value);
                cityInput.dispatchEvent(new Event("change", {bubbles: true}));
                return false;
            }
        });
    }

    checkinInput.addEventListener("change", function () {
        checkoutInput.min = checkinInput.value || today;
        if (checkoutInput.value && checkoutInput.value <= checkinInput.value) {
            checkoutInput.value = nextDate(checkinInput.value);
        }
        updateSummary();
    });
    checkoutInput.addEventListener("change", updateSummary);
    cityInput.addEventListener("input", function () {
        cityInput.removeAttribute("aria-invalid");
        updateSummary();
    });

    document.getElementById("hotelDecreaseGuests").addEventListener("click", function () {
        setGuests((parseInt(guestInput.value, 10) || 1) - 1);
    });
    document.getElementById("hotelIncreaseGuests").addEventListener("click", function () {
        setGuests((parseInt(guestInput.value, 10) || 1) + 1);
    });
    guestInput.addEventListener("change", function () {
        setGuests(parseInt(guestInput.value, 10) || 1);
    });

    form.addEventListener("submit", function (event) {
        form.querySelectorAll('[aria-invalid="true"]').forEach(function (input) {
            input.removeAttribute("aria-invalid");
        });

        if (!validCity(cityInput.value)) {
            event.preventDefault();
            return invalidate(cityInput, "Choose a destination from the suggestions or enter a city code.");
        }
        if (!validDate(checkinInput.value, today)) {
            event.preventDefault();
            return invalidate(checkinInput, "Choose a valid check-in date.");
        }
        if (!validDate(checkoutInput.value, checkinInput.value) || checkoutInput.value === checkinInput.value) {
            event.preventDefault();
            return invalidate(checkoutInput, "Check-out must be after check-in.");
        }

        cityInput.value = cityCode(cityInput.value);
        submitButton.disabled = true;
        submitButton.classList.add("loading");
        submitButton.querySelector("i").className = "fas fa-circle-notch";
        submitButton.querySelector("span").textContent = "Finding stays…";
    });

    setGuests(guestInput.value);
    updateSummary();

    function setGuests(value) {
        guestInput.value = Math.max(1, Math.min(9, parseInt(value, 10) || 1));
        updateSummary();
    }

    function updateSummary() {
        var destination = cityCode(cityInput.value);
        var guests = guestInput.value + " guest" + (guestInput.value === "1" ? "" : "s");
        if (destination && checkinInput.value && checkoutInput.value) {
            summary.textContent = destination + " · " + nightsBetween(checkinInput.value, checkoutInput.value) + " night stay · " + guests;
        } else {
            summary.textContent = "Choose a destination and dates · " + guests;
        }
    }

    function invalidate(input, message) {
        input.setAttribute("aria-invalid", "true");
        input.focus();
        if (typeof window.showToast === "function") {
            window.showToast(message, "error");
        } else {
            window.alert(message);
        }
    }

    function cityCode(value) {
        return String(value || "").split(",", 1)[0].trim().toUpperCase();
    }

    function validCity(value) {
        return /^[A-Z]{3}$/.test(cityCode(value));
    }

    function validDate(value, minimum) {
        return /^\d{4}-\d{2}-\d{2}$/.test(value) && value >= minimum;
    }

    function nextDate(value) {
        var date = new Date(value + "T12:00:00");
        if (Number.isNaN(date.getTime())) return "";
        date.setDate(date.getDate() + 1);
        return localDateString(date);
    }

    function nightsBetween(start, end) {
        return Math.max(
            1,
            Math.round((new Date(end + "T12:00:00") - new Date(start + "T12:00:00")) / 86400000)
        );
    }

    function normalizeSuggestions(data) {
        if (Array.isArray(data)) return data;
        try {
            var parsed = JSON.parse(data);
            return Array.isArray(parsed) ? parsed : [];
        } catch (error) {
            return [];
        }
    }

    function localDateString(date) {
        var year = date.getFullYear();
        var month = String(date.getMonth() + 1).padStart(2, "0");
        var day = String(date.getDate()).padStart(2, "0");
        return year + "-" + month + "-" + day;
    }
})();
