let cart = JSON.parse(localStorage.getItem("cart")) || [];

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
}

/* =========================================
SAVE CART
========================================= */

function saveCart() {
    localStorage.setItem("cart", JSON.stringify(cart));
    updateCartCount();
}

/* =========================================
ADD TO CART
========================================= */

function addToCart(name, price, image, stock) {
    stock = Number(stock);

    const existingItem = cart.find(function(item) {
        return item.name === name;
    });

    /* =====================================
       CHECK STOCK
    ===================================== */

    if (stock <= 0) {
        alert(name + " is currently out of stock.");
        return;
    }

    /* =====================================
       EXISTING ITEM
    ===================================== */

    if (existingItem) {
        const currentQuantity = Number(existingItem.quantity) || 0;

        if (currentQuantity >= stock) {
            alert("Only " + stock + " unit(s) of " + name + " are available.");
            return;
        }

        existingItem.quantity = currentQuantity + 1;

        /* Update stock in case product stock was changed */
        existingItem.stock = stock;
    }

    /* =====================================
       NEW ITEM
    ===================================== */
    else {
        cart.push({
            name: name,
            price: Number(price),
            quantity: 1,
            image: image || "mango-pickle.png",
            stock: stock
        });
    }

    saveCart();
    alert(name + " added to cart!");
}

/* =========================================
DISPLAY CART
========================================= */

function displayCart() {
    const cartItems = document.getElementById("cart-items");
    const cartTotal = document.getElementById("cart-total");

    if (!cartItems) return;

    cartItems.innerHTML = "";

    /* EMPTY CART */

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

    /* CART ITEMS */

    cart.forEach(function(item, index) {
        const price = Number(item.price) || 0;
        const quantity = Number(item.quantity) || 0;
        const stock = Number(item.stock);
        const subtotal = price * quantity;

        total += subtotal;

        const image = item.image || "mango-pickle.png";

        /* STOCK MESSAGE */
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
                    onclick="changeQuantity(${index}, 1)"
                >
                    +
                </button>
            `;
        }

        cartItems.innerHTML += `
            <div class="cart-item">
                <div class="cart-product-image">
                    <img
                        src="/static/images/${image}"
                        alt="${item.name}"
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
                            onclick="changeQuantity(${index}, -1)"
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
                        onclick="removeFromCart(${index})"
                    >
                        🗑️ Remove
                    </button>
                </div>
            </div>
        `;
    });

    if (cartTotal) {
        cartTotal.textContent = "Total: ₹" + total.toFixed(2);
    }
}

/* =========================================
CHANGE QUANTITY
========================================= */

function changeQuantity(index, amount) {
    if (!cart[index]) return;

    const item = cart[index];
    const currentQuantity = Number(item.quantity) || 0;
    const stock = Number(item.stock);

    /* PREVENT EXCEEDING STOCK */
    if (amount > 0 && !isNaN(stock) && currentQuantity >= stock) {
        alert("Only " + stock + " unit(s) of " + item.name + " are available.");
        return;
    }

    item.quantity = currentQuantity + amount;

    /* REMOVE IF ZERO */
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

    window.location.href = "/checkout";
}

/* =========================================
DISPLAY CHECKOUT
========================================= */

function displayCheckout() {
    const checkoutItems = document.getElementById("checkout-items");
    const checkoutTotal = document.getElementById("checkout-total");

    if (!checkoutItems) return;

    checkoutItems.innerHTML = "";

    let total = 0;

    cart.forEach(function(item) {
        const price = Number(item.price) || 0;
        const quantity = Number(item.quantity) || 0;
        const subtotal = price * quantity;

        total += subtotal;

        checkoutItems.innerHTML += `
            <div class="checkout-item">
                <p>
                    <strong>
                        ${item.name}
                    </strong>
                    × ${quantity}
                </p>
                <p>
                    ₹${subtotal.toFixed(2)}
                </p>
            </div>
        `;
    });

    if (checkoutTotal) {
        checkoutTotal.textContent = "Total: ₹" + total.toFixed(2);
    }
}

/* =========================================
PLACE ORDER & PAYMENT HANDLING
========================================= */

document.addEventListener("DOMContentLoaded", function() {
    updateCartCount();
    displayCart();
    displayCheckout();

    const checkoutForm = document.getElementById("checkout-form");

    if (!checkoutForm) return;

    checkoutForm.addEventListener("submit", async function(event) {
        event.preventDefault();

        if (cart.length === 0) {
            alert("Your cart is empty!");
            return;
        }

        /* GET CHECKOUT ADDRESS */
        const addressElement = document.getElementById("address");
        const address = addressElement ? addressElement.value.trim() : "";

        if (!address) {
            alert("Please enter your delivery address.");
            if (addressElement) {
                addressElement.focus();
            }
            return;
        }

        /* CALCULATE TOTAL */
        const total = cart.reduce(function(sum, item) {
            return sum + (Number(item.price) * Number(item.quantity));
        }, 0);

        /* PAYMENT METHOD */
        const paymentElement = document.querySelector('input[name="payment_method"]:checked');
        const paymentMethod = paymentElement ? paymentElement.value : "COD";

        /* PLACE ORDER BUTTON */
        const button = checkoutForm.querySelector("button[type='submit']");

        if (button) {
            button.disabled = true;
            button.textContent = "Processing Order...";
        }

        try {
            /* CASE 1: CASH ON DELIVERY */
            if (paymentMethod === "COD" || paymentMethod === "cod") {
                const response = await fetch("/place-order", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        items: cart,
                        total: total,
                        payment_method: "COD",
                        address: address
                    })
                });

                const result = await response.json();

                if (result.success) {
                    alert("Order placed successfully! Order #" + result.order_id);
                    cart = [];
                    localStorage.removeItem("cart");
                    updateCartCount();
                    window.location.href = "/order-history";
                } else {
                    alert(result.message || "Unable to place order.");
                    if (button) {
                        button.disabled = false;
                        button.textContent = "Place Order";
                    }
                }
            } 
            /* CASE 2: RAZORPAY / ONLINE PAYMENT */
            else {
                /* Step A: Create Razorpay Order on Backend */
                const createOrderRes = await fetch("/create-razorpay-order", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        amount: total,
                        items: cart,
                        address: address
                    })
                });

                const razorpayData = await createOrderRes.json();

                if (!razorpayData.success) {
                    alert(razorpayData.message || "Failed to initialize payment.");
                    if (button) {
                        button.disabled = false;
                        button.textContent = "Place Order";
                    }
                    return;
                }

                /* Step B: Launch Razorpay Checkout Modal */
                const options = {
                    key: razorpayData.key_id,
                    amount: razorpayData.amount,
                    currency: "INR",
                    name: "Pickles Store",
                    description: "Order Payment",
                    order_id: razorpayData.razorpay_order_id,
                    handler: async function (response) {
                        /* Step C: Verify Payment on Backend */
                        const verifyRes = await fetch("/verify-payment", {
                            method: "POST",
                            headers: {
                                "Content-Type": "application/json"
                            },
                            body: JSON.stringify({
                                razorpay_payment_id: response.razorpay_payment_id,
                                razorpay_order_id: response.razorpay_order_id,
                                razorpay_signature: response.razorpay_signature,
                                items: cart,
                                total: total,
                                address: address,
                                payment_method: "Online"
                            })
                        });

                        const verifyResult = await verifyRes.json();

                        if (verifyResult.success) {
                            alert("Payment successful! Order #" + verifyResult.order_id);
                            cart = [];
                            localStorage.removeItem("cart");
                            updateCartCount();
                            window.location.href = "/order-history";
                        } else {
                            alert(verifyResult.message || "Payment verification failed.");
                            if (button) {
                                button.disabled = false;
                                button.textContent = "Place Order";
                            }
                        }
                    },
                    modal: {
                        ondismiss: function() {
                            if (button) {
                                button.disabled = false;
                                button.textContent = "Place Order";
                            }
                        }
                    },
                    theme: {
                        color: "#285c41"
                    }
                };

                const rzp = new Razorpay(options);
                rzp.open();
            }
        } catch (error) {
            console.error("Order error:", error);
            alert("Unable to process order. Please try again.");

            if (button) {
                button.disabled = false;
                button.textContent = "Place Order";
            }
        }
    });
});