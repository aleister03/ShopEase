from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '12345',
    'database': 'ShopEaseDB'
}

def simple_password_update():
    """Simply update all user passwords to use demo123"""
    
    # Generate a working hash
    new_password = "demo123"
    password_hash = generate_password_hash(new_password)
    
    print(f"Password: {new_password}")
    print(f"Generated hash: {password_hash}")
    
    # Verify the hash works
    verification = check_password_hash(password_hash, new_password)
    print(f"Hash verification: {'WORKS' if verification else 'BROKEN'}")
    
    if not verification:
        print("ERROR: Hash generation failed!")
        return
    
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Just update all passwords - don't delete anything
        cursor.execute("UPDATE Users SET password = %s", (password_hash,))
        updated_count = cursor.rowcount
        conn.commit()
        
        print(f"\nUpdated {updated_count} user passwords")
        
        # Test a few key accounts
        test_accounts = [
            'admin@shopease.com',
            'seller@shopease.com', 
            'alice@email.com'
        ]
        
        print("\nVerifying updated accounts:")
        for email in test_accounts:
            cursor.execute("SELECT email, role, password FROM Users WHERE email = %s", (email,))
            user = cursor.fetchone()
            if user:
                email, role, stored_hash = user
                is_valid = check_password_hash(stored_hash, new_password)
                print(f"  {email} ({role}): {'LOGIN SHOULD WORK' if is_valid else 'LOGIN WILL FAIL'}")
        
        print(f"\n{'='*50}")
        print("LOGIN CREDENTIALS FOR ALL ACCOUNTS:")
        print(f"Password: {new_password}")
        print("Roles: admin, seller, customer")
        print(f"{'='*50}")
        
        # List all account emails
        cursor.execute("SELECT email, role FROM Users ORDER BY role, email")
        all_users = cursor.fetchall()
        
        current_role = None
        for email, role in all_users:
            if role != current_role:
                print(f"\n{role.upper()} accounts:")
                current_role = role
            print(f"  - {email}")
                
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    simple_password_update()
