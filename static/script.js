let cart = JSON.parse(localStorage.getItem("cart")) || [];

function getCsrfHeaders() {
    const token = document.querySelector('meta[name="csrf-token"]')?.content;
    return token ? { "X-CSRFToken": token } : {};
}


/* =========================================
UPDATE CART COUNT
========================================= */

function updateCartCount() {
    const cartCount = document.getElementById("cart-count");

    if (!cartCount) return;

    let total = 0;

    cart.forEach(function(item) {
        total += Number(item.quantity) || 0;
    });

    cartCount.textContent = total;
    cartCount.setAttribute("aria-label", total + " items in cart");
    cartCount.classList.remove("is-bumping");
    void cartCount.offsetWidth;
    cartCount.classList.add("is-bumping");
}

function showToast(message, type) {
    let toast = document.getElementById("app-toast");

    if (!toast) {
        toast = document.createElement("div");
        toast.id = "app-toast";
        toast.setAttribute("role", "status");
        toast.setAttribute("aria-live", "polite");
        toast.setAttribute("aria-atomic", "true");
        document.body.appendChild(toast);
    }

    window.clearTimeout(toast.hideTimer);
    toast.className = "app-toast is-visible" + (type === "error" ? " is-error" : "");
    toast.textContent = message;
    toast.hideTimer = window.setTimeout(function() {
        toast.classList.remove("is-visible");
    }, 3000);
}


/* =========================================
SAVE CART
========================================= */

function saveCart() {
    localStorage.setItem("cart", JSON.stringify(cart));
    updateCartCount();
    if (typeof renderCartDrawer === "function") {
        renderCartDrawer();
    }
}

function animateCartFlight(source, image) {
    if (
        !(source instanceof Element) ||
        window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
        return;
    }

    const destination =
        document.getElementById("cart-count") ||
        document.querySelector(".cart-link");
    if (!destination) return;

    const sourceRect = source.getBoundingClientRect();
    const destinationRect = destination.getBoundingClientRect();
    const productImage =
        source.closest(".product-card, .product-details")?.querySelector(".product-image img, .product-image-box img");
    const flyer = document.createElement("img");
    flyer.className = "cart-flyer";
    flyer.alt = "";
    flyer.width = 52;
    flyer.height = 52;
    flyer.setAttribute("aria-hidden", "true");
    flyer.src = productImage?.currentSrc ||
        (image ? "/static/images/" + encodeURIComponent(image) : "");
    if (!flyer.src) return;

    flyer.style.left = sourceRect.left + sourceRect.width / 2 - 26 + "px";
    flyer.style.top = sourceRect.top + sourceRect.height / 2 - 26 + "px";
    document.body.appendChild(flyer);

    requestAnimationFrame(function() {
        flyer.style.left = destinationRect.left + destinationRect.width / 2 - 26 + "px";
        flyer.style.top = destinationRect.top + destinationRect.height / 2 - 26 + "px";
        flyer.style.opacity = "0.2";
        flyer.style.transform = "scale(0.25) rotate(18deg)";
    });

    window.setTimeout(function() {
        flyer.remove();
    }, 650);
}

function renderCartDrawer() {
    const itemList = document.querySelector(".cart-drawer__items");
    const totalElement = document.querySelector(".cart-drawer__total strong");
    if (!itemList || !totalElement) return;

    const checkoutLink = document.querySelector(".cart-drawer__checkout");
    const checkoutAvailable = cart.length > 0;
    if (checkoutLink) {
        checkoutLink.setAttribute("aria-disabled", String(!checkoutAvailable));
        checkoutLink.tabIndex = checkoutAvailable ? 0 : -1;
        checkoutLink.classList.toggle("is-disabled", !checkoutAvailable);
    }

    itemList.replaceChildren();
    if (cart.length === 0) {
        const empty = document.createElement("p");
        empty.className = "cart-drawer__empty";
        empty.textContent = "Your cart is waiting for something delicious.";
        itemList.appendChild(empty);
        totalElement.textContent = "₹0.00";
        return;
    }

    cart.forEach(function(item, index) {
        const row = document.createElement("article");
        row.className = "cart-drawer__item";

        const image = document.createElement("img");
        image.src = "/static/images/" + encodeURIComponent(item.image || "mango-pickle.png");
        image.alt = item.name || "Pickle";
        image.width = 72;
        image.height = 72;
        image.loading = "lazy";
        image.decoding = "async";
        image.dataset.hideOnError = "true";
        const imageFrame = document.createElement("span");
        imageFrame.className = "cart-drawer__image";
        imageFrame.appendChild(image);

        const details = document.createElement("div");
        const name = document.createElement("h3");
        name.textContent = item.name || "Pickle";
        const price = document.createElement("p");
        price.textContent = "₹" + (Number(item.price) || 0).toFixed(2);
        const quantity = document.createElement("div");
        quantity.className = "cart-drawer__quantity";

        const decrease = document.createElement("button");
        decrease.type = "button";
        decrease.dataset.drawerAction = "decrease";
        decrease.dataset.cartIndex = String(index);
        decrease.setAttribute("aria-label", "Decrease quantity of " + (item.name || "pickle"));
        decrease.textContent = "−";
        const amount = document.createElement("span");
        amount.textContent = String(Number(item.quantity) || 0);
        const increase = document.createElement("button");
        increase.type = "button";
        increase.dataset.drawerAction = "increase";
        increase.dataset.cartIndex = String(index);
        increase.setAttribute("aria-label", "Increase quantity of " + (item.name || "pickle"));
        increase.textContent = "+";
        const stock = Number(item.stock);
        if (Number.isFinite(stock) && Number(item.quantity) >= stock) {
            increase.disabled = true;
        }

        quantity.append(decrease, amount, increase);
        details.append(name, price, quantity);

        const remove = document.createElement("button");
        remove.type = "button";
        remove.dataset.drawerAction = "remove";
        remove.dataset.cartIndex = String(index);
        remove.setAttribute("aria-label", "Remove " + (item.name || "pickle") + " from cart");
        remove.className = "cart-drawer__close";
        remove.textContent = "×";

        row.append(imageFrame, details, remove);
        itemList.appendChild(row);
    });

    totalElement.textContent = "₹" + calculateCartTotal().toFixed(2);
}

function initializePremiumUI() {
    const navbar = document.querySelector(".navbar, .storefront-navbar");
    const updateNavbar = function() {
        if (navbar) navbar.classList.toggle("is-compact", window.scrollY > 20);
    };
    updateNavbar();
    window.addEventListener("scroll", updateNavbar, { passive: true });

    const revealItems = document.querySelectorAll(
        ".hero-content, .hero-stage, .section-heading, .product-card, .why-card, .contact-card, .about-content, .product-details, .reviews-section, .checkout-details, .checkout-summary, .cart-container, .legal-shell"
    );
    if ("IntersectionObserver" in window) {
        const revealObserver = new IntersectionObserver(function(entries, observer) {
            entries.forEach(function(entry) {
                if (entry.isIntersecting) {
                    entry.target.classList.add("is-revealed");
                    observer.unobserve(entry.target);
                }
            });
        }, { threshold: 0.12, rootMargin: "0px 0px -30px 0px" });
        revealItems.forEach(function(item) {
            item.setAttribute("data-reveal", "");
            revealObserver.observe(item);
        });
    } else {
        revealItems.forEach(function(item) {
            item.classList.add("is-revealed");
        });
    }

    const hero = document.querySelector(".hero-stage");
    const heroProduct = hero?.querySelector(".hero-product");
    const finePointer = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (hero && heroProduct && finePointer && !reduceMotion) {
        hero.addEventListener("pointermove", function(event) {
            const bounds = hero.getBoundingClientRect();
            const x = (event.clientX - bounds.left) / bounds.width - 0.5;
            const y = (event.clientY - bounds.top) / bounds.height - 0.5;
            heroProduct.style.setProperty("--hero-x", (x * 14).toFixed(1) + "px");
            heroProduct.style.setProperty("--hero-y", (y * 14).toFixed(1) + "px");
            heroProduct.style.setProperty("--hero-rotate-y", (x * 14 - 7).toFixed(1) + "deg");
            heroProduct.style.setProperty("--hero-rotate-x", (y * -10).toFixed(1) + "deg");
        });
        hero.addEventListener("pointerleave", function() {
            heroProduct.style.removeProperty("--hero-x");
            heroProduct.style.removeProperty("--hero-y");
            heroProduct.style.removeProperty("--hero-rotate-y");
            heroProduct.style.removeProperty("--hero-rotate-x");
        });

        document.querySelectorAll(".storefront-home .product-card").forEach(function(card) {
            card.addEventListener("pointermove", function(event) {
                const bounds = card.getBoundingClientRect();
                const x = (event.clientX - bounds.left) / bounds.width;
                const y = (event.clientY - bounds.top) / bounds.height;
                card.style.setProperty("--card-tilt-y", ((x - 0.5) * 7).toFixed(2) + "deg");
                card.style.setProperty("--card-tilt-x", ((0.5 - y) * 7).toFixed(2) + "deg");
                card.style.setProperty("--shine-x", (x * 100).toFixed(1) + "%");
                card.style.setProperty("--shine-y", (y * 100).toFixed(1) + "%");
            });
            card.addEventListener("pointerleave", function() {
                card.style.setProperty("--card-tilt-x", "0deg");
                card.style.setProperty("--card-tilt-y", "0deg");
            });
        });
    }

    if (finePointer && !reduceMotion) {
        const cursor = document.createElement("span");
        cursor.className = "custom-cursor";
        cursor.setAttribute("aria-hidden", "true");
        document.body.appendChild(cursor);
        document.body.classList.add("has-custom-cursor");
        document.addEventListener("pointermove", function(event) {
            cursor.style.left = event.clientX + "px";
            cursor.style.top = event.clientY + "px";
        }, { passive: true });
        document.addEventListener("pointerover", function(event) {
            cursor.classList.toggle("is-hovering", Boolean(event.target.closest("a, button, summary, input, select, textarea")));
        });
    }

    document.addEventListener("click", function(event) {
        const addButton = event.target.closest(".add-to-cart-button, #add-product, [data-name][data-price][data-stock]");
        if (addButton && !addButton.disabled) {
            window.setTimeout(function() {
                animateCartFlight(addButton, addButton.dataset.image);
            }, 0);
        }

        const link = event.target.closest("a[href]");
        if (
            !event.defaultPrevented &&
            link &&
            link.origin === window.location.origin &&
            !link.hash &&
            !link.target &&
            !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey &&
            !reduceMotion
        ) {
            const progress = document.createElement("div");
            progress.className = "page-progress";
            progress.setAttribute("aria-hidden", "true");
            document.body.appendChild(progress);
            window.setTimeout(function() { progress.remove(); }, 600);
        }
    });
}


/* =========================================
ADD TO CART
========================================= */

function addToCart(name, price, image, stock, quantity) {
    stock = Number(stock);
    const requestedQuantity = Math.max(1, Math.floor(Number(quantity) || 1));

    const existingItem = cart.find(function(item) {
        return item.name === name;
    });

    if (stock <= 0) {
        showToast(name + " is currently out of stock.", "error");
        return;
    }

    if (stock > 0 && requestedQuantity > stock) {
        showToast(
            "Only " +
            stock +
            " unit(s) of " +
            name +
            " are available.",
            "error"
        );
        return;
    }

    if (existingItem) {
        const currentQuantity = Number(existingItem.quantity) || 0;

        if (stock > 0 && currentQuantity + requestedQuantity > stock) {
            showToast(
                "Only " +
                stock +
                " unit(s) of " +
                name +
                " are available.",
                "error"
            );
            return;
        }

        existingItem.quantity = currentQuantity + requestedQuantity;
        existingItem.stock = stock;
    } else {
        cart.push({
            name: name,
            price: Number(price),
            quantity: requestedQuantity,
            image: image || "mango-pickle.png",
            stock: stock
        });
    }

    saveCart();

    showToast(name + " added to cart.");
}


/* =========================================
DISPLAY CART
========================================= */

function displayCart() {
    const cartItems = document.getElementById("cart-items");
    const cartTotal = document.getElementById("cart-total");

    if (!cartItems) return;

    const checkoutButton = document.querySelector(".cart-page [data-checkout]");
    if (checkoutButton) {
        const checkoutAvailable = cart.length > 0;
        checkoutButton.disabled = !checkoutAvailable;
        checkoutButton.setAttribute("aria-disabled", String(!checkoutAvailable));
    }

    cartItems.innerHTML = "";

    if (cart.length === 0) {

        cartItems.innerHTML = `
            <div class="empty-cart">

                <div class="empty-cart-icon">
                    🛒
                </div>

                <h2>
                    Your cart is empty
                </h2>

                <p>
                    Add some delicious pickles to get started.
                </p>

            </div>
        `;

        if (cartTotal) {
            cartTotal.textContent = "Total: ₹0.00";
        }

        return;
    }

    let total = 0;

    cart.forEach(function(item, index) {

        const price = Number(item.price) || 0;
        const quantity = Number(item.quantity) || 0;
        const stock = Number(item.stock);
        const subtotal = price * quantity;

        total += subtotal;

        const image = item.image || "mango-pickle.png";

        let stockMessage = "";

        if (!isNaN(stock)) {

            if (stock <= 0) {

                stockMessage = `
                    <p style="color:#b02a37;font-weight:700;">
                        ❌ Out of stock
                    </p>
                `;

            } else if (stock <= 5) {

                stockMessage = `
                    <p style="color:#b45309;font-weight:700;">
                        ⚠️ Only ${stock} left
                    </p>
                `;

            } else {

                stockMessage = `
                    <p style="color:#285c41;font-weight:600;">
                        📦 ${stock} available
                    </p>
                `;
            }
        }


        /* PLUS BUTTON */

        let plusButton = "";

        if (!isNaN(stock) && quantity >= stock) {

            plusButton = `
                <button
                    type="button"
                    disabled
                    title="Maximum available stock reached"
                    style="opacity:0.5;cursor:not-allowed;"
                >
                    +
                </button>
            `;

        } else {

            plusButton = `
                <button
                    type="button"
                    data-cart-action="increase"
                    data-cart-index="${index}"
                >
                    +
                </button>
            `;
        }


        cartItems.innerHTML += `

            <div class="cart-item">

                <div class="cart-product-image">

                            <img
                                src="/static/images/${encodeURIComponent(image)}"
                        alt="${item.name}"
                                width="180"
                                height="180"
                                loading="lazy"
                                decoding="async"
                                data-hide-on-error
                            >

                </div>


                <div class="cart-product-details">

                    <h3>
                        ${item.name}
                    </h3>


                    <p class="cart-price">

                        Price:

                        ₹${price.toFixed(2)}

                    </p>


                    ${stockMessage}


                    <div class="quantity-row">

                        <span>
                            Quantity:
                        </span>


                        <button
                            type="button"
                            data-cart-action="decrease"
                            data-cart-index="${index}"
                        >
                            −
                        </button>


                        <strong>
                            ${quantity}
                        </strong>


                        ${plusButton}

                    </div>


                    <p class="cart-subtotal">

                        Subtotal:

                        <strong>
                            ₹${subtotal.toFixed(2)}
                        </strong>

                    </p>


                    <button
                        type="button"
                        class="remove-cart-btn"
                        data-cart-action="remove"
                        data-cart-index="${index}"
                    >
                        🗑️ Remove
                    </button>

                </div>

            </div>

        `;
    });


    if (cartTotal) {

        cartTotal.textContent =
            "Total: ₹" +
            total.toFixed(2);

    }
}


/* =========================================
CHANGE QUANTITY
========================================= */

function changeQuantity(index, amount) {

    if (!cart[index]) return;

    const item = cart[index];

    const currentQuantity =
        Number(item.quantity) || 0;

    const stock =
        Number(item.stock);


    if (
        amount > 0 &&
        !isNaN(stock) &&
        currentQuantity >= stock
    ) {

        alert(
            "Only " +
            stock +
            " unit(s) of " +
            item.name +
            " are available."
        );

        return;
    }


    item.quantity =
        currentQuantity + amount;


    if (item.quantity <= 0) {

        cart.splice(index, 1);

    }


    saveCart();

    displayCart();
}


/* =========================================
REMOVE ITEM
========================================= */

function removeFromCart(index) {

    if (!cart[index]) return;

    cart.splice(index, 1);

    saveCart();

    displayCart();
}


/* =========================================
CHECKOUT
========================================= */

function checkout() {

    if (cart.length === 0) {

        alert("Your cart is empty!");

        return;
    }

    window.location.href =
        "/checkout";
}


/* =========================================
CALCULATE CART TOTAL
========================================= */

function calculateCartTotal() {

    return cart.reduce(
        function(sum, item) {

            const price =
                Number(item.price) || 0;

            const quantity =
                Number(item.quantity) || 0;

            return sum +
                (price * quantity);

        },
        0
    );
}


/* =========================================
DISPLAY CHECKOUT
========================================= */

function displayCheckout() {

    const checkoutItems =
        document.getElementById(
            "checkout-items"
        );

    const checkoutTotal =
        document.getElementById(
            "checkout-total"
        );


    if (!checkoutItems) return;


    checkoutItems.replaceChildren();


    let total = 0;


    cart.forEach(function(item) {

        const price =
            Number(item.price) || 0;

        const quantity =
            Number(item.quantity) || 0;

        const subtotal =
            price * quantity;


        total += subtotal;


        const row = document.createElement("div");
        row.className = "checkout-item";

        const imageFrame = document.createElement("span");
        imageFrame.className = "checkout-item__image";
        const image = document.createElement("img");
        image.src = "/static/images/" + encodeURIComponent(item.image || "mango-pickle.png");
        image.alt = item.name || "Pickle";
        image.width = 72;
        image.height = 72;
        image.loading = "lazy";
        image.decoding = "async";
        image.dataset.hideOnError = "true";
        imageFrame.appendChild(image);

        const description = document.createElement("p");
        const name = document.createElement("strong");
        name.textContent = item.name || "Pickle";
        description.append(name, document.createTextNode(" × " + quantity));

        const amount = document.createElement("p");
        amount.textContent = "₹" + subtotal.toFixed(2);

        row.append(imageFrame, description, amount);
        checkoutItems.appendChild(row);
    });


    if (checkoutTotal) {

        checkoutTotal.textContent =
            "Total: ₹" +
            total.toFixed(2);

    }
}


/* =========================================
RESET PLACE ORDER BUTTON
========================================= */

function resetPlaceOrderButton() {

    const checkoutForm =
        document.getElementById(
            "checkout-form"
        );

    if (!checkoutForm) return;


    const button =
        checkoutForm.querySelector(
            "button[type='submit']"
        );


    if (button) {

        button.disabled = false;

        const paymentMethod = document.querySelector(
            'input[name="payment_method"]:checked'
        )?.value;
        const label = document.getElementById("checkout-submit-label");

        if (label) {
            label.textContent = paymentMethod === "online"
                ? "Continue to secure payment"
                : "Place COD order";
        } else {
            button.textContent = paymentMethod === "online"
                ? "Continue to secure payment"
                : "Place COD order";
        }
    }
}

function updateCheckoutPaymentChoice() {
    const paymentMethod = document.querySelector(
        'input[name="payment_method"]:checked'
    )?.value;
    const isOnline = paymentMethod === "online";
    const note = document.getElementById("payment-choice-note");
    const summaryTitle = document.getElementById("checkout-payment-title");
    const summaryDescription = document.getElementById("checkout-payment-description");
    const label = document.getElementById("checkout-submit-label");

    if (note) {
        note.textContent = isOnline
            ? "You’ll continue to Razorpay to complete payment before the order is placed."
            : "No online payment is taken now. Pay cash when your order is delivered.";
    }

    if (summaryTitle) {
        summaryTitle.textContent = isOnline
            ? "Online payment"
            : "Cash on Delivery";
    }

    if (summaryDescription) {
        summaryDescription.textContent = isOnline
            ? "You’ll pay securely through Razorpay before your order is confirmed."
            : "Pay when your order arrives. Nothing is charged online now.";
    }

    if (label) {
        label.textContent = isOnline
            ? "Continue to secure payment"
            : "Place COD order";
    }
}


/* =========================================
PLACE COD ORDER
========================================= */

async function placeCODOrder(
    items,
    address,
    button
) {

    try {

        const response =
            await fetch(
                "/place-order",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json",
                        ...getCsrfHeaders()
                    },

                    body: JSON.stringify({

                        items: items,

                        payment_method:
                            "COD",

                        address: address

                    })
                }
            );


        const result =
            await response.json();


        if (result.success) {

            alert(
                "Order placed successfully! Order #" +
                result.order_id
            );


            cart = [];

            localStorage.removeItem(
                "cart"
            );

            updateCartCount();


            window.location.href =
                "/order-history";


            return;
        }


        alert(
            result.message ||
            "Unable to place order."
        );


        resetPlaceOrderButton();

    } catch (error) {

        console.error(
            "COD order error:",
            error
        );


        alert(
            "Unable to place order. Please try again."
        );


        resetPlaceOrderButton();
    }
}


/* =========================================
CREATE RAZORPAY ORDER
========================================= */

async function createRazorpayOrder(
    items,
    address
) {

    const response =
        await fetch(
            "/create-razorpay-order",
            {
                method: "POST",

                headers: {
                    "Content-Type":
                        "application/json",
                    ...getCsrfHeaders()
                },

                body: JSON.stringify({

                    items: items,

                    address: address

                })
            }
        );


    const result =
        await response.json();


    if (!response.ok || !result.success) {

        throw new Error(
            result.message ||
            "Unable to create Razorpay order."
        );
    }


    return result;
}


/* =========================================
VERIFY RAZORPAY PAYMENT
========================================= */

async function verifyRazorpayPayment(
    paymentResponse,
    items,
    address
) {

    const response =
        await fetch(
            "/verify-razorpay-payment",
            {
                method: "POST",

                headers: {
                    "Content-Type":
                        "application/json",
                    ...getCsrfHeaders()
                },

                body: JSON.stringify({

                    razorpay_order_id:
                        paymentResponse.razorpay_order_id,

                    razorpay_payment_id:
                        paymentResponse.razorpay_payment_id,

                    razorpay_signature:
                        paymentResponse.razorpay_signature,

                    items: items,

                    address: address

                })
            }
        );


    const result =
        await response.json();


    if (!response.ok || !result.success) {

        throw new Error(
            result.message ||
            "Payment verification failed."
        );
    }


    return result;
}


/* =========================================
START RAZORPAY PAYMENT
========================================= */

async function startRazorpayPayment(
    items,
    address
) {

    try {

        /* CHECK RAZORPAY SCRIPT */

        if (
            typeof Razorpay ===
            "undefined"
        ) {

            throw new Error(
                "Razorpay payment system is not loaded. Please refresh the page and try again."
            );
        }


        /* CREATE RAZORPAY ORDER */

        const razorpayOrder =
            await createRazorpayOrder(
                items,
                address
            );


        if (
            !razorpayOrder.key_id ||
            !razorpayOrder.order_id
        ) {

            throw new Error(
                "Razorpay order information is missing."
            );
        }


        /* RAZORPAY OPTIONS */

        const options = {

            key:
                razorpayOrder.key_id,

            amount:
                razorpayOrder.amount,

            currency:
                razorpayOrder.currency ||
                "INR",

            name:
                "PICKELS STORE",

            description:
                "Pickles Store Order",

            order_id:
                razorpayOrder.order_id,


            handler:
                async function(
                    paymentResponse
                ) {

                    try {

                        const result =
                            await verifyRazorpayPayment(
                                paymentResponse,
                                items,
                                address
                            );


                        alert(
                            "Payment successful and order placed! Order #" +
                            result.order_id
                        );


                        cart = [];

                        localStorage.removeItem(
                            "cart"
                        );

                        updateCartCount();


                        window.location.href =
                            "/order-history";


                    } catch (error) {

                        console.error(
                            "Payment verification error:",
                            error
                        );


                        alert(
                            error.message ||
                            "Payment was completed, but order verification failed. Please contact PICKELS STORE."
                        );


                        resetPlaceOrderButton();
                    }
                },


            prefill: {

                name:
                    (
                        document.getElementById(
                            "name"
                        )?.value || ""
                    ).trim(),

                contact:
                    (
                        document.getElementById(
                            "mobile"
                        )?.value || ""
                    ).trim()

            },


            notes: {

                address:
                    address

            },


            theme: {

                color:
                    "#285c41"

            },


            modal: {

                ondismiss:
                    function() {

                        resetPlaceOrderButton();

                    }

            }

        };


        /* CREATE RAZORPAY CHECKOUT */

        const razorpay =
            new Razorpay(options);


        /* PAYMENT FAILED EVENT */

        razorpay.on(
            "payment.failed",
            function(response) {

                console.error(
                    "Razorpay payment failed:",
                    response
                );


                let message =
                    "Payment failed. Please try again.";


                if (
                    response &&
                    response.error &&
                    response.error.description
                ) {

                    message =
                        response.error.description;
                }


                alert(message);


                resetPlaceOrderButton();
            }
        );


        /* OPEN PAYMENT WINDOW */

        razorpay.open();

    } catch (error) {

        console.error(
            "Razorpay error:",
            error
        );


        alert(
            error.message ||
            "Unable to start online payment."
        );


        resetPlaceOrderButton();
    }
}


/* =========================================
CHECKOUT FORM
========================================= */

document.addEventListener(
    "DOMContentLoaded",
    function() {

        document.addEventListener("error", function(event) {
            const image = event.target;
            if (!(image instanceof HTMLImageElement) || !image.hasAttribute("data-hide-on-error")) {
                return;
            }
            image.hidden = true;
            image.parentElement?.classList.add("image-failed");
        }, true);

        document.querySelectorAll("img[data-hide-on-error]").forEach(function(image) {
            if (image.complete && image.naturalWidth === 0) {
                image.hidden = true;
                image.parentElement?.classList.add("image-failed");
            }
        });

        updateCartCount();

        displayCart();

        displayCheckout();
        initializePremiumUI();

        if (!localStorage.getItem("pickles_cookie_consent")) {
            const banner = document.createElement("div");
            banner.className = "cookie-consent";
            banner.innerHTML = `
                <div class="cookie-consent__content">
                    <div>
                        <strong>Cookie notice</strong>
                        <p>We use essential cookies to keep the store running and optional analytics cookies to improve the shopping experience.</p>
                    </div>
                    <div class="cookie-consent__actions">
                        <button type="button" class="cookie-btn cookie-btn__secondary" data-cookie-choice="essential">Only essentials</button>
                        <button type="button" class="cookie-btn cookie-btn__primary" data-cookie-choice="accept">Accept all</button>
                    </div>
                </div>
            `;
            document.body.appendChild(banner);

            banner.querySelectorAll("[data-cookie-choice]").forEach(function(button) {
                button.addEventListener("click", function() {
                    const choice = button.dataset.cookieChoice;
                    localStorage.setItem("pickles_cookie_consent", choice);
                    banner.remove();
                });
            });
        }

        const paymentOptions = document.querySelectorAll(
            'input[name="payment_method"]'
        );
        paymentOptions.forEach(function(option) {
            option.addEventListener("change", updateCheckoutPaymentChoice);
        });
        updateCheckoutPaymentChoice();


        const checkoutForm =
            document.getElementById(
                "checkout-form"
            );


        if (!checkoutForm) return;


        checkoutForm.addEventListener(
            "submit",
            async function(event) {

                event.preventDefault();


                /* EMPTY CART */

                if (cart.length === 0) {

                    alert(
                        "Your cart is empty!"
                    );

                    return;
                }


                /* ADDRESS */

                const addressElement =
                    document.getElementById(
                        "address"
                    );


                const address =
                    addressElement
                        ? addressElement.value.trim()
                        : "";


                if (!address) {

                    alert(
                        "Please enter your delivery address."
                    );


                    if (addressElement) {

                        addressElement.focus();

                    }


                    return;
                }


                /* CART COPY */

                const items =
                    cart.map(function(item) {

                        return {

                            name:
                                item.name,

                            price:
                                Number(item.price) || 0,

                            quantity:
                                Number(item.quantity) || 0,

                            image:
                                item.image || "",

                            stock:
                                Number(item.stock)

                        };

                    });


                /* PAYMENT METHOD */

                const paymentElement =
                    document.querySelector(
                        'input[name="payment_method"]:checked'
                    );


                if (!paymentElement) {

                    alert(
                        "Please select a payment method."
                    );

                    return;
                }


                const paymentMethod =
                    paymentElement.value
                        .toLowerCase()
                        .trim();


                /* BUTTON */

                const button =
                    checkoutForm.querySelector(
                        "button[type='submit']"
                    );


                if (button) {

                    button.disabled = true;

                    const buttonLabel = button.querySelector(
                        "#checkout-submit-label"
                    );
                    const loadingLabel = paymentMethod === "online"
                        ? "Opening secure payment..."
                        : "Placing COD order...";

                    if (buttonLabel) {
                        buttonLabel.textContent = loadingLabel;
                    } else {
                        button.textContent = loadingLabel;
                    }
                }


                /* =================================
                   CASH ON DELIVERY
                ================================= */

                if (
                    paymentMethod ===
                    "cod"
                ) {

                    await placeCODOrder(
                        items,
                        address,
                        button
                    );

                    return;
                }


                /* =================================
                   ONLINE PAYMENT
                ================================= */

                if (
                    paymentMethod ===
                    "online"
                ) {

                    await startRazorpayPayment(
                        items,
                        address
                    );

                    return;
                }


                /* INVALID METHOD */

                alert(
                    "Please select a valid payment method."
                );


                resetPlaceOrderButton();
            }
        );
    }
);