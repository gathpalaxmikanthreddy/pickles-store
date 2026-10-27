(() => {
    const toggle = document.querySelector(".nav-toggle");
    const navigation = document.getElementById("storefront-navigation");

    if (!toggle || !navigation) return;

    const dropdowns = Array.from(navigation.querySelectorAll(".nav-dropdown"));

    const closeDropdowns = () => {
        dropdowns.forEach((dropdown) => {
            dropdown.open = false;
        });
    };

    const closeMenu = () => {
        toggle.setAttribute("aria-expanded", "false");
        toggle.setAttribute("aria-label", "Open navigation menu");
        toggle.querySelector(".nav-toggle-label").textContent = "Menu";
        navigation.classList.remove("is-open");
        closeDropdowns();
    };

    toggle.addEventListener("click", () => {
        const isOpen = toggle.getAttribute("aria-expanded") === "true";

        toggle.setAttribute("aria-expanded", String(!isOpen));
        toggle.setAttribute(
            "aria-label",
            isOpen ? "Open navigation menu" : "Close navigation menu"
        );
        toggle.querySelector(".nav-toggle-label").textContent = isOpen ? "Menu" : "Close";
        navigation.classList.toggle("is-open", !isOpen);

        if (isOpen) closeDropdowns();
    });

    dropdowns.forEach((dropdown) => {
        const summary = dropdown.querySelector("summary");

        dropdown.addEventListener("toggle", () => {
            summary.setAttribute("aria-expanded", String(dropdown.open));

            if (dropdown.open) {
                dropdowns.forEach((otherDropdown) => {
                    if (otherDropdown !== dropdown) otherDropdown.open = false;
                });
            }
        });
    });

    document.addEventListener("pointerdown", (event) => {
        if (event.target instanceof Element && !event.target.closest(".storefront-navbar")) {
            closeMenu();
        }
    });

    document.addEventListener("click", (event) => {
        if (event.target instanceof Element && event.target.closest(".storefront-navigation a")) {
            closeMenu();
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeMenu();
            toggle.focus();
        }
    });

    window.addEventListener("resize", () => {
        if (window.matchMedia("(min-width: 901px)").matches) closeMenu();
    });
})();
