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
import urllib.parse
import hashlib
import threading

# ==================== 1. RAILWAY CONFIGURATION ====================
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8559128386:AAHYe9utD824SQh5UD1vQ1H8M9WNPGw_m_w')
ADMIN_ID = os.environ.get('ADMIN_ID', '8435248854')
BASE_URL = os.environ.get('BASE_URL', 'web-production-7f83a.up.railway.app')
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

# Global cache with lock for thread safety
cache_lock = threading.Lock()
CACHE = {
    'settings': None,
    'users': None,
    'withdrawals': None,
    'gifts': None,
    'leaderboard': None,
    'last_update': 0
}

# Logging
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
            "max_refer_reward": 50.0,
            "app_name": "Cyber Earn",
            "disable_channel_verification": False,
            "auto_accept_private": False,
            "hide_verify_button": False
        },
        WITHDRAWALS_FILE: [],
        GIFTS_FILE: [],
        LEADERBOARD_FILE: {"last_updated": "2000-01-01", "data": []}
    }
    
    for filepath, default_data in default_files.items():
        if not os.path.exists(filepath):
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(default_data, f, indent=4, ensure_ascii=False)
            logger.info(f"Created default file: {filepath}")

init_default_files()

# ==================== 2. DATA MANAGEMENT (CACHED) ====================
def load_json_cached(filepath, default, cache_key=None):
    try:
        with cache_lock:
            # Use cache if available and recent (5 seconds)
            if cache_key and CACHE[cache_key] and (time.time() - CACHE['last_update'] < 5):
                return CACHE[cache_key].copy()  # Return copy to avoid mutation issues
            
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if cache_key:
                        CACHE[cache_key] = data
                        CACHE['last_update'] = time.time()
                    return data
            return default
    except Exception as e:
        logger.error(f"Error loading {filepath}: {e}")
        return default

def save_json(filepath, data):
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        
        # Invalidate cache
        with cache_lock:
            if 'settings' in filepath:
                CACHE['settings'] = None
            elif 'users' in filepath:
                CACHE['users'] = None
            elif 'withdrawals' in filepath:
                CACHE['withdrawals'] = None
            elif 'gifts' in filepath:
                CACHE['gifts'] = None
            CACHE['last_update'] = time.time()
        
        return True
    except Exception as e:
        logger.error(f"Error saving {filepath}: {e}")
        return False

def get_settings():
    with cache_lock:
        if CACHE['settings'] and (time.time() - CACHE['last_update'] < 5):
            return CACHE['settings'].copy()
    
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
        "max_refer_reward": 50.0,
        "app_name": "Cyber Earn",
        "disable_channel_verification": False,
        "auto_accept_private": False,
        "hide_verify_button": False
    }
    current = load_json_cached(SETTINGS_FILE, defaults, 'settings')
    for k, v in defaults.items():
        if k not in current:
            current[k] = v
    with cache_lock:
        CACHE['settings'] = current
    return current.copy()

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
        # Remove special characters and emojis for display
        clean_name = re.sub(r'[^\w\s]', '', user.first_name)
        if clean_name.strip():
            name_parts.append(clean_name)
    if user.last_name:
        clean_last = re.sub(r'[^\w\s]', '', user.last_name)
        if clean_last.strip():
            name_parts.append(clean_last)
    return " ".join(name_parts) if name_parts else "User"

def get_user_display_name(user):
    """Get user's username or cleaned name"""
    if user.username:
        return f"@{user.username}"
    return get_user_full_name(user)

def generate_code(length=5):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def generate_refer_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=7))

def generate_device_fingerprint(ip, user_agent, other_data=""):
    """Generate a unique device fingerprint"""
    data = f"{ip}|{user_agent}|{other_data}"
    return hashlib.md5(data.encode()).hexdigest()

def update_leaderboard():
    try:
        users = load_json_cached(USERS_FILE, {}, 'users')
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
        with cache_lock:
            CACHE['leaderboard'] = data
        return data
    except Exception as e:
        logger.error(f"Error updating leaderboard: {e}")
        return {"last_updated": datetime.now().isoformat(), "data": []}

def check_gift_code_expiry():
    gifts = load_json_cached(GIFTS_FILE, [], 'gifts')
    updated = False
    current_time = datetime.now()
    
    for gift in gifts[:]:
        # Check expiry time
        if "expiry" in gift:
            try:
                expiry_time = datetime.fromisoformat(gift["expiry"])
                if expiry_time < current_time:
                    gift["expired"] = True
                    updated = True
            except:
                pass
        
        # Check if usage limit reached
        if not gift.get('expired') and 'used_by' in gift and 'total_uses' in gift:
            if len(gift['used_by']) >= gift['total_uses']:
                gift["expired"] = True
                updated = True
    
    if updated:
        save_json(GIFTS_FILE, gifts)
    return gifts

def get_user_status(user_data, settings):
    """Determine user status based on verification requirements"""
    if user_data.get('verified', False):
        # User is verified if they meet current requirements
        needs_device = not settings.get('ignore_device_check', False)
        device_ok = user_data.get('device_verified', False) or not needs_device
        
        # Check channels if not disabled
        channels_ok = True
        if settings['channels'] and not settings.get('disable_channel_verification', False):
            # Check if user has passed channel verification
            last_check = user_data.get('last_channel_check')
            if last_check:
                try:
                    last_check_time = datetime.fromisoformat(last_check)
                    # Consider channel check valid for 5 minutes
                    if (datetime.now() - last_check_time).total_seconds() > 300:
                        channels_ok = False
                except:
                    channels_ok = False
            else:
                channels_ok = False
        
        return "verified" if device_ok and channels_ok else "pending"
    else:
        return "pending"

# Custom Jinja2 filter
def datetime_from_isoformat(value):
    try:
        return datetime.fromisoformat(value)
    except:
        return datetime.now()

app.jinja_env.filters['fromisoformat'] = datetime_from_isoformat

# ==================== 4. PRIVATE CHANNEL HANDLER ====================
def handle_private_channel(channel_id, user_id, channel_name):
    """Handle private channel join requests"""
    try:
        # Check if user is already a member
        member = bot.get_chat_member(channel_id, user_id)
        if member.status in ['member', 'administrator', 'creator', 'restricted']:
            return True, "Already a member"
        
        # Check if bot is admin in the channel
        bot_member = bot.get_chat_member(channel_id, bot.get_me().id)
        if bot_member.status not in ['administrator', 'creator']:
            return False, f"Bot is not admin in {channel_name}"
        
        # Try to approve join request if exists
        try:
            bot.approve_chat_join_request(channel_id, user_id)
            return True, f"Join request approved for {channel_name}"
        except Exception as e:
            if "CHAT_JOIN_REQUEST_NOT_FOUND" in str(e):
                # Send join request
                try:
                    chat_invite_link = bot.create_chat_invite_link(channel_id, creates_join_request=True)
                    return False, f"Join request sent to {channel_name}. Please wait for admin approval."
                except Exception as e2:
                    return False, f"Could not send join request to {channel_name}"
            return False, f"Error approving join request for {channel_name}"
    except Exception as e:
        logger.error(f"Private channel error: {e}")
        return False, f"Error checking {channel_name}"

# ==================== 5. BOT HANDLERS ====================
@bot.chat_join_request_handler()
def auto_approve(message):
    """Auto approve join requests for channels where bot is admin"""
    try:
        settings = get_settings()
        if settings.get('auto_accept_private', False):
            bot.approve_chat_join_request(message.chat.id, message.from_user.id)
            logger.info(f"Auto-approved join request for user {message.from_user.id} in channel {message.chat.id}")
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
        
        users = load_json_cached(USERS_FILE, {}, 'users')
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
                "username": message.from_user.username,
                "joined_date": datetime.now().isoformat(),
                "ip": None,
                "device_id": None,
                "device_verified": False,
                "refer_code": user_refer_code,
                "referred_by": refer_code if refer_code else None,
                "referred_users": [],
                "claimed_gifts": [],
                "last_channel_check": None
            }
            save_json(USERS_FILE, users)
            
            msg = f"🔔 *New User*\nName: {full_name}\nID: `{uid}`"
            if message.from_user.username:
                msg += f"\nUsername: @{message.from_user.username}"
            if refer_code:
                msg += f"\nReferred by: `{refer_code}`"
            safe_send_message(ADMIN_ID, msg)
            for adm in settings.get('admins', []):
                safe_send_message(adm, msg)
        
        display_name = get_user_display_name(message.from_user)
        # Remove special characters for URL encoding
        clean_display_name = re.sub(r'[^\w\s]', '', display_name)
        if not clean_display_name.strip():
            clean_display_name = settings.get('app_name', 'USER')
        
        clean_display_name = urllib.parse.quote(clean_display_name)
        img_url = f"https://res.cloudinary.com/dneusgyzc/image/upload/v1767971399/IMG_20260109_203909_698_wr66ik.jpg"
        
        markup = InlineKeyboardMarkup(row_width=1)
        
        # Always show channels on start regardless of verification settings
        for ch in settings['channels']:
            markup.add(InlineKeyboardButton(ch.get('btn_name', 'Channel'), url=ch.get('link', '#')))
        
        # Only show verify button if not hidden in settings
        if not settings.get('hide_verify_button', False):
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

# ==================== 6. WEBAPP ROUTES ====================
@app.route('/')
def home():
    return "Telegram Bot is running! Use /start in Telegram."

@app.route('/mini_app')
def mini_app():
    try:
        uid = request.args.get('user_id')
        if not uid:
            return "User ID required", 400
            
        settings = get_settings()
        
        # Fast loading - load data directly
        users = load_json_cached(USERS_FILE, {}, 'users')
        leaderboard_data = load_json_cached(LEADERBOARD_FILE, {"last_updated": "2000-01-01", "data": []}, 'leaderboard')
        
        user = users.get(str(uid), {"name": "Guest", "balance": 0.0, "verified": False, "device_verified": False})
        
        # Determine user status
        user_status = get_user_status(user, settings)
        
        # Auto verify if channel verification is disabled
        if settings.get('disable_channel_verification', False) and not user.get('verified', False):
            user['verified'] = True
            user['last_channel_check'] = datetime.now().isoformat()
            
            # Give welcome bonus if this is first verification
            try: 
                bonus = float(settings.get('welcome_bonus', 50))
            except: 
                bonus = 50.0
            
            user['balance'] = float(user.get('balance', 0)) + bonus
            user_status = "verified"
            
            # Save updated user data
            save_json(USERS_FILE, users)
            
            # Add bonus transaction
            w_list = load_json_cached(WITHDRAWALS_FILE, [], 'withdrawals')
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
        
        return render_template_string(MINI_APP_TEMPLATE, 
            user=user, 
            user_id=uid, 
            settings=settings, 
            base_url=BASE_URL, 
            timestamp=int(time.time()),
            leaderboard=leaderboard_data.get("data", []),
            now=datetime.now().isoformat(),
            user_status=user_status
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
            return Response(requests.get(dl_url, timeout=3).content, mimetype='image/jpeg')
    except Exception as e:
        logger.error(f"PFP error: {e}")
    return "No Image", 404

@app.route('/api/verify', methods=['POST'])
def api_verify():
    try:
        data = request.json
        uid = str(data.get('user_id', ''))
        fp = str(data.get('fp', ''))
        user_agent = request.headers.get('User-Agent', '')
        client_ip = request.remote_addr
        
        if not uid:
            return jsonify({'ok': False, 'msg': 'User ID required'})
        
        users = load_json_cached(USERS_FILE, {}, 'users')
        settings = get_settings()
        
        if uid not in users:
            return jsonify({'ok': False, 'msg': 'User not found'})
        
        # Generate proper device fingerprint
        device_fingerprint = generate_device_fingerprint(client_ip, user_agent, fp)
        
        verification_steps = []
        channel_errors = []
        
        # Step 1: Check device verification (if enabled)
        needs_device_check = not settings.get('ignore_device_check', False)
        
        if needs_device_check and fp and fp != 'skip':
            verification_steps.append({"step": "device", "status": "checking", "message": "Checking device..."})
            
            if not users[uid].get('device_verified'):
                # Check for same device across different accounts
                device_error = None
                for u_id, u_data in users.items():
                    if u_id == uid: 
                        continue
                    if u_data.get('device_verified') and str(u_data.get('device_id', '')) == device_fingerprint:
                        device_error = '⚠️ Device already used by another account! Please use a different device or clear browser data.'
                        break
                
                if device_error:
                    verification_steps.append({"step": "device", "status": "failed", "message": device_error})
                    return jsonify({
                        'ok': False, 
                        'msg': device_error, 
                        'type': 'device',
                        'steps': verification_steps,
                        'retry': True
                    })
                else:
                    users[uid]['device_id'] = device_fingerprint
                    users[uid]['device_verified'] = True
                    verification_steps.append({"step": "device", "status": "passed", "message": "Device verified ✓"})
            else:
                verification_steps.append({"step": "device", "status": "passed", "message": "Device already verified ✓"})
        elif not needs_device_check:
            verification_steps.append({"step": "device", "status": "passed", "message": "Device check disabled ✓"})
        
        # Step 2: Check all channels (only if channel verification is not disabled)
        verification_steps.append({"step": "channels", "status": "checking", "message": "Checking channel memberships..."})
        
        if settings['channels'] and not settings.get('disable_channel_verification', False):
            for idx, ch in enumerate(settings['channels']):
                channel_name = ch.get('btn_name', f'Channel {idx+1}')
                channel_disabled = ch.get('disabled', False)
                
                # Skip verification for disabled channels
                if channel_disabled:
                    verification_steps.append({"step": f"channel_{idx}", "status": "passed", "message": f"{channel_name} - Verification disabled ✓"})
                    continue
                
                try:
                    if ch.get('id'):
                        # Try to get member status
                        member = bot.get_chat_member(ch['id'], uid)
                        if member.status not in ['member', 'administrator', 'creator', 'restricted']:
                            channel_errors.append(channel_name)
                except:
                    channel_errors.append(channel_name)
        
        # Return specific errors
        if channel_errors:
            verification_steps.append({"step": "channels", "status": "failed", "message": f"Please join: {', '.join(channel_errors)}"})
            return jsonify({
                'ok': False, 
                'msg': f"Please join: {', '.join(channel_errors)}", 
                'type': 'channels',
                'steps': verification_steps,
                'retry': True
            })
        
        verification_steps.append({"step": "channels", "status": "passed", "message": "All channels verified ✓"})
        
        # All checks passed
        users[uid]['last_channel_check'] = datetime.now().isoformat()
        
        # Determine if this is first time verification
        is_first_verification = not users[uid].get('verified', False)
        
        if is_first_verification:
            try: 
                bonus = float(settings.get('welcome_bonus', 50))
            except: 
                bonus = 50.0
            
            users[uid].update({
                'verified': True,
                'ip': client_ip,
                'balance': float(users[uid].get('balance', 0)) + bonus
            })
            
            # Give referral bonus to referrer ONLY when referred user verifies
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
                            
                            w_list = load_json_cached(WITHDRAWALS_FILE, [], 'withdrawals')
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
            
            w_list = load_json_cached(WITHDRAWALS_FILE, [], 'withdrawals')
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
            
            verification_steps.append({"step": "bonus", "status": "passed", "message": f"₹{bonus} bonus added ✓"})
        else:
            verification_steps.append({"step": "bonus", "status": "passed", "message": "Already verified ✓"})
        
        save_json(USERS_FILE, users)
        
        return jsonify({
            'ok': True, 
            'bonus': bonus if is_first_verification else 0, 
            'balance': users[uid]['balance'], 
            'verified': True,
            'device_verified': users[uid].get('device_verified', False),
            'steps': verification_steps
        })
    
    except Exception as e:
        logger.error(f"Verify error: {e}")
        return jsonify({'ok': False, 'msg': f"Error: {str(e)}", 'retry': True})

@app.route('/api/check_verification')
def api_check_verification():
    try:
        uid = request.args.get('user_id')
        if not uid:
            return jsonify({'ok': False, 'msg': 'User ID required'})
        
        users = load_json_cached(USERS_FILE, {}, 'users')
        if uid not in users:
            return jsonify({'ok': False, 'msg': 'User not found'})
        
        user = users[uid]
        settings = get_settings()
        status = get_user_status(user, settings)
        
        return jsonify({
            'ok': True,
            'verified': user.get('verified', False),
            'device_verified': user.get('device_verified', False),
            'balance': float(user.get('balance', 0)),
            'name': user.get('name', 'User'),
            'status': status
        })
    except Exception as e:
        logger.error(f"Check verification error: {e}")
        return jsonify({'ok': False, 'msg': str(e)})

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
        
        users = load_json_cached(USERS_FILE, {}, 'users')
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

        w_list = load_json_cached(WITHDRAWALS_FILE, [], 'withdrawals')
        w_list.append(record)
        save_json(WITHDRAWALS_FILE, w_list)
        
        return jsonify({
            'ok': True, 
            'msg': msg_client, 
            'auto': is_auto, 
            'utr': record.get('utr', ''), 
            'tx_id': tx_id,
            'new_balance': users[uid]['balance']
        })
        
    except Exception as e:
        logger.error(f"Withdraw Error: {e}")
        return jsonify({'ok': False, 'msg': f"Error: {str(e)}"})

@app.route('/api/get_balance')
def api_get_balance():
    try:
        uid = request.args.get('user_id')
        if not uid:
            return jsonify({'ok': False, 'msg': 'User ID required'})
        
        users = load_json_cached(USERS_FILE, {}, 'users')
        user = users.get(str(uid), {})
        
        return jsonify({
            'ok': True,
            'balance': float(user.get('balance', 0)),
            'verified': user.get('verified', False)
        })
    except Exception as e:
        logger.error(f"Get balance error: {e}")
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/api/history')
def api_history():
    try:
        uid = request.args.get('user_id')
        if not uid:
            return jsonify([])
        
        history = [w for w in load_json_cached(WITHDRAWALS_FILE, [], 'withdrawals') if w.get('user_id') == uid]
        return jsonify(history[::-1][:10])
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
            
        cap = f"📩 *Message from {uid}*\n{msg}"
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
        
        users = load_json_cached(USERS_FILE, {}, 'users')
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
                
                w_list = load_json_cached(WITHDRAWALS_FILE, [], 'withdrawals')
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
                    'amount': amount,
                    'new_balance': users[uid]['balance']
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
        
        users = load_json_cached(USERS_FILE, {}, 'users')
        settings = get_settings()
        
        if uid not in users:
            return jsonify({'ok': False, 'msg': 'User not found'})
        
        user = users[uid]
        
        if not user.get('refer_code'):
            user['refer_code'] = generate_refer_code()
            save_json(USERS_FILE, users)
        
        refer_code = user.get('refer_code', '')
        
        try:
            bot_username = bot.get_me().username
        except:
            bot_username = "telegram_bot"
        
        referred_users = user.get('referred_users', [])
        referred_details = []
        total_pending = 0
        total_verified = 0
        
        for ref_uid in referred_users[:20]:
            if ref_uid in users:
                ref_user = users[ref_uid]
                ref_status = get_user_status(ref_user, settings)
                is_verified = ref_status == "verified"
                status = "✅ VERIFIED" if is_verified else "⏳ PENDING"
                
                if is_verified:
                    total_verified += 1
                else:
                    total_pending += 1
                    
                referred_details.append({
                    'id': ref_uid,
                    'name': ref_user.get('name', 'Unknown'),
                    'username': ref_user.get('username', ''),
                    'status': status,
                    'verified': is_verified,
                    'status_type': ref_status
                })
        
        return jsonify({
            'ok': True,
            'refer_code': refer_code,
            'refer_link': f'https://t.me/{bot_username}?start={refer_code}',
            'referred_users': referred_details,
            'total_refers': len(referred_users),
            'verified_refers': total_verified,
            'pending_refers': total_pending
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

# ==================== 7. ADMIN PANEL ====================
@app.route('/admin_panel')
def admin_panel():
    try:
        uid = request.args.get('user_id')
        if not uid or not is_admin(uid): 
            return "⛔ Unauthorized"
        
        all_withdrawals = load_json_cached(WITHDRAWALS_FILE, [], 'withdrawals')
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
        
        users = load_json_cached(USERS_FILE, {}, 'users')
        settings = get_settings()
        
        user_list = []
        for user_id, user_data in users.items():
            status = get_user_status(user_data, settings)
            user_list.append({
                'id': user_id,
                'name': user_data.get('name', 'Unknown'),
                'username': user_data.get('username', ''),
                'balance': float(user_data.get('balance', 0)),
                'refer_code': user_data.get('refer_code', 'N/A'),
                'verified': user_data.get('verified', False),
                'device_verified': user_data.get('device_verified', False),
                'status': status,
                'refer_count': len(user_data.get('referred_users', [])),
                'joined_date': user_data.get('joined_date', '')
            })
        
        return render_template_string(ADMIN_TEMPLATE, 
            settings=get_settings(), 
            users=user_list,
            withdrawals=filtered_withdrawals[::-1], 
            stats={
                "total_users": len(users), 
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
            s['app_name'] = d.get('app_name', 'Cyber Earn')
        except:
            pass
        
        for k in ['bot_name','bots_disabled','auto_withdraw','ignore_device_check','withdraw_disabled','disable_channel_verification','auto_accept_private','hide_verify_button']:
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
                "id": d.get('id', ''),
                "disabled": False
            })
        elif action == 'delete':
            index = int(d.get('index', 0))
            if 0 <= index < len(s['channels']):
                del s['channels'][index]
        elif action == 'toggle':
            index = int(d.get('index', 0))
            if 0 <= index < len(s['channels']):
                s['channels'][index]['disabled'] = not s['channels'][index].get('disabled', False)
        
        save_json(SETTINGS_FILE, s)
        return jsonify({'ok': True})
    except Exception as e:
        logger.error(f"Channels error: {e}")
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/admin/process_withdraw', methods=['POST'])
def admin_process_withdraw():
    try:
        d = request.json
        w_list = load_json_cached(WITHDRAWALS_FILE, [], 'withdrawals')
        
        for w in w_list:
            if w.get('tx_id') == d.get('tx_id') and w.get('status') == 'pending':
                w['status'] = d.get('status', '')
                w['utr'] = d.get('utr', '')
                
                if d.get('status') == 'completed': 
                    safe_send_message(w['user_id'], f"✅ *Withdrawal Paid!*\nAmt: ₹{w['amount']}\nUTR: `{w['utr']}`\nTxID: `{w['tx_id']}`")
                else:
                    users = load_json_cached(USERS_FILE, {}, 'users')
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
        users = load_json_cached(USERS_FILE, {}, 'users')
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

@app.route('/admin/send_to_user', methods=['POST'])
def admin_send_to_user():
    try:
        user_id = request.form.get('user_id')
        txt = request.form.get('text', '')
        f = request.files.get('image')
        
        if not user_id:
            return jsonify({'ok': False, 'msg': 'User ID required'})
        
        if f:
            filename = secure_filename(f.filename)
            path = os.path.join(UPLOAD_FOLDER, filename)
            f.save(path)
            
            with open(path, 'rb') as img:
                idata = img.read()
                try: 
                    bot.send_photo(user_id, idata, caption=txt)
                    os.remove(path)
                    return jsonify({'ok': True, 'msg': 'Message sent successfully!'})
                except Exception as e:
                    os.remove(path)
                    return jsonify({'ok': False, 'msg': f'Error: {str(e)}'})
        else:
            try: 
                bot.send_message(user_id, txt)
                return jsonify({'ok': True, 'msg': 'Message sent successfully!'})
            except Exception as e:
                return jsonify({'ok': False, 'msg': f'Error: {str(e)}'})
    except Exception as e:
        logger.error(f"Send to user error: {e}")
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
        
        gifts = load_json_cached(GIFTS_FILE, [], 'gifts')
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
        
        gifts = load_json_cached(GIFTS_FILE, [], 'gifts')
        
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

# ==================== 8. SETUP ====================
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
    <link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;700&family=Poppins:wght@400;600;700&family=Orbitron:wght@400;700&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.6.0/dist/confetti.browser.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <style>
        :root { 
            --bg: #050508; 
            --cyan: #00f3ff; 
            --gold: #ffd700; 
            --panel: rgba(255,255,255,0.05); 
            --neon-pink: #ff00ff;
            --neon-blue: #00ccff;
            --neon-green: #00ffaa;
            --neon-purple: #9d4edd;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: radial-gradient(circle at top, #111122, var(--bg)); color: white; font-family: 'Poppins', sans-serif; margin: 0; padding: 0; min-height: 100vh; overflow-x: hidden; }
        .hidden { display: none !important; }
        .header { display: flex; align-items: center; justify-content: center; gap: 20px; margin: 20px 0; width: 100%; padding: 0 5%; animation: fadeInDown 0.8s ease-out; }
        @keyframes fadeInDown { from { opacity: 0; transform: translateY(-30px); } to { opacity: 1; transform: translateY(0); } }
        .logo { width: 70px; height: 70px; border-radius: 50%; border: 3px solid var(--cyan); box-shadow: 0 0 25px rgba(0,243,255,0.7), inset 0 0 15px rgba(0,243,255,0.3); object-fit: cover; animation: pulseLogo 3s infinite alternate; }
        @keyframes pulseLogo { 0% { box-shadow: 0 0 25px rgba(0,243,255,0.7), inset 0 0 15px rgba(0,243,255,0.3); } 100% { box-shadow: 0 0 40px rgba(0,243,255,0.9), inset 0 0 20px rgba(0,243,255,0.5); } }
        .title { font-size: 26px; font-weight: 800; text-shadow: 0 0 15px var(--cyan), 0 0 30px rgba(0,243,255,0.5); letter-spacing: 2px; font-family: 'Orbitron', monospace; background: linear-gradient(45deg, var(--cyan), var(--neon-blue)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; animation: textGlow 2s infinite alternate; }
        @keyframes textGlow { from { text-shadow: 0 0 15px var(--cyan), 0 0 30px rgba(0,243,255,0.5); } to { text-shadow: 0 0 20px var(--cyan), 0 0 40px rgba(0,243,255,0.7), 0 0 60px rgba(0,243,255,0.3); } }
        .nav-bar { display: flex; width: 100%; max-width: 550px; background: rgba(0,0,0,0.8); border-radius: 20px; margin: 15px auto; padding: 8px; justify-content: space-around; border: 1px solid rgba(255,255,255,0.1); backdrop-filter: blur(10px); animation: slideUp 0.6s ease-out; }
        @keyframes slideUp { from { opacity: 0; transform: translateY(30px); } to { opacity: 1; transform: translateY(0); } }
        .nav-btn { background: transparent; border: none; color: #aaa; padding: 12px 5px; border-radius: 15px; font-weight: bold; font-size: 14px; display: flex; flex-direction: column; align-items: center; gap: 5px; cursor: pointer; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); width: 25%; position: relative; overflow: hidden; }
        .nav-btn i { font-size: 24px; transition: all 0.3s; }
        .nav-text { font-size: 11px; margin-top: 3px; color: #888; transition: all 0.3s; font-family: 'Rajdhani', sans-serif; }
        .nav-btn::before { content: ''; position: absolute; top: 0; left: -100%; width: 100%; height: 100%; background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent); transition: left 0.7s; }
        .nav-btn:hover::before { left: 100%; }
        .nav-btn.active { background: linear-gradient(135deg, rgba(0,243,255,0.2), rgba(0,136,255,0.2)); color: var(--cyan); box-shadow: 0 0 20px rgba(0,243,255,0.5), inset 0 1px 0 rgba(255,255,255,0.2); border: 1px solid rgba(0,243,255,0.3); transform: translateY(-3px); }
        .nav-btn.active .nav-text { color: var(--cyan); text-shadow: 0 0 10px rgba(0,243,255,0.5); }
        .nav-btn.active i { transform: scale(1.2); filter: drop-shadow(0 0 8px rgba(0,243,255,0.7)); }
        .tab-content { width: 100%; max-width: 550px; padding: 0 5% 30px 5%; animation: fadeIn 0.5s ease-out; }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        .card-metal, .card-gold, .card-silver, .card-purple { width: 100%; border-radius: 20px; padding: 30px; margin-bottom: 25px; position: relative; overflow: hidden; animation: cardAppear 0.6s ease-out; }
        @keyframes cardAppear { from { opacity: 0; transform: scale(0.9); } to { opacity: 1; transform: scale(1); } }
        .card-metal { background: linear-gradient(135deg, #e0e0e0 0%, #bdc3c7 20%, #88929e 50%, #bdc3c7 80%, #e0e0e0 100%); border: 2px solid #fff; box-shadow: 0 15px 30px rgba(0,0,0,0.6), inset 0 0 20px rgba(255,255,255,0.7); display: flex; align-items: center; color: #222; animation: metalShine 4s infinite; }
        @keyframes metalShine { 0%, 100% { background: linear-gradient(135deg, #e0e0e0 0%, #bdc3c7 20%, #88929e 50%, #bdc3c7 80%, #e0e0e0 100%); } 50% { background: linear-gradient(135deg, #f0f0f0 0%, #d0d0d0 20%, #a0a0a0 50%, #d0d0d0 80%, #f0f0f0 100%); } }
        .card-metal::before { content: ''; position: absolute; top: 0; left: -150%; width: 60%; height: 100%; background: linear-gradient(90deg, transparent, rgba(255,255,255,0.9), transparent); animation: shine 3.5s infinite; transform: skewX(-20deg); }
        @keyframes shine { 100% { left: 200%; } }
        .p-pic-wrapper { position: relative; width: 80px; height: 80px; margin-right: 20px; z-index: 2; flex-shrink: 0; }
        .p-pic { width: 100%; height: 100%; border-radius: 50%; border: 4px solid #333; object-fit: cover; box-shadow: 0 5px 15px rgba(0,0,0,0.5); transition: transform 0.5s; }
        .p-pic:hover { transform: rotate(15deg) scale(1.05); }
        .p-icon { display: none; width: 100%; height: 100%; border-radius: 50%; border: 4px solid #333; background: linear-gradient(135deg, #ddd, #aaa); align-items: center; justify-content: center; font-size: 32px; color: #333; }
        .card-gold { background: radial-gradient(ellipse at center, #ffd700 0%, #d4af37 40%, #b8860b 100%); text-align: center; color: #2e2003; border: 3px solid #fff2ad; box-shadow: 0 0 35px rgba(255, 215, 0, 0.6), inset 0 0 15px rgba(255, 255, 255, 0.6); animation: pulseGold 3s infinite alternate, floatCard 6s infinite ease-in-out; position: relative; }
        @keyframes pulseGold { 0% { box-shadow: 0 0 35px rgba(255,215,0,0.6), inset 0 0 15px rgba(255,255,255,0.6); } 100% { box-shadow: 0 0 50px rgba(255,215,0,0.8), inset 0 0 25px rgba(255,255,255,0.8); } }
        @keyframes floatCard { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-10px); } }
        .card-gold::after { content: ''; position: absolute; top: -50%; left: -50%; width: 200%; height: 200%; background: radial-gradient(circle, rgba(255,255,255,0.4) 0%, transparent 70%); transform: rotate(30deg); pointer-events: none; animation: rotateLight 20s linear infinite; }
        @keyframes rotateLight { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        .glass-overlay { position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.9); backdrop-filter: blur(10px); display: flex; flex-direction: column; align-items: center; justify-content: center; border-radius: 20px; z-index: 10; animation: overlayAppear 0.5s ease-out; }
        @keyframes overlayAppear { from { opacity: 0; backdrop-filter: blur(0); } to { opacity: 1; backdrop-filter: blur(10px); } }
        .unlock-btn { background: linear-gradient(135deg, var(--neon-pink), var(--neon-purple), var(--neon-blue)); color: white; border: none; padding: 18px 40px; border-radius: 35px; font-weight: 800; font-size: 18px; cursor: pointer; display: inline-flex; align-items: center; gap: 12px; font-family: 'Orbitron', monospace; box-shadow: 0 8px 25px rgba(0,243,255,0.5), inset 0 1px 0 rgba(255,255,255,0.3); margin-top: 20px; position: relative; overflow: hidden; transition: all 0.3s; animation: buttonPulse 2s infinite; }
        @keyframes buttonPulse { 0%, 100% { box-shadow: 0 8px 25px rgba(0,243,255,0.5), inset 0 1px 0 rgba(255,255,255,0.3); } 50% { box-shadow: 0 8px 35px rgba(0,243,255,0.7), inset 0 1px 0 rgba(255,255,255,0.5); } }
        .unlock-btn::before { content: ''; position: absolute; top: 0; left: -100%; width: 100%; height: 100%; background: linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent); transition: left 0.7s; }
        .unlock-btn:hover::before { left: 100%; }
        .unlock-btn:active { transform: scale(0.95); animation: none; }
        .card-silver { background: linear-gradient(135deg, #c0c0c0 0%, #d0d0d0 30%, #e0e0e0 50%, #d0d0d0 70%, #c0c0c0 100%); border: 2px solid #fff; box-shadow: 0 15px 30px rgba(0,0,0,0.4); color: #222; text-align: center; aspect-ratio: 16/9; display: flex; flex-direction: column; justify-content: center; align-items: center; animation: silverShimmer 3s infinite alternate; }
        @keyframes silverShimmer { from { background: linear-gradient(135deg, #c0c0c0 0%, #d0d0d0 30%, #e0e0e0 50%, #d0d0d0 70%, #c0c0c0 100%); } to { background: linear-gradient(135deg, #d0d0d0 0%, #e0e0e0 30%, #f0f0f0 50%, #e0e0e0 70%, #d0d0d0 100%); } }
        .card-purple { background: linear-gradient(135deg, var(--neon-purple) 0%, #7b2cbf 50%, #5a189a 100%); border: 2px solid #c77dff; box-shadow: 0 0 30px rgba(157,78,221,0.7), inset 0 0 15px rgba(255,255,255,0.2); color: white; text-align: center; aspect-ratio: 16/9; display: flex; flex-direction: column; justify-content: center; align-items: center; position: relative; padding: 25px; animation: neonPulse 2s infinite alternate; }
        @keyframes neonPulse { from { box-shadow: 0 0 30px rgba(157,78,221,0.7), inset 0 0 15px rgba(255,255,255,0.2); } to { box-shadow: 0 0 45px rgba(157,78,221,0.9), inset 0 0 20px rgba(255,255,255,0.3); } }
        .card-purple::before { content: ''; position: absolute; top: -15px; left: -15px; right: -15px; bottom: -15px; background: linear-gradient(45deg, var(--neon-purple), #7b2cbf, #5a189a, var(--neon-purple)); z-index: -1; border-radius: 25px; opacity: 0.6; filter: blur(15px); animation: borderGlow 3s infinite alternate; }
        @keyframes borderGlow { from { opacity: 0.4; filter: blur(12px); } to { opacity: 0.7; filter: blur(18px); } }
        .btn { background: linear-gradient(135deg, #111, #222); color: var(--gold); border: none; padding: 16px 35px; border-radius: 35px; font-weight: 800; font-size: 18px; margin-top: 20px; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; gap: 12px; font-family: 'Orbitron', monospace; box-shadow: 0 8px 20px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.1); transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); position: relative; z-index: 5; overflow: hidden; }
        .btn::before { content: ''; position: absolute; top: 0; left: -100%; width: 100%; height: 100%; background: linear-gradient(90deg, transparent, rgba(255,215,0,0.3), transparent); transition: left 0.7s; }
        .btn:hover::before { left: 100%; }
        .btn:active { transform: scale(0.95); }
        .btn-purple { background: linear-gradient(135deg, #5a189a, var(--neon-purple)); color: white; }
        .btn-cyan { background: linear-gradient(135deg, #00f3ff, #0088ff); color: #000; }
        .popup { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.98); backdrop-filter: blur(15px); display: none; justify-content: center; align-items: center; z-index: 9999; padding: 20px; animation: popupAppear 0.3s ease-out; }
        @keyframes popupAppear { from { opacity: 0; backdrop-filter: blur(0); } to { opacity: 1; backdrop-filter: blur(15px); } }
        .popup-content { background: linear-gradient(135deg, #1a1a20, #2a2a30); padding: 35px; border-radius: 25px; width: 100%; max-width: 400px; border: 2px solid var(--cyan); text-align: center; box-shadow: 0 0 40px rgba(0,243,255,0.3), inset 0 0 20px rgba(0,243,255,0.1); animation: contentAppear 0.4s ease-out; }
        @keyframes contentAppear { from { transform: scale(0.8); opacity: 0; } to { transform: scale(1); opacity: 1; } }
        .popup-content h3 { margin-top: 0; color: var(--cyan); font-size: 24px; font-family: 'Orbitron', monospace; text-shadow: 0 0 15px rgba(0,243,255,0.7); }
        input, textarea { width: 100%; padding: 15px; margin: 12px 0; background: rgba(42,42,48,0.8); border: 2px solid #444; color: white; border-radius: 12px; font-family: inherit; font-size: 16px; transition: all 0.3s; }
        input:focus, textarea:focus { outline: none; border-color: var(--cyan); box-shadow: 0 0 15px rgba(0,243,255,0.3); background: rgba(42,42,48,1); }
        .hist-item { background: var(--panel); border-radius: 12px; padding: 15px; margin-bottom: 10px; display: flex; justify-content: space-between; border-left: 5px solid #333; width: 100%; transition: all 0.3s; animation: itemAppear 0.5s ease-out; }
        @keyframes itemAppear { from { opacity: 0; transform: translateX(-20px); } to { opacity: 1; transform: translateX(0); } }
        .hist-item:hover { transform: translateX(5px); box-shadow: 0 5px 15px rgba(0,0,0,0.3); }
        .status-completed { color: var(--neon-green); text-shadow: 0 0 10px rgba(0,255,170,0.5); } 
        .status-pending { color: orange; text-shadow: 0 0 10px rgba(255,165,0,0.5); } 
        .status-rejected { color: red; text-shadow: 0 0 10px rgba(255,0,0,0.5); }
        .overlay-loader { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.98); z-index: 2000; display: flex; flex-direction: column; justify-content: center; align-items: center; }
        .spinner { width: 60px; height: 60px; border: 6px solid #333; border-top: 6px solid var(--cyan); border-radius: 50%; animation: spin 1s linear infinite; margin: 25px; box-shadow: 0 0 20px rgba(0,243,255,0.5); }
        @keyframes spin { to { transform: rotate(360deg); } }
        .refer-code-box { background: rgba(255,255,255,0.15); border: 3px dashed var(--cyan); padding: 20px 15px; border-radius: 15px; margin: 15px 0; font-family: 'Orbitron', monospace; font-size: 28px; letter-spacing: 4px; cursor: pointer; text-align: center; word-break: break-all; margin-left: 25px; margin-right: 25px; transition: all 0.3s; animation: codePulse 2s infinite alternate; }
        @keyframes codePulse { from { box-shadow: 0 0 20px rgba(0,243,255,0.3); } to { box-shadow: 0 0 30px rgba(0,243,255,0.6); } }
        .refer-code-box:hover { transform: scale(1.05); background: rgba(255,255,255,0.2); }
        .leaderboard-table { width: 100%; border-collapse: collapse; margin-top: 20px; font-size: 15px; border-radius: 15px; overflow: hidden; }
        .leaderboard-table tr { border-bottom: 1px solid rgba(255,255,255,0.15); transition: background 0.3s; }
        .leaderboard-table tr:hover { background: rgba(0,243,255,0.1); }
        .leaderboard-table td { padding: 12px 8px; }
        .leaderboard-table .highlight { background: rgba(0,243,255,0.2); border-left: 5px solid var(--cyan); animation: highlightPulse 2s infinite alternate; }
        @keyframes highlightPulse { from { background: rgba(0,243,255,0.2); } to { background: rgba(0,243,255,0.3); } }
        .code-input { font-size: 28px; letter-spacing: 8px; text-align: center; text-transform: uppercase; width: 100%; margin: 15px 0; padding: 20px; border-radius: 15px; border: 3px solid silver; background: white; color: #222; font-family: 'Orbitron', monospace; box-shadow: 0 0 20px rgba(192,192,192,0.5); transition: all 0.3s; }
        .code-input:focus { outline: none; border-color: var(--cyan); box-shadow: 0 0 30px rgba(0,243,255,0.7); }
        .gift-result { text-align: center; margin-top: 25px; padding: 20px; border-radius: 15px; background: rgba(0,0,0,0.4); backdrop-filter: blur(10px); animation: resultAppear 0.5s ease-out; }
        @keyframes resultAppear { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
        .referrals-list { max-height: 350px; overflow-y: auto; padding-right: 8px; }
        .referrals-list::-webkit-scrollbar { width: 8px; }
        .referrals-list::-webkit-scrollbar-track { background: rgba(255,255,255,0.1); border-radius: 4px; }
        .referrals-list::-webkit-scrollbar-thumb { background: var(--cyan); border-radius: 4px; box-shadow: inset 0 0 6px rgba(0,0,0,0.3); }
        .verify-popup { z-index: 10000; }
        .verify-popup .popup-content { max-width: 450px; }
        .verify-actions { display: flex; gap: 15px; margin-top: 25px; }
        .verify-actions button { flex: 1; }
        .balance-loading { font-size: 56px; font-weight: 900; margin: 8px 0; text-shadow: 0 3px 8px rgba(0,0,0,0.3); color: #666; }
        .skeleton { background: linear-gradient(90deg, #333 25%, #444 50%, #333 75%); background-size: 200% 100%; animation: loading 1.5s infinite; border-radius: 10px; }
        @keyframes loading { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
        .action-loading { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.95); z-index: 99999; justify-content: center; align-items: center; flex-direction: column; }
        .action-loader { font-size: 18px; color: white; margin-top: 20px; font-weight: bold; font-family: 'Orbitron', monospace; }
        .toast { position: fixed; bottom: 25px; left: 50%; transform: translateX(-50%); background: #333; color: white; padding: 15px 30px; border-radius: 12px; z-index: 10000; display: none; box-shadow: 0 6px 20px rgba(0,0,0,0.4); animation: toastSlide 0.3s ease-out; }
        @keyframes toastSlide { from { transform: translateX(-50%) translateY(30px); opacity: 0; } to { transform: translateX(-50%) translateY(0); opacity: 1; } }
        .toast-success { background: linear-gradient(135deg, #28a745, #20c997); }
        .toast-error { background: linear-gradient(135deg, #dc3545, #fd7e14); }
        .toast-info { background: linear-gradient(135deg, #17a2b8, #0dcaf0); }
        .progress-bar { width: 100%; height: 6px; background: #333; border-radius: 3px; overflow: hidden; margin-top: 15px; }
        .progress-fill { height: 100%; background: linear-gradient(90deg, #00f3ff, #0088ff, var(--neon-pink)); width: 0%; transition: width 0.4s cubic-bezier(0.4, 0, 0.2, 1); }
        .verification-success { color: var(--neon-green); font-weight: bold; margin: 15px 0; font-size: 18px; text-shadow: 0 0 15px rgba(0,255,170,0.7); }
        .verification-error { color: #ff4444; font-weight: bold; margin: 15px 0; font-size: 18px; text-shadow: 0 0 15px rgba(255,68,68,0.7); }
        .loading-screen { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: radial-gradient(circle at top, #111122, #050508); display: flex; flex-direction: column; justify-content: center; align-items: center; z-index: 99999; }
        .loading-logo { width: 100px; height: 100px; border-radius: 50%; border: 4px solid var(--cyan); box-shadow: 0 0 30px rgba(0,243,255,0.8), inset 0 0 20px rgba(0,243,255,0.3); margin-bottom: 30px; animation: pulse 2s infinite alternate, rotate 20s linear infinite; }
        @keyframes pulse { 0%, 100% { transform: scale(1) rotate(0deg); opacity: 1; } 50% { transform: scale(1.1) rotate(180deg); opacity: 0.9; } }
        @keyframes rotate { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        .loading-text { color: var(--cyan); font-size: 22px; font-weight: bold; margin-top: 25px; font-family: 'Orbitron', monospace; text-shadow: 0 0 20px rgba(0,243,255,0.8); animation: textFlow 3s infinite alternate; }
        @keyframes textFlow { from { letter-spacing: 2px; } to { letter-spacing: 4px; } }
        .resource-bar { width: 85%; max-width: 350px; margin-top: 25px; }
        .resource-text { color: #888; font-size: 14px; margin-top: 8px; font-family: 'Rajdhani', sans-serif; }
        .verification-steps { background: rgba(255,255,255,0.08); border-radius: 15px; padding: 20px; margin-top: 20px; max-height: 250px; overflow-y: auto; backdrop-filter: blur(10px); }
        .step-item { display: flex; align-items: center; gap: 15px; margin: 8px 0; padding: 12px; border-radius: 10px; background: rgba(255,255,255,0.05); transition: all 0.3s; animation: stepAppear 0.5s ease-out; }
        @keyframes stepAppear { from { opacity: 0; transform: translateX(-20px); } to { opacity: 1; transform: translateX(0); } }
        .step-checking { color: #ffaa00; }
        .step-passed { color: var(--neon-green); }
        .step-failed { color: #ff4444; }
        .step-pending { color: #0088ff; }
        .step-icon { font-size: 18px; width: 25px; text-align: center; }
        .private-channel-info { background: rgba(0,136,255,0.15); border: 2px solid #0088ff; border-radius: 12px; padding: 15px; margin: 15px 0; animation: infoPulse 3s infinite alternate; }
        @keyframes infoPulse { from { box-shadow: 0 0 15px rgba(0,136,255,0.3); } to { box-shadow: 0 0 25px rgba(0,136,255,0.6); } }
        .device-error-retry { margin-top: 20px; }
        .floating-particles { position: fixed; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: -1; }
        .floating-coin { position: absolute; font-size: 24px; color: var(--gold); opacity: 0.7; animation: floatCoin 20s infinite linear; }
        @keyframes floatCoin { 0% { transform: translateY(100vh) rotate(0deg); } 100% { transform: translateY(-100px) rotate(360deg); } }
        .glitch-text { position: relative; animation: glitch 3s infinite; }
        @keyframes glitch { 0%, 100% { text-shadow: 2px 2px 0 var(--neon-pink), -2px -2px 0 var(--neon-blue); } 50% { text-shadow: -2px 2px 0 var(--neon-blue), 2px -2px 0 var(--neon-pink); } }
        .neon-border { position: relative; }
        .neon-border::after { content: ''; position: absolute; top: -2px; left: -2px; right: -2px; bottom: -2px; border-radius: inherit; background: linear-gradient(45deg, var(--neon-pink), var(--neon-blue), var(--neon-green), var(--neon-purple)); z-index: -1; opacity: 0.7; filter: blur(5px); animation: borderRotate 4s linear infinite; }
        @keyframes borderRotate { from { filter: hue-rotate(0deg) blur(5px); } to { filter: hue-rotate(360deg) blur(5px); } }
        .typing-effect { overflow: hidden; border-right: 3px solid var(--cyan); white-space: nowrap; animation: typing 3.5s steps(40, end), blink-caret 0.75s step-end infinite; }
        @keyframes typing { from { width: 0; } to { width: 100%; } }
        @keyframes blink-caret { from, to { border-color: transparent; } 50% { border-color: var(--cyan); } }
        .balance-number { font-family: 'Orbitron', monospace; font-size: 56px; font-weight: 900; margin: 10px 0; text-shadow: 0 0 20px rgba(255,215,0,0.8), 0 0 40px rgba(255,215,0,0.4); background: linear-gradient(45deg, #ffd700, #ffaa00, #ffd700); -webkit-background-clip: text; -webkit-text-fill-color: transparent; animation: balanceGlow 2s infinite alternate; }
        @keyframes balanceGlow { from { text-shadow: 0 0 20px rgba(255,215,0,0.8), 0 0 40px rgba(255,215,0,0.4); } to { text-shadow: 0 0 30px rgba(255,215,0,1), 0 0 60px rgba(255,215,0,0.6), 0 0 90px rgba(255,215,0,0.3); } }
        .channel-button { background: linear-gradient(135deg, #1a1a1a, #2a2a2a); border: 2px solid var(--cyan); border-radius: 15px; padding: 12px 20px; margin: 8px 0; display: flex; align-items: center; justify-content: space-between; cursor: pointer; transition: all 0.3s; animation: buttonAppear 0.6s ease-out; }
        .channel-button:hover { transform: translateX(5px); background: linear-gradient(135deg, #2a2a2a, #3a3a3a); box-shadow: 0 0 20px rgba(0,243,255,0.4); }
        .channel-button i { font-size: 20px; color: var(--cyan); }
        .channel-button.disabled { opacity: 0.5; border-color: #888; }
        .channel-button.disabled i { color: #888; }
        .channel-button.disabled:hover { transform: none; box-shadow: none; }
        .scan-line { position: absolute; top: 0; left: 0; width: 100%; height: 3px; background: linear-gradient(90deg, transparent, var(--cyan), transparent); animation: scan 3s infinite linear; }
        @keyframes scan { 0% { top: 0; } 100% { top: 100%; } }
        .holographic-effect { background: linear-gradient(45deg, rgba(0,243,255,0.1), rgba(157,78,221,0.1), rgba(255,0,255,0.1)); background-size: 400% 400%; animation: holographic 8s ease infinite; }
        @keyframes holographic { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }
    </style>
</head>
<body>
    <div id="particles-container" class="floating-particles"></div>
    
    <div id="loading-screen" class="loading-screen">
        <div class="scan-line"></div>
        <img src="{{ base_url }}/static/{{ settings.logo_filename }}?v={{ timestamp }}" class="loading-logo" onerror="this.src='data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iODAiIGhlaWdodD0iODAiIHZpZXdCb3g9IjAgMCA4MCA4MCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48Y2lyY2xlIGN4PSI0MCIgY3k9IjQwIiByPSIzOCIgZmlsbD0iIzAwZjNmZiIgc3Ryb2tlPSIjZmZmIiBzdHJva2Utd2lkdGg9IjIiLz48L3N2Zz4='">
        <div class="loading-text glitch-text">{{ settings.bot_name }}</div>
        <div class="resource-bar">
            <div class="progress-bar">
                <div id="resource-progress" class="progress-fill" style="width: 0%;"></div>
            </div>
            <div id="resource-text" class="resource-text">Initializing System...</div>
        </div>
    </div>
    
    <div id="verification-process" class="action-loading" style="display: none;">
        <div class="spinner"></div>
        <div id="verification-text" class="action-loader">Starting Verification Protocol...</div>
        <div id="verification-steps" class="verification-steps" style="width: 85%; max-width: 350px; margin-top: 25px;"></div>
    </div>
    
    <div id="action-loading" class="action-loading">
        <div class="spinner"></div>
        <div id="action-loader-text" class="action-loader">Processing Transaction...</div>
    </div>
    
    <div id="toast" class="toast"></div>
    
    <div id="app" class="hidden" style="width:100%; display:flex; flex-direction:column; align-items:center;">
        <div class="header">
            <img src="{{ base_url }}/static/{{ settings.logo_filename }}?v={{ timestamp }}" class="logo" onerror="this.src='data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNTAiIGhlaWdodD0iNTAiIHZpZXdCb3g9IjAgMCA1MCA1MCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48Y2lyY2xlIGN4PSIyNSIgY3k9IjI1IiByPSIyMyIgZmlsbD0iIzAwZjNmZiIgc3Ryb2tlPSIjZmZmIiBzdHJva2Utd2lkdGg9IjIiLz48L3N2Zz4='">
            <div class="title typing-effect">{{ settings.bot_name }}</div>
        </div>
        
        <div class="nav-bar">
            <button class="nav-btn active" onclick="switchTab('home')">
                <i class="fas fa-home"></i>
                <div class="nav-text">HOME</div>
            </button>
            <button class="nav-btn" onclick="switchTab('gift')">
                <i class="fas fa-gift"></i>
                <div class="nav-text">GIFT</div>
            </button>
            <button class="nav-btn" onclick="switchTab('refer')">
                <i class="fas fa-users"></i>
                <div class="nav-text">REFER</div>
            </button>
            <button class="nav-btn" onclick="switchTab('leaderboard')">
                <i class="fas fa-trophy"></i>
                <div class="nav-text">RANK</div>
            </button>
        </div>
        
        <div id="tab-home" class="tab-content">
            <div class="card-metal">
                <div class="p-pic-wrapper"><img src="/get_pfp?uid={{ user_id }}&v={{ timestamp }}" class="p-pic" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';"><div class="p-icon"><i class="fas fa-user"></i></div></div>
                <div style="z-index:2;">
                    <div style="font-size:22px; font-weight:800; color: #222;">{{ user.name }}</div>
                    <div onclick="openPop('contact')" style="color:#0044cc; font-size:14px; margin-top:8px; cursor:pointer; text-decoration:underline; font-weight:bold;">Contact Admin</div>
                </div>
            </div>
            
            <div class="card-gold neon-border" id="balance-card">
                {% if user_status != 'verified' and not settings.hide_verify_button %}
                <div id="glass-overlay" class="glass-overlay">
                    <div style="text-align: center; padding: 25px;">
                        <i class="fas fa-lock" style="font-size: 50px; color: var(--neon-pink); margin-bottom: 20px; animation: lockPulse 2s infinite alternate;"></i>
                        @keyframes lockPulse { from { transform: scale(1); } to { transform: scale(1.1); filter: drop-shadow(0 0 15px var(--neon-pink)); } }
                        <div style="font-size: 22px; font-weight: bold; color: white; margin-bottom: 10px;">Account Locked</div>
                        <div style="font-size: 15px; color: #aaa; margin-top: 15px; max-width: 280px; line-height: 1.5;">
                            Complete verification to unlock your wallet{% if user.verified %} and refresh channel access{% endif %}
                        </div>
                        <button class="unlock-btn" onclick="startVerification()">
                            <i class="fas fa-unlock-alt"></i> {% if user.verified %}CHECK CHANNELS{% else %}VERIFY NOW{% endif %}
                        </button>
                    </div>
                </div>
                {% endif %}
                <div style="font-size:16px; font-weight:800; opacity:0.9; letter-spacing:3px; color: #2e2003;">WALLET BALANCE</div>
                <div id="balance-amount" class="balance-number">₹{{ "%.2f"|format(user.balance) }}</div>
                <button class="btn" onclick="openPop('withdraw')" {% if user_status != 'verified' %}disabled style="opacity:0.5;"{% endif %}><i class="fas fa-wallet"></i> WITHDRAW</button>
            </div>
            
            <div style="margin-top:25px; width:100%;">
                <div style="color:#888; font-size:15px; font-weight:bold; margin-bottom:15px; display: flex; align-items: center; gap: 10px;">
                    <i class="fas fa-history"></i> RECENT ACTIVITY
                </div>
                <div id="history-list">
                    <div class="hist-item skeleton" style="height:70px;"></div>
                    <div class="hist-item skeleton" style="height:70px;"></div>
                </div>
            </div>
        </div>
        
        <div id="tab-gift" class="tab-content hidden">
            <div style="text-align:center; margin-bottom:25px;">
                <h2 style="margin:0; color:var(--cyan); text-shadow: 0 0 20px rgba(0,243,255,0.7);">GIFT CODE</h2>
                <p style="color:#aaa; margin-top:8px; font-size: 15px;">Enter 5-character code to claim rewards</p>
            </div>
            <div class="card-silver holographic-effect">
                <input type="text" id="gift-code" class="code-input" maxlength="5" placeholder="ABCDE" oninput="this.value = this.value.toUpperCase()">
                <button class="btn" onclick="claimGift()" style="background:linear-gradient(135deg, #222, #333); color:silver; margin-top: 25px;"><i class="fas fa-gift"></i> CLAIM NOW</button>
            </div>
            <div id="gift-result" class="gift-result"></div>
        </div>
        
        <div id="tab-refer" class="tab-content hidden">
            <div style="text-align:center; margin-bottom:25px;">
                <h2 style="margin:0; color:var(--neon-purple); text-shadow: 0 0 20px rgba(157,78,221,0.7);">REFER & EARN</h2>
                <p style="color:#aaa; margin-top:8px; font-size: 15px;">Share your code and earn rewards</p>
            </div>
            <div class="card-purple">
                <div id="refer-code-display" class="refer-code-box" onclick="copyReferCode()">LOADING...</div>
                <button class="btn btn-purple" onclick="shareReferLink()" style="margin-top:25px;"><i class="fas fa-share-alt"></i> SHARE LINK</button>
            </div>
            <div style="width:100%; margin-top:25px;">
                <h3 style="color:var(--neon-purple); margin-bottom:15px; display: flex; align-items: center; gap: 10px;">
                    <i class="fas fa-users"></i> YOUR REFERRALS
                </h3>
                <div id="referrals-list" class="referrals-list">
                    <div style="text-align:center; color:#666; padding:30px; font-size: 16px;">Loading referrals...</div>
                </div>
            </div>
        </div>
        
        <div id="tab-leaderboard" class="tab-content hidden">
            <div style="text-align:center; margin-bottom:25px;">
                <h2 style="margin:0; color:var(--gold); text-shadow: 0 0 20px rgba(255,215,0,0.7);">LEADERBOARD</h2>
                <p style="color:#aaa; font-size:15px;">Top 20 Users by Balance</p>
            </div>
            <table class="leaderboard-table">
                <thead>
                    <tr style="background:linear-gradient(135deg, rgba(255,215,0,0.2), rgba(255,193,7,0.1));">
                        <td style="font-weight:bold; color:var(--gold); padding: 15px 8px;">RANK</td>
                        <td style="font-weight:bold; color:var(--gold);">NAME</td>
                        <td style="font-weight:bold; color:var(--gold); text-align:right;">BALANCE</td>
                        <td style="font-weight:bold; color:var(--gold); text-align:right;">REFERS</td>
                    </tr>
                </thead>
                <tbody id="leaderboard-list">
                    {% for user in leaderboard %}
                    <tr {% if user.user_id == user_id %}class="highlight"{% endif %}>
                        <td style="font-weight:bold; color:#ccc; font-size: 16px;">{{ loop.index }}</td>
                        <td>
                            <div style="font-weight:bold; font-size: 14px;">{{ user.name[:15] }}{% if user.name|length > 15 %}...{% endif %}</div>
                            <div style="font-size:11px; color:#888;">{{ user.user_id[:8] }}...</div>
                        </td>
                        <td style="text-align:right; font-weight:bold; color:var(--gold); font-size: 16px;">₹{{ "%.2f"|format(user.balance) }}</td>
                        <td style="text-align:right; font-size:13px; color:#aaa;">{{ user.total_refers }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
    
    <!-- Popups -->
    <div id="pop-contact" class="popup">
        <div class="popup-content">
            <h3>Contact Admin</h3>
            <textarea id="c-msg" rows="4" placeholder="Your message..."></textarea>
            <input type="file" id="c-file" accept="image/*">
            <button class="btn" onclick="sendContact()">SEND MESSAGE</button>
            <button class="btn" onclick="closePop()" style="background:transparent; color:#f44; margin-top:15px;">Close</button>
        </div>
    </div>
    
    <div id="pop-withdraw" class="popup">
        <div class="popup-content">
            <h3>Withdraw Money</h3>
            <input id="w-upi" placeholder="Enter UPI ID (e.g. name@bank)">
            <input id="w-amt" type="number" placeholder="Amount (Min: ₹{{ settings.min_withdrawal }})">
            <button class="btn" onclick="submitWithdraw()">WITHDRAW</button>
            <button class="btn" onclick="closePop()" style="background:transparent; color:#f44; margin-top:15px;">Cancel</button>
        </div>
    </div>
    
    <div id="pop-verify" class="popup verify-popup">
        <div class="popup-content">
            <h3>⚠️ Verification Required</h3>
            <p id="verify-error-msg" style="color:var(--neon-pink); margin:20px 0; font-size: 16px;">Please complete verification to continue</p>
            <div id="device-error-retry" class="device-error-retry" style="display:none;">
                <button class="btn" onclick="retryDeviceVerification()" style="background:linear-gradient(135deg, #0088ff, #00ccff); color:white;">RETRY DEVICE CHECK</button>
            </div>
            <div id="private-channels-list" style="margin: 20px 0;"></div>
            <div class="verify-actions">
                <button class="btn" onclick="closePop()" style="background:linear-gradient(135deg, #dc3545, #fd7e14); color:white;">CLOSE</button>
                <button class="btn" onclick="retryVerification()" style="background:linear-gradient(135deg, #0088ff, #00ccff); color:white;">RETRY</button>
            </div>
        </div>
    </div>
    
    <script>
        const UID = "{{ user_id }}";
        const USER_STATUS = "{{ user_status }}";
        const IS_VERIFIED = {{ user.verified|lower }};
        const DEVICE_VERIFIED = {{ user.device_verified|lower }};
        const HIDE_VERIFY_BUTTON = {{ settings.hide_verify_button|lower }};
        let referData = null;
        let isVerified = IS_VERIFIED;
        let deviceVerified = DEVICE_VERIFIED;
        let userStatus = USER_STATUS;
        let deviceFingerprint = null;
        
        // Create floating particles
        function createParticles() {
            const container = document.getElementById('particles-container');
            for (let i = 0; i < 30; i++) {
                const coin = document.createElement('div');
                coin.className = 'floating-coin';
                coin.innerHTML = '₹';
                coin.style.left = Math.random() * 100 + 'vw';
                coin.style.fontSize = (Math.random() * 20 + 15) + 'px';
                coin.style.animationDuration = (Math.random() * 10 + 15) + 's';
                coin.style.animationDelay = Math.random() * 5 + 's';
                coin.style.opacity = Math.random() * 0.5 + 0.3;
                container.appendChild(coin);
            }
        }
        
        // Ultra fast loading with progress bar
        document.addEventListener('DOMContentLoaded', function() {
            createParticles();
            
            // Generate device fingerprint
            generateDeviceFingerprint();
            
            // Start progress animation
            let progress = 0;
            const progressBar = document.getElementById('resource-progress');
            const resourceText = document.getElementById('resource-text');
            
            const progressInterval = setInterval(() => {
                progress += 15;
                progressBar.style.width = progress + '%';
                
                if (progress <= 30) resourceText.textContent = "Loading assets...";
                else if (progress <= 60) resourceText.textContent = "Initializing app...";
                else if (progress <= 90) resourceText.textContent = "Almost ready...";
                else resourceText.textContent = "Complete!";
                
                if (progress >= 100) {
                    clearInterval(progressInterval);
                    
                    // Hide loading screen and show app
                    setTimeout(() => {
                        document.getElementById('loading-screen').style.display = 'none';
                        document.getElementById('app').classList.remove('hidden');
                        
                        // Auto-verify if channel verification is disabled and verify button is hidden
                        if (HIDE_VERIFY_BUTTON && userStatus !== 'verified') {
                            setTimeout(() => {
                                showToast("Account automatically verified!", "success", 3000);
                                updateBalance();
                            }, 500);
                        }
                        
                        // Load data in background
                        setTimeout(loadCriticalData, 100);
                    }, 100);
                }
            }, 30); // Very fast loading
        });
        
        function generateDeviceFingerprint() {
            // Collect browser fingerprint data
            const userAgent = navigator.userAgent;
            const language = navigator.language;
            const platform = navigator.platform;
            const hardwareConcurrency = navigator.hardwareConcurrency || 'unknown';
            const deviceMemory = navigator.deviceMemory || 'unknown';
            const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
            
            const fingerprintData = `${userAgent}|${language}|${platform}|${hardwareConcurrency}|${deviceMemory}|${timezone}|${Math.floor(Date.now()/1000/3600)}`;
            
            // Simple hash
            let hash = 0;
            for (let i = 0; i < fingerprintData.length; i++) {
                const char = fingerprintData.charCodeAt(i);
                hash = ((hash << 5) - hash) + char;
                hash = hash & hash;
            }
            
            deviceFingerprint = Math.abs(hash).toString(16);
            localStorage.setItem('device_fp', deviceFingerprint);
        }
        
        function loadCriticalData() {
            // Load history
            loadHistory();
            
            // Load refer info
            loadReferInfo();
            
            // Check if we need to verify
            if (userStatus !== 'verified' && !HIDE_VERIFY_BUTTON) {
                console.log('Verification needed');
            } else {
                document.querySelector('#balance-card .btn').disabled = false;
                document.querySelector('#balance-card .btn').style.opacity = '1';
            }
        }
        
        function startVerification() {
            document.getElementById('verification-process').style.display = 'flex';
            document.getElementById('verification-steps').innerHTML = '';
            document.getElementById('device-error-retry').style.display = 'none';
            
            updateVerificationStep('Starting verification process...', 'checking');
            
            // Use cached fingerprint or generate new
            const fp = deviceFingerprint || localStorage.getItem('device_fp') || 'new-device-' + Date.now();
            
            setTimeout(() => {
                fetch('/api/verify', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        user_id: UID, 
                        fp: fp,
                        bot_type: 'main'
                    })
                })
                .then(r => r.json())
                .then(data => {
                    if (data.ok) {
                        // Success - user verified
                        isVerified = true;
                        deviceVerified = data.device_verified || false;
                        userStatus = 'verified';
                        
                        // Update steps visualization
                        if (data.steps) {
                            data.steps.forEach(step => {
                                updateVerificationStep(step.message, step.status);
                            });
                        }
                        
                        // Hide verification process
                        setTimeout(() => {
                            document.getElementById('verification-process').style.display = 'none';
                            
                            // Hide glass overlay if exists
                            const glassOverlay = document.getElementById('glass-overlay');
                            if (glassOverlay) {
                                glassOverlay.classList.add('hidden');
                            }
                            
                            // Enable withdrawal button
                            const withdrawBtn = document.querySelector('#balance-card .btn');
                            withdrawBtn.disabled = false;
                            withdrawBtn.style.opacity = '1';
                            
                            // Update balance
                            if (data.balance !== undefined) {
                                document.getElementById('balance-amount').textContent = '₹' + data.balance.toFixed(2);
                            }
                            
                            // Show success message
                            if (data.bonus > 0) {
                                showToast(`✅ Verification successful! ₹${data.bonus} bonus added!`, 'success', 5000);
                            } else {
                                showToast('✅ Channels verified successfully!', 'success', 3000);
                            }
                            
                            // Load updated data
                            loadHistory();
                            loadReferInfo();
                            
                            // Show confetti for bonus
                            if (data.bonus > 0 && typeof confetti === 'function') {
                                confetti({particleCount: 200, spread: 100, origin: { y: 0.6 }});
                                setTimeout(() => {
                                    confetti({particleCount: 150, angle: 60, spread: 80, origin: { x: 0 }});
                                    confetti({particleCount: 150, angle: 120, spread: 80, origin: { x: 1 }});
                                }, 250);
                            }
                        }, 1000);
                    } else {
                        // Verification failed
                        setTimeout(() => {
                            document.getElementById('verification-process').style.display = 'none';
                            showVerificationError(data.msg, data.type, data.retry);
                        }, 1000);
                    }
                })
                .catch(err => {
                    document.getElementById('verification-process').style.display = 'none';
                    showToast('Verification failed. Please try again.', 'error');
                    console.error('Verification error:', err);
                });
            }, 500);
        }
        
        function updateVerificationStep(message, status) {
            const stepsContainer = document.getElementById('verification-steps');
            const stepClass = 'step-' + status;
            const icon = getStatusIcon(status);
            
            const stepDiv = document.createElement('div');
            stepDiv.className = 'step-item';
            stepDiv.innerHTML = `
                <div class="step-icon ${stepClass}">${icon}</div>
                <div class="${stepClass}" style="flex: 1;">${message}</div>
            `;
            
            stepsContainer.appendChild(stepDiv);
            stepsContainer.scrollTop = stepsContainer.scrollHeight;
            
            // Update verification text
            document.getElementById('verification-text').textContent = getVerificationStatusText(status);
        }
        
        function getStatusIcon(status) {
            switch(status) {
                case 'checking': return '⏳';
                case 'passed': return '✓';
                case 'failed': return '✗';
                case 'pending': return '⏱️';
                default: return '○';
            }
        }
        
        function getVerificationStatusText(status) {
            switch(status) {
                case 'checking': return 'Checking verification...';
                case 'passed': return 'Verification passed!';
                case 'failed': return 'Verification failed';
                case 'pending': return 'Waiting for approval...';
                default: return 'Processing...';
            }
        }
        
        function showVerificationError(message, errorType, showRetry = false) {
            let errorMsg = message;
            
            // Update error message in popup
            document.getElementById('verify-error-msg').textContent = errorMsg;
            
            // Show device retry button if needed
            if (showRetry && errorType === 'device') {
                document.getElementById('device-error-retry').style.display = 'block';
            } else {
                document.getElementById('device-error-retry').style.display = 'none';
            }
            
            document.getElementById('pop-verify').style.display = 'flex';
        }
        
        function retryDeviceVerification() {
            // Clear cached fingerprint and retry
            localStorage.removeItem('device_fp');
            deviceFingerprint = null;
            generateDeviceFingerprint();
            
            document.getElementById('pop-verify').style.display = 'none';
            startVerification();
        }
        
        function retryVerification() {
            document.getElementById('pop-verify').style.display = 'none';
            startVerification();
        }
        
        function showActionLoader(text = 'Processing...') {
            document.getElementById('action-loader-text').textContent = text;
            document.getElementById('action-loading').style.display = 'flex';
        }
        
        function hideActionLoader() {
            document.getElementById('action-loading').style.display = 'none';
        }
        
        function showToast(message, type = 'info', duration = 3000) {
            const toast = document.getElementById('toast');
            toast.textContent = message;
            toast.className = 'toast';
            toast.classList.add('toast-' + type);
            toast.style.display = 'block';
            
            setTimeout(() => {
                toast.style.display = 'none';
            }, duration);
        }
        
        function updateBalance() {
            fetch('/api/get_balance?user_id=' + UID)
                .then(r => r.json())
                .then(data => {
                    if (data.ok) {
                        document.getElementById('balance-amount').textContent = '₹' + data.balance.toFixed(2);
                    }
                })
                .catch(() => {});
        }
        
        function switchTab(tabName) {
            document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
            event.target.closest('.nav-btn').classList.add('active');
            
            document.querySelectorAll('.tab-content').forEach(tab => tab.classList.add('hidden'));
            document.getElementById('tab-' + tabName).classList.remove('hidden');
            
            if (tabName === 'leaderboard') {
                loadLeaderboard();
            } else if (tabName === 'refer') {
                loadReferInfo();
            }
        }
        
        function submitWithdraw() {
            if (userStatus !== 'verified') {
                showToast('Please verify your account first!', 'error');
                return;
            }
            
            const upi = document.getElementById('w-upi').value.trim();
            const amount = document.getElementById('w-amt').value;
            
            if (!upi || !amount) {
                showToast('Please fill all fields', 'error');
                return;
            }
            
            closePop();
            showActionLoader('Processing withdrawal...');
            
            fetch('/api/withdraw', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({user_id: UID, amount: amount, upi: upi})
            })
            .then(r => r.json())
            .then(data => {
                hideActionLoader();
                if (data.ok) {
                    showToast(data.msg, 'success', 5000);
                    if (data.auto && typeof confetti === 'function') {
                        confetti({particleCount: 200, spread: 100, origin: { y: 0.6 }});
                        setTimeout(() => {
                            confetti({particleCount: 150, angle: 60, spread: 80, origin: { x: 0 }});
                            confetti({particleCount: 150, angle: 120, spread: 80, origin: { x: 1 }});
                        }, 250);
                    }
                    if (data.new_balance !== undefined) {
                        document.getElementById('balance-amount').textContent = '₹' + data.new_balance.toFixed(2);
                    }
                    loadHistory();
                } else {
                    showToast(data.msg, 'error');
                }
            })
            .catch(err => {
                hideActionLoader();
                showToast('Withdrawal failed. Please try again.', 'error');
            });
        }
        
        function sendContact() {
            const message = document.getElementById('c-msg').value;
            const fileInput = document.getElementById('c-file');
            
            if (!message.trim()) {
                showToast('Please enter a message', 'error');
                return;
            }
            
            showActionLoader('Sending message...');
            
            const formData = new FormData();
            formData.append('user_id', UID);
            formData.append('msg', message);
            if (fileInput.files[0]) {
                formData.append('image', fileInput.files[0]);
            }
            
            fetch('/api/contact_upload', {
                method: 'POST',
                body: formData
            })
            .then(r => r.json())
            .then(data => {
                hideActionLoader();
                if (data.ok) {
                    showToast('Message sent successfully!', 'success');
                    closePop();
                    document.getElementById('c-msg').value = '';
                    document.getElementById('c-file').value = '';
                } else {
                    showToast('Failed to send: ' + data.msg, 'error');
                }
            })
            .catch(err => {
                hideActionLoader();
                showToast('Failed to send message', 'error');
            });
        }
        
        function loadHistory() {
            fetch('/api/history?user_id=' + UID)
            .then(r => r.json())
            .then(history => {
                const container = document.getElementById('history-list');
                if (!history || history.length === 0) {
                    container.innerHTML = '<div style="text-align:center; color:#666; padding:30px; font-size: 16px;">No activity yet</div>';
                    return;
                }
                
                container.innerHTML = history.map(item => `
                    <div class="hist-item" style="border-left-color:${item.status === 'completed' ? 'var(--neon-green)' : item.status === 'pending' ? 'orange' : 'red'}">
                        <div>
                            <div style="font-weight:bold; font-size: 16px;">${item.name || 'Transaction'}</div>
                            <div style="font-size:12px;color:#888; margin-top: 5px;">${item.date || ''}</div>
                            ${item.tx_id && item.tx_id !== 'BONUS' ? `<div style="font-size:11px;color:#aaa; margin-top: 3px;">ID: ${item.tx_id}</div>` : ''}
                        </div>
                        <div style="text-align:right;">
                            <div style="font-weight:bold; font-size: 18px;">₹${(item.amount || 0).toFixed(2)}</div>
                            <div class="status-${item.status}" style="font-size: 13px; margin-top: 5px;">${(item.status || '').toUpperCase()}</div>
                            ${item.utr ? `<div style="font-size:11px;color:#aaa; margin-top: 3px;">${item.utr}</div>` : ''}
                        </div>
                    </div>
                `).join('');
            })
            .catch(err => {
                const container = document.getElementById('history-list');
                container.innerHTML = '<div style="text-align:center; color:#666; padding:30px; font-size: 16px;">Failed to load history</div>';
            });
        }
        
        function loadReferInfo() {
            fetch('/api/get_refer_info?user_id=' + UID)
            .then(r => r.json())
            .then(data => {
                if (data.ok) {
                    referData = data;
                    document.getElementById('refer-code-display').textContent = data.refer_code;
                    
                    const referralsList = document.getElementById('referrals-list');
                    if (data.referred_users && data.referred_users.length > 0) {
                        referralsList.innerHTML = data.referred_users.map(user => `
                            <div style="background:linear-gradient(135deg, rgba(157,78,221,0.15), rgba(123,44,191,0.1)); padding:15px; border-radius:12px; margin-bottom:8px; border: 1px solid rgba(157,78,221,0.3);">
                                <div style="font-weight:bold; font-size: 15px;">${user.name}</div>
                                <div style="font-size:11px; color:#888; margin-top: 3px;">ID: ${user.id}</div>
                                <div style="font-size:12px; margin-top:8px; font-weight:bold; padding: 5px 10px; border-radius: 20px; display: inline-block; background: ${user.verified ? 'rgba(0,255,170,0.2)' : 'rgba(255,165,0,0.2)'}; color:${user.verified ? 'var(--neon-green)' : 'orange'};">
                                    ${user.status}
                                </div>
                            </div>
                        `).join('');
                    } else {
                        referralsList.innerHTML = '<div style="text-align:center; color:#666; padding:30px; font-size: 16px;">No referrals yet. Share your code!</div>';
                    }
                }
            })
            .catch(err => {
                document.getElementById('refer-code-display').textContent = 'ERROR';
            });
        }
        
        function copyReferCode() {
            if (!referData) return;
            
            navigator.clipboard.writeText(referData.refer_code)
                .then(() => showToast('Refer code copied!', 'success', 2000))
                .catch(() => showToast('Failed to copy', 'error'));
        }
        
        function shareReferLink() {
            if (!referData) return;
            
            const text = `🎉 Join {{ settings.bot_name }} and earn money! Use my refer code: ${referData.refer_code}\n${referData.refer_link}`;
            const url = `https://t.me/share/url?url=${encodeURIComponent(referData.refer_link)}&text=${encodeURIComponent(text)}`;
            window.open(url, '_blank');
        }
        
        function claimGift() {
            const code = document.getElementById('gift-code').value.trim().toUpperCase();
            
            if (!code || code.length !== 5) {
                showToast('Please enter a valid 5-character code', 'error');
                return;
            }
            
            showActionLoader('Claiming gift...');
            
            fetch('/api/claim_gift', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({user_id: UID, code: code})
            })
            .then(r => r.json())
            .then(data => {
                hideActionLoader();
                const resultDiv = document.getElementById('gift-result');
                if (data.ok) {
                    resultDiv.innerHTML = `<div style="color:var(--neon-green); font-weight:bold; font-size:20px; text-shadow: 0 0 15px rgba(0,255,170,0.7);">${data.msg}</div>`;
                    document.getElementById('gift-code').value = '';
                    showToast(data.msg, 'success', 5000);
                    if (typeof confetti === 'function') {
                        confetti({particleCount: 300, spread: 120, origin: { y: 0.6 }});
                        setTimeout(() => {
                            confetti({particleCount: 200, angle: 60, spread: 100, origin: { x: 0 }});
                            confetti({particleCount: 200, angle: 120, spread: 100, origin: { x: 1 }});
                        }, 250);
                    }
                    if (data.new_balance !== undefined) {
                        document.getElementById('balance-amount').textContent = '₹' + data.new_balance.toFixed(2);
                    }
                    loadHistory();
                } else {
                    resultDiv.innerHTML = `<div style="color:#f44; font-weight:bold; font-size:18px; text-shadow: 0 0 15px rgba(255,68,68,0.7);">${data.msg}</div>`;
                    showToast(data.msg, 'error');
                }
                setTimeout(() => {
                    resultDiv.innerHTML = '';
                }, 5000);
            })
            .catch(err => {
                hideActionLoader();
                showToast('Failed to claim gift code', 'error');
            });
        }
        
        function loadLeaderboard() {
            fetch('/api/leaderboard')
            .then(r => r.json())
            .then(data => {
                const container = document.getElementById('leaderboard-list');
                if (!data.data || data.data.length === 0) {
                    container.innerHTML = '<tr><td colspan="4" style="text-align:center; padding:30px; color:#666; font-size: 16px;">No data available</td></tr>';
                    return;
                }
                
                container.innerHTML = data.data.map((user, index) => `
                    <tr ${user.user_id == UID ? 'class="highlight"' : ''}>
                        <td style="font-weight:bold; color:#ccc; font-size: 16px;">${index + 1}</td>
                        <td>
                            <div style="font-weight:bold; font-size: 14px;">${(user.name || '').substring(0, 15)}${(user.name || '').length > 15 ? '...' : ''}</div>
                            <div style="font-size:11px; color:#888;">${(user.user_id || '').substring(0, 8)}...</div>
                        </td>
                        <td style="text-align:right; font-weight:bold; color:var(--gold); font-size: 16px;">₹${(user.balance || 0).toFixed(2)}</td>
                        <td style="text-align:right; font-size:13px; color:#aaa;">${user.total_refers || 0}</td>
                    </tr>
                `).join('');
            })
            .catch(err => {});
        }
        
        function openPop(id) {
            document.getElementById('pop-' + id).style.display = 'flex';
        }
        
        function closePop() {
            document.querySelectorAll('.popup').forEach(popup => {
                popup.style.display = 'none';
            });
        }
        
        // Add keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 'r') {
                e.preventDefault();
                loadCriticalData();
                showToast('Data refreshed!', 'info', 1000);
            }
        });
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
        .channel-toggle { background:#ff9800; color:white; margin-right:5px; }
        .channel-disabled { opacity:0.5; }
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
        .admin-loader { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.9); z-index: 9999; justify-content: center; align-items: center; flex-direction: column; }
        .admin-spinner { width: 40px; height: 40px; border: 5px solid #333; border-top: 5px solid #007bff; border-radius: 50%; animation: spin 1s linear infinite; margin: 20px; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .admin-loader-text { color: white; font-weight: bold; font-size: 16px; margin-top: 15px; }
        .user-card { background: #2a2a2a; border-radius: 8px; padding: 12px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; cursor: pointer; transition: background 0.3s; }
        .user-card:hover { background: #333; }
        .user-id { font-family: monospace; font-size: 11px; color: #888; }
        .user-name { font-weight: bold; margin: 5px 0; }
        .user-balance { color: #ffd700; font-weight: bold; font-size: 16px; }
        .user-status { font-size: 11px; padding: 2px 6px; border-radius: 10px; }
        .status-verified { background: rgba(40,167,69,0.2); color: #28a745; }
        .status-pending { background: rgba(255,193,7,0.2); color: #ffc107; }
        .channel-details { font-size: 11px; color: #888; margin-top: 5px; }
        .channel-id { font-family: monospace; }
        .config-options { display: flex; flex-wrap: wrap; gap: 15px; margin: 15px 0; }
        .config-option { flex: 1; min-width: 200px; background: #2a2a2a; padding: 15px; border-radius: 8px; }
        .toggle-switch { position: relative; display: inline-block; width: 50px; height: 24px; margin-left: 10px; }
        .toggle-switch input { opacity: 0; width: 0; height: 0; }
        .toggle-slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #ccc; transition: .4s; border-radius: 24px; }
        .toggle-slider:before { position: absolute; content: ""; height: 16px; width: 16px; left: 4px; bottom: 4px; background-color: white; transition: .4s; border-radius: 50%; }
        input:checked + .toggle-slider { background-color: #007bff; }
        input:checked + .toggle-slider:before { transform: translateX(26px); }
        .toggle-label { display: flex; align-items: center; justify-content: space-between; margin: 10px 0; }
    </style>
</head>
<body>
    <div id="adminLoader" class="admin-loader">
        <div class="admin-spinner"></div>
        <div id="adminLoaderText" class="admin-loader-text">Processing...</div>
    </div>
    
    <div id="sendMessageModal" class="modal">
        <div class="m-content" style="max-width: 400px;">
            <h3>Send Message to User</h3>
            <div id="sendToUserInfo" style="text-align: left; margin-bottom: 15px; padding: 10px; background: #2a2a2a; border-radius: 5px;"></div>
            <textarea id="userMessage" rows="4" placeholder="Enter your message..."></textarea>
            <input type="file" id="userImage" accept="image/*">
            <button class="btn" style="background:#28a745" onclick="sendUserMessage()">Send Message</button>
            <button class="btn" style="background:transparent; color:#f44; margin-top:10px;" onclick="document.getElementById('sendMessageModal').style.display='none'">Cancel</button>
        </div>
    </div>
    
    <div id="approveModal" class="modal"><div class="m-content"><h3>Enter UTR</h3><input id="utrInput" placeholder="UTR Number"><button class="btn" style="background:#28a745" onclick="confirmApprove()">Confirm Pay</button><button class="btn" style="background:transparent; color:#f44" onclick="document.getElementById('approveModal').style.display='none'">Cancel</button></div></div>
    
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
    
    <div id="dash" class="tab active">
        <div class="card">
            <h3>Total Users: <span style="color:#007bff">{{ stats.total_users }}</span></h3>
            <h3>Pending Withdrawals: <span style="color:#ffc107">{{ stats.pending_count }}</span></h3>
            <h3>Active Gift Codes: <span style="color:#9d4edd">{{ gifts|length }}</span></h3>
        </div>
    </div>
    
    <div id="withs" class="tab">
        <div class="card" style="padding:0; overflow:hidden;">
            <table style="width:100%;">
                <tr style="background:#2a2a30;">
                    <th>Request Info</th>
                    <th style="text-align:right;">Action</th>
                </tr>
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
        <div class="card">
            <input placeholder="Search by name, ID or username" onkeyup="searchUsers(this)" style="margin-bottom: 15px;">
            <div id="usersContainer">
                {% for user in users %}
                <div class="user-card" onclick="openUserMessage('{{ user.id }}', '{{ user.name|escape }}', '{{ user.username|escape }}', {{ user.balance }}, {{ user.verified }}, {{ user.device_verified }}, '{{ user.refer_code }}', {{ user.refer_count }})">
                    <div style="flex: 1;">
                        <div class="user-id">{{ user.id }}</div>
                        <div class="user-name">
                            {{ user.name }}
                            {% if user.username %}
                            <span style="color: #888; font-size: 11px;">(@{{ user.username }})</span>
                            {% endif %}
                        </div>
                        <div style="display: flex; gap: 15px; margin-top: 5px;">
                            <div>
                                <div style="font-size: 11px; color: #888;">Refer Code</div>
                                <div style="font-family: monospace; font-size: 12px;">{{ user.refer_code }}</div>
                                <div style="font-size: 10px; color: #666;">{{ user.refer_count }} refers</div>
                            </div>
                        </div>
                    </div>
                    <div style="text-align: right;">
                        <div class="user-balance">₹{{ "%.2f"|format(user.balance) }}</div>
                        <div class="user-status {% if user.verified and user.device_verified %}status-verified{% else %}status-pending{% endif %}">
                            {% if user.verified and user.device_verified %}✅ Verified{% else %}⏳ Pending{% endif %}
                        </div>
                        <div style="font-size: 10px; color: #666; margin-top: 5px;">
                            {{ user.joined_date[:10] if user.joined_date else 'N/A' }}
                        </div>
                    </div>
                </div>
                {% endfor %}
            </div>
        </div>
    </div>
    
    <div id="sets" class="tab">
        <div class="config-options">
            <div class="config-option">
                <h3>Basic Settings</h3>
                <label>Bot Name</label><input id="bName" value="{{ settings.bot_name }}">
                <label>App Display Name</label><input id="appName" value="{{ settings.app_name }}">
                <label>Min Withdraw (₹)</label><input type="number" id="minW" value="{{ settings.min_withdrawal }}">
                <label>Welcome Bonus (₹)</label><input type="number" id="bonus" value="{{ settings.welcome_bonus }}">
                <label>Min Refer Reward (₹)</label><input type="number" id="minRef" value="{{ settings.min_refer_reward }}">
                <label>Max Refer Reward (₹)</label><input type="number" id="maxRef" value="{{ settings.max_refer_reward }}">
            </div>
            
            <div class="config-option">
                <h3>Verification Settings</h3>
                <div class="toggle-label">
                    <span>Disable Channel Verification:</span>
                    <label class="toggle-switch">
                        <input type="checkbox" id="disable_channel_verification" {{ 'checked' if settings.disable_channel_verification else '' }}>
                        <span class="toggle-slider"></span>
                    </label>
                </div>
                <div class="toggle-label">
                    <span>Auto Accept Private Channels:</span>
                    <label class="toggle-switch">
                        <input type="checkbox" id="auto_accept_private" {{ 'checked' if settings.auto_accept_private else '' }}>
                        <span class="toggle-slider"></span>
                    </label>
                </div>
                <div class="toggle-label">
                    <span>Hide Verify Button in App:</span>
                    <label class="toggle-switch">
                        <input type="checkbox" id="hide_verify_button" {{ 'checked' if settings.hide_verify_button else '' }}>
                        <span class="toggle-slider"></span>
                    </label>
                </div>
                <div class="toggle-label">
                    <span>Disable Bot for Users:</span>
                    <label class="toggle-switch">
                        <input type="checkbox" id="dis" {{ 'checked' if settings.bots_disabled else '' }}>
                        <span class="toggle-slider"></span>
                    </label>
                </div>
                <div class="toggle-label">
                    <span>Auto-Withdraw (Instant Payment):</span>
                    <label class="toggle-switch">
                        <input type="checkbox" id="auto" {{ 'checked' if settings.auto_withdraw else '' }}>
                        <span class="toggle-slider"></span>
                    </label>
                </div>
                <div class="toggle-label">
                    <span>Allow Same Device Multiple Accounts:</span>
                    <label class="toggle-switch">
                        <input type="checkbox" id="idevice" {{ 'checked' if settings.ignore_device_check else '' }}>
                        <span class="toggle-slider"></span>
                    </label>
                </div>
                <div class="toggle-label">
                    <span>Disable Withdrawals:</span>
                    <label class="toggle-switch">
                        <input type="checkbox" id="withdraw_disabled" {{ 'checked' if settings.withdraw_disabled else '' }}>
                        <span class="toggle-slider"></span>
                    </label>
                </div>
            </div>
        </div>
        <button class="btn" onclick="saveBasic()">Save Settings</button>
        
        <div class="card">
            <h3>Upload Logo</h3>
            <input type="file" id="logoFile" accept="image/*">
            <button class="btn" onclick="upLogo()">Upload Logo</button>
            <p style="font-size:12px; color:#888; margin-top:10px;">Current: {{ settings.logo_filename }}</p>
        </div>
    </div>
    
    <div id="chans" class="tab">
        <div class="card">
            <h3>Add Channel</h3>
            <input id="cName" placeholder="Channel Name (e.g. News Channel)">
            <input id="cLink" placeholder="Channel Link (https://t.me/...)">
            <input id="cId" placeholder="Channel ID (e.g. @channelusername or -1001234567890)">
            <button class="btn" onclick="addChan()">Add Channel</button>
            <p style="font-size:12px; color:#888; margin-top:10px;">Users must join these channels to verify</p>
        </div>
        <div class="card">
            <h3>Current Channels</h3>
            <table>
                {% for ch in settings.channels %}
                <tr>
                    <td>
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <button class="btn-icon channel-toggle {{ 'channel-disabled' if ch.disabled else '' }}" onclick="toggleChannel({{ loop.index0 }})" title="{{ 'Enable verification' if ch.disabled else 'Disable verification' }}">
                                {{ '✓' if not ch.disabled else '✗' }}
                            </button>
                            <div>
                                <div style="font-weight: bold;">{{ ch.btn_name }}</div>
                                <div class="channel-details">
                                    <div>Link: <a href="{{ ch.link }}" target="_blank" style="color: #007bff;">{{ ch.link[:30] }}...</a></div>
                                    <div class="channel-id">ID: {{ ch.id }}</div>
                                    <div style="color: {{ '#28a745' if not ch.disabled else '#ff9800' }}; font-size: 10px;">
                                        {{ 'Verification Enabled' if not ch.disabled else 'Verification Disabled' }}
                                    </div>
                                </div>
                            </div>
                        </div>
                    </td>
                    <td><button class="btn-del" onclick="delChan({{ loop.index0 }})">Delete</button></td>
                </tr>
                {% else %}
                <tr><td colspan="2" style="text-align:center; color:#888; padding:20px;">No channels added</td></tr>
                {% endfor %}
            </table>
        </div>
    </div>
    
    <div id="admins" class="tab">
        <div class="card">
            <h3>Add Admin</h3>
            <input id="newAdmin" placeholder="Telegram User ID (e.g. 1234567890)">
            <button class="btn" onclick="addAdmin()">Add Admin</button>
            <p style="font-size:12px; color:#888; margin-top:10px;">Main Admin ID: {{ ADMIN_ID }}</p>
        </div>
        <div class="card">
            <h3>Current Admins</h3>
            <table>
                {% for adm in settings.admins %}
                <tr>
                    <td>{{ adm }}</td>
                    <td><button class="btn-del" onclick="remAdmin('{{ adm }}')">Remove</button></td>
                </tr>
                {% else %}
                <tr><td colspan="2" style="text-align:center; color:#888; padding:20px;">No additional admins</td></tr>
                {% endfor %}
            </table>
        </div>
    </div>
    
    <div id="gifts" class="tab">
        <div class="card">
            <h3>Create Gift Code</h3>
            <div style="display:flex; align-items:center; margin:10px 0;">
                <input id="giftCode" placeholder="Enter 5-character code" maxlength="5" style="text-transform:uppercase; flex:1;">
                <button class="gen-btn" onclick="generateCode()">GENERATE</button>
            </div>
            <label>Min Amount (₹)</label><input type="number" id="giftMin" value="10" step="0.01">
            <label>Max Amount (₹)</label><input type="number" id="giftMax" value="50" step="0.01">
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
                        {% set expiry_time = gift.expiry|fromisoformat %}
                        {% set remaining = (expiry_time - now).total_seconds() / 60 %}
                        Expires in: {{ remaining|int }} mins
                        {% endif %}
                    </div>
                </div>
                <div style="text-align:center;">
                    <div class="usage">{{ gift.used_by|length }}/{{ gift.total_uses }} uses</div>
                    <div style="font-size:11px; color:{% if gift.used_by|length >= gift.total_uses %}#f44{% else %}#0f0{% endif %};">₹{{ gift.min_amount }} - ₹{{ gift.max_amount }}</div>
                </div>
                <div>
                    <button class="btn-icon" style="background:#ff9800;" onclick="toggleGift('{{ gift.code }}')" title="Toggle Active">
                        {% if gift.is_active %}⏸{% else %}▶{% endif %}
                    </button>
                    <button class="btn-icon cross" onclick="deleteGift('{{ gift.code }}')" title="Delete">✘</button>
                </div>
            </div>
            {% else %}
            <div style="text-align:center; color:#888; padding:20px;">No gift codes created</div>
            {% endfor %}
        </div>
    </div>
    
    <div id="bc" class="tab">
        <div class="card">
            <h3>Broadcast Message</h3>
            <textarea id="bcMsg" placeholder="Enter message to send to all users" rows="5"></textarea>
            <input type="file" id="bcFile" accept="image/*">
            <button class="btn" onclick="sendBC()">Broadcast to All Users</button>
            <p style="font-size:12px; color:#888; margin-top:10px;">This will send to {{ stats.total_users }} users</p>
        </div>
    </div>
    
    <script>
        let curTx = '';
        let selectedUserId = '';
        
        function showAdminLoader(text = 'Processing...') {
            document.getElementById('adminLoaderText').textContent = text;
            document.getElementById('adminLoader').style.display = 'flex';
        }
        
        function hideAdminLoader() {
            document.getElementById('adminLoader').style.display = 'none';
        }
        
        function tab(n) {
            document.querySelectorAll('.tab').forEach(e => e.classList.remove('active'));
            document.getElementById(n).classList.add('active');
            document.querySelectorAll('.nav button').forEach(e => e.classList.remove('active'));
            event.target.classList.add('active');
        }
        
        function openUserMessage(userId, userName, username, balance, verified, deviceVerified, referCode, referCount) {
            selectedUserId = userId;
            const userInfo = document.getElementById('sendToUserInfo');
            userInfo.innerHTML = `
                <div><strong>User ID:</strong> ${userId}</div>
                <div><strong>Name:</strong> ${userName} ${username ? '(@' + username + ')' : ''}</div>
                <div><strong>Balance:</strong> ₹${balance.toFixed(2)}</div>
                <div><strong>Status:</strong> ${verified && deviceVerified ? '✅ Verified' : '⏳ Pending'}</div>
                <div><strong>Refer Code:</strong> ${referCode} (${referCount} refers)</div>
            `;
            document.getElementById('userMessage').value = '';
            document.getElementById('userImage').value = '';
            document.getElementById('sendMessageModal').style.display = 'flex';
        }
        
        function sendUserMessage() {
            const message = document.getElementById('userMessage').value;
            const fileInput = document.getElementById('userImage');
            
            if (!message.trim()) {
                alert('Please enter a message');
                return;
            }
            
            showAdminLoader('Sending message...');
            
            const formData = new FormData();
            formData.append('user_id', selectedUserId);
            formData.append('text', message);
            if (fileInput.files[0]) {
                formData.append('image', fileInput.files[0]);
            }
            
            fetch('/admin/send_to_user', {
                method: 'POST',
                body: formData
            })
            .then(r => r.json())
            .then(data => {
                hideAdminLoader();
                if (data.ok) {
                    alert(data.msg);
                    document.getElementById('sendMessageModal').style.display = 'none';
                } else {
                    alert('Error: ' + data.msg);
                }
            })
            .catch(err => {
                hideAdminLoader();
                alert('Error sending message');
                console.error(err);
            });
        }
        
        function searchUsers(input) {
            const value = input.value.toLowerCase();
            const cards = document.querySelectorAll('.user-card');
            
            cards.forEach(card => {
                const text = card.textContent.toLowerCase();
                card.style.display = text.includes(value) ? '' : 'none';
            });
        }
        
        function saveBasic() {
            showAdminLoader('Saving settings...');
            const data = {
                bot_name: document.getElementById('bName').value,
                app_name: document.getElementById('appName').value,
                min_withdrawal: parseFloat(document.getElementById('minW').value),
                welcome_bonus: parseFloat(document.getElementById('bonus').value),
                min_refer_reward: parseFloat(document.getElementById('minRef').value),
                max_refer_reward: parseFloat(document.getElementById('maxRef').value),
                bots_disabled: document.getElementById('dis').checked,
                auto_withdraw: document.getElementById('auto').checked,
                ignore_device_check: document.getElementById('idevice').checked,
                withdraw_disabled: document.getElementById('withdraw_disabled').checked,
                disable_channel_verification: document.getElementById('disable_channel_verification').checked,
                auto_accept_private: document.getElementById('auto_accept_private').checked,
                hide_verify_button: document.getElementById('hide_verify_button').checked
            };
            
            fetch('/admin/update_basic', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            })
            .then(r => r.json())
            .then(data => {
                hideAdminLoader();
                if (data.ok) {
                    alert('Settings saved successfully!');
                } else {
                    alert('Error: ' + (data.msg || 'Unknown error'));
                }
            })
            .catch(err => {
                hideAdminLoader();
                alert('Error saving settings');
                console.error(err);
            });
        }
        
        function addChan() {
            showAdminLoader('Adding channel...');
            const data = {
                action: 'add',
                name: document.getElementById('cName').value,
                link: document.getElementById('cLink').value,
                id: document.getElementById('cId').value
            };
            
            if (!data.name || !data.link || !data.id) {
                hideAdminLoader();
                alert('Please fill all channel details');
                return;
            }
            
            fetch('/admin/channels', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            })
            .then(r => r.json())
            .then(data => {
                hideAdminLoader();
                if (data.ok) {
                    location.reload();
                } else {
                    alert('Error: ' + (data.msg || 'Unknown error'));
                }
            })
            .catch(err => {
                hideAdminLoader();
                alert('Error adding channel');
                console.error(err);
            });
        }
        
        function toggleChannel(index) {
            showAdminLoader('Toggling channel...');
            
            fetch('/admin/channels', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({action: 'toggle', index: index})
            })
            .then(r => r.json())
            .then(data => {
                hideAdminLoader();
                if (data.ok) {
                    location.reload();
                } else {
                    alert('Error toggling channel');
                }
            })
            .catch(err => {
                hideAdminLoader();
                alert('Error toggling channel');
                console.error(err);
            });
        }
        
        function delChan(index) {
            if (!confirm('Delete this channel?')) return;
            
            showAdminLoader('Deleting channel...');
            
            fetch('/admin/channels', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({action: 'delete', index: index})
            })
            .then(r => r.json())
            .then(data => {
                hideAdminLoader();
                if (data.ok) {
                    location.reload();
                } else {
                    alert('Error deleting channel');
                }
            })
            .catch(err => {
                hideAdminLoader();
                alert('Error deleting channel');
                console.error(err);
            });
        }
        
        function addAdmin() {
            showAdminLoader('Adding admin...');
            const adminId = document.getElementById('newAdmin').value.trim();
            if (!adminId) {
                hideAdminLoader();
                alert('Please enter Telegram User ID');
                return;
            }
            
            fetch('/admin/manage_admins', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({action: 'add', id: adminId})
            })
            .then(r => r.json())
            .then(data => {
                hideAdminLoader();
                if (data.ok) {
                    location.reload();
                } else {
                    alert('Error: ' + (data.msg || 'Unknown error'));
                }
            })
            .catch(err => {
                hideAdminLoader();
                alert('Error adding admin');
                console.error(err);
            });
        }
        
        function remAdmin(id) {
            if (!confirm('Remove this admin?')) return;
            
            showAdminLoader('Removing admin...');
            
            fetch('/admin/manage_admins', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({action: 'remove', id: id})
            })
            .then(r => r.json())
            .then(data => {
                hideAdminLoader();
                if (data.ok) {
                    location.reload();
                } else {
                    alert('Error removing admin');
                }
            })
            .catch(err => {
                hideAdminLoader();
                alert('Error removing admin');
                console.error(err);
            });
        }
        
        function openApprove(id) {
            curTx = id;
            document.getElementById('approveModal').style.display = 'flex';
            document.getElementById('utrInput').focus();
        }
        
        function confirmApprove() {
            const utr = document.getElementById('utrInput').value.trim();
            if (!utr) {
                alert('Please enter UTR number');
                return;
            }
            
            showAdminLoader('Processing payment...');
            proc(curTx, 'completed', utr);
            document.getElementById('approveModal').style.display = 'none';
            document.getElementById('utrInput').value = '';
        }
        
        function proc(txId, status, utr = '') {
            showAdminLoader(status === 'completed' ? 'Processing payment...' : 'Rejecting withdrawal...');
            fetch('/admin/process_withdraw', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({tx_id: txId, status: status, utr: utr})
            })
            .then(r => r.json())
            .then(data => {
                hideAdminLoader();
                if (data.ok) {
                    location.reload();
                } else {
                    alert('Error: ' + (data.msg || 'Unknown error'));
                }
            })
            .catch(err => {
                hideAdminLoader();
                alert('Error processing withdrawal');
                console.error(err);
            });
        }
        
        function sendBC() {
            const message = document.getElementById('bcMsg').value;
            if (!message.trim()) {
                alert('Please enter a message');
                return;
            }
            
            if (!confirm(`Send this message to {{ stats.total_users }} users?`)) return;
            
            showAdminLoader('Broadcasting message...');
            
            const formData = new FormData();
            formData.append('text', message);
            const fileInput = document.getElementById('bcFile');
            if (fileInput.files[0]) {
                formData.append('image', fileInput.files[0]);
            }
            
            fetch('/admin/broadcast', {
                method: 'POST',
                body: formData
            })
            .then(r => r.json())
            .then(data => {
                hideAdminLoader();
                if (data.ok !== false) {
                    alert(`Message sent to ${data.count || data} users!`);
                    document.getElementById('bcMsg').value = '';
                    document.getElementById('bcFile').value = '';
                } else {
                    alert('Error: ' + (data.msg || 'Unknown error'));
                }
            })
            .catch(err => {
                hideAdminLoader();
                alert('Error broadcasting message');
                console.error(err);
            });
        }
        
        function upLogo() {
            const fileInput = document.getElementById('logoFile');
            if (!fileInput.files[0]) {
                alert('Please select a logo file');
                return;
            }
            
            showAdminLoader('Uploading logo...');
            
            const formData = new FormData();
            formData.append('logo', fileInput.files[0]);
            
            fetch('/admin/upload_logo', {
                method: 'POST',
                body: formData
            })
            .then(r => r.json())
            .then(data => {
                hideAdminLoader();
                if (data.ok) {
                    alert('Logo uploaded successfully!');
                    fileInput.value = '';
                } else {
                    alert('Error: ' + (data.msg || 'Unknown error'));
                }
            })
            .catch(err => {
                hideAdminLoader();
                alert('Error uploading logo');
                console.error(err);
            });
        }
        
        function generateCode() {
            const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
            let code = '';
            for (let i = 0; i < 5; i++) {
                code += chars.charAt(Math.floor(Math.random() * chars.length));
            }
            document.getElementById('giftCode').value = code;
        }
        
        function createGift() {
            showAdminLoader('Creating gift code...');
            const code = document.getElementById('giftCode').value.toUpperCase();
            const minAmt = document.getElementById('giftMin').value;
            const maxAmt = document.getElementById('giftMax').value;
            const expiry = document.getElementById('giftExpiry').value;
            const uses = document.getElementById('giftUses').value;
            
            if (!code || code.length !== 5) {
                hideAdminLoader();
                alert('Please enter a valid 5-character code');
                return;
            }
            
            if (parseFloat(minAmt) >= parseFloat(maxAmt)) {
                hideAdminLoader();
                alert('Max amount must be greater than min amount');
                return;
            }
            
            const data = {
                auto_generate: false,
                code: code,
                min_amount: minAmt,
                max_amount: maxAmt,
                expiry_hours: expiry,
                total_uses: uses
            };
            
            fetch('/admin/create_gift?user_id={{ admin_id }}', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            })
            .then(r => r.json())
            .then(data => {
                hideAdminLoader();
                if (data.ok) {
                    alert('Gift code created: ' + data.code);
                    location.reload();
                } else {
                    alert('Error: ' + data.msg);
                }
            })
            .catch(err => {
                hideAdminLoader();
                alert('Error creating gift code');
                console.error(err);
            });
        }
        
        function toggleGift(code) {
            showAdminLoader('Toggling gift code...');
            fetch('/admin/toggle_gift', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({code: code, action: 'toggle'})
            })
            .then(r => r.json())
            .then(data => {
                hideAdminLoader();
                if (data.ok) {
                    location.reload();
                } else {
                    alert('Error: ' + (data.msg || 'Unknown error'));
                }
            })
            .catch(err => {
                hideAdminLoader();
                alert('Error toggling gift code');
                console.error(err);
            });
        }
        
        function deleteGift(code) {
            if (!confirm('Delete this gift code?')) return;
            
            showAdminLoader('Deleting gift code...');
            
            fetch('/admin/toggle_gift', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({code: code, action: 'delete'})
            })
            .then(r => r.json())
            .then(data => {
                hideAdminLoader();
                if (data.ok) {
                    location.reload();
                } else {
                    alert('Error: ' + (data.msg || 'Unknown error'));
                }
            })
            .catch(err => {
                hideAdminLoader();
                alert('Error deleting gift code');
                console.error(err);
            });
        }
        
        // Generate initial code
        generateCode();
    </script>
</body>
</html>
"""

# ==================== 10. START APP ====================
if __name__ == '__main__':
    init_default_files()
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
