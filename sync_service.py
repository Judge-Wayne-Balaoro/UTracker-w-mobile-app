# sync_service.py
import sqlite3
from datetime import datetime
import traceback


# Import database functions directly to avoid circular imports
def get_connection():
    import sqlite3
    import os
    # Get the same DB path as main.py
    base = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base, "data")
    db_path = os.path.join(data_dir, "utracker.db")
    return sqlite3.connect(db_path)


def generate_id():
    import uuid
    return str(uuid.uuid4())


def get_current_timestamp():
    from datetime import datetime
    return datetime.now().isoformat()


class SyncService:
    def __init__(self):
        # Import here to avoid circular imports
        try:
            from firebase_config import db
            self.db = db
        except ImportError:
            self.db = None
        self.last_sync_time = None

    def is_connected(self):
        """Check if Firebase is connected"""
        return self.db is not None

    def sync_all_data(self):
        """Sync all data between local SQLite and Firebase"""
        if not self.is_connected():
            print("Firebase not connected - skipping sync")
            return False

        try:
            print("Starting full sync...")

            # Sync customers
            customers_synced = self.sync_customers()

            # Sync transactions
            transactions_synced = self.sync_transactions()

            # Update last sync time
            self.last_sync_time = get_current_timestamp()

            print(f"Sync completed: {customers_synced} customers, {transactions_synced} transactions")
            return True

        except Exception as e:
            print(f"Sync failed: {str(e)}")
            traceback.print_exc()
            return False

    def sync_customers(self):
        """Sync customers between local and Firebase"""
        if not self.is_connected():
            return 0

        conn = get_connection()
        c = conn.cursor()

        try:
            # Get local customers that need sync
            c.execute('''
                SELECT id, name, display_name, phone_number, balance, created_at, updated_at, sync_status, firebase_id
                FROM customers 
                WHERE sync_status = 'pending' OR firebase_id IS NULL
            ''')
            local_customers = c.fetchall()

            synced_count = 0

            for customer in local_customers:
                (local_id, name, display_name, phone_number, balance, created_at,
                 updated_at, sync_status, firebase_id) = customer

                customer_data = {
                    'name': name,
                    'display_name': display_name,
                    'phone_number': phone_number,
                    'balance': balance,
                    'created_at': created_at,
                    'updated_at': updated_at,
                    'local_id': local_id,  # Store local ID for reference
                    'last_sync': get_current_timestamp()
                }

                if firebase_id:
                    # Update existing Firebase document
                    doc_ref = self.db.collection('customers').document(firebase_id)
                    doc_ref.set(customer_data, merge=True)
                else:
                    # Create new Firebase document
                    doc_ref = self.db.collection('customers').document()
                    customer_data['firebase_id'] = doc_ref.id
                    doc_ref.set(customer_data)

                    # Update local record with Firebase ID
                    firebase_id = doc_ref.id
                    c.execute('UPDATE customers SET firebase_id = ?, sync_status = ? WHERE id = ?',
                              (firebase_id, 'synced', local_id))

                synced_count += 1

            conn.commit()
            return synced_count

        except Exception as e:
            conn.rollback()
            print(f"Error syncing customers: {e}")
            return 0
        finally:
            conn.close()

    def sync_transactions(self):
        """Sync transactions between local and Firebase"""
        if not self.is_connected():
            return 0

        conn = get_connection()
        c = conn.cursor()

        try:
            # Get local transactions that need sync
            c.execute('''
                SELECT t.id, t.customer_id, t.date, t.time, t.action, t.product, 
                       t.quantity, t.amount, t.actual_borrower, t.created_at, 
                       t.updated_at, t.sync_status, t.firebase_id,
                       c.firebase_id as customer_firebase_id
                FROM transactions t
                LEFT JOIN customers c ON t.customer_id = c.id
                WHERE t.sync_status = 'pending' OR t.firebase_id IS NULL
            ''')
            local_transactions = c.fetchall()

            synced_count = 0

            for tx in local_transactions:
                (local_id, customer_id, date, time, action, product, quantity,
                 amount, actual_borrower, created_at, updated_at, sync_status,
                 firebase_id, customer_firebase_id) = tx

                if not customer_firebase_id:
                    # Skip if customer doesn't have Firebase ID yet
                    print(f"Skipping transaction {local_id} - customer not synced")
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
                    'last_sync': get_current_timestamp()
                }

                if firebase_id:
                    # Update existing Firebase document
                    doc_ref = self.db.collection('transactions').document(firebase_id)
                    doc_ref.set(transaction_data, merge=True)
                else:
                    # Create new Firebase document
                    doc_ref = self.db.collection('transactions').document()
                    transaction_data['firebase_id'] = doc_ref.id
                    doc_ref.set(transaction_data)

                    # Update local record with Firebase ID
                    firebase_id = doc_ref.id
                    c.execute('UPDATE transactions SET firebase_id = ?, sync_status = ? WHERE id = ?',
                              (firebase_id, 'synced', local_id))

                synced_count += 1

            conn.commit()
            return synced_count

        except Exception as e:
            conn.rollback()
            print(f"Error syncing transactions: {e}")
            return 0
        finally:
            conn.close()


# Create global instance
sync_service = SyncService()