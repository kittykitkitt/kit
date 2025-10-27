import sqlite3
import os
import importlib.util
from typing import Optional, Dict, Any
from datetime import datetime


# --- Connect to DB ----------------------------------------------------------
DB_FILENAME = os.path.join(os.path.dirname(__file__), 'database1.db')


def connect(db_path: Optional[str] = None):
    """Return a sqlite3 connection. Default file is database1.db next to this file."""
    path = db_path or DB_FILENAME
    # enable row factory and foreign keys to make queries more predictable
    conn = sqlite3.connect(path, timeout=5)
    try:
        # enable foreign key enforcement
        conn.execute('PRAGMA foreign_keys = ON')
    except Exception:
        pass
    return conn


# --- Create tables ---
def create_tables():
    conn = connect()
    cur = conn.cursor()

    # Create login table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS login (
            admin_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)
    
    # Create menu table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS menu (
            menu_id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL
        )
    """)

    # Create orders table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_time TEXT NOT NULL,
            total REAL NOT NULL,
            paid REAL NOT NULL,
            change REAL NOT NULL,
            employee TEXT,
            receipt_filename TEXT UNIQUE
        )
    """)

    # Create order_items table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            order_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL NOT NULL,
            total REAL NOT NULL,
            FOREIGN KEY(order_id) REFERENCES orders(order_id)
        )
    """)

    # Create sales aggregate table (total quantity sold per code and total revenue)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            code TEXT PRIMARY KEY,
            name TEXT,
            total_quantity INTEGER NOT NULL DEFAULT 0,
            total_revenue REAL NOT NULL DEFAULT 0.0,
            last_sold TEXT
        )
    """)

    conn.commit()
    conn.close()

    # Migration: if older DB existed without employee/receipt_filename columns,
    # try to add them (ALTER TABLE). SQLite can only add columns; ignore errors.
    try:
        conn = connect()
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(orders)")
        cols = [r[1] for r in cur.fetchall()]
        if 'employee' not in cols:
            try:
                cur.execute("ALTER TABLE orders ADD COLUMN employee TEXT")
            except Exception:
                pass
        if 'receipt_filename' not in cols:
            try:
                cur.execute("ALTER TABLE orders ADD COLUMN receipt_filename TEXT")
            except Exception:
                pass
        conn.commit()
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def write_schema_sql(path: Optional[str] = None):
    """Write a SQL schema file compatible with SQLite containing the
    CREATE TABLE statements used by this module.
    """
    path = path or os.path.join(os.path.dirname(__file__), 'schema_mysqlite.sql')
    sql = '''-- SQLite schema for POS System Management cashier system
CREATE TABLE IF NOT EXISTS login (
    admin_id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS menu (
    menu_id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    price REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    order_id INTEGER PRIMARY KEY AUTOINCREMENT,
    date_time TEXT NOT NULL,
    total REAL NOT NULL,
    paid REAL NOT NULL,
    change REAL NOT NULL,
    employee TEXT,
    receipt_filename TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS order_items (
    order_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    price REAL NOT NULL,
    total REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sales (
    code TEXT PRIMARY KEY,
    name TEXT,
    total_quantity INTEGER NOT NULL DEFAULT 0,
    total_revenue REAL NOT NULL DEFAULT 0.0,
    last_sold TEXT
);
'''
    with open(path, 'w', encoding='utf-8') as f:
        f.write(sql)
    return path


def dump_seed_sql(path: Optional[str] = None):
    """Dump INSERT statements for menu and login based on system.py (if
    available) or current defaults. Returns path to the written SQL file."""
    path = path or os.path.join(os.path.dirname(__file__), 'seed_mysqlite.sql')
    # reuse insert_default_data logic to get menu/employees without writing to DB
    menu_items = None
    employees = None
    system_path = os.path.join(os.path.dirname(__file__), 'system.py')
    if os.path.exists(system_path):
        try:
            spec = importlib.util.spec_from_file_location('sysmod_for_dump', system_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore
            menu_items = getattr(mod, 'MENU', None)
            employees = getattr(mod, 'EMPLOYEES', None)
        except Exception:
            menu_items = None
            employees = None

    lines = ['-- Seed data for POS System Management\n']
    if employees and isinstance(employees, dict):
        for uname, info in employees.items():
            pwd = info.get('password', '')
            lines.append("INSERT OR IGNORE INTO login (username, password) VALUES ('%s', '%s');" % (uname.replace("'", "''"), pwd.replace("'", "''")))
    else:
        lines.append("INSERT OR IGNORE INTO login (username, password) VALUES ('kit', 'admin123');")

    if menu_items and isinstance(menu_items, dict):
        for category, items in menu_items.items():
            for code, name, price in items:
                lines.append("INSERT OR IGNORE INTO menu (code, name, category, price) VALUES ('%s', '%s', '%s', %s);" % (code.replace("'", "''"), name.replace("'", "''"), category.replace("'", "''"), float(price)))
    else:
        # fallback
        fallback = [
            ("AR", "Adobo Rice Bowl", "Student Meal", 65.00),
            ("SR", "Siomai Rice Bowl", "Student Meal", 60.00),
            ("BS", "Burger Steak Bowl", "Student Meal", 65.00),
        ]
        for code, name, cat, price in fallback:
            lines.append("INSERT OR IGNORE INTO menu (code, name, category, price) VALUES ('%s', '%s', '%s', %s);" % (code, name, cat, price))

    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    return path


# --- Fetch menu items from database ---
def fetch_all():
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT category, code, name, price FROM menu ORDER BY category;")
    rows = cur.fetchall()
    conn.close()
    return rows


# --- Insert default data ---
def insert_default_data():
    conn = connect()
    cur = conn.cursor()

    # Try to load menu and employees from local system.py if present so the
    # database is seeded with the same values as the application.
    menu_items = None
    employees: Optional[Dict[str, Dict[str, Any]]] = None
    system_path = os.path.join(os.path.dirname(__file__), 'system.py')
    if os.path.exists(system_path):
        try:
            spec = importlib.util.spec_from_file_location('sysmod_for_db', system_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore
            menu_items = getattr(mod, 'MENU', None)
            employees = getattr(mod, 'EMPLOYEES', None)
        except Exception:
            menu_items = None
            employees = None

    # Default login (fallback)
    if employees and isinstance(employees, dict):
        for uname, info in employees.items():
            pwd = info.get('password', '')
            cur.execute("INSERT OR IGNORE INTO login (username, password) VALUES (?, ?)", (uname, pwd))
    else:
        cur.execute("INSERT OR IGNORE INTO login (username, password) VALUES (?, ?)", ("kit", "admin123"))

    # Default menu items (from system.py if available, otherwise a built-in list)
    if menu_items and isinstance(menu_items, dict):
        inserts = []
        for category, items in menu_items.items():
            for code, name, price in items:
                inserts.append((code, name, category, float(price)))
        if inserts:
            cur.executemany("INSERT OR IGNORE INTO menu (code, name, category, price) VALUES (?, ?, ?, ?)", inserts)
    else:
        # fallback list (kept backward compatible)
        menu = [
            ("AR", "Adobo Rice Bowl", "Student Meal", 65.00),
            ("SR", "Siomai Rice Bowl", "Student Meal", 60.00),
            ("BS", "Burger Steak Bowl", "Student Meal", 65.00),
            ("LS", "Lumpiang Shanghai Bowl", "Student Meal", 65.00),
            ("CS", "Chicken Skin Bowl", "Student Meal", 60.00),
            ("SS", "Sisig Bowl", "Student Meal", 65.00),
        ]
        cur.executemany("INSERT OR IGNORE INTO menu (code, name, category, price) VALUES (?, ?, ?, ?)", menu)

    conn.commit()
    conn.close()

    print("Menu and login data inserted successfully into database1.db")


# --- Run this only once when initializing your DB ---

def save_receipt(items: list, total: float, paid: float, change: float) -> None:
    """Persist a receipt (order and its items) into the local SQLite database.

    items: iterable of (code, name, quantity, price, item_total)
    total/paid/change: numeric values
    """
    conn = connect()
    cur = conn.cursor()
    # 1. Insert into 'orders' table
    date_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("INSERT INTO orders (date_time, total, paid, change) VALUES (?, ?, ?, ?)",
                (date_time, float(total), float(paid), float(change)))
    order_id = cur.lastrowid

    # 2. Insert each item into 'order_items' table
    for item in items:
        code, name, quantity, price, item_total = item
        cur.execute("""
            INSERT INTO order_items (order_id, code, name, quantity, price, total)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (order_id, str(code), str(name), int(quantity), float(price), float(item_total)))

    conn.commit()
    conn.close()
    print(f"Receipt saved successfully with order_id: {order_id}")
    # update sales aggregates for these items
    try:
        _increment_sales(items, datetime.now())
    except Exception:
        # non-fatal; keep DB consistent even if sales update fails
        pass


def save_order(items: list, total: float, paid: float, change: float, employee: Optional[str] = None, receipt_filename: Optional[str] = None) -> int:
    """Save an order and its items. Stores employee and receipt filename when provided.

    Returns the created order_id.
    """
    conn = connect()
    cur = conn.cursor()
    date_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Try a straightforward insert. If a UNIQUE constraint on receipt_filename
    # causes an IntegrityError, fall back to selecting the existing order_id.
    try:
        cur.execute("INSERT INTO orders (date_time, total, paid, change, employee, receipt_filename) VALUES (?, ?, ?, ?, ?, ?)",
                    (date_time, float(total), float(paid), float(change), employee, receipt_filename))
        order_id = cur.lastrowid
    except sqlite3.IntegrityError:
        # If receipt_filename duplicated, try to fetch the existing order id.
        order_id = None
        if receipt_filename:
            row = cur.execute('SELECT order_id FROM orders WHERE receipt_filename = ?', (receipt_filename,)).fetchone()
            if row:
                order_id = row[0]
        if order_id is None:
            # re-raise if we cannot resolve
            conn.rollback()
            conn.close()
            raise

    # insert items for this order
    for item in items:
        code, name, quantity, price, item_total = item
        cur.execute("INSERT INTO order_items (order_id, code, name, quantity, price, total) VALUES (?, ?, ?, ?, ?, ?)",
                    (order_id, str(code), str(name), int(quantity), float(price), float(item_total)))
    conn.commit()
    conn.close()
    # update sales aggregates for these items
    try:
        _increment_sales(items, datetime.now())
    except Exception:
        # non-fatal; keep DB consistent even if sales update fails
        pass
    return order_id


def fetch_receipts() -> list:
    """Return a list of receipts (orders) with their items.

    Each entry is a dict with keys: order_id, date_time, total, paid, change, employee, receipt_filename, items
    """
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT order_id, date_time, total, paid, change, employee, receipt_filename FROM orders ORDER BY order_id DESC")
    orders = []
    rows = cur.fetchall()
    for row in rows:
        order_id, date_time, total, paid, change, employee, receipt_filename = row
        cur.execute("SELECT code, name, quantity, price, total FROM order_items WHERE order_id = ?", (order_id,))
        items = cur.fetchall()
        orders.append({'order_id': order_id, 'date_time': date_time, 'total': total, 'paid': paid, 'change': change, 'employee': employee, 'receipt_filename': receipt_filename, 'items': [tuple(it) for it in items]})
    conn.close()
    return orders


def import_receipts_from_folder(receipts_dir: Optional[str] = None) -> int:
    """Scan `receipts_dir` and import any text receipts not already recorded in the DB.

    Returns number of receipts imported.
    """
    receipts_dir = receipts_dir or os.path.join(os.path.dirname(__file__), 'receipts')
    if not os.path.isdir(receipts_dir):
        return 0
    imported = 0
    conn = connect()
    cur = conn.cursor()
    for fname in os.listdir(receipts_dir):
        if not fname.lower().endswith('.txt'):
            continue
        full = os.path.join(receipts_dir, fname)
        # skip if already imported (by filename)
        cur.execute('SELECT COUNT(1) FROM orders WHERE receipt_filename = ?', (fname,))
        if cur.fetchone()[0] > 0:
            continue
        try:
            with open(full, 'r', encoding='utf-8') as f:
                lines = [L.rstrip('\n') for L in f]
        except Exception:
            continue

        # parse employee from line that starts with 'Employee:'
        employee = None
        items = []
        for i, L in enumerate(lines):
            if L.startswith('Employee:'):
                employee = L.split(':', 1)[1].strip()
            # timestamp line: after employee it's typically the second line
            # Find the blank line that separates items from totals
        # attempt to parse items: lines containing ' x ' and '(@' style
        import re
        # accept optional $ or ₱ currency symbol when parsing saved receipts
        item_re = re.compile(r"^(\d+)\s+x\s+(.*?)\s+\(([^)]+)\)\s+@\s*[\$₱]?([0-9,]+\.?[0-9]*)\s*=\s*[\$₱]?([0-9,]+\.?[0-9]*)$")
        for L in lines:
            m = item_re.match(L)
            if m:
                qty = int(m.group(1))
                name = m.group(2).strip()
                code = m.group(3).strip()
                price = float(m.group(4).replace(',', '').replace('$', '').replace('₱', ''))
                total = float(m.group(5).replace(',', '').replace('$', '').replace('₱', ''))
                items.append((code, name, qty, price, total))

        # find totals
        subtotal = None
        paid = None
        change = None
        for L in reversed(lines[-10:]):
            if L.startswith('Subtotal:'):
                try:
                    subtotal = float(L.split(':',1)[1].strip().replace('$','').replace('₱','').replace(',',''))
                except Exception:
                    subtotal = None
            if L.startswith('Paid:'):
                try:
                    paid = float(L.split(':',1)[1].strip().replace('$','').replace('₱','').replace(',',''))
                except Exception:
                    paid = None
            if L.startswith('Change:'):
                try:
                    change = float(L.split(':',1)[1].strip().replace('$','').replace('₱','').replace(',',''))
                except Exception:
                    change = None

        if not items:
            continue
        total_val = subtotal if subtotal is not None else sum(it[4] for it in items)
        paid_val = paid if paid is not None else total_val
        change_val = change if change is not None else (paid_val - total_val)

        # insert into DB
        try:
            _ = save_order(items, total_val, paid_val, change_val, employee, fname)
            imported += 1
        except Exception:
            # try again using save_receipt fallback
            try:
                save_receipt(items, total_val, paid_val, change_val)
                imported += 1
            except Exception:
                pass

    conn.close()
    return imported


def _increment_sales(items: list, when: Optional[datetime] = None) -> None:
    """Increment sales aggregates for a list of items.

    items: iterable of (code, name, quantity, price, item_total)
    when: optional datetime for last_sold timestamp
    """
    if when is None:
        when = datetime.now()
    conn = connect()
    cur = conn.cursor()
    try:
        for code, name, qty, price, item_total in items:
            # upsert row in sales
            try:
                cur.execute("SELECT total_quantity, total_revenue FROM sales WHERE code = ?", (code,))
                row = cur.fetchone()
                if row:
                    cur.execute("UPDATE sales SET total_quantity = total_quantity + ?, total_revenue = total_revenue + ?, last_sold = ? WHERE code = ?",
                                (int(qty), float(item_total), when.strftime('%Y-%m-%d %H:%M:%S'), code))
                else:
                    cur.execute("INSERT INTO sales (code, name, total_quantity, total_revenue, last_sold) VALUES (?, ?, ?, ?, ?)",
                                (str(code), str(name), int(qty), float(item_total), when.strftime('%Y-%m-%d %H:%M:%S')))
            except Exception:
                # continue on item-level failures
                continue
        conn.commit()
    finally:
        try:
            conn.close()
        except Exception:
            pass


def update_sales_from_orders() -> int:
    """Rebuild sales aggregates from all existing order_items.

    Returns number of distinct product codes processed.
    """
    conn = connect()
    cur = conn.cursor()
    try:
        # clear table
        cur.execute('DELETE FROM sales')
        # aggregate
        cur.execute('SELECT code, name, SUM(quantity) as qty_sum, SUM(total) as revenue_sum, MAX((SELECT date_time FROM orders WHERE orders.order_id = order_items.order_id)) as last_dt FROM order_items GROUP BY code, name')
        rows = cur.fetchall()
        for code, name, qty_sum, revenue_sum, last_dt in rows:
            try:
                cur.execute('INSERT INTO sales (code, name, total_quantity, total_revenue, last_sold) VALUES (?, ?, ?, ?, ?)',
                            (code, name, int(qty_sum or 0), float(revenue_sum or 0.0), last_dt))
            except Exception:
                continue
        conn.commit()
        return len(rows)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def fetch_sales() -> list:
    """Return sales aggregate rows as dicts."""
    conn = connect()
    cur = conn.cursor()
    cur.execute('SELECT code, name, total_quantity, total_revenue, last_sold FROM sales ORDER BY total_revenue DESC')
    rows = cur.fetchall()
    conn.close()
    return [{'code': r[0], 'name': r[1], 'total_quantity': r[2], 'total_revenue': r[3], 'last_sold': r[4]} for r in rows]


def delete_imported_receipts(receipts_dir: Optional[str] = None) -> int:
    """Delete orders (and their order_items) in the DB that were imported from the receipts folder.

    Returns the number of orders deleted.
    """
    receipts_dir = receipts_dir or os.path.join(os.path.dirname(__file__), 'receipts')
    if not os.path.isdir(receipts_dir):
        return 0
    # gather filenames present in folder
    filenames = [f for f in os.listdir(receipts_dir) if f.lower().endswith('.txt')]
    if not filenames:
        return 0
    conn = connect()
    cur = conn.cursor()
    deleted = 0
    try:
        # find orders that reference these filenames
        qmarks = ','.join('?' for _ in filenames)
        cur.execute(f"SELECT order_id FROM orders WHERE receipt_filename IN ({qmarks})", tuple(filenames))
        rows = cur.fetchall()
        order_ids = [r[0] for r in rows]
        if not order_ids:
            return 0
        # delete items first
        qmarks2 = ','.join('?' for _ in order_ids)
        cur.execute(f"DELETE FROM order_items WHERE order_id IN ({qmarks2})", tuple(order_ids))
        cur.execute(f"DELETE FROM orders WHERE order_id IN ({qmarks2})", tuple(order_ids))
        deleted = cur.rowcount if cur.rowcount is not None else len(order_ids)
        conn.commit()
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return deleted

if __name__ == "__main__":
    create_tables()
    insert_default_data()