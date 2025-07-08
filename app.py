from flask import Flask, request, jsonify, send_from_directory, render_template
import sqlite3
import os

app = Flask(__name__, static_folder='static', template_folder='templates')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/data')
def api_data():
    price_min = request.args.get('price_min', '').strip()
    price_max = request.args.get('price_max', '').strip()
    global_q = request.args.get('global', '').strip()

    sql = "SELECT * FROM data"
    conditions = []
    params = []

    if global_q:
        like = f"%{global_q}%"
        conditions.append("""
            (
              标题 LIKE ? OR
              CAST(价格 AS TEXT) LIKE ? OR
              QQ LIKE ? OR
              微信 LIKE ? OR
              手机 LIKE ?
            )
        """)
        params.extend([like] * 5)

    if price_min:
        try:
            price_min_val = float(price_min)
            conditions.append("价格 >= ?")
            params.append(price_min_val)
        except ValueError:
            return jsonify([])

    if price_max:
        try:
            price_max_val = float(price_max)
            conditions.append("价格 <= ?")
            params.append(price_max_val)
        except ValueError:
            return jsonify([])

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    else:
        # 无条件避免返回全表
        return jsonify([])

    conn = sqlite3.connect('data.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    rows = cursor.execute(sql, params).fetchall()
    conn.close()

    return jsonify([dict(row) for row in rows])

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(app.static_folder, filename)

if __name__ == '__main__':
    app.run(debug=True)
