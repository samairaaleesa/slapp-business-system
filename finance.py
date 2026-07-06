from database import get_connection
import math

def calculate_order_cost(order_id):
    conn = get_connection()
    cursor = conn.cursor()
    
    # get order items
    cursor.execute('''
        SELECT oi.flavour, oi.quantity
        FROM order_items oi
        WHERE oi.order_id = %s
    ''', (order_id,))
    
    items = cursor.fetchall()
    
    total_ingredient_cost = 0
    total_cookies = 0
    
    for flavour, quantity in items:
        total_cookies += quantity
        
        # get base yield
        cursor.execute('SELECT base_yield FROM recipes WHERE name = %s', (flavour,))
        base_yield = cursor.fetchone()[0]
        multiplier = quantity / base_yield
        
        # get ingredients and calculate cost
        cursor.execute('''
            SELECT ri.ingredient_name, ri.amount
            FROM recipe_ingredients ri
            JOIN recipes r ON ri.recipe_id = r.id
            WHERE r.name = %s
        ''', (flavour,))
        
        for ingredient_name, amount in cursor.fetchall():
            scaled_amount = amount * multiplier
            
            # get current active price
            cursor.execute('''
                SELECT packet_size, packet_price
                FROM ingredient_prices
                WHERE ingredient_name = %s AND is_active = 1
                ORDER BY created_at DESC
                LIMIT 1
            ''', (ingredient_name,))
            
            price_data = cursor.fetchone()
            if price_data:
                packet_size, packet_price = price_data
                cost_per_unit = packet_price / packet_size
                total_ingredient_cost += scaled_amount * cost_per_unit
    
    conn.close()
    return {
        'total_cookies': total_cookies,
        'ingredient_cost': round(total_ingredient_cost, 2)
    }

def calculate_order_revenue(order_id):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT oi.flavour, oi.quantity, o.combo_id
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.id
        WHERE oi.order_id = %s
    ''', (order_id,))
    
    items = cursor.fetchall()
    total_cookies = sum(quantity for _, quantity, _ in items)
    combo_id = items[0][2] if items else None
    
    free_cookies = 0
    discount_pct = 0

    if combo_id:
        cursor.execute('''
            SELECT buy_quantity, free_quantity, discount_percentage
            FROM combos WHERE id = %s
        ''', (combo_id,))
        combo = cursor.fetchone()
        if combo:
            buy_qty, free_qty, discount_pct = combo
            discount_pct = discount_pct or 0
            if buy_qty and buy_qty > 0 and free_qty and free_qty > 0:
                free_cookies = math.floor(total_cookies / (buy_qty + free_qty)) * free_qty

    paid_cookies = total_cookies - free_cookies

    revenue = 0
    for flavour, quantity, _ in items:
        cursor.execute('''
            SELECT price_per_cookie FROM pricing
            WHERE is_active = 1 AND flavour = %s
            LIMIT 1
        ''', (flavour,))
        price = cursor.fetchone()[0]
        revenue += quantity * price

    if free_cookies > 0:
        avg_price = revenue / total_cookies
        revenue -= free_cookies * avg_price
    elif discount_pct > 0:
        revenue = revenue * (1 - discount_pct / 100)

    conn.close()
    return {
        'total_cookies': total_cookies,
        'free_cookies': free_cookies,
        'paid_cookies': paid_cookies,
        'revenue': round(revenue, 2)
    }

def calculate_packaging_cost(total_cookies):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT capacity, cost_per_box FROM packaging
        WHERE box_name = 'standard_box'
    ''')
    
    box = cursor.fetchone()
    conn.close()
    
    if not box:
        return 0
    
    capacity, cost_per_box = box
    boxes_needed = math.ceil(total_cookies / capacity)
    return round(boxes_needed * cost_per_box, 2)

def calculate_order_profit(order_id):
    cost = calculate_order_cost(order_id)
    revenue = calculate_order_revenue(order_id)
    
    packaging_cost = calculate_packaging_cost(revenue['total_cookies'])
    total_cost = cost['ingredient_cost'] + packaging_cost
    
    profit = revenue['revenue'] - total_cost
    margin = (profit / revenue['revenue']) * 100 if revenue['revenue'] > 0 else 0
    
    return {
        'order_id': order_id,
        'total_cookies': revenue['total_cookies'],
        'free_cookies': revenue['free_cookies'],
        'paid_cookies': revenue['paid_cookies'],
        'revenue': revenue['revenue'],
        'ingredient_cost': cost['ingredient_cost'],
        'packaging_cost': packaging_cost,
        'total_cost': round(total_cost, 2),
        'profit': round(profit, 2),
        'margin': round(margin, 2)
    }
def get_weekly_report(start_date, end_date):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT 
            COUNT(DISTINCT o.id) as total_orders,
            SUM(oi.quantity) as total_cookies,
            SUM(o.revenue) as total_revenue,
            SUM(o.total_cost) as total_cost,
            SUM(o.profit) as total_profit
        FROM orders o
        JOIN order_items oi ON o.id = oi.order_id
        WHERE o.delivery_date BETWEEN %s AND %s
        AND o.status = 'delivered'
    ''', (start_date, end_date))
    
    summary = cursor.fetchone()
    
    cursor.execute('''
        SELECT oi.flavour, SUM(oi.quantity) as total
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.id
        WHERE o.delivery_date BETWEEN %s AND %s
        AND o.status != 'delivered'
        GROUP BY oi.flavour
        ORDER BY total DESC
    ''', (start_date, end_date))
    
    flavours = cursor.fetchall()
    
    cursor.execute('''
        SELECT o.id, c.name, SUM(oi.quantity) as cookies,
               o.revenue, o.profit
        FROM orders o
        JOIN customers c ON o.customer_id = c.id
        JOIN order_items oi ON o.id = oi.order_id
        WHERE o.delivery_date BETWEEN %s AND %s
        AND o.status != 'cancelled'
        GROUP BY o.id, c.name, o.revenue, o.profit
        ORDER BY o.id
    ''', (start_date, end_date))
    
    orders = cursor.fetchall()
    conn.close()
    
    total_orders, total_cookies, revenue, cost, profit = summary
    margin = (profit / revenue * 100) if revenue else 0
    
    return {
        'period': f"{start_date} to {end_date}",
        'total_orders': total_orders,
        'total_cookies': total_cookies,
        'revenue': round(revenue or 0, 2),
        'cost': round(cost or 0, 2),
        'profit': round(profit or 0, 2),
        'margin': round(margin, 2),
        'flavour_breakdown': flavours,
        'best_seller': flavours[0] if flavours else None,
        'orders': orders
    }

def get_monthly_report(year, month):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT 
            COUNT(DISTINCT o.id) as total_orders,
            SUM(oi.quantity) as total_cookies,
            SUM(o.revenue) as total_revenue,
            SUM(o.total_cost) as total_cost,
            SUM(o.profit) as total_profit
        FROM orders o
        JOIN order_items oi ON o.id = oi.order_id
        WHERE EXTRACT(MONTH FROM o.delivery_date) = %s
        AND EXTRACT(YEAR FROM o.delivery_date) = %s
        AND o.status = 'delivered'
    ''', (month, year))
    
    summary = cursor.fetchone()
    
    cursor.execute('''
        SELECT oi.flavour, SUM(oi.quantity) as total
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.id
        WHERE EXTRACT(MONTH FROM o.delivery_date) = %s
        AND EXTRACT(YEAR FROM o.delivery_date) = %s
        AND o.status = 'delivered'
        GROUP BY oi.flavour
        ORDER BY total DESC
    ''', (month, year))
    
    flavours = cursor.fetchall()
    
    cursor.execute('''
        SELECT SUM(revenue), SUM(investment), 
               SUM(revenue - investment) as profit
        FROM popups
        WHERE EXTRACT(MONTH FROM event_date) = %s
        AND EXTRACT(YEAR FROM event_date) = %s
    ''', (month, year))
    
    popup_summary = cursor.fetchone()
    
    conn.close()
    
    total_orders, total_cookies, revenue, cost, profit = summary
    margin = (profit / revenue * 100) if revenue else 0
    
    popup_revenue = popup_summary[0] or 0 if popup_summary else 0
    popup_investment = popup_summary[1] or 0 if popup_summary else 0
    popup_profit = popup_summary[2] or 0 if popup_summary else 0
    
    return {
        'period': f"{month}/{year}",
        'total_orders': total_orders or 0,
        'total_cookies': total_cookies or 0,
        'delivery_revenue': round(revenue or 0, 2),
        'delivery_cost': round(cost or 0, 2),
        'delivery_profit': round(profit or 0, 2),
        'delivery_margin': round(margin, 2),
        'popup_revenue': round(popup_revenue, 2),
        'popup_investment': round(popup_investment, 2),
        'popup_profit': round(popup_profit, 2),
        'total_revenue': round((revenue or 0) + popup_revenue, 2),
        'total_profit': round((profit or 0) + popup_profit, 2),
        'flavour_breakdown': flavours,
        'best_seller': flavours[0] if flavours else None,
        'worst_seller': flavours[-1] if flavours else None
    }

def get_shopping_list(flavour, portions_to_make):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT base_yield FROM recipes WHERE name = %s', (flavour,))
    base_yield = cursor.fetchone()[0]
    multiplier = portions_to_make / base_yield
    
    cursor.execute('''
        SELECT ri.ingredient_name, ri.amount, ri.unit,
               ist.quantity as in_stock
        FROM recipe_ingredients ri
        LEFT JOIN ingredient_stock ist 
        ON ri.ingredient_name = ist.ingredient_name
        WHERE ri.recipe_id = (SELECT id FROM recipes WHERE name = %s)
    ''', (flavour,))
    
    ingredients = cursor.fetchall()
    shopping_list = []
    
    for ingredient_name, amount, unit, in_stock in ingredients:
        needed = amount * multiplier
        in_stock = in_stock or 0
        shortfall = max(0, needed - in_stock)
        
        if shortfall > 0:
            cursor.execute('''
                SELECT packet_size, packet_price 
                FROM ingredient_prices
                WHERE ingredient_name = %s AND is_active = 1
                ORDER BY created_at DESC
                LIMIT 1
            ''', (ingredient_name,))
            
            price_data = cursor.fetchone()
            if price_data:
                packet_size, packet_price = price_data
                packets_needed = math.ceil(shortfall / packet_size)
                estimated_cost = packets_needed * packet_price
                
                shopping_list.append({
                    'ingredient': ingredient_name,
                    'needed': round(needed, 2),
                    'in_stock': round(in_stock, 2),
                    'shortfall': round(shortfall, 2),
                    'packets_to_buy': packets_needed,
                    'estimated_cost': estimated_cost,
                    'packet_price': packet_price,
                    'unit': unit
                })
    
    total_cost = sum(item['estimated_cost'] for item in shopping_list)
    conn.close()
    
    return {
        'flavour': flavour,
        'portions_to_make': portions_to_make,
        'shopping_list': shopping_list,
        'total_estimated_cost': round(total_cost, 2)
    }

def get_combined_shopping_list(items_to_make):
    total_needed = {}
    
    from database import get_connection
    import math
    
    for flavour, portions in items_to_make.items():
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT base_yield FROM recipes WHERE name = %s', (flavour,))
        base_yield = cursor.fetchone()[0]
        multiplier = portions / base_yield
        
        cursor.execute('''
            SELECT ingredient_name, amount, unit FROM recipe_ingredients
            WHERE recipe_id = (SELECT id FROM recipes WHERE name = %s)
        ''', (flavour,))
        
        for ingredient_name, amount, unit in cursor.fetchall():
            scaled = amount * multiplier
            if ingredient_name in total_needed:
                total_needed[ingredient_name]['needed'] += scaled
            else:
                total_needed[ingredient_name] = {
                    'ingredient': ingredient_name,
                    'needed': scaled,
                    'unit': unit
                }
        conn.close()
    
    conn = get_connection()
    cursor = conn.cursor()
    
    total_cost = 0
    shopping_list = []
    
    for ingredient_name, data in total_needed.items():
        cursor.execute('SELECT quantity FROM ingredient_stock WHERE ingredient_name = %s', (ingredient_name,))
        result = cursor.fetchone()
        in_stock = result[0] if result else 0
        shortfall = max(0, data['needed'] - in_stock)
        
        if shortfall > 0:
            cursor.execute('''
                SELECT packet_size, packet_price FROM ingredient_prices
                WHERE ingredient_name = %s AND is_active = 1
                ORDER BY created_at DESC LIMIT 1
            ''', (ingredient_name,))
            price_data = cursor.fetchone()
            if price_data:
                packet_size, packet_price = price_data
                packets = math.ceil(shortfall / packet_size)
                cost = packets * packet_price
                total_cost += cost
                shopping_list.append({
                    'ingredient': ingredient_name,
                    'needed': round(data['needed'], 2),
                    'in_stock': round(in_stock, 2),
                    'shortfall': round(shortfall, 2),
                    'packets_to_buy': packets,
                    'estimated_cost': cost,
                    'packet_price': packet_price,
                    'unit': data['unit']
                })
    
    conn.close()
    return {
        'shopping_list': shopping_list,
        'total_estimated_cost': round(total_cost, 2)
    }

if __name__ == '__main__':
    from orders import add_customer, create_order
    
    customer_id = add_customer('Test Customer', '9999999999', 'Test Address')
    order_id = create_order(
        customer_id,
        '2026-05-17',
        'Test Address',
        {'the_brownie_slapp': 4, 'the_classic_slapp': 1},
        1
    )
    
    print("\nOrder profit breakdown:")
    result = calculate_order_profit(order_id)
    for key, value in result.items():
        print(f"  {key}: {value}")
    
    print("\nWeekly report:")
    weekly = get_weekly_report('2026-05-13', '2026-05-19')
    for key, value in weekly.items():
        print(f"  {key}: {value}")
    
    print("\nShopping list for 24 brownies:")
    shopping = get_shopping_list('the_brownie_slapp', 24)
    print(f"  Total estimated cost: ₹{shopping['total_estimated_cost']}")
    for item in shopping['shopping_list']:
        print(f"  {item['ingredient']}: buy {item['packets_to_buy']} packets (₹{item['estimated_cost']})")