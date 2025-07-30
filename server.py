from flask import Flask, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import json
from datetime import datetime, timedelta
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)  # Generate a random secret key

# Add CORS headers to allow cross-origin requests
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization,Cookie')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    return response

# Database initialization
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    # Users table - separate coins (spending) from earnings (money earned)
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE NOT NULL,
                  password_hash TEXT NOT NULL,
                  coins INTEGER DEFAULT 0,
                  earnings_cents INTEGER DEFAULT 0,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Add earnings column to existing users table if it doesn't exist
    try:
        c.execute('ALTER TABLE users ADD COLUMN earnings_cents INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    # Shop items table (client-registered items)
    c.execute('''CREATE TABLE IF NOT EXISTS shop_items
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  owner_username TEXT NOT NULL,
                  item_name TEXT NOT NULL,
                  item_description TEXT,
                  price INTEGER NOT NULL,
                  item_data TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (owner_username) REFERENCES users (username))''')
    
    # Purchase history
    c.execute('''CREATE TABLE IF NOT EXISTS purchases
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  buyer_username TEXT NOT NULL,
                  target_username TEXT NOT NULL,
                  item_name TEXT NOT NULL,
                  price INTEGER NOT NULL,
                  purchase_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  executed BOOLEAN DEFAULT FALSE,
                  FOREIGN KEY (buyer_username) REFERENCES users (username),
                  FOREIGN KEY (target_username) REFERENCES users (username))''')
    
    # Activity tracking for hourly coins
    c.execute('''CREATE TABLE IF NOT EXISTS activity_pings
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT NOT NULL,
                  ping_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (username) REFERENCES users (username))''')
    
    conn.commit()
    conn.close()

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    try:
        password_hash = generate_password_hash(password)
        c.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", 
                 (username, password_hash))
        conn.commit()
        return jsonify({'message': 'Account created successfully', 'coins': 0}), 201
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Username already exists'}), 409
    finally:
        conn.close()

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT password_hash, coins FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    conn.close()
    
    if user and check_password_hash(user[0], password):
        session['username'] = username
        # Debug: Print session info
        print(f"Login successful for {username}, session ID: {session.get('username')}")
        return jsonify({'message': 'Login successful', 'coins': user[1]}), 200
    else:
        return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/logout', methods=['POST'])
def logout():
    session.pop('username', None)
    return jsonify({'message': 'Logged out successfully'}), 200

@app.route('/profile', methods=['GET'])
def profile():
    print(f"Profile request - Session: {dict(session)}")  # Debug
    if 'username' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    username = session['username']
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT coins, earnings_cents FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    
    conn.close()
    
    if user:
        return jsonify({
            'username': username, 
            'coins': user[0],
            'total_earnings_usd': user[1] / 100.0  # Convert cents to dollars
        }), 200
    else:
        return jsonify({'error': 'User not found'}), 404

@app.route('/search_users', methods=['GET'])
def search_users():
    if 'username' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'users': []}), 200
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT username FROM users WHERE username LIKE ? LIMIT 10", 
             (f'%{query}%',))
    users = [row[0] for row in c.fetchall()]
    conn.close()
    
    return jsonify({'users': users}), 200

@app.route('/register_items', methods=['POST'])
def register_items():
    if 'username' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    data = request.get_json()
    username = session['username']
    items = data.get('items', [])
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    # Clear existing items for this user
    c.execute("DELETE FROM shop_items WHERE owner_username = ?", (username,))
    
    # Insert new items
    for item in items:
        c.execute("""INSERT INTO shop_items 
                    (owner_username, item_name, item_description, price, item_data) 
                    VALUES (?, ?, ?, ?, ?)""",
                 (username, item['name'], item['description'], 
                  item['price'], json.dumps(item.get('data', {}))))
    
    conn.commit()
    conn.close()
    
    return jsonify({'message': f'Registered {len(items)} items'}), 200

@app.route('/get_shop_items/<target_username>', methods=['GET'])
def get_shop_items(target_username):
    if 'username' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("""SELECT item_name, item_description, price, item_data 
                FROM shop_items WHERE owner_username = ?""", (target_username,))
    items = []
    for row in c.fetchall():
        items.append({
            'name': row[0],
            'description': row[1],
            'price': row[2],
            'data': json.loads(row[3]) if row[3] else {}
        })
    conn.close()
    
    return jsonify({'items': items}), 200

@app.route('/purchase', methods=['POST'])
def purchase():
    if 'username' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    data = request.get_json()
    buyer = session['username']
    target = data.get('target_username')
    item_name = data.get('item_name')
    
    if not target or not item_name:
        return jsonify({'error': 'Target username and item name required'}), 400
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    # Get item price
    c.execute("SELECT price FROM shop_items WHERE owner_username = ? AND item_name = ?", 
             (target, item_name))
    item = c.fetchone()
    if not item:
        conn.close()
        return jsonify({'error': 'Item not found'}), 404
    
    price = item[0]
    
    # Check buyer's coins
    c.execute("SELECT coins FROM users WHERE username = ?", (buyer,))
    buyer_coins = c.fetchone()[0]
    
    if buyer_coins < price:
        conn.close()
        return jsonify({'error': 'Insufficient coins'}), 400
    
    # Calculate earnings (70% of price, rounded down)
    earnings_cents = int(price * 0.7)
    
    # Debug: Print transaction details
    print(f"Purchase: {buyer} buying {item_name} for {price} coins from {target}")
    print(f"Buyer had {buyer_coins} coins, will lose {price} coins")
    print(f"Target will gain {earnings_cents} cents in earnings (70% of {price})")
    
    # Process purchase - buyer loses coins, target gains earnings (not coins)
    c.execute("UPDATE users SET coins = coins - ? WHERE username = ?", (price, buyer))
    c.execute("UPDATE users SET earnings_cents = earnings_cents + ? WHERE username = ?", (earnings_cents, target))
    c.execute("""INSERT INTO purchases 
                (buyer_username, target_username, item_name, price) 
                VALUES (?, ?, ?, ?)""", (buyer, target, item_name, price))
    
    # Debug: Check final balances
    c.execute("SELECT coins, earnings_cents FROM users WHERE username = ?", (buyer,))
    buyer_final = c.fetchone()
    c.execute("SELECT coins, earnings_cents FROM users WHERE username = ?", (target,))
    target_final = c.fetchone()
    print(f"After purchase - Buyer: {buyer_final[0]} coins, {buyer_final[1]} cents")
    print(f"After purchase - Target: {target_final[0]} coins, {target_final[1]} cents")
    
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Purchase successful'}), 200

@app.route('/get_pending_actions', methods=['GET'])
def get_pending_actions():
    if 'username' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    username = session['username']
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("""SELECT id, buyer_username, item_name, price, purchase_time 
                FROM purchases 
                WHERE target_username = ? AND executed = FALSE
                ORDER BY purchase_time DESC""", (username,))
    
    actions = []
    for row in c.fetchall():
        actions.append({
            'id': row[0],
            'buyer': row[1],
            'item_name': row[2],
            'price': row[3],
            'purchase_time': row[4]
        })
    
    conn.close()
    return jsonify({'actions': actions}), 200

@app.route('/mark_action_executed', methods=['POST'])
def mark_action_executed():
    if 'username' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    data = request.get_json()
    action_id = data.get('action_id')
    username = session['username']
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("UPDATE purchases SET executed = TRUE WHERE id = ? AND target_username = ?", 
             (action_id, username))
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Action marked as executed'}), 200

@app.route('/activity_ping', methods=['POST'])
def activity_ping():
    if 'username' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    username = session['username']
    current_time = datetime.now()
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    # Check last ping time (must be at least 5 minutes ago)
    c.execute("""SELECT ping_time FROM activity_pings 
                WHERE username = ? 
                ORDER BY ping_time DESC LIMIT 1""", (username,))
    last_ping = c.fetchone()
    
    if last_ping:
        last_ping_time = datetime.fromisoformat(last_ping[0])
        time_diff = current_time - last_ping_time
        if time_diff.total_seconds() < 300:  # 5 minutes = 300 seconds
            conn.close()
            return jsonify({'error': 'Must wait 5 minutes between pings'}), 429
    
    # Record the ping
    c.execute("INSERT INTO activity_pings (username, ping_time) VALUES (?, ?)",
             (username, current_time.isoformat()))
    
    # Count pings in the last hour
    one_hour_ago = current_time - timedelta(hours=1)
    c.execute("""SELECT COUNT(*) FROM activity_pings 
                WHERE username = ? AND ping_time >= ?""", 
             (username, one_hour_ago.isoformat()))
    ping_count = c.fetchone()[0]
    
    coins_earned = 0
    # Give 1 coin for every 12 pings (every hour if pinging every 5 minutes)
    if ping_count >= 12 and ping_count % 12 == 0:
        c.execute("UPDATE users SET coins = coins + 1 WHERE username = ?", (username,))
        coins_earned = 1
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'message': 'Ping recorded',
        'ping_count': ping_count,
        'coins_earned': coins_earned
    }), 200

# Admin endpoints (basic authentication for demo - you should add proper admin auth)
@app.route('/admin/stats', methods=['GET'])
def admin_stats():
    # Simple admin check - in production, use proper authentication
    admin_key = request.headers.get('Admin-Key')
    if admin_key != 'your_admin_key_here':  # Change this to a secure key
        return jsonify({'error': 'Unauthorized'}), 401
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    # Get total coins in system
    c.execute("SELECT SUM(coins) FROM users")
    total_coins = c.fetchone()[0] or 0
    
    # Get total USD earnings (70% of all executed purchases)
    c.execute("SELECT SUM(price) FROM purchases WHERE executed = TRUE")
    total_sales = c.fetchone()[0] or 0
    total_usd_earnings = (total_sales * 0.7) / 100.0  # Convert to dollars
    
    # Get user count
    c.execute("SELECT COUNT(*) FROM users")
    user_count = c.fetchone()[0]
    
    # Get top earners
    c.execute("""SELECT u.username, u.coins, u.earnings_cents,
                       CAST(u.earnings_cents / 100.0 AS REAL) as usd_earnings
                FROM users u
                ORDER BY u.earnings_cents DESC
                LIMIT 10""")
    top_earners = []
    for row in c.fetchall():
        top_earners.append({
            'username': row[0],
            'coins': row[1],
            'earnings_cents': row[2],
            'usd_earnings': row[3]
        })
    
    # Get total USD earnings
    c.execute("SELECT SUM(earnings_cents) FROM users")
    total_earnings_cents = c.fetchone()[0] or 0
    total_usd_earnings = total_earnings_cents / 100.0
    
    conn.close()
    
    return jsonify({
        'total_coins': total_coins,
        'total_usd_earnings': total_usd_earnings,
        'user_count': user_count,
        'top_earners': top_earners
    }), 200

@app.route('/admin/add_coins', methods=['POST'])
def admin_add_coins():
    # Simple admin check - in production, use proper authentication
    admin_key = request.headers.get('Admin-Key')
    if admin_key != 'your_admin_key_here':  # Change this to a secure key
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    username = data.get('username')
    coins_to_add = data.get('coins', 0)
    
    if not username or coins_to_add <= 0:
        return jsonify({'error': 'Valid username and positive coin amount required'}), 400
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    # Check if user exists
    c.execute("SELECT coins FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    if not user:
        conn.close()
        return jsonify({'error': 'User not found'}), 404
    
    # Add coins
    c.execute("UPDATE users SET coins = coins + ? WHERE username = ?", (coins_to_add, username))
    
    # Get updated balance
    c.execute("SELECT coins FROM users WHERE username = ?", (username,))
    new_balance = c.fetchone()[0]
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'message': f'Added {coins_to_add} coins to {username}',
        'new_balance': new_balance
    }), 200

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)