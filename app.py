import os
import json
import random
import hashlib
import hmac
import secrets
from datetime import date, datetime, timedelta
from uuid import uuid4

import requests
import razorpay
from dotenv import load_dotenv
from flask import Flask, flash, g, jsonify, redirect, render_template, request, session
from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import inspect, text
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("SECRET_KEY must be set before starting the application.")

APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
IS_PRODUCTION = APP_ENV == "production"
try:
    trusted_proxy_hops = int(os.getenv("TRUSTED_PROXY_HOPS", "0"))
except ValueError as exc:
    raise RuntimeError("TRUSTED_PROXY_HOPS must be a non-negative integer.") from exc
if trusted_proxy_hops < 0:
    raise RuntimeError("TRUSTED_PROXY_HOPS must be a non-negative integer.")

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
app.config["SESSION_COOKIE_SECURE"] = (
    IS_PRODUCTION or os.getenv("SESSION_COOKIE_SECURE", "0") == "1"
)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

if IS_PRODUCTION:
    required_production_settings = (
        "ADMIN_USERNAME",
        "ADMIN_PASSWORD",
        "DATABASE_URL",
        "RAZORPAY_KEY_ID",
        "RAZORPAY_KEY_SECRET",
        "RATELIMIT_STORAGE_URI",
        "TEXTBEE_API_KEY",
        "TEXTBEE_DEVICE_ID",
        "TRUSTED_PROXY_HOPS",
    )
    missing_production_settings = [
        key for key in required_production_settings if not os.getenv(key)
    ]
    if missing_production_settings:
        raise RuntimeError(
            "Missing required production settings: "
            + ", ".join(missing_production_settings)
        )
    if len(app.secret_key) < 32:
        raise RuntimeError("Production SECRET_KEY must be at least 32 characters.")
    if os.getenv("ADMIN_USERNAME", "").strip().lower() == "admin":
        raise RuntimeError("Production ADMIN_USERNAME must not be the default value.")
    if os.getenv("ADMIN_PASSWORD", "").strip() in {
        "use-a-strong-unique-password",
        "password",
        "admin",
    }:
        raise RuntimeError("Production ADMIN_PASSWORD must be changed from its default.")
    if database_url.startswith("sqlite:"):
        raise RuntimeError("Production DATABASE_URL must use PostgreSQL.")
    if os.getenv("RATELIMIT_STORAGE_URI", "").startswith("memory://"):
        raise RuntimeError("Production rate limits require shared Redis storage.")
    if trusted_proxy_hops < 1:
        raise RuntimeError("Production TRUSTED_PROXY_HOPS must match the trusted HTTPS proxy chain.")

@app.before_request
def assign_csp_nonce():
    g.csp_nonce = secrets.token_urlsafe(16)


csrf = CSRFProtect(app)
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    storage_uri=os.getenv("RATELIMIT_STORAGE_URI", "memory://"),
    headers_enabled=True,
)


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=()",
    )
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin-allow-popups")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "base-uri 'self'; "
        "object-src 'none'; "
        "frame-ancestors 'none'; "
        "form-action 'self' https://api.razorpay.com https://checkout.razorpay.com; "
        f"script-src 'self' 'nonce-{g.csp_nonce}' https://checkout.razorpay.com; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self' data:; "
        "connect-src 'self' https://api.razorpay.com https://checkout.razorpay.com; "
        "frame-src https://api.razorpay.com https://checkout.razorpay.com",
    )
    if app.config.get("APP_ENV") == "production":
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000",
        )
    return response


app.config["APP_ENV"] = APP_ENV
if trusted_proxy_hops:
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=trusted_proxy_hops,
        x_proto=trusted_proxy_hops,
    )

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


def otp_digest(otp):
    return hmac.new(
        app.secret_key.encode("utf-8"),
        otp.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def clear_otp_session(purpose):
    keys = {
        "register": (
            "register_challenge_id",
            "register_otp",
            "register_otp_mobile",
            "register_name",
            "register_address",
            "register_password",
            "register_otp_expires",
            "register_otp_attempts",
        ),
        "reset": (
            "reset_challenge_id",
            "reset_otp",
            "reset_otp_mobile",
            "reset_otp_expires",
            "reset_otp_attempts",
            "reset_otp_verified",
        ),
    }

    for key in keys[purpose]:
        session.pop(key, None)


@app.before_request
def discard_legacy_otp_session_data():
    for key in (
        "register_otp",
        "register_otp_mobile",
        "register_name",
        "register_address",
        "register_password",
        "register_otp_expires",
        "register_otp_attempts",
        "reset_otp",
        "reset_otp_mobile",
        "reset_otp_expires",
        "reset_otp_attempts",
        "reset_otp_verified",
        "user_name",
        "user_address",
    ):
        session.pop(key, None)


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


class OTPChallenge(db.Model):
    id = db.Column(db.String(64), primary_key=True)
    purpose = db.Column(db.String(20), nullable=False)
    mobile = db.Column(db.String(20), nullable=False)
    otp_digest = db.Column(db.String(64), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    verified = db.Column(db.Boolean, nullable=False, default=False)
    registration_name = db.Column(db.String(100), nullable=True)
    registration_address = db.Column(db.Text, nullable=True)
    registration_password = db.Column(db.String(255), nullable=True)


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

    payment_recorded_at = db.Column(
        db.DateTime,
        nullable=True
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

    if "payment_recorded_at" not in order_columns:

        with db.engine.begin() as connection:

            connection.execute(
                text(
                    'ALTER TABLE "order" '
                    "ADD COLUMN payment_recorded_at TIMESTAMP"
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
        app.logger.error("SMS provider is not configured.")
        return False

    if not phone:
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

        if not 200 <= response.status_code < 300:
            app.logger.warning(
                "SMS provider returned HTTP %s.",
                response.status_code,
            )

        return 200 <= response.status_code < 300

    except requests.RequestException as exc:
        app.logger.error("SMS delivery failed (%s).", type(exc).__name__)
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
    customer = None
    if session.get("user_mobile"):
        customer = Customer.query.filter_by(
            mobile=session["user_mobile"]
        ).first()

    return render_template(
        "index.html",
        products=products,
        customer=customer,
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
@limiter.limit("5 per hour")
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
@limiter.limit("5 per hour", methods=["POST"])
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

        old_challenge_id = session.get("register_challenge_id")
        clear_otp_session("register")
        old_challenge = (
            db.session.get(OTPChallenge, old_challenge_id)
            if old_challenge_id
            else None
        )
        if old_challenge:
            db.session.delete(old_challenge)

        otp = str(secrets.randbelow(900000) + 100000)
        challenge_id = secrets.token_urlsafe(32)
        challenge = OTPChallenge(
            id=challenge_id,
            purpose="register",
            mobile=mobile,
            otp_digest=otp_digest(otp),
            expires_at=datetime.now() + timedelta(minutes=5),
            registration_name=name,
            registration_address=address,
            registration_password=generate_password_hash(password),
        )
        db.session.add(challenge)
        db.session.commit()
        session["register_challenge_id"] = challenge_id

        message = (
            f"Your PICKELS STORE registration OTP is {otp}. "
            "Do not share this OTP with anyone."
        )

        if not send_sms("+91" + mobile, message):
            db.session.delete(challenge)
            db.session.commit()
            clear_otp_session("register")

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
@limiter.limit("10 per 10 minutes", methods=["POST"])
def verify_registration_otp():

    challenge_id = session.get("register_challenge_id")
    challenge = (
        db.session.get(OTPChallenge, challenge_id)
        if challenge_id
        else None
    )
    if not challenge or challenge.purpose != "register":
        clear_otp_session("register")
        return redirect("/register")

    if request.method == "POST":

        if datetime.now() >= challenge.expires_at:
            db.session.delete(challenge)
            db.session.commit()
            clear_otp_session("register")
            return render_template(
                "verify_registration_otp.html",
                error="OTP expired. Please register again."
            )

        entered_otp = request.form.get(
            "otp",
            ""
        ).strip()

        if challenge.attempts >= 5:
            db.session.delete(challenge)
            db.session.commit()
            clear_otp_session("register")
            return render_template(
                "verify_registration_otp.html",
                error="Too many incorrect attempts. Please register again."
            )

        if not hmac.compare_digest(
            otp_digest(entered_otp),
            challenge.otp_digest,
        ):
            challenge.attempts += 1
            db.session.commit()

            return render_template(
                "verify_registration_otp.html",
                error="Invalid OTP. Please try again."
            )

        mobile = challenge.mobile
        name = challenge.registration_name or ""
        address = challenge.registration_address or ""
        password_hash = challenge.registration_password
        if not password_hash:
            db.session.delete(challenge)
            db.session.commit()
            clear_otp_session("register")
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

        db.session.delete(challenge)
        db.session.commit()
        clear_otp_session("register")
        session.clear()
        session["user_mobile"] = mobile

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
@limiter.limit("10 per minute; 50 per hour", methods=["POST"])
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
                error="Invalid mobile number or password."
            )

        # ------------------------------------------
        # PASSWORD CHECK
        # ------------------------------------------

        if not customer.password:

            return render_template(
                "login.html",
                error="Invalid mobile number or password."
            )

        if not check_password_hash(
            customer.password,
            password
        ):

            return render_template(
                "login.html",
                error="Invalid mobile number or password."
            )

        session.clear()
        session["user_mobile"] = customer.mobile

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
@limiter.limit("5 per hour", methods=["POST"])
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

        old_challenge_id = session.get("reset_challenge_id")
        clear_otp_session("reset")
        old_challenge = (
            db.session.get(OTPChallenge, old_challenge_id)
            if old_challenge_id
            else None
        )
        if old_challenge:
            db.session.delete(old_challenge)

        otp = str(secrets.randbelow(900000) + 100000)
        challenge_id = secrets.token_urlsafe(32)
        challenge = OTPChallenge(
            id=challenge_id,
            purpose="reset",
            mobile=mobile,
            otp_digest=otp_digest(otp),
            expires_at=datetime.now() + timedelta(minutes=5),
        )
        db.session.add(challenge)
        db.session.commit()
        session["reset_challenge_id"] = challenge_id

        message = (
            f"Your PICKELS STORE password reset OTP is {otp}. "
            "Do not share this OTP with anyone."
        )

        if not send_sms("+91" + mobile, message):
            db.session.delete(challenge)
            db.session.commit()
            clear_otp_session("reset")

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
@limiter.limit("10 per 10 minutes", methods=["POST"])
def verify_reset_otp():

    challenge_id = session.get("reset_challenge_id")
    challenge = (
        db.session.get(OTPChallenge, challenge_id)
        if challenge_id
        else None
    )
    if not challenge or challenge.purpose != "reset":
        clear_otp_session("reset")
        return redirect("/forgot-password")

    if datetime.now() >= challenge.expires_at:
        db.session.delete(challenge)
        db.session.commit()
        clear_otp_session("reset")
        return render_template(
            "verify_reset_otp.html",
            error="OTP expired. Please request a new one."
        )

    if challenge.verified:
        return redirect("/reset-password")

    if request.method == "POST":

        if challenge.attempts >= 5:
            db.session.delete(challenge)
            db.session.commit()
            clear_otp_session("reset")
            return render_template(
                "verify_reset_otp.html",
                error="Too many incorrect attempts. Please request a new OTP."
            )

        entered_otp = request.form.get(
            "otp",
            ""
        ).strip()

        if not hmac.compare_digest(
            otp_digest(entered_otp),
            challenge.otp_digest,
        ):
            challenge.attempts += 1
            db.session.commit()

            return render_template(
                "verify_reset_otp.html",
                error="Invalid OTP. Please try again."
            )

        challenge.verified = True
        db.session.commit()

        return redirect("/reset-password")

    return render_template("verify_reset_otp.html")


@app.route(
    "/reset-password",
    methods=["GET", "POST"]
)
@limiter.limit("5 per hour", methods=["POST"])
def reset_password():

    challenge_id = session.get("reset_challenge_id")
    challenge = (
        db.session.get(OTPChallenge, challenge_id)
        if challenge_id
        else None
    )
    if not challenge or challenge.purpose != "reset" or not challenge.verified:
        clear_otp_session("reset")
        return redirect("/forgot-password")

    if datetime.now() >= challenge.expires_at:
        db.session.delete(challenge)
        db.session.commit()
        clear_otp_session("reset")
        return redirect("/forgot-password")

    customer = Customer.query.filter_by(
        mobile=challenge.mobile
    ).first()

    if not customer:
        db.session.delete(challenge)
        db.session.commit()
        clear_otp_session("reset")
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
        db.session.delete(challenge)
        db.session.commit()
        clear_otp_session("reset")

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

    if not customer:
        session.clear()
        return redirect("/login")

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
        customer=customer,
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
@limiter.limit("30 per hour")
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

    if not address or len(address) > 1000:

        return redirect("/account")

    customer = Customer.query.filter_by(
        mobile=mobile
    ).first()

    if not customer:
        session.clear()
        return redirect("/login")

    customer.address = address

    db.session.commit()

    return redirect("/account")


# --------------------------------------------------
# CUSTOMER LOGOUT
# --------------------------------------------------

@app.route("/logout")
def logout():
    session.clear()

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

    if not customer:
        session.clear()
        return redirect("/login")

    return render_template(
        "checkout.html",
        customer=customer,
    )


# --------------------------------------------------
# PLACE ORDER
# --------------------------------------------------

@app.route(
    "/place-order",
    methods=["POST"]
)
@limiter.limit("10 per minute; 100 per hour")
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

        items = data.get("items", [])
        if not isinstance(items, list) or not items or len(items) > 50:
            return jsonify(
                {
                    "success": False,
                    "message": "Invalid cart items.",
                }
            ), 400

        payment_method = str(data.get("payment_method", "COD")).strip().upper()
        if payment_method != "COD":
            return jsonify(
                {
                    "success": False,
                    "message": "Use the secure online payment flow for online orders.",
                }
            ), 400

        mobile = session.get(
            "user_mobile",
            ""
        )
        customer = Customer.query.filter_by(mobile=mobile).first()
        if not customer:
            session.clear()
            return jsonify(
                {
                    "success": False,
                    "message": "Please login again.",
                }
            ), 401

        name = customer.name

        address = data.get(
            "address",
            customer.address or "",
        )

        if not address:
            address = customer.address or ""

        if not isinstance(address, str):
            return jsonify(
                {
                    "success": False,
                    "message": "Please enter a valid delivery address.",
                }
            ), 400
        address = address.strip()

        if not address or len(address) > 1000:

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
        seen_product_names = set()

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
            normalized_name = product_name.casefold()
            if not product_name or len(product_name) > 100 or normalized_name in seen_product_names:
                return jsonify(
                    {
                        "success": False,
                        "message": "Invalid or duplicate cart item.",
                    }
                ), 400
            seen_product_names.add(normalized_name)

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
                return jsonify(
                    {
                        "success": False,
                        "message": "Invalid cart quantity.",
                    }
                ), 400

            if quantity <= 0 or quantity > 100:
                return jsonify(
                    {
                        "success": False,
                        "message": "Invalid cart quantity.",
                    }
                ), 400

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

        customer.address = address

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
            payment_status="Pending",
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

        app.logger.error("Place order failed (%s).", type(e).__name__)

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
@limiter.limit("10 per minute; 100 per hour")
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
        ) or not items or len(items) > 50:

            return jsonify(
                {
                    "success": False,
                    "message": "Your cart is empty."
                }
            ), 400

        total = 0
        seen_product_names = set()

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
            normalized_name = product_name.casefold()
            if not product_name or len(product_name) > 100 or normalized_name in seen_product_names:
                return jsonify(
                    {
                        "success": False,
                        "message": "Invalid or duplicate cart item.",
                    }
                ), 400
            seen_product_names.add(normalized_name)

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

            if quantity <= 0 or quantity > 100:

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

        app.logger.error("Razorpay order creation failed (%s).", type(e).__name__)

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
@limiter.limit("10 per minute; 100 per hour")
def verify_razorpay_payment():

    if not session.get("user_mobile"):
        return jsonify({"success": False, "message": "Please login first."}), 401

    try:
        data = request.get_json(silent=True) or {}
        razorpay_order_id = str(data.get("razorpay_order_id", "")).strip()
        razorpay_payment_id = str(data.get("razorpay_payment_id", "")).strip()
        razorpay_signature = str(data.get("razorpay_signature", "")).strip()
        items = data.get("items", [])
        customer = Customer.query.filter_by(
            mobile=session.get("user_mobile")
        ).first()
        if not customer:
            session.clear()
            return jsonify({"success": False, "message": "Please login again."}), 401

        address = data.get("address") or customer.address or ""
        if not isinstance(address, str):
            return jsonify({"success": False, "message": "Please enter a valid delivery address."}), 400
        address = address.strip()

        if not razorpay_order_id or not razorpay_payment_id or not razorpay_signature:
            return jsonify({"success": False, "message": "Payment verification data is missing."}), 400
        if not isinstance(items, list) or not items or len(items) > 50:
            return jsonify({"success": False, "message": "Your cart is empty."}), 400
        if not address or len(address) > 1000:
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
        seen_product_names = set()

        for item in items:
            if not isinstance(item, dict):
                return jsonify({"success": False, "message": "Invalid cart item."}), 400
            product_name = str(item.get("name", "")).strip()
            normalized_name = product_name.casefold()
            if not product_name or len(product_name) > 100 or normalized_name in seen_product_names:
                return jsonify({"success": False, "message": "Invalid or duplicate cart item."}), 400
            seen_product_names.add(normalized_name)
            try:
                quantity = int(item.get("quantity", 0))
            except (TypeError, ValueError):
                return jsonify({"success": False, "message": "Invalid quantity."}), 400
            if quantity <= 0 or quantity > 100:
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
        name = customer.name
        customer.address = address

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
            payment_recorded_at=datetime.now(),
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
        app.logger.error("Razorpay verification failed (%s).", type(e).__name__)
        return jsonify({"success": False, "message": "Payment verification failed."}), 400


# --------------------------------------------------
# CANCEL ORDER
# --------------------------------------------------

@app.route(
    "/cancel-order/<int:order_id>",
    methods=["POST"]
)
@limiter.limit("20 per hour")
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
@limiter.limit("30 per hour", methods=["POST"])
def track_order():

    mobile = session.get("user_mobile")
    if not mobile:
        return redirect("/login")

    order = None
    error = None

    if request.method == "POST":

        order_id = request.form.get(
            "order_id",
            ""
        ).strip()

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
                error="Order not found for your account.",
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
@limiter.limit("10 per 15 minutes", methods=["POST"])
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

        username_matches = bool(expected_username) and hmac.compare_digest(
            username.encode("utf-8"),
            expected_username.encode("utf-8"),
        )
        password_matches = bool(expected_password) and hmac.compare_digest(
            password.encode("utf-8"),
            expected_password.encode("utf-8"),
        )

        if username_matches and password_matches:

            session.clear()
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
@limiter.limit("60 per hour")
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


@app.route(
    "/record-cod-payment/<int:order_id>",
    methods=["POST"]
)
@limiter.limit("30 per hour")
def record_cod_payment(order_id):

    if not session.get("admin_logged_in"):
        return redirect("/admin-login")

    order = Order.query.get_or_404(order_id)

    if (order.payment_method or "").strip().lower() != "cod":
        flash("Only COD orders can be recorded as collected here.", "error")
        return redirect("/admin")

    if (order.status or "").strip().lower() == "cancelled":
        flash("Payment cannot be recorded for a cancelled order.", "error")
        return redirect("/admin")

    if (order.payment_status or "").strip().lower() != "pending":
        flash("Only pending COD payments can be recorded as received.", "error")
        return redirect("/admin")

    order.payment_status = "Paid"
    order.payment_recorded_at = datetime.now()
    db.session.commit()

    flash(f"COD payment for Order #{order.id} recorded as received.", "success")
    return redirect("/admin")


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
@limiter.limit("30 per hour")
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
@limiter.limit("30 per hour", methods=["POST"])
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
@limiter.limit("30 per hour")
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
        debug=(
            not IS_PRODUCTION
            and os.getenv("FLASK_DEBUG", "0") == "1"
        ),
    )