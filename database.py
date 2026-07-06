import psycopg2
import os

DB_CONFIG = {
    'dbname': 'slapp_db',
    'user': os.environ.get('USER'),
    'host': 'localhost',
    'port': 5432
}

def get_connection():
    conn = psycopg2.connect(**DB_CONFIG)
    return conn

def create_tables():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            phone TEXT UNIQUE NOT NULL,
            address TEXT,
            is_active INTEGER DEFAULT 1,
            created_at DATE DEFAULT CURRENT_DATE
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS combos (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            buy_quantity INTEGER NOT NULL,
            free_quantity INTEGER NOT NULL,
            discount_percentage REAL DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at DATE DEFAULT CURRENT_DATE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            customer_id INTEGER NOT NULL,
            delivery_date DATE NOT NULL,
            status TEXT DEFAULT 'pending',
            address TEXT NOT NULL,
            combo_id INTEGER REFERENCES combos(id),
            packaging_cost REAL DEFAULT 0,
            total_cost REAL DEFAULT 0,
            revenue REAL DEFAULT 0,
            ingredient_cost REAL DEFAULT 0,
            profit REAL DEFAULT 0,
            margin REAL DEFAULT 0,
            notes TEXT,
            created_at DATE DEFAULT CURRENT_DATE,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS order_items (
            id SERIAL PRIMARY KEY,
            order_id INTEGER NOT NULL,
            flavour TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recipes (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            base_yield INTEGER NOT NULL,
            is_active INTEGER DEFAULT 1
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recipe_ingredients (
            id SERIAL PRIMARY KEY,
            recipe_id INTEGER NOT NULL,
            ingredient_name TEXT NOT NULL,
            amount REAL NOT NULL,
            unit TEXT NOT NULL,
            FOREIGN KEY (recipe_id) REFERENCES recipes(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cookie_stock (
            id SERIAL PRIMARY KEY,
            flavour TEXT UNIQUE NOT NULL,
            quantity INTEGER DEFAULT 0,
            reserved INTEGER DEFAULT 0,
            low_stock_threshold INTEGER DEFAULT 10
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ingredient_stock (
            id SERIAL PRIMARY KEY,
            ingredient_name TEXT UNIQUE NOT NULL,
            quantity REAL DEFAULT 0,
            unit TEXT NOT NULL,
            low_stock_threshold REAL DEFAULT 100
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ingredient_prices (
            id SERIAL PRIMARY KEY,
            ingredient_name TEXT NOT NULL,
            packet_size REAL NOT NULL,
            packet_unit TEXT NOT NULL,
            packet_price REAL NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at DATE DEFAULT CURRENT_DATE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS packaging (
            id SERIAL PRIMARY KEY,
            box_name TEXT UNIQUE NOT NULL,
            capacity INTEGER NOT NULL,
            cost_per_box REAL DEFAULT 0,
            stock INTEGER DEFAULT 0,
            low_stock_threshold INTEGER DEFAULT 20
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pricing (
            id SERIAL PRIMARY KEY,
            flavour TEXT UNIQUE NOT NULL,
            price_per_cookie REAL NOT NULL,
            is_active INTEGER DEFAULT 1
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS popups (
            id SERIAL PRIMARY KEY,
            event_name TEXT NOT NULL,
            event_date DATE,
            location TEXT,
            units_produced INTEGER DEFAULT 0,
            units_sold INTEGER DEFAULT 0,
            units_given_free INTEGER DEFAULT 0,
            revenue REAL DEFAULT 0,
            investment REAL DEFAULT 0,
            game_players INTEGER DEFAULT 0,
            game_revenue REAL DEFAULT 0,
            notes TEXT,
            created_at DATE DEFAULT CURRENT_DATE
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id SERIAL PRIMARY KEY,
            type TEXT NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            description TEXT,
            created_at DATE DEFAULT CURRENT_DATE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS balance (
            id SERIAL PRIMARY KEY,
            current_balance REAL DEFAULT 0,
            updated_at DATE DEFAULT CURRENT_DATE
        )
    ''')

    conn.commit()
    conn.close()

if __name__ == '__main__':
    create_tables()
    print("Database created successfully!")