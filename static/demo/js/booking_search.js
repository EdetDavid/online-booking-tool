(function () {
    "use strict";

    var form = document.getElementById("flightSearchForm");
    if (!form) return;

    var today = localDateString(new Date());
    var maxPassengers = 9;
    var maxLegs = 5;
    var standardPanel = document.getElementById("standardTripPanel");
    var multiPanel = document.getElementById("multiCityPanel");
    var returnControl = document.getElementById("returnControl");
    var returnInput = document.getElementById("returnDate");
    var departureInput = document.getElementById("departureDate");
    var passengerInput = document.getElementById("bookingPassengerCount");
    var addLegButton = document.getElementById("addMultiCityLeg");
    var legsContainer = document.getElementById("multiCityLegs");
    var legTemplate = document.getElementById("multiCityLegTemplate");
    var submitButton = document.getElementById("flightSearchSubmit");
    var summaryText = document.getElementById("tripSummaryText");
    var originUrl = form.dataset.originUrl;
    var destinationUrl = form.dataset.destinationUrl;
    var isAuthenticated = form.dataset.authenticated === "true";
    var loginUrl = form.dataset.loginUrl;
    var autocompleteCache = {};

    departureInput.min = today;
    returnInput.min = today;

    attachAirportAutocomplete(document.getElementById("originInput"), originUrl);
    attachAirportAutocomplete(document.getElementById("destinationInput"), destinationUrl);
    allLegs().forEach(initializeLeg);

    form.querySelectorAll('input[name="tripType"]').forEach(function (radio) {
        radio.addEventListener("change", function () {
            applyTripType(radio.value);
        });
    });

    document.getElementById("bookingSwapLocations").addEventListener("click", function () {
        var origin = document.getElementById("originInput");
        var destination = document.getElementById("destinationInput");
        var value = origin.value;
        origin.value = destination.value;
        destination.value = value;
        updateSummary();
    });

    departureInput.addEventListener("change", function () {
        returnInput.min = departureInput.value || today;
        if (returnInput.value && returnInput.value < returnInput.min) {
            returnInput.value = "";
        }
        updateSummary();
    });
    returnInput.addEventListener("change", updateSummary);

    document.getElementById("bookingDecreasePassengers").addEventListener("click", function () {
        setPassengerCount((parseInt(passengerInput.value, 10) || 1) - 1);
    });
    document.getElementById("bookingIncreasePassengers").addEventListener("click", function () {
        setPassengerCount((parseInt(passengerInput.value, 10) || 1) + 1);
    });
    passengerInput.addEventListener("change", function () {
        setPassengerCount(parseInt(passengerInput.value, 10) || 1);
    });

    form.querySelectorAll(".search-input").forEach(function (input) {
        input.addEventListener("input", function () {
            input.removeAttribute("aria-invalid");
            updateSummary();
        });
    });

    addLegButton.addEventListener("click", function () {
        if (allLegs().length >= maxLegs) return;
        var fragment = legTemplate.content.cloneNode(true);
        legsContainer.appendChild(fragment);
        var newLeg = allLegs()[allLegs().length - 1];
        var previousLeg = allLegs()[allLegs().length - 2];
        var previousDestination = previousLeg.querySelector(".multi-destination").value;
        var previousDate = previousLeg.querySelector(".multi-date").value;
        var origin = newLeg.querySelector(".multi-origin");
        if (previousDestination) {
            origin.value = airportCode(previousDestination);
            origin.dataset.autoFilled = "true";
        }
        if (previousDate) {
            newLeg.querySelector(".multi-date").min = previousDate;
        }
        initializeLeg(newLeg);
        renumberLegs();
        newLeg.querySelector(".multi-destination").focus();
        updateSummary();
    });

    legsContainer.addEventListener("click", function (event) {
        var button = event.target.closest(".remove-leg-button");
        if (!button || allLegs().length <= 2) return;
        button.closest(".multi-leg").remove();
        renumberLegs();
        updateSummary();
    });

    form.addEventListener("submit", function (event) {
        clearInvalidStates();
        if (!isAuthenticated) {
            event.preventDefault();
            showSearchToast("Sign in with a staff account to search and request travel.", "error");
            window.setTimeout(function () {
                window.location.href = loginUrl;
            }, 900);
            return;
        }

        var tripType = selectedTripType();
        var valid = tripType === "multi-city"
            ? validateMultiCity()
            : validateStandard(tripType);
        if (!valid) {
            event.preventDefault();
            return;
        }

        submitButton.disabled = true;
        submitButton.classList.add("loading");
        submitButton.querySelector("i").className = "fas fa-circle-notch";
        submitButton.querySelector("span").textContent = "Finding flights…";
    });

    applyTripType(selectedTripType());
    setPassengerCount(passengerInput.value);
    renumberLegs();
    updateSummary();

    function applyTripType(tripType) {
        var isMulti = tripType === "multi-city";
        standardPanel.hidden = isMulti;
        multiPanel.hidden = !isMulti;

        if (tripType === "one-way") {
            returnInput.value = "";
            returnInput.disabled = true;
            returnInput.required = false;
            returnControl.classList.add("is-disabled");
        } else if (tripType === "round-trip") {
            returnInput.disabled = false;
            returnInput.required = true;
            returnInput.min = departureInput.value || today;
            returnControl.classList.remove("is-disabled");
        } else {
            returnInput.disabled = true;
            returnInput.required = false;
        }
        updateSummary();
    }

    function initializeLeg(leg) {
        var origin = leg.querySelector(".multi-origin");
        var destination = leg.querySelector(".multi-destination");
        var date = leg.querySelector(".multi-date");
        date.min = date.min || today;
        attachAirportAutocomplete(origin, originUrl);
        attachAirportAutocomplete(destination, destinationUrl);

        destination.addEventListener("change", function () {
            var legs = allLegs();
            var index = legs.indexOf(leg);
            var nextLeg = legs[index + 1];
            if (nextLeg) {
                var nextOrigin = nextLeg.querySelector(".multi-origin");
                if (!nextOrigin.value || nextOrigin.dataset.autoFilled === "true") {
                    nextOrigin.value = airportCode(destination.value);
                    nextOrigin.dataset.autoFilled = "true";
                }
            }
            updateSummary();
        });
        origin.addEventListener("input", function () {
            origin.dataset.autoFilled = "false";
            origin.removeAttribute("aria-invalid");
            updateSummary();
        });
        destination.addEventListener("input", function () {
            destination.removeAttribute("aria-invalid");
            updateSummary();
        });
        date.addEventListener("change", function () {
            var legs = allLegs();
            var index = legs.indexOf(leg);
            var nextLeg = legs[index + 1];
            if (nextLeg) {
                var nextDate = nextLeg.querySelector(".multi-date");
                nextDate.min = date.value || today;
                if (nextDate.value && nextDate.value < nextDate.min) {
                    nextDate.value = "";
                }
            }
            updateSummary();
        });
    }

    function attachAirportAutocomplete(input, url) {
        if (!input || input.dataset.autocompleteReady === "true" || !window.jQuery) return;
        input.dataset.autocompleteReady = "true";
        window.jQuery(input).autocomplete({
            source: function (request, response) {
                var term = request.term.trim();
                if (!term) return response([]);
                var cacheKey = url + "::" + term.toLowerCase();
                if (autocompleteCache[cacheKey]) {
                    return response(autocompleteCache[cacheKey]);
                }
                window.jQuery.ajax({
                    url: url,
                    data: {term: term},
                    success: function (data) {
                        var suggestions = normalizeSuggestions(data);
                        autocompleteCache[cacheKey] = suggestions;
                        response(suggestions);
                    },
                    error: function () {
                        response([]);
                    }
                });
            },
            minLength: 1,
            delay: 150,
            select: function (event, ui) {
                input.value = airportCode(ui.item.value);
                input.dispatchEvent(new Event("change", {bubbles: true}));
                return false;
            }
        });
    }

    function validateStandard(tripType) {
        var origin = document.getElementById("originInput");
        var destination = document.getElementById("destinationInput");
        if (!validAirport(origin.value)) return invalidate(origin, "Choose a valid departure airport.");
        if (!validAirport(destination.value)) return invalidate(destination, "Choose a valid arrival airport.");
        if (airportCode(origin.value) === airportCode(destination.value)) {
            return invalidate(destination, "Origin and destination must be different.");
        }
        if (!validDate(departureInput.value, today)) {
            return invalidate(departureInput, "Choose a valid departure date.");
        }
        if (tripType === "round-trip") {
            if (!validDate(returnInput.value, departureInput.value)) {
                return invalidate(returnInput, "Return date must be on or after departure.");
            }
        }
        origin.value = airportCode(origin.value);
        destination.value = airportCode(destination.value);
        return true;
    }

    function validateMultiCity() {
        var legs = allLegs();
        if (legs.length < 2) {
            showSearchToast("Add at least two flights for a multi-city trip.", "error");
            return false;
        }
        var previousDate = today;
        for (var index = 0; index < legs.length; index += 1) {
            var origin = legs[index].querySelector(".multi-origin");
            var destination = legs[index].querySelector(".multi-destination");
            var date = legs[index].querySelector(".multi-date");
            if (!validAirport(origin.value)) return invalidate(origin, "Choose a valid origin for flight " + (index + 1) + ".");
            if (!validAirport(destination.value)) return invalidate(destination, "Choose a valid destination for flight " + (index + 1) + ".");
            if (airportCode(origin.value) === airportCode(destination.value)) {
                return invalidate(destination, "Flight " + (index + 1) + " must arrive somewhere different.");
            }
            if (!validDate(date.value, previousDate)) {
                return invalidate(date, "Flight dates must be in chronological order.");
            }
            origin.value = airportCode(origin.value);
            destination.value = airportCode(destination.value);
            previousDate = date.value;
        }
        return true;
    }

    function invalidate(input, message) {
        input.setAttribute("aria-invalid", "true");
        input.focus();
        showSearchToast(message, "error");
        return false;
    }

    function clearInvalidStates() {
        form.querySelectorAll('[aria-invalid="true"]').forEach(function (input) {
            input.removeAttribute("aria-invalid");
        });
    }

    function selectedTripType() {
        var selected = form.querySelector('input[name="tripType"]:checked');
        return selected ? selected.value : "round-trip";
    }

    function setPassengerCount(value) {
        var count = Math.max(1, Math.min(maxPassengers, parseInt(value, 10) || 1));
        passengerInput.value = count;
        updateSummary();
    }

    function renumberLegs() {
        allLegs().forEach(function (leg, index) {
            leg.querySelector(".multi-leg-number").textContent = index + 1;
            leg.querySelector(".remove-leg-button").disabled = allLegs().length <= 2;
            var date = leg.querySelector(".multi-date");
            if (index === 0) {
                date.min = today;
            } else {
                date.min = allLegs()[index - 1].querySelector(".multi-date").value || today;
            }
        });
        addLegButton.disabled = allLegs().length >= maxLegs;
        addLegButton.querySelector("span").textContent = allLegs().length >= maxLegs
            ? "Maximum 5 flights"
            : "Add another flight";
    }

    function updateSummary() {
        var tripType = selectedTripType();
        var passengerText = passengerInput.value + " passenger" + (passengerInput.value === "1" ? "" : "s");
        if (tripType === "multi-city") {
            var completeRoutes = allLegs().map(function (leg) {
                var origin = airportCode(leg.querySelector(".multi-origin").value);
                var destination = airportCode(leg.querySelector(".multi-destination").value);
                return origin && destination ? origin + " → " + destination : "";
            }).filter(Boolean);
            summaryText.textContent = completeRoutes.length
                ? completeRoutes.join(" · ") + " · " + passengerText
                : "Build a trip with 2–5 flights · " + passengerText;
            return;
        }
        var origin = airportCode(document.getElementById("originInput").value);
        var destination = airportCode(document.getElementById("destinationInput").value);
        var label = tripType === "round-trip" ? "Round trip" : "One way";
        summaryText.textContent = origin && destination
            ? origin + " → " + destination + " · " + label + " · " + passengerText
            : label + " · " + passengerText;
    }

    function allLegs() {
        return Array.prototype.slice.call(legsContainer.querySelectorAll(".multi-leg"));
    }

    function airportCode(value) {
        return String(value || "").split(",", 1)[0].trim().toUpperCase();
    }

    function validAirport(value) {
        return /^[A-Z]{3}$/.test(airportCode(value));
    }

    function validDate(value, minimum) {
        return /^\d{4}-\d{2}-\d{2}$/.test(value) && value >= minimum;
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

    function showSearchToast(message, type) {
        if (typeof window.showToast === "function") {
            window.showToast(message, type);
        } else {
            window.alert(message);
        }
    }
})();
