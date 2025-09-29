from kivy.config import Config

Config.set('graphics', 'width', '360')
Config.set('graphics', 'height', '640')
Config.set('input', 'mouse', 'mouse,multitouch_on_demand')

from kivy.clock import Clock

Clock.max_iteration = 20

from kivy.lang import Builder
from kivy.uix.popup import Popup
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.spinner import Spinner
from kivy.metrics import dp
from kivy.core.window import Window
from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivy.uix.screenmanager import ScreenManager
from kivymd.uix.card import MDCard
from kivymd.uix.toolbar import MDToolbar
from kivymd.uix.dialog import MDDialog
from kivymd.uix.button import MDFlatButton, MDRaisedButton
from kivymd.uix.label import MDLabel

from datetime import datetime
import sqlite3
import os
import traceback
import uuid


from kivy.clock import Clock

# --------------------------
# UUID and timestamp helpers
# --------------------------
def generate_id():
    return str(uuid.uuid4())


def get_current_timestamp():
    return datetime.now().isoformat()


# --------------------------
# Database helpers / schema
# --------------------------
def get_app_dir():
    try:
        base = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        base = os.getcwd()
    data_dir = os.path.join(base, "data")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


DB_PATH = os.path.join(get_app_dir(), "utracker.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Customers table with sync fields
    c.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            display_name TEXT NOT NULL,
            phone_number TEXT,
            balance REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            sync_status TEXT DEFAULT 'pending',
            firebase_id TEXT
        )
    ''')

    # Transactions table with sync fields
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            action TEXT NOT NULL,
            product TEXT,
            quantity INTEGER NOT NULL DEFAULT 0,
            amount REAL NOT NULL,
            actual_borrower TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            sync_status TEXT DEFAULT 'pending',
            firebase_id TEXT,
            FOREIGN KEY (customer_id) REFERENCES customers (id)
        )
    ''')

    c.execute('CREATE INDEX IF NOT EXISTS idx_customer_name ON customers (name)')

    # Create sync indexes separately to ensure tables exist first
    try:
        c.execute('CREATE INDEX IF NOT EXISTS idx_sync_status ON customers (sync_status)')
    except:
        pass  # Index might fail if table doesn't exist yet, will be created in migration

    try:
        c.execute('CREATE INDEX IF NOT EXISTS idx_tx_sync_status ON transactions (sync_status)')
    except:
        pass  # Index might fail if table doesn't exist yet, will be created in migration

    conn.commit()
    conn.close()


def migrate_database():
    """Migrate existing database to new schema"""
    conn = get_connection()
    c = conn.cursor()

    # Check if migration is needed by looking for old integer ID column
    c.execute("PRAGMA table_info(customers)")
    columns = [col[1] for col in c.fetchall()]

    # Check if this is the old schema (has integer ID)
    has_integer_id = any(
        col[1] == 'id' and col[2] == 'INTEGER' for col in c.execute("PRAGMA table_info(customers)").fetchall())

    if has_integer_id:
        print("Migrating database to new schema...")
        # Backup old tables
        c.execute("ALTER TABLE customers RENAME TO customers_old")
        c.execute("ALTER TABLE transactions RENAME TO transactions_old")

        # Re-create new tables with proper schema
        c.execute('''
            CREATE TABLE IF NOT EXISTS customers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                display_name TEXT NOT NULL,
                phone_number TEXT,
                balance REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                sync_status TEXT DEFAULT 'pending',
                firebase_id TEXT
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                action TEXT NOT NULL,
                product TEXT,
                quantity INTEGER NOT NULL DEFAULT 0,
                amount REAL NOT NULL,
                actual_borrower TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                sync_status TEXT DEFAULT 'pending',
                firebase_id TEXT,
                FOREIGN KEY (customer_id) REFERENCES customers (id)
            )
        ''')

        # Migrate customers
        c.execute('SELECT id, name, display_name, phone_number, balance FROM customers_old')
        old_customers = c.fetchall()

        for old_id, name, display_name, phone_number, balance in old_customers:
            new_id = generate_id()
            now = get_current_timestamp()
            c.execute('''INSERT INTO customers 
                        (id, name, display_name, phone_number, balance, created_at, updated_at, sync_status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                      (new_id, name, display_name, phone_number, balance, now, now, 'synced'))

            # Update transactions with new customer ID
            c.execute('UPDATE transactions_old SET customer_id = ? WHERE customer_id = ?', (new_id, old_id))

        # Migrate transactions
        c.execute(
            'SELECT id, customer_id, date, time, action, product, quantity, amount, actual_borrower FROM transactions_old')
        old_transactions = c.fetchall()

        for old_id, customer_id, date, time, action, product, quantity, amount, actual_borrower in old_transactions:
            new_id = generate_id()
            now = get_current_timestamp()
            c.execute('''INSERT INTO transactions
                        (id, customer_id, date, time, action, product, quantity, amount, actual_borrower, created_at, updated_at, sync_status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                      (new_id, customer_id, date, time, action, product, quantity, amount, actual_borrower, now, now,
                       'synced'))

        # Create indexes after migration
        c.execute('CREATE INDEX IF NOT EXISTS idx_customer_name ON customers (name)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_sync_status ON customers (sync_status)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_tx_sync_status ON transactions (sync_status)')

        # Drop old tables
        c.execute("DROP TABLE customers_old")
        c.execute("DROP TABLE transactions_old")

        conn.commit()
        print("Database migrated successfully")
    else:
        print("Database already uses new schema")

    conn.close()


def get_connection():
    return sqlite3.connect(DB_PATH)


# FIXED: Helper function to recalculate balance from scratch
def recalculate_customer_balance(customer_id):
    """Recalculate customer balance from all transactions"""
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT action, amount FROM transactions WHERE customer_id = ?', (customer_id,))
    rows = c.fetchall()

    balance = 0
    for action, amount in rows:
        if action == "Add Credit":
            balance += amount
        elif action == "Record Payment":
            balance -= amount

    # Update customer with timestamp
    now = get_current_timestamp()
    c.execute('UPDATE customers SET balance = ?, updated_at = ?, sync_status = ? WHERE id = ?',
              (balance, now, 'pending', customer_id))
    conn.commit()
    conn.close()
    return balance


# --------------------------
# DB operations matching desktop logic
# --------------------------
def get_customers(search_term=None):
    conn = get_connection()
    c = conn.cursor()
    if search_term:
        like = f'%{search_term.lower()}%'
        c.execute('''SELECT id, display_name, balance FROM customers 
                     WHERE (name LIKE ? OR display_name LIKE ?) AND balance >= 0 ORDER BY display_name''',
                  (like, like))
    else:
        c.execute('SELECT id, display_name, balance FROM customers WHERE balance >= 0 ORDER BY display_name')
    rows = c.fetchall()
    conn.close()
    return rows


def get_customer_by_name_or_create(name):
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT id, display_name FROM customers WHERE name = ?', (name.lower(),))
    r = c.fetchone()
    if r:
        conn.close()
        return r[0], r[1]

    # Create new customer with UUID and timestamps
    customer_id = generate_id()
    now = get_current_timestamp()
    c.execute('''INSERT INTO customers 
                (id, name, display_name, balance, created_at, updated_at, sync_status) 
                VALUES (?, ?, ?, 0, ?, ?, ?)''',
              (customer_id, name.lower(), name, now, now, 'pending'))
    conn.commit()
    conn.close()
    return customer_id, name


def get_latest_transaction_datetime(customer_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT date, time FROM transactions WHERE customer_id = ? ORDER BY date DESC, time DESC LIMIT 1',
              (customer_id,))
    r = c.fetchone()
    conn.close()
    if r:
        try:
            dt = datetime.strptime(f"{r[0]} {r[1]}", "%Y-%m-%d %H:%M")
            return dt.strftime("%Y-%m-%d %I:%M %p")
        except:
            return f"{r[0]} {r[1]}"
    return "N/A"


def add_credit_db(account_name, actual_borrower, product, quantity, unit_amount):
    if not account_name:
        raise ValueError("Account name cannot be empty.")
    if not product:
        raise ValueError("Product cannot be empty.")
    try:
        quantity = int(quantity)
        if quantity < 1:
            raise ValueError("Quantity must be 1 or more for adding credit.")
    except ValueError:
        raise ValueError("Quantity must be an integer >= 1.")
    try:
        unit_amount = float(unit_amount)
        if unit_amount < 0:
            raise ValueError("Amount cannot be negative.")
    except ValueError:
        raise ValueError("Amount must be a positive number.")
    total_amount = unit_amount * quantity

    conn = get_connection()
    c = conn.cursor()
    cid, display_name = get_customer_by_name_or_create(account_name)
    now_date = datetime.now().strftime("%Y-%m-%d")
    now_time = datetime.now().strftime("%H:%M")
    now_iso = get_current_timestamp()

    borrower_to_store = actual_borrower if actual_borrower and actual_borrower != display_name else None

    # Generate transaction ID and add timestamps
    tx_id = generate_id()
    c.execute('''INSERT INTO transactions 
                 (id, customer_id, date, time, action, product, quantity, amount, actual_borrower, created_at, updated_at, sync_status) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (tx_id, cid, now_date, now_time, "Add Credit", product, quantity, total_amount,
               borrower_to_store, now_iso, now_iso, 'pending'))
    conn.commit()
    conn.close()

    # FIXED: Recalculate balance from scratch
    recalculate_customer_balance(cid)


def record_payment_db(account_name, amount):
    if not account_name:
        raise ValueError("Account name cannot be empty.")
    try:
        amount = float(amount)
        if amount < 0:
            raise ValueError("Payment amount cannot be negative.")
    except ValueError:
        raise ValueError("Amount must be a positive number.")

    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT id, display_name, balance FROM customers WHERE name = ?', (account_name.lower(),))
    r = c.fetchone()
    if not r:
        conn.close()
        raise ValueError("Customer not found.")
    customer_id, display_name, current_balance = r

    # Check if payment would result in negative balance
    if current_balance < amount:
        conn.close()
        raise ValueError(f"Payment amount (₱{amount:.2f}) exceeds current balance (₱{current_balance:.2f})")

    now_date = datetime.now().strftime("%Y-%m-%d")
    now_time = datetime.now().strftime("%H:%M")
    now_iso = get_current_timestamp()

    # Generate transaction ID
    tx_id = generate_id()
    c.execute('''INSERT INTO transactions (id, customer_id, date, time, action, product, quantity, amount, created_at, updated_at, sync_status) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (tx_id, customer_id, now_date, now_time, "Record Payment", "N/A", 0, amount, now_iso, now_iso, 'pending'))
    conn.commit()
    conn.close()

    # FIXED: Recalculate balance from scratch
    new_balance = recalculate_customer_balance(customer_id)
    return customer_id, display_name, new_balance


def get_transactions_db(customer_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''SELECT id, date, time, action, product, quantity, amount, actual_borrower
                 FROM transactions WHERE customer_id = ? ORDER BY datetime(date || ' ' || time) ASC''',
              (customer_id,))
    rows = c.fetchall()
    conn.close()
    return rows


def update_customer_name_phone_db(customer_id, new_name=None, new_phone=None):
    conn = get_connection()
    c = conn.cursor()
    now = get_current_timestamp()
    if new_name:
        c.execute('UPDATE customers SET display_name = ?, name = ?, updated_at = ?, sync_status = ? WHERE id = ?',
                  (new_name, new_name.lower(), now, 'pending', customer_id))
    if new_phone is not None:
        c.execute('UPDATE customers SET phone_number = ?, updated_at = ?, sync_status = ? WHERE id = ?',
                  (new_phone if new_phone else None, now, 'pending', customer_id))
    conn.commit()
    conn.close()


def get_customer_db(customer_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT id, display_name, phone_number, balance FROM customers WHERE id = ?', (customer_id,))
    r = c.fetchone()
    conn.close()
    return r


# FIXED: Completely rewritten update_transaction_db function
def update_transaction_db(transaction_id, updated_date, updated_time, updated_action,
                          updated_product, updated_quantity, updated_amount, updated_borrower):
    if updated_amount < 0:
        raise ValueError("Amount cannot be negative.")

    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT customer_id FROM transactions WHERE id = ?', (transaction_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise ValueError("Transaction not found.")
    customer_id = row[0]

    # Update the transaction with timestamp
    now = get_current_timestamp()
    c.execute('''UPDATE transactions SET date=?, time=?, action=?, product=?, quantity=?, amount=?, actual_borrower=?, updated_at=?, sync_status=?
                 WHERE id=?''',
              (updated_date, updated_time, updated_action, updated_product, updated_quantity, updated_amount,
               updated_borrower if updated_borrower else None, now, 'pending', transaction_id))
    conn.commit()
    conn.close()

    # FIXED: Recalculate balance from scratch instead of trying to adjust
    new_balance = recalculate_customer_balance(customer_id)
    return customer_id, new_balance


def delete_transaction_db(transaction_id):
    conn = get_connection()
    c = conn.cursor()

    # Find the customer linked to this transaction
    c.execute('SELECT customer_id, action, amount FROM transactions WHERE id = ?', (transaction_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise ValueError("Transaction not found.")
    customer_id, action, amount = row

    # Delete the transaction
    c.execute('DELETE FROM transactions WHERE id = ?', (transaction_id,))

    # Count remaining transactions
    c.execute('SELECT COUNT(*) FROM transactions WHERE customer_id = ?', (customer_id,))
    tx_count = c.fetchone()[0]

    conn.commit()
    conn.close()

    # FIXED: Recalculate balance from scratch
    new_balance = recalculate_customer_balance(customer_id)
    return customer_id, tx_count, new_balance, action, amount


def mark_customer_removed_db(customer_id):
    conn = get_connection()
    c = conn.cursor()
    now = get_current_timestamp()
    c.execute('UPDATE customers SET balance = -1, updated_at = ?, sync_status = ? WHERE id = ?',
              (now, 'pending', customer_id))
    conn.commit()
    conn.close()


# --------------------------
# UI helper popups (Kivy Popup for complex forms; MDDialog for simple messages)
# --------------------------
def show_message(title, message):
    dlg = MDDialog(title=title, text=message, buttons=[MDFlatButton(text="OK", on_release=lambda x: dlg.dismiss())])
    dlg.open()


def confirm_action(title, message, on_confirm):
    content = BoxLayout(orientation='vertical', spacing=10, padding=8)
    content.add_widget(Label(text=message))
    btns = BoxLayout(size_hint=(1, None), height=dp(40), spacing=10)
    yes = Button(text='Yes')
    no = Button(text='No')
    btns.add_widget(yes)
    btns.add_widget(no)
    content.add_widget(btns)
    popup = Popup(title=title, content=content, size_hint=(0.9, 0.4))

    def do_yes(*_):
        popup.dismiss()
        on_confirm()

    yes.bind(on_release=do_yes)
    no.bind(on_release=lambda *_: popup.dismiss())
    popup.open()


# --------------------------
# UI components (cards / rows)
# --------------------------
class CustomerCard(MDCard):
    def __init__(self, cid, name, balance, last_tx, open_history_cb, **kwargs):
        super().__init__(**kwargs)
        self.size_hint_y = None
        self.height = dp(90)
        self.padding = dp(12)
        self.spacing = dp(8)
        self.orientation = 'vertical'
        self.customer_id = cid
        self.elevation = 2

        # Create main content with proper size hints
        main_content = BoxLayout(orientation='vertical', spacing=dp(4))

        # Top row: name and balance
        top = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(24))
        name_label = MDLabel(text=f"[b]{name}[/b]", markup=True, size_hint_x=0.7)
        name_label.theme_text_color = "Primary"
        top.add_widget(name_label)

        balance_color = 'Primary' if balance >= 0 else 'Error'
        balance_label = MDLabel(text=f"₱{balance:.2f}", halign='right', size_hint_x=0.3, theme_text_color=balance_color)
        top.add_widget(balance_label)
        main_content.add_widget(top)

        # Bottom row: last transaction + open button
        bottom = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(36), spacing=dp(8))
        last_tx_label = MDLabel(text=f"{last_tx}", theme_text_color='Hint', size_hint_x=0.65)
        bottom.add_widget(last_tx_label)

        # Use regular Button instead of MDRaisedButton to avoid layout issues
        open_btn = Button(text='Open', size_hint=(None, None), size=(dp(70), dp(32)))
        open_btn.bind(on_release=lambda *_: open_history_cb(cid))
        bottom.add_widget(open_btn)
        main_content.add_widget(bottom)

        self.add_widget(main_content)


class TransactionRow(BoxLayout):
    def __init__(self, tx, edit_cb, delete_cb, **kwargs):
        super().__init__(orientation='horizontal', size_hint_y=None, height=dp(70), spacing=dp(8), **kwargs)
        self.tx = tx
        tx_id, date, time, action, product, quantity, amount, actual_borrower = tx

        # Left side - transaction info
        left = BoxLayout(orientation='vertical', size_hint_x=0.6, spacing=dp(2))
        date_label = MDLabel(text=f"{date} {time}", theme_text_color='Hint', font_style='Caption')
        date_label.size_hint_y = None
        date_label.height = dp(20)
        left.add_widget(date_label)

        desc = f"{action} • {product}"
        borrower_display = actual_borrower if actual_borrower else ""
        if borrower_display:
            desc += f" • {borrower_display}"
        desc_label = MDLabel(text=desc, font_style='Body2')
        desc_label.size_hint_y = None
        desc_label.height = dp(24)
        left.add_widget(desc_label)
        self.add_widget(left)

        # Right side - amount and buttons
        right = BoxLayout(orientation='vertical', size_hint_x=0.4, spacing=dp(4))
        amount_color = 'Primary' if amount >= 0 else 'Error'
        amount_label = MDLabel(text=f"₱{amount:.2f}", halign='right', theme_text_color=amount_color)
        amount_label.size_hint_y = None
        amount_label.height = dp(24)
        right.add_widget(amount_label)

        # Use regular buttons to avoid layout loops
        btns = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(4))
        edit = Button(text='Edit', size_hint_x=0.5)
        delete = Button(text='Delete', size_hint_x=0.5)
        btns.add_widget(edit)
        btns.add_widget(delete)
        right.add_widget(btns)
        self.add_widget(right)

        edit.bind(on_release=lambda *_: edit_cb(tx_id))
        delete.bind(on_release=lambda *_: delete_cb(tx_id))


# --------------------------
# Screens
# --------------------------
KV = """
<MainScreenManager>:
    LoginScreen:
    DashboardScreen:
    HistoryScreen:

<LoginScreen>:
    name: 'login'
    BoxLayout:
        orientation: 'vertical'
        padding: dp(16)
        spacing: dp(12)

        MDLabel:
            text: 'UTracker Login'
            halign: 'center'
            font_style: 'H5'

        TextInput:
            id: username
            hint_text: 'Username'
            multiline: False
            size_hint_y: None
            height: dp(44)

        TextInput:
            id: password
            hint_text: 'Password'
            password: True
            multiline: False
            size_hint_y: None
            height: dp(44)

        BoxLayout:
            size_hint_y: None
            height: dp(48)
            spacing: dp(8)
            Button:
                text: 'Login'
                on_release: app.do_login(username.text, password.text)

<DashboardScreen>:
    name: 'dashboard'
    BoxLayout:
        orientation: 'vertical'

        MDToolbar:
            title: 'UTracker'
            elevation: 10
            right_action_items: [['cloud-sync', lambda x: app.manual_sync()]]
        
        BoxLayout:
            size_hint_y: None
            height: dp(56)
            padding: dp(8)
            TextInput:
                id: search_input
                hint_text: 'Search name...'
                multiline: False
                on_text: app.load_customers(self.text)

        ScrollView:
            id: scroll_customers
            GridLayout:
                id: customers_grid
                cols: 1
                spacing: dp(8)
                size_hint_y: None
                height: self.minimum_height
                padding: dp(8)

        BoxLayout:
            orientation: 'vertical'
            padding: dp(8)
            spacing: dp(8)
            size_hint_y: None
            height: dp(300)

            TextInput:
                id: account_name
                hint_text: 'Account Name'
                multiline: False
                size_hint_y: None
                height: dp(44)

            TextInput:
                id: actual_borrower
                hint_text: 'Actual Borrower (optional)'
                multiline: False
                size_hint_y: None
                height: dp(44)

            TextInput:
                id: product
                hint_text: 'Product'
                multiline: False
                size_hint_y: None
                height: dp(44)

            BoxLayout:
                size_hint_y: None
                height: dp(44)
                spacing: dp(8)
                TextInput:
                    id: quantity
                    hint_text: 'Quantity'
                    text: '1'
                    multiline: False
                    input_filter: 'int'
                TextInput:
                    id: amount
                    hint_text: 'Amount (₱)'
                    text: ''
                    multiline: False
                    input_filter: 'float'

            BoxLayout:
                size_hint_y: None
                height: dp(48)
                spacing: dp(8)
                Button:
                    text: 'Add Credit'
                    on_release: app.handle_add_credit()
                Button:
                    text: 'Record Payment'
                    on_release: app.handle_record_payment()
                Button:
                    text: 'Clear'
                    on_release: app.clear_form()

<HistoryScreen>:
    name: 'history'
    BoxLayout:
        orientation: 'vertical'

        MDToolbar:
            id: history_toolbar
            title: 'Transaction History'
            elevation: 10

        BoxLayout:
            orientation: 'horizontal'
            size_hint_y: None
            height: dp(44)
            padding: dp(8)
            spacing: dp(8)
            TextInput:
                id: cust_name_input
                multiline: False
                hint_text: 'Account Name'
            Button:
                text: 'Update Name'
                size_hint_x: None
                width: dp(120)
                on_release: app.update_customer_name()
        BoxLayout:
            orientation: 'horizontal'
            size_hint_y: None
            height: dp(44)
            padding: dp(8)
            spacing: dp(8)
            TextInput:
                id: cust_phone_input
                multiline: False
                hint_text: 'Phone (optional)'
            Button:
                text: 'Update Phone'
                size_hint_x: None
                width: dp(120)
                on_release: app.update_customer_phone()

        ScrollView:
            GridLayout:
                id: tx_grid
                cols: 1
                spacing: dp(6)
                size_hint_y: None
                height: self.minimum_height
                padding: dp(8)

        BoxLayout:
            size_hint_y: None
            height: dp(44)
            padding: dp(8)
            Button:
                text: 'Back'
                on_release: app.go_back_to_dashboard()
"""


class MainScreenManager(ScreenManager):
    pass


class LoginScreen(MDScreen):
    pass


class DashboardScreen(MDScreen):
    pass


class HistoryScreen(MDScreen):
    pass


# --------------------------
# App
# --------------------------
class UTrackerApp(MDApp):
    def build(self):
        init_db()
        migrate_database()  # Add migration here
        Window.clearcolor = (1, 0.973, 0.863, 1)  # soft cream
        self.theme_cls.theme_style = "Light"
        self.theme_cls.primary_palette = "Amber"
        Builder.load_string(KV)
        self.sm = MainScreenManager()
        self.current_customer_id = None  # used by history screen
        return self.sm

    # ---------- Login ----------
    def do_login(self, username, password):
        if username.strip() == 'admin' and password.strip() == 'admin':
            self.sm.current = 'dashboard'
            self.load_customers()
        else:
            show_message("Login Failed", "Invalid username or password")

    # ---------- Dashboard helpers ----------
    def load_customers(self, search_text=""):
        try:
            screen = self.sm.get_screen('dashboard')
            grid = screen.ids.customers_grid
            grid.clear_widgets()
            rows = get_customers(search_text.strip() if search_text else None)
            if not rows:
                lbl = MDLabel(text='(no customers)', halign='center')
                grid.add_widget(lbl)
                return
            for cid, display_name, balance in rows:
                last_tx = get_latest_transaction_datetime(cid)
                card = CustomerCard(cid, display_name, balance, last_tx, self.open_history)
                grid.add_widget(card)
        except Exception as e:
            traceback.print_exc()
            show_message("Error", str(e))

    def clear_form(self):
        screen = self.sm.get_screen('dashboard')
        screen.ids.account_name.text = ''
        screen.ids.actual_borrower.text = ''
        screen.ids.product.text = ''
        screen.ids.quantity.text = '1'
        screen.ids.amount.text = ''
        screen.ids.search_input.text = ''

    def handle_add_credit(self):
        screen = self.sm.get_screen('dashboard')
        account = screen.ids.account_name.text.strip()
        borrower = screen.ids.actual_borrower.text.strip()
        product = screen.ids.product.text.strip()
        quantity = screen.ids.quantity.text.strip()
        amount = screen.ids.amount.text.strip()
        try:
            add_credit_db(account, borrower, product, quantity, amount)
            show_message("Success", "Credit added.")
            self.clear_form()
            self.load_customers()
        except Exception as e:
            traceback.print_exc()
            show_message("Error", str(e))

    def handle_record_payment(self):
        screen = self.sm.get_screen('dashboard')
        account = screen.ids.account_name.text.strip()
        amount = screen.ids.amount.text.strip()
        try:
            cid, name, new_bal = record_payment_db(account, amount)
            show_message("Payment Recorded", f"{name}'s new balance: ₱{new_bal:.2f}")
            self.clear_form()
            self.load_customers()
            if new_bal <= 0:
                def do_remove():
                    mark_customer_removed_db(cid)
                    self.load_customers()

                confirm_action("Balance Cleared", f"{name}'s balance is now ₱{new_bal:.2f}. Remove from list?",
                               do_remove)
        except Exception as e:
            traceback.print_exc()
            show_message("Error", str(e))

    # ---------- History screen ----------
    def open_history(self, customer_id):
        # open history screen and populate
        self.current_customer_id = customer_id
        data = get_customer_db(customer_id)
        if not data:
            show_message("Error", "Customer not found.")
            return
        cid, display_name, phone, balance = data
        screen = self.sm.get_screen('history')
        screen.ids.history_toolbar.title = f"History — {display_name} (₱{balance:.2f})"
        screen.ids.cust_name_input.text = display_name
        screen.ids.cust_phone_input.text = phone if phone else ''
        # load transactions list
        self.refresh_transactions()
        self.sm.current = 'history'

    def refresh_transactions(self):
        screen = self.sm.get_screen('history')
        grid = screen.ids.tx_grid
        grid.clear_widgets()
        try:
            txs = get_transactions_db(self.current_customer_id)
            if not txs:
                grid.add_widget(MDLabel(text="(no transactions)", halign='center'))
                return
            for tx in txs:
                # tx tuple: id, date, time, action, product, quantity, amount, actual_borrower
                row = TransactionRow(tx, edit_cb=self.open_edit_transaction_popup,
                                     delete_cb=self.confirm_delete_transaction)
                grid.add_widget(row)
        except Exception as e:
            traceback.print_exc()
            show_message("Error", str(e))

    def go_back_to_dashboard(self):
        self.current_customer_id = None
        self.sm.current = 'dashboard'
        self.load_customers()

    # ---------- Update name / phone ----------
    def update_customer_name(self):
        screen = self.sm.get_screen('history')
        new_name = screen.ids.cust_name_input.text.strip()
        if not new_name:
            show_message("Error", "Customer name cannot be empty.")
            return
        try:
            update_customer_name_phone_db(self.current_customer_id, new_name=new_name)
            show_message("Updated", "Customer name updated.")
            # refresh
            self.open_history(self.current_customer_id)
            self.load_customers()
        except Exception as e:
            traceback.print_exc()
            show_message("Error", str(e))

    def update_customer_phone(self):
        screen = self.sm.get_screen('history')
        new_phone = screen.ids.cust_phone_input.text.strip()
        try:
            update_customer_name_phone_db(self.current_customer_id, new_phone=new_phone)
            show_message("Updated", "Phone number updated.")
            self.open_history(self.current_customer_id)
        except Exception as e:
            traceback.print_exc()
            show_message("Error", str(e))

    # ---------- Edit transaction ----------
    def open_edit_transaction_popup(self, tx_id):
        # fetch transaction
        conn = get_connection()
        c = conn.cursor()
        c.execute(
            'SELECT id, customer_id, date, time, action, product, quantity, amount, actual_borrower '
            'FROM transactions WHERE id = ?', (tx_id,))
        r = c.fetchone()
        conn.close()
        if not r:
            show_message("Error", "Transaction not found.")
            return

        (tid, cid, date, time, action, product, quantity, amount, actual_borrower) = r

        # Build popup content
        content = BoxLayout(orientation='vertical', spacing=8, padding=8)

        # Date & Time
        dt_row = BoxLayout(orientation='horizontal', spacing=8, size_hint_y=None, height=dp(40))
        date_input = TextInput(text=date, multiline=False)
        time_input = TextInput(text=time, multiline=False)
        dt_row.add_widget(date_input)
        dt_row.add_widget(time_input)
        content.add_widget(Label(text="Date (YYYY-MM-DD) and Time (HH:MM)"))
        content.add_widget(dt_row)

        # Action dropdown (Spinner)
        content.add_widget(Label(text="Action"))
        action_spinner = Spinner(
            text=action,
            values=("Add Credit", "Record Payment"),
            size_hint=(1, None),
            height=dp(40)
        )
        content.add_widget(action_spinner)

        # Product
        content.add_widget(Label(text="Product"))
        product_input = TextInput(text=product if product else '', multiline=False)
        content.add_widget(product_input)

        # Quantity
        content.add_widget(Label(text="Quantity"))
        quantity_input = TextInput(text=str(quantity), multiline=False, input_filter='int')
        content.add_widget(quantity_input)

        # Amount (always show what's stored in DB)
        amount_input = TextInput(text=str(amount), multiline=False, input_filter='float')
        content.add_widget(Label(text="Amount"))
        content.add_widget(amount_input)

        # Borrower
        content.add_widget(Label(text="Actual Borrower (optional)"))
        borrower_input = TextInput(text=actual_borrower if actual_borrower else '', multiline=False)
        content.add_widget(borrower_input)

        # Buttons
        btns = BoxLayout(size_hint_y=None, height=dp(48), spacing=8)
        save_btn = Button(text="Save")
        cancel_btn = Button(text="Cancel")
        btns.add_widget(save_btn)
        btns.add_widget(cancel_btn)
        content.add_widget(btns)

        popup = Popup(title="Edit Transaction", content=content, size_hint=(0.95, 0.9))
        cancel_btn.bind(on_release=popup.dismiss)

        def do_save(*_):
            ds = date_input.text.strip()
            ts = time_input.text.strip()

            # validate date/time
            try:
                datetime.strptime(ds, "%Y-%m-%d")
            except:
                show_message("Input Error", "Invalid date format. Use YYYY-MM-DD.")
                return
            try:
                datetime.strptime(ts, "%H:%M")
            except:
                show_message("Input Error", "Invalid time format. Use HH:MM.")
                return

            up_action = action_spinner.text.strip()
            up_product = product_input.text.strip()

            try:
                up_qty = int(quantity_input.text.strip())
                if up_qty < 0:
                    show_message("Input Error", "Quantity cannot be negative.")
                    return
            except:
                show_message("Input Error", "Quantity must be a number.")
                return

            try:
                if up_action == "Add Credit":
                    unit = float(amount_input.text.strip())
                    if unit < 0:
                        show_message("Input Error", "Amount cannot be negative.")
                        return
                    up_amount = unit * up_qty
                else:
                    up_amount = float(amount_input.text.strip())
                    if up_amount < 0:
                        show_message("Input Error", "Amount cannot be negative.")
                        return
            except:
                show_message("Input Error", "Amount must be a number.")
                return

            up_borrower = borrower_input.text.strip() if borrower_input.text.strip() else None

            # FIXED: Additional validation for payment amounts
            if up_action == "Record Payment":
                # Get current customer balance and check if this edit would cause issues
                conn = get_connection()
                c = conn.cursor()
                c.execute('SELECT balance FROM customers WHERE id = ?', (cid,))
                current_balance = c.fetchone()[0]
                conn.close()

                # Calculate what balance would be after removing original transaction
                if action == "Add Credit":
                    temp_balance = current_balance - amount  # Remove the credit
                elif action == "Record Payment":
                    temp_balance = current_balance + amount  # Add back the payment
                else:
                    temp_balance = current_balance

                # Check if new payment would cause negative balance
                if temp_balance < up_amount:
                    show_message("Input Error",
                                 f"Payment amount (₱{up_amount:.2f}) would exceed available balance (₱{temp_balance:.2f})")
                    return

            try:
                customer_id, new_balance = update_transaction_db(
                    tid, ds, ts, up_action, up_product, up_qty, up_amount, up_borrower)
                popup.dismiss()
                show_message("Saved", f"Transaction updated. New balance: ₱{new_balance:.2f}")
                # refresh UI
                self.load_customers()
                if self.current_customer_id == customer_id:
                    self.open_history(customer_id)
            except Exception as e:
                traceback.print_exc()
                show_message("Error", str(e))

        save_btn.bind(on_release=do_save)
        popup.open()

    # ---------- Delete transaction ----------
    def confirm_delete_transaction(self, tx_id):
        def do_delete():
            try:
                customer_id, tx_count, new_balance, action, amount = delete_transaction_db(tx_id)
                show_message("Deleted",
                             f"Deleted {action} transaction for ₱{amount:.2f}. New balance: ₱{new_balance:.2f}")
                if tx_count == 0 or new_balance <= 0:
                    def do_remove():
                        mark_customer_removed_db(customer_id)
                        self.load_customers()
                        if self.sm.current == 'history':
                            self.sm.current = 'dashboard'

                    msg = "No transactions left." if tx_count == 0 else "Balance cleared."
                    confirm_action("Customer Status", f"{msg} Remove customer from list?", do_remove)
                self.load_customers()
                if self.current_customer_id == customer_id:
                    self.open_history(customer_id)
            except Exception as e:
                traceback.print_exc()
                show_message("Error", str(e))

        confirm_action("Confirm Deletion", "Are you sure you want to delete this transaction?", do_delete)

    def on_start(self):
        """Called when app starts - add this method"""
        # Schedule periodic sync every 5 minutes
        Clock.schedule_interval(self.auto_sync, 300)  # 300 seconds = 5 minutes

        # Initial sync after 3 seconds (let app load first)
        Clock.schedule_once(lambda dt: self.auto_sync(), 3)

    def auto_sync(self, dt=None):
        """Automatically sync data - add this method"""
        try:
            from sync_service import sync_service
            if sync_service.is_connected():
                print("Auto-syncing data...")
                success = sync_service.sync_all_data()
                if success:
                    print("Auto-sync completed")
                    # Optional: Show brief notification
                    # self.show_sync_notification("Synced with cloud")
                else:
                    print("Auto-sync failed")
            else:
                print("Firebase not connected - skipping auto-sync")
        except Exception as e:
            print(f"Auto-sync error: {e}")

    def manual_sync(self):
        """Manual sync triggered by user - add this method"""
        try:
            from sync_service import sync_service
            if sync_service.is_connected():
                show_message("Syncing", "Syncing data with cloud...")
                success = sync_service.sync_all_data()
                if success:
                    show_message("Sync Complete", "Data synchronized successfully!")
                    # Refresh the display
                    self.load_customers()
                else:
                    show_message("Sync Failed", "Failed to sync data")
            else:
                show_message("Sync Error", "Firebase not configured")
        except Exception as e:
            show_message("Sync Error", f"Sync failed: {str(e)}")


    def show_sync_notification(self, message):
        """Show a brief sync status notification"""
        from kivymd.uix.snackbar import Snackbar
        Snackbar(text=message).open()

if __name__ == '__main__':
    UTrackerApp().run()