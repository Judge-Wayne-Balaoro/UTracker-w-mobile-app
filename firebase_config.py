# firebase_config.py
import firebase_admin
from firebase_admin import credentials, firestore
import os
import json


def initialize_firebase():
    """Initialize Firebase Admin SDK"""
    try:
        # Check if already initialized
        firebase_admin.get_app()
        print("Firebase already initialized")
        return firestore.client()
    except ValueError:
        # Initialize Firebase
        service_account_path = os.path.join(os.path.dirname(__file__), 'serviceAccountKey.json')

        if os.path.exists(service_account_path):
            cred = credentials.Certificate(service_account_path)
            firebase_admin.initialize_app(cred)
            print("✅ Firebase initialized with service account")
            return firestore.client()
        else:
            print("❌ Firebase not initialized - serviceAccountKey.json not found")
            print(f"Looking for file at: {service_account_path}")
            return None


# Initialize immediately
db = initialize_firebase()