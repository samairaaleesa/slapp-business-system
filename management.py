from database import get_connection

def get_all_recipes():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, name, base_yield, is_active
        FROM recipes
        ORDER BY name
    ''')
    
    recipes = cursor.fetchall()
    conn.close()
    return recipes

def get_recipe_with_ingredients(recipe_name):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT r.id, r.name, r.base_yield,
               ri.ingredient_name, ri.amount, ri.unit
        FROM recipes r
        JOIN recipe_ingredients ri ON r.id = ri.recipe_id
        WHERE r.name = %s AND r.is_active = 1
        ORDER BY ri.ingredient_name
    ''', (recipe_name,))
    
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return None
    
    recipe = {
        'id': rows[0][0],
        'name': rows[0][1],
        'base_yield': rows[0][2],
        'ingredients': []
    }
    
    for row in rows:
        recipe['ingredients'].append({
            'ingredient': row[3],
            'amount': row[4],
            'unit': row[5]
        })
    
    return recipe

def add_recipe(name, base_yield):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO recipes (name, base_yield)
        VALUES (%s, %s)
        ON CONFLICT (name) DO NOTHING
        RETURNING id
    ''', (name, base_yield))
    
    result = cursor.fetchone()
    
    cursor.execute('''
        INSERT INTO cookie_stock (flavour, quantity)
        VALUES (%s, 0)
        ON CONFLICT (flavour) DO NOTHING
    ''', (name,))
    
    cursor.execute('''
        INSERT INTO pricing (flavour, price_per_cookie)
        VALUES (%s, 99)
        ON CONFLICT (flavour) DO NOTHING
    ''', (name,))
    
    conn.commit()
    conn.close()
    print(f"Recipe {name} added!")

def delete_recipe(recipe_name):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE recipes SET is_active = 0
        WHERE name = %s
    ''', (recipe_name,))
    
    conn.commit()
    conn.close()
    print(f"Recipe {recipe_name} deactivated!")

def add_ingredient_to_recipe(recipe_name, ingredient_name, amount, unit, stage='dough'):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT id FROM recipes WHERE name = %s', (recipe_name,))
    recipe = cursor.fetchone()

    if not recipe:
        print(f"Recipe {recipe_name} not found!")
        return

    cursor.execute('''
        INSERT INTO recipe_ingredients (recipe_id, ingredient_name, amount, unit, stage)
        VALUES (%s, %s, %s, %s, %s)
    ''', (recipe[0], ingredient_name, amount, unit, stage))

    conn.commit()
    conn.close()
    print(f"Added {ingredient_name} ({stage}) to {recipe_name}")

def remove_ingredient_from_recipe(ingredient_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('DELETE FROM recipe_ingredients WHERE id = %s', (ingredient_id,))

    conn.commit()
    conn.close()
    print(f"Removed recipe_ingredients row #{ingredient_id}")

def update_ingredient_amount(ingredient_id, new_amount):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE recipe_ingredients
        SET amount = %s
        WHERE id = %s
    ''', (new_amount, ingredient_id))

    conn.commit()
    conn.close()
    print(f"Updated recipe_ingredients row #{ingredient_id} to {new_amount}")

def update_flavour_price(flavour, new_price):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE pricing SET price_per_cookie = %s
        WHERE flavour = %s
    ''', (new_price, flavour))
    
    conn.commit()
    conn.close()
    print(f"Updated {flavour} price to ₹{new_price}")

def get_all_pricing():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT flavour, price_per_cookie
        FROM pricing
        WHERE is_active = 1
        ORDER BY flavour
    ''')
    
    prices = cursor.fetchall()
    conn.close()
    return prices

def add_combo(name, buy_quantity, free_quantity, discount_percentage=0):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO combos (name, buy_quantity, free_quantity, discount_percentage)
        VALUES (%s, %s, %s, %s)
    ''', (name, buy_quantity, free_quantity, discount_percentage))
    
    conn.commit()
    conn.close()
    print(f"Combo {name} added!")

def deactivate_combo(combo_id):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE combos SET is_active = 0
        WHERE id = %s
    ''', (combo_id,))
    
    conn.commit()
    conn.close()
    print(f"Combo #{combo_id} deactivated!")

def get_all_combos():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, name, buy_quantity, free_quantity, 
               discount_percentage, is_active
        FROM combos
        ORDER BY is_active DESC, name
    ''')
    
    combos = cursor.fetchall()
    conn.close()
    return combos

def add_delivery_zone(zone_name, typical_porter_cost=0):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO delivery_zones (zone_name, typical_porter_cost)
        VALUES (%s, %s)
        ON CONFLICT (zone_name) DO NOTHING
    ''', (zone_name, typical_porter_cost))

    conn.commit()
    conn.close()
    print(f"Delivery zone {zone_name} added!")

def update_delivery_zone(zone_id, zone_name=None, typical_porter_cost=None):
    conn = get_connection()
    cursor = conn.cursor()

    if zone_name:
        cursor.execute('UPDATE delivery_zones SET zone_name = %s WHERE id = %s', (zone_name, zone_id))

    if typical_porter_cost is not None:
        cursor.execute('UPDATE delivery_zones SET typical_porter_cost = %s WHERE id = %s', (typical_porter_cost, zone_id))

    conn.commit()
    conn.close()

def deactivate_delivery_zone(zone_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('UPDATE delivery_zones SET is_active = 0 WHERE id = %s', (zone_id,))

    conn.commit()
    conn.close()
    print(f"Delivery zone #{zone_id} deactivated!")

def activate_delivery_zone(zone_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('UPDATE delivery_zones SET is_active = 1 WHERE id = %s', (zone_id,))

    conn.commit()
    conn.close()

def get_all_delivery_zones():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, zone_name, typical_porter_cost, is_active
        FROM delivery_zones
        ORDER BY is_active DESC, zone_name
    ''')

    zones = cursor.fetchall()
    conn.close()
    return zones

def update_packaging(box_name, capacity=None, cost_per_box=None,
                     stock=None, low_stock_threshold=None):
    conn = get_connection()
    cursor = conn.cursor()
    
    if capacity:
        cursor.execute('''
            UPDATE packaging SET capacity = %s WHERE box_name = %s
        ''', (capacity, box_name))
    
    if cost_per_box:
        cursor.execute('''
            UPDATE packaging SET cost_per_box = %s WHERE box_name = %s
        ''', (cost_per_box, box_name))
    
    if stock:
        cursor.execute('''
            UPDATE packaging SET stock = stock + %s WHERE box_name = %s
        ''', (stock, box_name))
    
    if low_stock_threshold:
        cursor.execute('''
            UPDATE packaging SET low_stock_threshold = %s WHERE box_name = %s
        ''', (low_stock_threshold, box_name))
    
    conn.commit()
    conn.close()
    print(f"Packaging {box_name} updated!")

def add_packaging(box_name, capacity, cost_per_box, stock=0, low_stock_threshold=20):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO packaging (box_name, capacity, cost_per_box, stock, low_stock_threshold)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (box_name) DO NOTHING
    ''', (box_name, capacity, cost_per_box, stock, low_stock_threshold))
    
    conn.commit()
    conn.close()
    print(f"Box {box_name} added!")

def deactivate_packaging(box_name):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('UPDATE packaging SET is_active = 0 WHERE box_name = %s', (box_name,))

    conn.commit()
    conn.close()
    print(f"Packaging {box_name} deactivated!")

def activate_packaging(box_name):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('UPDATE packaging SET is_active = 1 WHERE box_name = %s', (box_name,))

    conn.commit()
    conn.close()
    print(f"Packaging {box_name} activated!")

def get_all_customers():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, name, phone, address, created_at
        FROM customers
        WHERE is_active = 1
        ORDER BY name
    ''')
    
    customers = cursor.fetchall()
    conn.close()
    return customers

def get_customer_orders(customer_id):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT o.id, o.delivery_date, o.status, 
               o.revenue, o.profit, o.address
        FROM orders o
        WHERE o.customer_id = %s
        ORDER BY o.delivery_date DESC
    ''', (customer_id,))
    
    orders = cursor.fetchall()
    conn.close()
    return orders

def update_customer(customer_id, name=None, phone=None, address=None):
    conn = get_connection()
    cursor = conn.cursor()
    
    if name:
        cursor.execute('''
            UPDATE customers SET name = %s WHERE id = %s
        ''', (name, customer_id))
    
    if phone:
        cursor.execute('''
            UPDATE customers SET phone = %s WHERE id = %s
        ''', (phone, customer_id))
    
    if address:
        cursor.execute('''
            UPDATE customers SET address = %s WHERE id = %s
        ''', (address, customer_id))
    
    conn.commit()
    conn.close()
    print(f"Customer #{customer_id} updated!")

def delete_customer(customer_id):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE customers SET is_active = 0 WHERE id = %s
    ''', (customer_id,))
    
    conn.commit()
    conn.close()
    print(f"Customer #{customer_id} deactivated!")

def update_cookie_threshold(flavour, new_threshold):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE cookie_stock SET low_stock_threshold = %s
        WHERE flavour = %s
    ''', (new_threshold, flavour))
    
    conn.commit()
    conn.close()
    print(f"Updated {flavour} threshold to {new_threshold}")

def update_ingredient_threshold(ingredient_name, new_threshold):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE ingredient_stock SET low_stock_threshold = %s
        WHERE ingredient_name = %s
    ''', (new_threshold, ingredient_name))
    
    conn.commit()
    conn.close()
    print(f"Updated {ingredient_name} threshold to {new_threshold}")

def update_ingredient_price(ingredient_name, packet_size, packet_unit, packet_price):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE ingredient_prices SET is_active = 0
        WHERE ingredient_name = %s
    ''', (ingredient_name,))
    
    cursor.execute('''
        INSERT INTO ingredient_prices 
        (ingredient_name, packet_size, packet_unit, packet_price, is_active)
        VALUES (%s, %s, %s, %s, 1)
    ''', (ingredient_name, packet_size, packet_unit, packet_price))
    
    conn.commit()
    conn.close()
    print(f"Updated {ingredient_name} price to ₹{packet_price}")