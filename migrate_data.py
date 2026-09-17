import sqlite3
from datetime import datetime

from app import app, db, Product, Customer, Order, Review


OLD_DB = "instance/pickels_store.db"


def parse_datetime(value):
    if not value:
        return None

    if isinstance(value, datetime):
        return value

    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


old = sqlite3.connect(OLD_DB)
old.row_factory = sqlite3.Row


with app.app_context():

    print("\n=== PICKELS STORE DATA MIGRATION ===")

    # --------------------------------------------------
    # 1. PRODUCTS
    # --------------------------------------------------

    old_products = old.execute(
        "SELECT * FROM product ORDER BY id"
    ).fetchall()

    print(f"\nMigrating {len(old_products)} products...")

    product_map = {}

    for row in old_products:

        existing = Product.query.filter_by(id=row["id"]).first()

        if existing:
            product_map[row["id"]] = existing.id
            print(f"Product {row['id']} already exists - skipped")
            continue

        product = Product(
            id=row["id"],
            name=row["name"],
            price=row["price"],
            unit=row["unit"],
            image=row["image"],
            description=row["description"],
            active=row["active"],
            stock=row["stock"]
        )

        db.session.add(product)
        product_map[row["id"]] = row["id"]

    db.session.commit()

    print("Products migration complete.")


    # --------------------------------------------------
    # 2. CUSTOMERS
    # --------------------------------------------------

    old_customers = old.execute(
        "SELECT * FROM customer ORDER BY id"
    ).fetchall()

    print(f"\nMigrating {len(old_customers)} customers...")

    customer_map = {}

    for row in old_customers:

        # Match an existing customer by mobile number.
        existing = Customer.query.filter_by(
            mobile=row["mobile"]
        ).first()

        if existing:
            customer_map[row["id"]] = existing.id
            print(
                f"Customer {row['id']} matched existing customer "
                f"{existing.id} - {row['mobile']}"
            )
            continue

        customer = Customer(
            name=row["name"],
            mobile=row["mobile"],
            address=row["address"],
            created_at=parse_datetime(row["created_at"]),
            updated_at=parse_datetime(row["updated_at"])
        )

        db.session.add(customer)
        db.session.flush()

        customer_map[row["id"]] = customer.id

        print(
            f"Customer {row['id']} -> new customer {customer.id}"
        )

    db.session.commit()

    print("Customers migration complete.")


    # --------------------------------------------------
    # 3. ORDERS
    # --------------------------------------------------

    old_orders = old.execute(
        'SELECT * FROM "order" ORDER BY id'
    ).fetchall()

    print(f"\nMigrating {len(old_orders)} orders...")

    for row in old_orders:

        existing = Order.query.filter_by(id=row["id"]).first()

        if existing:
            print(f"Order {row['id']} already exists - skipped")
            continue

        order = Order(
            id=row["id"],
            name=row["name"],
            mobile=row["mobile"],
            address=row["address"],
            items=row["items"],
            total=row["total"],
            status=row["status"],
            payment_method=row["payment_method"],
            created_at=parse_datetime(row["created_at"])
        )

        db.session.add(order)

    db.session.commit()

    print("Orders migration complete.")


    # --------------------------------------------------
    # 4. REVIEWS
    # --------------------------------------------------

    old_reviews = old.execute(
        "SELECT * FROM review ORDER BY id"
    ).fetchall()

    print(f"\nMigrating {len(old_reviews)} reviews...")

    for row in old_reviews:

        existing = Review.query.filter_by(id=row["id"]).first()

        if existing:
            print(f"Review {row['id']} already exists - skipped")
            continue

        new_customer_id = customer_map.get(row["customer_id"])

        if new_customer_id is None:
            print(
                f"Review {row['id']} skipped: "
                f"customer mapping not found"
            )
            continue

        review = Review(
            id=row["id"],
            product_id=product_map[row["product_id"]],
            customer_id=new_customer_id,
            rating=row["rating"],
            comment=row["comment"],
            created_at=parse_datetime(row["created_at"])
        )

        db.session.add(review)

    db.session.commit()

    print("Reviews migration complete.")


    # --------------------------------------------------
    # 5. RESET POSTGRESQL ID SEQUENCES
    # --------------------------------------------------

    print("\nUpdating PostgreSQL ID sequences...")

    db.session.execute(
        db.text(
            "SELECT setval("
            "pg_get_serial_sequence('product', 'id'), "
            "COALESCE((SELECT MAX(id) FROM product), 1), "
            "true)"
        )
    )

    db.session.execute(
        db.text(
            "SELECT setval("
            "pg_get_serial_sequence('customer', 'id'), "
            "COALESCE((SELECT MAX(id) FROM customer), 1), "
            "true)"
        )
    )

    db.session.execute(
        db.text(
            "SELECT setval("
            "pg_get_serial_sequence('order', 'id'), "
            "COALESCE((SELECT MAX(id) FROM \"order\"), 1), "
            "true)"
        )
    )

    db.session.execute(
        db.text(
            "SELECT setval("
            "pg_get_serial_sequence('review', 'id'), "
            "COALESCE((SELECT MAX(id) FROM review), 1), "
            "true)"
        )
    )

    db.session.commit()

    print("ID sequences updated.")


    # --------------------------------------------------
    # 6. FINAL COUNTS
    # --------------------------------------------------

    print("\n=== MIGRATION COMPLETE ===")

    print(f"Products : {Product.query.count()}")
    print(f"Customers: {Customer.query.count()}")
    print(f"Orders   : {Order.query.count()}")
    print(f"Reviews  : {Review.query.count()}")

    print("\nOld data has been copied to Supabase.")
    print("Your existing Supabase customer was NOT deleted.")


old.close()