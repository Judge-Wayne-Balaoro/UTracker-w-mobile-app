# desktop_sync.py
import sqlite3
import os
import traceback
import sys
import uuid
from datetime import datetime

# Try to import Firebase, but don't crash if it fails
try:
    import firebase_admin
    from firebase_admin import credentials, firestore

    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    print("⚠️ Firebase not available - running in offline mode")


class DesktopSyncService:
    def __init__(self):
        self.db = None
        if FIREBASE_AVAILABLE:
            self._initialize_firebase()
        else:
            print("🖥️ Desktop sync running in offline mode")

    def _initialize_firebase(self):
        """Initialize Firebase for desktop app with better error handling"""
        try:
            # Check if any Firebase app is already initialized
            try:
                # Try to get default app
                firebase_admin.get_app()
                print("⚠️ Firebase already initialized (probably by mobile app)")

                # Try to create desktop app with different name
                cred = credentials.Certificate(os.path.join(os.path.dirname(__file__), 'serviceAccountKey.json'))
                desktop_app = firebase_admin.initialize_app(cred, name='desktop-app')
                self.db = firestore.client(app=desktop_app)
                print("✅ Desktop Firebase initialized with separate app!")
                return

            except ValueError:
                # No app exists yet, initialize fresh
                pass

            # Fresh initialization
            service_account_path = os.path.join(os.path.dirname(__file__), 'serviceAccountKey.json')

            if os.path.exists(service_account_path):
                cred = credentials.Certificate(service_account_path)
                firebase_admin.initialize_app(cred)
                self.db = firestore.client()
                print("✅ Desktop Firebase initialized successfully!")
            else:
                print("❌ serviceAccountKey.json not found")
                self.db = None

        except Exception as e:
            print(f"❌ Desktop Firebase init failed: {e}")
            # Don't crash - just run in offline mode
            self.db = None

    def is_connected(self):
        return self.db is not None and FIREBASE_AVAILABLE

    def get_db_connection(self):
        """Get database connection for desktop app"""
        if getattr(sys, 'frozen', False):
            app_dir = os.path.dirname(sys.executable)
        else:
            app_dir = os.path.dirname(os.path.abspath(__file__))

        db_path = os.path.join(app_dir, 'data', 'utracker.db')
        return sqlite3.connect(db_path)

    def sync_all_data(self):
        """Two-way sync for desktop app"""
        if not self.is_connected():
            print("Firebase not connected - working in offline mode")
            return self._show_offline_message()

        try:
            print("🖥️ Starting desktop sync...")

            # Push to Firebase
            customers_synced = self.push_customers_to_firebase()
            transactions_synced = self.push_transactions_to_firebase()

            success = customers_synced > 0 or transactions_synced > 0

            if success:
                print(f"🖥️ Desktop sync completed: {customers_synced} customers, {transactions_synced} transactions")
                return True
            else:
                print("🖥️ No data needed sync")
                return True

        except Exception as e:
            print(f"🖥️ Desktop sync failed: {e}")
            traceback.print_exc()
            return self._show_error_message(str(e))

    def _show_offline_message(self):
        """Show offline mode message"""
        import tkinter.messagebox as messagebox
        messagebox.showinfo(
            "Offline Mode",
            "Desktop app is running in offline mode.\n\n"
            "Your data is saved locally and ready for sync.\n"
            "Firebase connection is not available.\n\n"
            "Make sure:\n"
            "• serviceAccountKey.json is in the same folder\n"
            "• You have internet connection\n"
            "• Firebase libraries are installed"
        )
        return False

    def _show_error_message(self, error):
        """Show error message"""
        import tkinter.messagebox as messagebox
        messagebox.showerror(
            "Sync Error",
            f"Sync failed: {error}\n\n"
            "Your data is safe locally.\n"
            "Try using the mobile app for cloud sync."
        )
        return False

    def push_customers_to_firebase(self):
        """Push local customers to Firebase"""
        if not self.is_connected():
            return 0

        conn = self.get_db_connection()
        c = conn.cursor()

        try:
            c.execute('''
                SELECT id, name, display_name, phone_number, balance, created_at, updated_at, sync_status, firebase_id
                FROM customers WHERE sync_status = 'pending' OR firebase_id IS NULL
            ''')
            customers = c.fetchall()

            synced_count = 0
            for customer in customers:
                (local_id, name, display_name, phone_number, balance, created_at,
                 updated_at, sync_status, firebase_id) = customer

                customer_data = {
                    'name': name,
                    'display_name': display_name,
                    'phone_number': phone_number,
                    'balance': balance,
                    'created_at': created_at,
                    'updated_at': updated_at,
                    'local_id': local_id,
                    'last_sync': datetime.now().isoformat(),
                    'source': 'desktop'
                }

                try:
                    if firebase_id:
                        # Update existing
                        doc_ref = self.db.collection('customers').document(firebase_id)
                        doc_ref.set(customer_data, merge=True)
                        print(f"✅ Updated customer: {display_name}")
                    else:
                        # Create new
                        doc_ref = self.db.collection('customers').document()
                        customer_data['firebase_id'] = doc_ref.id
                        doc_ref.set(customer_data)

                        # Update local record
                        c.execute('UPDATE customers SET firebase_id = ?, sync_status = ? WHERE id = ?',
                                  (doc_ref.id, 'synced', local_id))
                        print(f"✅ Created customer: {display_name}")

                    synced_count += 1

                except Exception as e:
                    print(f"❌ Failed to sync customer {display_name}: {e}")
                    continue

            conn.commit()
            return synced_count

        except Exception as e:
            conn.rollback()
            print(f"Error pushing customers: {e}")
            return 0
        finally:
            conn.close()

    def push_transactions_to_firebase(self):
        """Push local transactions to Firebase"""
        if not self.is_connected():
            return 0

        conn = self.get_db_connection()
        c = conn.cursor()

        try:
            c.execute('''
                SELECT t.id, t.customer_id, t.date, t.time, t.action, t.product, 
                       t.quantity, t.amount, t.actual_borrower, t.created_at, 
                       t.updated_at, t.sync_status, t.firebase_id,
                       c.firebase_id as customer_firebase_id
                FROM transactions t
                LEFT JOIN customers c ON t.customer_id = c.id
                WHERE t.sync_status = 'pending' OR t.firebase_id IS NULL
            ''')
            transactions = c.fetchall()

            synced_count = 0
            for tx in transactions:
                (local_id, customer_id, date, time, action, product, quantity,
                 amount, actual_borrower, created_at, updated_at, sync_status,
                 firebase_id, customer_firebase_id) = tx

                if not customer_firebase_id:
                    print(f"⏭️ Skipping transaction - customer not synced: {local_id}")
                    continue

                transaction_data = {
                    'customer_firebase_id': customer_firebase_id,
                    'date': date,
                    'time': time,
                    'action': action,
                    'product': product,
                    'quantity': quantity,
                    'amount': amount,
                    'actual_borrower': actual_borrower,
                    'created_at': created_at,
                    'updated_at': updated_at,
                    'local_id': local_id,
                    'last_sync': datetime.now().isoformat(),
                    'source': 'desktop'
                }

                try:
                    if firebase_id:
                        doc_ref = self.db.collection('transactions').document(firebase_id)
                        doc_ref.set(transaction_data, merge=True)
                    else:
                        doc_ref = self.db.collection('transactions').document()
                        transaction_data['firebase_id'] = doc_ref.id
                        doc_ref.set(transaction_data)

                        c.execute('UPDATE transactions SET firebase_id = ?, sync_status = ? WHERE id = ?',
                                  (doc_ref.id, 'synced', local_id))

                    synced_count += 1
                    print(f"✅ Synced transaction: {action} - {product}")

                except Exception as e:
                    print(f"❌ Failed to sync transaction {local_id}: {e}")
                    continue

            conn.commit()
            return synced_count

        except Exception as e:
            conn.rollback()
            print(f"Error pushing transactions: {e}")
            return 0
        finally:
            conn.close()


# Global instance
desktop_sync = DesktopSyncService()