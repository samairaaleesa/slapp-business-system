from database import get_connection
from datetime import datetime, timedelta

def predict_batch_size(flavour, weeks_to_look_back=4, buffer_percentage=10, weeks_to_cover=3):
    conn = get_connection()
    cursor = conn.cursor()
    
    start_date = datetime.now() - timedelta(weeks=weeks_to_look_back)
    
    cursor.execute('''
        SELECT SUM(oi.quantity) as total_sold,
               COUNT(DISTINCT DATE_TRUNC('week', o.delivery_date)) as weeks_with_sales
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.id
        WHERE oi.flavour = %s
        AND o.delivery_date >= %s
        AND o.status = 'delivered'
    ''', (flavour, start_date.date()))
    
    result = cursor.fetchone()
    conn.close()
    
    total_sold, weeks_with_sales = result
    
    if not total_sold or weeks_with_sales == 0:
        return {
            'flavour': flavour,
            'recommended_batch': 0,
            'reason': 'Not enough sales data yet'
        }
    
    avg_weekly = total_sold / weeks_to_look_back
    recommended_for_period = avg_weekly * weeks_to_cover
    buffer = recommended_for_period * (buffer_percentage / 100)
    recommended = round(recommended_for_period + buffer)
    
    return {
        'flavour': flavour,
        'weeks_analysed': weeks_to_look_back,
        'weeks_to_cover': weeks_to_cover,
        'total_sold': total_sold,
        'avg_weekly': round(avg_weekly, 1),
        'recommended_batch': recommended
    }

def predict_all_flavours():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT name FROM recipes WHERE is_active = 1')
    flavours = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    predictions = []
    for flavour in flavours:
        prediction = predict_batch_size(flavour)
        predictions.append(prediction)
    
    predictions.sort(key=lambda x: x['recommended_batch'], reverse=True)
    return predictions

if __name__ == '__main__':
    print("Demand predictions:")
    predictions = predict_all_flavours()
    for p in predictions:
        if p['recommended_batch'] > 0:
            print(f"  {p['flavour']}: make {p['recommended_batch']} portions (covers ~{p['weeks_to_cover']} weeks)")
            print(f"    avg weekly: {p['avg_weekly']}")
        else:
            print(f"  {p['flavour']}: {p['reason']}")