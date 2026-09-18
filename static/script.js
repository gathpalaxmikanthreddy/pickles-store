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

    if (stock <= 0) {
        alert(name + " is currently out of stock.");
        return;
    }

    if (existingItem) {
        const currentQuantity = Number(existingItem.quantity) || 0;

        if (currentQuantity >= stock) {
            alert(
                "Only " +
                stock +
                " unit(s) of " +
                name +
                " are available."
            );
            return;
        }

        existingItem.quantity = currentQuantity + 1;
        existingItem.stock = stock;
    } else {
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


    checkoutItems.innerHTML = "";


    let total = 0;


    cart.forEach(function(item) {

        const price =
            Number(item.price) || 0;

        const quantity =
            Number(item.quantity) || 0;

        const subtotal =
            price * quantity;


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

        button.textContent =
            "Place Order";
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
                            "application/json"
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
                        "application/json"
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
                        "application/json"
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

        updateCartCount();

        displayCart();

        displayCheckout();


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

                    button.textContent =
                        "Placing Order...";
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