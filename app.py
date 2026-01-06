# app.py - Railway Optimized Version
import os
from flask import Flask, request, jsonify, render_template_string, send_from_directory, Response
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import json
import logging
from datetime import datetime, timedelta
import time
import random
import string
import requests
import re
from werkzeug.utils import secure_filename

# ==================== 1. RAILWAY CONFIGURATION ====================
# Get from Railway Environment Variables
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8295150408:AAF1P_IcRG-z8L54PNzZVFKNXts0Uwy0TtY')
ADMIN_ID = os.environ.get('ADMIN_ID', '8435248854')
BASE_URL = os.environ.get('BASE_URL', 'https://web-production-7f83a.up.railway.app')
PORT = int(os.environ.get('PORT', 8080))

# Directory Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")

# File Paths
USERS_FILE = os.path.join(DATA_DIR, "users.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
WITHDRAWALS_FILE = os.path.join(DATA_DIR, "withdrawals.json")
GIFTS_FILE = os.path.join(DATA_DIR, "gifts.json")
LEADERBOARD_FILE = os.path.join(DATA_DIR, "leaderboard.json")

# Logging for Railway
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# App Setup
app = Flask(__name__, static_folder=STATIC_DIR)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Initialize Bot
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

# Ensure Directories
for d in [DATA_DIR, STATIC_DIR, UPLOAD_FOLDER]:
    os.makedirs(d, exist_ok=True)

# Initialize default files
def init_default_files():
    default_files = {
        USERS_FILE: {},
        SETTINGS_FILE: {
            "bot_name": "CYBER EARN ULTIMATE",
            "min_withdrawal": 100.0,
            "welcome_bonus": 50.0,
            "channels": [],
            "admins": [],
            "auto_withdraw": False,
            "bots_disabled": False,
            "ignore_device_check": False,
            "withdraw_disabled": False,
            "logo_filename": "logo_default.png",
            "min_refer_reward": 10.0,
            "max_refer_reward": 50.0
        },
        WITHDRAWALS_FILE: [],
        GIFTS_FILE: [],
        LEADERBOARD_FILE: {"last_updated": "2000-01-01", "data": []}
    }
    
    for filepath, default_data in default_files.items():
        if not os.path.exists(filepath):
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(default_data, f, indent=4)
            logger.info(f"Created default file: {filepath}")

# Run initialization
init_default_files()

# ==================== 2. DATA MANAGEMENT ====================
def load_json(filepath, default):
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        return default
    except Exception as e:
        logger.error(f"Error loading {filepath}: {e}")
        return default

def save_json(filepath, data):
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error saving {filepath}: {e}")
        return False

def get_settings():
    defaults = {
        "bot_name": "CYBER EARN ULTIMATE",
        "min_withdrawal": 100.0,
        "welcome_bonus": 50.0,
        "channels": [],
        "admins": [],
        "auto_withdraw": False,
        "bots_disabled": False,
        "ignore_device_check": False,
        "withdraw_disabled": False,
        "logo_filename": "logo_default.png",
        "min_refer_reward": 10.0,
        "max_refer_reward": 50.0
    }
    current = load_json(SETTINGS_FILE, defaults)
    for k, v in defaults.items():
        if k not in current:
            current[k] = v
    return current

def is_admin(user_id):
    s = get_settings()
    uid = str(user_id)
    return uid == str(ADMIN_ID) or uid in s.get('admins', [])

# ==================== 3. UTILS ====================
def safe_send_message(chat_id, text, reply_markup=None):
    try:
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Send Error {chat_id}: {e}")

def get_user_full_name(user):
    name_parts = []
    if user.first_name:
        name_parts.append(user.first_name)
    if user.last_name:
        name_parts.append(user.last_name)
    return " ".join(name_parts) if name_parts else "User"

def generate_code(length=5):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def generate_refer_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=7))

def update_leaderboard():
    try:
        users = load_json(USERS_FILE, {})
        leaderboard = []
        
        for uid, user_data in users.items():
            leaderboard.append({
                "user_id": uid,
                "name": user_data.get("name", "Unknown"),
                "balance": float(user_data.get("balance", 0)),
                "total_refers": len(user_data.get("referred_users", []))
            })
        
        leaderboard.sort(key=lambda x: x["balance"], reverse=True)
        leaderboard = leaderboard[:20]
        
        data = {"last_updated": datetime.now().isoformat(), "data": leaderboard}
        save_json(LEADERBOARD_FILE, data)
        return data
    except Exception as e:
        logger.error(f"Error updating leaderboard: {e}")
        return {"last_updated": datetime.now().isoformat(), "data": []}

def check_gift_code_expiry():
    gifts = load_json(GIFTS_FILE, [])
    updated = False
    current_time = datetime.now()
    
    for gift in gifts[:]:
        if "expiry" in gift:
            try:
                expiry_time = datetime.fromisoformat(gift["expiry"])
                if expiry_time < current_time:
                    gift["expired"] = True
                    updated = True
            except:
                pass
    
    if updated:
        save_json(GIFTS_FILE, gifts)
    return gifts

# ==================== 4. BOT HANDLERS ====================
@bot.chat_join_request_handler()
def auto_approve(message):
    try:
        bot.approve_chat_join_request(message.chat.id, message.from_user.id)
    except Exception as e:
        logger.error(f"Auto approve error: {e}")

@bot.message_handler(commands=['start'])
def handle_start(message):
    try:
        settings = get_settings()
        uid = str(message.from_user.id)
        
        if settings['bots_disabled'] and not is_admin(uid):
            safe_send_message(message.chat.id, "⛔ *System Maintenance*")
            return
        
        refer_code = None
        if len(message.text.split()) > 1:
            refer_code = message.text.split()[1]
        
        users = load_json(USERS_FILE, {})
        is_new = uid not in users
        
        if is_new:
            user_refer_code = generate_refer_code()
            while any(user.get('refer_code') == user_refer_code for user in users.values()):
                user_refer_code = generate_refer_code()
            
            full_name = get_user_full_name(message.from_user)
            users[uid] = {
                "balance": 0.0,
                "verified": False,
                "name": full_name,
                "joined_date": datetime.now().isoformat(),
                "ip": None,
                "device_id": None,
                "refer_code": user_refer_code,
                "referred_by": refer_code if refer_code else None,
                "referred_users": [],
                "claimed_gifts": []
            }
            
            if refer_code:
                for referrer_id, referrer_data in users.items():
                    if referrer_data.get('refer_code') == refer_code:
                        min_reward = float(settings.get('min_refer_reward', 10))
                        max_reward = float(settings.get('max_refer_reward', 50))
                        reward = random.uniform(min_reward, max_reward)
                        reward = round(reward, 2)
                        
                        referrer_data['balance'] = float(referrer_data.get('balance', 0)) + reward
                        if 'referred_users' not in referrer_data:
                            referrer_data['referred_users'] = []
                        referrer_data['referred_users'].append(uid)
                        
                        w_list = load_json(WITHDRAWALS_FILE, [])
                        w_list.append({
                            "tx_id": f"REF-{generate_code(5)}",
                            "user_id": referrer_id,
                            "name": "Referral Bonus",
                            "amount": reward,
                            "upi": "-",
                            "status": "completed",
                            "date": datetime.now().strftime("%Y-%m-%d %H:%M")
                        })
                        save_json(WITHDRAWALS_FILE, w_list)
                        
                        safe_send_message(referrer_id, f"🎉 *Referral Bonus!*\nYou earned ₹{reward} for referring {full_name}")
                        break
            
            save_json(USERS_FILE, users)
            
            msg = f"🔔 *New User*\nName: {full_name}\nID: `{uid}`"
            if refer_code:
                msg += f"\nReferred by: `{refer_code}`"
            safe_send_message(ADMIN_ID, msg)
            for adm in settings.get('admins', []):
                safe_send_message(adm, msg)
        
        display_name = message.from_user.first_name or "USER"
        img_url = f"https://res.cloudinary.com/dneusgyzc/image/upload/l_text:Stalinist%20One_90_bold_center:{display_name},co_white,g_center/v1767253426/botpy_fdkyke.jpg"
        
        markup = InlineKeyboardMarkup(row_width=1)
        for ch in settings['channels']:
            markup.add(InlineKeyboardButton(ch.get('btn_name', 'Channel'), url=ch.get('link', '#')))
        
        web_app = WebAppInfo(url=f"{BASE_URL}/mini_app?user_id={uid}")
        markup.add(InlineKeyboardButton("✅ VERIFY & START EARNING", web_app=web_app))
        
        if is_admin(uid):
            markup.add(InlineKeyboardButton("👑 Open Admin Panel", url=f"{BASE_URL}/admin_panel?user_id={uid}"))

        cap = f"👋 *WELCOME {display_name}!*\n\n🚀 Complete the steps below to start earning ₹{settings['welcome_bonus']}!"
        
        try:
            bot.send_photo(message.chat.id, img_url, caption=cap, parse_mode="Markdown", reply_markup=markup)
        except:
            safe_send_message(message.chat.id, cap, reply_markup=markup)
            
    except Exception as e:
        logger.error(f"Start handler error: {e}")

# ==================== 5. WEBAPP ROUTES ====================
@app.route('/')
def home():
    return "Telegram Bot is running! Use /start in Telegram."

@app.route('/mini_app')
def mini_app():
    try:
        uid = request.args.get('user_id')
        if not uid:
            return "User ID required", 400
            
        users = load_json(USERS_FILE, {})
        settings = get_settings()
        user = users.get(str(uid), {"name": "Guest", "balance": 0.0, "verified": False})
        
        leaderboard_data = load_json(LEADERBOARD_FILE, {"last_updated": "2000-01-01", "data": []})
        last_updated = datetime.fromisoformat(leaderboard_data.get("last_updated", "2000-01-01T00:00:00"))
        if (datetime.now() - last_updated).total_seconds() > 600:
            leaderboard_data = update_leaderboard()
        
        return render_template_string(MINI_APP_TEMPLATE, 
            user=user, 
            user_id=uid, 
            settings=settings, 
            base_url=BASE_URL, 
            timestamp=int(time.time()),
            leaderboard=leaderboard_data.get("data", [])
        )
    except Exception as e:
        logger.error(f"Mini app error: {e}")
        return "Internal Server Error", 500

@app.route('/get_pfp')
def get_pfp():
    uid = request.args.get('uid')
    try:
        photos = bot.get_user_profile_photos(uid)
        if photos.total_count > 0:
            file_id = photos.photos[0][0].file_id
            file_info = bot.get_file(file_id)
            dl_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
            return Response(requests.get(dl_url).content, mimetype='image/jpeg')
    except Exception as e:
        logger.error(f"PFP error: {e}")
    return "No Image", 404

@app.route('/api/verify', methods=['POST'])
def api_verify():
    try:
        data = request.json
        uid = str(data.get('user_id', ''))
        fp = str(data.get('fp', ''))
        client_ip = request.remote_addr
        
        if not uid:
            return jsonify({'ok': False, 'msg': 'User ID required'})
        
        users = load_json(USERS_FILE, {})
        settings = get_settings()
        
        if uid not in users:
            return jsonify({'ok': False, 'msg': 'User not found'})
        
        if settings['channels']:
            missing = []
            for ch in settings['channels']:
                try:
                    if ch.get('id'):
                        status = bot.get_chat_member(ch['id'], uid).status
                        if status not in ['member', 'administrator', 'creator', 'restricted']:
                            missing.append(ch.get('btn_name', 'Channel'))
                except:
                    missing.append(ch.get('btn_name', 'Channel'))
            
            if missing: 
                return jsonify({'ok': False, 'msg': f"Please join: {', '.join(missing)}"})

        if not users[uid].get('verified'):
            if not settings.get('ignore_device_check', False):
                for u_id, u_data in users.items():
                    if u_id == uid: 
                        continue
                    if u_data.get('verified') and str(u_data.get('device_id', '')) == fp:
                        return jsonify({'ok': False, 'msg': '⚠️ Device already used!'})

            try: 
                bonus = float(settings.get('welcome_bonus', 50))
            except: 
                bonus = 50.0
            
            users[uid].update({
                'verified': True, 
                'device_id': fp, 
                'ip': client_ip,
                'balance': float(users[uid].get('balance', 0)) + bonus
            })
            
            if users[uid].get('referred_by'):
                refer_code = users[uid]['referred_by']
                for referrer_id, referrer_data in users.items():
                    if referrer_data.get('refer_code') == refer_code:
                        if uid not in referrer_data.get('referred_users', []):
                            min_reward = float(settings.get('min_refer_reward', 10))
                            max_reward = float(settings.get('max_refer_reward', 50))
                            reward = random.uniform(min_reward, max_reward)
                            reward = round(reward, 2)
                            
                            referrer_data['balance'] = float(referrer_data.get('balance', 0)) + reward
                            if 'referred_users' not in referrer_data:
                                referrer_data['referred_users'] = []
                            referrer_data['referred_users'].append(uid)
                            
                            w_list = load_json(WITHDRAWALS_FILE, [])
                            w_list.append({
                                "tx_id": f"REF-VERIFY-{generate_code(5)}",
                                "user_id": referrer_id,
                                "name": "Referral Bonus (Verified)",
                                "amount": reward,
                                "upi": "-",
                                "status": "completed",
                                "date": datetime.now().strftime("%Y-%m-%d %H:%M")
                            })
                            save_json(WITHDRAWALS_FILE, w_list)
                            
                            safe_send_message(referrer_id, f"🎉 *Referral Bonus!*\nYou earned ₹{reward} for {users[uid]['name']}'s verification")
                        break
            
            save_json(USERS_FILE, users)
            
            w_list = load_json(WITHDRAWALS_FILE, [])
            w_list.append({
                "tx_id": "BONUS", 
                "user_id": uid, 
                "name": "Signup Bonus",
                "amount": bonus, 
                "upi": "-", 
                "status": "completed",
                "date": datetime.now().strftime("%Y-%m-%d %H:%M")
            })
            save_json(WITHDRAWALS_FILE, w_list)
            return jsonify({'ok': True, 'bonus': bonus})
        
        return jsonify({'ok': True, 'bonus': 0}) 

    except Exception as e:
        logger.error(f"Verify error: {e}")
        return jsonify({'ok': False, 'msg': f"Error: {str(e)}"})

@app.route('/api/withdraw', methods=['POST'])
def api_withdraw():
    try:
        data = request.json
        uid = str(data.get('user_id', ''))
        try: 
            amt = float(data.get('amount', 0))
        except: 
            return jsonify({'ok': False, 'msg': 'Invalid Amount'})
        upi = str(data.get('upi', ''))
        
        users = load_json(USERS_FILE, {})
        settings = get_settings()
        
        if settings.get('withdraw_disabled'):
            return jsonify({'ok': False, 'msg': '❌ Withdrawals are currently disabled'})
        
        if not re.match(r"[\w\.\-_]{2,}@[\w]{2,}", upi):
            return jsonify({'ok': False, 'msg': '❌ Invalid UPI Format'})
            
        min_w = float(settings.get('min_withdrawal', 100))
        if amt < min_w:
            return jsonify({'ok': False, 'msg': f'⚠️ Min Withdraw: ₹{min_w}'})
            
        cur_bal = float(users.get(uid, {}).get('balance', 0))
        if cur_bal < amt:
            return jsonify({'ok': False, 'msg': '❌ Insufficient Balance'})
        
        users[uid]['balance'] = cur_bal - amt
        save_json(USERS_FILE, users)
        
        tx_id = generate_code(5)
        record = {
            "tx_id": tx_id, 
            "user_id": uid, 
            "name": users[uid].get('name', 'User'), 
            "amount": amt, 
            "upi": upi, 
            "status": "pending", 
            "date": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        
        is_auto = settings.get('auto_withdraw', False)
        msg_client = ""
        
        if is_auto:
            record['status'] = 'completed'
            record['utr'] = f"AUTO-{int(time.time())}"
            msg_client = f"✅ PAID! UTR: {record['utr']}"
            safe_send_message(uid, f"✅ *Auto-Withdrawal Paid!*\nAmt: ₹{amt}\nUTR: `{record['utr']}`\nTxID: `{tx_id}`")
        else:
            msg_client = "✅ Request Sent! Waiting for Admin..."
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("Open Admin Panel", url=f"{BASE_URL}/admin_panel?user_id={ADMIN_ID}"))
            
            msg_adm = f"💸 *New Withdrawal*\nUser: {users[uid]['name']}\nAmt: ₹{amt}\nTxID: `{tx_id}`"
            safe_send_message(ADMIN_ID, msg_adm, reply_markup=markup)
            for adm in settings.get('admins', []):
                safe_send_message(adm, msg_adm, reply_markup=markup)

        w_list = load_json(WITHDRAWALS_FILE, [])
        w_list.append(record)
        save_json(WITHDRAWALS_FILE, w_list)
        
        return jsonify({
            'ok': True, 
            'msg': msg_client, 
            'auto': is_auto, 
            'utr': record.get('utr', ''), 
            'tx_id': tx_id
        })
        
    except Exception as e:
        logger.error(f"Withdraw Error: {e}")
        return jsonify({'ok': False, 'msg': f"Error: {str(e)}"})

@app.route('/api/history')
def api_history():
    try:
        uid = request.args.get('user_id')
        if not uid:
            return jsonify([])
        
        history = [w for w in load_json(WITHDRAWALS_FILE, []) if w.get('user_id') == uid]
        return jsonify(history[::-1])
    except Exception as e:
        logger.error(f"History error: {e}")
        return jsonify([])

@app.route('/api/contact_upload', methods=['POST'])
def api_contact():
    try:
        uid = request.form.get('user_id')
        msg = request.form.get('msg', '')
        f = request.files.get('image')
        
        if not uid:
            return jsonify({'ok': False, 'msg': 'User ID required'})
            
        cap = f"📩 *Msg from {uid}*\n{msg}"
        recipients = [ADMIN_ID] + get_settings().get('admins', [])
        
        if f:
            filename = secure_filename(f.filename)
            path = os.path.join(UPLOAD_FOLDER, filename)
            f.save(path)
            
            with open(path, 'rb') as img:
                file_data = img.read()
                for adm in recipients:
                    try: 
                        bot.send_photo(adm, file_data, caption=cap, parse_mode="Markdown")
                    except Exception as e:
                        logger.error(f"Send photo error to {adm}: {e}")
            os.remove(path)
        else:
            for adm in recipients:
                safe_send_message(adm, cap)
                
        return jsonify({'ok': True})
    except Exception as e:
        logger.error(f"Contact error: {e}")
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/api/claim_gift', methods=['POST'])
def api_claim_gift():
    try:
        data = request.json
        uid = str(data.get('user_id', ''))
        code = str(data.get('code', '')).strip().upper()
        
        if not uid:
            return jsonify({'ok': False, 'msg': 'User ID required'})
        
        users = load_json(USERS_FILE, {})
        if uid not in users:
            return jsonify({'ok': False, 'msg': 'User not found'})
        
        if 'claimed_gifts' not in users[uid]:
            users[uid]['claimed_gifts'] = []
        
        if code in users[uid]['claimed_gifts']:
            return jsonify({'ok': False, 'msg': 'Already claimed this code'})
        
        gifts = check_gift_code_expiry()
        
        for gift in gifts:
            if gift.get('code') == code:
                if gift.get('expired'):
                    return jsonify({'ok': False, 'msg': '❌ Gift code expired'})
                if not gift.get('is_active', True):
                    return jsonify({'ok': False, 'msg': 'Code is inactive'})
                
                if len(gift.get('used_by', [])) >= gift.get('total_uses', 1):
                    return jsonify({'ok': False, 'msg': 'Code usage limit reached'})
                
                amount = random.uniform(
                    float(gift.get('min_amount', 10)),
                    float(gift.get('max_amount', 50))
                )
                amount = round(amount, 2)
                
                users[uid]['balance'] = float(users[uid].get('balance', 0)) + amount
                users[uid]['claimed_gifts'].append(code)
                
                if 'used_by' not in gift:
                    gift['used_by'] = []
                gift['used_by'].append(uid)
                
                w_list = load_json(WITHDRAWALS_FILE, [])
                w_list.append({
                    "tx_id": f"GIFT-{generate_code(5)}",
                    "user_id": uid,
                    "name": "Gift Code Reward",
                    "amount": amount,
                    "upi": "-",
                    "status": "completed",
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M")
                })
                
                save_json(USERS_FILE, users)
                save_json(GIFTS_FILE, gifts)
                save_json(WITHDRAWALS_FILE, w_list)
                
                return jsonify({
                    'ok': True, 
                    'msg': f'🎉 Gift code claimed! ₹{amount} added to your balance',
                    'amount': amount
                })
        
        return jsonify({'ok': False, 'msg': 'Invalid gift code'})
    except Exception as e:
        logger.error(f"Claim gift error: {e}")
        return jsonify({'ok': False, 'msg': f'Error: {str(e)}'})

@app.route('/api/get_refer_info')
def api_get_refer_info():
    try:
        uid = request.args.get('user_id')
        if not uid:
            return jsonify({'ok': False, 'msg': 'User ID required'})
        
        users = load_json(USERS_FILE, {})
        
        if uid not in users:
            return jsonify({'ok': False, 'msg': 'User not found'})
        
        user = users[uid]
        
        if not user.get('refer_code'):
            user['refer_code'] = generate_refer_code()
            save_json(USERS_FILE, users)
        
        refer_code = user.get('refer_code', '')
        referred_users = user.get('referred_users', [])
        
        bot_username = bot.get_me().username
        
        referred_details = []
        for ref_uid in referred_users:
            if ref_uid in users:
                status = "✅ VERIFIED" if users[ref_uid].get('verified') else "⏳ PENDING"
                referred_details.append({
                    'id': ref_uid,
                    'name': users[ref_uid].get('name', 'Unknown'),
                    'status': status
                })
        
        return jsonify({
            'ok': True,
            'refer_code': refer_code,
            'refer_link': f'https://t.me/{bot_username}?start={refer_code}',
            'referred_users': referred_details,
            'total_refers': len(referred_users)
        })
    except Exception as e:
        logger.error(f"Refer info error: {e}")
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/api/leaderboard')
def api_leaderboard():
    try:
        data = update_leaderboard()
        return jsonify(data)
    except Exception as e:
        logger.error(f"Leaderboard error: {e}")
        return jsonify({"last_updated": datetime.now().isoformat(), "data": []})

# ==================== 6. ADMIN PANEL ====================
@app.route('/admin_panel')
def admin_panel():
    try:
        uid = request.args.get('user_id')
        if not uid or not is_admin(uid): 
            return "⛔ Unauthorized"
        
        all_withdrawals = load_json(WITHDRAWALS_FILE, [])
        filtered_withdrawals = []
        for w in all_withdrawals:
            tx_id = w.get('tx_id', '')
            if tx_id != "BONUS" and not tx_id.startswith('REF-') and not tx_id.startswith('GIFT-'):
                filtered_withdrawals.append(w)
        
        gifts = check_gift_code_expiry()
        
        current_time = datetime.now()
        for gift in gifts:
            if 'expiry' in gift:
                try:
                    expiry_time = datetime.fromisoformat(gift['expiry'])
                    remaining_minutes = max(0, int((expiry_time - current_time).total_seconds() / 60))
                    gift['remaining_minutes'] = remaining_minutes
                except:
                    gift['remaining_minutes'] = 0
        
        return render_template_string(ADMIN_TEMPLATE, 
            settings=get_settings(), 
            users=load_json(USERS_FILE, {}), 
            withdrawals=filtered_withdrawals[::-1], 
            stats={
                "total_users": len(load_json(USERS_FILE, {})), 
                "pending_count": len([w for w in filtered_withdrawals if w.get('status') == 'pending'])
            },
            timestamp=int(time.time()),
            admin_id=uid,
            gifts=gifts,
            now=current_time
        )
    except Exception as e:
        logger.error(f"Admin panel error: {e}")
        return f"Internal Server Error: {str(e)}", 500

@app.route('/admin/update_basic', methods=['POST'])
def admin_update_basic():
    try:
        s = get_settings()
        d = request.json
        
        try:
            s['min_withdrawal'] = float(d.get('min_withdrawal', 100))
            s['welcome_bonus'] = float(d.get('welcome_bonus', 50))
            s['min_refer_reward'] = float(d.get('min_refer_reward', 10))
            s['max_refer_reward'] = float(d.get('max_refer_reward', 50))
        except:
            pass
        
        for k in ['bot_name','bots_disabled','auto_withdraw','ignore_device_check','withdraw_disabled']:
            if k in d:
                s[k] = d[k]
        
        save_json(SETTINGS_FILE, s)
        return jsonify({'ok': True})
    except Exception as e:
        logger.error(f"Update basic error: {e}")
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/admin/manage_admins', methods=['POST'])
def admin_manage_admins():
    try:
        d = request.json
        s = get_settings()
        if 'admins' not in s: 
            s['admins'] = []
        
        tid = str(d.get('id', '')).strip()
        action = d.get('action', '')
        
        if action == 'add':
            if tid and tid != str(ADMIN_ID) and tid not in s['admins']:
                s['admins'].append(tid)
        elif action == 'remove':
            if tid in s['admins']:
                s['admins'].remove(tid)
                
        save_json(SETTINGS_FILE, s)
        return jsonify({'ok': True})
    except Exception as e:
        logger.error(f"Manage admins error: {e}")
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/admin/channels', methods=['POST'])
def admin_channels():
    try:
        d = request.json
        s = get_settings()
        action = d.get('action', '')
        
        if action == 'add':
            s['channels'].append({
                "btn_name": d.get('name', 'Channel'),
                "link": d.get('link', '#'),
                "id": d.get('id', '')
            })
        elif action == 'delete':
            index = int(d.get('index', 0))
            if 0 <= index < len(s['channels']):
                del s['channels'][index]
        
        save_json(SETTINGS_FILE, s)
        return jsonify({'ok': True})
    except Exception as e:
        logger.error(f"Channels error: {e}")
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/admin/process_withdraw', methods=['POST'])
def admin_process_withdraw():
    try:
        d = request.json
        w_list = load_json(WITHDRAWALS_FILE, [])
        
        for w in w_list:
            if w.get('tx_id') == d.get('tx_id') and w.get('status') == 'pending':
                w['status'] = d.get('status', '')
                w['utr'] = d.get('utr', '')
                
                if d.get('status') == 'completed': 
                    safe_send_message(w['user_id'], f"✅ *Withdrawal Paid!*\nAmt: ₹{w['amount']}\nUTR: `{w['utr']}`\nTxID: `{w['tx_id']}`")
                else:
                    users = load_json(USERS_FILE, {})
                    if w['user_id'] in users:
                        users[w['user_id']]['balance'] = float(users[w['user_id']].get('balance', 0)) + float(w['amount'])
                        save_json(USERS_FILE, users)
                        safe_send_message(w['user_id'], f"❌ *Withdrawal Rejected*\nAmt: ₹{w['amount']}\nRefunded to balance.\nTxID: `{w['tx_id']}`")
                break
                
        save_json(WITHDRAWALS_FILE, w_list)
        return jsonify({'ok': True})
    except Exception as e:
        logger.error(f"Process withdraw error: {e}")
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/admin/upload_logo', methods=['POST'])
def admin_logo():
    try:
        if 'logo' in request.files:
            f = request.files['logo']
            f.save(os.path.join(STATIC_DIR, "logo_custom.png"))
            s = get_settings()
            s['logo_filename'] = "logo_custom.png"
            save_json(SETTINGS_FILE, s)
            return jsonify({'ok': True})
        return jsonify({'ok': False, 'msg': 'No file uploaded'})
    except Exception as e:
        logger.error(f"Upload logo error: {e}")
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/admin/broadcast', methods=['POST'])
def admin_broadcast():
    try:
        txt = request.form.get('text', '')
        f = request.files.get('image')
        users = load_json(USERS_FILE, {})
        cnt = 0
        
        if f:
            filename = secure_filename(f.filename)
            path = os.path.join(UPLOAD_FOLDER, filename)
            f.save(path)
            
            with open(path, 'rb') as img:
                idata = img.read()
                for u in users:
                    try: 
                        bot.send_photo(u, idata, caption=txt)
                        cnt += 1
                    except: 
                        pass
            os.remove(path)
        else:
            for u in users:
                try: 
                    bot.send_message(u, txt)
                    cnt += 1
                except: 
                    pass
        return jsonify({'count': cnt})
    except Exception as e:
        logger.error(f"Broadcast error: {e}")
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/admin/create_gift', methods=['POST'])
def admin_create_gift():
    try:
        data = request.json
        code = data.get('code', '').strip().upper()
        auto_gen = data.get('auto_generate', False)
        
        if auto_gen or not code:
            code = generate_code(5)
        elif len(code) != 5 or not code.isalnum():
            return jsonify({'ok': False, 'msg': 'Code must be 5 alphanumeric characters'})
        
        gifts = load_json(GIFTS_FILE, [])
        if any(g.get('code') == code for g in gifts):
            return jsonify({'ok': False, 'msg': 'Code already exists'})
        
        expiry_hours = int(data.get('expiry_hours', 2))
        expiry_time = datetime.now() + timedelta(hours=expiry_hours)
        
        gift = {
            'code': code,
            'min_amount': float(data.get('min_amount', 10)),
            'max_amount': float(data.get('max_amount', 50)),
            'expiry': expiry_time.isoformat(),
            'total_uses': int(data.get('total_uses', 1)),
            'used_by': [],
            'is_active': True,
            'expired': False,
            'created_at': datetime.now().isoformat(),
            'created_by': request.args.get('user_id', 'admin')
        }
        
        gifts.append(gift)
        save_json(GIFTS_FILE, gifts)
        
        return jsonify({'ok': True, 'code': code})
    except Exception as e:
        logger.error(f"Create gift error: {e}")
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/admin/toggle_gift', methods=['POST'])
def admin_toggle_gift():
    try:
        data = request.json
        code = data.get('code')
        action = data.get('action')
        
        gifts = load_json(GIFTS_FILE, [])
        
        for gift in gifts:
            if gift.get('code') == code:
                if action == 'toggle':
                    gift['is_active'] = not gift.get('is_active', True)
                elif action == 'delete':
                    gifts.remove(gift)
                break
        
        save_json(GIFTS_FILE, gifts)
        return jsonify({'ok': True})
    except Exception as e:
        logger.error(f"Toggle gift error: {e}")
        return jsonify({'ok': False, 'msg': str(e)})

# ==================== 7. SETUP ====================
@app.route('/static/<path:filename>')
def serve_static(filename): 
    return send_from_directory(STATIC_DIR, filename)

@app.route('/setup_webhooks')
def setup_webhooks():
    try:
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(f"{BASE_URL}/webhook/main")
        return "✅ Webhook Configured"
    except Exception as e:
        return f"Error: {str(e)}"

@app.route('/webhook/main', methods=['POST'])
def wm():
    if request.headers.get('content-type') == 'application/json':
        try:
            json_string = request.get_data().decode('utf-8')
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return ''
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return 'Error', 500
    return 'OK', 200

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

# ==================== 9. HTML TEMPLATES ====================

MINI_APP_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;700&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/clientjs@0.2.1/dist/client.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.6.0/dist/confetti.browser.min.js"></script>
    <style>
        :root { --bg: #050508; --cyan: #00f3ff; --gold: #ffd700; --panel: rgba(255,255,255,0.05); }
        body { background: radial-gradient(circle at top, #111122, var(--bg)); color: white; font-family: 'Rajdhani', sans-serif; margin: 0; padding: 0; box-sizing: border-box; min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: flex-start; overflow-x: hidden; width: 100%; }
        .hidden { display: none !important; }
        .header { display: flex; align-items: center; justify-content: center; gap: 15px; margin: 15px 0; width: 100%; padding: 0 5%; }
        .logo { width: 50px; height: 50px; border-radius: 50%; border: 2px solid var(--cyan); box-shadow: 0 0 15px rgba(0,243,255,0.3); object-fit: cover; }
        .title { font-size: 22px; font-weight: 800; text-shadow: 0 0 10px var(--cyan); letter-spacing: 1px; }
        .nav-bar { display: flex; width: 100%; max-width: 500px; background: rgba(0,0,0,0.7); border-radius: 15px; margin: 10px auto; padding: 8px; justify-content: space-around; border: 1px solid rgba(255,255,255,0.1); }
        .nav-btn { background: transparent; border: none; color: #aaa; padding: 10px 15px; border-radius: 10px; font-weight: bold; font-size: 14px; display: flex; align-items: center; gap: 5px; cursor: pointer; transition: all 0.3s; }
        .nav-btn.active { background: rgba(0,243,255,0.2); color: var(--cyan); box-shadow: 0 0 10px rgba(0,243,255,0.3); }
        .tab-content { width: 100%; max-width: 500px; padding: 0 5% 20px 5%; box-sizing: border-box; }
        .card-metal, .card-gold, .card-silver, .card-purple { width: 100%; box-sizing: border-box; border-radius: 16px; padding: 25px; margin-bottom: 20px; position: relative; overflow: hidden; }
        .card-metal { background: linear-gradient(135deg, #e0e0e0 0%, #bdc3c7 20%, #88929e 50%, #bdc3c7 80%, #e0e0e0 100%); border: 1px solid #fff; box-shadow: 0 10px 20px rgba(0,0,0,0.5), inset 0 0 15px rgba(255,255,255,0.5); display: flex; align-items: center; color: #222; }
        .card-metal::before { content: ''; position: absolute; top: 0; left: -150%; width: 60%; height: 100%; background: linear-gradient(90deg, transparent, rgba(255,255,255,0.8), transparent); animation: shine 3.5s infinite; transform: skewX(-20deg); }
        @keyframes shine { 100% { left: 200%; } }
        .p-pic-wrapper { position: relative; width: 60px; height: 60px; margin-right: 15px; z-index: 2; flex-shrink: 0; }
        .p-pic { width: 100%; height: 100%; border-radius: 50%; border: 3px solid #333; object-fit: cover; }
        .p-icon { display: none; width: 100%; height: 100%; border-radius: 50%; border: 3px solid #333; background: #ddd; align-items: center; justify-content: center; font-size: 24px; color: #333; }
        .card-gold { background: radial-gradient(ellipse at center, #ffd700 0%, #d4af37 40%, #b8860b 100%); text-align: center; color: #2e2003; border: 2px solid #fff2ad; box-shadow: 0 0 25px rgba(255, 215, 0, 0.4), inset 0 0 10px rgba(255, 255, 255, 0.4); animation: pulse-gold 3s infinite; }
        .card-gold::after { content: ''; position: absolute; top: -50%; left: -50%; width: 200%; height: 200%; background: radial-gradient(circle, rgba(255,255,255,0.3) 0%, transparent 60%); transform: rotate(30deg); pointer-events: none; }
        @keyframes pulse-gold { 50% { box-shadow: 0 0 40px rgba(255,215,0,0.6); } }
        .card-silver { background: linear-gradient(135deg, #c0c0c0 0%, #d0d0d0 30%, #e0e0e0 50%, #d0d0d0 70%, #c0c0c0 100%); border: 1px solid #fff; box-shadow: 0 10px 20px rgba(0,0,0,0.3); color: #222; text-align: center; aspect-ratio: 16/9; display: flex; flex-direction: column; justify-content: center; align-items: center; }
        .card-purple { background: linear-gradient(135deg, #9d4edd 0%, #7b2cbf 50%, #5a189a 100%); border: 1px solid #c77dff; box-shadow: 0 0 20px rgba(157,78,221,0.5); color: white; text-align: center; aspect-ratio: 16/9; display: flex; flex-direction: column; justify-content: center; align-items: center; position: relative; }
        .card-purple::before { content: ''; position: absolute; top: -10px; left: -10px; right: -10px; bottom: -10px; background: linear-gradient(45deg, #9d4edd, #7b2cbf, #5a189a, #9d4edd); z-index: -1; border-radius: 20px; opacity: 0.5; filter: blur(10px); }
        .btn { background: #111; color: var(--gold); border: none; padding: 14px 30px; border-radius: 30px; font-weight: 800; font-size: 16px; margin-top: 15px; cursor: pointer; display: inline-flex; align-items: center; gap: 10px; font-family: 'Rajdhani'; box-shadow: 0 5px 15px rgba(0,0,0,0.3); transition: transform 0.2s; position: relative; z-index: 5; }
        .btn:active { transform: scale(0.95); }
        .btn-purple { background: #5a189a; color: white; }
        .btn-cyan { background: #00f3ff; color: #000; }
        .verify-box { height: 60vh; width: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; }
        .popup { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.9); backdrop-filter: blur(5px); display: none; justify-content: center; align-items: center; z-index: 999; padding: 20px; box-sizing: border-box; }
        .popup-content { background: #1a1a20; padding: 30px; border-radius: 20px; width: 100%; max-width: 350px; border: 1px solid var(--cyan); text-align: center; box-shadow: 0 0 30px rgba(0,243,255,0.2); }
        input, textarea { width: 100%; padding: 12px; margin: 10px 0; background: #2a2a30; border: 1px solid #444; color: white; border-radius: 8px; box-sizing: border-box; font-family: inherit; }
        .hist-item { background: var(--panel); border-radius: 8px; padding: 12px; margin-bottom: 8px; display: flex; justify-content: space-between; border-left: 3px solid #333; width: 100%; box-sizing: border-box; }
        .status-completed { color: #00ff00; } .status-pending { color: orange; } .status-rejected { color: red; }
        .overlay-loader { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.95); z-index: 2000; display: none; flex-direction: column; justify-content: center; align-items: center; }
        .spinner { width: 40px; height: 40px; border: 5px solid #333; border-top: 5px solid var(--cyan); border-radius: 50%; animation: spin 1s linear infinite; margin: 20px; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .refer-code-box { background: rgba(255,255,255,0.1); border: 2px dashed var(--cyan); padding: 15px; border-radius: 10px; margin: 10px 0; font-family: monospace; font-size: 24px; letter-spacing: 3px; cursor: pointer; width: 90%; text-align: center; word-break: break-all; }
        .leaderboard-table { width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 14px; }
        .leaderboard-table tr { border-bottom: 1px solid rgba(255,255,255,0.1); }
        .leaderboard-table td { padding: 10px 5px; }
        .leaderboard-table .highlight { background: rgba(0,243,255,0.1); border-left: 3px solid var(--cyan); }
        .code-input { font-size: 24px; letter-spacing: 5px; text-align: center; text-transform: uppercase; width: 90%; margin: 10px 0; padding: 15px; border-radius: 10px; border: 2px solid silver; background: white; color: #222; }
        .gift-result { text-align: center; margin-top: 20px; padding: 15px; border-radius: 10px; background: rgba(0,0,0,0.3); }
        .referrals-list { max-height: 300px; overflow-y: auto; padding-right: 5px; }
        .referrals-list::-webkit-scrollbar { width: 5px; }
        .referrals-list::-webkit-scrollbar-track { background: rgba(255,255,255,0.1); }
        .referrals-list::-webkit-scrollbar-thumb { background: var(--cyan); border-radius: 5px; }
    </style>
</head>
<body>
    <div id="loader" class="overlay-loader" style="display:flex;"><div class="spinner"></div><div id="loader-txt" style="color:#fff; font-weight:bold; font-size:18px;">INITIALIZING...</div></div>
    
    <div id="app" class="hidden" style="width:100%; display:flex; flex-direction:column; align-items:center;">
        <div class="header"><img src="{{ base_url }}/static/{{ settings.logo_filename }}?v={{ timestamp }}" class="logo"><div class="title">{{ settings.bot_name }}</div></div>
        
        <div class="nav-bar">
            <button class="nav-btn active" onclick="switchTab('home')"><i class="fas fa-home"></i> HOME</button>
            <button class="nav-btn" onclick="switchTab('gift')"><i class="fas fa-gift"></i> GIFT</button>
            <button class="nav-btn" onclick="switchTab('refer')"><i class="fas fa-users"></i> REFER</button>
            <button class="nav-btn" onclick="switchTab('leaderboard')"><i class="fas fa-trophy"></i> RANK</button>
        </div>
        
        <div id="verify-screen" class="hidden verify-box"><i class="fas fa-shield-alt" style="font-size:50px; color:var(--cyan); margin-bottom:15px;"></i><h2 style="margin:0;">VERIFICATION</h2><p id="v-msg" style="color:#aaa; margin-top:10px;">Checking channels...</p><div class="spinner" style="margin:20px auto;"></div><button id="retry-btn" class="btn hidden" style="background:#f44; color:white;" onclick="location.reload()">RETRY</button></div>
        
        <div id="tab-home" class="tab-content">
            <div class="card-metal">
                <div class="p-pic-wrapper"><img src="/get_pfp?uid={{ user_id }}" class="p-pic" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';"><div class="p-icon"><i class="fas fa-user"></i></div></div>
                <div style="z-index:2;"><div style="font-size:18px; font-weight:800;">{{ user.name }}</div><div onclick="openPop('contact')" style="color:#0044cc; font-size:13px; margin-top:5px; cursor:pointer; text-decoration:underline; font-weight:bold;">Contact Admin</div></div>
            </div>
            
            <div class="card-gold">
                <div style="font-size:14px; font-weight:800; opacity:0.8; letter-spacing:2px;">WALLET BALANCE</div>
                <div style="font-size:48px; font-weight:900; margin:5px 0; text-shadow:0 2px 5px rgba(0,0,0,0.2);">₹{{ "%.2f"|format(user.balance) }}</div>
                <button class="btn" onclick="openPop('withdraw')"><i class="fas fa-wallet"></i> WITHDRAW</button>
            </div>
            
            <div style="margin-top:20px; width:100%;"><div style="color:#888; font-size:13px; font-weight:bold; margin-bottom:10px;">RECENT ACTIVITY</div><div id="history-list"></div></div>
        </div>
        
        <div id="tab-gift" class="tab-content hidden">
            <div style="text-align:center; margin-bottom:20px;"><h2 style="margin:0; color:var(--cyan);">GIFT CODE</h2></div>
            <div class="card-silver"><input type="text" id="gift-code" class="code-input" maxlength="5" placeholder="ABCDE" oninput="this.value = this.value.toUpperCase()"><button class="btn" onclick="claimGift()" style="background:#222; color:silver; width:90%;"><i class="fas fa-gift"></i> CLAIM NOW</button></div>
            <div id="gift-result" class="gift-result"></div>
        </div>
        
        <div id="tab-refer" class="tab-content hidden">
            <div style="text-align:center; margin-bottom:20px;"><h2 style="margin:0; color:#9d4edd;">REFER & EARN</h2></div>
            <div class="card-purple">
                <div id="refer-code-display" class="refer-code-box" onclick="copyReferCode()">LOADING...</div>
                <button class="btn btn-purple" onclick="shareReferLink()" style="width:90%; margin:15px 0;"><i class="fas fa-share-alt"></i> SHARE ON TELEGRAM</button>
                <div style="margin-top:20px; font-size:14px; text-align:center;"><div style="color:#c77dff; font-weight:bold;">Min Reward: ₹{{ settings.min_refer_reward }}</div><div style="color:#c77dff; font-weight:bold;">Max Reward: ₹{{ settings.max_refer_reward }}</div></div>
            </div>
            <div style="width:100%; margin-top:20px;"><h3 style="color:#9d4edd; margin-bottom:10px;">YOUR REFERRALS</h3><div id="referrals-list" class="referrals-list"></div></div>
        </div>
        
        <div id="tab-leaderboard" class="tab-content hidden">
            <div style="text-align:center; margin-bottom:20px;"><h2 style="margin:0; color:var(--gold);">LEADERBOARD</h2><p style="color:#aaa; font-size:14px;">Top 20 Users by Balance</p></div>
            <table class="leaderboard-table">
                <thead><tr style="background:rgba(255,215,0,0.1);"><td style="font-weight:bold; color:var(--gold);">RANK</td><td style="font-weight:bold; color:var(--gold);">NAME</td><td style="font-weight:bold; color:var(--gold); text-align:right;">BALANCE</td><td style="font-weight:bold; color:var(--gold); text-align:right;">REFERS</td></tr></thead>
                <tbody id="leaderboard-list">
                    {% for user in leaderboard %}
                    <tr {% if user.user_id == user_id %}class="highlight"{% endif %}><td style="font-weight:bold; color:#ccc;">{{ loop.index }}</td><td><div style="font-weight:bold;">{{ user.name[:15] }}{% if user.name|length > 15 %}...{% endif %}</div><div style="font-size:10px; color:#888;">{{ user.user_id[:8] }}...</div></td><td style="text-align:right; font-weight:bold; color:var(--gold);">₹{{ "%.2f"|format(user.balance) }}</td><td style="text-align:right; font-size:12px; color:#aaa;">{{ user.total_refers }}</td></tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
    
    <div id="pop-contact" class="popup"><div class="popup-content"><h3>Support</h3><textarea id="c-msg" rows="3" placeholder="Message..."></textarea><input type="file" id="c-file" accept="image/*"><button class="btn" onclick="sendContact()">SEND</button><button class="btn" onclick="closePop()" style="background:transparent; color:#f44; margin-top:10px;">Close</button></div></div>
    <div id="pop-withdraw" class="popup"><div class="popup-content"><h3>Withdraw</h3><input id="w-upi" placeholder="Enter UPI ID (e.g. name@bank)"><input id="w-amt" type="number" placeholder="Amount"><button class="btn" onclick="subW()">SUBMIT</button><button class="btn" onclick="closePop()" style="background:transparent; color:#f44; margin-top:10px;">Cancel</button></div></div>
    
    <script>
        const UID="{{ user_id }}";
        let referData=null;
        
        window.onload=()=>{setTimeout(()=>{document.getElementById('loader').style.display='none';document.getElementById('app').classList.remove('hidden');verifySilent();loadReferInfo();},600)};
        
        function switchTab(tabName){document.querySelectorAll('.nav-btn').forEach(btn=>btn.classList.remove('active'));event.target.classList.add('active');document.querySelectorAll('.tab-content').forEach(tab=>tab.classList.add('hidden'));document.getElementById('tab-'+tabName).classList.remove('hidden');if(tabName==='leaderboard'){loadLeaderboard();}}
        
        function verifySilent(){loadHistory();fetch('/api/verify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:UID,fp:'skip',bot_type:'main'})}).then(r=>r.json()).then(d=>{if(!d.ok){document.getElementById('tab-home').classList.add('hidden');document.getElementById('verify-screen').classList.remove('hidden');document.getElementById('v-msg').innerHTML=`<span style="color:#f44">${d.msg}</span>`;if(d.msg.includes('Device'))document.getElementById('retry-btn').classList.remove('hidden');}else if(d.bonus>0){refreshApp();}}).catch(err=>console.error('Verify error:',err));}
        
        function refreshApp(){fetch('/api/history?user_id='+UID).then(r=>r.json()).then(l=>{const container=document.getElementById('history-list');if(!l.length){container.innerHTML='<div style="text-align:center; color:#555; padding:20px;">No Activity</div>';return;}container.innerHTML=l.map(i=>`<div class="hist-item" style="border-left-color:${i.status=='completed'?'#0f0':i.status=='pending'?'orange':'red'}"><div><div style="font-weight:bold;">${i.name}</div><div style="font-size:11px;color:#888;">${i.date}</div>${i.tx_id&&i.tx_id!=='BONUS'?`<div style="font-size:10px;color:#aaa;">TxID: ${i.tx_id}</div>`:''}</div><div style="text-align:right;"><div style="font-weight:bold;">₹${i.amount.toFixed(2)}</div><div class="status-${i.status}">${i.status.toUpperCase()}</div>${i.utr?`<div style="font-size:10px;color:#aaa;">${i.utr}</div>`:''}</div></div>`).join('');});fetch('/mini_app?user_id='+UID).then(r=>r.text()).then(html=>{const parser=new DOMParser();const doc=parser.parseFromString(html,'text/html');const balanceElement=doc.querySelector('.card-gold div:nth-child(2)');if(balanceElement){document.querySelector('.card-gold div:nth-child(2)').textContent=balanceElement.textContent;}});}
        
        function subW(){const u=document.getElementById('w-upi').value,a=document.getElementById('w-amt').value;if(!u||!a)return alert("Fill all fields");closePop();const l=document.getElementById('loader');l.style.display='flex';document.getElementById('loader-txt').innerText="PROCESSING...";fetch('/api/withdraw',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:UID,amount:a,upi:u})}).then(r=>r.json()).then(d=>{setTimeout(()=>{l.style.display='none';if(d.ok){confetti({particleCount:200,spread:90});alert(d.msg+"\\nTxID: "+d.tx_id);refreshApp();}else{alert(d.msg);}},1000);}).catch(err=>{l.style.display='none';alert('Withdrawal failed');console.error('Withdraw error:',err);});}
        
        function sendContact(){const fd=new FormData();fd.append('user_id',UID);fd.append('msg',document.getElementById('c-msg').value);fd.append('image',document.getElementById('c-file').files[0]);fetch('/api/contact_upload',{method:'POST',body:fd}).then(()=>{alert("Sent!");closePop();}).catch(err=>{alert('Failed to send');console.error('Contact error:',err);});}
        
        function loadHistory(){fetch('/api/history?user_id='+UID).then(r=>r.json()).then(l=>{const container=document.getElementById('history-list');if(!l||!l.length){container.innerHTML='<div style="text-align:center; color:#555; padding:20px;">No Activity</div>';return;}container.innerHTML=l.map(i=>`<div class="hist-item" style="border-left-color:${i.status=='completed'?'#0f0':i.status=='pending'?'orange':'red'}"><div><div style="font-weight:bold;">${i.name}</div><div style="font-size:11px;color:#888;">${i.date}</div>${i.tx_id&&i.tx_id!=='BONUS'?`<div style="font-size:10px;color:#aaa;">TxID: ${i.tx_id}</div>`:''}</div><div style="text-align:right;"><div style="font-weight:bold;">₹${i.amount.toFixed(2)}</div><div class="status-${i.status}">${i.status.toUpperCase()}</div>${i.utr?`<div style="font-size:10px;color:#aaa;">${i.utr}</div>`:''}</div></div>`).join('');}).catch(err=>console.error('History error:',err));}
        
        function loadReferInfo(){fetch('/api/get_refer_info?user_id='+UID).then(r=>r.json()).then(data=>{if(data.ok){referData=data;document.getElementById('refer-code-display').textContent=data.refer_code;const referralsList=document.getElementById('referrals-list');if(data.referred_users&&data.referred_users.length){referralsList.innerHTML=data.referred_users.map(u=>`<div style="background:rgba(157,78,221,0.1); padding:10px; border-radius:8px; margin-bottom:5px;"><div style="font-weight:bold;">${u.name}</div><div style="font-size:10px; color:#888;">ID: ${u.id}</div><div style="font-size:11px; margin-top:5px; font-weight:bold; color:${u.status.includes('VERIFIED')?'#0f0':'orange'}">${u.status}</div></div>`).join('');}else{referralsList.innerHTML='<div style="text-align:center; color:#666; padding:20px;">No referrals yet</div>';}}else{document.getElementById('refer-code-display').textContent='ERROR';}}).catch(err=>{document.getElementById('refer-code-display').textContent='ERROR';console.error('Refer info error:',err);});}
        
        function copyReferCode(){if(!referData)return;navigator.clipboard.writeText(referData.refer_link).then(()=>alert('Refer link copied!')).catch(()=>alert('Failed to copy'));}
        
        function shareReferLink(){if(!referData)return;const text=`🎉 Join {{ settings.bot_name }} and earn money!\\nUse my refer code: ${referData.refer_code}\\n${referData.refer_link}`;window.open(`https://t.me/share/url?url=${encodeURIComponent(referData.refer_link)}&text=${encodeURIComponent(text)}`,'_blank');}
        
        function claimGift(){const code=document.getElementById('gift-code').value.trim().toUpperCase();if(!code||code.length!==5){alert('Enter 5-character code');return;}const l=document.getElementById('loader');l.style.display='flex';document.getElementById('loader-txt').innerText='CLAIMING...';fetch('/api/claim_gift',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:UID,code:code})}).then(r=>r.json()).then(data=>{setTimeout(()=>{l.style.display='none';const resultDiv=document.getElementById('gift-result');if(data.ok){resultDiv.innerHTML=`<div style="color:#0f0; font-weight:bold; font-size:18px;">${data.msg}</div>`;document.getElementById('gift-code').value='';confetti({particleCount:300,spread:100});refreshApp();}else{resultDiv.innerHTML=`<div style="color:#f44; font-weight:bold;">${data.msg}</div>`;}},1000);}).catch(err=>{l.style.display='none';alert('Failed to claim');console.error('Claim error:',err);});}
        
        function loadLeaderboard(){fetch('/api/leaderboard').then(r=>r.json()).then(data=>{const container=document.getElementById('leaderboard-list');if(!data.data||!data.data.length){container.innerHTML='<tr><td colspan="4" style="text-align:center; padding:20px; color:#666;">No data</td></tr>';return;}container.innerHTML=data.data.map((user,index)=>`<tr ${user.user_id==UID?'class="highlight"':''}><td style="font-weight:bold; color:#ccc;">${index+1}</td><td><div style="font-weight:bold;">${(user.name||'').substring(0,15)}${(user.name||'').length>15?'...':''}</div><div style="font-size:10px; color:#888;">${(user.user_id||'').substring(0,8)}...</div></td><td style="text-align:right; font-weight:bold; color:var(--gold);">₹${(user.balance||0).toFixed(2)}</td><td style="text-align:right; font-size:12px; color:#aaa;">${user.total_refers||0}</td></tr>`).join('');}).catch(err=>console.error('Leaderboard error:',err));}
        
        function openPop(id){document.getElementById('pop-'+id).style.display='flex'}
        function closePop(){document.querySelectorAll('.popup').forEach(e=>e.style.display='none')}
    </script>
</body>
</html>
"""

ADMIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Admin Panel</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { background: #111; color: #ddd; font-family: sans-serif; margin: 0; padding-bottom: 50px; }
        .nav { background: #222; padding: 10px; display: flex; overflow-x: auto; gap: 10px; position: sticky; top: 0; z-index: 100; border-bottom: 1px solid #333; }
        .nav button { background: none; border: none; color: #888; padding: 10px; font-weight: bold; cursor: pointer; white-space: nowrap; border-radius: 5px; }
        .nav button.active { background: #007bff; color: white; }
        .tab { display: none; padding: 15px; } .tab.active { display: block; }
        .card { background: #222; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #333; }
        input, select, textarea { width: 100%; padding: 10px; background: #333; border: 1px solid #444; color: white; margin: 5px 0; border-radius: 5px; box-sizing: border-box; }
        .btn { width: 100%; padding: 12px; background: #007bff; color: white; border: none; border-radius: 5px; margin-top: 10px; font-weight: bold; cursor: pointer;}
        .btn-del { width: auto; background: #dc3545; padding: 5px 10px; margin: 0; font-size: 12px; cursor: pointer;}
        .btn-icon { width:35px; height:35px; border-radius:5px; border:none; cursor:pointer; font-weight:bold; font-size:16px; margin-left:5px; display:inline-flex; align-items:center; justify-content:center; }
        .check { background:#28a745; color:white; } .cross { background:#dc3545; color:white; }
        table { width: 100%; border-collapse: collapse; font-size: 13px; } 
        th { text-align: left; color: #888; border-bottom: 1px solid #444; padding:8px; } 
        td { padding: 8px; border-bottom: 1px solid #333; vertical-align: middle; }
        .tx-id { font-weight:bold; color:#007bff; display:block; }
        .u-info { font-size:11px; color:#aaa; display:block; }
        .paid-utr { font-family:monospace; color:#28a745; background:rgba(40,167,69,0.1); padding:2px 5px; border-radius:4px; font-size:11px; }
        .modal { display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.9); justify-content:center; align-items:center; z-index:999; }
        .m-content { background:#222; padding:20px; border-radius:10px; border:1px solid #444; width:90%; max-width:300px; text-align:center; }
        .gift-row { background: rgba(157,78,221,0.1); margin: 5px 0; padding: 10px; border-radius: 5px; display: flex; justify-content: space-between; align-items: center; }
        .gift-code { font-family: monospace; font-weight: bold; color: #9d4edd; }
        .expiry { font-size: 11px; color: #ff9800; }
        .usage { font-size: 12px; color: #aaa; }
        .nowrap { white-space: nowrap; }
        .expired { opacity: 0.5; text-decoration: line-through; }
        .gen-btn { background: #9d4edd; color: white; border: none; padding: 8px 15px; border-radius: 5px; cursor: pointer; font-size: 12px; margin-left: 10px; }
    </style>
</head>
<body>
    <div class="nav">
        <button class="active" onclick="tab('dash')">Stats</button>
        <button onclick="tab('withs')">Withdraws</button>
        <button onclick="tab('users')">Users</button>
        <button onclick="tab('sets')">Config</button>
        <button onclick="tab('chans')">Channels</button>
        <button onclick="tab('admins')">Admins</button>
        <button onclick="tab('gifts')">Gift Codes</button>
        <button onclick="tab('bc')">Broadcast</button>
    </div>
    
    <div id="approveModal" class="modal"><div class="m-content"><h3>Enter UTR</h3><input id="utrInput" placeholder="UTR Number"><button class="btn" style="background:#28a745" onclick="confirmApprove()">Confirm Pay</button><button class="btn" style="background:transparent; color:#f44" onclick="document.getElementById('approveModal').style.display='none'">Cancel</button></div></div>
    
    <div id="dash" class="tab active"><div class="card"><h3>Total Users: <span style="color:#007bff">{{ stats.total_users }}</span></h3><h3>Pending Withdrawals: <span style="color:#ffc107">{{ stats.pending_count }}</span></h3><h3>Active Gift Codes: <span style="color:#9d4edd">{{ gifts|length }}</span></h3></div></div>
    
    <div id="withs" class="tab">
        <div class="card" style="padding:0; overflow:hidden;">
            <table style="width:100%;">
                <tr style="background:#2a2a30;"><th>Request Info</th><th style="text-align:right;">Action</th></tr>
                {% for w in withdrawals %}
                <tr>
                    <td>
                        <span class="tx-id">{{ w.tx_id }}</span>
                        <span class="u-info">ID: {{ w.user_id }}</span>
                        <div style="color:#ffc107; font-weight:bold; margin-top:2px;">₹{{ w.amount }}</div>
                        <div style="font-size:10px; color:#888;">{{ w.upi }}</div>
                    </td>
                    <td style="text-align:right;">
                        {% if w.status == 'pending' %}
                        <button class="btn-icon check" onclick="openApprove('{{ w.tx_id }}')">✔</button>
                        <button class="btn-icon cross" onclick="proc('{{ w.tx_id }}','rejected')">✘</button>
                        {% elif w.status == 'completed' %}
                        <span class="paid-utr">{{ w.utr }}</span>
                        {% else %}
                        <span style="color:#dc3545; font-size:11px;">REJECTED</span>
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </table>
        </div>
    </div>

    <div id="users" class="tab">
        <div class="card"><input placeholder="Search" onkeyup="search(this)">
            <table id="uTable"><tr><th>ID</th><th>Name</th><th>Bal</th><th>Refers</th><th>Code</th></tr>
                {% for uid, u in users.items() %}
                <tr><td class="nowrap">{{ uid[:8] }}...</td><td>{{ u.name }}</td><td>{{ "%.2f"|format(u.balance) }}</td><td>{{ u.referred_users|length if u.referred_users else 0 }}</td><td style="font-family:monospace; font-size:11px;">{{ u.refer_code if u.refer_code else 'N/A' }}</td></tr>
                {% endfor %}
            </table>
        </div>
    </div>
    
    <div id="sets" class="tab">
        <div class="card">
            <label>Bot Name</label><input id="bName" value="{{ settings.bot_name }}">
            <label>Min Withdraw</label><input type="number" id="minW" value="{{ settings.min_withdrawal }}">
            <label>Welcome Bonus</label><input type="number" id="bonus" value="{{ settings.welcome_bonus }}">
            <label>Min Refer Reward</label><input type="number" id="minRef" value="{{ settings.min_refer_reward }}">
            <label>Max Refer Reward</label><input type="number" id="maxRef" value="{{ settings.max_refer_reward }}">
            <div style="margin:10px 0"><input type="checkbox" id="dis" style="width:auto" {{ 'checked' if settings.bots_disabled else '' }}> Disable Bots</div>
            <div style="margin:10px 0"><input type="checkbox" id="auto" style="width:auto" {{ 'checked' if settings.auto_withdraw else '' }}> Auto-Withdraw</div>
            <div style="margin:10px 0"><input type="checkbox" id="idevice" style="width:auto" {{ 'checked' if settings.ignore_device_check else '' }}> Disable Strict Device Check</div>
            <div style="margin:10px 0"><input type="checkbox" id="withdraw_disabled" style="width:auto" {{ 'checked' if settings.withdraw_disabled else '' }}> Disable Withdrawals</div>
            <button class="btn" onclick="saveBasic()">Save Settings</button>
        </div>
        <div class="card"><h3>Logo</h3><input type="file" id="logoFile"><button class="btn" onclick="upLogo()">Upload Logo</button></div>
    </div>
    
    <div id="chans" class="tab">
        <div class="card"><input id="cName" placeholder="Channel Name"><input id="cLink" placeholder="Channel Link"><input id="cId" placeholder="Channel ID"><button class="btn" onclick="addChan()">Add Channel</button></div>
        <div class="card"><table>{% for ch in settings.channels %}<tr><td>{{ ch.btn_name }}</td><td><button class="btn-del" onclick="delChan({{ loop.index0 }})">X</button></td></tr>{% endfor %}</table></div>
    </div>
    
    <div id="admins" class="tab">
        <div class="card"><h3>Manage Admins</h3><input id="newAdmin" placeholder="Telegram ID"><button class="btn" onclick="addAdmin()">Add Admin</button></div>
        <div class="card"><table>{% for adm in settings.admins %}<tr><td>{{ adm }}</td><td><button class="btn-del" onclick="remAdmin('{{ adm }}')">X</button></td></tr>{% endfor %}</table></div>
    </div>
    
    <div id="gifts" class="tab">
        <div class="card">
            <h3>Create Gift Code</h3>
            <div style="display:flex; align-items:center; margin:10px 0;">
                <input id="giftCode" placeholder="Enter 5-character code" maxlength="5" style="text-transform:uppercase; flex:1;">
                <button class="gen-btn" onclick="generateCode()">GENERATE</button>
            </div>
            <label>Min Amount</label><input type="number" id="giftMin" value="10" step="0.01">
            <label>Max Amount</label><input type="number" id="giftMax" value="50" step="0.01">
            <label>Expiry (Hours)</label><input type="number" id="giftExpiry" value="2">
            <label>Total Uses</label><input type="number" id="giftUses" value="1">
            <button class="btn" onclick="createGift()" style="background:#9d4edd;">Create Gift Code</button>
        </div>
        
        <div class="card">
            <h3>Active Gift Codes</h3>
            {% for gift in gifts %}
            <div class="gift-row {% if gift.expired %}expired{% endif %}">
                <div>
                    <div class="gift-code">{{ gift.code }}</div>
                    <div class="expiry">
                        {% if gift.expired %}
                        EXPIRED
                        {% else %}
                        {% set expiry_time = gift.expiry|string %}
                        {% set remaining = (expiry_time|fromisoformat - now).total_seconds() / 60 %}
                        Expires in: {{ remaining|int }} mins
                        {% endif %}
                    </div>
                </div>
                <div style="text-align:center;">
                    <div class="usage">{{ gift.used_by|length }}/{{ gift.total_uses }} uses</div>
                    <div style="font-size:11px; color:#0f0;">₹{{ gift.min_amount }} - ₹{{ gift.max_amount }}</div>
                </div>
                <div>
                    <button class="btn-icon" style="background:#ff9800;" onclick="toggleGift('{{ gift.code }}')">
                        {% if gift.is_active %}⏸{% else %}▶{% endif %}
                    </button>
                    <button class="btn-icon cross" onclick="deleteGift('{{ gift.code }}')">✘</button>
                </div>
            </div>
            {% endfor %}
        </div>
    </div>
    
    <div id="bc" class="tab">
        <div class="card"><textarea id="bcMsg" placeholder="Message" rows="5"></textarea><input type="file" id="bcFile"><button class="btn" onclick="sendBC()">Broadcast Message</button></div>
    </div>
    
    <script>
        let curTx='';
        function tab(n){document.querySelectorAll('.tab').forEach(e=>e.classList.remove('active'));document.getElementById(n).classList.add('active');document.querySelectorAll('.nav button').forEach(e=>e.classList.remove('active'));event.target.classList.add('active');}
        function saveBasic(){fetch('/admin/update_basic',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({bot_name:document.getElementById('bName').value,min_withdrawal:document.getElementById('minW').value,welcome_bonus:document.getElementById('bonus').value,min_refer_reward:document.getElementById('minRef').value,max_refer_reward:document.getElementById('maxRef').value,bots_disabled:document.getElementById('dis').checked,auto_withdraw:document.getElementById('auto').checked,ignore_device_check:document.getElementById('idevice').checked,withdraw_disabled:document.getElementById('withdraw_disabled').checked})}).then(r=>r.json()).then(data=>{if(data.ok){alert("Saved!");}else{alert("Error");}}).catch(err=>alert("Error saving"));}
        function addChan(){fetch('/admin/channels',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'add',name:document.getElementById('cName').value,link:document.getElementById('cLink').value,id:document.getElementById('cId').value})}).then(r=>r.json()).then(data=>{if(data.ok){location.reload();}else{alert("Error");}}).catch(err=>alert("Error adding"));}
        function delChan(i){fetch('/admin/channels',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'delete',index:i})}).then(r=>r.json()).then(data=>{if(data.ok){location.reload();}else{alert("Error");}}).catch(err=>alert("Error deleting"));}
        function addAdmin(){const adminId=document.getElementById('newAdmin').value.trim();if(!adminId){alert("Enter ID");return;}fetch('/admin/manage_admins',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'add',id:adminId})}).then(r=>r.json()).then(data=>{if(data.ok){location.reload();}else{alert("Error");}}).catch(err=>alert("Error adding"));}
        function remAdmin(id){if(!confirm('Remove admin?'))return;fetch('/admin/manage_admins',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'remove',id:id})}).then(r=>r.json()).then(data=>{if(data.ok){location.reload();}else{alert("Error");}}).catch(err=>alert("Error removing"));}
        function openApprove(id){curTx=id;document.getElementById('approveModal').style.display='flex'}
        function confirmApprove(){const u=document.getElementById('utrInput').value;if(!u)return alert("Enter UTR");proc(curTx,'completed',u)}
        function proc(i,s,u=''){fetch('/admin/process_withdraw',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tx_id:i,status:s,utr:u})}).then(r=>r.json()).then(data=>{if(data.ok){location.reload();}else{alert("Error");}}).catch(err=>alert("Error processing"));}
        function sendBC(){const fd=new FormData();fd.append('text',document.getElementById('bcMsg').value);fd.append('image',document.getElementById('bcFile').files[0]);fetch('/admin/broadcast',{method:'POST',body:fd}).then(r=>r.json()).then(data=>{alert("Sent to "+data.count+" users");}).catch(err=>alert("Error broadcasting"));}
        function upLogo(){const fd=new FormData();fd.append('logo',document.getElementById('logoFile').files[0]);fetch('/admin/upload_logo',{method:'POST',body:fd}).then(r=>r.json()).then(data=>{if(data.ok){alert("Logo uploaded!");}else{alert("Error");}}).catch(err=>alert("Error uploading"));}
        function search(e){const v=e.value.toLowerCase();document.querySelectorAll('#uTable tr').forEach((r,i)=>{if(i>0)r.style.display=r.innerText.toLowerCase().includes(v)?'':'none';});}
        function generateCode(){const chars='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';let code='';for(let i=0;i<5;i++){code+=chars.charAt(Math.floor(Math.random()*chars.length));}document.getElementById('giftCode').value=code;}
        function createGift(){const code=document.getElementById('giftCode').value.toUpperCase();const minAmt=document.getElementById('giftMin').value;const maxAmt=document.getElementById('giftMax').value;const expiry=document.getElementById('giftExpiry').value;const uses=document.getElementById('giftUses').value;if(!code||code.length!==5){alert('Enter 5-character code');return;}if(parseFloat(minAmt)>=parseFloat(maxAmt)){alert('Max must be > min');return;}fetch('/admin/create_gift?user_id={{ admin_id }}',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({auto_generate:false,code:code,min_amount:minAmt,max_amount:maxAmt,expiry_hours:expiry,total_uses:uses})}).then(r=>r.json()).then(data=>{if(data.ok){alert('Gift code created: '+data.code);location.reload();}else{alert('Error: '+data.msg);}}).catch(err=>alert('Error creating'));}
        function toggleGift(code){fetch('/admin/toggle_gift',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:code,action:'toggle'})}).then(r=>r.json()).then(data=>{if(data.ok){location.reload();}else{alert('Error');}}).catch(err=>alert('Error toggling'));}
        function deleteGift(code){if(!confirm('Delete gift code?'))return;fetch('/admin/toggle_gift',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:code,action:'delete'})}).then(r=>r.json()).then(data=>{if(data.ok){location.reload();}else{alert('Error');}}).catch(err=>alert('Error deleting'));}
        generateCode();
    </script>
</body>
</html>
"""
# ==================== 9. START APP ====================
if __name__ == '__main__':
    # Initialize default files
    init_default_files()
    
    # Railway provides PORT environment variable
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
