#!/usr/bin/env python3
"""POS System Management - GUI and CLI modes with employee authentication."""

import os
import sys
import argparse
from datetime import datetime
from typing import Dict, Tuple, Optional
from urllib.error import URLError
import urllib.request
import io
# optional DB integration
try:
    import database
    HAS_DATABASE = True
except Exception:
    database = None
    HAS_DATABASE = False

# Optional Pillow support for JPEG images. If unavailable, images will be skipped.
try:
    from PIL import Image, ImageTk  # type: ignore
    HAS_PIL = True
except Exception:
    HAS_PIL = False

# -- Configuration / Constants -------------------------------------------------
HEADER_NAME = 'POS System Management'
RECEIPTS_DIR = 'receipts'

THEME = {
    'bg': '#F5E6D3',
    'accent': '#9B7D52',
    'tile_bg': '#E8DCC8',
    'tile_inner': '#DCC7AD',
    'text': '#2D1B0F',
}

MENU = {
    "Student Meals": [
        ("AR", "Adobo Rice Bowl", 65),
        ("SR", "Siomai Rice Bowl", 60),
        ("BS", "Burger Steak Bowl", 65),
        ("LS", "Lumpiang Shanghai Bowl", 65),
        ("CS", "Chicken Skin Bowl", 60),
        ("SS", "Sisig Bowl", 65),
    ],
    "Add-ons": [
        ("R", "Rice", 20),
        ("E", "Egg", 15),
        ("SM", "Siomai (4pcs)", 25),
        ("CH", "Cheese Sticks (7pcs)", 20),
        ("F", "Fries", 25),
    ],
    "Drinks": [
        ("SG", "Sago't Gulaman", 30),
        ("BJ", "Buko Juice", 30),
        ("CK", "Coke", 25),
        ("RY", "Royal", 25),
        ("SP", "Sprite", 25),
    ],
    "Shakes": [
        ("MG", "Mango Graham Shake", 45),
        ("WM", "Watermelon Shake", 45),
        ("CM", "Choco Milo Shake", 45),
    ],
}

EMPLOYEES = {
    "kit": {"password": "admin123", "name": "Kit"},
}

# Map item codes to image URLs (GitHub raw links provided)
IMAGE_URLS = {
    'AR': 'https://github.com/kittykitkitt/kit/blob/main/adobo%20rice%20bowl.jpg?raw=true',
    'LS': 'https://github.com/kittykitkitt/kit/blob/main/shanghai%20rice%20bowl.jpg?raw=true',
    'BS': 'https://github.com/kittykitkitt/kit/blob/main/burger%20steak%20bowl.jpg?raw=true',
    'SR': 'https://github.com/kittykitkitt/kit/blob/main/siomai%20rice%20bowl.jpg?raw=true',
    'SS': 'https://github.com/kittykitkitt/kit/blob/main/pork%20sisig%20rice%20bowl.jpg?raw=true',
    'CS': 'https://github.com/kittykitkitt/kit/blob/main/chicken%20skin%20rice%20bowl.jpg?raw=true',
}

# Images for Add-ons
IMAGE_URLS.update({
    'R':  'https://github.com/kittykitkitt/kit/blob/main/rice.jpg?raw=true',
    'E':  'https://github.com/kittykitkitt/kit/blob/main/egg.jpg?raw=true',
    'SM': 'https://github.com/kittykitkitt/kit/blob/main/siomai.jpg?raw=true',
    'CH': 'https://github.com/kittykitkitt/kit/blob/main/cheese%20stick.jpg?raw=true',
    'F':  'https://github.com/kittykitkitt/kit/blob/main/fries.jpg?raw=true',
})

# Images for Drinks
IMAGE_URLS.update({
    'SG': 'https://github.com/kittykitkitt/kit/blob/main/gulaman.jpg?raw=true',
    'BJ': 'https://github.com/kittykitkitt/kit/blob/main/buko%20juice.jpg?raw=true',
    'CK': 'https://github.com/kittykitkitt/kit/blob/main/coke.jpg?raw=true',
    'RY': 'https://github.com/kittykitkitt/kit/blob/main/royal.jpg?raw=true',
    'SP': 'https://github.com/kittykitkitt/kit/blob/main/sprite.jpg?raw=true',
})

# Images for Shakes
IMAGE_URLS.update({     
    'MG': 'https://github.com/kittykitkitt/kit/blob/main/mango%20graham%20shake.jpg?raw=true',
    'WM': 'https://github.com/kittykitkitt/kit/blob/main/watermelon%20shake.png?raw=true',
    'CM': 'https://github.com/kittykitkitt/kit/blob/main/choco%20milo%20shake.jpg?raw=true',
})  

# thumbnail size used for menu tile previews
IMAGE_THUMBNAIL = (140, 70)

def build_lookup(menu) -> Dict[str, Tuple[str, float]]:
    """Create a code -> (name, price) lookup from MENU.

    Codes are normalized to uppercase and prices are converted to float.
    """
    lookup: Dict[str, Tuple[str, float]] = {}
    for _, items in menu.items():
        for code, name, price in items:
            lookup[code.upper()] = (name, float(price))
    return lookup

LOOKUP = build_lookup(MENU)

def format_currency(v: float) -> str:
    """Format number as currency string using Philippine peso sign."""
    return f"₱{v:,.2f}"

class Order:
    """Simple order container.

    Items are stored as dicts: {'code', 'name', 'price', 'qty'}.
    This class intentionally keeps a simple structure for easy serialization
    and straightforward unit testing.
    """
    def __init__(self) -> None:
        self.items = []

    def add(self, code: str, name: str, price: float, qty: int = 1) -> None:
        """Add qty of an item to the order. If present, increase quantity."""
        for it in self.items:
            if it['code'] == code:
                it['qty'] += int(qty)
                return
        self.items.append({'code': code, 'name': name, 'price': float(price), 'qty': int(qty)})

    def remove_index(self, idx: int) -> None:
        if 0 <= idx < len(self.items):
            del self.items[idx]

    def clear(self) -> None:
        self.items.clear()

    def subtotal(self) -> float:
        return sum(it['price'] * it['qty'] for it in self.items)

    def is_empty(self) -> bool:
        return len(self.items) == 0

    def as_lines(self):
        for it in self.items:
            yield (it['code'], it['name'], it['qty'], it['price'], it['price'] * it['qty'])

    def __repr__(self) -> str:  # helpful when debugging
        return f"Order({self.items!r})"

def ensure_receipts_dir() -> None:
    os.makedirs(RECEIPTS_DIR, exist_ok=True)


def save_receipt(order: Order, paid: float, change: float, employee_name: Optional[str]):
    ensure_receipts_dir()
    now = datetime.now().strftime('%Y%m%d_%H%M%S')
    fname = os.path.join(RECEIPTS_DIR, f'receipt_{now}.txt')
    with open(fname, 'w', encoding='utf-8') as f:
        f.write(f"{HEADER_NAME}\n")
        f.write(f'Employee: {employee_name}\n')
        f.write(now + '\n\n')
        for code, name, qty, price, total in order.as_lines():
            f.write(f"{qty} x {name} ({code}) @ {format_currency(price)} = {format_currency(total)}\n")
        f.write('\n')
        subtotal = order.subtotal()
        tax = 0.0
        total = subtotal + tax
        f.write(f'Subtotal: {format_currency(subtotal)}\n')
        f.write(f'Tax: {format_currency(tax)}\n')
        f.write(f'Total: {format_currency(total)}\n')
        f.write(f'Paid: {format_currency(paid)}\n')
        f.write(f'Change: {format_currency(change)}\n')
    return fname

def get_employee_info(username: str) -> Optional[Dict[str, str]]:
    if not username:
        return None
    return EMPLOYEES.get(username.lower())


def authenticate(username: str, password: str) -> bool:
    info = get_employee_info(username)
    return bool(info and info.get('password') == password)


def cli_login():
    print('Employee login')
    for _ in range(3):
        u = input('Username: ').strip()
        p = input('Password: ').strip()
        if authenticate(u, p):
            info = get_employee_info(u)
            return info['name'] if info else u
        print('Invalid credentials')
    print('Failed login')
    sys.exit(1)

def cli_main(employee_name):
    order = Order()
    print(f'{HEADER_NAME} - CLI mode (employee: {employee_name})')
    print('Type "help" for commands')
    while True:
        try:
            cmd = input('> ').strip()
        except (EOFError, KeyboardInterrupt):
            print('\nExiting')
            break
        if not cmd:
            continue
        parts = cmd.split()
        c = parts[0].lower()
        if c in ('quit', 'exit'):
            print('Goodbye')
            break
        if c == 'help':
            print('Commands: menu, add <code> [qty], cart, remove <index>, clear, checkout, quit')
            continue
        if c == 'menu':
            for cat, items in MENU.items():
                print('==', cat, '==')
                for code, name, price in items:
                    print(code, name, format_currency(price))
            continue
        if c == 'add':
            if len(parts) < 2:
                print('Usage: add <code> [qty]')
                continue
            code = parts[1].upper()
            qty = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
            if code in LOOKUP:
                name, price = LOOKUP[code]
                order.add(code, name, price, qty)
                print(f'Added {qty} x {name}')
            else:
                print('Unknown code')
            continue
        if c == 'cart':
            if order.is_empty():
                print('Cart empty')
            else:
                for i, (code, name, qty, price, total) in enumerate(order.as_lines()):
                    print(i, qty, 'x', name, format_currency(price), '->', format_currency(total))
                print('Subtotal:', format_currency(order.subtotal()))
            continue
        if c == 'remove':
            if len(parts) < 2 or not parts[1].isdigit():
                print('Usage: remove <index>')
                continue
            order.remove_index(int(parts[1]))
            continue
        if c == 'clear':
            order.clear()
            print('Cleared')
            continue
        if c == 'checkout':
            if order.is_empty():
                print('Cart empty')
                continue
            subtotal = order.subtotal()
            print('Total:', format_currency(subtotal))
            paid_raw = input('Paid amount: ').strip()
            try:
                paid = float(paid_raw)
            except Exception:
                print('Invalid amount')
                continue
            change = paid - subtotal
            # capture items before clearing order so we can store them in DB
            items = list(order.as_lines())
            fname = save_receipt(order, paid, change, employee_name)
            print('Receipt saved to', fname)
            # try saving into DB (best-effort)
            try:
                if HAS_DATABASE and database:
                    _ = database.save_order(items, subtotal, paid, change, employee_name, os.path.basename(fname))
            except Exception:
                pass
            order.clear()
            continue

def _has_tkinter() -> bool:
    """Return True if a tkinter installation is available on this Python.

    Use importlib.util.find_spec to avoid importing tkinter at module load time
    (prevents linter 'imported but unused' warnings and is lightweight).
    """
    try:
        import importlib.util
        return importlib.util.find_spec('tkinter') is not None
    except Exception:
        return False

if _has_tkinter():
    import tkinter as tk
    from tkinter import ttk, simpledialog, messagebox

    class CashierGUI(tk.Tk):
        def __init__(self, employee_name=None):
            super().__init__()
            self._employee_name = employee_name
            title = HEADER_NAME
            if employee_name:
                title += f' — {employee_name}'
            self.title(title)
            self.geometry('1000x650')
            self.configure(bg=THEME['bg'])
            style = ttk.Style(self)
            try:
                style.theme_use('clam')
            except Exception:
                pass
            style.configure('TFrame', background=THEME['bg'])
            style.configure('TButton', background=THEME['accent'], foreground='white', font=('Helvetica', 10, 'bold'))
            style.configure('TButton:hover', background='#8B6F47')
            style.configure('Header.TLabel', background=THEME['accent'], foreground='white', font=('Helvetica', 16, 'bold'))
            style.map('TButton', background=[('active', '#8B6F47')])

            header = tk.Frame(self, bg=THEME['accent'], height=48)
            header.pack(fill='x')
            header.pack_propagate(False)
            hdr_lbl = tk.Label(header, text=HEADER_NAME, bg=THEME['accent'], fg='#FFFEF9', font=('Helvetica', 18, 'bold'))
            hdr_lbl.pack(side='left', padx=15, pady=10)
            # employee label shown top-right to indicate who is currently logged in
            self._emp_lbl = tk.Label(header, text='', bg=THEME['accent'], fg='#FFFEF9', font=('Helvetica', 11, 'bold'))
            self._emp_lbl.pack(side='right', padx=15, pady=12)
            # allow clicking the employee label to open a small account popup
            try:
                self._emp_lbl.bind('<Button-1>', lambda e: self._on_emp_click())
            except Exception:
                pass

            container = ttk.Frame(self)
            container.pack(fill='both', expand=True, padx=8, pady=8)

            left = ttk.Frame(container)
            left.pack(side='left', fill='both', expand=True)

            self.canvas = tk.Canvas(left, bg=THEME['bg'], highlightthickness=0)
            scrollbar = ttk.Scrollbar(left, orient='vertical', command=self.canvas.yview)
            self.scrollable_frame = ttk.Frame(self.canvas)
            self.scrollable_frame.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
            self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor='nw')
            self.canvas.configure(yscrollcommand=scrollbar.set)
            self.canvas.pack(side='left', fill='both', expand=True)
            scrollbar.pack(side='right', fill='y')

            def _on_mousewheel(event):
                if sys.platform.startswith('win'):
                    delta = -1 * (event.delta // 120)
                    self.canvas.yview_scroll(delta, 'units')
                else:
                    if getattr(event, 'num', None) == 4:
                        self.canvas.yview_scroll(-1, 'units')
                    elif getattr(event, 'num', None) == 5:
                        self.canvas.yview_scroll(1, 'units')
                    else:
                        try:
                            delta = -1 * int(event.delta)
                            self.canvas.yview_scroll(delta, 'units')
                        except Exception:
                            pass

            def _bind_mousewheel(_):
                if sys.platform.startswith('win'):
                    self.canvas.bind_all('<MouseWheel>', _on_mousewheel)
                else:
                    self.canvas.bind_all('<Button-4>', _on_mousewheel)
                    self.canvas.bind_all('<Button-5>', _on_mousewheel)

            def _unbind_mousewheel(_):
                if sys.platform.startswith('win'):
                    self.canvas.unbind_all('<MouseWheel>')
                else:
                    self.canvas.unbind_all('<Button-4>')
                    self.canvas.unbind_all('<Button-5>')

            self._bind_mousewheel_fn = _bind_mousewheel
            self._unbind_mousewheel_fn = _unbind_mousewheel
            self.canvas.bind('<Enter>', self._bind_mousewheel_fn)
            self.canvas.bind('<Leave>', self._unbind_mousewheel_fn)

            self.add_buttons = []
            # cache for Tk image objects to avoid GC and reloading
            self._images = {}

            # centralized image loader helper (bound to instance). This must
            # exist before we build tiles because the tile loop calls it.
            def _load_image(code: str):
                code = code.upper()
                if code in self._images:
                    return self._images[code]
                url = IMAGE_URLS.get(code)
                if not url or not HAS_PIL:
                    return None
                try:
                    with urllib.request.urlopen(url, timeout=5) as resp:
                        data = resp.read()
                    pil = Image.open(io.BytesIO(data))
                    pil.thumbnail(IMAGE_THUMBNAIL)
                    tkimg = ImageTk.PhotoImage(pil)
                    self._images[code] = tkimg
                    return tkimg
                except URLError:
                    # network-related issue (DNS, timeout, HTTP error)
                    return None
                except Exception:
                    # PIL or other unexpected errors
                    return None

            # bind helper to instance
            self._load_image = _load_image

            for cat, items in MENU.items():
                lbl = ttk.Label(self.scrollable_frame, text=cat, font=('Helvetica', 12, 'bold'))
                lbl.pack(anchor='w', pady=(8, 0), padx=6)

                tiles = ttk.Frame(self.scrollable_frame)
                tiles.pack(fill='x', padx=6, pady=4)
                cols = 2
                for idx, (code, name, price) in enumerate(items):
                    r = idx // cols
                    c = idx % cols
                    tile = tk.Frame(tiles, bg=THEME['tile_bg'], bd=3, relief='sunken', width=180, height=90)
                    tile.grid(row=r, column=c, padx=8, pady=8, sticky='nsew')
                    tile.grid_propagate(False)
                    inner = tk.Frame(tile, bg=THEME['tile_bg'])
                    inner.pack(fill='both', expand=True, padx=2, pady=2)
                    code_lbl = tk.Label(inner, text=code.upper(), font=('Helvetica', 11, 'bold'), bg=THEME['tile_bg'], fg='#6B4423')
                    code_lbl.pack(anchor='nw', padx=6, pady=(4, 2))
                    # try to load image for this item code (best-effort via helper)
                    img = None
                    try:
                        img = self._load_image(code)
                    except Exception:
                        img = None
                    if img:
                        img_lbl = tk.Label(inner, image=img, bg=THEME['tile_bg'])
                        img_lbl.pack(anchor='center', pady=(2, 2))
                    name_lbl = tk.Label(inner, text=name, font=('Helvetica', 10, 'bold'), bg=THEME['tile_bg'], fg=THEME['text'], wraplength=160, justify='left')
                    name_lbl.pack(anchor='nw', padx=6, pady=(0, 4), fill='both', expand=True)
                    price_lbl = tk.Label(inner, text=format_currency(price), font=('Helvetica', 10, 'bold'), bg=THEME['tile_inner'], fg='#6B4423')
                    price_lbl.pack(anchor='se', padx=6, pady=(4, 4))

                    def _make_click(c):
                        def _cb(ev=None):
                            try:
                                q = int(self.qty_spinbox.get())
                            except (TypeError, ValueError):
                                q = 1
                            self._add_by_code(c, qty=q)
                        return _cb

                    click_cb = _make_click(code)
                    tile.bind('<Button-1>', click_cb)
                    code_lbl.bind('<Button-1>', click_cb)
                    name_lbl.bind('<Button-1>', click_cb)
                    price_lbl.bind('<Button-1>', click_cb)

                    self.add_buttons.append((tile, click_cb, (code_lbl, name_lbl, price_lbl)))

                # make columns expand evenly
                for col_i in range(cols):
                    try:
                        tiles.grid_columnconfigure(col_i, weight=1)
                    except tk.TclError:
                        pass

            right = ttk.Frame(container, width=380)
            right.pack(side='right', fill='both')

            top_right = ttk.Frame(right)
            top_right.pack(fill='x', padx=6, pady=(6, 4))
            qty_lbl = ttk.Label(top_right, text='Qty:', font=('Helvetica', 11, 'bold'))
            qty_lbl.pack(side='left')
            self.qty_spinbox = tk.Spinbox(top_right, from_=1, to=99, width=5, bg='#FFFEF9', fg='#3D2817', font=('Helvetica', 11), relief='ridge', bd=2)
            self.qty_spinbox.pack(side='left', padx=(8, 20))

            self.tree = ttk.Treeview(right, columns=('code', 'name', 'qty', 'price', 'total'), show='headings', height=18)
            cols = [('code', 'Code', 60), ('name', 'Name', 160), ('qty', 'Qty', 50), ('price', 'Price', 70), ('total', 'Total', 70)]
            for col, txt, w in cols:
                self.tree.heading(col, text=txt)
                self.tree.column(col, width=w, anchor='center')
            tree_style = ttk.Style()
            tree_style.configure('Treeview', background='#FFFEF9', foreground='#2D1B0F', fieldbackground='#FFFEF9', font=('Helvetica', 10))
            tree_style.configure('Treeview.Heading', background='#E8DCC8', foreground='#3D2817', font=('Helvetica', 10, 'bold'))
            tree_style.map('Treeview', background=[('selected', '#9B7D52')], foreground=[('selected', '#FFFEF9')])
            self.tree.pack(fill='both', expand=True, padx=6, pady=6)

            btns = ttk.Frame(right)
            btns.pack(fill='x', padx=6, pady=(0,6))
            self.remove_btn = ttk.Button(btns, text='Remove Selected', command=self._remove_selected)
            self.remove_btn.pack(side='left', padx=4)
            self.clear_btn = ttk.Button(btns, text='Clear Cart', command=self._clear)
            self.clear_btn.pack(side='left', padx=4)
            self.checkout_btn = ttk.Button(btns, text='Checkout', command=self._checkout)
            self.checkout_btn.pack(side='right', padx=4)

            self._order = Order()

            pass

            try:
                self._enable_ui(False)
            except AttributeError:
                # if _enable_ui isn't present for some reason, ignore
                pass

        def show_login_box(self):
            top = tk.Toplevel(self)
            top.title('Employee login')
            top.transient(self)
            top.grab_set()
            top.configure(bg='#F5E6D3')
            top.resizable(False, False)
            frm = ttk.Frame(top, padding=16)
            frm.pack(fill='both', expand=True)
            title_lbl = ttk.Label(frm, text='Please sign in', font=('Helvetica', 14, 'bold'))
            title_lbl.grid(row=0, column=0, columnspan=2, pady=(0, 12))
            ttk.Label(frm, text='Username:', font=('Helvetica', 10)).grid(row=1, column=0, sticky='e', padx=(0, 8), pady=6)
            ttk.Label(frm, text='Password:', font=('Helvetica', 10)).grid(row=2, column=0, sticky='e', padx=(0, 8), pady=6)
            user_e = tk.Entry(frm, font=('Helvetica', 10), bg='#FFFEF9', fg='#3D2817', relief='ridge', bd=2, width=20)
            pass_e = tk.Entry(frm, font=('Helvetica', 10), bg='#FFFEF9', fg='#3D2817', relief='ridge', bd=2, width=20, show='•')
            user_e.grid(row=1, column=1, pady=6)
            pass_e.grid(row=2, column=1, pady=6)
            err = ttk.Label(frm, text='', foreground='#C85A54', font=('Helvetica', 9, 'bold'))
            err.grid(row=3, column=0, columnspan=2, pady=(6,0))
            btn_fr = ttk.Frame(frm)
            btn_fr.grid(row=4, column=0, columnspan=2, pady=(16,0))

            def do_cancel():
                try:
                    top.grab_release()
                except tk.TclError:
                    pass
                try:
                    top.destroy()
                except tk.TclError:
                    pass
                try:
                    self.destroy()
                except tk.TclError:
                    pass

            # Disable the window manager close button (X) on the login box
            # so users cannot bypass authentication by closing the dialog.
            try:
                top.protocol('WM_DELETE_WINDOW', lambda: None)
            except Exception:
                pass

            def do_login(event=None):
                uname = user_e.get().strip()
                pwd = pass_e.get()
                if authenticate(uname, pwd):
                    info = get_employee_info(uname)
                    self._employee_name = info['name'] if info else uname
                    self.title(f'{HEADER_NAME} — {self._employee_name}')
                    try:
                        # update top-right employee label
                        self._emp_lbl.config(text=f"Employee: {self._employee_name}")
                    except Exception:
                        pass
                    try:
                        top.grab_release()
                    except tk.TclError:
                        # ignore failures releasing the grab
                        pass
                    try:
                        self._enable_ui(True)
                    except AttributeError:
                        pass
                    try:
                        top.destroy()
                    except tk.TclError:
                        pass
                else:
                    err.config(text='Invalid credentials')

            login_btn = ttk.Button(btn_fr, text='Login', command=do_login)
            login_btn.pack(side='left', padx=8)
            cancel_btn = ttk.Button(btn_fr, text='Cancel', command=do_cancel)
            cancel_btn.pack(side='right', padx=8)
            user_e.focus_set()
            user_e.bind('<Return>', do_login)
            pass_e.bind('<Return>', do_login)
            # center the login box over the main window
            self.update_idletasks()
            w = top.winfo_reqwidth()
            h = top.winfo_reqheight()
            x = self.winfo_x() + (self.winfo_width() - w) // 2
            y = self.winfo_y() + (self.winfo_height() - h) // 2
            try:
                top.geometry(f'+{x}+{y}')
            except tk.TclError:
                pass

        def _on_emp_click(self, event=None):
            """Show a small account popup when the employee label is clicked.

            If not signed in, open the login dialog. If signed in, show a
            small Toplevel with a Logout button.
            """
            if not getattr(self, '_employee_name', None):
                try:
                    self.show_login_box()
                except Exception:
                    pass
                return

            try:
                top = tk.Toplevel(self)
                top.title('Account')
                top.transient(self)
                top.resizable(False, False)
                frm = ttk.Frame(top, padding=8)
                frm.pack(fill='both', expand=True)
                lbl = ttk.Label(frm, text=f'Logged in as {self._employee_name}', font=('Helvetica', 10))
                lbl.pack(pady=(0, 8))
                btn_fr = ttk.Frame(frm)
                btn_fr.pack(fill='x')
                def _do_logout():
                    self._perform_logout(top)
                logout_btn = ttk.Button(btn_fr, text='Logout', command=_do_logout)
                logout_btn.pack(side='left', padx=6)
                cancel_btn = ttk.Button(btn_fr, text='Cancel', command=lambda: top.destroy())
                cancel_btn.pack(side='right', padx=6)
                # position the small popup near the top-right of the main window
                self.update_idletasks()
                w = top.winfo_reqwidth()
                x = self.winfo_x() + self.winfo_width() - w - 20
                y = self.winfo_y() + 48
                try:
                    top.geometry(f'+{x}+{y}')
                except tk.TclError:
                    pass
                try:
                    top.grab_set()
                except tk.TclError:
                    pass
            except Exception:
                # fallback: ask to logout via confirmation
                try:
                    if messagebox.askyesno('Logout', 'Log out now?'):
                        self._perform_logout(None)
                except Exception:
                    pass

        def _perform_logout(self, popup_top):
            """Clear employee state, disable UI and show the login box."""
            try:
                if popup_top:
                    try:
                        popup_top.grab_release()
                    except Exception:
                        pass
                    try:
                        popup_top.destroy()
                    except Exception:
                        pass
            except Exception:
                pass

            self._employee_name = None
            try:
                self._emp_lbl.config(text='')
            except Exception:
                pass
            try:
                self.title(HEADER_NAME)
            except Exception:
                pass
            try:
                self._enable_ui(False)
            except Exception:
                pass
            # reopen the login box to lock the UI again
            try:
                self.show_login_box()
            except Exception:
                pass

        def _enable_ui(self, enabled: bool):
            """Enable or disable interactive controls in the main UI."""
            state = 'normal' if enabled else 'disabled'
            for entry in getattr(self, 'add_buttons', []):
                try:
                    if isinstance(entry, tuple):
                        widget, cb, children = entry
                        if enabled:
                            try:
                                widget.bind('<Button-1>', cb)
                                for ch in children:
                                    ch.bind('<Button-1>', cb)
                            except tk.TclError:
                                pass
                        else:
                            try:
                                widget.unbind('<Button-1>')
                                for ch in children:
                                    ch.unbind('<Button-1>')
                            except tk.TclError:
                                pass
                    else:
                        try:
                            entry.state(['!disabled'] if enabled else ['disabled'])
                        except (AttributeError, tk.TclError):
                            try:
                                entry.configure(state=state)
                            except (AttributeError, tk.TclError):
                                pass
                except Exception:
                    pass

            for name in ('remove_btn', 'clear_btn', 'checkout_btn'):
                btn = getattr(self, name, None)
                if btn is None:
                    continue
                try:
                    btn.state(['!disabled'] if enabled else ['disabled'])
                except (AttributeError, tk.TclError):
                    try:
                        btn.configure(state=state)
                    except (AttributeError, tk.TclError):
                        pass

            try:
                if enabled:
                    if hasattr(self, '_bind_mousewheel_fn'):
                        self.canvas.bind('<Enter>', self._bind_mousewheel_fn)
                    if hasattr(self, '_unbind_mousewheel_fn'):
                        self.canvas.bind('<Leave>', self._unbind_mousewheel_fn)
                else:
                    try:
                        self.canvas.unbind('<Enter>')
                    except tk.TclError:
                        pass
                    try:
                        self.canvas.unbind('<Leave>')
                    except tk.TclError:
                        pass
            except Exception:
                pass

        def _add_by_code(self, code, qty=None):
            code = code.upper()
            if code in LOOKUP:
                name, price = LOOKUP[code]
                q = 1
                if qty is not None:
                    try:
                        q = int(qty)
                    except (TypeError, ValueError):
                        q = 1
                else:
                    try:
                        q = int(self.qty_spinbox.get())
                    except (TypeError, ValueError):
                        q = 1
                self._order.add(code, name, price, q)
                self._refresh_tree()

        def _refresh_tree(self):
            for i in self.tree.get_children():
                self.tree.delete(i)
            for it in self._order.items:
                self.tree.insert('', 'end', values=(it['code'], it['name'], it['qty'], format_currency(it['price']), format_currency(it['price']*it['qty'])))

        def _remove_selected(self):
            sel = self.tree.selection()
            if not sel:
                return
            idx = self.tree.index(sel[0])
            self._order.remove_index(idx)
            self._refresh_tree()

        def _clear(self):
            self._order.clear()
            self._refresh_tree()

        def _checkout(self):
            if self._order.is_empty():
                messagebox.showinfo('Checkout', 'Cart is empty')
                return
            total = self._order.subtotal()
            paid = simpledialog.askfloat('Paid', f'Total: {format_currency(total)}\nEnter amount paid:')
            if paid is None:
                return
            change = paid - total
            # capture items before clearing the order so we can store them in DB
            items = list(self._order.as_lines())
            fname = save_receipt(self._order, paid, change, self._employee_name)
            # try saving into DB (best-effort). save_order will also update sales aggregates.
            try:
                if HAS_DATABASE and database:
                    try:
                        database.save_order(items, total, paid, change, self._employee_name, os.path.basename(fname))
                    except Exception:
                        # fallback: try the older save_receipt-style saver which doesn't store filename/employee
                        try:
                            database.save_receipt(items, total, paid, change)
                        except Exception:
                            pass
            except Exception:
                # non-fatal; keep UI flow even if DB save fails
                pass

            messagebox.showinfo('Receipt saved', f'Receipt saved to {fname}\nChange: {format_currency(change)}')
            self._order.clear()
            self._refresh_tree()

    def launch_gui_with_login():
        app = CashierGUI()
        try:
            app.show_login_box()
        except tk.TclError:
            pass
        app.mainloop()

else:
    def launch_gui_with_login():
        print('Tkinter not available; use --cli')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cli', action='store_true', help='Run CLI instead of GUI')
    args = parser.parse_args()
    if args.cli or not _has_tkinter():
        employee_name = cli_login()
        # use HEADER_NAME in CLI banner
        print(f'{HEADER_NAME} - starting in CLI mode')
        cli_main(employee_name)
    else:
        launch_gui_with_login()

if __name__ == '__main__':
    main()