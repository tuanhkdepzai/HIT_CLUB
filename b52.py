import json
import threading
import time
import os
import logging
from urllib.request import urlopen, Request
from flask import Flask, jsonify

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

HOST = '0.0.0.0'
POLL_INTERVAL = 5
RETRY_DELAY = 5
MAX_HISTORY = 50

# Khởi tạo locks và bộ nhớ riêng biệt
lock_tx = threading.Lock()
lock_md5 = threading.Lock()

latest_tx = {"Phien": 0, "Xuc_xac_1": 0, "Xuc_xac_2": 0, "Xuc_xac_3": 0, "Tong": 0, "Ket_qua": "Chưa có", "id": "thanhnhatx"}
latest_md5 = {"Phien": 0, "Xuc_xac_1": 0, "Xuc_xac_2": 0, "Xuc_xac_3": 0, "Tong": 0, "Ket_qua": "Chưa có", "id": "thanhnhatx"}

history_tx = []
history_md5 = []

def get_tai_xiu(d1, d2, d3):
    total = d1 + d2 + d3
    return "Xỉu" if total <= 10 else "Tài"

def update_data(store, history, lock, result):
    with lock:
        store.clear()
        store.update(result)
        # Chèn vào đầu danh sách lịch sử
        history.insert(0, result.copy())
        if len(history) > MAX_HISTORY:
            history.pop()

def poll_game_data(gid, is_md5):
    """Luồng lấy dữ liệu riêng biệt cho từng loại game"""
    last_sid = None
    # Biến tạm để giữ SID cho Tài Xỉu thường (vì CMD 1008 trả về SID, CMD 1003 trả về xúc xắc)
    pending_sid = None 
    
    url = f"https://jakpotgwab.geightdors.net/glms/v1/notify/taixiu?platform_id=g8&gid={gid}"
    
    while True:
        try:
            req = Request(url, headers={'User-Agent': 'Python-Proxy/1.0'})
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            
            if data.get('status') == 'OK' and isinstance(data.get('data'), list):
                for item in data['data']:
                    cmd = item.get("cmd")
                    
                    # LOGIC CHO MD5 (GID: vgmn_101)
                    if is_md5 and cmd == 2006:
                        sid = item.get("sid")
                        d1, d2, d3 = item.get("d1"), item.get("d2"), item.get("d3")
                        if sid and sid != last_sid and None not in (d1, d2, d3):
                            last_sid = sid
                            res = {
                                "Phien": sid, "Xuc_xac_1": d1, "Xuc_xac_2": d2, "Xuc_xac_3": d3,
                                "Tong": d1+d2+d3, "Ket_qua": get_tai_xiu(d1, d2, d3), "id": "thanhnhatx"
                            }
                            update_data(latest_md5, history_md5, lock_md5, res)
                            logger.info(f"[MD5] Cập nhật phiên: {sid}")

                    # LOGIC CHO TÀI XỈU THƯỜNG (GID: vgmn_100)
                    elif not is_md5:
                        if cmd == 1008:
                            pending_sid = item.get("sid")
                        elif cmd == 1003 and pending_sid:
                            d1, d2, d3 = item.get("d1"), item.get("d2"), item.get("d3")
                            if pending_sid != last_sid and None not in (d1, d2, d3):
                                last_sid = pending_sid
                                res = {
                                    "Phien": pending_sid, "Xuc_xac_1": d1, "Xuc_xac_2": d2, "Xuc_xac_3": d3,
                                    "Tong": d1+d2+d3, "Ket_qua": get_tai_xiu(d1, d2, d3), "id": "thanhnhatx"
                                }
                                update_data(latest_tx, history_tx, lock_tx, res)
                                logger.info(f"[TX] Cập nhật phiên: {pending_sid}")
                                pending_sid = None

        except Exception as e:
            logger.error(f"Lỗi API {gid}: {e}")
            time.sleep(RETRY_DELAY)
        time.sleep(POLL_INTERVAL)

app = Flask(__name__)

# --- ENDPOINTS ---

@app.route("/api/taixiu")
def get_tx():
    with lock_tx: return jsonify(latest_tx)

@app.route("/api/taixiumd5")
def get_md5():
    with lock_md5: return jsonify(latest_md5)

@app.route("/api/history/taixiu")
def get_history_tx():
    with lock_tx: return jsonify(history_tx)

@app.route("/api/history/md5")
def get_history_md5():
    with lock_md5: return jsonify(history_md5)

@app.route("/")
def index():
    return {
        "status": "running",
        "endpoints": [
            "/api/taixiu", "/api/taixiumd5", 
            "/api/history/taixiu", "/api/history/md5"
        ]
    }

if __name__ == "__main__":
    # Khởi chạy 2 luồng độc lập hoàn toàn
    threading.Thread(target=poll_game_data, args=("vgmn_100", False), daemon=True).start()
    threading.Thread(target=poll_game_data, args=("vgmn_101", True), daemon=True).start()
    
    port = int(os.environ.get("PORT", 8000))
    app.run(host=HOST, port=port)