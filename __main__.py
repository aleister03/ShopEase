from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import secrets
import hashlib

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

DELIVERY_CHARGE = Decimal('60.00')
LOYALTY_POINTS_RATE = Decimal('0.01')  # 1% of discounted subtotal

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '12345',
    'database': 'shopeasedb'
}

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

def execute_query(query, params=None, fetch=False):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(query, params)
        if fetch:
            result = cursor.fetchall()
        else:
            conn.commit()
            result = cursor.rowcount
        return result
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()

def currency_round(amount):
    """Round currency amounts to 2 decimal places"""
    return Decimal(str(amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

def login_required(role=None):
    def decorator(f):
        def wrapper(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            if role and session.get('role') != role:
                flash('Access denied', 'error')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        wrapper.__name__ = f.__name__
        return wrapper
    return decorator

@app.before_request
def load_user_data():
    if 'user_id' in session and session.get('role') == 'customer':
        user = execute_query("SELECT loyaltyPoints FROM Users WHERE userID = %s", (session['user_id'],), fetch=True)
        if user:
            session['loyalty_points'] = user[0]['loyaltyPoints']

# Authentication Routes
@app.route('/')
def index():
    if 'user_id' in session:
        if session['role'] == 'customer':
            return redirect(url_for('customer_home'))
        elif session['role'] == 'seller':
            return redirect(url_for('seller_dashboard'))
        elif session['role'] == 'admin':
            return redirect(url_for('admin_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = execute_query(
            "SELECT * FROM Users WHERE email = %s AND status = 'active' ORDER BY FIELD(role, 'customer', 'seller', 'admin')",
            (email,), fetch=True
        )
        
        if user and check_password_hash(user[0]['password'], password):
            session['user_id'] = user[0]['userID']
            session['name'] = user[0]['name']
            session['role'] = user[0]['role']
            session['email'] = user[0]['email']
            
            role = user[0]['role']
            if role == 'customer':
                return redirect(url_for('customer_home'))
            elif role == 'seller':
                return redirect(url_for('seller_dashboard'))
            elif role == 'admin':
                return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid credentials or account is banned', 'error')
    
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        address = request.form['address']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        role = request.form.get('role', 'customer')
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('signup.html')
        existing_user = execute_query(
            "SELECT * FROM Users WHERE email = %s", (email,), fetch=True
        )
        if existing_user:
            flash('Email already exists', 'error')
            return render_template('signup.html')
        
        hashed_password = generate_password_hash(password)
        
        execute_query(
            "INSERT INTO Users (name, email, phone, password, role, address, joinDate, loyaltyPoints, status) VALUES (%s, %s, %s, %s, %s, %s, %s, 0, 'active')",
            (name, email, phone, hashed_password, role, address, datetime.now())
        )
        
        flash('Account created successfully! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('signup.html')

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        user = execute_query("SELECT * FROM Users WHERE email = %s", (email,), fetch=True)
        
        if user:
            # In a real app, send email with reset link
            flash('Reset link sent to your email', 'success')
        else:
            flash('Email not found', 'error')
    
    return render_template('forgot_password.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/customer/home')
@login_required('customer')
def customer_home():
    top_products = execute_query("""
        SELECT p.*, i.pricePerUnit, i.currentStock, i.inventoryID, u.name as seller_name
        FROM Products p 
        JOIN Inventory i ON p.productID = i.productID 
        JOIN Users u ON i.sellerID = u.userID
        WHERE i.currentStock > 0 AND u.status = 'active'
        ORDER BY p.dateAdded DESC LIMIT 4
    """, fetch=True)
 
    categories = execute_query(
        "SELECT DISTINCT productCategory FROM Products ORDER BY productCategory",
        fetch=True
    )
    
    discounts = execute_query("""
        SELECT * FROM Discounts 
        WHERE startDate <= %s AND endDate >= %s AND useLimit > 0
        LIMIT 5
    """, (datetime.now(), datetime.now()), fetch=True)
    
    recommended_products = get_recommended_products(session['user_id'], limit=4)
    
    return render_template('customer/home.html', 
                         top_products=top_products, 
                         categories=categories, 
                         discounts=discounts,
                         recommended_products=recommended_products)

@app.route('/customer/product/<int:product_id>')
@login_required('customer')
def product_detail(product_id):
    product = execute_query("""
        SELECT p.*, i.pricePerUnit, i.currentStock, i.inventoryID, u.name as seller_name
        FROM Products p 
        JOIN Inventory i ON p.productID = i.productID 
        JOIN Users u ON i.sellerID = u.userID
        WHERE p.productID = %s AND u.status = 'active'
    """, (product_id,), fetch=True)
    
    if not product:
        flash('Product not found', 'error')
        return redirect(url_for('customer_home'))
    
    product = product[0]
    
    # Track product view activity
    track_user_activity(session['user_id'], product['inventoryID'], 'view')
    
    # Check if product is in wishlist
    in_wishlist = execute_query(
        "SELECT * FROM Wishlist WHERE userID = %s AND productID = %s",
        (session['user_id'], product_id), fetch=True
    )
    
    # Get reviews
    reviews = execute_query("""
        SELECT pr.*, u.name as customer_name
        FROM ProductReview pr
        JOIN Users u ON pr.userID = u.userID
        WHERE pr.productID = %s
        ORDER BY pr.feedbackDate DESC
    """, (product_id,), fetch=True)
    
    return render_template('customer/product_detail.html', 
                         product=product, 
                         reviews=reviews, 
                         in_wishlist=bool(in_wishlist))

@app.route('/customer/add_to_cart', methods=['POST'])
@login_required('customer')
def add_to_cart():
    inventory_id = request.form.get('inventory_id', '').strip()
    quantity = int(request.form.get('quantity', 1))
    if not inventory_id or not inventory_id.isdigit():
        flash('Invalid product selection', 'error')
        return redirect(request.referrer or url_for('customer_home'))
    
    inventory_id = int(inventory_id)
    inventory_check = execute_query("""
        SELECT i.*, p.productName 
        FROM Inventory i 
        JOIN Products p ON i.productID = p.productID
        JOIN Users u ON i.sellerID = u.userID
        WHERE i.inventoryID = %s AND i.currentStock > 0 AND u.status = 'active'
    """, (inventory_id,), fetch=True)
    
    if not inventory_check:
        flash('Product not available', 'error')
        return redirect(request.referrer or url_for('customer_home'))
    if quantity > inventory_check[0]['currentStock']:
        flash(f'Only {inventory_check[0]["currentStock"]} items available', 'error')
        return redirect(request.referrer or url_for('customer_home'))
    existing = execute_query(
        "SELECT * FROM Cart WHERE userID = %s AND inventoryID = %s",
        (session['user_id'], inventory_id), fetch=True
    )
    
    try:
        if existing:
            new_quantity = existing[0]['quantity'] + quantity
            if new_quantity > inventory_check[0]['currentStock']:
                flash(f'Cannot add more items. Only {inventory_check[0]["currentStock"]} available', 'error')
                return redirect(request.referrer or url_for('customer_home'))
            
            execute_query(
                "UPDATE Cart SET quantity = quantity + %s WHERE userID = %s AND inventoryID = %s",
                (quantity, session['user_id'], inventory_id)
            )
        else:
            execute_query(
                "INSERT INTO Cart (userID, inventoryID, quantity, dateAdded) VALUES (%s, %s, %s, %s)",
                (session['user_id'], inventory_id, quantity, datetime.now())
            )
        
        flash(f'{inventory_check[0]["productName"]} added to cart', 'success')
        
    except Exception as e:
        flash('Error adding item to cart', 'error')
        print(f"Error in add_to_cart: {e}") 
        
    return redirect(request.referrer or url_for('customer_home'))

@app.route('/customer/cart')
@login_required('customer')
def view_cart():
    cart_items = execute_query("""
        SELECT c.*, p.productName, i.pricePerUnit, i.currentStock,
               (c.quantity * i.pricePerUnit) as total_price
        FROM Cart c
        JOIN Inventory i ON c.inventoryID = i.inventoryID
        JOIN Products p ON i.productID = p.productID
        WHERE c.userID = %s
    """, (session['user_id'],), fetch=True)
    subtotal = currency_round(sum(Decimal(str(item['total_price'])) for item in cart_items))
    delivery_charge = DELIVERY_CHARGE if cart_items else Decimal('0.00')
    total_amount = currency_round(subtotal + delivery_charge)
    
    return render_template('customer/cart.html', 
                         cart_items=cart_items, 
                         subtotal=float(subtotal), 
                         delivery_charge=float(delivery_charge),
                         total_amount=float(total_amount)) 

@app.route('/customer/update_cart', methods=['POST'])
@login_required('customer')
def update_cart():
    inventory_id = request.form['inventory_id']
    quantity = int(request.form['quantity'])
    
    if quantity > 0:
        execute_query(
            "UPDATE Cart SET quantity = %s WHERE userID = %s AND inventoryID = %s",
            (quantity, session['user_id'], inventory_id)
        )
    else:
        execute_query(
            "DELETE FROM Cart WHERE userID = %s AND inventoryID = %s",
            (session['user_id'], inventory_id)
        )
    
    return redirect(url_for('view_cart'))

@app.route('/customer/checkout')
@login_required('customer')
def checkout():
    cart_items = execute_query("""
        SELECT c.*, p.productName, i.pricePerUnit,
               (c.quantity * i.pricePerUnit) as total_price
        FROM Cart c
        JOIN Inventory i ON c.inventoryID = i.inventoryID
        JOIN Products p ON i.productID = p.productID
        WHERE c.userID = %s
    """, (session['user_id'],), fetch=True)
    
    if not cart_items:
        flash('Cart is empty', 'error')
        return redirect(url_for('view_cart'))
    
    subtotal = currency_round(sum(Decimal(str(item['total_price'])) for item in cart_items))
    discount_amount = Decimal('0.00')
    
    applied_discount = session.get('applied_discount')
    if applied_discount:
        if applied_discount['discountType'] == 'percentage':
            discount_amount = subtotal * (Decimal(str(applied_discount['discountValue'])) / Decimal('100'))
            discount_amount = min(discount_amount, subtotal * Decimal('0.5'))  # Max 50% discount
        else:
            discount_amount = min(Decimal(str(applied_discount['discountValue'])), subtotal)
        
        discount_amount = currency_round(discount_amount)
        session['applied_discount']['discount_amount'] = float(discount_amount)
    
    discounted_subtotal = currency_round(subtotal - discount_amount)
    total_amount = currency_round(discounted_subtotal + DELIVERY_CHARGE)
    earnable_points = int(discounted_subtotal * LOYALTY_POINTS_RATE)
    
    user = execute_query("SELECT * FROM Users WHERE userID = %s", (session['user_id'],), fetch=True)[0]
    
    return render_template('customer/checkout.html', 
                         cart_items=cart_items, 
                         subtotal=float(subtotal),
                         discount_amount=float(discount_amount),
                         discounted_subtotal=float(discounted_subtotal),
                         delivery_charge=float(DELIVERY_CHARGE),
                         total_amount=float(total_amount),
                         earnable_points=earnable_points,
                         applied_discount=applied_discount,
                         user=user)

@app.route('/customer/apply_discount', methods=['POST'])
@login_required('customer')
def apply_discount():
    """Apply discount coupon to session"""
    discount_code = request.form.get('discount_code', '').strip().upper()
    
    if not discount_code:
        return jsonify({'success': False, 'message': 'Please enter a discount code'})
    
    discount = execute_query("""
        SELECT * FROM Discounts 
        WHERE UPPER(discountCode) = %s 
        AND startDate <= %s 
        AND endDate >= %s 
        AND useLimit > 0
    """, (discount_code, datetime.now(), datetime.now()), fetch=True)
    
    if not discount:
        return jsonify({'success': False, 'message': 'Invalid or expired discount code'})
    
    discount = discount[0]
    cart_items = execute_query("""
        SELECT c.*, i.pricePerUnit, (c.quantity * i.pricePerUnit) as total_price
        FROM Cart c
        JOIN Inventory i ON c.inventoryID = i.inventoryID
        WHERE c.userID = %s
    """, (session['user_id'],), fetch=True)
    
    if not cart_items:
        return jsonify({'success': False, 'message': 'Your cart is empty'})
    
    subtotal = currency_round(sum(Decimal(str(item['total_price'])) for item in cart_items))
    
    if discount['discountType'] == 'percentage':
        discount_amount = subtotal * (Decimal(str(discount['discountValue'])) / Decimal('100'))
        discount_amount = min(discount_amount, subtotal * Decimal('0.5'))
    else:
        discount_amount = min(Decimal(str(discount['discountValue'])), subtotal)
    
    discount_amount = currency_round(discount_amount)
    
    session['applied_discount'] = {
        'discountID': discount['discountID'],
        'discountCode': discount['discountCode'],
        'discountType': discount['discountType'],
        'discountValue': float(discount['discountValue']),
        'discount_amount': float(discount_amount)
    }
    
    return jsonify({
        'success': True, 
        'message': f'Discount "{discount_code}" applied successfully!',
        'discount_amount': float(discount_amount),
        'discount_type': discount['discountType'],
        'discount_value': float(discount['discountValue'])
    })

@app.route('/customer/remove_discount', methods=['POST'])
@login_required('customer')
def remove_discount():
    """Remove applied discount from session"""
    session.pop('applied_discount', None)
    return jsonify({'success': True, 'message': 'Discount removed'})

@app.route('/customer/place_order', methods=['POST'])
@login_required('customer')
def place_order():
    delivery_address = request.form['delivery_address']
    cart_items = execute_query("""
        SELECT c.*, i.pricePerUnit
        FROM Cart c
        JOIN Inventory i ON c.inventoryID = i.inventoryID
        WHERE c.userID = %s
    """, (session['user_id'],), fetch=True)
    
    if not cart_items:
        flash('Cart is empty', 'error')
        return redirect(url_for('view_cart'))
    
    applied_discount = session.get('applied_discount')
    discount_id = applied_discount['discountID'] if applied_discount else None
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "INSERT INTO Orders (userID, orderDate, orderStatus) VALUES (%s, %s, 'pending')",
            (session['user_id'], datetime.now())
        )
        order_id = cursor.lastrowid
        
        subtotal = Decimal('0.00')
        for item in cart_items:
            item_total = Decimal(str(item['quantity'])) * Decimal(str(item['pricePerUnit']))
            subtotal = currency_round(subtotal + item_total)
            
            cursor.execute("""
                INSERT INTO OrderItems (orderID, inventoryID, quantity, priceOnSale, discountID)
                VALUES (%s, %s, %s, %s, %s)
            """, (order_id, item['inventoryID'], item['quantity'], float(Decimal(str(item['pricePerUnit']))), discount_id))
            
            cursor.execute(
                "UPDATE Inventory SET currentStock = currentStock - %s WHERE inventoryID = %s",
                (item['quantity'], item['inventoryID'])
            )
            cursor.execute("""
                INSERT INTO UserActivity (userID, inventoryID, activityType, activityDate)
                VALUES (%s, %s, 'purchase', %s)
            """, (session['user_id'], item['inventoryID'], datetime.now()))
        
        discount_amount = Decimal(str(applied_discount['discount_amount'])) if applied_discount else Decimal('0.00')
        discounted_subtotal = currency_round(subtotal - discount_amount)
        total_amount = currency_round(discounted_subtotal + DELIVERY_CHARGE)
        
        cursor.execute("""
            INSERT INTO Payments (orderID, amount, paymentMethod, paymentStatus, transactionDate)
            VALUES (%s, %s, 'cash_on_delivery', 'pending', %s)
        """, (order_id, float(total_amount), datetime.now()))
        
        loyalty_points = int(discounted_subtotal * LOYALTY_POINTS_RATE)
        cursor.execute(
            "UPDATE Users SET loyaltyPoints = loyaltyPoints + %s WHERE userID = %s",
            (loyalty_points, session['user_id'])
        )
        
        if applied_discount:
            cursor.execute(
                "UPDATE Discounts SET useLimit = useLimit - 1 WHERE discountID = %s",
                (applied_discount['discountID'],)
            )
        
        cursor.execute("DELETE FROM Cart WHERE userID = %s", (session['user_id'],))
        session.pop('applied_discount', None)
        
        conn.commit()
        
        discount_msg = f" (Saved ৳{discount_amount:.2f} with discount!)" if discount_amount > 0 else ""
        flash(f'Order placed successfully! Total amount: ৳{total_amount:.2f}{discount_msg} You earned {loyalty_points} loyalty points.', 'success')
        return redirect(url_for('order_history'))
        
    except Exception as e:
        conn.rollback()
        flash(f'Error placing order: {str(e)}', 'error')
        return redirect(url_for('view_cart'))
    finally:
        cursor.close()
        conn.close()

@app.route('/customer/orders')
@login_required('customer')
def order_history():
    orders = execute_query("""
        SELECT o.*, p.amount, p.paymentMethod, p.paymentStatus
        FROM Orders o
        LEFT JOIN Payments p ON o.orderID = p.orderID
        WHERE o.userID = %s
        ORDER BY o.orderDate DESC
    """, (session['user_id'],), fetch=True)
    
    return render_template('customer/order_history.html', orders=orders)

@app.route('/customer/order/<int:order_id>')
@login_required('customer')
def order_detail(order_id):
    order = execute_query("""
        SELECT o.*, p.amount, p.paymentMethod, p.paymentStatus
        FROM Orders o
        LEFT JOIN Payments p ON o.orderID = p.orderID
        WHERE o.orderID = %s AND o.userID = %s
    """, (order_id, session['user_id']), fetch=True)
    
    if not order:
        flash('Order not found', 'error')
        return redirect(url_for('order_history'))
    
    order_items = execute_query("""
        SELECT oi.*, p.productName, (oi.quantity * oi.priceOnSale) as total_price
        FROM OrderItems oi
        JOIN Inventory i ON oi.inventoryID = i.inventoryID
        JOIN Products p ON i.productID = p.productID
        WHERE oi.orderID = %s
    """, (order_id,), fetch=True)
    
    return render_template('customer/order_detail.html', order=order[0], order_items=order_items)

@app.route('/customer/profile', methods=['GET', 'POST'])
@login_required('customer')
def customer_profile():
    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']
        address = request.form['address']
        
        execute_query(
            "UPDATE Users SET name = %s, phone = %s, address = %s WHERE userID = %s",
            (name, phone, address, session['user_id'])
        )
        
        session['name'] = name
        flash('Profile updated successfully', 'success')
    
    user = execute_query("SELECT * FROM Users WHERE userID = %s", (session['user_id'],), fetch=True)[0]
    return render_template('customer/profile.html', user=user)

@app.route('/customer/wishlist')
@login_required('customer')
def wishlist():
    # FIXED: Get wishlisted products with the best available inventory option
    wishlist_items = execute_query("""
        SELECT w.productID, w.dateAdded,
               p.productName, p.productCategory, p.brand,
               i.inventoryID, i.pricePerUnit, i.currentStock, 
               u.name as seller_name
        FROM Wishlist w
        JOIN Products p ON w.productID = p.productID
        JOIN Inventory i ON p.productID = i.productID
        JOIN Users u ON i.sellerID = u.userID
        WHERE w.userID = %s AND i.currentStock > 0 AND u.status = 'active'
        AND i.inventoryID = (
            SELECT i2.inventoryID 
            FROM Inventory i2 
            JOIN Users u2 ON i2.sellerID = u2.userID
            WHERE i2.productID = p.productID 
            AND i2.currentStock > 0 
            AND u2.status = 'active'
            ORDER BY i2.pricePerUnit ASC, i2.currentStock DESC 
            LIMIT 1
        )
        ORDER BY w.dateAdded DESC
    """, (session['user_id'],), fetch=True)
    
    return render_template('customer/wishlist.html', wishlist_items=wishlist_items)

@app.route('/customer/move_to_cart', methods=['POST'])
@login_required('customer')
def move_to_cart():
    inventory_id = request.form.get('inventory_id')
    product_id = request.form.get('product_id')
    quantity = int(request.form.get('quantity', 1))
    
    if not inventory_id:
        flash('Invalid item selected', 'error')
        return redirect(url_for('wishlist'))
    
    try:
        # Add to cart
        existing = execute_query(
            "SELECT * FROM Cart WHERE userID = %s AND inventoryID = %s",
            (session['user_id'], inventory_id), fetch=True
        )
        
        if existing:
            execute_query(
                "UPDATE Cart SET quantity = quantity + %s WHERE userID = %s AND inventoryID = %s",
                (quantity, session['user_id'], inventory_id)
            )
        else:
            execute_query(
                "INSERT INTO Cart (userID, inventoryID, quantity, dateAdded) VALUES (%s, %s, %s, %s)",
                (session['user_id'], inventory_id, quantity, datetime.now())
            )
        
        # Remove from wishlist
        if product_id:
            execute_query(
                "DELETE FROM Wishlist WHERE userID = %s AND productID = %s",
                (session['user_id'], product_id)
            )
        
        flash('Item moved to cart successfully', 'success')
        
    except Exception as e:
        flash(f'Error moving item to cart: {str(e)}', 'error')
    
    return redirect(url_for('wishlist'))

@app.route('/customer/add_to_wishlist', methods=['POST'])
@login_required('customer')
def add_to_wishlist():
    product_id = request.form['product_id']
    existing = execute_query(
        "SELECT * FROM Wishlist WHERE userID = %s AND productID = %s",
        (session['user_id'], product_id), fetch=True
    )
    
    if not existing:
        execute_query(
            "INSERT INTO Wishlist (userID, productID, dateAdded) VALUES (%s, %s, %s)",
            (session['user_id'], product_id, datetime.now())
        )
        
        # Get inventory ID for activity tracking
        inventory = execute_query(
            "SELECT inventoryID FROM Inventory WHERE productID = %s LIMIT 1",
            (product_id,), fetch=True
        )
        
        if inventory:
            track_user_activity(session['user_id'], inventory[0]['inventoryID'], 'wishlist')
        
        flash('Added to wishlist', 'success')
    else:
        flash('Item already in wishlist', 'info')
    
    return redirect(request.referrer)

@app.route('/customer/remove_from_wishlist', methods=['POST'])
@login_required('customer')
def remove_from_wishlist():
    product_id = request.form['product_id']
    
    result = execute_query(
        "DELETE FROM Wishlist WHERE userID = %s AND productID = %s",
        (session['user_id'], product_id)
    )
    
    if result > 0:
        flash('Item removed from wishlist', 'success')
    else:
        flash('Item not found in wishlist', 'error')
    
    return redirect(url_for('wishlist'))

@app.route('/customer/add_review', methods=['POST'])
@login_required('customer')
def add_review():
    product_id = request.form['product_id']
    rating = int(request.form['rating'])
    review = request.form['review']
    
    execute_query("""
        INSERT INTO ProductReview (userID, productID, rating, review, feedbackDate)
        VALUES (%s, %s, %s, %s, %s)
    """, (session['user_id'], product_id, rating, review, datetime.now()))
    
    flash('Review added successfully', 'success')
    return redirect(url_for('product_detail', product_id=product_id))

@app.route('/seller/dashboard')
@login_required('seller')
def seller_dashboard():
    products = execute_query("""
        SELECT p.*, i.pricePerUnit, i.currentStock, i.reorderLevel, i.inventoryID
        FROM Products p
        JOIN Inventory i ON p.productID = i.productID
        WHERE i.sellerID = %s
        ORDER BY p.dateAdded DESC
    """, (session['user_id'],), fetch=True)
    
    orders = execute_query("""
        SELECT o.orderID, o.orderDate, o.orderStatus, u.name as customer_name,
               SUM(oi.quantity * oi.priceOnSale) as amount
        FROM Orders o
        JOIN OrderItems oi ON o.orderID = oi.orderID
        JOIN Inventory i ON oi.inventoryID = i.inventoryID
        JOIN Users u ON o.userID = u.userID
        WHERE i.sellerID = %s
        GROUP BY o.orderID, o.orderDate, o.orderStatus, u.name
        ORDER BY o.orderDate DESC LIMIT 10
    """, (session['user_id'],), fetch=True)
    
    monthly_stats = get_seller_monthly_stats(session['user_id'])
    simple_analytics = get_seller_simple_analytics(session['user_id'])
    
    return render_template('seller/dashboard.html', 
                         products=products, 
                         orders=orders,
                         monthly_stats=monthly_stats,
                         simple_analytics=simple_analytics)

@app.route('/seller/add_product', methods=['GET', 'POST'])
@login_required('seller')
def add_product():
    if request.method == 'POST':
        product_name = request.form['product_name']
        category = request.form['category']
        brand = request.form['brand']
        price = currency_round(Decimal(request.form['price']))
        stock = int(request.form['stock'])
        reorder_level = int(request.form['reorder_level'])
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Insert product
            cursor.execute("""
                INSERT INTO Products (productName, productCategory, brand, dateAdded)
                VALUES (%s, %s, %s, %s)
            """, (product_name, category, brand, datetime.now()))
            
            product_id = cursor.lastrowid
            
            # Insert inventory
            cursor.execute("""
                INSERT INTO Inventory (productID, userID, pricePerUnit, currentStock, reorderLevel)
                VALUES (%s, %s, %s, %s, %s)
            """, (product_id, session['user_id'], float(price), stock, reorder_level))
            
            conn.commit()
            flash('Product added successfully', 'success')
            return redirect(url_for('seller_dashboard'))
            
        except Exception as e:
            conn.rollback()
            flash('Error adding product', 'error')
        finally:
            cursor.close()
            conn.close()
    
    return render_template('seller/add_product.html')

@app.route('/seller/edit_product/<int:inventory_id>', methods=['GET', 'POST'])
@login_required('seller')
def edit_product(inventory_id):
    if request.method == 'POST':
        price = currency_round(Decimal(request.form['price']))
        stock = int(request.form['stock'])
        reorder_level = int(request.form['reorder_level'])
        
        execute_query("""
            UPDATE Inventory SET pricePerUnit = %s, currentStock = %s, reorderLevel = %s
            WHERE inventoryID = %s AND userID = %s
        """, (float(price), stock, reorder_level, inventory_id, session['user_id']))
        
        flash('Product updated successfully', 'success')
        return redirect(url_for('seller_dashboard'))
    
    product = execute_query("""
        SELECT p.*, i.pricePerUnit, i.currentStock, i.reorderLevel, i.inventoryID
        FROM Products p
        JOIN Inventory i ON p.productID = i.productID
        WHERE i.inventoryID = %s AND i.sellerID = %s
    """, (inventory_id, session['user_id']), fetch=True)
    
    if not product:
        flash('Product not found', 'error')
        return redirect(url_for('seller_dashboard'))
    
    return render_template('seller/edit_product.html', product=product[0])

@app.route('/seller/orders')
@login_required('seller')
def seller_orders():
    orders = execute_query("""
        SELECT o.orderID, o.orderDate, o.orderStatus, u.name as customer_name, u.address,
               SUM(oi.quantity * oi.priceOnSale) as amount
        FROM Orders o
        JOIN OrderItems oi ON o.orderID = oi.orderID
        JOIN Inventory i ON oi.inventoryID = i.inventoryID
        JOIN Users u ON o.userID = u.userID
        WHERE i.sellerID = %s
        GROUP BY o.orderID, o.orderDate, o.orderStatus, u.name, u.address
        ORDER BY o.orderDate DESC
    """, (session['user_id'],), fetch=True)
    
    return render_template('seller/orders.html', orders=orders)

@app.route('/seller/update_order_status', methods=['POST'])
@login_required('seller')
def update_order_status():
    order_id = request.form['order_id']
    status = request.form['status']
    
    execute_query(
        "UPDATE Orders SET orderStatus = %s WHERE orderID = %s",
        (status, order_id)
    )
    
    flash('Order status updated', 'success')
    return redirect(url_for('seller_orders'))

@app.route('/seller/order/<int:order_id>')
@login_required('seller')
def seller_order_detail(order_id):
    order = execute_query("""
        SELECT o.*, u.name as customer_name, u.email as customer_email, 
               u.phone as customer_phone, u.address, p.amount as total_order_amount, 
               p.paymentMethod, p.paymentStatus,
               (SELECT SUM(oi.quantity * oi.priceOnSale) 
                FROM OrderItems oi 
                JOIN Inventory i2 ON oi.inventoryID = i2.inventoryID
                WHERE oi.orderID = o.orderID AND i2.sellerID = %s) as seller_earnings
        FROM Orders o
        JOIN Users u ON o.userID = u.userID
        LEFT JOIN Payments p ON o.orderID = p.orderID
        WHERE o.orderID = %s 
        AND EXISTS (
            SELECT 1 FROM OrderItems oi2 
            JOIN Inventory i3 ON oi2.inventoryID = i3.inventoryID 
            WHERE oi2.orderID = o.orderID AND i3.sellerID = %s
        )
    """, (session['user_id'], order_id, session['user_id']), fetch=True)
    
    if not order:
        flash('Order not found or access denied', 'error')
        return redirect(url_for('seller_orders'))
    order_items = execute_query("""
        SELECT oi.*, p.productName, p.brand, p.productCategory,
               (oi.quantity * oi.priceOnSale) as total_price
        FROM OrderItems oi
        JOIN Inventory i ON oi.inventoryID = i.inventoryID
        JOIN Products p ON i.productID = p.productID
        WHERE oi.orderID = %s AND i.sellerID = %s
    """, (order_id, session['user_id']), fetch=True)
    
    return render_template('seller/order_detail.html', order=order[0], order_items=order_items)

def get_seller_monthly_stats(seller_id):
    """Get current month statistics for seller - Fixed to work with actual data"""
    current_month_start = datetime(2025, 8, 1)
    next_month = datetime(2025, 9, 1)
    
    stats = execute_query("""
        SELECT 
            COUNT(DISTINCT o.orderID) as orders_count,
            COALESCE(SUM(oi.quantity * oi.priceOnSale), 0) as total_revenue,
            COALESCE(SUM(oi.quantity), 0) as items_sold,
            CASE 
                WHEN COUNT(DISTINCT o.orderID) > 0 
                THEN COALESCE(SUM(oi.quantity * oi.priceOnSale), 0) / COUNT(DISTINCT o.orderID)
                ELSE 0 
            END as avg_order_value
        FROM Orders o
        JOIN OrderItems oi ON o.orderID = oi.orderID
        JOIN Inventory i ON oi.inventoryID = i.inventoryID
        WHERE i.sellerID = %s 
        AND o.orderDate >= %s 
        AND o.orderDate < %s
        AND o.orderStatus != 'cancelled'
    """, (seller_id, current_month_start, next_month), fetch=True)
    
    return stats[0] if stats else {
        'orders_count': 0,
        'total_revenue': 0,
        'items_sold': 0,
        'avg_order_value': 0
    }

def get_seller_simple_analytics(seller_id):
    """Get comprehensive analytics for seller popup - Fixed version"""
    best_month = execute_query("""
        SELECT 
            MONTHNAME(o.orderDate) as month_name,
            YEAR(o.orderDate) as year,
            COUNT(DISTINCT o.orderID) as order_count,
            SUM(oi.quantity * oi.priceOnSale) as revenue
        FROM Orders o
        JOIN OrderItems oi ON o.orderID = oi.orderID
        JOIN Inventory i ON oi.inventoryID = i.inventoryID
        WHERE i.sellerID = %s 
        AND o.orderStatus != 'cancelled'
        GROUP BY YEAR(o.orderDate), MONTH(o.orderDate), MONTHNAME(o.orderDate)
        HAVING revenue > 0
        ORDER BY revenue DESC
        LIMIT 1
    """, (seller_id,), fetch=True)
    
    best_product = execute_query("""
        SELECT 
            p.productName,
            p.brand,
            SUM(oi.quantity) as total_sold,
            SUM(oi.quantity * oi.priceOnSale) as total_revenue
        FROM OrderItems oi
        JOIN Inventory i ON oi.inventoryID = i.inventoryID
        JOIN Products p ON i.productID = p.productID
        JOIN Orders o ON oi.orderID = o.orderID
        WHERE i.sellerID = %s 
        AND o.orderStatus != 'cancelled'
        GROUP BY p.productID, p.productName, p.brand
        HAVING total_sold > 0
        ORDER BY total_sold DESC
        LIMIT 1
    """, (seller_id,), fetch=True)
    monthly_comparison = execute_query("""
        SELECT 
            -- August 2025 data (current month in your data)
            SUM(CASE WHEN YEAR(o.orderDate) = 2025 AND MONTH(o.orderDate) = 8
                     THEN oi.quantity * oi.priceOnSale ELSE 0 END) as current_revenue,
            COUNT(DISTINCT CASE WHEN YEAR(o.orderDate) = 2025 AND MONTH(o.orderDate) = 8
                     THEN o.orderID ELSE NULL END) as current_orders,
            SUM(CASE WHEN YEAR(o.orderDate) = 2025 AND MONTH(o.orderDate) = 8
                     THEN oi.quantity ELSE 0 END) as current_items,
                     
            -- July 2025 data (previous month in your data)
            SUM(CASE WHEN YEAR(o.orderDate) = 2025 AND MONTH(o.orderDate) = 7
                     THEN oi.quantity * oi.priceOnSale ELSE 0 END) as previous_revenue,
            COUNT(DISTINCT CASE WHEN YEAR(o.orderDate) = 2025 AND MONTH(o.orderDate) = 7
                     THEN o.orderID ELSE NULL END) as previous_orders,
            SUM(CASE WHEN YEAR(o.orderDate) = 2025 AND MONTH(o.orderDate) = 7
                     THEN oi.quantity ELSE 0 END) as previous_items
        FROM Orders o
        JOIN OrderItems oi ON o.orderID = oi.orderID
        JOIN Inventory i ON oi.inventoryID = i.inventoryID
        WHERE i.sellerID = %s 
        AND o.orderStatus != 'cancelled'
        AND (
            (YEAR(o.orderDate) = 2025 AND MONTH(o.orderDate) = 7) OR
            (YEAR(o.orderDate) = 2025 AND MONTH(o.orderDate) = 8)
        )
    """, (seller_id,), fetch=True)
    
    comparison_data = monthly_comparison[0] if monthly_comparison else {
        'current_revenue': 0, 'current_orders': 0, 'current_items': 0,
        'previous_revenue': 0, 'previous_orders': 0, 'previous_items': 0
    }
    
    current_avg = float(comparison_data['current_revenue']) / comparison_data['current_orders'] if comparison_data['current_orders'] > 0 else 0
    previous_avg = float(comparison_data['previous_revenue']) / comparison_data['previous_orders'] if comparison_data['previous_orders'] > 0 else 0
    
    comparison_data['current_avg'] = current_avg
    comparison_data['previous_avg'] = previous_avg
    
    if best_month:
        best_month[0]['month'] = f"{best_month[0]['month_name']} {best_month[0]['year']}"
    
    return {
        'best_month': best_month[0] if best_month else None,
        'best_product': best_product[0] if best_product else None,
        'monthly_comparison': comparison_data
    }

# Admin Routes
@app.route('/admin/dashboard')
@login_required('admin')
def admin_dashboard():
    # Get statistics
    stats = {
        'total_users': execute_query("SELECT COUNT(*) as count FROM Users WHERE role != 'admin'", fetch=True)[0]['count'],
        'total_orders': execute_query("SELECT COUNT(*) as count FROM Orders", fetch=True)[0]['count'],
        'total_products': execute_query("SELECT COUNT(*) as count FROM Products", fetch=True)[0]['count'],
        'active_discounts': execute_query("SELECT COUNT(*) as count FROM Discounts WHERE endDate >= %s", (datetime.now(),), fetch=True)[0]['count']
    }
    
    return render_template('admin/dashboard.html', stats=stats)

@app.route('/admin/users')
@login_required('admin')
def admin_users():
    users = execute_query("""
        SELECT userID, name, email, phone, role, joinDate, loyaltyPoints, status
        FROM Users WHERE role != 'admin'
        ORDER BY joinDate DESC
    """, fetch=True)
    
    return render_template('admin/users.html', users=users)

@app.route('/admin/update_payment_status', methods=['POST'])
@login_required('admin')
def update_payment_status():
    order_id = request.form['order_id']
    payment_status = request.form['payment_status']
    
    existing_payment = execute_query(
        "SELECT orderID FROM Payments WHERE orderID = %s", 
        (order_id,), fetch=True
    )
    
    if existing_payment:
        execute_query(
            "UPDATE Payments SET paymentStatus = %s WHERE orderID = %s",
            (payment_status, order_id)
        )
    else:
        order_items_total = execute_query("""
            SELECT COALESCE(SUM(oi.quantity * oi.priceOnSale), 0) as subtotal
            FROM OrderItems oi 
            WHERE oi.orderID = %s
        """, (order_id,), fetch=True)
        
        subtotal = currency_round(Decimal(str(order_items_total[0]['subtotal']))) if order_items_total else Decimal('0.00')
        total_amount = currency_round(subtotal + DELIVERY_CHARGE)
        
        execute_query("""
            INSERT INTO Payments (orderID, amount, paymentMethod, paymentStatus, transactionDate)
            VALUES (%s, %s, 'cash_on_delivery', %s, %s)
        """, (order_id, float(total_amount), payment_status, datetime.now()))
    
    flash('Payment status updated successfully', 'success')
    return redirect(url_for('admin_orders'))

@app.route('/admin/sync_payment_status', methods=['POST'])
@login_required('admin')
def sync_payment_status():
    """Auto-sync payment status based on business logic"""
    delivered_updates = execute_query("""
        UPDATE Payments p
        JOIN Orders o ON p.orderID = o.orderID
        SET p.paymentStatus = 'completed'
        WHERE o.orderStatus = 'delivered' AND p.paymentStatus = 'pending'
    """)
    orders_without_payments = execute_query("""
        SELECT o.orderID, o.orderStatus, COALESCE(SUM(oi.quantity * oi.priceOnSale), 0) as subtotal
        FROM Orders o
        JOIN OrderItems oi ON o.orderID = oi.orderID
        LEFT JOIN Payments p ON o.orderID = p.orderID
        WHERE p.orderID IS NULL
        GROUP BY o.orderID, o.orderStatus
    """, fetch=True)
    
    created_records = 0
    for order in orders_without_payments:
        if order['orderStatus'] == 'delivered':
            payment_status = 'completed'
        elif order['orderStatus'] == 'cancelled':
            payment_status = 'failed'
        else:
            payment_status = 'pending'
        total_amount = currency_round(Decimal(str(order['subtotal'])) + DELIVERY_CHARGE)
        
        execute_query("""
            INSERT INTO Payments (orderID, amount, paymentMethod, paymentStatus, transactionDate)
            VALUES (%s, %s, 'cash_on_delivery', %s, %s)
        """, (order['orderID'], float(total_amount), payment_status, datetime.now()))
        
        created_records += 1
    
    flash(f'Payment status synchronized successfully. Created {created_records} missing payment records.', 'success')
    return redirect(url_for('admin_orders'))

@app.route('/admin/toggle_user_status', methods=['POST'])
@login_required('admin')
def toggle_user_status():
    user_id = request.form['user_id']
    action = request.form['action']
    
    new_status = 'banned' if action == 'ban' else 'active'
    
    execute_query(
        "UPDATE Users SET status = %s WHERE userID = %s AND role != 'admin'",
        (new_status, user_id)
    )
    
    flash(f'User {action}ned successfully', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/orders')
@login_required('admin')
def admin_orders():
    orders = execute_query("""
        SELECT o.orderID, o.userID, o.orderDate, o.orderStatus, 
               u.name as customer_name, 
               p.amount, p.paymentStatus
        FROM Orders o
        JOIN Users u ON o.userID = u.userID
        LEFT JOIN Payments p ON o.orderID = p.orderID
        ORDER BY o.orderDate DESC
    """, fetch=True)
    
    return render_template('admin/orders.html', orders=orders)

@app.route('/admin/discounts')
@login_required('admin')
def admin_discounts():
    discounts = execute_query("""
        SELECT *, 
               COALESCE(useLimit, 0) as useLimit
        FROM Discounts 
        ORDER BY startDate DESC
    """, fetch=True)
    
    from datetime import date
    today = date.today()
    
    return render_template('admin/discounts.html', discounts=discounts, today=today)

@app.route('/admin/add_discount', methods=['POST'])
@login_required('admin')
def add_discount():
    discount_code = request.form['discount_code']
    discount_type = request.form['discount_type']
    discount_value = currency_round(Decimal(request.form['discount_value']))
    start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d')
    end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d')
    use_limit = int(request.form.get('use_limit', 0))
    
    execute_query("""
        INSERT INTO Discounts (discountCode, discountType, discountValue, startDate, endDate, useLimit)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (discount_code, discount_type, float(discount_value), start_date, end_date, use_limit))
    
    flash('Discount added successfully', 'success')
    return redirect(url_for('admin_discounts'))

# Search functionality
@app.route('/search')
@login_required('customer')
def search():
    query = request.args.get('q', '')
    category = request.args.get('category', '')
    
    search_query = """
        SELECT p.*, i.pricePerUnit, i.currentStock, u.name as seller_name
        FROM Products p 
        JOIN Inventory i ON p.productID = i.productID 
        JOIN Users u ON i.sellerID = u.userID
        WHERE i.currentStock > 0 AND u.status = 'active'
    """
    params = []
    
    if query:
        search_query += " AND (p.productName LIKE %s OR p.brand LIKE %s)"
        params.extend([f'%{query}%', f'%{query}%'])
    
    if category:
        search_query += " AND p.productCategory = %s"
        params.append(category)
    
    search_query += " ORDER BY p.dateAdded DESC"
    
    products = execute_query(search_query, params, fetch=True)
    
    return render_template('customer/search_results.html', products=products, query=query, category=category)

def track_user_activity(user_id, inventory_id, activity_type):
    try:
        execute_query("""
            INSERT INTO UserActivity (userID, inventoryID, activityType, activityDate)
            VALUES (%s, %s, %s, %s)
        """, (user_id, inventory_id, activity_type, datetime.now()))
    except Exception as e:
        pass

def get_recommended_products(user_id, limit=4):
    """Get personalized product recommendations based on user activity"""
    
    # Strategy 1: Products from categories the user has interacted with
    category_based = execute_query("""
        SELECT DISTINCT p.*, i.pricePerUnit, i.currentStock, i.inventoryID, u.name as seller_name
        FROM Products p 
        JOIN Inventory i ON p.productID = i.productID 
        JOIN Users u ON i.sellerID = u.userID
        WHERE i.currentStock > 0 AND u.status = 'active'
        AND p.productCategory IN (
            SELECT DISTINCT p2.productCategory
            FROM UserActivity ua
            JOIN Inventory i2 ON ua.inventoryID = i2.inventoryID
            JOIN Products p2 ON i2.productID = p2.productID
            WHERE ua.userID = %s
        )
        AND i.inventoryID NOT IN (
            SELECT inventoryID FROM UserActivity 
            WHERE userID = %s AND activityType = 'purchase'
        )
        ORDER BY RAND()
        LIMIT %s
    """, (user_id, user_id, limit), fetch=True)
    
    if len(category_based) >= limit:
        return category_based[:limit]
    
    # Strategy 2: Popular products
    popular_products = execute_query("""
        SELECT p.*, i.pricePerUnit, i.currentStock, i.inventoryID, u.name as seller_name,
               COUNT(ua.inventoryID) as activity_count
        FROM Products p 
        JOIN Inventory i ON p.productID = i.productID 
        JOIN Users u ON i.sellerID = u.userID
        LEFT JOIN UserActivity ua ON i.inventoryID = ua.inventoryID
        WHERE i.currentStock > 0 AND u.status = 'active'
        AND i.inventoryID NOT IN (
            SELECT inventoryID FROM UserActivity 
            WHERE userID = %s AND activityType = 'purchase'
        )
        GROUP BY i.inventoryID
        ORDER BY activity_count DESC, p.dateAdded DESC
        LIMIT %s
    """, (user_id, limit - len(category_based)), fetch=True)
    
    all_recommendations = category_based + popular_products
    
    seen = set()
    unique_recommendations = []
    for product in all_recommendations:
        if product['inventoryID'] not in seen:
            seen.add(product['inventoryID'])
            unique_recommendations.append(product)
            if len(unique_recommendations) >= limit:
                break
    
    return unique_recommendations

@app.route('/api/user_points')
@login_required('customer')
def get_user_points():
    user = execute_query("SELECT loyaltyPoints FROM Users WHERE userID = %s", (session['user_id'],), fetch=True)
    if user:
        session['loyalty_points'] = user[0]['loyaltyPoints']
        return jsonify({'points': user[0]['loyaltyPoints']})
    return jsonify({'points': 0})

@app.route('/seller/analytics_popup')
@login_required('seller')
def analytics_popup():
    analytics = get_seller_simple_analytics(session['user_id'])
    return render_template('seller/analytics_popup.html', analytics=analytics)

if __name__ == '__main__':
    app.run(debug=True)
