import os
import json
import random
import time
from datetime import date, datetime, timedelta
from uuid import uuid4

import requests
import razorpay
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("SECRET_KEY must be set before starting the application.")

database_url = os.getenv("DATABASE_URL", "sqlite:///pickels_store.db")

if database_url.startswith("postgres://"):
    database_url = database_url.replace(
        "postgres://", "postgresql+psycopg://", 1
    )
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace(
        "postgresql://", "postgresql+psycopg://", 1
    )

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "0") == "1"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# --------------------------------------------------
# IMAGE UPLOAD SETTINGS
# --------------------------------------------------

UPLOAD_FOLDER = os.path.join(app.root_path, "static", "images")

ALLOWED_IMAGE_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "webp",
}

MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_IMAGE_SIZE

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)


# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def allowed_image(filename):
    if not filename or "." not in filename:
        return False

    extension = filename.rsplit(".", 1)[1].lower()

    return extension in ALLOWED_IMAGE_EXTENSIONS

def save_uploaded_image(file):
    """
    Save an uploaded image into static/images.

    Returns the filename that should be stored in the database,
    or None if the upload is invalid.
    """

    if not file:
        return None

    if not file.filename:
        return None

    if not allowed_image(file.filename):
        return None

    original_name = secure_filename(file.filename)

    if not original_name:
        return None

    extension = original_name.rsplit(".", 1)[1].lower()

    unique_name = f"{uuid4().hex}.{extension}"

    save_path = os.path.join(
        app.config["UPLOAD_FOLDER"],
        unique_name,
    )

    file.save(save_path)

    return unique_name


@app.errorhandler(413)
def file_too_large(error):
    if request.path.startswith("/admin"):
        return redirect("/admin/products")

    return "Uploaded image is too large. Maximum size is 5 MB.", 413


@app.template_filter("fromjson")
def fromjson_filter(value):
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []



# --------------------------------------------------
# RAZORPAY
# --------------------------------------------------

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

razorpay_client = razorpay.Client(
    auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)
)


# --------------------------------------------------
# DATABASE MODELS
# --------------------------------------------------

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(
        db.String(100),
        nullable=False
    )

    mobile = db.Column(
        db.String(20),
        unique=True,
        nullable=False
    )

    password = db.Column(
        db.String(255),
        nullable=True
    )

    address = db.Column(
        db.Text,
        nullable=True
    )

    created_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp()
    )

    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )


class Product(db.Model):
    id = db.Column(
        db.Integer,
        primary_key=True
    )

    name = db.Column(
        db.String(100),
        nullable=False
    )

    price = db.Column(
        db.Float,
        nullable=False
    )

    unit = db.Column(
        db.String(50),
        nullable=False
    )

    image = db.Column(
        db.String(200),
        nullable=False
    )

    description = db.Column(
        db.Text,
        nullable=True
    )

    active = db.Column(
        db.Boolean,
        default=True
    )

    stock = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )


class Review(db.Model):
    id = db.Column(
        db.Integer,
        primary_key=True
    )

    product_id = db.Column(
        db.Integer,
        db.ForeignKey("product.id"),
        nullable=False
    )

    customer_id = db.Column(
        db.Integer,
        db.ForeignKey("customer.id"),
        nullable=False
    )

    rating = db.Column(
        db.Integer,
        nullable=False
    )

    comment = db.Column(
        db.Text,
        nullable=True
    )

    created_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp()
    )

    customer = db.relationship(
        "Customer",
        backref="reviews"
    )


class Order(db.Model):
    id = db.Column(
        db.Integer,
        primary_key=True
    )

    name = db.Column(
        db.String(100),
        nullable=False
    )

    mobile = db.Column(
        db.String(20),
        nullable=False
    )

    address = db.Column(
        db.Text,
        nullable=False
    )

    items = db.Column(
        db.Text,
        nullable=False
    )

    total = db.Column(
        db.Float,
        nullable=False
    )

    status = db.Column(
        db.String(50),
        default="Pending"
    )

    payment_method = db.Column(
        db.String(30),
        default="COD"
    )

    payment_status = db.Column(
        db.String(30),
        default="Pending"
    )

    razorpay_order_id = db.Column(
        db.String(100),
        nullable=True,
        unique=True
    )

    razorpay_payment_id = db.Column(
        db.String(100),
        nullable=True,
        unique=True
    )

    created_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp()
    )


# --------------------------------------------------
# DATABASE SETUP
# --------------------------------------------------

with app.app_context():

    db.create_all()

    inspector = inspect(db.engine)

    order_columns = [
        column["name"]
        for column in inspector.get_columns("order")
    ]

    if "created_at" not in order_columns:

        with db.engine.begin() as connection:

            connection.execute(
                text(
                    'ALTER TABLE "order" '
                    "ADD COLUMN created_at TIMESTAMP"
                )
            )

    if "payment_method" not in order_columns:

        with db.engine.begin() as connection:

            connection.execute(
                text(
                    'ALTER TABLE "order" '
                    "ADD COLUMN payment_method "
                    "VARCHAR(30) DEFAULT \'COD\'"
                )
            )

    if "payment_status" not in order_columns:

        with db.engine.begin() as connection:

            connection.execute(
                text(
                    'ALTER TABLE "order" '
                    "ADD COLUMN payment_status "
                    "VARCHAR(30) DEFAULT 'Pending'"
                )
            )

    if "razorpay_order_id" not in order_columns:

        with db.engine.begin() as connection:

            connection.execute(
                text(
                    'ALTER TABLE "order" '
                    "ADD COLUMN razorpay_order_id VARCHAR(100)"
                )
            )

    if "razorpay_payment_id" not in order_columns:

        with db.engine.begin() as connection:

            connection.execute(
                text(
                    'ALTER TABLE "order" '
                    "ADD COLUMN razorpay_payment_id VARCHAR(100)"
                )
            )

    customer_columns = [
        column["name"]
        for column in inspector.get_columns("customer")
    ]

    if "password" not in customer_columns:
        with db.engine.begin() as connection:
            connection.execute(
                text(
                    'ALTER TABLE "customer" '
                    "ADD COLUMN password VARCHAR(255)"
                )
            )

    product_columns = [
        column["name"]
        for column in inspector.get_columns("product")
    ]

    if "stock" not in product_columns:

        with db.engine.begin() as connection:

            connection.execute(
                text(
                    'ALTER TABLE "product" '
                    "ADD COLUMN stock INTEGER DEFAULT 0"
                )
            )


# --------------------------------------------------
# SEND SMS
# --------------------------------------------------

TEXTBEE_API_KEY = os.getenv("TEXTBEE_API_KEY")
TEXTBEE_DEVICE_ID = os.getenv("TEXTBEE_DEVICE_ID")
TEXTBEE_URL = "https://api.textbee.dev/api/v1/gateway/send-sms"


def format_mobile(phone_number):
    phone_number = str(phone_number or "").strip().replace(" ", "")

    if phone_number.startswith("+91"):
        return phone_number

    if phone_number.startswith("91") and len(phone_number) == 12:
        return "+" + phone_number

    if phone_number.startswith("0") and len(phone_number) == 11:
        return "+91" + phone_number[1:]

    if phone_number.isdigit() and len(phone_number) == 10:
        return "+91" + phone_number

    return phone_number


def send_sms(phone, message):
    """Send an SMS through TextBee."""
    if not TEXTBEE_API_KEY:
        print("TEXTBEE ERROR: API key not configured")
        return False

    if not phone:
        print("TEXTBEE ERROR: phone number missing")
        return False

    try:
        headers = {
            "Content-Type": "application/json",
            "x-api-key": TEXTBEE_API_KEY,
        }

        payload = {
            "recipients": [format_mobile(phone)],
            "message": message,
        }

        if TEXTBEE_DEVICE_ID:
            payload["deviceId"] = TEXTBEE_DEVICE_ID

        response = requests.post(
            TEXTBEE_URL,
            headers=headers,
            json=payload,
            timeout=15,
        )

        print("TEXTBEE STATUS:", response.status_code)
        print("TEXTBEE RESPONSE:", response.text)

        return 200 <= response.status_code < 300

    except requests.RequestException as exc:
        print("TEXTBEE ERROR:", exc)
        return False


# --------------------------------------------------
# HOME
# --------------------------------------------------

@app.route("/")
def home():

    products = (
        Product.query
        .filter_by(active=True)
        .order_by(Product.id.asc())
        .all()
    )

    return render_template(
        "index.html",
        products=products
    )


# --------------------------------------------------
# PRODUCT DETAILS
# --------------------------------------------------

@app.route("/product/<int:product_id>")
def product_details(product_id):

    product = Product.query.get_or_404(product_id)

    if not product.active:

        return redirect("/")

    reviews = (
        Review.query
        .filter_by(product_id=product.id)
        .order_by(Review.id.desc())
        .all()
    )

    review_count = len(reviews)

    average_rating = (
        round(
            sum(review.rating for review in reviews)
            / review_count,
            1,
        )
        if review_count > 0
        else 0
    )

    return render_template(
        "product_details.html",
        product=product,
        reviews=reviews,
        average_rating=average_rating,
        review_count=review_count,
    )


# --------------------------------------------------
# ADD REVIEW
# --------------------------------------------------

@app.route(
    "/product/<int:product_id>/review",
    methods=["POST"]
)
def add_review(product_id):

    if not session.get("user_mobile"):

        return redirect("/login")

    product = Product.query.get_or_404(product_id)

    if not product.active:

        return redirect("/")

    rating = request.form.get(
        "rating",
        ""
    ).strip()

    comment = request.form.get(
        "comment",
        ""
    ).strip()

    try:

        rating = int(rating)

    except (TypeError, ValueError):

        return redirect(
            f"/product/{product_id}"
        )

    if rating < 1 or rating > 5:

        return redirect(
            f"/product/{product_id}"
        )

    if len(comment) > 1000:

        comment = comment[:1000]

    customer = Customer.query.filter_by(
        mobile=session.get("user_mobile")
    ).first()

    if not customer:

        return redirect("/login")

    review = Review(
        product_id=product.id,
        customer_id=customer.id,
        rating=rating,
        comment=comment,
    )

    db.session.add(review)

    db.session.commit()

    return redirect(
        f"/product/{product_id}"
    )


# --------------------------------------------------
# CART
# --------------------------------------------------

@app.route("/cart")
def cart():

    return render_template("cart.html")


# --------------------------------------------------
# CUSTOMER REGISTRATION
# --------------------------------------------------

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        mobile = request.form.get("mobile", "").strip()
        address = request.form.get("address", "").strip()
        password = request.form.get("password", "").strip()
        confirm_password = request.form.get(
            "confirm_password",
            ""
        ).strip()

        if not all([
            name,
            mobile,
            address,
            password,
            confirm_password,
        ]):
            return render_template(
                "register.html",
                error="Please fill all fields."
            )

        if len(password) < 6:
            return render_template(
                "register.html",
                error="Password must be at least 6 characters."
            )

        if password != confirm_password:
            return render_template(
                "register.html",
                error="Passwords do not match."
            )

        mobile = mobile.replace(" ", "")

        if mobile.startswith("+91"):
            mobile = mobile[3:]

        if mobile.startswith("91") and len(mobile) == 12:
            mobile = mobile[2:]

        if len(mobile) != 10 or not mobile.isdigit():
            return render_template(
                "register.html",
                error="Please enter a valid 10-digit mobile number."
            )

        customer = Customer.query.filter_by(
            mobile=mobile
        ).first()

        if customer and customer.password:
            return render_template(
                "register.html",
                error="This mobile number is already registered. Please login."
            )

        otp = str(
            random.randint(100000, 999999)
        )

        session["register_otp"] = otp
        session["register_otp_mobile"] = mobile
        session["register_name"] = name
        session["register_address"] = address
        session["register_password"] = generate_password_hash(password)
        session["register_otp_expires"] = time.time() + 300
        session["register_otp_attempts"] = 0

        message = (
            f"Your PICKELS STORE registration OTP is {otp}. "
            "Do not share this OTP with anyone."
        )

        if not send_sms("+91" + mobile, message):
            for key in [
                "register_otp",
                "register_otp_mobile",
                "register_name",
                "register_address",
                "register_password",
                "register_otp_expires",
                "register_otp_attempts",
            ]:
                session.pop(key, None)

            return render_template(
                "register.html",
                error="Unable to send OTP. Please try again."
            )

        return redirect("/verify-registration-otp")

    return render_template("register.html")


# --------------------------------------------------
# VERIFY REGISTRATION OTP
# --------------------------------------------------

@app.route(
    "/verify-registration-otp",
    methods=["GET", "POST"]
)
def verify_registration_otp():

    if not session.get("register_otp"):
        return redirect("/register")

    if request.method == "POST":

        if time.time() > session.get(
            "register_otp_expires",
            0
        ):
            return render_template(
                "verify_registration_otp.html",
                error="OTP expired. Please register again."
            )

        entered_otp = request.form.get(
            "otp",
            ""
        ).strip()

        attempts = session.get(
            "register_otp_attempts",
            0
        )

        if attempts >= 5:
            return render_template(
                "verify_registration_otp.html",
                error="Too many incorrect attempts. Please register again."
            )

        if entered_otp != session.get("register_otp"):
            session["register_otp_attempts"] = attempts + 1

            return render_template(
                "verify_registration_otp.html",
                error="Invalid OTP. Please try again."
            )

        mobile = session.get(
            "register_otp_mobile"
        )
        name = session.get(
            "register_name",
            ""
        )
        address = session.get(
            "register_address",
            ""
        )
        password_hash = session.get(
            "register_password"
        )

        if not mobile or not password_hash:
            return redirect("/register")

        customer = Customer.query.filter_by(
            mobile=mobile
        ).first()

        if customer:
            customer.name = name
            customer.address = address
            customer.password = password_hash
        else:
            customer = Customer(
                name=name,
                mobile=mobile,
                address=address,
                password=password_hash,
            )
            db.session.add(customer)

        db.session.commit()

        session["user_mobile"] = mobile
        session["user_name"] = name
        session["user_address"] = address

        for key in [
            "register_otp",
            "register_otp_mobile",
            "register_name",
            "register_address",
            "register_password",
            "register_otp_expires",
            "register_otp_attempts",
        ]:
            session.pop(key, None)

        return redirect("/")

    return render_template(
        "verify_registration_otp.html"
    )


# --------------------------------------------------
# CUSTOMER LOGIN
# --------------------------------------------------

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        mobile = request.form.get(
            "mobile",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        ).strip()

        # ------------------------------------------
        # REQUIRED FIELDS
        # ------------------------------------------

        if not mobile or not password:

            return render_template(
                "login.html",
                error="Please enter mobile number and password."
            )

        # ------------------------------------------
        # PASSWORD VALIDATION
        # ------------------------------------------

        if len(password) < 6:

            return render_template(
                "login.html",
                error="Password must be at least 6 characters."
            )

        # ------------------------------------------
        # MOBILE NUMBER NORMALIZATION
        # ------------------------------------------

        mobile = mobile.replace(
            " ",
            ""
        )

        if mobile.startswith("+91"):

            mobile = mobile[3:]

        if mobile.startswith("91") and len(mobile) == 12:

            mobile = mobile[2:]

        if len(mobile) != 10 or not mobile.isdigit():

            return render_template(
                "login.html",
                error="Please enter a valid 10-digit mobile number.",
            )

        # ------------------------------------------
        # FIND CUSTOMER
        # ------------------------------------------

        customer = Customer.query.filter_by(
            mobile=mobile
        ).first()

        if not customer:

            return render_template(
                "login.html",
                error="Account not found. Please register first."
            )

        # ------------------------------------------
        # PASSWORD CHECK
        # ------------------------------------------

        if not customer.password:

            return render_template(
                "login.html",
                error="Please reset your password using Forgot Password."
            )

        if not check_password_hash(
            customer.password,
            password
        ):

            return render_template(
                "login.html",
                error="Invalid mobile number or password."
            )

        session["user_mobile"] = customer.mobile

        session["user_name"] = customer.name

        session["user_address"] = (
            customer.address or ""
        )

        return redirect("/")

    return render_template(
        "login.html"
    )


# --------------------------------------------------
# FORGOT PASSWORD
# --------------------------------------------------

@app.route(
    "/forgot-password",
    methods=["GET", "POST"]
)
def forgot_password():

    if request.method == "POST":

        mobile = request.form.get(
            "mobile",
            ""
        ).strip().replace(" ", "")

        if mobile.startswith("+91"):
            mobile = mobile[3:]

        if mobile.startswith("91") and len(mobile) == 12:
            mobile = mobile[2:]

        if len(mobile) != 10 or not mobile.isdigit():
            return render_template(
                "forgot_password.html",
                error="Please enter a valid 10-digit mobile number."
            )

        customer = Customer.query.filter_by(
            mobile=mobile
        ).first()

        if not customer:
            return render_template(
                "forgot_password.html",
                error="Account not found. Please register first."
            )

        otp = str(random.randint(100000, 999999))

        session["reset_otp"] = otp
        session["reset_otp_mobile"] = mobile
        session["reset_otp_expires"] = time.time() + 300
        session["reset_otp_attempts"] = 0
        session.pop("reset_otp_verified", None)

        message = (
            f"Your PICKELS STORE password reset OTP is {otp}. "
            "Do not share this OTP with anyone."
        )

        if not send_sms("+91" + mobile, message):
            for key in [
                "reset_otp",
                "reset_otp_mobile",
                "reset_otp_expires",
                "reset_otp_attempts",
                "reset_otp_verified",
            ]:
                session.pop(key, None)

            return render_template(
                "forgot_password.html",
                error="Unable to send OTP. Please try again."
            )

        return redirect("/verify-reset-otp")

    return render_template("forgot_password.html")


@app.route(
    "/verify-reset-otp",
    methods=["GET", "POST"]
)
def verify_reset_otp():

    if not session.get("reset_otp"):
        return redirect("/forgot-password")

    if request.method == "POST":

        if time.time() > session.get("reset_otp_expires", 0):
            for key in [
                "reset_otp",
                "reset_otp_mobile",
                "reset_otp_expires",
                "reset_otp_attempts",
            ]:
                session.pop(key, None)

            return render_template(
                "verify_reset_otp.html",
                error="OTP expired. Please request a new one."
            )

        attempts = session.get("reset_otp_attempts", 0)

        if attempts >= 5:
            for key in [
                "reset_otp",
                "reset_otp_mobile",
                "reset_otp_expires",
                "reset_otp_attempts",
            ]:
                session.pop(key, None)

            return render_template(
                "verify_reset_otp.html",
                error="Too many incorrect attempts. Please request a new OTP."
            )

        entered_otp = request.form.get(
            "otp",
            ""
        ).strip()

        if entered_otp != session.get("reset_otp"):
            session["reset_otp_attempts"] = attempts + 1

            return render_template(
                "verify_reset_otp.html",
                error="Invalid OTP. Please try again."
            )

        session["reset_otp_verified"] = True
        session.pop("reset_otp", None)
        session.pop("reset_otp_expires", None)
        session.pop("reset_otp_attempts", None)

        return redirect("/reset-password")

    return render_template("verify_reset_otp.html")


@app.route(
    "/reset-password",
    methods=["GET", "POST"]
)
def reset_password():

    mobile = session.get("reset_otp_mobile")

    if not mobile or not session.get("reset_otp_verified"):
        return redirect("/forgot-password")

    customer = Customer.query.filter_by(
        mobile=mobile
    ).first()

    if not customer:
        session.pop("reset_otp_mobile", None)
        session.pop("reset_otp_verified", None)
        return redirect("/forgot-password")

    if request.method == "POST":

        password = request.form.get(
            "password",
            ""
        ).strip()
        confirm_password = request.form.get(
            "confirm_password",
            ""
        ).strip()

        if not password or not confirm_password:
            return render_template(
                "reset_password.html",
                error="Please fill in both password fields."
            )

        if len(password) < 6:
            return render_template(
                "reset_password.html",
                error="Password must be at least 6 characters."
            )

        if password != confirm_password:
            return render_template(
                "reset_password.html",
                error="Passwords do not match."
            )

        customer.password = generate_password_hash(password)
        db.session.commit()

        session.pop("reset_otp_mobile", None)
        session.pop("reset_otp_verified", None)

        return redirect("/login")

    return render_template("reset_password.html")


# --------------------------------------------------
# CUSTOMER ACCOUNT
# --------------------------------------------------

@app.route("/account")
def account():

    if not session.get("user_mobile"):

        return redirect("/login")

    user_mobile = session.get(
        "user_mobile"
    )

    customer = Customer.query.filter_by(
        mobile=user_mobile
    ).first()

    if customer:

        session["user_name"] = customer.name
        session["user_address"] = (
            customer.address or ""
        )

    total_orders = Order.query.filter_by(
        mobile=user_mobile
    ).count()

    recent_orders = (
        Order.query
        .filter_by(mobile=user_mobile)
        .order_by(Order.id.desc())
        .limit(5)
        .all()
    )

    return render_template(
        "account.html",
        total_orders=total_orders,
        recent_orders=recent_orders,
    )


# --------------------------------------------------
# UPDATE ADDRESS
# --------------------------------------------------

@app.route(
    "/update-address",
    methods=["POST"]
)
def update_address():

    if not session.get("user_mobile"):

        return redirect("/login")

    mobile = session.get(
        "user_mobile"
    )

    address = request.form.get(
        "address",
        ""
    ).strip()

    if not address:

        return redirect("/account")

    customer = Customer.query.filter_by(
        mobile=mobile
    ).first()

    if not customer:

        customer = Customer(
            name=session.get(
                "user_name",
                "Customer"
            ),
            mobile=mobile,
            address=address,
        )

        db.session.add(customer)

    else:

        customer.address = address

    db.session.commit()

    session["user_address"] = address

    return redirect("/account")


# --------------------------------------------------
# CUSTOMER LOGOUT
# --------------------------------------------------

@app.route("/logout")
def logout():

    session.pop(
        "user_mobile",
        None
    )

    session.pop(
        "user_name",
        None
    )

    session.pop(
        "user_address",
        None
    )

    return redirect("/")


# --------------------------------------------------
# CHECKOUT
# --------------------------------------------------

@app.route("/checkout")
def checkout():

    if not session.get("user_mobile"):

        return redirect("/login")

    customer = Customer.query.filter_by(
        mobile=session.get("user_mobile")
    ).first()

    if customer:

        session["user_name"] = customer.name
        session["user_address"] = (
            customer.address or ""
        )

    return render_template(
        "checkout.html"
    )


# --------------------------------------------------
# PLACE ORDER
# --------------------------------------------------

@app.route(
    "/place-order",
    methods=["POST"]
)
def place_order():

    if not session.get("user_mobile"):

        return jsonify(
            {
                "success": False,
                "message": "Please login first."
            }
        ), 401

    try:

        data = request.get_json()

        if not data:

            return jsonify(
                {
                    "success": False,
                    "message": "Invalid request."
                }
            ), 400

        items = data.get(
            "items",
            []
        )

        payment_method = data.get(
            "payment_method",
            "COD"
        )

        name = session.get(
            "user_name",
            ""
        )

        mobile = session.get(
            "user_mobile",
            ""
        )

        address = data.get(
            "address",
            ""
        )

        if not address:

            address = session.get(
                "user_address",
                ""
            )

        address = str(
            address
        ).strip()

        if not address:

            return jsonify(
                {
                    "success": False,
                    "message": "Please enter your delivery address."
                }
            ), 400

        if not items:

            return jsonify(
                {
                    "success": False,
                    "message": "Your cart is empty."
                }
            ), 400

        validated_items = []
        products_by_item = []

        for item in items:

            if not isinstance(
                item,
                dict
            ):

                return jsonify(
                    {
                        "success": False,
                        "message": "Invalid cart item."
                    }
                ), 400

            product_name = str(
                item.get(
                    "name",
                    ""
                )
            ).strip()

            try:

                quantity = int(
                    item.get(
                        "quantity",
                        1
                    )
                )

            except (
                TypeError,
                ValueError
            ):

                quantity = 1

            product = Product.query.filter(
                db.func.lower(Product.name)
                == product_name.lower()
            ).first()

            if not product:

                return jsonify(
                    {
                        "success": False,
                        "message": (
                            f"Product '{product_name}' "
                            "is no longer available."
                        )
                    }
                ), 400

            if not product.active:

                return jsonify(
                    {
                        "success": False,
                        "message": (
                            f"{product.name} "
                            "is currently unavailable."
                        )
                    }
                ), 400

            if quantity <= 0:

                return jsonify(
                    {
                        "success": False,
                        "message": (
                            f"Invalid quantity "
                            f"for {product.name}."
                        )
                    }
                ), 400

            if product.stock < quantity:

                return jsonify(
                    {
                        "success": False,
                        "message": (
                            f"Only {product.stock} "
                            f"unit(s) of {product.name} "
                            "are available."
                        )
                    }
                ), 400

            products_by_item.append(
                (
                    product,
                    quantity
                )
            )

            validated_items.append(
                {
                    "name": product.name,
                    "price": product.price,
                    "quantity": quantity,
                    "image": product.image,
                }
            )

        calculated_total = sum(
            product.price * quantity
            for product, quantity
            in products_by_item
        )

        customer = Customer.query.filter_by(
            mobile=mobile
        ).first()

        if customer:

            customer.name = name
            customer.address = address

        else:

            customer = Customer(
                name=name,
                mobile=mobile,
                address=address
            )

            db.session.add(customer)

        session["user_address"] = address

        for product, quantity in products_by_item:

            product.stock -= quantity

        order = Order(
            name=name,
            mobile=mobile,
            address=address,
            items=json.dumps(
                validated_items
            ),
            total=calculated_total,
            status="Pending",
            payment_method=payment_method,
            payment_status=(
                "Pending"
                if str(payment_method).lower() == "cod"
                else "Pending"
            ),
        )

        db.session.add(order)

        db.session.commit()

        sms_message = (
            f"PICKELS STORE: Order #{order.id} "
            f"placed successfully. "
            f"Total ₹{calculated_total:.2f}. "
            f"Payment: {payment_method.upper()}. "
            f"Status: Pending."
        )

        send_sms(
            "+91" + mobile,
            sms_message
        )

        return jsonify(
            {
                "success": True,
                "order_id": order.id,
                "message": "Order placed successfully.",
            }
        )

    except Exception as e:

        db.session.rollback()

        print(
            "Place order error:",
            e
        )

        return jsonify(
            {
                "success": False,
                "message": "Unable to place order."
            }
        ), 500


# --------------------------------------------------
# CREATE RAZORPAY ORDER
# --------------------------------------------------

@app.route(
    "/create-razorpay-order",
    methods=["POST"]
)
def create_razorpay_order():

    if not session.get("user_mobile"):

        return jsonify(
            {
                "success": False,
                "message": "Please login first."
            }
        ), 401

    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:

        return jsonify(
            {
                "success": False,
                "message": "Online payment is not configured."
            }
        ), 500

    try:

        data = request.get_json(
            silent=True
        ) or {}

        items = data.get(
            "items",
            []
        )

        if not isinstance(
            items,
            list
        ) or not items:

            return jsonify(
                {
                    "success": False,
                    "message": "Your cart is empty."
                }
            ), 400

        total = 0

        for item in items:

            if not isinstance(
                item,
                dict
            ):

                return jsonify(
                    {
                        "success": False,
                        "message": "Invalid cart item."
                    }
                ), 400

            product_name = str(
                item.get(
                    "name",
                    ""
                )
            ).strip()

            try:

                quantity = int(
                    item.get(
                        "quantity",
                        0
                    )
                )

            except (
                TypeError,
                ValueError
            ):

                return jsonify(
                    {
                        "success": False,
                        "message": "Invalid quantity."
                    }
                ), 400

            if not product_name or quantity <= 0:

                return jsonify(
                    {
                        "success": False,
                        "message": "Invalid cart item."
                    }
                ), 400

            product = Product.query.filter(
                db.func.lower(Product.name)
                == product_name.lower()
            ).first()

            if not product or not product.active:

                return jsonify(
                    {
                        "success": False,
                        "message": (
                            f"Product '{product_name}' "
                            "is no longer available."
                        )
                    }
                ), 400

            if product.stock < quantity:

                return jsonify(
                    {
                        "success": False,
                        "message": (
                            f"Only {product.stock} "
                            f"unit(s) of {product.name} "
                            "are available."
                        )
                    }
                ), 400

            total += product.price * quantity

        amount_paise = int(
            round(
                total * 100
            )
        )

        receipt = (
            f"pickle_{session['user_mobile']}_"
            f"{random.randint(100000, 999999)}"
        )

        razorpay_order = razorpay_client.order.create(
            {
                "amount": amount_paise,
                "currency": "INR",
                "receipt": receipt,
                "notes": {
                    "customer_mobile": session["user_mobile"],
                    "store": "PICKELS STORE",
                },
            }
        )

        return jsonify(
            {
                "success": True,
                "order_id": razorpay_order["id"],
                "amount": amount_paise,
                "currency": "INR",
                "key_id": RAZORPAY_KEY_ID,
            }
        )

    except Exception as e:

        print(
            "Razorpay order error:",
            e
        )

        return jsonify(
            {
                "success": False,
                "message": (
                    "Unable to create online payment order."
                )
            }
        ), 500


# --------------------------------------------------
# VERIFY RAZORPAY PAYMENT
# --------------------------------------------------

@app.route(
    "/verify-razorpay-payment",
    methods=["POST"]
)
def verify_razorpay_payment():

    if not session.get("user_mobile"):
        return jsonify({"success": False, "message": "Please login first."}), 401

    try:
        data = request.get_json(silent=True) or {}
        razorpay_order_id = str(data.get("razorpay_order_id", "")).strip()
        razorpay_payment_id = str(data.get("razorpay_payment_id", "")).strip()
        razorpay_signature = str(data.get("razorpay_signature", "")).strip()
        items = data.get("items", [])
        address = str(data.get("address", "")).strip() or str(session.get("user_address", "")).strip()

        if not razorpay_order_id or not razorpay_payment_id or not razorpay_signature:
            return jsonify({"success": False, "message": "Payment verification data is missing."}), 400
        if not isinstance(items, list) or not items:
            return jsonify({"success": False, "message": "Your cart is empty."}), 400
        if not address:
            return jsonify({"success": False, "message": "Please enter your delivery address."}), 400

        razorpay_client.utility.verify_payment_signature({
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature,
        })

        existing_order = Order.query.filter(
            (Order.razorpay_payment_id == razorpay_payment_id) |
            (Order.razorpay_order_id == razorpay_order_id)
        ).first()
        if existing_order:
            return jsonify({"success": True, "order_id": existing_order.id, "message": "Payment already processed."})

        razorpay_order = razorpay_client.order.fetch(razorpay_order_id)
        if str(razorpay_order.get("currency", "")).upper() != "INR":
            return jsonify({"success": False, "message": "Invalid payment currency."}), 400

        validated_items = []
        products_by_item = []
        calculated_total = 0

        for item in items:
            if not isinstance(item, dict):
                return jsonify({"success": False, "message": "Invalid cart item."}), 400
            product_name = str(item.get("name", "")).strip()
            try:
                quantity = int(item.get("quantity", 0))
            except (TypeError, ValueError):
                return jsonify({"success": False, "message": "Invalid quantity."}), 400
            if not product_name or quantity <= 0:
                return jsonify({"success": False, "message": "Invalid cart item."}), 400

            product = Product.query.filter(db.func.lower(Product.name) == product_name.lower()).first()
            if not product or not product.active:
                return jsonify({"success": False, "message": f"Product '{product_name}' is no longer available."}), 400
            if product.stock < quantity:
                return jsonify({"success": False, "message": f"Only {product.stock} unit(s) of {product.name} are available."}), 400

            products_by_item.append((product, quantity))
            validated_items.append({
                "name": product.name,
                "price": product.price,
                "quantity": quantity,
                "image": product.image,
            })
            calculated_total += product.price * quantity

        expected_amount = int(round(calculated_total * 100))
        try:
            razorpay_amount = int(razorpay_order.get("amount", 0))
        except (TypeError, ValueError):
            razorpay_amount = 0
        if razorpay_amount != expected_amount:
            return jsonify({"success": False, "message": "Payment amount does not match the order total."}), 400

        payment = razorpay_client.payment.fetch(razorpay_payment_id)
        if str(payment.get("order_id", "")) != razorpay_order_id:
            return jsonify({"success": False, "message": "Payment/order mismatch."}), 400
        if int(payment.get("amount", 0)) != expected_amount:
            return jsonify({"success": False, "message": "Payment amount mismatch."}), 400
        if str(payment.get("currency", "")).upper() != "INR":
            return jsonify({"success": False, "message": "Invalid payment currency."}), 400

        payment_status = str(payment.get("status", "")).lower()
        if payment_status == "authorized":
            razorpay_client.payment.capture(razorpay_payment_id, expected_amount)
            payment = razorpay_client.payment.fetch(razorpay_payment_id)
            payment_status = str(payment.get("status", "")).lower()

        if payment_status != "captured":
            return jsonify({"success": False, "message": "Payment is not captured yet. Please contact PICKELS STORE."}), 400

        mobile = session.get("user_mobile", "")
        name = session.get("user_name", "")
        customer = Customer.query.filter_by(mobile=mobile).first()
        if customer:
            customer.name = name
            customer.address = address
        else:
            db.session.add(Customer(name=name, mobile=mobile, address=address))
        session["user_address"] = address

        for product, quantity in products_by_item:
            product.stock -= quantity

        order = Order(
            name=name,
            mobile=mobile,
            address=address,
            items=json.dumps(validated_items),
            total=calculated_total,
            status="Pending",
            payment_method="Online",
            payment_status="Paid",
            razorpay_order_id=razorpay_order_id,
            razorpay_payment_id=razorpay_payment_id,
        )
        db.session.add(order)
        db.session.commit()

        send_sms(
            "+91" + mobile,
            f"PICKELS STORE: Online payment received for Order #{order.id}. Total ₹{calculated_total:.2f}. Status: Pending."
        )

        return jsonify({"success": True, "order_id": order.id, "message": "Payment successful and order placed."})

    except Exception as e:
        db.session.rollback()
        print("Razorpay verification error:", e)
        return jsonify({"success": False, "message": "Payment verification failed."}), 400


# --------------------------------------------------
# CANCEL ORDER
# --------------------------------------------------

@app.route(
    "/cancel-order/<int:order_id>",
    methods=["POST"]
)
def cancel_order(order_id):

    mobile = session.get(
        "user_mobile"
    )

    if not mobile:

        return redirect("/login")

    order = Order.query.filter_by(
        id=order_id,
        mobile=mobile
    ).first_or_404()

    if order.status != "Pending":

        return redirect(
            "/order-history"
        )

    try:

        raw_items = json.loads(
            order.items
        )

    except Exception:

        raw_items = []

    if isinstance(
        raw_items,
        list
    ):

        for item in raw_items:

            if not isinstance(
                item,
                dict
            ):

                continue

            product_name = str(
                item.get(
                    "name",
                    ""
                )
            ).strip()

            try:

                quantity = int(
                    item.get(
                        "quantity",
                        1
                    )
                )

            except (
                TypeError,
                ValueError
            ):

                quantity = 1

            if not product_name or quantity <= 0:

                continue

            product = Product.query.filter_by(
                name=product_name
            ).first()

            if product:

                product.stock += quantity

    order.status = "Cancelled"

    db.session.commit()

    send_sms(
        "+91" + mobile,
        (
            f"PICKELS STORE: Order #{order.id} "
            "has been cancelled successfully."
        )
    )

    return redirect(
        "/order-history"
    )


# --------------------------------------------------
# ORDER HISTORY
# --------------------------------------------------

@app.route("/order-history")
def order_history():

    mobile = session.get(
        "user_mobile"
    )

    if not mobile:

        return redirect("/login")

    orders = (
        Order.query
        .filter_by(mobile=mobile)
        .order_by(Order.id.desc())
        .all()
    )

    for order in orders:

        order.created_at_ist = (
            order.created_at
            + timedelta(
                hours=5,
                minutes=30
            )
            if order.created_at
            else None
        )

        try:

            raw_items = json.loads(
                order.items
            )

        except Exception:

            raw_items = []

        display_items = []

        if isinstance(
            raw_items,
            list
        ):

            for item in raw_items:

                if isinstance(
                    item,
                    dict
                ):

                    item_name = item.get(
                        "name",
                        "Unknown Product"
                    )

                    try:

                        item_price = float(
                            item.get(
                                "price",
                                0
                            )
                        )

                    except (
                        TypeError,
                        ValueError
                    ):

                        item_price = 0

                    try:

                        item_quantity = int(
                            item.get(
                                "quantity",
                                1
                            )
                        )

                    except (
                        TypeError,
                        ValueError
                    ):

                        item_quantity = 1

                    # --------------------------------------
                    # FIX:
                    # Keep the product image from order.items
                    # --------------------------------------

                    display_items.append(
                        {
                            "name": item_name,
                            "price": item_price,
                            "quantity": item_quantity,
                            "image": item.get(
                                "image",
                                ""
                            ),
                        }
                    )

                elif isinstance(
                    item,
                    str
                ):

                    display_items.append(
                        {
                            "name": item,
                            "price": 0,
                            "quantity": 1,
                            "image": "",
                        }
                    )

        order.display_items = display_items

    return render_template(
        "order_history.html",
        orders=orders
    )


# --------------------------------------------------
# TRACK ORDER
# --------------------------------------------------

@app.route(
    "/track-order",
    methods=["GET", "POST"]
)
def track_order():

    order = None
    error = None

    if request.method == "POST":

        order_id = request.form.get(
            "order_id",
            ""
        ).strip()

        mobile = request.form.get(
            "mobile",
            ""
        ).strip().replace(
            " ",
            ""
        )

        if mobile.startswith("+91"):

            mobile = mobile[3:]

        if mobile.startswith("91") and len(mobile) == 12:

            mobile = mobile[2:]

        try:

            order_id = int(
                order_id
            )

        except ValueError:

            return render_template(
                "track_order.html",
                order=None,
                error="Please enter a valid Order ID.",
            )

        order = Order.query.filter_by(
            id=order_id,
            mobile=mobile
        ).first()

        if not order:

            return render_template(
                "track_order.html",
                order=None,
                error=(
                    "Order not found. "
                    "Please check your Order ID "
                    "and mobile number."
                ),
            )

        order.created_at_ist = (
            order.created_at
            + timedelta(
                hours=5,
                minutes=30
            )
            if order.created_at
            else None
        )

    return render_template(
        "track_order.html",
        order=order,
        error=error
    )


# --------------------------------------------------
# ADMIN LOGIN
# --------------------------------------------------

@app.route(
    "/admin-login",
    methods=["GET", "POST"]
)
def admin_login():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        ).strip()

        expected_username = os.getenv(
            "ADMIN_USERNAME"
        )

        expected_password = os.getenv(
            "ADMIN_PASSWORD"
        )

        if (
            expected_username
            and expected_password
            and username == expected_username
            and password == expected_password
        ):

            session["admin_logged_in"] = True

            return redirect(
                "/admin"
            )

        return render_template(
            "admin_login.html",
            error="Invalid username or password.",
        )

    return render_template(
        "admin_login.html"
    )


# --------------------------------------------------
# ADMIN DASHBOARD
# --------------------------------------------------

@app.route("/admin")
def admin():

    if not session.get(
        "admin_logged_in"
    ):

        return redirect(
            "/admin-login"
        )

    # Optional date-range filter for the admin sales report.
    start_date_text = request.args.get("start_date", "").strip()
    end_date_text = request.args.get("end_date", "").strip()
    date_filter_error = None
    start_date = None
    end_date = None

    try:
        if start_date_text:
            start_date = date.fromisoformat(start_date_text)
        if end_date_text:
            end_date = date.fromisoformat(end_date_text)
        if start_date and end_date and start_date > end_date:
            date_filter_error = "Start date must be on or before end date."
            start_date = end_date = None
    except ValueError:
        date_filter_error = "Please select valid dates."
        start_date = end_date = None

    query = Order.query
    if start_date:
        query = query.filter(
            Order.created_at >= datetime.combine(start_date, datetime.min.time())
        )
    if end_date:
        query = query.filter(
            Order.created_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time())
        )

    orders = query.order_by(Order.id.desc()).all()

    for order in orders:

        try:

            raw_items = json.loads(
                order.items
            )

            if isinstance(
                raw_items,
                str
            ):

                raw_items = json.loads(
                    raw_items
                )

            if not isinstance(
                raw_items,
                list
            ):

                raw_items = []

            order.display_items = []

            for raw_item in raw_items:

                item = (
                    dict(raw_item)
                    if isinstance(
                        raw_item,
                        dict
                    )
                    else {
                        "name": str(raw_item)
                    }
                )

                item_name = str(
                    item.get(
                        "name",
                        ""
                    )
                ).strip().lower()

                product = Product.query.filter(
                    db.func.lower(Product.name)
                    == item_name
                ).first()

                if product:

                    if not item.get(
                        "image"
                    ):

                        item["image"] = (
                            product.image
                        )

                    if not item.get(
                        "price"
                    ):

                        item["price"] = (
                            product.price
                        )

                    if not item.get(
                        "quantity"
                    ):

                        item["quantity"] = 1

                order.display_items.append(
                    item
                )

        except Exception:

            order.display_items = []

    total_sales = sum(
        order.total
        for order in orders
        if order.status != "Cancelled"
    )

    paid_online_orders = [
        order
        for order in orders
        if (order.payment_method or "").lower() == "online"
        and (order.payment_status or "").lower() == "paid"
    ]
    online_payment_total = sum(
        order.total
        for order in paid_online_orders
    )

    return render_template(
        "admin.html",
        orders=orders,
        total_sales=total_sales,
        online_payment_total=online_payment_total,
        paid_online_order_count=len(paid_online_orders),
        start_date=start_date_text,
        end_date=end_date_text,
        date_filter_error=date_filter_error,
    )


# --------------------------------------------------
# UPDATE ORDER
# --------------------------------------------------

@app.route(
    "/update-order/<int:order_id>",
    methods=["POST"]
)
def update_order(order_id):

    if not session.get(
        "admin_logged_in"
    ):

        return redirect(
            "/admin-login"
        )

    order = Order.query.get_or_404(
        order_id
    )

    status = request.form.get(
        "status",
        "Pending"
    )

    allowed_statuses = [
        "Pending",
        "Confirmed",
        "Shipped",
        "Delivered",
        "Cancelled"
    ]

    if status not in allowed_statuses:

        status = "Pending"

    order.status = status

    db.session.commit()

    message = (
        f"PICKELS STORE: Order #{order.id} "
        f"status updated to {order.status}."
    )

    send_sms(
        "+91" + order.mobile,
        message
    )

    return redirect(
        "/admin"
    )


# --------------------------------------------------
# ADMIN PRODUCTS
# --------------------------------------------------

@app.route("/admin/products")
def admin_products():

    if not session.get(
        "admin_logged_in"
    ):

        return redirect(
            "/admin-login"
        )

    products = (
        Product.query
        .order_by(Product.id.desc())
        .all()
    )

    return render_template(
        "admin_products.html",
        products=products
    )


# --------------------------------------------------
# ADD PRODUCT WITH IMAGE UPLOAD
# --------------------------------------------------

@app.route(
    "/admin/products/add",
    methods=["POST"]
)
def add_product():

    if not session.get(
        "admin_logged_in"
    ):

        return redirect(
            "/admin-login"
        )

    name = request.form.get(
        "name",
        ""
    ).strip()

    price = request.form.get(
        "price",
        ""
    ).strip()

    unit = request.form.get(
        "unit",
        ""
    ).strip()

    description = request.form.get(
        "description",
        ""
    ).strip()

    stock = request.form.get(
        "stock",
        "0"
    ).strip()

    # ------------------------------------------
    # NEW IMAGE UPLOAD
    # ------------------------------------------

    image_file = request.files.get(
        "image_file"
    )

    image = None

    if image_file and image_file.filename:

        image = save_uploaded_image(
            image_file
        )

        if not image:

            return redirect(
                "/admin/products"
            )

    # ------------------------------------------
    # BACKWARD COMPATIBILITY
    # ------------------------------------------

    if not image:

        image = request.form.get(
            "image",
            ""
        ).strip()

        image = image.replace(
            ",png",
            ".png"
        )

        image = image.replace(
            ",jpg",
            ".jpg"
        )

        image = image.replace(
            ",jpeg",
            ".jpeg"
        )

    # ------------------------------------------
    # REQUIRED FIELDS
    # ------------------------------------------

    if not name or not price or not unit or not image:

        return redirect(
            "/admin/products"
        )

    # ------------------------------------------
    # PRICE + STOCK
    # ------------------------------------------

    try:

        price = float(
            price
        )

        stock = int(
            stock
        )

    except ValueError:

        return redirect(
            "/admin/products"
        )

    if stock < 0:

        stock = 0

    # ------------------------------------------
    # CREATE PRODUCT
    # ------------------------------------------

    product = Product(
        name=name,
        price=price,
        unit=unit,
        image=image,
        description=description,
        active=True,
        stock=stock,
    )

    db.session.add(
        product
    )

    db.session.commit()

    return redirect(
        "/admin/products"
    )


# --------------------------------------------------
# EDIT PRODUCT
# --------------------------------------------------

@app.route(
    "/admin/products/edit/<int:product_id>",
    methods=["GET", "POST"]
)
def edit_product(product_id):

    if not session.get(
        "admin_logged_in"
    ):

        return redirect(
            "/admin-login"
        )

    product = Product.query.get_or_404(
        product_id
    )

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        price = request.form.get(
            "price",
            ""
        ).strip()

        unit = request.form.get(
            "unit",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        stock = request.form.get(
            "stock",
            "0"
        ).strip()

        active = request.form.get(
            "active"
        )

        if not name or not price or not unit:

            return render_template(
                "edit_product.html",
                product=product,
                error="Please fill all required fields.",
            )

        # --------------------------------------
        # OPTIONAL NEW IMAGE
        # --------------------------------------

        image_file = request.files.get(
            "image_file"
        )

        if image_file and image_file.filename:

            new_image = save_uploaded_image(
                image_file
            )

            if not new_image:

                return render_template(
                    "edit_product.html",
                    product=product,
                    error=(
                        "Invalid image. "
                        "Use PNG, JPG, JPEG or WEBP."
                    ),
                )

            product.image = new_image

        else:

            image = request.form.get(
                "image",
                ""
            ).strip()

            if image:

                image = image.replace(
                    ",png",
                    ".png"
                )

                image = image.replace(
                    ",jpg",
                    ".jpg"
                )

                image = image.replace(
                    ",jpeg",
                    ".jpeg"
                )

                product.image = image

        try:

            price = float(
                price
            )

            stock = int(
                stock
            )

        except ValueError:

            return render_template(
                "edit_product.html",
                product=product,
                error="Please enter valid price and stock.",
            )

        if stock < 0:

            stock = 0

        product.name = name
        product.price = price
        product.unit = unit
        product.description = description
        product.stock = stock
        product.active = (
            active == "on"
        )

        db.session.commit()

        return redirect(
            "/admin/products"
        )

    return render_template(
        "edit_product.html",
        product=product
    )


# --------------------------------------------------
# DELETE PRODUCT
# --------------------------------------------------

@app.route(
    "/admin/products/delete/<int:product_id>",
    methods=["POST"]
)
@app.route(
    "/delete-product/<int:product_id>",
    methods=["POST"]
)
def delete_product(product_id):

    if not session.get(
        "admin_logged_in"
    ):

        return redirect(
            "/admin-login"
        )

    product = Product.query.get_or_404(
        product_id
    )

    db.session.delete(
        product
    )

    db.session.commit()

    return redirect(
        "/admin/products"
    )


# --------------------------------------------------
# ADMIN CUSTOMERS
# --------------------------------------------------

@app.route("/admin/customers")
def admin_customers():

    if not session.get(
        "admin_logged_in"
    ):

        return redirect(
            "/admin-login"
        )

    customers = (
        Customer.query
        .order_by(Customer.id.desc())
        .all()
    )

    customer_data = []

    for customer in customers:

        order_count = Order.query.filter_by(
            mobile=customer.mobile
        ).count()

        customer_data.append(
            {
                "id": customer.id,
                "name": customer.name,
                "mobile": customer.mobile,
                "address": customer.address,
                "created_at": customer.created_at,
                "order_count": order_count,
            }
        )

    return render_template(
        "admin_customers.html",
        customers=customer_data
    )


# --------------------------------------------------
# ADMIN CUSTOMER DETAILS
# --------------------------------------------------

@app.route(
    "/admin/customer/<int:customer_id>"
)
def admin_customer_details(customer_id):

    if not session.get(
        "admin_logged_in"
    ):

        return redirect(
            "/admin-login"
        )

    customer = Customer.query.get_or_404(
        customer_id
    )

    orders = (
        Order.query
        .filter_by(mobile=customer.mobile)
        .order_by(Order.id.desc())
        .all()
    )

    total_spent = sum(
        order.total
        for order in orders
        if order.status != "Cancelled"
    )

    return render_template(
        "admin_customer_details.html",
        customer=customer,
        orders=orders,
        total_spent=total_spent,
    )


# --------------------------------------------------
# ADMIN LOGOUT
# --------------------------------------------------

@app.route("/admin-logout")
def admin_logout():

    session.pop(
        "admin_logged_in",
        None
    )

    return redirect(
        "/admin-login"
    )


# --------------------------------------------------
# START APPLICATION
# --------------------------------------------------

if __name__ == "__main__":

    app.run(
        host=os.getenv(
            "HOST",
            "127.0.0.1"
        ),
        port=int(
            os.getenv(
                "PORT",
                "5000"
            )
        ),
        debug=os.getenv(
            "FLASK_DEBUG",
            "0"
        ) == "1",
    )