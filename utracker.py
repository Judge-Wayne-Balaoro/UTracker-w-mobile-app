import uuid
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import sqlite3
import os
import re
import sys


def generate_id():
    return str(uuid.uuid4())


def get_current_timestamp():
    return datetime.now().isoformat()


class LoginWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("UTracker - Login")
        self.root.geometry("500x300")
        self.root.resizable(False, False)

        # Center the window
        window_width = 500
        window_height = 300
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")

        self.cream_color = "#FFF8DC"  # Cornsilk color (light cream)
        self.root.configure(bg=self.cream_color)

        # Login frame
        login_frame = tk.Frame(root, bg=self.cream_color)
        login_frame.pack(pady=40)

        # Title
        tk.Label(login_frame, text="UTracker Login", font=("Arial", 18, "bold"),
                 bg=self.cream_color, fg="black").grid(row=0, column=0, columnspan=2, pady=10)

        # Username
        tk.Label(login_frame, text="Username:", font=("Arial", 12),
                 bg=self.cream_color, fg="black").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.username_entry = tk.Entry(login_frame, font=("Arial", 12), width=25)
        self.username_entry.grid(row=1, column=1, padx=5, pady=5)

        # Password
        tk.Label(login_frame, text="Password:", font=("Arial", 12),
                 bg=self.cream_color, fg="black").grid(row=2, column=0, padx=5, pady=5, sticky="e")
        self.password_entry = tk.Entry(login_frame, font=("Arial", 12), show="*", width=25)
        self.password_entry.grid(row=2, column=1, padx=5, pady=5)

        # Login button
        login_button = tk.Button(root, text="Login", command=self.authenticate,
                                 font=("Arial", 12), bg="#E6D9B8", fg="black",
                                 width=15, height=1)
        login_button.pack(pady=10)

        # Focus on username field
        self.username_entry.focus_set()

        # Bind Enter key to authenticate
        self.root.bind('<Return>', lambda event: self.authenticate())

    def authenticate(self):
        username = self.username_entry.get()
        password = self.password_entry.get()

        if username == "admin" and password == "admin":
            self.root.destroy()  # Close login window
            # Open main application
            root = tk.Tk()
            app = UtangTrackerApp(root)
            root.mainloop()
        else:
            messagebox.showerror("Login Failed", "Invalid username or password")
            self.password_entry.delete(0, tk.END)
            self.username_entry.focus_set()


class AutocompleteEntry(ttk.Entry):
    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, **kwargs)
        self.app = app
        self.var = tk.StringVar()
        self.config(textvariable=self.var, font=("Arial", 14))

        # Create a Toplevel window for suggestions
        self.suggestion_window = tk.Toplevel(parent)
        self.suggestion_window.wm_overrideredirect(True)
        self.suggestion_window.wm_transient(parent)
        self.suggestion_window.configure(bg="white", relief="solid", borderwidth=1)

        self.listbox = tk.Listbox(self.suggestion_window,
                                  font=("Arial", 12),
                                  bg="white",
                                  relief="flat",
                                  borderwidth=0,
                                  highlightthickness=0,
                                  selectmode="single")
        self.listbox.pack(fill=tk.BOTH, expand=True)
        self.listbox.bind('<<ListboxSelect>>', self.on_select)

        self.var.trace('w', self.on_change)
        self.bind('<Key-Up>', self.on_up)
        self.bind('<Key-Down>', self.on_down)
        self.bind('<Return>', self.on_enter)
        self.bind('<Escape>', self.hide_listbox)
        self.bind('<FocusOut>', lambda e: self.hide_listbox())

        self.suggestions = []
        self.suggestion_window.withdraw()

    def on_change(self, *args):
        self.update_suggestions()

    def update_suggestions(self):
        typed = self.var.get().lower()
        if not typed:
            self.hide_listbox()
            return

        # Filter suggestions based on input
        self.suggestions = [name for name in self.app.all_borrowers if typed in name.lower()]

        if self.suggestions:
            self.show_suggestions()
        else:
            self.hide_listbox()

    def show_suggestions(self):
        # Get the absolute screen position of the entry
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()

        # Update listbox content
        self.listbox.delete(0, tk.END)
        for suggestion in self.suggestions[:8]:  # Show max 8 suggestions
            self.listbox.insert(tk.END, suggestion)

        # Calculate the exact height needed for the suggestions
        item_count = min(8, len(self.suggestions))
        item_height = 20  # Approximate height per item in pixels
        total_height = item_count * item_height

        # Set the window size to fit the content exactly
        width = self.winfo_width()
        self.suggestion_window.geometry(f"{width}x{total_height}+{x}+{y}")
        self.suggestion_window.deiconify()
        self.suggestion_window.lift()

        # Select first item by default
        if self.suggestions:
            self.listbox.selection_set(0)
            self.listbox.activate(0)

    def hide_listbox(self, event=None):
        self.suggestion_window.withdraw()

    def on_select(self, event):
        if self.listbox.curselection():
            index = self.listbox.curselection()[0]
            value = self.listbox.get(index)
            self.var.set(value)
            self.hide_listbox()
            self.icursor(tk.END)

    def on_up(self, event):
        if self.suggestion_window.winfo_viewable():
            current = self.listbox.curselection()
            if current:
                index = current[0]
                if index > 0:
                    self.listbox.selection_clear(0, tk.END)
                    self.listbox.selection_set(index - 1)
                    self.listbox.activate(index - 1)
            else:
                self.listbox.selection_set(0)
                self.listbox.activate(0)
            return 'break'

    def on_down(self, event):
        if self.suggestion_window.winfo_viewable():
            current = self.listbox.curselection()
            if current:
                index = current[0]
                if index < len(self.suggestions) - 1 and index < 7:
                    self.listbox.selection_clear(0, tk.END)
                    self.listbox.selection_set(index + 1)
                    self.listbox.activate(index + 1)
            else:
                self.listbox.selection_set(0)
                self.listbox.activate(0)
            return 'break'
        else:
            self.update_suggestions()
            return 'break'

    def on_enter(self, event):
        if self.suggestion_window.winfo_viewable() and self.listbox.curselection():
            self.on_select(event)
            return 'break'
        elif self.suggestions and not self.suggestion_window.winfo_viewable():
            self.var.set(self.suggestions[0])
            self.icursor(tk.END)
            return 'break'


class UtangTrackerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("UTracker")
        self.root.geometry("900x600")
        self.root.state("zoomed")

        # Track open windows
        self.open_windows = []

        # Theme variables
        self.cream_color = "#FFF8DC"  # Cornsilk color (light cream)
        self.current_bg_color = self.cream_color
        self.current_fg_color = "#000000"
        self.button_bg = "#E6D9B8"
        self.button_fg = "#000000"
        self.entry_bg = "#FFFFFF"
        self.entry_fg = "#000000"

        # Track search mode
        self.search_mode = False

        # Initialize SQLite database
        self.init_db()

        # Apply theme
        self.root.configure(bg=self.current_bg_color)

        # Top header frame with title
        header_frame = tk.Frame(root, bg=self.current_bg_color)
        header_frame.pack(fill=tk.X, pady=5)

        title_label = tk.Label(header_frame, text="UTracker", font=("Arial", 22, "bold"),
                               bg=self.current_bg_color, fg=self.current_fg_color)
        title_label.pack(side=tk.LEFT, padx=20)

        # Search frame
        search_frame = tk.Frame(root, bg=self.current_bg_color)
        search_frame.pack(pady=10)

        tk.Label(search_frame, text="Search Name:", font=("Arial", 14),
                 bg=self.current_bg_color, fg=self.current_fg_color).pack(side=tk.LEFT, padx=5)

        # Create a StringVar to track changes to the search entry
        self.search_var = tk.StringVar()
        self.search_var.trace("w", self.on_search_change)

        self.search_entry = tk.Entry(search_frame, font=("Arial", 14), width=25, textvariable=self.search_var)
        self.search_entry.pack(side=tk.LEFT, padx=5)
        self.search_entry.config(state='disabled')  # Disabled by default

        # Search button
        self.search_button = tk.Button(search_frame, text="Search", command=self.toggle_search_mode,
                                       font=("Arial", 14), bg=self.button_bg, fg=self.button_fg)
        self.search_button.pack(side=tk.LEFT, padx=5)

        # Form frame
        form_frame = tk.Frame(root, bg=self.current_bg_color)
        form_frame.pack(pady=10)

        # Updated labels: Account Name -> Borrower, Actual Borrower -> Co-borrower
        labels = ["Borrower:", "Co-borrower:", "Product:", "Quantity:", "Amount (₱):"]
        self.entries = {}

        for i, label in enumerate(labels):
            tk.Label(form_frame, text=label, font=("Arial", 14), anchor="e",
                     bg=self.current_bg_color, fg=self.current_fg_color).grid(row=i, column=0, padx=10, pady=5,
                                                                              sticky="w")

            if label == "Quantity:":
                entry = tk.Spinbox(form_frame, from_=0, to=100, font=("Arial", 14),
                                   width=5, increment=1)
                entry.delete(0, tk.END)
                entry.insert(0, "0")
            elif label == "Borrower:":
                # Get all borrower names for autocomplete
                self.all_borrowers = self.get_all_borrower_names()
                entry = AutocompleteEntry(form_frame, self, font=("Arial", 14), width=25)
            else:
                entry = tk.Entry(form_frame, font=("Arial", 14), width=25)

            entry.grid(row=i, column=1, padx=10, pady=5, sticky="w")
            self.entries[label] = entry

        # Button frame
        button_frame = tk.Frame(root, bg=self.current_bg_color)
        button_frame.pack(pady=10)

        sync_btn = tk.Button(button_frame, text="Sync Cloud", command=self.manual_sync,
                             font=("Arial", 14), width=18, height=2, bg="#4CAF50", fg="white")
        sync_btn.grid(row=0, column=3, padx=10, pady=10)

        buttons = [
            ("Add Credit", self.add_utang),
            ("Record Payment", self.record_payment),
            ("Clear", self.clear_fields)
        ]

        for i, (text, command) in enumerate(buttons):
            btn = tk.Button(button_frame, text=text, command=command, font=("Arial", 14),
                            width=18, height=2, bg=self.button_bg, fg=self.button_fg)
            btn.grid(row=0, column=i, padx=10, pady=10)
            if text != "Clear":
                self.entries[text] = btn  # Store buttons for enabling/disabling

        reminder_btn = tk.Button(button_frame, text="View Reminders", command=self.check_for_reminders,
                                 font=("Arial", 14), width=18, height=2, bg="#FF9999", fg="white")
        reminder_btn.grid(row=0, column=4, padx=10, pady=10)

        # Table frame with scrollbar
        self.table_frame = tk.Frame(root, bg=self.current_bg_color)
        self.table_frame.pack(pady=10, fill=tk.BOTH, expand=True)

        # Add scrollbar to main table
        self.tree_scrollbar = ttk.Scrollbar(self.table_frame)
        self.tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Main table columns
        columns = ("Last Transaction", "Borrower", "Balance")
        self.tree = ttk.Treeview(self.table_frame, columns=columns, show="headings",
                                 yscrollcommand=self.tree_scrollbar.set)
        self.tree_scrollbar.config(command=self.tree.yview)

        # Configure column headings and widths
        self.tree.heading("Last Transaction", text="Last Transaction")
        self.tree.column("Last Transaction", anchor="center", width=150)

        self.tree.heading("Borrower", text="Borrower")
        self.tree.column("Borrower", anchor="center", width=200)

        self.tree.heading("Balance", text="Balance")
        self.tree.column("Balance", anchor="center", width=150)

        # Initialize style for treeview
        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure("Treeview",
                             background="#FFF8E7",
                             foreground="black",
                             fieldbackground="#FFF8E7")
        self.style.configure("Treeview.Heading",
                             background="#E6D9B8",
                             foreground="black")

        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<Double-1>", self.on_double_click)

        # Initialize data
        self.refresh_table()

        # Start the automatic sync cycle 5 seconds after the app launches
        self.root.after(5000, self.auto_sync)

        # ADD THIS LINE to check for reminders 2 seconds after startup
        self.root.after(2000, self.check_startup_reminders)

    def auto_delete_zero_balance(self):
        """Automatically delete customers with zero balance for more than 1 week"""
        print("Checking for zero balance customers to delete...")
        conn = self.get_db_connection()

        try:
            cursor = conn.cursor()

            # Calculate date 1 week ago
            one_week_ago = (datetime.now() - timedelta(days=7)).isoformat()

            # Find customers with zero balance and no transactions in the last week
            cursor.execute("""
                SELECT c.id, c.display_name 
                FROM customers c
                WHERE c.balance = 0 
                AND c.updated_at < ?
                AND NOT EXISTS (
                    SELECT 1 FROM transactions t 
                    WHERE t.customer_id = c.id 
                    AND t.created_at > ?
                )
            """, (one_week_ago, one_week_ago))

            customers_to_delete = cursor.fetchall()

            if customers_to_delete:
                deleted_count = 0
                for customer_id, display_name in customers_to_delete:
                    # Delete customer and their transactions
                    cursor.execute('DELETE FROM transactions WHERE customer_id = ?', (customer_id,))
                    cursor.execute('DELETE FROM customers WHERE id = ?', (customer_id,))
                    print(f"Auto-deleted customer: {display_name}")
                    deleted_count += 1

                conn.commit()
                print(f"Auto-deleted {deleted_count} customers with zero balance")

                # Refresh table if any were deleted
                if deleted_count > 0:
                    self.refresh_table()

        except Exception as e:
            conn.rollback()
            print(f"Error in auto-delete: {e}")
        finally:
            conn.close()

    def check_startup_reminders(self):
        """Check for reminders at startup - adds ₱3 penalty monthly and shows popup if there are overdue debts"""
        print("Checking for overdue accounts at startup...")
        conn = self.get_db_connection()
        overdue_customers = []
        penalty_added = False

        try:
            cursor = conn.cursor()

            # Calculate the date 30 days ago (but set to 1 day for testing)
            thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
            today = datetime.now().strftime("%Y-%m-%d")

            # Find all customers with a balance > 0
            cursor.execute("SELECT id, display_name, balance FROM customers WHERE balance > 0")
            customers_with_balance = cursor.fetchall()

            for customer_id, display_name, balance in customers_with_balance:
                # For each customer, find the date of their oldest credit transaction
                cursor.execute("""
                    SELECT MIN(created_at) FROM transactions 
                    WHERE customer_id = ? AND action = 'Credit Added'
                """, (customer_id,))
                result = cursor.fetchone()
                oldest_credit_date_str = result[0] if result else None

                # If they have a credit and it's older than 30 days (1 day for testing)
                if oldest_credit_date_str and oldest_credit_date_str < thirty_days_ago:
                    # MONTHLY PENALTY LOGIC: Check last penalty date
                    cursor.execute("""
                        SELECT MAX(date) FROM transactions 
                        WHERE customer_id = ? AND action = 'Overdue Penalty'
                    """, (customer_id,))
                    last_penalty_result = cursor.fetchone()
                    last_penalty_date = last_penalty_result[0] if last_penalty_result[0] else None

                    # Add penalty if never penalized or last penalty was more than 30 days ago
                    should_add_penalty = True
                    penalty_status = "new monthly penalty"

                    if last_penalty_date:
                        try:
                            last_penalty_datetime = datetime.strptime(last_penalty_date, "%Y-%m-%d")
                            days_since_last_penalty = (datetime.now() - last_penalty_datetime).days
                            should_add_penalty = days_since_last_penalty >= 30

                            if not should_add_penalty:
                                penalty_status = f"penalty added {days_since_last_penalty} days ago"
                        except ValueError:
                            # If date parsing fails, add penalty
                            should_add_penalty = True
                            penalty_status = "new monthly penalty"

                    if should_add_penalty:
                        # Add ₱3 penalty
                        penalty_amount = 3.0
                        new_balance = balance + penalty_amount

                        # Update customer balance
                        cursor.execute(
                            'UPDATE customers SET balance = ?, updated_at = ?, sync_status = ? WHERE id = ?',
                            (new_balance, datetime.now().isoformat(), 'pending', customer_id)
                        )

                        # Create penalty transaction
                        transaction_id = str(uuid.uuid4())
                        now = datetime.now().isoformat()
                        cursor.execute(
                            '''INSERT INTO transactions 
                            (id, customer_id, date, time, action, product, quantity, amount, created_at, updated_at, sync_status) 
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                            (transaction_id, customer_id,
                             today,
                             datetime.now().strftime("%H:%M"),
                             "Overdue Penalty", "Late Fee", 1, penalty_amount,
                             now, now, 'pending')
                        )

                        overdue_customers.append((display_name, balance, new_balance, penalty_status))
                        penalty_added = True
                    else:
                        # Penalty already added recently, but still show as overdue
                        overdue_customers.append((display_name, balance, balance, penalty_status))

            if penalty_added:
                conn.commit()

        except Exception as e:
            conn.rollback()
            print(f"Error checking for startup reminders: {e}")
        finally:
            conn.close()

        # Refresh table to show updated balances
        self.refresh_table()

        # ONLY show popup at startup if there are overdue customers
        if overdue_customers:
            message = "Overdue Accounts:\n\n"
            for name, old_balance, new_balance, status in overdue_customers:
                if status == "new monthly penalty":
                    message += f"- {name}: ₱{old_balance:.2f} → ₱{new_balance:.2f} (₱3 monthly penalty added)\n"
                else:
                    message += f"- {name}: ₱{new_balance:.2f} ({status})\n"
            messagebox.showwarning("Overdue Accounts Reminder", message)
        # No else clause - if no overdue debts, don't show any popup at startup

    def check_for_reminders(self):
        """Checks for borrowers with debts older than 30 days, adds ₱3 penalty monthly, and shows a reminder."""
        print("Checking for overdue accounts...")
        conn = self.get_db_connection()
        overdue_customers = []
        penalty_added = False

        try:
            cursor = conn.cursor()

            # Calculate the date 30 days ago (but set to 1 day for testing)
            thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()  # TESTING: changed from 30 to 1
            today = datetime.now().strftime("%Y-%m-%d")
            print(f"DEBUG: Looking for transactions older than: {thirty_days_ago}")

            # Find all customers with a balance > 0
            cursor.execute("SELECT id, display_name, balance FROM customers WHERE balance > 0")
            customers_with_balance = cursor.fetchall()
            print(f"DEBUG: Found {len(customers_with_balance)} customers with balance > 0")

            for customer_id, display_name, balance in customers_with_balance:
                print(f"DEBUG: Checking customer: {display_name}, Balance: {balance}")

                # For each customer, find the date of their oldest credit transaction
                cursor.execute("""
                    SELECT MIN(created_at) FROM transactions 
                    WHERE customer_id = ? AND action = 'Credit Added'
                """, (customer_id,))
                result = cursor.fetchone()
                oldest_credit_date_str = result[0] if result else None
                print(f"DEBUG: {display_name} - Oldest credit date: {oldest_credit_date_str}")

                # If they have a credit and it's older than 30 days (1 day for testing)
                if oldest_credit_date_str and oldest_credit_date_str < thirty_days_ago:
                    print(f"DEBUG: {display_name} - Account is overdue!")

                    # MONTHLY PENALTY LOGIC: Check last penalty date
                    cursor.execute("""
                        SELECT MAX(date) FROM transactions 
                        WHERE customer_id = ? AND action = 'Overdue Penalty'
                    """, (customer_id,))
                    last_penalty_result = cursor.fetchone()
                    last_penalty_date = last_penalty_result[0] if last_penalty_result[0] else None

                    # Add penalty if never penalized or last penalty was more than 30 days ago
                    should_add_penalty = True
                    penalty_status = "new monthly penalty"

                    if last_penalty_date:
                        try:
                            last_penalty_datetime = datetime.strptime(last_penalty_date, "%Y-%m-%d")
                            days_since_last_penalty = (datetime.now() - last_penalty_datetime).days
                            should_add_penalty = days_since_last_penalty >= 30
                            print(
                                f"DEBUG: {display_name} - Days since last penalty: {days_since_last_penalty}, Should add penalty: {should_add_penalty}")

                            if not should_add_penalty:
                                penalty_status = f"penalty added {days_since_last_penalty} days ago"
                        except ValueError as e:
                            print(f"DEBUG: Error parsing date {last_penalty_date}: {e}")
                            # If date parsing fails, add penalty
                            should_add_penalty = True
                            penalty_status = "new monthly penalty"

                    if should_add_penalty:
                        # Add ₱3 penalty
                        penalty_amount = 3.0
                        new_balance = balance + penalty_amount
                        print(f"DEBUG: Adding ₱3 monthly penalty to {display_name}")

                        # Update customer balance
                        cursor.execute(
                            'UPDATE customers SET balance = ?, updated_at = ?, sync_status = ? WHERE id = ?',
                            (new_balance, datetime.now().isoformat(), 'pending', customer_id)
                        )

                        # Create penalty transaction
                        transaction_id = str(uuid.uuid4())
                        now = datetime.now().isoformat()
                        cursor.execute(
                            '''INSERT INTO transactions 
                            (id, customer_id, date, time, action, product, quantity, amount, created_at, updated_at, sync_status) 
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                            (transaction_id, customer_id,
                             today,
                             datetime.now().strftime("%H:%M"),
                             "Overdue Penalty", "Late Fee", 1, penalty_amount,
                             now, now, 'pending')
                        )

                        overdue_customers.append((display_name, balance, new_balance, penalty_status))
                        penalty_added = True
                    else:
                        # Penalty already added recently, but still show as overdue
                        print(f"DEBUG: Monthly penalty already added recently for {display_name}")
                        overdue_customers.append((display_name, balance, balance, penalty_status))
                else:
                    print(f"DEBUG: {display_name} - Account is NOT overdue")

            if penalty_added:
                conn.commit()
                print("DEBUG: Monthly penalties committed to database")

        except Exception as e:
            conn.rollback()
            print(f"Error checking for reminders: {e}")
        finally:
            conn.close()

        # Refresh table to show updated balances
        self.refresh_table()

        print(f"DEBUG: Overdue customers found: {len(overdue_customers)}")

        # If we found any overdue customers, show the pop-up
        if overdue_customers:
            message = "Overdue Accounts:\n\n"
            for name, old_balance, new_balance, status in overdue_customers:
                if status == "new monthly penalty":
                    message += f"- {name}: ₱{old_balance:.2f} → ₱{new_balance:.2f} (₱3 monthly penalty added)\n"
                else:
                    message += f"- {name}: ₱{new_balance:.2f} ({status})\n"
            print("DEBUG: Showing popup with overdue accounts")
            messagebox.showwarning("Overdue Accounts Reminder", message)
        else:
            print("DEBUG: No overdue accounts found, showing 'no overdue' popup")
            messagebox.showinfo("Reminders", "No overdue account found!")

    def get_all_borrower_names(self):
        """Get all unique borrower names for autocomplete"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT DISTINCT display_name FROM customers WHERE balance >= 0 ORDER BY display_name')
        borrowers = [row[0] for row in cursor.fetchall()]
        conn.close()
        return borrowers

    def toggle_search_mode(self):
        """Toggle between search mode and normal mode"""
        self.search_mode = not self.search_mode

        if self.search_mode:
            self.search_button.config(text="Cancel Search", bg="#FF9999")
            self.search_entry.config(state='normal')
            # Disable form fields and buttons except Clear
            for label, widget in self.entries.items():
                if label != "Clear":
                    if isinstance(widget, tk.Button):
                        widget.config(state='disabled')
                    else:
                        widget.config(state='disabled')
            self.search_entry.focus()
        else:
            self.search_button.config(text="Search", bg=self.button_bg)
            self.search_entry.config(state='disabled')
            self.search_var.set("")
            # Enable form fields and buttons
            for label, widget in self.entries.items():
                if label != "Clear":
                    if isinstance(widget, tk.Button):
                        widget.config(state='normal')
                    else:
                        widget.config(state='normal')
            self.refresh_table()
            self.entries["Borrower:"].focus()

    def clear_fields(self):
        """Clear all input fields including search"""
        for label, entry in self.entries.items():
            if isinstance(entry, tk.Spinbox):
                entry.delete(0, tk.END)
                entry.insert(0, "0")
            elif isinstance(entry, (tk.Entry, AutocompleteEntry)):
                entry.delete(0, tk.END)

        # Clear search field regardless of mode
        self.search_var.set("")

        # If in search mode, refresh the table to show all records
        if self.search_mode:
            self.refresh_table()

    def init_db(self):
        """Initialize the SQLite database with sync fields"""
        if getattr(sys, 'frozen', False):
            app_dir = os.path.dirname(sys.executable)
        else:
            app_dir = os.path.dirname(os.path.abspath(__file__))

        data_dir = os.path.join(app_dir, 'data')
        os.makedirs(data_dir, exist_ok=True)

        db_path = os.path.join(data_dir, 'utracker.db')

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # First, check if we need to migrate the schema
        cursor.execute("PRAGMA table_info(customers)")
        columns = [col[1] for col in cursor.fetchall()]

        # Check if this is the old schema (missing sync fields)
        needs_migration = 'sync_status' not in columns

        if needs_migration:
            print("Migrating database to new schema...")
            self._migrate_database(conn, cursor)
        else:
            print("Database already uses new schema")

        # Create indexes only if they don't exist
        try:
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_customer_name ON customers (name)')
        except:
            pass

        try:
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sync_status ON customers (sync_status)')
        except:
            pass

        try:
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_tx_sync_status ON transactions (sync_status)')
        except:
            pass

        conn.commit()
        conn.close()
        return db_path

    def _migrate_database(self, conn, cursor):
        """Migrate from old schema to new schema with sync fields"""
        try:
            # Backup old tables
            cursor.execute("ALTER TABLE customers RENAME TO customers_old")
            cursor.execute("ALTER TABLE transactions RENAME TO transactions_old")

            # Create new tables with sync fields
            cursor.execute('''
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

            cursor.execute('''
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

            # Migrate customers data
            cursor.execute('SELECT id, name, display_name, phone_number, balance FROM customers_old')
            old_customers = cursor.fetchall()

            for old_id, name, display_name, phone_number, balance in old_customers:
                # Convert old integer ID to string UUID if needed
                if isinstance(old_id, int):
                    new_id = str(uuid.uuid4())
                else:
                    new_id = old_id

                now = datetime.now().isoformat()
                cursor.execute('''
                    INSERT INTO customers 
                    (id, name, display_name, phone_number, balance, created_at, updated_at, sync_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (new_id, name, display_name, phone_number, balance, now, now, 'synced'))

                # Update transactions to use new customer ID if ID changed
                if isinstance(old_id, int):
                    cursor.execute('UPDATE transactions_old SET customer_id = ? WHERE customer_id = ?',
                                   (new_id, old_id))

            # Migrate transactions data
            cursor.execute('''
                SELECT id, customer_id, date, time, action, product, quantity, amount, actual_borrower 
                FROM transactions_old
            ''')
            old_transactions = cursor.fetchall()

            for (old_id, customer_id, date, time, action, product, quantity,
                 amount, actual_borrower) in old_transactions:

                if isinstance(old_id, int):
                    new_id = str(uuid.uuid4())
                else:
                    new_id = old_id

                now = datetime.now().isoformat()
                cursor.execute('''
                    INSERT INTO transactions
                    (id, customer_id, date, time, action, product, quantity, amount, 
                     actual_borrower, created_at, updated_at, sync_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (new_id, customer_id, date, time, action, product, quantity,
                      amount, actual_borrower, now, now, 'synced'))

            # Drop old tables
            cursor.execute("DROP TABLE customers_old")
            cursor.execute("DROP TABLE transactions_old")

            print("Database migration completed successfully!")

        except Exception as e:
            # If migration fails, restore old tables
            try:
                cursor.execute("DROP TABLE IF EXISTS customers")
                cursor.execute("DROP TABLE IF EXISTS transactions")
                cursor.execute("ALTER TABLE customers_old RENAME TO customers")
                cursor.execute("ALTER TABLE transactions_old RENAME TO transactions")
            except:
                pass
            raise e

    def get_db_connection(self):
        if getattr(sys, 'frozen', False):
            app_dir = os.path.dirname(sys.executable)
        else:
            app_dir = os.path.dirname(os.path.abspath(__file__))

        db_path = os.path.join(app_dir, 'data', 'utracker.db')
        return sqlite3.connect(db_path)

    def get_customer_id(self, name, actual_borrower=None):
        conn = self.get_db_connection()
        cursor = conn.cursor()

        name_lower = name.lower()
        cursor.execute('SELECT id, display_name FROM customers WHERE name = ?', (name_lower,))
        result = cursor.fetchone()

        if result:
            customer_id, display_name = result
        else:
            # Create new customer with UUID and timestamps
            customer_id = str(uuid.uuid4())
            now = datetime.now().isoformat()
            cursor.execute(
                'INSERT INTO customers (id, name, display_name, balance, created_at, updated_at, sync_status) VALUES (?, ?, ?, 0, ?, ?, ?)',
                (customer_id, name_lower, name, now, now, 'pending')
            )
            conn.commit()
            display_name = name

        conn.close()
        return customer_id, display_name

    def get_latest_transaction_datetime(self, customer_id):
        conn = self.get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            'SELECT date, time FROM transactions WHERE customer_id = ? ORDER BY date DESC, time DESC LIMIT 1',
            (customer_id,)
        )
        result = cursor.fetchone()

        conn.close()
        if result:
            date, time = result
            dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
            return dt.strftime("%Y-%m-%d %I:%M %p")
        return "N/A"

    def add_utang(self):
        borrower_name = self.entries["Borrower:"].get().strip()
        co_borrower = self.entries["Co-borrower:"].get().strip()
        product = self.entries["Product:"].get().strip()
        quantity = self.entries["Quantity:"].get()
        date = datetime.now().strftime("%Y-%m-%d")
        time = datetime.now().strftime("%H:%M")

        if not borrower_name:
            messagebox.showerror("Input Error", "Borrower name cannot be empty.")
            return

        try:
            amount = float(self.entries["Amount (₱):"].get())
        except ValueError:
            messagebox.showerror("Input Error", "Please enter a valid amount.")
            return

        try:
            quantity = int(quantity)
            if quantity < 1:
                messagebox.showerror("Input Error", "Quantity must be 1 or more for adding credit.")
                return
        except ValueError:
            messagebox.showerror("Input Error", "Please enter a valid quantity.")
            return

        if not product:
            messagebox.showerror("Input Error", "Product cannot be empty.")
            return

        total_amount = amount * quantity

        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            customer_id, display_name = self.get_customer_id(borrower_name)

            # Update customer balance
            cursor.execute(
                'UPDATE customers SET balance = balance + ?, updated_at = ?, sync_status = ? WHERE id = ?',
                (total_amount, datetime.now().isoformat(), 'pending', customer_id)
            )

            # Create transaction with new schema - CHANGED: "Add Credit" to "Credit Added"
            transaction_id = str(uuid.uuid4())
            now = datetime.now().isoformat()
            cursor.execute(
                '''INSERT INTO transactions 
                (id, customer_id, date, time, action, product, quantity, amount, actual_borrower, created_at, updated_at, sync_status) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    transaction_id, customer_id, date, time, "Credit Added",
                    product, quantity, total_amount,
                    co_borrower if co_borrower and co_borrower != display_name else None,
                    now, now, 'pending'
                )
            )

            conn.commit()
            self.refresh_table()
            self.clear_fields()
            self.auto_sync()

        except Exception as e:
            conn.rollback()
            messagebox.showerror("Database Error", f"An error occurred: {str(e)}")
        finally:
            conn.close()

    def record_payment(self):
        borrower_name = self.entries["Borrower:"].get().strip()
        date = datetime.now().strftime("%Y-%m-%d")
        time = datetime.now().strftime("%H:%M")

        if not borrower_name:
            messagebox.showerror("Input Error", "Borrower name cannot be empty.")
            return

        try:
            amount = float(self.entries["Amount (₱):"].get())
        except ValueError:
            messagebox.showerror("Input Error", "Please enter a valid amount.")
            return

        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('SELECT id, display_name, balance FROM customers WHERE name = ?', (borrower_name.lower(),))
            result = cursor.fetchone()

            if not result:
                messagebox.showerror("Error", "Customer not found.")
                return

            customer_id, display_name, balance = result

            new_balance = balance - amount

            # Update customer balance with sync fields
            now = datetime.now().isoformat()
            cursor.execute(
                'UPDATE customers SET balance = ?, updated_at = ?, sync_status = ? WHERE id = ?',
                (new_balance, now, 'pending', customer_id)
            )

            # Create transaction with UUID and sync fields - CHANGED: "Record Payment" to "Paid"
            transaction_id = str(uuid.uuid4())
            cursor.execute(
                '''INSERT INTO transactions 
                (id, customer_id, date, time, action, product, quantity, amount, created_at, updated_at, sync_status) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (transaction_id, customer_id, date, time, "Paid", "N/A", 0, amount, now, now, 'pending')
            )

            conn.commit()
            self.clear_fields()

            # REMOVED: No longer prompt to remove when balance reaches zero
            # The customer will simply stay in the list with zero balance

            self.refresh_table()
            self.auto_sync()

        except Exception as e:
            conn.rollback()
            messagebox.showerror("Database Error", f"An error occurred: {str(e)}")
            import traceback
            traceback.print_exc()  # This will print the full error to console
        finally:
            conn.close()

    def refresh_table(self, search_term=None):
        self.tree.delete(*self.tree.get_children())

        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            if search_term:
                cursor.execute(
                    '''SELECT id, display_name, balance FROM customers 
                    WHERE (name LIKE ? OR display_name LIKE ?) 
                    AND balance >= 0 ORDER BY display_name''',
                    (f'%{search_term.lower()}%', f'%{search_term}%')
                )
            else:
                cursor.execute(
                    'SELECT id, display_name, balance FROM customers WHERE balance >= 0 ORDER BY display_name'
                )

            customers = cursor.fetchall()

            # Calculate 30 days ago (PERMANENT)
            thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()

            for customer_id, display_name, balance in customers:
                last_transaction = self.get_latest_transaction_datetime(customer_id)

                # Check if overdue - only for customers with balance > 0
                is_overdue = False
                if balance > 0:
                    cursor.execute("""
                        SELECT MIN(created_at) FROM transactions 
                        WHERE customer_id = ? AND action = 'Credit Added'
                    """, (customer_id,))
                    result = cursor.fetchone()
                    oldest_credit_date_str = result[0] if result else None

                    is_overdue = (oldest_credit_date_str and
                                  oldest_credit_date_str < thirty_days_ago)

                # Add warning emoji for overdue customers
                display_name_with_indicator = display_name + " ⚠️" if is_overdue else display_name

                self.tree.insert("", "end", values=(
                    last_transaction,
                    display_name_with_indicator,
                    f"₱{balance:.2f}"
                ))

        except Exception as e:
            messagebox.showerror("Database Error", f"An error occurred: {str(e)}")
        finally:
            conn.close()

    def on_search_change(self, *args):
        if not self.search_mode:
            return

        search_term = self.search_var.get().strip()
        self.refresh_table(search_term)

    def on_double_click(self, event):
        selected_item = self.tree.selection()
        if not selected_item:
            return

        display_name = self.tree.item(selected_item[0], "values")[1]

        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('SELECT id FROM customers WHERE display_name = ?', (display_name,))
            result = cursor.fetchone()

            if result:
                customer_id = result[0]
                self.show_transaction_history(customer_id)
            else:
                messagebox.showerror("Error", "Customer not found.")

        except Exception as e:
            messagebox.showerror("Database Error", f"An error occurred: {str(e)}")
        finally:
            conn.close()

    def show_transaction_history(self, customer_id):
        # Close any existing history window for this customer
        for window in self.open_windows[:]:
            if hasattr(window, 'customer_id') and window.customer_id == customer_id:
                window.destroy()
                self.open_windows.remove(window)

        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('SELECT display_name, phone_number FROM customers WHERE id = ?', (customer_id,))
            customer = cursor.fetchone()

            if not customer:
                messagebox.showerror("Error", "Customer not found.")
                return

            display_name, phone_number = customer

            history_window = tk.Toplevel(self.root)
            history_window.title(f"Transaction History for {display_name}")
            history_window.geometry("1100x600")
            history_window.configure(bg=self.current_bg_color)

            # Track this window
            history_window.customer_id = customer_id
            self.open_windows.append(history_window)

            # Handle window close
            history_window.protocol("WM_DELETE_WINDOW", lambda: self.on_history_window_close(history_window))

            # Customer info frame
            info_frame = tk.Frame(history_window, bg=self.current_bg_color)
            info_frame.pack(fill=tk.X, padx=10, pady=5)

            # Name frame - Updated label
            name_frame = tk.Frame(info_frame, bg=self.current_bg_color)
            name_frame.pack(side=tk.LEFT, pady=5)

            tk.Label(name_frame, text="Borrower Name:",
                     font=("Arial", 12), bg=self.current_bg_color,
                     fg=self.current_fg_color).pack(side=tk.LEFT, padx=5)

            name_var = tk.StringVar()
            name_var.set(display_name)

            name_entry = tk.Entry(name_frame, textvariable=name_var,
                                  font=("Arial", 12), width=20, bg=self.entry_bg, fg=self.entry_fg)
            name_entry.pack(side=tk.LEFT, padx=5)

            def update_name():
                try:
                    new_name = name_var.get().strip()
                    if not new_name:
                        messagebox.showerror("Error", "Borrower name cannot be empty.")
                        return

                    conn = self.get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute('UPDATE customers SET display_name = ?, name = ? WHERE id = ?',
                                   (new_name, new_name.lower(), customer_id))
                    conn.commit()
                    conn.close()
                    history_window.title(f"Transaction History for {new_name}")
                    messagebox.showinfo("Updated", "Borrower name updated successfully")
                    self.refresh_table()
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to update name: {str(e)}")

            update_name_btn = tk.Button(name_frame, text="Update", command=update_name,
                                        font=("Arial", 10), bg=self.button_bg, fg=self.button_fg)
            update_name_btn.pack(side=tk.LEFT, padx=5)

            # Phone number frame
            phone_frame = tk.Frame(info_frame, bg=self.current_bg_color)
            phone_frame.pack(side=tk.LEFT, pady=5, padx=20)

            tk.Label(phone_frame, text="Phone Number:",
                     font=("Arial", 12), bg=self.current_bg_color,
                     fg=self.current_fg_color).pack(side=tk.LEFT, padx=5)

            phone_var = tk.StringVar()
            phone_var.set(phone_number if phone_number else "")

            phone_entry = tk.Entry(phone_frame, textvariable=phone_var,
                                   font=("Arial", 12), width=15, bg=self.entry_bg, fg=self.entry_fg)
            phone_entry.pack(side=tk.LEFT, padx=5)

            def update_phone():
                try:
                    new_phone = phone_var.get().strip()
                    conn = self.get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute('UPDATE customers SET phone_number = ? WHERE id = ?',
                                   (new_phone if new_phone else None, customer_id))
                    conn.commit()
                    conn.close()
                    messagebox.showinfo("Updated", "Phone number updated successfully")
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to update phone number: {str(e)}")

            update_phone_btn = tk.Button(phone_frame, text="Update", command=update_phone,
                                         font=("Arial", 10), bg=self.button_bg, fg=self.button_fg)
            update_phone_btn.pack(side=tk.LEFT, padx=5)

            # Transaction history
            tk.Label(history_window, text="Transaction History",
                     font=("Arial", 14), bg=self.current_bg_color,
                     fg=self.current_fg_color).pack(pady=5)

            tree_frame = tk.Frame(history_window, bg=self.current_bg_color)
            tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

            scrollbar = ttk.Scrollbar(tree_frame)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            # Updated column name: Actual Borrower -> Co-borrower
            history_columns = ("#", "Date & Time", "Action", "Product", "Quantity", "Amount", "Co-borrower")
            history_tree = ttk.Treeview(tree_frame, columns=history_columns, show="headings",
                                        yscrollcommand=scrollbar.set)
            history_tree.pack(fill=tk.BOTH, expand=True)

            scrollbar.config(command=history_tree.yview)

            # Configure columns
            history_tree.heading("#", text="#")
            history_tree.column("#", anchor="center", width=40, stretch=tk.NO)
            history_tree.heading("Date & Time", text="Date & Time")
            history_tree.column("Date & Time", anchor="center", width=150)
            history_tree.heading("Action", text="Action")
            history_tree.column("Action", anchor="center", width=100)
            history_tree.heading("Product", text="Product")
            history_tree.column("Product", anchor="center", width=150)
            history_tree.heading("Quantity", text="Qty")
            history_tree.column("Quantity", anchor="center", width=60)
            history_tree.heading("Amount", text="Amount")
            history_tree.column("Amount", anchor="center", width=100)
            history_tree.heading("Co-borrower", text="Co-borrower")
            history_tree.column("Co-borrower", anchor="center", width=150)

            cursor.execute(
                '''SELECT t.date, t.time, t.action, t.product, t.quantity, t.amount, t.actual_borrower 
                FROM transactions t
                WHERE t.customer_id = ? 
                ORDER BY datetime(t.date || ' ' || t.time) ASC''',
                (customer_id,)
            )
            transactions = cursor.fetchall()

            for row_num, transaction in enumerate(transactions, 1):
                date, time, action, product, quantity, amount, actual_borrower = transaction

                # Calculate unit price for display purposes
                unit_price = amount / quantity if quantity > 0 else amount
                display_amount = amount if action == "Paid" else unit_price * quantity

                dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
                formatted_datetime = dt.strftime("%Y-%m-%d %I:%M %p")

                # Get account name
                borrower_display = display_name if not actual_borrower else actual_borrower

                history_tree.insert("", "end", values=(
                    row_num,
                    formatted_datetime,
                    action,
                    product,
                    quantity,
                    f"₱{display_amount:.2f}",
                    borrower_display
                ))

            # Action buttons
            btn_frame = tk.Frame(history_window, bg=self.current_bg_color)
            btn_frame.pack(pady=10)

            edit_btn = tk.Button(btn_frame, text="Edit Selected Entry",
                                 command=lambda: self.edit_transaction(history_window, history_tree),
                                 font=("Arial", 12), width=20, bg=self.button_bg, fg=self.button_fg)
            edit_btn.pack(side=tk.LEFT, padx=10)

            delete_btn = tk.Button(btn_frame, text="Delete Selected Entry",
                                   command=lambda: self.delete_transaction(history_window, history_tree),
                                   font=("Arial", 12), width=20, bg=self.button_bg, fg=self.button_fg)
            delete_btn.pack(side=tk.LEFT, padx=10)

            history_window.history_tree = history_tree

        except Exception as e:
            messagebox.showerror("Database Error", f"An error occurred: {str(e)}")
        finally:
            conn.close()

    def on_history_window_close(self, window):
        """Handle closing of history window"""
        if window in self.open_windows:
            self.open_windows.remove(window)
        window.destroy()

    def validate_date(self, date_str):
        """Validate date format (YYYY-MM-DD)"""
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    def validate_time(self, time_str):
        """Validate time format (HH:MM)"""
        try:
            datetime.strptime(time_str, "%H:%M")
            return True
        except ValueError:
            return False

    def edit_transaction(self, history_window, history_tree):
        selected_items = history_window.history_tree.selection()
        if not selected_items:
            messagebox.showwarning("Selection Required", "Please select a transaction to edit.")
            return

        transaction_values = history_window.history_tree.item(selected_items[0], "values")
        row_num = transaction_values[0]
        customer_id = history_window.customer_id

        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            formatted_datetime = transaction_values[1]
            action = transaction_values[2]

            dt = datetime.strptime(formatted_datetime, "%Y-%m-%d %I:%M %p")
            date = dt.strftime("%Y-%m-%d")
            time = dt.strftime("%H:%M")

            cursor.execute(
                '''SELECT t.id, t.date, t.time, t.action, t.product, t.quantity, t.amount, t.actual_borrower 
                FROM transactions t
                WHERE t.customer_id = ? AND t.date = ? AND t.time = ? AND t.action = ?''',
                (customer_id, date, time, action)
            )
            transaction = cursor.fetchone()

            if not transaction:
                messagebox.showerror("Error", "Transaction not found.")
                return

            transaction_id, date, time, action, product, quantity, amount, actual_borrower = transaction

            cursor.execute('SELECT display_name FROM customers WHERE id = ?', (customer_id,))
            display_name = cursor.fetchone()[0]

            edit_window = tk.Toplevel(history_window)
            edit_window.title("Edit Transaction")
            edit_window.geometry("400x450")
            edit_window.transient(history_window)
            edit_window.grab_set()
            edit_window.configure(bg=self.current_bg_color)

            # Track this window
            self.open_windows.append(edit_window)
            edit_window.protocol("WM_DELETE_WINDOW", lambda: self.on_edit_window_close(edit_window))

            tk.Label(edit_window, text="Edit Transaction", font=("Arial", 14, "bold"),
                     bg=self.current_bg_color, fg=self.current_fg_color).pack(pady=10)

            form_frame = tk.Frame(edit_window, bg=self.current_bg_color)
            form_frame.pack(pady=10, fill=tk.X, padx=20)

            original_amount = amount
            original_action = action
            original_quantity = quantity

            # Calculate unit price for editing
            if action == "Credit Added" and quantity > 0:
                amount_to_show = amount / quantity
            else:
                amount_to_show = amount

            # Updated label: Actual Borrower -> Co-borrower
            fields = {
                "Date": date,
                "Time": time,
                "Action": action,
                "Product": product,
                "Quantity": quantity,
                "Amount": amount_to_show,  # Show unit price for editing
                "Co-borrower": actual_borrower if actual_borrower else ""
            }

            entries = {}
            row = 0

            for label, value in fields.items():
                tk.Label(form_frame, text=f"{label}:", anchor="w",
                         bg=self.current_bg_color, fg=self.current_fg_color).grid(row=row, column=0, sticky="w", pady=5)

                if label == "Action":
                    # CHANGED HERE: Updated action values
                    entry = ttk.Combobox(form_frame, values=["Credit Added", "Paid"])
                    entry.set(value)
                elif label == "Quantity":
                    entry = tk.Spinbox(form_frame, from_=0, to=1000, width=10,
                                       bg=self.entry_bg, fg=self.entry_fg)
                    entry.delete(0, tk.END)
                    entry.insert(0, value)
                elif label in ["Amount", "Time", "Co-borrower"]:
                    entry = tk.Entry(form_frame, width=15, bg=self.entry_bg, fg=self.entry_fg)
                    entry.insert(0, value)
                else:
                    entry = tk.Entry(form_frame, width=25, bg=self.entry_bg, fg=self.entry_fg)
                    entry.insert(0, value)

                entry.grid(row=row, column=1, sticky="ew", pady=5, padx=5)
                entries[label] = entry
                row += 1

            # Add trace to update amount display when quantity changes for "Credit Added" transactions
            if action == "Credit Added":
                def update_amount(*args):
                    try:
                        new_qty = int(entries["Quantity"].get())
                        unit_price = float(entries["Amount"].get())
                        total_amount = new_qty * unit_price
                        # This just updates the display, actual save happens in save_changes
                    except ValueError:
                        pass

                qty_var = tk.StringVar()
                qty_var.set(quantity)
                qty_var.trace_add("write", update_amount)
                entries["Quantity"].config(textvariable=qty_var)

            form_frame.grid_columnconfigure(1, weight=1)

            btn_frame = tk.Frame(edit_window, bg=self.current_bg_color)
            btn_frame.pack(pady=10)

            def save_changes():
                try:
                    updated_date = entries["Date"].get()
                    updated_time = entries["Time"].get()
                    updated_action = entries["Action"].get()
                    updated_product = entries["Product"].get()
                    updated_borrower = entries["Co-borrower"].get()  # Updated field name

                    # Validate date and time formats
                    if not self.validate_date(updated_date):
                        messagebox.showerror("Input Error", "Invalid date format. Please use YYYY-MM-DD.")
                        return

                    if not self.validate_time(updated_time):
                        messagebox.showerror("Input Error", "Invalid time format. Please use HH:MM.")
                        return

                    try:
                        updated_quantity = int(entries["Quantity"].get())
                    except ValueError:
                        messagebox.showerror("Input Error", "Quantity must be a number.")
                        return

                    # For "Credit Added" transactions, multiply amount by quantity
                    if updated_action == "Credit Added":
                        try:
                            unit_price = float(entries["Amount"].get())
                            updated_amount = unit_price * updated_quantity
                        except ValueError:
                            messagebox.showerror("Input Error", "Amount must be a number.")
                            return
                    else:
                        try:
                            updated_amount = float(entries["Amount"].get())
                        except ValueError:
                            messagebox.showerror("Input Error", "Amount must be a number.")
                            return

                    balance_adjustment = 0

                    if original_action == "Credit Added":
                        if updated_action == "Credit Added":
                            balance_adjustment = updated_amount - original_amount
                        else:
                            balance_adjustment = -original_amount - updated_amount
                    else:
                        if updated_action == "Paid":
                            balance_adjustment = original_amount - updated_amount
                        else:
                            balance_adjustment = original_amount + updated_amount

                    conn = self.get_db_connection()
                    cursor = conn.cursor()

                    cursor.execute(
                        '''UPDATE transactions 
                        SET date = ?, time = ?, action = ?, product = ?, 
                        quantity = ?, amount = ?, actual_borrower = ? 
                        WHERE id = ?''',
                        (
                            updated_date, updated_time, updated_action, updated_product,
                            updated_quantity, updated_amount,
                            updated_borrower if updated_borrower else None,
                            transaction_id
                        )
                    )

                    cursor.execute(
                        'UPDATE customers SET balance = balance + ? WHERE id = ?',
                        (balance_adjustment, customer_id)
                    )

                    cursor.execute('SELECT balance FROM customers WHERE id = ?', (customer_id,))
                    new_balance = cursor.fetchone()[0]

                    conn.commit()

                    # REMOVED: No longer prompt to remove when balance reaches zero
                    # The customer will simply stay in the list

                    self.refresh_transaction_history(history_window, customer_id)
                    self.refresh_table()
                    edit_window.destroy()

                except Exception as e:
                    if conn:
                        conn.rollback()
                    messagebox.showerror("Error", f"An error occurred: {str(e)}")
                finally:
                    if conn:
                        conn.close()

            save_btn = tk.Button(btn_frame, text="Save Changes", command=save_changes,
                                 font=("Arial", 12), bg=self.button_bg, fg=self.button_fg)
            save_btn.pack(side=tk.LEFT, padx=10)

            cancel_btn = tk.Button(btn_frame, text="Cancel", command=edit_window.destroy,
                                   font=("Arial", 12), bg=self.button_bg, fg=self.button_fg)
            cancel_btn.pack(side=tk.LEFT, padx=10)

        except Exception as e:
            messagebox.showerror("Database Error", f"An error occurred: {str(e)}")
        finally:
            conn.close()

    def on_edit_window_close(self, window):
        """Handle closing of edit window"""
        if window in self.open_windows:
            self.open_windows.remove(window)
        window.destroy()

    def delete_transaction(self, history_window, history_tree):
        selected_items = history_window.history_tree.selection()
        if not selected_items:
            messagebox.showwarning("Selection Required", "Please select a transaction to delete.")
            return

        transaction_values = history_window.history_tree.item(selected_items[0])['values']
        formatted_datetime = transaction_values[1]
        transaction_action = transaction_values[2]
        customer_id = history_window.customer_id

        dt = datetime.strptime(formatted_datetime, "%Y-%m-%d %I:%M %p")
        transaction_date = dt.strftime("%Y-%m-%d")
        transaction_time = dt.strftime("%H:%M")

        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                '''SELECT id, action, amount FROM transactions 
                WHERE customer_id = ? AND date = ? AND time = ? AND action = ?''',
                (customer_id, transaction_date, transaction_time, transaction_action)
            )
            transaction = cursor.fetchone()

            if not transaction:
                messagebox.showerror("Error", "Transaction not found.")
                return

            transaction_id, action, amount = transaction

            cursor.execute('SELECT display_name FROM customers WHERE id = ?', (customer_id,))
            display_name = cursor.fetchone()[0]

            if not messagebox.askyesno("Confirm Deletion",
                                       f"Are you sure you want to delete this {action} transaction for ₱{amount:.2f}?"):
                return

            # CHANGED HERE: Updated logic for new action names
            if action == "Paid":
                balance_adjustment = amount
            else:
                balance_adjustment = -amount

            cursor.execute(
                'UPDATE customers SET balance = balance + ? WHERE id = ?',
                (balance_adjustment, customer_id)
            )

            cursor.execute('DELETE FROM transactions WHERE id = ?', (transaction_id,))

            cursor.execute('SELECT COUNT(*) FROM transactions WHERE customer_id = ?', (customer_id,))
            transaction_count = cursor.fetchone()[0]

            cursor.execute('SELECT balance FROM customers WHERE id = ?', (customer_id,))
            new_balance = cursor.fetchone()[0]

            conn.commit()

            # REMOVED: No longer prompt to remove when balance reaches zero or no transactions
            # The customer will simply stay in the list

            self.refresh_transaction_history(history_window, customer_id)
            self.refresh_table()

        except Exception as e:
            conn.rollback()
            messagebox.showerror("Database Error", f"An error occurred: {str(e)}")
        finally:
            conn.close()

    def refresh_transaction_history(self, history_window, customer_id):
        history_tree = history_window.history_tree
        history_tree.delete(*history_tree.get_children())

        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            # Get customer info
            cursor.execute('SELECT display_name, phone_number FROM customers WHERE id = ?', (customer_id,))
            customer = cursor.fetchone()

            if customer:
                display_name, phone_number = customer

                # Update phone number display if exists
                if hasattr(history_window, 'phone_var'):
                    history_window.phone_var.set(phone_number if phone_number else "")

                # Update window title
                history_window.title(f"Transaction History for {display_name}")

            # Get transactions sorted with oldest first (ascending order)
            cursor.execute(
                '''SELECT t.date, t.time, t.action, t.product, t.quantity, t.amount, t.actual_borrower 
                FROM transactions t
                WHERE t.customer_id = ? 
                ORDER BY datetime(t.date || ' ' || t.time) ASC''',
                (customer_id,)
            )
            transactions = cursor.fetchall()

            for row_num, transaction in enumerate(transactions, 1):
                date, time, action, product, quantity, amount, actual_borrower = transaction
                dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
                formatted_datetime = dt.strftime("%Y-%m-%d %I:%M %p")

                # Get the account name to use as default
                cursor.execute('SELECT display_name FROM customers WHERE id = ?', (customer_id,))
                account_name = cursor.fetchone()[0]

                # Use account name if borrower is empty/None
                borrower_display = account_name if not actual_borrower else actual_borrower

                history_tree.insert("", "end", values=(
                    row_num,
                    formatted_datetime,
                    action,
                    product,
                    quantity,
                    f"₱{amount:.2f}",
                    borrower_display
                ))

        except Exception as e:
            messagebox.showerror("Database Error", f"An error occurred: {str(e)}")
        finally:
            conn.close()

    def manual_sync(self):
        """Manual sync for desktop app"""
        try:
            from desktop_sync import desktop_sync
            import tkinter.messagebox as messagebox

            if desktop_sync.is_connected():
                messagebox.showinfo("Syncing", "Syncing desktop data with cloud...")

                # The sync function now returns a success flag and a message
                success, message = desktop_sync.sync_all_data()

                if success:
                    # Show the detailed summary message on success
                    messagebox.showinfo("Sync Complete", message)
                    self.refresh_table()
                else:
                    # The sync function will show its own error popup,
                    # but we can log it here if needed.
                    print(f"Sync failed with message: {message}")
            else:
                messagebox.showerror("Sync Error", "Firebase not configured for desktop app")

        except ImportError as e:
            import tkinter.messagebox as messagebox
            messagebox.showerror("Sync Error", f"Desktop sync module not found: {e}")
        except Exception as e:
            import tkinter.messagebox as messagebox
            messagebox.showerror("Sync Error", f"An unexpected error occurred during sync: {str(e)}")

    def auto_sync(self):
        """Automatically sync data with the cloud and run maintenance tasks."""
        print("Performing automatic background sync...")
        try:
            from desktop_sync import desktop_sync
            if desktop_sync.is_connected():
                success, message = desktop_sync.sync_all_data()
                if success:
                    print("Auto-sync successful. Refreshing table.")
                    self.refresh_table()
                    # Also refresh any open history windows
                    for window in self.open_windows:
                        if hasattr(window, 'customer_id'):
                            self.refresh_transaction_history(window, window.customer_id)
                else:
                    print(f"Auto-sync failed: {message}")
            else:
                print("Firebase not connected, skipping auto-sync.")
        except Exception as e:
            print(f"An error occurred during auto-sync: {e}")
            import traceback
            traceback.print_exc()

        # Run auto-delete for zero balance customers
        self.auto_delete_zero_balance()

        # Schedule the next sync: 300000 milliseconds = 5 minutes
        self.root.after(300000, self.auto_sync)

    def get_db_connection(self):
        """Get database connection for desktop app"""
        if getattr(sys, 'frozen', False):
            app_dir = os.path.dirname(sys.executable)
        else:
            app_dir = os.path.dirname(os.path.abspath(__file__))

        db_path = os.path.join(app_dir, 'data', 'utracker.db')
        return sqlite3.connect(db_path)


if __name__ == "__main__":
    import sys

    login_root = tk.Tk()
    login_app = LoginWindow(login_root)
    login_root.mainloop()
