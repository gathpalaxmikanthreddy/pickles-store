import sqlite3
from app import app, db, Product, Customer, Order, Review

OLD_DB = "instance/pickels_store.db"

old = sqlite3.connect(OLD_DB)
old.row_factory = sqlite3.Row

with app.app_context():
    print("\n=== MIGRATION CHECK ===")

    old_products = old.execute("SELECT * FROM product").fetchall()
    old_customers = old.execute("SELECT * FROM customer").fetchall()
    old_orders = old.execute('SELECT * FROM "order"').fetchall()
    old_reviews = old.execute("SELECT * FROM review").fetchall()

    print(f"Old SQLite products : {len(old_products)}")
    print(f"Old SQLite customers: {len(old_customers)}")
    print(f"Old SQLite orders   : {len(old_orders)}")
    print(f"Old SQLite reviews  : {len(old_reviews)}")

    print("\nCurrent Supabase:")

    print(f"Products : {Product.query.count()}")
    print(f"Customers: {Customer.query.count()}")
    print(f"Orders   : {Order.query.count()}")
    print(f"Reviews  : {Review.query.count()}")

    print("\nNo data has been changed.")
    print("Migration check completed.")

old.close()