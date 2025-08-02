from flask import Flask, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import json
from datetime import datetime, timedelta
import secrets
APP_VERSION = "2.0.0"  # Update this when you make breaking changes
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
                  passive_progress TEXT DEFAULT NULL,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Add earnings column to existing users table if it doesn't exist
    try:
        c.execute('ALTER TABLE users ADD COLUMN earnings_cents INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass  # Column already exists
        
    # Add passive progress column
    try:
        c.execute('ALTER TABLE users ADD COLUMN passive_progress TEXT DEFAULT NULL')
    except sqlite3.OperationalError:
        pass  # Column already exists
        
    # Add passive coin tracking
    try:
        c.execute('ALTER TABLE users ADD COLUMN last_passive_award TIMESTAMP DEFAULT NULL')
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

@app.route('/save_passive_progress', methods=['POST'])
def save_passive_progress():
    if 'username' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    data = request.get_json()
    username = session['username']
    passive_progress = data.get('passive_progress')
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("UPDATE users SET passive_progress = ? WHERE username = ?", 
             (passive_progress, username))
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Passive progress saved'}), 200

@app.route('/load_passive_progress', methods=['GET'])
def load_passive_progress():
    if 'username' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    username = session['username']
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT passive_progress FROM users WHERE username = ?", (username,))
    result = c.fetchone()
    conn.close()
    
    if result and result[0]:
        return jsonify({'progress': result[0]}), 200
    else:
        return jsonify({'progress': None}), 200

@app.route('/award_passive_coin', methods=['POST'])
def award_passive_coin():
    if 'username' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    username = session['username']
    current_time = datetime.now()
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    # Check last passive award time to prevent abuse
    c.execute("SELECT last_passive_award, coins FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    
    if not user:
        conn.close()
        return jsonify({'error': 'User not found'}), 404
    
    last_award_time = user[0]
    current_coins = user[1]
    
    # Rate limiting: minimum 25 seconds between awards (allowing some client-side variance)
    if last_award_time:
        last_award = datetime.fromisoformat(last_award_time)
        time_diff = current_time - last_award
        if time_diff.total_seconds() < 295:  # 5 minutes - 5 seconds
            conn.close()
            return jsonify({
                'error': 'Passive coin awarded too quickly', 
                'wait_seconds': 25 - int(time_diff.total_seconds())
            }), 429
    
    # Award the coin
    c.execute("UPDATE users SET coins = coins + 1, last_passive_award = ? WHERE username = ?", 
             (current_time.isoformat(), username))
    
    # Get updated balance
    c.execute("SELECT coins FROM users WHERE username = ?", (username,))
    new_balance = c.fetchone()[0]
    
    conn.commit()
    conn.close()
    
    print(f"Passive coin awarded to {username}: {current_coins} -> {new_balance}")
    
    return jsonify({
        'message': 'Passive coin awarded',
        'new_balance': new_balance
    }), 200

# Add this endpoint to your Flask server (server.py)

@app.route('/admin/reset_passive', methods=['POST'])
def admin_reset_passive():
    # Simple admin check - in production, use proper authentication
    admin_key = request.headers.get('Admin-Key')
    if admin_key != 'your_admin_key_here':  # Change this to a secure key
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    username = data.get('username')
    reset_all = data.get('reset_all', False)  # Option to reset all users
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    if reset_all:
        # Reset passive progress for all users
        c.execute("SELECT username FROM users WHERE passive_progress IS NOT NULL")
        affected_users = [row[0] for row in c.fetchall()]
        
        # Clear passive progress and last award time for all users
        c.execute("UPDATE users SET passive_progress = NULL, last_passive_award = NULL")
        conn.commit()
        conn.close()
        
        return jsonify({
            'message': f'Reset passive coin progress for {len(affected_users)} users',
            'users_affected': affected_users,
            'action': 'All passive progress cleared - users will start fresh cycle on next login'
        }), 200
    
    elif username:
        # Reset passive progress for specific user
        # Check if user exists
        c.execute("SELECT passive_progress, last_passive_award FROM users WHERE username = ?", (username,))
        user = c.fetchone()
        if not user:
            conn.close()
            return jsonify({'error': 'User not found'}), 404
        
        had_progress = user[0] is not None
        had_award_time = user[1] is not None
        
        # Clear passive progress and last award time
        c.execute("UPDATE users SET passive_progress = NULL, last_passive_award = NULL WHERE username = ?", (username,))
        conn.commit()
        conn.close()
        
        return jsonify({
            'message': f'Reset passive coin progress for {username}',
            'had_saved_progress': had_progress,
            'had_award_time': had_award_time,
            'action': 'Passive progress cleared - user will start fresh cycle on next login'
        }), 200
    
    else:
        conn.close()
        return jsonify({'error': 'Must provide username or set reset_all=true'}), 400

# Optional: Admin endpoint to check passive coin status
@app.route('/admin/passive_status', methods=['GET'])
def admin_passive_status():
    # Simple admin check - in production, use proper authentication
    admin_key = request.headers.get('Admin-Key')
    if admin_key != 'your_admin_key_here':  # Change this to a secure key
        return jsonify({'error': 'Unauthorized'}), 401
    
    username = request.args.get('username')
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    if username:
        # Get specific user's passive status
        c.execute("SELECT username, passive_progress, last_passive_award FROM users WHERE username = ?", (username,))
        user = c.fetchone()
        if not user:
            conn.close()
            return jsonify({'error': 'User not found'}), 404
        
        status = {
            'username': user[0],
            'has_passive_progress': user[1] is not None,
            'passive_progress_data': user[1],
            'last_passive_award': user[2],
            'progress_corrupted': False
        }
        
        # Try to parse the progress data to check if it's corrupted
        if user[1]:
            try:
                import json
                progress_data = json.loads(user[1])
                # Basic validation
                if not isinstance(progress_data, dict):
                    status['progress_corrupted'] = True
                elif 'passiveCoins' not in progress_data or 'currentGrowingCoin' not in progress_data:
                    status['progress_corrupted'] = True
            except (json.JSONDecodeError, TypeError):
                status['progress_corrupted'] = True
        
        conn.close()
        return jsonify(status), 200
    
    else:
        # Get overview of all users' passive status
        c.execute("""SELECT username, 
                           CASE WHEN passive_progress IS NOT NULL THEN 1 ELSE 0 END as has_progress,
                           CASE WHEN last_passive_award IS NOT NULL THEN 1 ELSE 0 END as has_award_time
                    FROM users 
                    ORDER BY username""")
        
        users = []
        total_with_progress = 0
        total_with_award_time = 0
        
        for row in c.fetchall():
            user_status = {
                'username': row[0],
                'has_passive_progress': bool(row[1]),
                'has_last_award_time': bool(row[2])
            }
            users.append(user_status)
            
            if row[1]:
                total_with_progress += 1
            if row[2]:
                total_with_award_time += 1
        
        conn.close()
        
        return jsonify({
            'total_users': len(users),
            'users_with_passive_progress': total_with_progress,
            'users_with_award_time': total_with_award_time,
            'users': users
        }), 200

@app.route('/admin/fix_passive_corruption', methods=['POST'])
def admin_fix_passive_corruption():
    # Simple admin check - in production, use proper authentication
    admin_key = request.headers.get('Admin-Key')
    if admin_key != 'your_admin_key_here':  # Change this to a secure key
        return jsonify({'error': 'Unauthorized'}), 401
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    # Find users with corrupted passive progress
    c.execute("SELECT username, passive_progress FROM users WHERE passive_progress IS NOT NULL")
    corrupted_users = []
    
    for row in c.fetchall():
        username, progress_data = row
        is_corrupted = False
        
        try:
            import json
            progress = json.loads(progress_data)
            
            # Check if the data structure is valid
            if not isinstance(progress, dict):
                is_corrupted = True
            elif 'passiveCoins' not in progress or 'currentGrowingCoin' not in progress:
                is_corrupted = True
            elif not isinstance(progress.get('passiveCoins'), list):
                is_corrupted = True
            elif not isinstance(progress.get('currentGrowingCoin'), int):
                is_corrupted = True
            else:
                # Check each coin structure
                for coin in progress.get('passiveCoins', []):
                    if not isinstance(coin, dict) or 'progress' not in coin or 'isComplete' not in coin:
                        is_corrupted = True
                        break
                        
        except (json.JSONDecodeError, TypeError, AttributeError):
            is_corrupted = True
        
        if is_corrupted:
            corrupted_users.append(username)
    
    # Clear corrupted data
    if corrupted_users:
        placeholders = ','.join(['?' for _ in corrupted_users])
        c.execute(f"UPDATE users SET passive_progress = NULL, last_passive_award = NULL WHERE username IN ({placeholders})", corrupted_users)
        conn.commit()
    
    conn.close()
    
    return jsonify({
        'message': f'Fixed passive coin corruption for {len(corrupted_users)} users',
        'corrupted_users_fixed': corrupted_users,
        'action': 'Corrupted passive progress cleared - users will start fresh on next login'
    }), 200

@app.route('/version_check', methods=['POST'])
def version_check():
    data = request.get_json()
    client_version = data.get('version', '')
    
    if client_version != APP_VERSION:
        return jsonify({
            'error': 'Version mismatch',
            'server_version': APP_VERSION,
            'client_version': client_version,
            'message': f'Client version {client_version} does not match server version {APP_VERSION}. Please update your client.'
        }), 426  # Upgrade Required
    
    return jsonify({'message': 'Version compatible', 'version': APP_VERSION}), 200
    
    return jsonify({'message': 'Version compatible', 'version': APP_VERSION}), 200

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)