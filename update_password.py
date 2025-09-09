from werkzeug.security import generate_password_hash
import mysql.connector

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '12345',
    'database': 'ShopEaseDB'
}

def simple_password_update():
    """Update all user passwords to demo123 and print Done"""
    
    new_password = "demo123"
    password_hash = generate_password_hash(new_password)

    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Update all passwords
        cursor.execute("UPDATE Users SET password = %s", (password_hash,))
        conn.commit()

        print("Done")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    simple_password_update()
