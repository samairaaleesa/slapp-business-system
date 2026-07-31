import os
import json
import math
from groq import Groq
from dotenv import load_dotenv
from datetime import date, timedelta
import anthropic

load_dotenv()

# ============ TOOLS ============

def get_orders_tool(status=None, delivery_date=None, customer_name=None, start_date=None, end_date=None):
    from database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    
    query = '''
        SELECT o.id, c.name, c.phone, o.address, o.status,
               o.delivery_date, o.revenue, o.profit, o.notes,
               oi.flavour, oi.quantity
        FROM orders o
        JOIN customers c ON o.customer_id = c.id
        JOIN order_items oi ON o.id = oi.order_id
        WHERE 1=1
    '''
    params = []
    
    if status:
        query += ' AND o.status = %s'
        params.append(status)
    if delivery_date:
        query += ' AND o.delivery_date = %s'
        params.append(delivery_date)
    if customer_name:
        query += ' AND c.name ILIKE %s'
        params.append(f'%{customer_name}%')
    if start_date and end_date:
        query += ' AND o.delivery_date BETWEEN %s AND %s'
        params.extend([start_date, end_date])
    
    query += ' ORDER BY o.delivery_date ASC'
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    orders = {}
    for row in rows:
        oid = row[0]
        if oid not in orders:
            orders[oid] = {
                'order_id': oid, 'customer': row[1], 'phone': row[2],
                'address': row[3], 'status': row[4],
                'delivery_date': str(row[5]), 'revenue': float(row[6] or 0),
                'profit': float(row[7] or 0), 'notes': row[8],
                'items': {}
            }
        orders[oid]['items'][row[9]] = row[10]
    
    return list(orders.values())

def get_order_details_tool(order_id):
    from database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT o.id, c.name, c.phone, o.address, o.status, o.delivery_date,
               o.revenue, o.ingredient_cost, o.packaging_cost, o.total_cost,
               o.profit, o.margin, o.notes, o.created_at
        FROM orders o
        JOIN customers c ON o.customer_id = c.id
        WHERE o.id = %s
    ''', (order_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return {'error': f'Order #{order_id} not found'}

    order = {
        'order_id': row[0], 'customer': row[1], 'phone': row[2],
        'address': row[3], 'status': row[4], 'delivery_date': str(row[5]),
        'revenue': float(row[6] or 0), 'ingredient_cost': float(row[7] or 0),
        'packaging_cost': float(row[8] or 0), 'total_cost': float(row[9] or 0),
        'profit': float(row[10] or 0), 'margin': float(row[11] or 0),
        'notes': row[12], 'created_at': str(row[13]),
        'items': {}
    }

    cursor.execute('SELECT flavour, quantity FROM order_items WHERE order_id = %s', (order_id,))
    for flavour, qty in cursor.fetchall():
        order['items'][flavour] = qty

    cursor.execute('''
        SELECT cb.name, cb.buy_quantity, cb.free_quantity, oc.count
        FROM order_combos oc
        JOIN combos cb ON oc.combo_id = cb.id
        WHERE oc.order_id = %s
    ''', (order_id,))
    order['combos_applied'] = [
        {'name': name, 'buy': buy, 'free': free, 'count': count, 'free_cookies': free * count}
        for name, buy, free, count in cursor.fetchall()
    ]

    conn.close()
    return order

def get_customer_insights_tool(customer_name=None, phone=None):
    from database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    
    base_query = '''
        SELECT c.id, c.name, c.phone, COUNT(o.id) as total_orders,
               SUM(CASE WHEN o.status = 'delivered' THEN 1 ELSE 0 END) as delivered,
               SUM(CASE WHEN o.status = 'cancelled' THEN 1 ELSE 0 END) as cancelled,
               SUM(CASE WHEN o.status = 'delivered' THEN o.revenue ELSE 0 END) as total_spent,
               MAX(o.delivery_date) as last_order_date
        FROM customers c
        LEFT JOIN orders o ON c.id = o.customer_id
    '''
    #to get customers favourite flavour
    cursor.execute('''
        SELECT oi.flavour, SUM(oi.quantity) as total
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.id
        WHERE o.customer_id = %s AND o.status != 'cancelled'
        GROUP BY oi.flavour
        ORDER BY total DESC
        LIMIT 1
    ''')
    if customer_name:
        cursor.execute(base_query + ' WHERE c.name ILIKE %s GROUP BY c.id, c.name, c.phone', (f'%{customer_name}%',))
    elif phone:
        cursor.execute(base_query + ' WHERE c.phone LIKE %s GROUP BY c.id, c.name, c.phone', (f'%{phone}%',))
    else:
        cursor.execute(base_query + ''' 
            GROUP BY c.id, c.name, c.phone
            HAVING COUNT(o.id) > 1
            ORDER BY COUNT(o.id) DESC
        ''')
    
    results = [{'name': r[1], 'phone': r[2], 'total_orders': r[3],
                'delivered': r[4], 'cancelled': r[5],
                'total_spent': float(r[6] or 0),
                'last_order': str(r[7]) if r[7] else None} for r in cursor.fetchall()]
    conn.close()
    return results

def run_anomaly_checks_tool():
    from database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    anomalies = []
    
    # 1. FINANCE MATH — internal consistency of stored numbers
    cursor.execute('''
        SELECT id, revenue, ingredient_cost, packaging_cost, total_cost, profit, margin
        FROM orders WHERE status != 'cancelled'
    ''')
    for row in cursor.fetchall():
        oid, rev, ing, pkg, total, profit, margin = [float(x or 0) for x in row]
        oid = int(oid)
        
        # total_cost should = ingredient + packaging
        if abs((ing + pkg) - total) > 0.5:
            anomalies.append(f"MATH ERROR Order #{oid}: ingredient({ing}) + packaging({pkg}) = {ing+pkg} but total_cost stored as {total}")
        
        # profit should = revenue - total_cost
        if abs((rev - total) - profit) > 0.5:
            anomalies.append(f"MATH ERROR Order #{oid}: revenue({rev}) - total_cost({total}) = {rev-total} but profit stored as {profit}")
        
        # margin should = profit/revenue * 100
        if rev > 0:
            expected_margin = round(profit / rev * 100, 1)
            if abs(expected_margin - margin) > 1:
                anomalies.append(f"MATH ERROR Order #{oid}: margin should be {expected_margin}% but stored as {margin}%")
    
    # 2. Zero revenue on non-cancelled orders
    cursor.execute('''
        SELECT o.id, c.name FROM orders o
        JOIN customers c ON o.customer_id = c.id
        WHERE o.revenue = 0 AND o.status != 'cancelled'
    ''')
    for row in cursor.fetchall():
        anomalies.append(f"ZERO REVENUE Order #{row[0]} ({row[1]}) — finance calculation may have failed")
    
    # 3. Overdue pending orders
    cursor.execute('''
        SELECT o.id, c.name, o.delivery_date FROM orders o
        JOIN customers c ON o.customer_id = c.id
        WHERE o.status = 'pending' AND o.delivery_date < CURRENT_DATE
    ''')
    for row in cursor.fetchall():
        anomalies.append(f"OVERDUE Order #{row[0]} ({row[1]}) was due {row[2]} — still pending. Delivered but not marked? Or genuinely late?")
    
    # 4. Possible duplicate orders
    cursor.execute('''
        SELECT c.name, o.delivery_date, COUNT(*), STRING_AGG(o.id::text, ', ')
        FROM orders o
        JOIN customers c ON o.customer_id = c.id
        WHERE o.status = 'pending'
        GROUP BY c.name, o.delivery_date
        HAVING COUNT(*) > 1
    ''')
    for row in cursor.fetchall():
        anomalies.append(f"POSSIBLE DUPLICATE: {row[0]} has {row[2]} pending orders for {row[1]} (orders: {row[3]}) — intentional or double entry?")
    
    # 5. Negative available stock
    cursor.execute('SELECT flavour, quantity, reserved FROM cookie_stock WHERE quantity - reserved < 0')
    for row in cursor.fetchall():
        anomalies.append(f"NEGATIVE STOCK: {row[0]} — quantity {row[1]}, reserved {row[2]}. More reserved than exists!")
    
    # 6. Reserved stock but no pending orders (orphan reservations)
    cursor.execute('''
        SELECT cs.flavour, cs.reserved,
               COALESCE(SUM(CASE WHEN o.status = 'pending' THEN oi.quantity ELSE 0 END), 0) as pending_qty
        FROM cookie_stock cs
        LEFT JOIN order_items oi ON cs.flavour = oi.flavour
        LEFT JOIN orders o ON oi.order_id = o.id
        GROUP BY cs.flavour, cs.reserved
    ''')
    for row in cursor.fetchall():
        if row[1] != row[2]:
            anomalies.append(f"RESERVATION MISMATCH: {row[0]} shows {row[1]} reserved but pending orders only need {row[2]}")
    
    # 7. Order total doesn't match its recorded combo breakdown (bundles + implied singles)
    cursor.execute('''
        SELECT o.id, c.name,
               (SELECT COALESCE(SUM(quantity), 0) FROM order_items WHERE order_id = o.id) as total_cookies,
               (SELECT COALESCE(SUM(oc.count * (cb.buy_quantity + cb.free_quantity)), 0)
                FROM order_combos oc JOIN combos cb ON oc.combo_id = cb.id
                WHERE oc.order_id = o.id) as bundled_cookies
        FROM orders o
        JOIN customers c ON o.customer_id = c.id
        WHERE o.status != 'cancelled'
    ''')
    for row in cursor.fetchall():
        if row[3] > row[2]:
            anomalies.append(f"COMBO MISMATCH Order #{row[0]} ({row[1]}): combo bundles account for {row[3]} cookies but order only has {row[2]}")

    conn.close()
    return anomalies if anomalies else ["All checks passed — no anomalies detected ✓"]

def cancel_order_tool(order_id):
    from orders import cancel_order
    cancel_order(order_id)
    return {'success': True, 'message': f'Order #{order_id} cancelled and stock released'}

def get_order_stats_tool(start_date, end_date):
    from database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    
    # totals per day
    cursor.execute('''
        SELECT o.delivery_date, COUNT(DISTINCT o.id), SUM(oi.quantity)
        FROM orders o JOIN order_items oi ON o.id = oi.order_id
        WHERE o.status != 'cancelled' AND o.delivery_date BETWEEN %s AND %s
        GROUP BY o.delivery_date ORDER BY o.delivery_date
    ''', (start_date, end_date))
    per_day = [{'date': str(r[0]), 'orders': r[1], 'cookies': int(r[2])} for r in cursor.fetchall()]
    
    # totals per flavour
    cursor.execute('''
        SELECT oi.flavour, SUM(oi.quantity)
        FROM orders o JOIN order_items oi ON o.id = oi.order_id
        WHERE o.status != 'cancelled' AND o.delivery_date BETWEEN %s AND %s
        GROUP BY oi.flavour ORDER BY SUM(oi.quantity) DESC
    ''', (start_date, end_date))
    per_flavour = [{'flavour': r[0], 'cookies': int(r[1])} for r in cursor.fetchall()]
    
    # money totals (delivered only)
    cursor.execute('''
        SELECT COUNT(*), COALESCE(SUM(revenue),0), COALESCE(SUM(profit),0)
        FROM orders WHERE status = 'delivered' AND delivery_date BETWEEN %s AND %s
    ''', (start_date, end_date))
    money = cursor.fetchone()
    
    conn.close()
    return {
        'period': f'{start_date} to {end_date}',
        'per_day': per_day,
        'per_flavour': per_flavour,
        'delivered_orders': money[0],
        'delivered_revenue': float(money[1]),
        'delivered_profit': float(money[2])
    }

def edit_order_items_tool(order_id, items):
    from orders import update_order_items
    from database import get_connection

    # 1. packaging check FIRST
    total_cookies = sum(items.values())
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT capacity, stock FROM packaging WHERE is_active = 1 ORDER BY capacity DESC')
    boxes = cursor.fetchall()
    total_capacity = sum(cap * stock for cap, stock in boxes)
    conn.close()
    
    if total_capacity < total_cookies:
        return {
            'success': False,
            'reason': 'packaging',
            'detail': f'Need to pack {total_cookies} cookies but total box capacity available is {total_capacity}',
            'draft_customer_message': f"heyy! so sorry — we can't modify the order right now, we're short on packaging for {total_cookies} cookies. can do a smaller size or a later date if that works?"
        }
    
    # 2. try the item update (checks cookie stock internally)
    result = update_order_items(order_id, items)
    
    if isinstance(result, dict) and not result.get('success'):
        shortages = ", ".join(
            f"{w['flavour'].replace('_slapp','').replace('_',' ').title()} (want {w['needed']}, have {w['available']})"
            for w in result['warnings']
        )
        return {
            'success': False,
            'reason': 'cookie stock',
            'detail': shortages,
            'draft_customer_message': f"heyy! quick update — we're short on stock for that change: {shortages}. want to swap flavours or shift the delivery date so we can bake fresh?"
        }
    
    # update_order_items already recomputed the optimal combo mix and finance snapshot internally
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT cb.name, oc.count FROM order_combos oc
        JOIN combos cb ON oc.combo_id = cb.id
        WHERE oc.order_id = %s
    ''', (order_id,))
    combos_applied = [f"{count}x {name}" for name, count in cursor.fetchall()]
    conn.close()

    return {'success': True, 'combos_applied': combos_applied or ['none'],
            'message': f'Order #{order_id} updated. Combo mix and finance recalculated.'}

def edit_order_details_tool(order_id, delivery_date=None, address=None, notes=None,
                              delivery_required=None, is_bulk_order=None, bulk_discount_pct=None):
    from orders import update_order
    if is_bulk_order is True:
        discount = bulk_discount_pct if bulk_discount_pct is not None else 0
    elif is_bulk_order is False:
        discount = None
    else:
        discount = -1  # not mentioned, leave bulk status unchanged
    update_order(order_id, delivery_date=delivery_date, address=address, notes=notes,
                 delivery_required=delivery_required, bulk_discount_pct=discount)
    return {'success': True, 'message': f'Order #{order_id} details updated'}

def mark_delivered_tool(order_id):
    from stock import log_order_delivered
    log_order_delivered(order_id)
    return {'success': True, 'message': f'Order #{order_id} marked delivered. Stock deducted, revenue logged to cashflow.'}

# ============ TOOL DEFINITIONS ============

TOOLS = [
    {
        "name": "get_orders",
        "description": "Get orders. Filter by status (pending/delivered/cancelled), delivery_date (YYYY-MM-DD), customer_name, or a date range (start_date + end_date). No filters = all orders.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["pending", "delivered", "cancelled"]},
                "delivery_date": {"type": "string"},
                "customer_name": {"type": "string"},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"}
                }
            }
    },
    {
        "name": "get_order_details",
        "description": "Get complete detail of one order — full finance breakdown (revenue, ingredient cost, packaging cost, profit, margin), items, combo, notes",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "integer"}},
            "required": ["order_id"]
            }
    },
    {
        "name": "get_customer_insights",
        "description": "Customer order history, spending,their favourite flavour(most ordered flavour). No args = all repeat customers ranked by order count. Or filter by name/phone.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_name": {"type": "string"},
                "phone": {"type": "string"}
            }
        }
    },
    {
        "name": "run_anomaly_checks",
        "description": "Run all anomaly checks: finance math verification, zero revenue orders, overdue pending orders, duplicate orders, negative stock, reservation mismatches, combo mismatches. Returns list of findings.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "cancel_order",
        "description": "Cancel a pending order. Releases reserved stock. ONLY call after user explicitly confirms.",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "integer"}},
            "required": ["order_id"]
        }
    },
    {
        "name": "edit_order_items",
        "description": "Change items in a pending order. Full replacement — pass ALL items the order should have, not just changes. ONLY call after user explicitly confirms.",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "integer"},
                "items": {"type": "object", "description": "e.g. {\"the_brownie_slapp\": 4, \"the_classic_slapp\": 2}"}
            },
            "required": ["order_id", "items"]
        }
    },
    {
        "name": "mark_delivered",
        "description": "Mark a pending order as delivered. Deducts stock and packaging, logs revenue to cashflow. ONLY call after user explicitly confirms.",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "integer"}},
            "required": ["order_id"]
            }
    },
    {
        "name": "edit_order_details",
        "description": "Change a pending order's delivery date, address, notes, delivery-required flag, or bulk-discount status — NOT items (use edit_order_items for that). Pass only the fields being changed. Changing delivery_required or bulk order status recalculates revenue/profit. ONLY call after user explicitly confirms.",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "integer"},
                "delivery_date": {"type": "string", "description": "YYYY-MM-DD"},
                "address": {"type": "string"},
                "notes": {"type": "string"},
                "delivery_required": {"type": "boolean", "description": "Whether this order needs Porter delivery (adds ₹50 if order total is under ₹500)"},
                "is_bulk_order": {"type": "boolean", "description": "true = use a manual bulk discount instead of auto-combo pricing; false = revert to normal auto-combo pricing"},
                "bulk_discount_pct": {"type": "number", "description": "Discount percentage to apply, only used when is_bulk_order is true"}
            },
            "required": ["order_id"]
            }
        },
    {
        "name": "get_order_stats",
        "description": "Aggregate order statistics for a date range: orders and cookies per day, cookies per flavour, delivered revenue and profit totals. Use for questions like 'busiest day', 'most popular flavour', 'how many cookies this week', 'revenue this month'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"}
            },
            "required": ["start_date", "end_date"]
        }
    },
    {
        "name": "navigate",
        "description": "Open an existing page in the SLAPP system for the user. ONLY use when the user explicitly asks to open/show/go to a page. Pages: bake brief (/bake?date=YYYY-MM-DD), orders by date (/orders/date?date=YYYY-MM-DD), all orders (/orders/all), new order form (/orders/new), DM intake (/orders/dm)",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"]
        }
    }
]


TOOL_FUNCTIONS = {
    'get_orders': get_orders_tool,
    'get_order_details': get_order_details_tool,
    'get_customer_insights': get_customer_insights_tool,
    'run_anomaly_checks': run_anomaly_checks_tool,
    'cancel_order': cancel_order_tool,
    'edit_order_items': edit_order_items_tool,
    'mark_delivered': mark_delivered_tool,
    'edit_order_details': edit_order_details_tool,
    'get_order_stats': get_order_stats_tool
}

# ============ AGENT ============

def run_agent(user_message, chat_history=None):
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    from database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT name FROM recipes WHERE is_active = 1 ORDER BY name')
    flavour_keys = ", ".join(
        f"{row[0]} ({row[0].replace('_slapp', '').replace('_', ' ').title()})"
        for row in cursor.fetchall()
    )
    conn.close()

    system_prompt = f"""You are the SLAPP Order Manager — the operations agent for a cookie business in Bangalore.

TODAY: {date.today()} ({date.today().strftime('%A')})
UPCOMING DATES:
{chr(10).join(f"- {(date.today() + timedelta(days=i)).strftime('%A')} = {date.today() + timedelta(days=i)}" for i in range(8))}
FLAVOUR KEYS: {flavour_keys}

YOUR TOOLS:
- get_orders: fetch orders with filters (status, date, date range, customer). Your main data source.
- get_order_details: full finance + item detail for ONE order
- get_customer_insights: customer history, repeat customers, spending, favourite flavours
- run_anomaly_checks: automated integrity checks
- cancel_order / edit_order_items / edit_order_details / mark_delivered: actions (need confirmation)
- navigate: send user to an existing page (ONLY when explicitly asked)

HOW TO ANSWER ANALYTICAL QUESTIONS:
Questions like "which day has most orders", "most popular flavour this week", "how many cookies next week" require you to:
1. Call get_orders with the right date range (start_date + end_date)
2. Analyze the returned data YOURSELF — group, count, sum, compare
3. Answer with specific numbers

Example: "which day next week has most orders?"
→ get_orders(start_date={date.today()}, end_date={date.today() + timedelta(days=7)}, status="pending")
→ count orders per delivery_date in the result
→ "Saturday July 12 has the most: 4 orders (18 cookies total)"

CRITICAL RULES:
1. DESTRUCTIVE ACTIONS (cancel, edit_order_items, edit_order_details, mark_delivered): ALWAYS restate the exact change with specific values and ask for confirmation BEFORE calling the tool — even if the user's instruction was precise. Example: user says "move rabbit's order to July 15" → you say "Moving order #14 (Rabbit) from July 12 to July 15 — confirm?" → only call the tool after they say yes. No exceptions.
2. ANOMALIES: Present each finding and ask if it's intentional or needs fixing. Never auto-fix.
3. NAVIGATION: navigate ONLY when the user explicitly asks to open/see a page ("open the bake brief", "take me to all orders"). For questions and actions, work directly in chat with tools. Never navigate as a substitute for answering.
5. When looking for patterns, pull data with get_orders and analyze it yourself — spikes, unusual quantities, same address different names, anything off.
6. If a tool returns empty results, say so plainly — don't invent data.
7. NEVER call tools with placeholder or guessed values. Need an order ID? get_orders first, use the real integer.
8. Editing items = FULL REPLACEMENT. get_order_details first, apply the change, pass the complete final list.
9. When an edit fails due to stock or packaging, show the user the draft_customer_message from the tool result so they can send it to the customer.
10. Be concise. Use ₹. Real numbers, no padding.
11. If you cannot answer or complete an action because data is missing or a tool doesn't provide it, say so EXPLICITLY: name what's missing, which tool you tried, and what the user could do (provide info, or this may need a new tool). Never give a vague "I can't do that" — always specify the gap.
12. FORMAT: Plain conversational text only — NO markdown tables, NO pipes, no headers. For lists of orders use simple lines like: "Order #33 — Rohan, 12 cookies (3 Classic, 6 Brownie, 3 Comfort), ₹891, pending".
"""
    messages = []
    if chat_history:
        messages.extend(chat_history)
    messages.append({"role": "user", "content": user_message})
    
    max_rounds = 10
    rounds = 0
    
    while rounds < max_rounds:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            system=system_prompt,
            messages=messages,
            tools=TOOLS
        )
        rounds += 1
        
        # final answer — no tool requested
        if response.stop_reason != "tool_use":
            text = "".join(b.text for b in response.content if b.type == "text")
            return {'type': 'message', 'content': text}
        
        # find the tool call block (native object — nothing to parse)
        tool_block = next(b for b in response.content if b.type == "tool_use")
        tool_name = tool_block.name
        tool_args = tool_block.input
        
        print(f"AGENT ROUND {rounds}: calling {tool_name} with {tool_args}")
        if tool_name == 'navigate':
            return {'type': 'navigate', 'url': tool_args['url']}
        
        if tool_name in TOOL_FUNCTIONS:
            try:
                result = TOOL_FUNCTIONS[tool_name](**tool_args)
            except Exception as e:
                result = {'error': str(e)}
        else:
            result = {'error': f'Unknown tool {tool_name}'}
        
        messages.append({"role": "assistant", "content": response.content})
        messages.append({
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": tool_block.id,
                "content": json.dumps(result)
            }]
        })
    
    return {'type': 'message', 'content': "Couldn't complete that within my round limit — try breaking it into smaller steps."}