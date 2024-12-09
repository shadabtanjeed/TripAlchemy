import firebase_admin
from firebase_admin import credentials
import os


def initialize_firebase():
    try:
        if not firebase_admin._apps:
            cred_path = os.path.join(
                os.path.dirname(__file__), "serviceAccountKey.json"
            )
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
            print("Firebase initialization successful!")
        else:
            print("Firebase already initialized")
        return True
    except Exception as e:
        print(f"Firebase initialization failed: {str(e)}")
        return False
