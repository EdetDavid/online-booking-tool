(function () {
    "use strict";

    window.showToast = function (message, type, timeout) {
        var stack = document.querySelector(".toast-stack");
        if (!stack) {
            stack = document.createElement("div");
            stack.className = "toast-stack";
            stack.setAttribute("aria-live", "polite");
            stack.setAttribute("aria-atomic", "true");
            document.body.appendChild(stack);
        }

        var toast = document.createElement("div");
        toast.className = "app-toast toast-" + (type || "info");
        toast.setAttribute("role", type === "error" ? "alert" : "status");

        var text = document.createElement("span");
        text.textContent = message;
        var close = document.createElement("button");
        close.type = "button";
        close.className = "toast-close";
        close.setAttribute("aria-label", "Close");
        close.innerHTML = "&times;";
        close.addEventListener("click", function () {
            toast.remove();
        });

        toast.appendChild(text);
        toast.appendChild(close);
        stack.appendChild(toast);
        window.setTimeout(function () {
            if (toast.parentNode) toast.remove();
        }, timeout || 6000);
    };
})();
