
import sqlite3
import uuid
from datetime import datetime

DB_NAME = "restaurant.db"

# DATABASE CONNECTION

def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
# INITIALIZE DATABASE

def initialize_database():

    conn = get_connection()
    cursor = conn.cursor()

    try:

        # MENU TABLE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS menu (
                item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL,
                price REAL NOT NULL
            )
        """)

        # ORDERS TABLE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id TEXT,
                user_id INTEGER NOT NULL DEFAULT 1,
                customer_name TEXT DEFAULT '',
                customer_gstin TEXT DEFAULT '',
                subtotal REAL NOT NULL DEFAULT 0,
                discount REAL NOT NULL DEFAULT 0,
                gst REAL NOT NULL DEFAULT 0,
                grand_total REAL NOT NULL DEFAULT 0,
                order_date TEXT
            )
        """)

        # MIGRATE OLD ORDERS TABLE
        cursor.execute("PRAGMA table_info(orders)")

        existing_columns = {
            column[1] for column in cursor.fetchall()
        }

        migrations = {
            "invoice_id": "TEXT",
            "user_id": "INTEGER NOT NULL DEFAULT 1",
            "customer_name": "TEXT DEFAULT ''",
            "customer_gstin": "TEXT DEFAULT ''",
            "subtotal": "REAL NOT NULL DEFAULT 0",
            "discount": "REAL NOT NULL DEFAULT 0",
            "gst": "REAL NOT NULL DEFAULT 0",
            "grand_total": "REAL NOT NULL DEFAULT 0",
            "order_date": "TEXT"
        }

        for column, definition in migrations.items():

            if column not in existing_columns:

                cursor.execute(
                    f"ALTER TABLE orders ADD COLUMN {column} {definition}"
                )

        # FILL MISSING INVOICE IDS
        cursor.execute("""
            SELECT order_id
            FROM orders
            WHERE invoice_id IS NULL OR invoice_id = ''
        """)

        old_orders = cursor.fetchall()

        for order in old_orders:

            order_id = order[0]

            invoice_id = f"INV-OLD-{order_id:06d}"

            cursor.execute("""
                UPDATE orders
                SET invoice_id = ?
                WHERE order_id = ?
            """, (invoice_id, order_id))

        # FILL MISSING ORDER DATES
        current_date = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        cursor.execute("""
            UPDATE orders
            SET order_date = ?
            WHERE order_date IS NULL OR order_date = ''
        """, (current_date,))

        # UNIQUE INVOICE ID INDEX
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_invoice_id
            ON orders(invoice_id)
        """)

        # ORDER ITEMS TABLE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                item_id INTEGER,
                item_name TEXT NOT NULL,
                price REAL NOT NULL,
                quantity INTEGER NOT NULL,
                total REAL NOT NULL,

                FOREIGN KEY (order_id)
                REFERENCES orders(order_id)
            )
        """)

        # INSERT SAMPLE FOOD ITEMS
        cursor.execute("SELECT COUNT(*) FROM menu")

        count = cursor.fetchone()[0]

        if count == 0:

            food_items = [

                ("Burger", "Fast Food", 120),
                ("Cheese Burger", "Fast Food", 150),

                ("Veg Pizza", "Pizza", 250),
                ("Margherita Pizza", "Pizza", 220),
                ("Farmhouse Pizza", "Pizza", 320),

                ("Pasta", "Italian", 180),
                ("White Sauce Pasta", "Italian", 220),
                ("Red Sauce Pasta", "Italian", 200),

                ("Sandwich", "Fast Food", 80),
                ("Grilled Sandwich", "Fast Food", 120),

                ("French Fries", "Snacks", 90),
                ("Garlic Bread", "Snacks", 110),

                ("Momos", "Chinese", 100),
                ("Veg Noodles", "Chinese", 140),
                ("Fried Rice", "Chinese", 150),

                ("Paneer Tikka", "Starters", 220),
                ("Chilli Paneer", "Chinese", 200),

                ("Cold Coffee", "Beverages", 100),
                ("Lemon Soda", "Beverages", 60),
                ("Chocolate Shake", "Beverages", 130)

            ]

            cursor.executemany("""
                INSERT INTO menu (
                    item_name,
                    category,
                    price
                )
                VALUES (?, ?, ?)
            """, food_items)

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()
# GET MENU ITEMS

def get_menu_items():

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute("""
            SELECT
                item_id,
                item_name,
                category,
                price
            FROM menu
            ORDER BY item_id
        """)

        items = cursor.fetchall()

        return items

    finally:
        conn.close()
# ADD MENU ITEM

def add_menu_item(item_name, category, price):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute("""
            INSERT INTO menu (
                item_name,
                category,
                price
            )
            VALUES (?, ?, ?)
        """, (item_name, category, price))

        conn.commit()

        return cursor.lastrowid

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()
# SAVE ORDER / INVOICE

def save_order(
    user_id=1,
    cart=None,
    subtotal=0,
    discount=0,
    gst=0,
    grand_total=0,
    customer_name="",
    customer_gstin=""
):

    if cart is None:
        cart = []

    if not cart:
        raise ValueError("Cannot save an empty cart.")

    conn = get_connection()
    cursor = conn.cursor()

    invoice_id = (
        "INV-"
        + datetime.now().strftime("%Y%m%d")
        + "-"
        + uuid.uuid4().hex[:6].upper()
    )

    order_date = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    try:

        # INSERT ORDER
        cursor.execute("""
            INSERT INTO orders (
                invoice_id,
                user_id,
                customer_name,
                customer_gstin,
                subtotal,
                discount,
                gst,
                grand_total,
                order_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            invoice_id,
            user_id,
            customer_name,
            customer_gstin,
            subtotal,
            discount,
            gst,
            grand_total,
            order_date
        ))

        order_id = cursor.lastrowid

        # INSERT CART ITEMS
        for item in cart:

            cursor.execute("""
                INSERT INTO order_items (
                    order_id,
                    item_id,
                    item_name,
                    price,
                    quantity,
                    total
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                order_id,
                item.get("item_id"),
                item["item_name"],
                item["price"],
                item["quantity"],
                item["total"]
            ))

        conn.commit()

        return order_id, invoice_id

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()
# GET ALL ORDERS FOR USER

def get_user_orders(user_id=1):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute("""
            SELECT
                order_id,
                invoice_id,
                customer_name,
                customer_gstin,
                subtotal,
                discount,
                gst,
                grand_total,
                order_date
            FROM orders
            WHERE user_id = ?
            ORDER BY order_id DESC
        """, (user_id,))

        orders = cursor.fetchall()

        return orders

    finally:
        conn.close()
# GET ITEMS FOR ONE ORDER

def get_order_items(order_id):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute("""
            SELECT
                item_id,
                item_name,
                price,
                quantity,
                total
            FROM order_items
            WHERE order_id = ?
            ORDER BY id
        """, (order_id,))

        items = cursor.fetchall()

        return items

    finally:
        conn.close()
# GET INVOICE DETAILS

def get_invoice_details(invoice_id):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute("""
            SELECT
                order_id,
                invoice_id,
                user_id,
                customer_name,
                customer_gstin,
                subtotal,
                discount,
                gst,
                grand_total,
                order_date
            FROM orders
            WHERE invoice_id = ?
        """, (invoice_id,))

        invoice = cursor.fetchone()

        return invoice

    finally:
        conn.close()
# DELETE ORDER

def delete_order(order_id):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        # Delete order items first
        cursor.execute("""
            DELETE FROM order_items
            WHERE order_id = ?
        """, (order_id,))

        # Delete order
        cursor.execute("""
            DELETE FROM orders
            WHERE order_id = ?
        """, (order_id,))

        conn.commit()

        return cursor.rowcount

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()
# INITIALIZE DATABASE AUTOMATICALLY

initialize_database()
