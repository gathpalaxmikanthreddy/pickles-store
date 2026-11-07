import json
import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

os.environ["APP_ENV"] = "development"
os.environ["SECRET_KEY"] = "test-only-secret-key-that-is-long-enough"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["RATELIMIT_STORAGE_URI"] = "memory://"

import app as store


class SecurityControlsTests(unittest.TestCase):
    def setUp(self):
        self.sms_patcher = patch.object(store, "send_sms", return_value=False)
        self.sms_patcher.start()
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

    def tearDown(self):
        self.sms_patcher.stop()

    def _create_order(self, **overrides):
        values = {
            "name": "Test Customer",
            "mobile": "1234567890",
            "address": "Test Address",
            "items": "[]",
            "total": 10,
            "status": "Pending",
            "payment_method": "COD",
            "payment_status": "Pending",
        }
        values.update(overrides)
        with store.app.app_context():
            order = store.Order(**values)
            store.db.session.add(order)
            store.db.session.commit()
            return order.id

    def _create_product(self, stock=5):
        with store.app.app_context():
            product = store.Product(
                name=f"Test Pickle {uuid4().hex}",
                price=10,
                unit="250g",
                image="mango-pickle.png",
                stock=stock,
            )
            store.db.session.add(product)
            store.db.session.commit()
            return product.id

    def _set_session_role(self, role, value):
        with self.client.session_transaction() as browser_session:
            browser_session[role] = value

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
        self.assertEqual(response.headers["Cross-Origin-Embedder-Policy"], "credentialless")
        self.assertEqual(response.headers["Cross-Origin-Resource-Policy"], "same-origin")
        policy = response.headers["Content-Security-Policy"]
        self.assertIn("frame-ancestors 'none'", policy)
        self.assertIn("script-src 'self' 'nonce-", policy)
        self.assertNotIn("'unsafe-inline'", policy.split("script-src", 1)[1].split(";", 1)[0])
        style_policy = policy.split("style-src ", 1)[1].split(";", 1)[0]
        self.assertIn("'nonce-", style_policy)
        self.assertNotIn("'unsafe-inline'", style_policy)
        self.assertNotIn("data:", style_policy)
        self.assertNotIn("https:", style_policy)
        self.assertIn("style-src-attr 'none'", policy)
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
        inline_styles = re.findall(rb"<style(?![^>]*\bsrc=)([^>]*)>", response.data)
        style_nonce_match = re.search(r"style-src [^;]*'nonce-([^']+)'", policy)
        self.assertIsNotNone(style_nonce_match)
        self.assertTrue(inline_styles)
        self.assertTrue(
            all(
                re.search(
                    rb'nonce="' + style_nonce_match.group(1).encode("ascii") + rb'"',
                    attributes,
                )
                for attributes in inline_styles
            )
        )

    def test_external_checkout_script_has_sri(self):
        checkout_template = (
            Path(store.app.root_path) / "templates" / "checkout.html"
        ).read_text(encoding="utf-8")

        self.assertRegex(
            checkout_template,
            r'<script\s+src="https://checkout\.razorpay\.com/v1/checkout\.js"'
            r'\s+integrity="sha384-[A-Za-z0-9+/=]+"'
            r'\s+crossorigin="anonymous"',
        )

    def test_https_deployment_gets_hsts(self):
        store.app.config["APP_ENV"] = "production"
        try:
            response = self.client.get("/login")
        finally:
            store.app.config["APP_ENV"] = "development"

        self.assertEqual(
            response.headers["Strict-Transport-Security"],
            "max-age=63072000; includeSubDomains; preload",
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

    def test_legal_and_seo_pages_exist(self):
        legal_pages = [
            ("/privacy-policy", b"Privacy Policy"),
            ("/terms-and-conditions", b"Terms and Conditions"),
        ]

        for path, expected_text in legal_pages:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn(expected_text, response.data)

        robots_response = self.client.get("/robots.txt")
        self.assertEqual(robots_response.status_code, 200)
        self.assertIn(b"Sitemap:", robots_response.data)

        sitemap_response = self.client.get("/sitemap.xml")
        self.assertEqual(sitemap_response.status_code, 200)
        self.assertIn(b"<urlset", sitemap_response.data)

    def test_admin_session_clears_customer_session_state(self):
        with self.client.session_transaction() as browser_session:
            browser_session["user_mobile"] = "1234567890"
            browser_session["admin_logged_in"] = True

        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 200)

        with self.client.session_transaction() as browser_session:
            self.assertNotIn("user_mobile", browser_session)

    def test_admin_cancel_restores_stock_once_and_sets_online_refund_pending(self):
        product_id = self._create_product(stock=3)
        order_id = self._create_order(
            items=json.dumps(
                [
                    {
                        "product_id": product_id,
                        "name": "Test Pickle",
                        "price": 10,
                        "quantity": 2,
                        "unit": "250g",
                    }
                ]
            ),
            total=20,
            payment_method="Online",
            payment_status="Paid",
            razorpay_payment_id="pay_test_admin_cancel",
        )
        token = self._csrf_token()
        self._set_session_role("admin_logged_in", True)

        response = self.client.post(
            f"/update-order/{order_id}",
            data={"csrf_token": token, "status": "Cancelled"},
            environ_overrides={"REMOTE_ADDR": self.remote_addr},
        )
        self.assertEqual(response.status_code, 302)

        with store.app.app_context():
            order = store.db.session.get(store.Order, order_id)
            product = store.db.session.get(store.Product, product_id)
            self.assertEqual(order.status, "Cancelled")
            self.assertEqual(order.cancelled_by, "admin")
            self.assertEqual(order.refund_status, "Refund Pending")
            self.assertTrue(order.stock_restored)
            self.assertEqual(product.stock, 5)

        self.client.post(
            f"/update-order/{order_id}",
            data={"csrf_token": token, "status": "Cancelled"},
            environ_overrides={"REMOTE_ADDR": self.remote_addr},
        )
        with store.app.app_context():
            self.assertEqual(store.db.session.get(store.Product, product_id).stock, 5)

    def test_admin_cancel_cod_does_not_create_refund(self):
        product_id = self._create_product(stock=4)
        order_id = self._create_order(
            items=json.dumps(
                [{"product_id": product_id, "quantity": 1}]
            )
        )
        token = self._csrf_token()
        self._set_session_role("admin_logged_in", True)

        self.client.post(
            f"/update-order/{order_id}",
            data={"csrf_token": token, "status": "Cancelled"},
            environ_overrides={"REMOTE_ADDR": self.remote_addr},
        )

        with store.app.app_context():
            order = store.db.session.get(store.Order, order_id)
            self.assertEqual(order.refund_status, "Not Required")
            self.assertEqual(store.db.session.get(store.Product, product_id).stock, 5)

    def test_customer_cancel_restores_stock_and_admin_cannot_restore_it_again(self):
        product_id = self._create_product(stock=2)
        order_id = self._create_order(
            items=json.dumps(
                [{"product_id": product_id, "quantity": 3}]
            ),
            payment_method="Online",
            payment_status="Paid",
        )
        token = self._csrf_token()
        self._set_session_role("user_mobile", "1234567890")

        response = self.client.post(
            f"/cancel-order/{order_id}",
            data={"csrf_token": token},
            environ_overrides={"REMOTE_ADDR": self.remote_addr},
        )
        self.assertEqual(response.status_code, 302)

        with store.app.app_context():
            order = store.db.session.get(store.Order, order_id)
            self.assertEqual(order.cancelled_by, "customer")
            self.assertEqual(order.refund_status, "Refund Pending")
            self.assertTrue(order.stock_restored)
            self.assertEqual(store.db.session.get(store.Product, product_id).stock, 5)

        self.client.post(
            f"/cancel-order/{order_id}",
            data={"csrf_token": token},
            environ_overrides={"REMOTE_ADDR": self.remote_addr},
        )
        with store.app.app_context():
            self.assertEqual(store.db.session.get(store.Product, product_id).stock, 5)

        self._set_session_role("admin_logged_in", True)
        self.client.post(
            f"/update-order/{order_id}",
            data={"csrf_token": token, "status": "Cancelled"},
            environ_overrides={"REMOTE_ADDR": self.remote_addr},
        )
        with store.app.app_context():
            self.assertEqual(store.db.session.get(store.Product, product_id).stock, 5)

    def test_invalid_order_quantity_does_not_increase_stock(self):
        product_id = self._create_product(stock=4)
        order_id = self._create_order(
            items=json.dumps(
                [
                    {"product_id": product_id, "quantity": "invalid"},
                    {"product_id": product_id, "quantity": True},
                    {"product_id": product_id, "quantity": 0},
                    {"product_id": product_id, "quantity": -1},
                    {"product_id": product_id, "quantity": 101},
                    {"product_id": product_id, "quantity": 1.5},
                ]
            )
        )
        token = self._csrf_token()
        self._set_session_role("admin_logged_in", True)

        self.client.post(
            f"/update-order/{order_id}",
            data={"csrf_token": token, "status": "Cancelled"},
            environ_overrides={"REMOTE_ADDR": self.remote_addr},
        )

        with store.app.app_context():
            self.assertEqual(store.db.session.get(store.Product, product_id).stock, 4)

    def test_cod_checkout_persists_product_id_and_weight_for_cancellation(self):
        product_id = self._create_product(stock=4)
        with store.app.app_context():
            product = store.db.session.get(store.Product, product_id)
            product_name = product.name
            product_unit = product.unit
        self._set_session_role("user_mobile", "1234567890")
        token = self._csrf_token("/checkout")

        response = self.client.post(
            "/place-order",
            json={
                "payment_method": "COD",
                "address": "Test Address",
                "items": [{"name": product_name, "quantity": 2}],
            },
            headers={"X-CSRFToken": token},
            environ_overrides={"REMOTE_ADDR": self.remote_addr},
        )
        self.assertEqual(response.status_code, 200)
        order_id = response.get_json()["order_id"]

        with store.app.app_context():
            order = store.db.session.get(store.Order, order_id)
            item = json.loads(order.items)[0]
            self.assertEqual(item["product_id"], product_id)
            self.assertEqual(item["unit"], product_unit)
            self.assertEqual(store.db.session.get(store.Product, product_id).stock, 2)

    def test_refund_is_not_repeated_and_only_provider_confirmed_refund_is_completed(self):
        order_id = self._create_order(
            status="Cancelled",
            payment_method="Online",
            payment_status="Paid",
            refund_status="Refund Pending",
            razorpay_payment_id="pay_test_refund",
        )
        token = self._csrf_token()
        self._set_session_role("admin_logged_in", True)

        with (
            patch.object(store, "RAZORPAY_KEY_ID", "test_key"),
            patch.object(store, "RAZORPAY_KEY_SECRET", "test_secret"),
            patch.object(
                store.razorpay_client.payment,
                "refund",
                return_value={"id": "rfnd_test", "status": "pending"},
            ) as refund_call,
        ):
            response = self.client.post(
                f"/admin/refund/{order_id}",
                headers={"X-CSRFToken": token},
                environ_overrides={"REMOTE_ADDR": self.remote_addr},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["refund_status"], "Refund Processing")

            repeated = self.client.post(
                f"/admin/refund/{order_id}",
                headers={"X-CSRFToken": token},
                environ_overrides={"REMOTE_ADDR": self.remote_addr},
            )
            self.assertEqual(repeated.status_code, 409)
            self.assertEqual(refund_call.call_count, 1)

        with store.app.app_context():
            order = store.db.session.get(store.Order, order_id)
            self.assertEqual(order.refund_status, "Refund Processing")
            self.assertEqual(order.payment_status, "Paid")

    def test_invoice_is_private_and_contains_purchase_information(self):
        order_id = self._create_order(
            items='[{"name":"Invoice Pickle","price":10,"quantity":1,"unit":"500g"}]',
            total=17,
        )
        self._set_session_role("user_mobile", "1234567890")
        own_invoice = self.client.get(f"/invoice/{order_id}?placed=1")
        self.assertEqual(own_invoice.status_code, 200)
        self.assertIn(b"Invoice #PS-INV-", own_invoice.data)
        self.assertIn(b"500g", own_invoice.data)
        self.assertIn(b"Order Placed Successfully", own_invoice.data)
        self.assertIn(b"SAVED ORDER TOTAL", own_invoice.data)
        self.assertIn(b"\xe2\x82\xb917.00", own_invoice.data)
        self.assertNotIn(b"Discount / Coupon", own_invoice.data)
        self.assertNotIn(b"Delivery charges", own_invoice.data)
        self.assertIn(b'data-print', own_invoice.data)
        self.assertIn(b"security-ui.js", own_invoice.data)
        policy = own_invoice.headers["Content-Security-Policy"]
        self.assertIn("script-src 'self' 'nonce-", policy)
        style_nonce_match = re.search(
            rb'<style nonce="([^"]+)"',
            own_invoice.data,
        )
        self.assertIsNotNone(style_nonce_match)
        self.assertIn(
            b"'nonce-" + style_nonce_match.group(1) + b"'",
            policy.encode("ascii"),
        )

        self._set_session_role("user_mobile", "9999999999")
        other_invoice = self.client.get(f"/invoice/{order_id}")
        self.assertEqual(other_invoice.status_code, 404)

        self._set_session_role("admin_logged_in", True)
        admin_invoice = self.client.get(f"/invoice/{order_id}")
        self.assertEqual(admin_invoice.status_code, 200)

    def test_refund_remains_in_admin_orders_after_alert_marked_seen(self):
        order_id = self._create_order(
            status="Cancelled",
            cancelled_by="customer",
            cancel_seen_by_admin=False,
            payment_method="Online",
            payment_status="Paid",
            refund_status="Refund Pending",
            razorpay_payment_id="pay_test_seen_alert",
        )
        token = self._csrf_token()
        self._set_session_role("admin_logged_in", True)

        first_dashboard = self.client.get("/admin")
        self.assertIn(b"Refund Now", first_dashboard.data)
        response = self.client.post(
            f"/admin/cancel-alerts/{order_id}/seen",
            headers={"X-CSRFToken": token},
            environ_overrides={"REMOTE_ADDR": self.remote_addr},
        )
        self.assertEqual(response.status_code, 200)
        next_dashboard = self.client.get("/admin")
        self.assertIn(b"Refund Now", next_dashboard.data)

    def test_manual_refund_workflow_requires_explicit_admin_record(self):
        order_id = self._create_order(
            status="Cancelled",
            payment_method="Online",
            payment_status="Paid",
            refund_status="Refund Pending",
        )
        token = self._csrf_token()
        self._set_session_role("admin_logged_in", True)

        provider_attempt = self.client.post(
            f"/admin/refund/{order_id}",
            headers={"X-CSRFToken": token},
            environ_overrides={"REMOTE_ADDR": self.remote_addr},
        )
        self.assertEqual(provider_attempt.status_code, 400)
        self.assertIn("manually", provider_attempt.get_json()["message"])

        unconfirmed_record = self.client.post(
            f"/admin/refund/{order_id}/manual",
            headers={"X-CSRFToken": token},
            environ_overrides={"REMOTE_ADDR": self.remote_addr},
        )
        self.assertEqual(unconfirmed_record.status_code, 400)
        with store.app.app_context():
            order = store.db.session.get(store.Order, order_id)
            self.assertEqual(order.refund_status, "Refund Pending")
            self.assertFalse(order.refund_completed_manually)

        manual_record = self.client.post(
            f"/admin/refund/{order_id}/manual",
            data={"confirmation": f"REFUNDED {order_id}"},
            headers={"X-CSRFToken": token},
            environ_overrides={"REMOTE_ADDR": self.remote_addr},
        )
        self.assertEqual(manual_record.status_code, 200)
        with store.app.app_context():
            order = store.db.session.get(store.Order, order_id)
            self.assertEqual(order.refund_status, "Refunded")
            self.assertEqual(order.payment_status, "Refunded")
            self.assertTrue(order.refund_completed_manually)
            self.assertIsNotNone(order.refund_completed_manually_at)
            self.assertTrue(order.refund_completed_manually_by)

    def test_manual_refund_cannot_complete_while_provider_refund_is_processing(self):
        order_id = self._create_order(
            status="Cancelled",
            payment_method="Online",
            payment_status="Paid",
            refund_status="Refund Processing",
        )
        token = self._csrf_token()
        self._set_session_role("admin_logged_in", True)

        response = self.client.post(
            f"/admin/refund/{order_id}/manual",
            data={"confirmation": f"REFUNDED {order_id}"},
            headers={"X-CSRFToken": token},
            environ_overrides={"REMOTE_ADDR": self.remote_addr},
        )
        self.assertEqual(response.status_code, 400)
        with store.app.app_context():
            order = store.db.session.get(store.Order, order_id)
            self.assertEqual(order.refund_status, "Refund Processing")
            self.assertEqual(order.payment_status, "Paid")
            self.assertFalse(order.refund_completed_manually)

    def test_processed_provider_refund_is_recorded_as_complete(self):
        order_id = self._create_order(
            status="Cancelled",
            payment_method="Online",
            payment_status="Paid",
            refund_status="Refund Pending",
            razorpay_payment_id="pay_test_processed_refund",
        )
        token = self._csrf_token()
        self._set_session_role("admin_logged_in", True)

        with (
            patch.object(store, "RAZORPAY_KEY_ID", "test_key"),
            patch.object(store, "RAZORPAY_KEY_SECRET", "test_secret"),
            patch.object(
                store.razorpay_client.payment,
                "refund",
                return_value={"id": "rfnd_test_processed", "status": "processed"},
            ),
        ):
            response = self.client.post(
                f"/admin/refund/{order_id}",
                headers={"X-CSRFToken": token},
                environ_overrides={"REMOTE_ADDR": self.remote_addr},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["refund_status"], "Refunded")
        with store.app.app_context():
            order = store.db.session.get(store.Order, order_id)
            self.assertEqual(order.payment_status, "Refunded")
            self.assertEqual(order.razorpay_refund_id, "rfnd_test_processed")


if __name__ == "__main__":
    unittest.main()
