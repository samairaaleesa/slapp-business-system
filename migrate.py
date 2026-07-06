import json
import os
from database import get_connection

DATA_PATH = os.path.join(os.path.dirname(__file__), 'data')

def load_json(filename):
    with open(os.path.join(DATA_PATH, filename)) as f:
        return json.load(f)

def migrate_recipes():
    conn = get_connection()
    cursor = conn.cursor()
    
    recipes = load_json('recipes.json')
    
    for recipe_name, recipe_data in recipes.items():
        cursor.execute('''
            INSERT INTO recipes (name, base_yield)
            VALUES (%s, %s)
            ON CONFLICT (name) DO NOTHING
        ''', (recipe_name, recipe_data['base_yield']))
        
        cursor.execute('SELECT id FROM recipes WHERE name = %s', (recipe_name,))
        recipe_id = cursor.fetchone()[0]
        
        for ingredient_name, amount in recipe_data['ingredients'].items():
            if ingredient_name.endswith('_g'):
                unit = 'g'
                clean_name = ingredient_name[:-2]
            else:
                unit = 'pieces'
                clean_name = ingredient_name
                
            cursor.execute('''
                INSERT INTO recipe_ingredients 
                (recipe_id, ingredient_name, amount, unit)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            ''', (recipe_id, clean_name, amount, unit))
    
    conn.commit()
    conn.close()
    print("Recipes migrated!")

def migrate_ingredients():
    conn = get_connection()
    cursor = conn.cursor()
    
    ingredients = load_json('ingredients.json')
    
    for ingredient in ingredients:
        if ingredient.endswith('_g'):
            unit = 'g'
            clean_name = ingredient[:-2]
        else:
            unit = 'pieces'
            clean_name = ingredient
            
        cursor.execute('''
            INSERT INTO ingredient_stock 
            (ingredient_name, quantity, unit)
            VALUES (%s, 0, %s)
            ON CONFLICT (ingredient_name) DO NOTHING
        ''', (clean_name, unit))
    
    conn.commit()
    conn.close()
    print("Ingredients migrated!")

def migrate_prices():
    conn = get_connection()
    cursor = conn.cursor()
    
    prices = load_json('prices.json')
    
    for ingredient_name, price_data in prices.items():
        if ingredient_name.endswith('_g'):
            clean_name = ingredient_name[:-2]
            unit = 'g'
        else:
            clean_name = ingredient_name
            unit = 'pieces'
            
        cursor.execute('''
            INSERT INTO ingredient_prices 
            (ingredient_name, packet_size, packet_unit, packet_price)
            VALUES (%s, %s, %s, %s)
        ''', (clean_name, price_data['packet_size_g'], unit, price_data['packet_price']))
    
    conn.commit()
    conn.close()
    print("Prices migrated!")

def migrate_cookie_stock():
    conn = get_connection()
    cursor = conn.cursor()
    
    recipes = load_json('recipes.json')
    
    for recipe_name in recipes.keys():
        cursor.execute('''
            INSERT INTO cookie_stock (flavour, quantity)
            VALUES (%s, 0)
            ON CONFLICT (flavour) DO NOTHING
        ''', (recipe_name,))
    
    conn.commit()
    conn.close()
    print("Cookie stock migrated!")

def migrate_flavour_pricing():
    conn = get_connection()
    cursor = conn.cursor()
    
    recipes = load_json('recipes.json')
    
    for recipe_name in recipes.keys():
        cursor.execute('''
            INSERT INTO pricing (flavour, price_per_cookie)
            VALUES (%s, 99)
            ON CONFLICT (flavour) DO NOTHING
        ''', (recipe_name,))
    
    conn.commit()
    conn.close()
    print("Flavour pricing migrated!")
def migrate_combos():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO combos (name, buy_quantity, free_quantity)
        VALUES (%s, %s, %s)
        ON CONFLICT DO NOTHING
    ''', ('buy4get1free', 4, 1))
    
    conn.commit()
    conn.close()
    print("Combos migrated!")
def migrate_packaging():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO packaging (box_name,cost_per_box, capacity, stock, low_stock_threshold)
        VALUES (%s, %s, %s, %s,%s)
        ON CONFLICT (box_name) DO NOTHING
    ''', ('standard_box', 20,5, 0, 20))
    
    conn.commit()
    conn.close()
    print("Packaging migrated!")

if __name__ == '__main__':
    migrate_recipes()
    migrate_ingredients()
    migrate_prices()
    migrate_cookie_stock()
    migrate_flavour_pricing()
    migrate_combos()
    migrate_packaging()
    print("All data migrated successfully!")