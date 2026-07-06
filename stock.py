from database import get_connection
import math  

def log_dough_made(flavour, portions):
    conn = get_connection()
    cursor = conn.cursor()
    
    # get base yield and calculate multiplier
    cursor.execute('SELECT base_yield FROM recipes WHERE name = %s', (flavour,))
    base_yield = cursor.fetchone()[0]
    multiplier = portions / base_yield
    
    # deduct ingredients
    cursor.execute('''
        SELECT ingredient_name, amount FROM recipe_ingredients
        WHERE recipe_id = (SELECT id FROM recipes WHERE name = %s)
    ''', (flavour,))
    
    for ingredient_name, amount in cursor.fetchall():
        scaled_amount = amount * multiplier
        cursor.execute('''
            UPDATE ingredient_stock
            SET quantity = quantity - %s
            WHERE ingredient_name = %s
        ''', (scaled_amount, ingredient_name))
    
    # increase frozen stock
    cursor.execute('''
        UPDATE cookie_stock
        SET quantity = quantity + %s
        WHERE flavour = %s
    ''', (portions, flavour))
    
    conn.commit()
    conn.close()
    print(f"Logged {portions} portions of {flavour}. Ingredients deducted.")

def log_order_delivered(order_id):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT flavour, quantity FROM order_items
        WHERE order_id = %s
    ''', (order_id,))
    
    items = cursor.fetchall()
    
    for flavour, quantity in items:
        cursor.execute('''
            UPDATE cookie_stock
            SET quantity = quantity - %s,
                reserved = reserved - %s
            WHERE flavour = %s
        ''', (quantity, quantity, flavour))
    
    cursor.execute('''
        UPDATE orders SET status = 'delivered'
        WHERE id = %s
    ''', (order_id,))
    
    deduct_packaging_for_order(order_id)
    
    conn.commit()
    conn.close()
    from cashflow import add_transaction
    conn2 = get_connection()
    cursor2 = conn2.cursor()
    cursor2.execute('SELECT revenue FROM orders WHERE id = %s', (order_id,))
    revenue = cursor2.fetchone()[0]
    conn2.close()
    if revenue:
        add_transaction('income', 'order', revenue, f'Order #{order_id} delivered')
    print(f"Order #{order_id} marked as delivered. Stock updated.")

def check_low_stock():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT flavour, quantity, reserved, low_stock_threshold,
               (quantity - reserved) as available
        FROM cookie_stock
        WHERE (quantity - reserved) <= low_stock_threshold
    ''')
    
    low = cursor.fetchall()
    conn.close()
    return low

def check_low_ingredients():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT ingredient_name, quantity, low_stock_threshold
        FROM ingredient_stock
        WHERE quantity <= low_stock_threshold
    ''')
    
    low = cursor.fetchall()
    conn.close()
    return low

if __name__ == '__main__':
    print("Testing stock module...")
    
    log_dough_made('the_brownie_slapp', 12)
    
    print("\nCookie stock after making dough:")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT flavour, quantity FROM cookie_stock')
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]}")
    conn.close()
    
    print("\nLow stock alerts:")
    low = check_low_stock()
    if low:
        for flavour, qty, threshold in low:
            print(f"  {flavour}: {qty} portions (threshold: {threshold})")
    else:
        print("  All good!")

def check_stock_for_order(items):
    conn = get_connection()
    cursor = conn.cursor()
    
    warnings = []
    
    for flavour, quantity_needed in items.items():
        cursor.execute('''
            SELECT quantity - reserved as available
            FROM cookie_stock
            WHERE flavour = %s
        ''', (flavour,))
        
        result = cursor.fetchone()
        available = result[0] if result else 0
        
        if available < quantity_needed:
            warnings.append({
                'flavour': flavour,
                'needed': quantity_needed,
                'available': available,
                'shortage': quantity_needed - available
            })
    
    conn.close()
    return warnings

def check_low_packaging():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT box_name, stock, low_stock_threshold
        FROM packaging
        WHERE stock <= low_stock_threshold
    ''')
    
    low = cursor.fetchall()
    conn.close()
    return low

def deduct_packaging_for_order(order_id):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT SUM(quantity) FROM order_items
        WHERE order_id = %s
    ''', (order_id,))
    
    total_cookies = cursor.fetchone()[0]
    
    cursor.execute('''
        SELECT id, capacity FROM packaging
        WHERE box_name = 'standard_box'
    ''')
    
    box = cursor.fetchone()
    if box:
        box_id, capacity = box
        boxes_needed = math.ceil(total_cookies / capacity)
        
        cursor.execute('''
            UPDATE packaging
            SET stock = stock - %s
            WHERE id = %s
        ''', (boxes_needed, box_id))
    
    conn.commit()
    conn.close()

def set_ingredient_stock(ingredient_name, quantity):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE ingredient_stock
        SET quantity = %s
        WHERE ingredient_name = %s
    ''', (quantity, ingredient_name))
    
    conn.commit()
    conn.close()
    print(f"Updated {ingredient_name} stock to {quantity}")

def add_ingredient_stock(ingredient_name, quantity):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE ingredient_stock
        SET quantity = quantity + %s
        WHERE ingredient_name = %s
    ''', (quantity, ingredient_name))
    
    conn.commit()
    conn.close()
    print(f"Added {quantity} to {ingredient_name} stock")

def reserve_stock(order_id):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT flavour, quantity FROM order_items
        WHERE order_id = %s
    ''', (order_id,))
    
    items = cursor.fetchall()
    
    for flavour, quantity in items:
        cursor.execute('''
            UPDATE cookie_stock
            SET reserved = reserved + %s
            WHERE flavour = %s
        ''', (quantity, flavour))
    
    conn.commit()
    conn.close()

def release_reservation(order_id):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT flavour, quantity FROM order_items
        WHERE order_id = %s
    ''', (order_id,))
    
    items = cursor.fetchall()
    
    for flavour, quantity in items:
        cursor.execute('''
            UPDATE cookie_stock
            SET reserved = reserved - %s
            WHERE flavour = %s
        ''', (quantity, flavour))
    
    conn.commit()
    conn.close()    

def set_cookie_stock(flavour, quantity):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE cookie_stock
        SET quantity = %s
        WHERE flavour = %s
    ''', (quantity, flavour))
    
    conn.commit()
    conn.close()
    print(f"Updated {flavour} stock to {quantity}")

def add_cookie_stock(flavour, quantity):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE cookie_stock
        SET quantity = quantity + %s
        WHERE flavour = %s
    ''', (quantity, flavour))
    
    conn.commit()
    conn.close()
    print(f"Added {quantity} to {flavour} stock")