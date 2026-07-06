from database import get_connection

def get_balance():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT current_balance FROM balance ORDER BY id DESC LIMIT 1')
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def set_initial_balance(amount):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM balance')
    cursor.execute('INSERT INTO balance (current_balance) VALUES (%s)', (amount,))
    conn.commit()
    conn.close()

def add_transaction(type, category, amount, description=''):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM balance')
    count = cursor.fetchone()[0]
    if count == 0:
        cursor.execute('INSERT INTO balance (current_balance) VALUES (0)')
    
    cursor.execute('''
        INSERT INTO transactions (type, category, amount, description)
        VALUES (%s, %s, %s, %s)
    ''', (type, category, amount, description))
    
    if type == 'income':
        cursor.execute('UPDATE balance SET current_balance = current_balance + %s', (amount,))
    else:
        cursor.execute('UPDATE balance SET current_balance = current_balance - %s', (amount,))
    
    conn.commit()
    conn.close()

def get_transactions(limit=50):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT type, category, amount, description, created_at
        FROM transactions
        ORDER BY created_at DESC, id DESC
        LIMIT %s
    ''', (limit,))
    transactions = cursor.fetchall()
    conn.close()
    return transactions

def get_spending_summary():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT category, SUM(amount) as total
        FROM transactions
        WHERE type = 'expense'
        GROUP BY category
        ORDER BY total DESC
    ''')
    summary = cursor.fetchall()
    conn.close()
    return summary