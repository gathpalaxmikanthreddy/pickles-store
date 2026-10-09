document.addEventListener("click", function(event) {
    const target = event.target.closest(
        "[data-toggle-password], [data-checkout], [data-print], [data-cart-action]"
    );
    if (!target) return;

    if (target.hasAttribute("data-toggle-password")) {
        const input = document.getElementById(target.dataset.togglePassword);
        if (!input) return;

        const showing = input.type === "password";
        input.type = showing ? "text" : "password";
        target.textContent = showing ? "🙈" : "👁️";
    } else if (target.hasAttribute("data-checkout")) {
        if (typeof checkout === "function") checkout();
    } else if (target.hasAttribute("data-print")) {
        window.print();
    } else if (target.dataset.cartAction === "increase") {
        changeQuantity(Number(target.dataset.cartIndex), 1);
    } else if (target.dataset.cartAction === "decrease") {
        changeQuantity(Number(target.dataset.cartIndex), -1);
    } else if (target.dataset.cartAction === "remove") {
        removeFromCart(Number(target.dataset.cartIndex));
    }
});

document.addEventListener("submit", function(event) {
    const message = event.target.dataset.confirmMessage;
    if (message && !window.confirm(message)) event.preventDefault();
});

document.addEventListener("input", function(event) {
    const input = event.target.closest("[data-search-table]");
    if (!input) return;

    const table = document.querySelector(input.dataset.searchTable);
    if (!table) return;

    const search = input.value.toLowerCase();
    table.querySelectorAll("tbody tr").forEach(function(row) {
        row.style.display = row.innerText.toLowerCase().includes(search) ? "" : "none";
    });
});

document.addEventListener("error", function(event) {
    const image = event.target;
    if (!(image instanceof HTMLImageElement)) return;

    if (image.dataset.fallbackImage && image.dataset.fallbackApplied !== "true") {
        image.dataset.fallbackApplied = "true";
        image.src = image.dataset.fallbackImage;
    } else if (image.hasAttribute("data-hide-on-error")) {
        image.hidden = true;
    }
}, true);
