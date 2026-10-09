import os
import re
import unittest
from uuid import uuid4

os.environ["APP_ENV"] = "development"
os.environ["SECRET_KEY"] = "test-only-secret-key-that-is-long-enough"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["RATELIMIT_STORAGE_URI"] = "memory://"

import app as store


class SecurityControlsTests(unittest.TestCase):
    def setUp(self):
        store.app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=True,
            APP_ENV="development",
        )
        with store.app.app_context():
            customer = store.Customer.query.filter_by(
                mobile="1234567890"
            ).first()
            if not customer:
                store.db.session.add(
                    store.Customer(
                        name="Test Customer",
                        mobile="1234567890",
                        address="Test Address",
                    )
                )
                store.db.session.commit()
        self.client = store.app.test_client()
        self.remote_addr = f"198.51.100.{(uuid4().int % 200) + 1}"

    def _csrf_token(self, path="/login"):
        response = self.client.get(
            path,
            environ_overrides={"REMOTE_ADDR": self.remote_addr},
        )
        self.assertEqual(response.status_code, 200)
        match = re.search(
            rb'name="csrf_token" value="([^"]+)"',
            response.data,
        )
        self.assertIsNotNone(match)
        return match.group(1).decode("ascii")

    def test_security_headers_are_added(self):
        response = self.client.get("/login")

        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        policy = response.headers["Content-Security-Policy"]
        self.assertIn("frame-ancestors 'none'", policy)
        self.assertIn("script-src 'self' 'nonce-", policy)
        self.assertNotIn("'unsafe-inline'", policy.split("script-src", 1)[1].split(";", 1)[0])
        self.assertNotIn("Strict-Transport-Security", response.headers)

    def test_inline_scripts_use_response_csp_nonce(self):
        response = self.client.get("/")
        policy = response.headers["Content-Security-Policy"]
        nonce_match = re.search(r"script-src [^;]*'nonce-([^']+)'", policy)
        self.assertIsNotNone(nonce_match)
        inline_scripts = re.findall(rb"<script(?![^>]*\bsrc=)([^>]*)>", response.data)
        self.assertTrue(inline_scripts)
        self.assertTrue(
            all(
                re.search(
                    rb'nonce="' + nonce_match.group(1).encode("ascii") + rb'"',
                    attributes,
                )
                for attributes in inline_scripts
            )
        )

    def test_https_deployment_gets_hsts(self):
        store.app.config["APP_ENV"] = "production"
        try:
            response = self.client.get("/login")
        finally:
            store.app.config["APP_ENV"] = "development"

        self.assertEqual(
            response.headers["Strict-Transport-Security"],
            "max-age=31536000",
        )

    def test_browser_post_requires_csrf_token(self):
        response = self.client.post(
            "/login",
            data={"mobile": "1234567890", "password": "not-a-real-password"},
            environ_overrides={"REMOTE_ADDR": self.remote_addr},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"CSRF", response.data)

    def test_login_form_token_allows_normal_post(self):
        token = self._csrf_token()
        response = self.client.post(
            "/login",
            data={
                "csrf_token": token,
                "mobile": "1234567890",
                "password": "not-a-real-password",
            },
            environ_overrides={"REMOTE_ADDR": self.remote_addr},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Invalid mobile number or password.", response.data)

    def test_login_is_rate_limited(self):
        token = self._csrf_token()
        responses = [
            self.client.post(
                "/login",
                data={
                    "csrf_token": token,
                    "mobile": "1234567890",
                    "password": "not-a-real-password",
                },
                environ_overrides={"REMOTE_ADDR": self.remote_addr},
            )
            for _ in range(11)
        ]

        self.assertEqual(responses[-1].status_code, 429)

    def test_cancelled_order_does_not_show_active_tracking_timeline(self):
        with store.app.app_context():
            order = store.Order(
                name="Test Customer",
                mobile="1234567890",
                address="Test Address",
                items="[]",
                total=10,
                status="Cancelled",
                payment_method="COD",
            )
            store.db.session.add(order)
            store.db.session.commit()
            order_id = order.id

        with self.client.session_transaction() as browser_session:
            browser_session["user_mobile"] = "1234567890"

        token = self._csrf_token("/track-order")
        response = self.client.post(
            "/track-order",
            data={"csrf_token": token, "order_id": order_id},
            environ_overrides={"REMOTE_ADDR": self.remote_addr},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Order Cancelled", response.data)
        self.assertNotIn(b'class="timeline"', response.data)

    def test_active_order_keeps_tracking_timeline(self):
        with store.app.app_context():
            order = store.Order(
                name="Test Customer",
                mobile="1234567890",
                address="Test Address",
                items="[]",
                total=10,
                status="Pending",
                payment_method="COD",
            )
            store.db.session.add(order)
            store.db.session.commit()
            order_id = order.id

        with self.client.session_transaction() as browser_session:
            browser_session["user_mobile"] = "1234567890"

        token = self._csrf_token("/track-order")
        response = self.client.post(
            "/track-order",
            data={"csrf_token": token, "order_id": order_id},
            environ_overrides={"REMOTE_ADDR": self.remote_addr},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'class="timeline"', response.data)
        self.assertIn(b"Order Received", response.data)

    def test_cod_endpoint_rejects_online_payment_method(self):
        with self.client.session_transaction() as browser_session:
            browser_session["user_mobile"] = "1234567890"

        token = self._csrf_token("/checkout")
        response = self.client.post(
            "/place-order",
            json={
                "payment_method": "Online",
                "address": "Test Address",
                "items": [{"name": "Not a real product", "quantity": 1}],
            },
            headers={"X-CSRFToken": token},
            environ_overrides={"REMOTE_ADDR": self.remote_addr},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "Use the secure online payment flow",
            response.get_json()["message"],
        )


if __name__ == "__main__":
    unittest.main()
