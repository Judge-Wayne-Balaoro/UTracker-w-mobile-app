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

from datetime import datetime, timedelta
import sqlite3
import os
import traceback
import uuid


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

    # Transactions table with sync fields AND is_deleted flag
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
            is_deleted INTEGER DEFAULT 0,
            FOREIGN KEY (customer_id) REFERENCES customers (id)
        )
    ''')

    c.execute('CREATE INDEX IF NOT EXISTS idx_customer_name ON customers (name)')

    try:
        c.execute('CREATE INDEX IF NOT EXISTS idx_sync_status ON customers (sync_status)')
    except:
        pass

    try:
        c.execute('CREATE INDEX IF NOT EXISTS idx_tx_sync_status ON transactions (sync_status)')
    except:
        pass

    conn.commit()
    conn.close()


def update_schema_if_needed():
    """Adds the is_deleted column to the transactions table if it doesn't exist."""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("PRAGMA table_info(transactions)")
        columns = [col[1] for col in c.fetchall()]
        if 'is_deleted' not in columns:
            print("Updating transactions schema to add 'is_deleted' column...")
            c.execute("ALTER TABLE transactions ADD COLUMN is_deleted INTEGER DEFAULT 0")
            conn.commit()
            print("Schema updated successfully.")
    except Exception as e:
        print(f"Schema update failed: {e}")
    finally:
        conn.close()


def migrate_database():
    """Migrate existing database to new schema"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("PRAGMA table_info(customers)")
    columns = [col[1] for col in c.fetchall()]
    has_integer_id = any(
        col[1] == 'id' and col[2] == 'INTEGER' for col in c.execute("PRAGMA table_info(customers)").fetchall())

    if has_integer_id:
        print("Migrating database to new schema...")
        c.execute("ALTER TABLE customers RENAME TO customers_old")
        c.execute("ALTER TABLE transactions RENAME TO transactions_old")
        init_db()  # Re-create tables with the correct, modern schema

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
        c.execute("DROP TABLE customers_old")
        c.execute("DROP TABLE transactions_old")
        conn.commit()
        print("Database migrated successfully")
    else:
        print("Database already uses new schema")

    conn.close()


def get_connection():
    return sqlite3.connect(DB_PATH)


def recalculate_customer_balance(customer_id):
    """Recalculate customer balance from non-deleted transactions"""
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT action, amount FROM transactions WHERE customer_id = ? AND is_deleted = 0', (customer_id,))
    rows = c.fetchall()

    balance = 0
    for action, amount in rows:
        if action == "Add Credit":
            balance += amount
        elif action == "Paid":  # Changed from "Record Payment" to "Paid"
            balance -= amount
        elif action == "Overdue Penalty":
            balance += amount  # Penalties increase the balance

    now = get_current_timestamp()
    c.execute('UPDATE customers SET balance = ?, updated_at = ?, sync_status = ? WHERE id = ?',
              (balance, now, 'pending', customer_id))
    conn.commit()
    conn.close()
    return balance


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
    c.execute(
        'SELECT date, time FROM transactions WHERE customer_id = ? AND is_deleted = 0 ORDER BY date DESC, time DESC LIMIT 1',
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


def add_credit_db(borrower_name, co_borrower, product, quantity, unit_amount):
    if not borrower_name:
        raise ValueError("Borrower name cannot be empty.")
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
    cid, display_name = get_customer_by_name_or_create(borrower_name)
    now_date = datetime.now().strftime("%Y-%m-%d")
    now_time = datetime.now().strftime("%H:%M")
    now_iso = get_current_timestamp()
    borrower_to_store = co_borrower if co_borrower and co_borrower != display_name else None

    tx_id = generate_id()
    c.execute('''INSERT INTO transactions
                 (id, customer_id, date, time, action, product, quantity, amount, actual_borrower, created_at, updated_at, sync_status, is_deleted)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)''',
              (tx_id, cid, now_date, now_time, "Credit Added", product, quantity, total_amount,
               borrower_to_store, now_iso, now_iso, 'pending'))
    conn.commit()
    conn.close()
    recalculate_customer_balance(cid)


def record_payment_db(borrower_name, amount):
    if not borrower_name:
        raise ValueError("Borrower name cannot be empty.")
    try:
        amount = float(amount)
        if amount < 0:
            raise ValueError("Payment amount cannot be negative.")
    except ValueError:
        raise ValueError("Amount must be a positive number.")

    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT id, display_name, balance FROM customers WHERE name = ?', (borrower_name.lower(),))
    r = c.fetchone()
    if not r:
        conn.close()
        raise ValueError("Customer not found.")
    customer_id, display_name, current_balance = r
    if current_balance < amount:
        conn.close()
        raise ValueError(f"Payment amount (₱{amount:.2f}) exceeds current balance (₱{current_balance:.2f})")

    now_date = datetime.now().strftime("%Y-%m-%d")
    now_time = datetime.now().strftime("%H:%M")
    now_iso = get_current_timestamp()
    tx_id = generate_id()
    c.execute('''INSERT INTO transactions (id, customer_id, date, time, action, product, quantity, amount, created_at, updated_at, sync_status, is_deleted)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)''',
              (tx_id, customer_id, now_date, now_time, "Paid", "N/A", 0, amount, now_iso, now_iso, 'pending'))  # Changed to "Paid"
    conn.commit()
    conn.close()
    new_balance = recalculate_customer_balance(customer_id)
    return customer_id, display_name, new_balance


def get_transactions_db(customer_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''SELECT id, date, time, action, product, quantity, amount, actual_borrower
                 FROM transactions WHERE customer_id = ? AND is_deleted = 0 ORDER BY datetime(date || ' ' || time) ASC''',
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
    now = get_current_timestamp()
    c.execute('''UPDATE transactions SET date=?, time=?, action=?, product=?, quantity=?, amount=?, actual_borrower=?, updated_at=?, sync_status=?
                 WHERE id=?''',
              (updated_date, updated_time, updated_action, updated_product, updated_quantity, updated_amount,
               updated_borrower if updated_borrower else None, now, 'pending', transaction_id))
    conn.commit()
    conn.close()
    new_balance = recalculate_customer_balance(customer_id)
    return customer_id, new_balance


def delete_transaction_db(transaction_id):
    """Soft deletes a transaction by marking it as deleted."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT customer_id, action, amount FROM transactions WHERE id = ?', (transaction_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise ValueError("Transaction not found.")
    customer_id, action, amount = row

    now = get_current_timestamp()
    c.execute('''
        UPDATE transactions
        SET is_deleted = 1, updated_at = ?, sync_status = 'pending'
        WHERE id = ?
    ''', (now, transaction_id))
    conn.commit()
    conn.close()

    new_balance = recalculate_customer_balance(customer_id)
    c = get_connection().cursor()
    c.execute('SELECT COUNT(*) FROM transactions WHERE customer_id = ? AND is_deleted = 0', (customer_id,))
    tx_count = c.fetchone()[0]
    c.connection.close()
    return customer_id, tx_count, new_balance, action, amount


def mark_customer_removed_db(customer_id):
    conn = get_connection()
    c = conn.cursor()
    now = get_current_timestamp()
    c.execute('UPDATE customers SET balance = -1, updated_at = ?, sync_status = ? WHERE id = ?',
              (now, 'pending', customer_id))
    conn.commit()
    conn.close()


def check_for_overdue_accounts():
    """Check for overdue accounts and add penalties - returns list of overdue customers"""
    conn = get_connection()
    c = conn.cursor()
    overdue_customers = []
    penalty_added = False

    try:
        thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
        today = datetime.now().strftime("%Y-%m-%d")

        # Find all customers with a balance > 0
        c.execute("SELECT id, display_name, balance FROM customers WHERE balance > 0")
        customers_with_balance = c.fetchall()

        for customer_id, display_name, balance in customers_with_balance:
            # For each customer, find the date of their oldest credit transaction
            c.execute("""
                SELECT MIN(created_at) FROM transactions 
                WHERE customer_id = ? AND action = 'Add Credit' AND is_deleted = 0
            """, (customer_id,))
            result = c.fetchone()
            oldest_credit_date_str = result[0] if result else None

            # If they have a credit and it's older than 2 hours (for testing)
            if oldest_credit_date_str and oldest_credit_date_str < thirty_days_ago:
                # Check last penalty date
                c.execute("""
                    SELECT MAX(date) FROM transactions 
                    WHERE customer_id = ? AND action = 'Overdue Penalty' AND is_deleted = 0
                """, (customer_id,))
                last_penalty_result = c.fetchone()
                last_penalty_date = last_penalty_result[0] if last_penalty_result[0] else None

                # Add penalty if never penalized or last penalty was more than 30 days ago
                should_add_penalty = True
                penalty_status = "NEW PENALTY"

                if last_penalty_date:
                    try:
                        last_penalty_datetime = datetime.strptime(last_penalty_date, "%Y-%m-%d")
                        days_since_last_penalty = (datetime.now() - last_penalty_datetime).days
                        should_add_penalty = days_since_last_penalty >= 30

                        if not should_add_penalty:
                            penalty_status = f"Last penalty {days_since_last_penalty} days ago"
                    except ValueError:
                        should_add_penalty = True
                        penalty_status = "NEW PENALTY"

                if should_add_penalty:
                    # Add ₱3 penalty
                    penalty_amount = 3.0
                    new_balance = balance + penalty_amount

                    # Update customer balance
                    c.execute(
                        'UPDATE customers SET balance = ?, updated_at = ?, sync_status = ? WHERE id = ?',
                        (new_balance, datetime.now().isoformat(), 'pending', customer_id)
                    )

                    # Create penalty transaction
                    transaction_id = generate_id()
                    now = get_current_timestamp()
                    c.execute(
                        '''INSERT INTO transactions 
                        (id, customer_id, date, time, action, product, quantity, amount, created_at, updated_at, sync_status, is_deleted) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)''',
                        (transaction_id, customer_id,
                         today,
                         datetime.now().strftime("%H:%M"),
                         "Overdue Penalty", "Late Fee", 1, penalty_amount,
                         now, now, 'pending')
                    )

                    overdue_customers.append({
                        'name': display_name,
                        'old_balance': balance,
                        'new_balance': new_balance,
                        'status': penalty_status,
                        'penalty_added': True
                    })
                    penalty_added = True
                else:
                    # Penalty already added recently, but still show as overdue
                    overdue_customers.append({
                        'name': display_name,
                        'old_balance': balance,
                        'new_balance': balance,
                        'status': penalty_status,
                        'penalty_added': False
                    })

        if penalty_added:
            conn.commit()

    except Exception as e:
        conn.rollback()
        print(f"Error checking for overdue accounts: {e}")
        traceback.print_exc()
    finally:
        conn.close()

    return overdue_customers


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

        # Check if customer is overdue
        is_overdue = self.check_if_overdue(cid, balance)

        main_content = BoxLayout(orientation='vertical', spacing=dp(4))
        top = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(24))

        # Add warning emoji for overdue customers
        display_name = f"{name}" if is_overdue else name
        name_label = MDLabel(text=f"[b]{display_name}[/b]", markup=True, size_hint_x=0.7)
        name_label.theme_text_color = "Primary"
        top.add_widget(name_label)

        balance_color = 'Primary' if balance >= 0 else 'Error'
        balance_label = MDLabel(text=f"₱{balance:.2f}", halign='right', size_hint_x=0.3, theme_text_color=balance_color)
        top.add_widget(balance_label)
        main_content.add_widget(top)

        bottom = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(36), spacing=dp(8))
        last_tx_label = MDLabel(text=f"{last_tx}", theme_text_color='Hint', size_hint_x=0.65)
        bottom.add_widget(last_tx_label)
        open_btn = Button(text='Open', size_hint=(None, None), size=(dp(70), dp(32)))
        open_btn.bind(on_release=lambda *_: open_history_cb(cid))
        bottom.add_widget(open_btn)
        main_content.add_widget(bottom)
        self.add_widget(main_content)

    def check_if_overdue(self, customer_id, balance):
        """Check if customer is overdue (balance > 0 and oldest credit > 2 hours)"""
        if balance <= 0:
            return False

        conn = get_connection()
        c = conn.cursor()
        try:
            # Calculate 2 hours ago (for testing - same as desktop)
            thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()

            c.execute("""
                SELECT MIN(created_at) FROM transactions 
                WHERE customer_id = ? AND action = 'Add Credit'
            """, (customer_id,))
            result = c.fetchone()
            oldest_credit_date_str = result[0] if result else None

            return oldest_credit_date_str and oldest_credit_date_str < thirty_days_ago
        except Exception as e:
            print(f"Error checking overdue status: {e}")
            return False
        finally:
            conn.close()


class TransactionRow(BoxLayout):
    def __init__(self, tx, edit_cb, delete_cb, **kwargs):
        super().__init__(orientation='horizontal', size_hint_y=None, height=dp(70), spacing=dp(8), **kwargs)
        self.tx = tx
        tx_id, date, time, action, product, quantity, amount, actual_borrower = tx
        left = BoxLayout(orientation='vertical', size_hint_x=0.6, spacing=dp(2))
        date_label = MDLabel(text=f"{date} {time}", theme_text_color='Hint', font_style='Caption')
        date_label.size_hint_y = None
        date_label.height = dp(20)
        left.add_widget(date_label)
        desc = f"{action} • {product}"
        co_borrower_display = actual_borrower if actual_borrower else ""
        if co_borrower_display:
            desc += f" • {co_borrower_display}"
        desc_label = MDLabel(text=desc, font_style='Body2')
        desc_label.size_hint_y = None
        desc_label.height = dp(24)
        left.add_widget(desc_label)
        self.add_widget(left)
        right = BoxLayout(orientation='vertical', size_hint_x=0.4, spacing=dp(4))
        amount_color = 'Primary' if amount >= 0 else 'Error'
        amount_label = MDLabel(text=f"₱{amount:.2f}", halign='right', theme_text_color=amount_color)
        amount_label.size_hint_y = None
        amount_label.height = dp(24)
        right.add_widget(amount_label)
        btns = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(4))
        edit = Button(text='Edit', size_hint_x=0.5)
        delete = Button(text='Delete', size_hint_x=0.5)
        btns.add_widget(edit)
        btns.add_widget(delete)
        right.add_widget(btns)
        self.add_widget(right)
        edit.bind(on_release=lambda *_: edit_cb(tx_id))
        delete.bind(on_release=lambda *_: delete_cb(tx_id))


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
            right_action_items: [['cloud-sync', lambda x: app.manual_sync()], ['alert', lambda x: app.check_reminders()]]

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
                id: borrower_name
                hint_text: 'Borrower'
                multiline: False
                size_hint_y: None
                height: dp(44)

            TextInput:
                id: co_borrower
                hint_text: 'Co-borrower'
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
                hint_text: 'Borrower Name'
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


class UTrackerApp(MDApp):
    def build(self):
        init_db()
        update_schema_if_needed()
        migrate_database()
        Window.clearcolor = (1, 0.973, 0.863, 1)
        self.theme_cls.theme_style = "Light"
        self.theme_cls.primary_palette = "Amber"
        Builder.load_string(KV)
        self.sm = MainScreenManager()
        self.current_customer_id = None
        return self.sm

    def do_login(self, username, password):
        if username.strip() == 'admin' and password.strip() == 'admin':
            self.sm.current = 'dashboard'
            self.load_customers()
            # Check for overdue accounts on startup
            Clock.schedule_once(lambda dt: self.check_startup_reminders(), 2)
        else:
            show_message("Login Failed", "Invalid username or password")

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
        screen.ids.borrower_name.text = ''
        screen.ids.co_borrower.text = ''
        screen.ids.product.text = ''
        screen.ids.quantity.text = '1'
        screen.ids.amount.text = ''
        screen.ids.search_input.text = ''

    def handle_add_credit(self):
        screen = self.sm.get_screen('dashboard')
        borrower = screen.ids.borrower_name.text.strip()
        co_borrower = screen.ids.co_borrower.text.strip()
        product = screen.ids.product.text.strip()
        quantity = screen.ids.quantity.text.strip()
        amount = screen.ids.amount.text.strip()
        try:
            add_credit_db(borrower, co_borrower, product, quantity, amount)
            show_message("Success", "Credit added.")
            self.clear_form()
            self.load_customers()
            self.trigger_background_sync()
        except Exception as e:
            traceback.print_exc()
            show_message("Error", str(e))

    def handle_record_payment(self):
        screen = self.sm.get_screen('dashboard')
        borrower = screen.ids.borrower_name.text.strip()
        amount = screen.ids.amount.text.strip()
        try:
            cid, name, new_bal = record_payment_db(borrower, amount)
            show_message("Payment Recorded", f"{name}'s new balance: ₱{new_bal:.2f}")
            self.clear_form()
            self.load_customers()
            self.trigger_background_sync()
        except Exception as e:
            traceback.print_exc()
            show_message("Error", str(e))

    def open_history(self, customer_id):
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
        self.load_transactions()
        self.sm.current = 'history'

    def load_transactions(self):
        screen = self.sm.get_screen('history')
        grid = screen.ids.tx_grid
        grid.clear_widgets()
        if not self.current_customer_id:
            return
        rows = get_transactions_db(self.current_customer_id)
        if not rows:
            lbl = MDLabel(text='(no transactions)', halign='center')
            grid.add_widget(lbl)
            return
        for tx in rows:
            row = TransactionRow(tx, self.edit_transaction, self.delete_transaction)
            grid.add_widget(row)

    def edit_transaction(self, tx_id):
        pass  # Edit functionality for mobile can be added later

    def delete_transaction(self, tx_id):
        confirm_action("Delete Transaction", "Are you sure?", lambda: self.do_delete_transaction(tx_id))

    def do_delete_transaction(self, tx_id):
        try:
            cid, tx_count, new_bal, action, amount = delete_transaction_db(tx_id)
            show_message("Deleted", f"Deleted {action} of ₱{amount:.2f}. New balance: ₱{new_bal:.2f}")
            self.load_transactions()
            self.trigger_background_sync()
            if tx_count == 0:
                self.go_back_to_dashboard()
                self.load_customers()
        except Exception as e:
            traceback.print_exc()
            show_message("Error", str(e))

    def update_customer_name(self):
        if not self.current_customer_id:
            return
        screen = self.sm.get_screen('history')
        new_name = screen.ids.cust_name_input.text.strip()
        if not new_name:
            show_message("Error", "Name cannot be empty.")
            return
        try:
            update_customer_name_phone_db(self.current_customer_id, new_name=new_name)
            show_message("Updated", "Customer name updated.")
            self.load_transactions()
            self.trigger_background_sync()
            self.go_back_to_dashboard()
            self.load_customers()
        except Exception as e:
            traceback.print_exc()
            show_message("Error", str(e))

    def update_customer_phone(self):
        if not self.current_customer_id:
            return
        screen = self.sm.get_screen('history')
        new_phone = screen.ids.cust_phone_input.text.strip()
        try:
            update_customer_name_phone_db(self.current_customer_id, new_phone=new_phone)
            show_message("Updated", "Customer phone updated.")
            self.trigger_background_sync()
        except Exception as e:
            traceback.print_exc()
            show_message("Error", str(e))

    def go_back_to_dashboard(self):
        self.sm.current = 'dashboard'
        self.current_customer_id = None
        self.load_customers()

    def trigger_background_sync(self):
        pass  # Background sync functionality for mobile

    def manual_sync(self):
        show_message("Sync", "Manual sync triggered (mobile sync not implemented)")

    def check_startup_reminders(self):
        """Check for overdue accounts on startup"""
        overdue_customers = check_for_overdue_accounts()
        if overdue_customers:
            message = "Overdue accounts found:\n\n"
            for customer in overdue_customers:
                name = customer['name']
                old_balance = customer['old_balance']
                new_balance = customer['new_balance']
                status = customer['status']
                penalty_added = customer['penalty_added']

                if penalty_added:
                    message += f"{name}: ₱{old_balance:.2f} → ₱{new_balance:.2f} ({status})\n"
                else:
                    message += f"{name}: ₱{old_balance:.2f} ({status})\n"

            # Refresh the customer list to show updated balances
            self.load_customers()
            show_message("Overdue Accounts", message)

    def check_reminders(self):
        """Manual check for overdue accounts"""
        overdue_customers = check_for_overdue_accounts()
        if overdue_customers:
            message = "Overdue accounts:\n\n"
            for customer in overdue_customers:
                name = customer['name']
                old_balance = customer['old_balance']
                new_balance = customer['new_balance']
                status = customer['status']
                penalty_added = customer['penalty_added']

                if penalty_added:
                    message += f"{name}: ₱{old_balance:.2f} → ₱{new_balance:.2f} ({status})\n"
                else:
                    message += f"{name}: ₱{old_balance:.2f} ({status})\n"

            # Refresh the customer list to show updated balances
            self.load_customers()
            show_message("Overdue Accounts", message)
        else:
            show_message("Reminders", "No overdue accounts found.")


if __name__ == '__main__':
    UTrackerApp().run()
