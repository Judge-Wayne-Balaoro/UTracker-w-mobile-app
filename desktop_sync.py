import sqlite3
import os
import traceback
import sys
import uuid
from datetime import datetime

try:
    import firebase_admin
    from firebase_admin import credentials, firestore

    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    print("⚠️ Firebase not available - running in offline mode")


def generate_id():
    return str(uuid.uuid4())


class DesktopSyncService:
    def __init__(self):
        self.db = None
        if FIREBASE_AVAILABLE:
            self._initialize_firebase()
        else:
            print("🖥️ Desktop sync running in offline mode")

    def _initialize_firebase(self):
        try:
            if not firebase_admin._apps:
                service_account_path = os.path.join(os.path.dirname(__file__), 'serviceAccountKey.json')
                if os.path.exists(service_account_path):
                    cred = credentials.Certificate(service_account_path)
                    firebase_admin.initialize_app(cred)
                    self.db = firestore.client()
                    print("✅ Desktop Firebase initialized successfully!")
                else:
                    print("❌ serviceAccountKey.json not found")
                    self.db = None
            else:
                self.db = firestore.client()
                print("✅ Firebase connection re-used successfully.")
        except Exception as e:
            print(f"❌ Desktop Firebase init failed: {e}")
            self.db = None

    def is_connected(self):
        return self.db is not None and FIREBASE_AVAILABLE

    def get_db_connection(self):
        if getattr(sys, 'frozen', False):
            app_dir = os.path.dirname(sys.executable)
        else:
            app_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(app_dir, 'data', 'utracker.db')
        return sqlite3.connect(db_path)

    def sync_all_data(self):
        if not self.is_connected():
            print("Firebase not connected - working in offline mode")
            self._show_offline_message()
            return False, "Firebase not connected"
        try:
            print("🖥️ Starting desktop two-way sync...")
            customers_pulled = self.pull_customers_from_firebase()
            transactions_pulled = self.pull_transactions_from_firebase()
            customers_pushed = self.push_customers_to_firebase()
            transactions_pushed = self.push_transactions_to_firebase()
            summary = (f"Sync completed successfully.\n\n"
                       f"Pulled: {customers_pulled} customers, {transactions_pulled} transactions.\n"
                       f"Pushed: {customers_pushed} customers, {transactions_pushed} transactions.")
            print(summary)
            return True, summary
        except Exception as e:
            error_message = f"Sync failed: {str(e)}"
            print(f"🖥️ {error_message}")
            traceback.print_exc()
            self._show_error_message(str(e))
            return False, error_message

    def pull_customers_from_firebase(self):
        if not self.is_connected(): return 0
        conn = self.get_db_connection()
        c = conn.cursor()
        updated_count = 0
        try:
            customers_ref = self.db.collection('customers').stream()
            for cust in customers_ref:
                customer_data = cust.to_dict()
                firebase_id = cust.id
                c.execute("SELECT updated_at FROM customers WHERE firebase_id = ?", (firebase_id,))
                result = c.fetchone()
                if result:
                    local_updated_at = result[0]
                    firebase_updated_at = customer_data.get('updated_at')
                    if firebase_updated_at and firebase_updated_at > local_updated_at:
                        c.execute(
                            "UPDATE customers SET name=?, display_name=?, phone_number=?, balance=?, created_at=?, updated_at=?, sync_status='synced' WHERE firebase_id=?",
                            (customer_data.get('name'), customer_data.get('display_name'),
                             customer_data.get('phone_number'), customer_data.get('balance'),
                             customer_data.get('created_at'), customer_data.get('updated_at'), firebase_id))
                        updated_count += 1
                else:
                    local_id = customer_data.get('local_id', generate_id())
                    c.execute(
                        "INSERT INTO customers (id, name, display_name, phone_number, balance, created_at, updated_at, sync_status, firebase_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (local_id, customer_data.get('name'), customer_data.get('display_name'),
                         customer_data.get('phone_number'), customer_data.get('balance'),
                         customer_data.get('created_at'), customer_data.get('updated_at'), 'synced', firebase_id))
                    updated_count += 1
            conn.commit()
            return updated_count
        except Exception as e:
            conn.rollback();
            print(f"Error pulling customers: {e}");
            return 0
        finally:
            conn.close()

    def pull_transactions_from_firebase(self):
        if not self.is_connected(): return 0
        conn = self.get_db_connection()
        c = conn.cursor()
        updated_count = 0
        try:
            transactions_ref = self.db.collection('transactions').stream()
            for tx in transactions_ref:
                tx_data = tx.to_dict();
                firebase_id = tx.id

                if tx_data.get('is_deleted') == 1:
                    c.execute("DELETE FROM transactions WHERE firebase_id = ?", (firebase_id,))
                    updated_count += 1
                    continue

                customer_firebase_id = tx_data.get('customer_firebase_id')
                c.execute("SELECT id FROM customers WHERE firebase_id = ?", (customer_firebase_id,))
                cust_result = c.fetchone()
                if not cust_result: continue
                local_customer_id = cust_result[0]
                c.execute("SELECT updated_at FROM transactions WHERE firebase_id = ?", (firebase_id,))
                result = c.fetchone()
                if result:
                    local_updated_at = result[0]
                    firebase_updated_at = tx_data.get('updated_at')
                    if firebase_updated_at and firebase_updated_at > local_updated_at:
                        c.execute(
                            "UPDATE transactions SET customer_id=?, date=?, time=?, action=?, product=?, quantity=?, amount=?, actual_borrower=?, created_at=?, updated_at=?, sync_status='synced' WHERE firebase_id=?",
                            (local_customer_id, tx_data.get('date'), tx_data.get('time'), tx_data.get('action'),
                             tx_data.get('product'), tx_data.get('quantity'), tx_data.get('amount'),
                             tx_data.get('actual_borrower'), tx_data.get('created_at'), tx_data.get('updated_at'),
                             firebase_id))
                        updated_count += 1
                else:
                    local_id = tx_data.get('local_id', generate_id())
                    c.execute(
                        "INSERT INTO transactions (id, customer_id, date, time, action, product, quantity, amount, actual_borrower, created_at, updated_at, sync_status, firebase_id, is_deleted) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
                        (local_id, local_customer_id, tx_data.get('date'), tx_data.get('time'), tx_data.get('action'),
                         tx_data.get('product'), tx_data.get('quantity'), tx_data.get('amount'),
                         tx_data.get('actual_borrower'), tx_data.get('created_at'), tx_data.get('updated_at'), 'synced',
                         firebase_id))
                    updated_count += 1
            conn.commit()
            return updated_count
        except Exception as e:
            conn.rollback();
            print(f"Error pulling transactions: {e}");
            return 0
        finally:
            conn.close()

    def _show_offline_message(self):
        import tkinter.messagebox as messagebox
        messagebox.showinfo("Offline Mode", "Desktop app is running in offline mode...")

    def _show_error_message(self, error):
        import tkinter.messagebox as messagebox
        messagebox.showerror("Sync Error", f"Sync failed: {error}...")

    def push_customers_to_firebase(self):
        if not self.is_connected(): return 0
        conn = self.get_db_connection()
        c = conn.cursor()
        try:
            c.execute(
                "SELECT id, name, display_name, phone_number, balance, created_at, updated_at, sync_status, firebase_id FROM customers WHERE sync_status = 'pending' OR firebase_id IS NULL")
            customers = c.fetchall()
            synced_count = 0
            for customer in customers:
                (local_id, name, display_name, phone_number, balance, created_at, updated_at, sync_status,
                 firebase_id) = customer
                customer_data = {'name': name, 'display_name': display_name, 'phone_number': phone_number,
                                 'balance': balance, 'created_at': created_at, 'updated_at': updated_at,
                                 'local_id': local_id, 'last_sync': datetime.now().isoformat(), 'source': 'desktop'}
                try:
                    if firebase_id:
                        self.db.collection('customers').document(firebase_id).set(customer_data, merge=True)
                    else:
                        doc_ref = self.db.collection('customers').document()
                        firebase_id = doc_ref.id
                        doc_ref.set(customer_data)
                    c.execute("UPDATE customers SET firebase_id = ?, sync_status = 'synced' WHERE id = ?",
                              (firebase_id, local_id))
                    synced_count += 1
                except Exception as e:
                    print(f"❌ Failed to sync customer {display_name}: {e}")
            conn.commit()
            return synced_count
        except Exception as e:
            conn.rollback();
            print(f"Error pushing customers: {e}");
            return 0
        finally:
            conn.close()

    def push_transactions_to_firebase(self):
        if not self.is_connected(): return 0
        conn = self.get_db_connection()
        c = conn.cursor()
        try:
            c.execute(
                "SELECT t.id, t.customer_id, t.date, t.time, t.action, t.product, t.quantity, t.amount, t.actual_borrower, t.created_at, t.updated_at, t.sync_status, t.firebase_id, t.is_deleted, c.firebase_id as customer_firebase_id FROM transactions t LEFT JOIN customers c ON t.customer_id = c.id WHERE t.sync_status = 'pending' OR t.firebase_id IS NULL")
            transactions = c.fetchall()
            synced_count = 0
            for tx in transactions:
                (local_id, customer_id, date, time, action, product, quantity, amount, actual_borrower, created_at,
                 updated_at, sync_status, firebase_id, is_deleted, customer_firebase_id) = tx
                if not customer_firebase_id:
                    print(f"⏭️ Skipping transaction - customer not synced: {local_id}")
                    continue
                transaction_data = {'customer_firebase_id': customer_firebase_id, 'date': date, 'time': time,
                                    'action': action, 'product': product, 'quantity': quantity, 'amount': amount,
                                    'actual_borrower': actual_borrower, 'created_at': created_at,
                                    'updated_at': updated_at, 'local_id': local_id, 'is_deleted': is_deleted,
                                    'last_sync': datetime.now().isoformat(), 'source': 'desktop'}
                try:
                    if firebase_id:
                        self.db.collection('transactions').document(firebase_id).set(transaction_data, merge=True)
                    else:
                        doc_ref = self.db.collection('transactions').document()
                        firebase_id = doc_ref.id
                        doc_ref.set(transaction_data)
                    c.execute("UPDATE transactions SET firebase_id = ?, sync_status = 'synced' WHERE id = ?",
                              (firebase_id, local_id))
                    synced_count += 1
                except Exception as e:
                    print(f"❌ Failed to sync transaction {local_id}: {e}")
            conn.commit()
            return synced_count
        except Exception as e:
            conn.rollback();
            print(f"Error pushing transactions: {e}");
            return 0
        finally:
            conn.close()


desktop_sync = DesktopSyncService()
