# app.py - Complete Fixed Telegram Bot with UPI Integration
import os
import sys
import json
import time
import random
import string
import hashlib
import logging
import threading
import requests
import re
import urllib.parse
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify, render_template_string, send_from_directory, Response, session

# MongoDB imports
from pymongo import MongoClient
from bson import ObjectId
from pymongo.errors import ConnectionFailure

# Telegram imports
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# ==================== CONFIGURATION ====================
# Environment variables with defaults
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8280352331:AAGwEGmIKlPnFWBeFihp9mLxbgtM_qBpATc')
ADMIN_IDS = [8469993808]  # Fixed admin ID
BASE_URL = os.environ.get('BASE_URL', 'web-production-3dfc9.up.railway.app')
PORT = int(os.environ.get('PORT', 8080))

# MongoDB Configuration
MONGO_URI = os.environ.get('MONGO_URI', 'mongodb+srv://sandip:9E9AISFqTfU3VI5i@cluster0.p8irtov.mongodb.net/telegram_bot')
DB_NAME = os.environ.get('DB_NAME', 'telegram_bot')

# Directory setup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")

# Create directories
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask app setup
app = Flask(__name__, static_folder=STATIC_DIR)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Initialize bot
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

# ==================== MONGODB CONNECTION ====================
class MongoDB:
    def __init__(self):
        self.client = None
        self.db = None
        self.connected = False
        self.connect()
    
    def connect(self):
        """Connect to MongoDB"""
        try:
            self.client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
            self.db = self.client[DB_NAME]
            # Test connection
            self.client.admin.command('ping')
            self.connected = True
            logger.info("✅ MongoDB connected successfully")
            
            # Create indexes for better performance
            self.db.users.create_index('user_id', unique=True)
            self.db.users.create_index('refer_code', unique=True, sparse=True)
            self.db.withdrawals.create_index('tx_id', unique=True)
            self.db.withdrawals.create_index([('user_id', 1), ('created_at', -1)])
            self.db.settings.create_index('key', unique=True)
            
        except Exception as e:
            self.connected = False
            logger.error(f"❌ MongoDB connection failed: {e}")
            logger.warning("Using file-based storage as fallback")
    
    def get_collection(self, name):
        """Get MongoDB collection or fallback to dict"""
        if self.connected:
            return self.db[name]
        return None
    
    def is_connected(self):
        return self.connected

mongo = MongoDB()

# ==================== DATA STORAGE (MongoDB + File Fallback) ====================
class Storage:
    @staticmethod
    def get_settings():
        """Get settings from MongoDB or file"""
        if mongo.is_connected():
            settings = mongo.db.settings.find_one({'key': 'main'})
            if settings:
                # Remove MongoDB _id
                settings.pop('_id', None)
                settings.pop('key', None)
                return settings
        
        # File fallback
        settings_file = os.path.join(BASE_DIR, 'data', 'settings.json')
        if os.path.exists(settings_file):
            with open(settings_file, 'r') as f:
                return json.load(f)
        
        # Default settings
        return {
            "bot_name": "CYBER EARN ULTIMATE",
            "min_withdrawal": 100.0,
            "welcome_bonus": 50.0,
            "channels": [],
            "admins": ADMIN_IDS.copy(),
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
            "hide_verify_button": False,
            # UPI Payment Settings
            "upi_enabled": False,
            "upi_token": "0127d8b8b09c9f3c6674dd5d676a6e17",
            "upi_key": "25d33a0508f8249ebf03ee2b36cc019e",
            "upi_receiver": "",
            "upi_mode": "manual",  # auto, manual, fake
            "upi_api_url": "https://easepay.site/upiapi.php",
            "upi_balance": 0,
            "upi_min_balance_alert": 100
        }
    
    @staticmethod
    def save_settings(settings):
        """Save settings to MongoDB and file"""
        # Remove sensitive data from logs
        settings_copy = settings.copy()
        
        if mongo.is_connected():
            mongo.db.settings.update_one(
                {'key': 'main'},
                {'$set': settings_copy},
                upsert=True
            )
        
        # File backup
        os.makedirs(os.path.join(BASE_DIR, 'data'), exist_ok=True)
        with open(os.path.join(BASE_DIR, 'data', 'settings.json'), 'w') as f:
            json.dump(settings_copy, f, indent=2)
    
    @staticmethod
    def get_user(user_id):
        """Get user by ID"""
        if mongo.is_connected():
            user = mongo.db.users.find_one({'user_id': str(user_id)})
            if user:
                user.pop('_id', None)
                return user
        
        # File fallback - not implemented for production
        return None
    
    @staticmethod
    def save_user(user_data):
        """Save or update user"""
        if mongo.is_connected():
            mongo.db.users.update_one(
                {'user_id': user_data['user_id']},
                {'$set': user_data},
                upsert=True
            )
            return True
        return False
    
    @staticmethod
    def get_all_users():
        """Get all users"""
        if mongo.is_connected():
            users = list(mongo.db.users.find())
            for user in users:
                user.pop('_id', None)
            return users
        return []
    
    @staticmethod
    def create_withdrawal(withdrawal_data):
        """Create withdrawal record"""
        if mongo.is_connected():
            result = mongo.db.withdrawals.insert_one(withdrawal_data)
            return str(result.inserted_id)
        return None
    
    @staticmethod
    def update_withdrawal(tx_id, update_data):
        """Update withdrawal record"""
        if mongo.is_connected():
            mongo.db.withdrawals.update_one(
                {'tx_id': tx_id},
                {'$set': update_data}
            )
            return True
        return False
    
    @staticmethod
    def get_withdrawals(user_id=None, status=None, limit=100):
        """Get withdrawals with filters"""
        if mongo.is_connected():
            query = {}
            if user_id:
                query['user_id'] = str(user_id)
            if status:
                query['status'] = status
            
            withdrawals = list(mongo.db.withdrawals.find(query).sort('created_at', -1).limit(limit))
            for w in withdrawals:
                w.pop('_id', None)
            return withdrawals
        return []
    
    @staticmethod
    def get_pending_withdrawals():
        """Get all pending withdrawals"""
        return Storage.get_withdrawals(status='pending')
    
    @staticmethod
    def create_gift_code(gift_data):
        """Create gift code"""
        if mongo.is_connected():
            result = mongo.db.gift_codes.insert_one(gift_data)
            return str(result.inserted_id)
        return None
    
    @staticmethod
    def get_gift_code(code):
        """Get gift code by code"""
        if mongo.is_connected():
            gift = mongo.db.gift_codes.find_one({'code': code.upper()})
            if gift:
                gift.pop('_id', None)
                return gift
        return None
    
    @staticmethod
    def update_gift_code(code, update_data):
        """Update gift code"""
        if mongo.is_connected():
            mongo.db.gift_codes.update_one(
                {'code': code.upper()},
                {'$set': update_data}
            )
            return True
        return False
    
    @staticmethod
    def get_all_gift_codes():
        """Get all gift codes"""
        if mongo.is_connected():
            gifts = list(mongo.db.gift_codes.find().sort('created_at', -1))
            for g in gifts:
                g.pop('_id', None)
            return gifts
        return []

# ==================== UPI PAYMENT INTEGRATION ====================
class UPIPayment:
    @staticmethod
    def send_payment(upi_id, amount, comment=""):
        """Send UPI payment using API"""
        settings = Storage.get_settings()
        
        # Check if UPI is enabled
        if not settings.get('upi_enabled', False):
            return {
                'status': 'error',
                'message': 'UPI payments are currently disabled'
            }
        
        # Check payment mode
        mode = settings.get('upi_mode', 'manual')
        
        if mode == 'fake':
            # Fake payment for testing
            return {
                'status': 'success',
                'message': 'Fake payment processed successfully',
                'txn_id': f"FAKE{random.randint(10000000, 99999999)}",
                'amount_sent': amount,
                'mode': 'fake'
            }
        
        elif mode == 'manual':
            # Manual payment - just record and notify admin
            return {
                'status': 'pending',
                'message': 'Payment request sent to admin',
                'mode': 'manual'
            }
        
        elif mode == 'auto':
            # Auto payment via API
            try:
                url = settings.get('upi_api_url', 'https://easepay.site/upiapi.php')
                payload = {
                    "token": settings.get('upi_token', ''),
                    "key": settings.get('upi_key', ''),
                    "upiid": upi_id,
                    "amount": str(amount)
                }
                
                response = requests.post(url, data=payload, timeout=10)
                data = response.json()
                
                if data.get('status') == 'success':
                    return {
                        'status': 'success',
                        'message': data.get('message', 'Payment successful'),
                        'txn_id': data.get('txn_id', ''),
                        'amount_sent': data.get('amount_sent', amount),
                        'total_deducted': data.get('total_deducted', amount),
                        'remaining_balance': data.get('remaining_balance', 0)
                    }
                else:
                    return {
                        'status': 'error',
                        'message': data.get('message', 'Payment failed')
                    }
            
            except requests.exceptions.Timeout:
                return {
                    'status': 'error',
                    'message': 'Payment gateway timeout'
                }
            except Exception as e:
                logger.error(f"UPI payment error: {e}")
                return {
                    'status': 'error',
                    'message': f'Payment error: {str(e)}'
                }
        
        return {
            'status': 'error',
            'message': 'Invalid payment mode'
        }
    
    @staticmethod
    def check_balance():
        """Check UPI wallet balance"""
        settings = Storage.get_settings()
        
        if settings.get('upi_mode') != 'auto':
            return {'balance': 0, 'status': 'manual'}
        
        try:
            # Using the balance check endpoint (you may need to adjust this)
            url = "https://easepay.site/balance.php"
            payload = {
                "token": settings.get('upi_token', ''),
                "key": settings.get('upi_key', '')
            }
            
            response = requests.post(url, data=payload, timeout=10)
            data = response.json()
            
            if data.get('status') == 'success':
                balance = float(data.get('balance', 0))
                # Update settings with balance
                settings['upi_balance'] = balance
                Storage.save_settings(settings)
                return {'balance': balance, 'status': 'success'}
            
            return {'balance': 0, 'status': 'error', 'message': data.get('message', 'Unknown error')}
        
        except Exception as e:
            logger.error(f"Balance check error: {e}")
            return {'balance': 0, 'status': 'error', 'message': str(e)}

# ==================== UTILITY FUNCTIONS ====================
def generate_code(length=5):
    """Generate random code"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def generate_refer_code():
    """Generate unique referral code"""
    return generate_code(7)

def generate_tx_id():
    """Generate transaction ID"""
    return f"TXN{int(time.time())}{random.randint(1000, 9999)}"

def is_admin(user_id):
    """Check if user is admin"""
    return str(user_id) in [str(admin_id) for admin_id in ADMIN_IDS]

def get_user_full_name(user):
    """Get user's full name safely"""
    name_parts = []
    if user.first_name:
        name_parts.append(user.first_name)
    if user.last_name:
        name_parts.append(user.last_name)
    return " ".join(name_parts) if name_parts else "User"

def safe_send_message(chat_id, text, reply_markup=None, parse_mode="Markdown"):
    """Safely send message with error handling"""
    try:
        bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Send message error to {chat_id}: {e}")

def generate_device_fingerprint(ip, user_agent, extra=""):
    """Generate device fingerprint"""
    data = f"{ip}|{user_agent}|{extra}|{datetime.now().strftime('%Y%m%d')}"
    return hashlib.sha256(data.encode()).hexdigest()

# ==================== BOT HANDLERS ====================
@bot.message_handler(commands=['start'])
def handle_start(message):
    """Handle /start command"""
    try:
        user_id = str(message.from_user.id)
        settings = Storage.get_settings()
        
        # Check if bot is disabled
        if settings.get('bots_disabled') and not is_admin(user_id):
            safe_send_message(message.chat.id, "⛔ Bot is currently under maintenance. Please try again later.")
            return
        
        # Get referral code from start parameter
        refer_code = None
        if len(message.text.split()) > 1:
            refer_code = message.text.split()[1]
        
        # Check if user exists
        user = Storage.get_user(user_id)
        is_new = user is None
        
        if is_new:
            # Create new user
            refer_code_to_use = generate_refer_code()
            # Ensure unique refer code
            while True:
                existing_users = Storage.get_all_users()
                existing_codes = [u.get('refer_code') for u in existing_users if u.get('refer_code')]
                if refer_code_to_use not in existing_codes:
                    break
                refer_code_to_use = generate_refer_code()
            
            user_data = {
                "user_id": user_id,
                "balance": 0.0,
                "verified": False,
                "name": get_user_full_name(message.from_user),
                "username": message.from_user.username,
                "joined_date": datetime.now().isoformat(),
                "ip": None,
                "device_id": None,
                "device_verified": False,
                "refer_code": refer_code_to_use,
                "referred_by": refer_code if refer_code else None,
                "referred_users": [],
                "claimed_gifts": [],
                "last_channel_check": None,
                "total_withdrawn": 0.0,
                "last_active": datetime.now().isoformat()
            }
            Storage.save_user(user_data)
            
            # Notify admins
            admin_msg = f"🔔 *New User*\nName: {user_data['name']}\nID: `{user_id}`"
            if message.from_user.username:
                admin_msg += f"\nUsername: @{message.from_user.username}"
            if refer_code:
                admin_msg += f"\nReferred by: `{refer_code}`"
            
            for admin_id in ADMIN_IDS:
                safe_send_message(admin_id, admin_msg)
        
        else:
            # Update last active
            user['last_active'] = datetime.now().isoformat()
            Storage.save_user(user)
        
        # Create welcome message with buttons
        display_name = user.get('name', 'User') if not is_new else get_user_full_name(message.from_user)
        
        # Create inline keyboard
        markup = InlineKeyboardMarkup(row_width=1)
        
        # Add channel buttons
        for ch in settings.get('channels', []):
            if not ch.get('disabled', False):
                markup.add(InlineKeyboardButton(
                    ch.get('btn_name', 'Channel'), 
                    url=ch.get('link', '#')
                ))
        
        # Add verify button (if not hidden)
        if not settings.get('hide_verify_button', False):
            web_app_url = f"https://{BASE_URL}/mini_app?user_id={user_id}&t={int(time.time())}"
            markup.add(InlineKeyboardButton(
                "🚀 OPEN EARNING APP", 
                web_app=WebAppInfo(url=web_app_url)
            ))
        
        # Admin panel button
        if is_admin(user_id):
            markup.add(InlineKeyboardButton(
                "⚙️ ADMIN PANEL", 
                url=f"https://{BASE_URL}/admin_panel?user_id={user_id}&t={int(time.time())}"
            ))
        
        welcome_text = f"""🎉 *WELCOME {display_name}!* 🎉

🚀 *Start Earning Money Today!*

💰 Get ₹{settings.get('welcome_bonus', 50)} welcome bonus
👥 Earn up to ₹{settings.get('max_refer_reward', 50)} per referral
💸 Instant withdrawals via UPI
🎁 Daily gift codes

👇 *Complete these steps:*
1️⃣ Join all channels below
2️⃣ Click the OPEN EARNING APP button
3️⃣ Complete verification
4️⃣ Start earning!"""

        # Try to send with logo
        try:
            logo_url = f"https://{BASE_URL}/static/{settings.get('logo_filename', 'logo_default.png')}"
            bot.send_photo(
                message.chat.id,
                logo_url,
                caption=welcome_text,
                parse_mode="Markdown",
                reply_markup=markup
            )
        except Exception as e:
            logger.error(f"Photo send error: {e}")
            # Fallback to text only
            safe_send_message(message.chat.id, welcome_text, reply_markup=markup)
    
    except Exception as e:
        logger.error(f"Start handler error: {e}")
        safe_send_message(message.chat.id, "An error occurred. Please try again later.")

@bot.message_handler(commands=['balance'])
def handle_balance(message):
    """Check balance command"""
    try:
        user_id = str(message.from_user.id)
        user = Storage.get_user(user_id)
        
        if user:
            balance = float(user.get('balance', 0))
            safe_send_message(
                message.chat.id,
                f"💰 *Your Balance*\n\nCurrent Balance: ₹{balance:.2f}\nTotal Withdrawn: ₹{float(user.get('total_withdrawn', 0)):.2f}",
                parse_mode="Markdown"
            )
        else:
            safe_send_message(message.chat.id, "Please start the bot first with /start")
    
    except Exception as e:
        logger.error(f"Balance command error: {e}")

@bot.message_handler(commands=['refer'])
def handle_refer(message):
    """Get referral link"""
    try:
        user_id = str(message.from_user.id)
        user = Storage.get_user(user_id)
        
        if user:
            refer_code = user.get('refer_code')
            if not refer_code:
                refer_code = generate_refer_code()
                user['refer_code'] = refer_code
                Storage.save_user(user)
            
            bot_username = bot.get_me().username
            refer_link = f"https://t.me/{bot_username}?start={refer_code}"
            
            referred_count = len(user.get('referred_users', []))
            
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("📋 Copy Referral Link", url=refer_link))
            markup.add(InlineKeyboardButton("👥 My Referrals", web_app=WebAppInfo(url=f"https://{BASE_URL}/mini_app?user_id={user_id}&tab=refer")))
            
            safe_send_message(
                message.chat.id,
                f"👥 *Your Referral Info*\n\n"
                f"📌 Your Code: `{refer_code}`\n"
                f"🔗 Your Link: {refer_link}\n\n"
                f"👤 Total Referrals: {referred_count}\n"
                f"💰 Earn up to ₹{Storage.get_settings().get('max_refer_reward', 50)} per referral!",
                reply_markup=markup
            )
        else:
            safe_send_message(message.chat.id, "Please start the bot first with /start")
    
    except Exception as e:
        logger.error(f"Refer command error: {e}")

@bot.chat_join_request_handler()
def handle_join_request(message):
    """Auto-approve join requests for private channels"""
    try:
        settings = Storage.get_settings()
        if settings.get('auto_accept_private', False):
            bot.approve_chat_join_request(message.chat.id, message.from_user.id)
            logger.info(f"Auto-approved join request for user {message.from_user.id}")
    except Exception as e:
        logger.error(f"Join request error: {e}")

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    """Handle callback queries from inline buttons"""
    try:
        data = call.data
        
        if data.startswith('approve_'):
            tx_id = data.replace('approve_', '')
            
            # Ask for UTR
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("📝 Enter UTR", callback_data=f"utr_{tx_id}"))
            markup.add(InlineKeyboardButton("❌ Cancel", callback_data=f"cancel"))
            
            bot.edit_message_text(
                f"Please enter UTR for transaction {tx_id}:",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )
        
        elif data.startswith('reject_'):
            tx_id = data.replace('reject_', '')
            
            # Process rejection
            result = admin_process_withdrawal_internal(tx_id, 'reject')
            
            if result['ok']:
                bot.edit_message_text(
                    f"✅ Transaction {tx_id} has been rejected and amount refunded.",
                    call.message.chat.id,
                    call.message.message_id
                )
            else:
                bot.edit_message_text(
                    f"❌ Error: {result['msg']}",
                    call.message.chat.id,
                    call.message.message_id
                )
        
        elif data.startswith('utr_'):
            tx_id = data.replace('utr_', '')
            
            # Ask user to send UTR as message
            bot.edit_message_text(
                f"Please reply to this message with the UTR for {tx_id}:",
                call.message.chat.id,
                call.message.message_id
            )
        
        elif data == 'cancel':
            bot.edit_message_text(
                "Action cancelled.",
                call.message.chat.id,
                call.message.message_id
            )
    
    except Exception as e:
        logger.error(f"Callback error: {e}")

# Helper function for internal withdrawal processing
def admin_process_withdrawal_internal(tx_id, action, utr=''):
    """Internal function to process withdrawal"""
    try:
        withdrawals = Storage.get_withdrawals()
        target_withdrawal = None
        
        for w in withdrawals:
            if w.get('tx_id') == tx_id:
                target_withdrawal = w
                break
        
        if not target_withdrawal:
            return {'ok': False, 'msg': 'Withdrawal not found'}
        
        if action == 'approve':
            # Update withdrawal status
            target_withdrawal['status'] = 'completed'
            target_withdrawal['utr'] = utr
            target_withdrawal['completed_at'] = datetime.now().isoformat()
            
            # Update in database
            Storage.update_withdrawal(tx_id, {
                'status': 'completed',
                'utr': utr,
                'completed_at': datetime.now().isoformat()
            })
            
            # Update user's total withdrawn
            user = Storage.get_user(target_withdrawal['user_id'])
            if user:
                user['total_withdrawn'] = float(user.get('total_withdrawn', 0)) + float(target_withdrawal['amount'])
                Storage.save_user(user)
            
            # Notify user
            safe_send_message(
                target_withdrawal['user_id'],
                f"✅ *Withdrawal Approved!*\n\nAmount: ₹{target_withdrawal['amount']}\nUTR: `{utr}`\nTxID: `{tx_id}`"
            )
            
            return {'ok': True}
        
        elif action == 'reject':
            # Refund amount to user
            user = Storage.get_user(target_withdrawal['user_id'])
            if user:
                user['balance'] = float(user.get('balance', 0)) + float(target_withdrawal['amount'])
                Storage.save_user(user)
            
            # Update withdrawal status
            target_withdrawal['status'] = 'rejected'
            target_withdrawal['rejected_at'] = datetime.now().isoformat()
            
            Storage.update_withdrawal(tx_id, {
                'status': 'rejected',
                'rejected_at': datetime.now().isoformat()
            })
            
            # Notify user
            safe_send_message(
                target_withdrawal['user_id'],
                f"❌ *Withdrawal Rejected*\n\nAmount: ₹{target_withdrawal['amount']} has been refunded to your balance.\nTxID: `{tx_id}`"
            )
            
            return {'ok': True}
        
        return {'ok': False, 'msg': 'Invalid action'}
    
    except Exception as e:
        logger.error(f"Process withdrawal internal error: {e}")
        return {'ok': False, 'msg': str(e)}

# ==================== FLASK ROUTES ====================
@app.route('/')
def home():
    """Home route"""
    bot_username = "bot"
    try:
        bot_username = bot.get_me().username
    except:
        pass
    
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Bot Status</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; color: white; text-align: center; }
            .card { background: rgba(255,255,255,0.1); backdrop-filter: blur(10px); padding: 40px; border-radius: 20px; box-shadow: 0 8px 32px rgba(0,0,0,0.1); }
            h1 { font-size: 2.5em; margin-bottom: 10px; }
            .status { display: inline-block; padding: 8px 20px; background: rgba(0,255,0,0.2); border-radius: 50px; margin: 20px 0; }
            .btn { display: inline-block; padding: 12px 30px; background: white; color: #764ba2; text-decoration: none; border-radius: 50px; font-weight: bold; margin-top: 20px; }
            .btn:hover { transform: translateY(-2px); box-shadow: 0 5px 20px rgba(0,0,0,0.2); }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>🚀 Telegram Bot</h1>
            <div class="status">✅ Bot is running</div>
            <p>MongoDB: {{ '✅ Connected' if mongo_connected else '❌ Using file storage' }}</p>
            <p>Total Users: {{ user_count }}</p>
            <a href="https://t.me/{{ bot_username }}" class="btn">Open in Telegram</a>
        </div>
    </body>
    </html>
    """, mongo_connected=mongo.is_connected(), user_count=len(Storage.get_all_users()), bot_username=bot_username)

@app.route('/mini_app')
def mini_app():
    """Main mini app interface"""
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return "User ID required", 400
        
        user = Storage.get_user(user_id)
        if not user:
            return "User not found", 404
        
        settings = Storage.get_settings()
        
        # Check verification status
        user_status = "pending"
        if user.get('verified'):
            needs_device = not settings.get('ignore_device_check', False)
            device_ok = user.get('device_verified', False) or not needs_device
            
            channels_ok = True
            if settings.get('channels') and not settings.get('disable_channel_verification', False):
                last_check = user.get('last_channel_check')
                if last_check:
                    try:
                        last_check_time = datetime.fromisoformat(last_check)
                        if (datetime.now() - last_check_time).total_seconds() < 300:
                            channels_ok = True
                        else:
                            channels_ok = False
                    except:
                        channels_ok = False
                else:
                    channels_ok = False
            
            user_status = "verified" if device_ok and channels_ok else "pending"
        
        # Get leaderboard
        all_users = Storage.get_all_users()
        leaderboard = []
        for u in all_users:
            leaderboard.append({
                "user_id": u.get('user_id'),
                "name": u.get('name', 'User'),
                "balance": float(u.get('balance', 0)),
                "total_refers": len(u.get('referred_users', []))
            })
        leaderboard.sort(key=lambda x: x['balance'], reverse=True)
        leaderboard = leaderboard[:20]
        
        # Get recent withdrawals
        recent_withdrawals = Storage.get_withdrawals(user_id=user_id, limit=10)
        
        return render_template_string(MINI_APP_TEMPLATE,
            user=user,
            user_id=user_id,
            settings=settings,
            base_url=BASE_URL,
            leaderboard=leaderboard,
            withdrawals=recent_withdrawals,
            user_status=user_status,
            timestamp=int(time.time()),
            now=datetime.now().isoformat()
        )
    
    except Exception as e:
        logger.error(f"Mini app error: {e}")
        return f"Error: {str(e)}", 500

@app.route('/api/verify', methods=['POST'])
def api_verify():
    """Verify user membership and device"""
    try:
        data = request.json
        user_id = str(data.get('user_id'))
        fingerprint = data.get('fp', '')
        user_agent = request.headers.get('User-Agent', '')
        client_ip = request.remote_addr
        
        if not user_id:
            return jsonify({'ok': False, 'msg': 'User ID required'})
        
        user = Storage.get_user(user_id)
        if not user:
            return jsonify({'ok': False, 'msg': 'User not found'})
        
        settings = Storage.get_settings()
        
        verification_steps = []
        channel_errors = []
        
        # Device verification
        needs_device = not settings.get('ignore_device_check', False)
        if needs_device:
            device_fp = generate_device_fingerprint(client_ip, user_agent, fingerprint)
            
            # Check for duplicate devices
            all_users = Storage.get_all_users()
            for other_user in all_users:
                if other_user.get('user_id') != user_id and other_user.get('device_id') == device_fp:
                    if other_user.get('device_verified'):
                        return jsonify({
                            'ok': False,
                            'msg': '⚠️ This device is already registered with another account',
                            'type': 'device',
                            'retry': True
                        })
            
            user['device_id'] = device_fp
            user['device_verified'] = True
            verification_steps.append({"step": "device", "status": "passed", "message": "✅ Device verified"})
        
        # Channel verification
        if settings.get('channels') and not settings.get('disable_channel_verification', False):
            for idx, channel in enumerate(settings['channels']):
                if channel.get('disabled'):
                    continue
                
                channel_name = channel.get('btn_name', f'Channel {idx+1}')
                channel_id = channel.get('id', '')
                
                try:
                    if channel_id:
                        # Clean channel ID
                        channel_id = channel_id.strip()
                        if channel_id.startswith('@'):
                            channel_id = channel_id[1:]
                        
                        member = bot.get_chat_member(f"@{channel_id}", user_id)
                        if member.status not in ['member', 'administrator', 'creator', 'restricted']:
                            channel_errors.append(channel_name)
                except Exception as e:
                    logger.error(f"Channel check error for {channel_id}: {e}")
                    channel_errors.append(channel_name)
        
        if channel_errors:
            return jsonify({
                'ok': False,
                'msg': f"Please join: {', '.join(channel_errors)}",
                'type': 'channels',
                'steps': verification_steps,
                'retry': True
            })
        
        # Update verification status
        was_verified = user.get('verified', False)
        user['verified'] = True
        user['last_channel_check'] = datetime.now().isoformat()
        
        # Give welcome bonus if first time
        bonus = 0
        if not was_verified:
            try:
                bonus = float(settings.get('welcome_bonus', 50))
                user['balance'] = float(user.get('balance', 0)) + bonus
                
                # Create transaction record
                tx_id = generate_tx_id()
                withdrawal_data = {
                    "tx_id": tx_id,
                    "user_id": user_id,
                    "name": "Welcome Bonus",
                    "amount": bonus,
                    "status": "completed",
                    "type": "bonus",
                    "created_at": datetime.now().isoformat()
                }
                Storage.create_withdrawal(withdrawal_data)
                
                verification_steps.append({"step": "bonus", "status": "passed", "message": f"✨ ₹{bonus} bonus added"})
                
                # Handle referral bonus
                if user.get('referred_by'):
                    refer_code = user['referred_by']
                    all_users = Storage.get_all_users()
                    for referrer in all_users:
                        if referrer.get('refer_code') == refer_code:
                            if user_id not in referrer.get('referred_users', []):
                                # Calculate random reward
                                min_reward = float(settings.get('min_refer_reward', 10))
                                max_reward = float(settings.get('max_refer_reward', 50))
                                reward = round(random.uniform(min_reward, max_reward), 2)
                                
                                referrer['balance'] = float(referrer.get('balance', 0)) + reward
                                referrer.setdefault('referred_users', []).append(user_id)
                                Storage.save_user(referrer)
                                
                                # Create referral bonus record
                                ref_tx_id = generate_tx_id()
                                ref_data = {
                                    "tx_id": ref_tx_id,
                                    "user_id": referrer['user_id'],
                                    "name": "Referral Bonus",
                                    "amount": reward,
                                    "status": "completed",
                                    "type": "referral",
                                    "referred_user": user_id,
                                    "created_at": datetime.now().isoformat()
                                }
                                Storage.create_withdrawal(ref_data)
                                
                                # Notify referrer
                                safe_send_message(
                                    referrer['user_id'],
                                    f"🎉 *Referral Bonus!*\nYou earned ₹{reward} from {user['name']}'s verification!"
                                )
                            break
            except Exception as e:
                logger.error(f"Bonus error: {e}")
        
        Storage.save_user(user)
        
        return jsonify({
            'ok': True,
            'bonus': bonus,
            'balance': user['balance'],
            'verified': True,
            'device_verified': user.get('device_verified', False),
            'steps': verification_steps
        })
    
    except Exception as e:
        logger.error(f"Verify API error: {e}")
        return jsonify({'ok': False, 'msg': f"Error: {str(e)}"})

@app.route('/api/withdraw', methods=['POST'])
def api_withdraw():
    """Process withdrawal request"""
    try:
        data = request.json
        user_id = str(data.get('user_id'))
        amount = float(data.get('amount', 0))
        upi_id = str(data.get('upi', '')).strip()
        
        if not user_id:
            return jsonify({'ok': False, 'msg': 'User ID required'})
        
        if not upi_id or not re.match(r'^[\w\.\-_]{2,}@[\w]{2,}$', upi_id):
            return jsonify({'ok': False, 'msg': 'Invalid UPI ID format'})
        
        user = Storage.get_user(user_id)
        if not user:
            return jsonify({'ok': False, 'msg': 'User not found'})
        
        settings = Storage.get_settings()
        
        # Check if withdrawals are disabled
        if settings.get('withdraw_disabled'):
            return jsonify({'ok': False, 'msg': '❌ Withdrawals are currently disabled'})
        
        # Check minimum amount
        min_withdrawal = float(settings.get('min_withdrawal', 100))
        if amount < min_withdrawal:
            return jsonify({'ok': False, 'msg': f'Minimum withdrawal amount is ₹{min_withdrawal}'})
        
        # Check balance
        current_balance = float(user.get('balance', 0))
        if current_balance < amount:
            return jsonify({'ok': False, 'msg': 'Insufficient balance'})
        
        # Check if user is verified
        if not user.get('verified'):
            return jsonify({'ok': False, 'msg': 'Please complete verification first'})
        
        # Generate transaction ID
        tx_id = generate_tx_id()
        
        # Process based on payment mode
        payment_mode = settings.get('upi_mode', 'manual')
        
        # Deduct balance
        user['balance'] = current_balance - amount
        Storage.save_user(user)
        
        # Create withdrawal record
        withdrawal_data = {
            "tx_id": tx_id,
            "user_id": user_id,
            "name": user.get('name', 'User'),
            "amount": amount,
            "upi": upi_id,
            "status": "pending",
            "type": "withdrawal",
            "mode": payment_mode,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        # Process payment based on mode
        payment_result = None
        if payment_mode == 'auto' and settings.get('upi_enabled'):
            # Auto payment via API
            payment_result = UPIPayment.send_payment(upi_id, amount)
            
            if payment_result['status'] == 'success':
                withdrawal_data['status'] = 'completed'
                withdrawal_data['completed_at'] = datetime.now().isoformat()
                withdrawal_data['txn_id'] = payment_result.get('txn_id', '')
                withdrawal_data['utr'] = payment_result.get('txn_id', '')
                
                # Update user's total withdrawn
                user['total_withdrawn'] = float(user.get('total_withdrawn', 0)) + amount
                Storage.save_user(user)
                
                # Notify user
                safe_send_message(
                    user_id,
                    f"✅ *Withdrawal Successful!*\n\nAmount: ₹{amount}\nUTR: `{payment_result.get('txn_id', '')}`\nTxID: `{tx_id}`"
                )
                
                # Notify admins
                admin_msg = f"💰 *Auto Withdrawal Processed*\nUser: {user['name']}\nAmount: ₹{amount}\nUPI: {upi_id}\nTxn ID: {payment_result.get('txn_id', '')}"
                for admin_id in ADMIN_IDS:
                    safe_send_message(admin_id, admin_msg)
            
            elif payment_result['status'] == 'error':
                # Refund balance
                user['balance'] = current_balance
                Storage.save_user(user)
                
                withdrawal_data['status'] = 'failed'
                withdrawal_data['error'] = payment_result.get('message', 'Payment failed')
                
                return jsonify({
                    'ok': False,
                    'msg': f"Payment failed: {payment_result.get('message', 'Unknown error')}"
                })
        
        elif payment_mode == 'fake':
            # Fake payment (for testing)
            withdrawal_data['status'] = 'completed'
            withdrawal_data['completed_at'] = datetime.now().isoformat()
            withdrawal_data['txn_id'] = f"FAKE{random.randint(10000000, 99999999)}"
            withdrawal_data['utr'] = withdrawal_data['txn_id']
            
            # Update user's total withdrawn
            user['total_withdrawn'] = float(user.get('total_withdrawn', 0)) + amount
            Storage.save_user(user)
            
            # Notify user
            safe_send_message(
                user_id,
                f"✅ *Withdrawal Successful (Test Mode)!*\n\nAmount: ₹{amount}\nUTR: `{withdrawal_data['txn_id']}`\nTxID: `{tx_id}`"
            )
            
            payment_result = {'status': 'success', 'mode': 'fake'}
        
        else:
            # Manual payment - just notify admin
            admin_msg = f"""💸 *New Withdrawal Request*
            
User: {user['name']}
ID: `{user_id}`
Amount: ₹{amount}
UPI: {upi_id}
TxID: `{tx_id}`

Click below to process this withdrawal."""
            
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{tx_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{tx_id}")
            )
            
            for admin_id in ADMIN_IDS:
                safe_send_message(admin_id, admin_msg, reply_markup=markup)
            
            # Notify user
            safe_send_message(
                user_id,
                f"✅ *Withdrawal Request Submitted!*\n\nAmount: ₹{amount}\nTxID: `{tx_id}`\n\nYour request has been sent to admin. You'll be notified once processed."
            )
        
        # Save withdrawal record
        Storage.create_withdrawal(withdrawal_data)
        
        return jsonify({
            'ok': True,
            'msg': 'Withdrawal request submitted successfully',
            'tx_id': tx_id,
            'new_balance': user['balance'],
            'mode': payment_mode,
            'payment_result': payment_result
        })
    
    except Exception as e:
        logger.error(f"Withdraw API error: {e}")
        return jsonify({'ok': False, 'msg': f"Error: {str(e)}"})

@app.route('/api/check_verification')
def api_check_verification():
    """Check user verification status"""
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({'ok': False, 'msg': 'User ID required'})
        
        user = Storage.get_user(user_id)
        if not user:
            return jsonify({'ok': False, 'msg': 'User not found'})
        
        settings = Storage.get_settings()
        
        # Determine status
        if user.get('verified'):
            needs_device = not settings.get('ignore_device_check', False)
            device_ok = user.get('device_verified', False) or not needs_device
            
            channels_ok = True
            if settings.get('channels') and not settings.get('disable_channel_verification', False):
                last_check = user.get('last_channel_check')
                if last_check:
                    try:
                        last_check_time = datetime.fromisoformat(last_check)
                        if (datetime.now() - last_check_time).total_seconds() < 300:
                            channels_ok = True
                        else:
                            channels_ok = False
                    except:
                        channels_ok = False
                else:
                    channels_ok = False
            
            status = "verified" if device_ok and channels_ok else "pending"
        else:
            status = "pending"
        
        return jsonify({
            'ok': True,
            'verified': user.get('verified', False),
            'device_verified': user.get('device_verified', False),
            'balance': float(user.get('balance', 0)),
            'name': user.get('name', 'User'),
            'status': status,
            'referred_by': user.get('referred_by')
        })
    
    except Exception as e:
        logger.error(f"Check verification error: {e}")
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/api/get_balance')
def api_get_balance():
    """Get user balance"""
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({'ok': False, 'msg': 'User ID required'})
        
        user = Storage.get_user(user_id)
        if not user:
            return jsonify({'ok': False, 'msg': 'User not found'})
        
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
    """Get user transaction history"""
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify([])
        
        withdrawals = Storage.get_withdrawals(user_id=user_id, limit=20)
        return jsonify(withdrawals)
    
    except Exception as e:
        logger.error(f"History error: {e}")
        return jsonify([])

@app.route('/api/get_refer_info')
def api_get_refer_info():
    """Get referral information"""
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({'ok': False, 'msg': 'User ID required'})
        
        user = Storage.get_user(user_id)
        if not user:
            return jsonify({'ok': False, 'msg': 'User not found'})
        
        # Ensure user has refer code
        if not user.get('refer_code'):
            user['refer_code'] = generate_refer_code()
            Storage.save_user(user)
        
        refer_code = user.get('refer_code')
        
        # Get bot username
        try:
            bot_username = bot.get_me().username
        except:
            bot_username = "bot"
        
        refer_link = f"https://t.me/{bot_username}?start={refer_code}"
        
        # Get referred users details
        referred_users = user.get('referred_users', [])
        referred_details = []
        verified_count = 0
        pending_count = 0
        
        for ref_id in referred_users:
            ref_user = Storage.get_user(ref_id)
            if ref_user:
                is_verified = ref_user.get('verified', False)
                if is_verified:
                    verified_count += 1
                else:
                    pending_count += 1
                
                referred_details.append({
                    'id': ref_id,
                    'name': ref_user.get('name', 'Unknown'),
                    'username': ref_user.get('username', ''),
                    'verified': is_verified,
                    'joined': ref_user.get('joined_date', '')
                })
        
        return jsonify({
            'ok': True,
            'refer_code': refer_code,
            'refer_link': refer_link,
            'referred_users': referred_details,
            'total_refers': len(referred_users),
            'verified_refers': verified_count,
            'pending_refers': pending_count
        })
    
    except Exception as e:
        logger.error(f"Refer info error: {e}")
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/api/claim_gift', methods=['POST'])
def api_claim_gift():
    """Claim gift code"""
    try:
        data = request.json
        user_id = str(data.get('user_id'))
        code = str(data.get('code', '')).upper().strip()
        
        if not user_id:
            return jsonify({'ok': False, 'msg': 'User ID required'})
        
        if not code or len(code) != 5:
            return jsonify({'ok': False, 'msg': 'Invalid gift code'})
        
        user = Storage.get_user(user_id)
        if not user:
            return jsonify({'ok': False, 'msg': 'User not found'})
        
        gift = Storage.get_gift_code(code)
        if not gift:
            return jsonify({'ok': False, 'msg': 'Invalid gift code'})
        
        # Check if expired
        if gift.get('expired'):
            return jsonify({'ok': False, 'msg': 'Gift code has expired'})
        
        # Check if active
        if not gift.get('is_active', True):
            return jsonify({'ok': False, 'msg': 'Gift code is inactive'})
        
        # Check expiry date
        if gift.get('expiry'):
            try:
                expiry = datetime.fromisoformat(gift['expiry'])
                if expiry < datetime.now():
                    gift['expired'] = True
                    Storage.update_gift_code(code, {'expired': True})
                    return jsonify({'ok': False, 'msg': 'Gift code has expired'})
            except:
                pass
        
        # Check usage limit
        used_by = gift.get('used_by', [])
        if len(used_by) >= gift.get('total_uses', 1):
            return jsonify({'ok': False, 'msg': 'Gift code usage limit reached'})
        
        # Check if user already claimed
        if user_id in used_by:
            return jsonify({'ok': False, 'msg': 'You have already claimed this code'})
        
        # Calculate reward
        min_amount = float(gift.get('min_amount', 10))
        max_amount = float(gift.get('max_amount', 50))
        amount = round(random.uniform(min_amount, max_amount), 2)
        
        # Add to user balance
        user['balance'] = float(user.get('balance', 0)) + amount
        user.setdefault('claimed_gifts', []).append(code)
        Storage.save_user(user)
        
        # Update gift code
        used_by.append(user_id)
        Storage.update_gift_code(code, {
            'used_by': used_by,
            'last_claimed': datetime.now().isoformat()
        })
        
        # Create transaction record
        tx_id = generate_tx_id()
        withdrawal_data = {
            "tx_id": tx_id,
            "user_id": user_id,
            "name": "Gift Code Reward",
            "amount": amount,
            "status": "completed",
            "type": "gift",
            "gift_code": code,
            "created_at": datetime.now().isoformat()
        }
        Storage.create_withdrawal(withdrawal_data)
        
        return jsonify({
            'ok': True,
            'msg': f'🎉 Congratulations! You got ₹{amount}!',
            'amount': amount,
            'new_balance': user['balance']
        })
    
    except Exception as e:
        logger.error(f"Claim gift error: {e}")
        return jsonify({'ok': False, 'msg': f'Error: {str(e)}'})

@app.route('/api/leaderboard')
def api_leaderboard():
    """Get leaderboard data"""
    try:
        all_users = Storage.get_all_users()
        leaderboard = []
        
        for user in all_users:
            leaderboard.append({
                'user_id': user.get('user_id'),
                'name': user.get('name', 'User'),
                'balance': float(user.get('balance', 0)),
                'total_refers': len(user.get('referred_users', [])),
                'verified': user.get('verified', False)
            })
        
        leaderboard.sort(key=lambda x: x['balance'], reverse=True)
        
        return jsonify({
            'last_updated': datetime.now().isoformat(),
            'data': leaderboard[:20]
        })
    
    except Exception as e:
        logger.error(f"Leaderboard error: {e}")
        return jsonify({'last_updated': datetime.now().isoformat(), 'data': []})

@app.route('/api/contact', methods=['POST'])
def api_contact():
    """Contact admin"""
    try:
        user_id = request.form.get('user_id')
        message = request.form.get('message', '')
        image = request.files.get('image')
        
        if not user_id or not message:
            return jsonify({'ok': False, 'msg': 'User ID and message required'})
        
        user = Storage.get_user(user_id)
        if not user:
            return jsonify({'ok': False, 'msg': 'User not found'})
        
        # Send to all admins
        caption = f"📩 *Message from {user['name']}*\nID: `{user_id}`\n\n{message}"
        
        for admin_id in ADMIN_IDS:
            try:
                if image:
                    # Read image data
                    image_data = image.read()
                    image.seek(0)  # Reset for next admin
                    
                    # Create a new file-like object for each admin
                    from io import BytesIO
                    bio = BytesIO(image_data)
                    bio.name = image.filename
                    
                    bot.send_photo(admin_id, bio, caption=caption, parse_mode="Markdown")
                else:
                    safe_send_message(admin_id, caption)
            except Exception as e:
                logger.error(f"Send to admin {admin_id} error: {e}")
        
        return jsonify({'ok': True, 'msg': 'Message sent to admin'})
    
    except Exception as e:
        logger.error(f"Contact error: {e}")
        return jsonify({'ok': False, 'msg': str(e)})

# ==================== ADMIN API ROUTES ====================
@app.route('/admin_panel')
def admin_panel():
    """Admin panel interface"""
    try:
        user_id = request.args.get('user_id')
        if not user_id or not is_admin(user_id):
            return "Unauthorized", 403
        
        settings = Storage.get_settings()
        users = Storage.get_all_users()
        withdrawals = Storage.get_withdrawals()
        gifts = Storage.get_all_gift_codes()
        
        # Get pending withdrawals
        pending_withdrawals = [w for w in withdrawals if w.get('status') == 'pending']
        
        # Calculate stats
        total_users = len(users)
        total_balance = sum(float(u.get('balance', 0)) for u in users)
        total_withdrawn = sum(float(w.get('amount', 0)) for w in withdrawals if w.get('status') == 'completed')
        
        # Get UPI balance
        upi_balance = UPIPayment.check_balance()
        
        return render_template_string(ADMIN_TEMPLATE,
            settings=settings,
            users=users,
            withdrawals=withdrawals,
            pending_withdrawals=pending_withdrawals,
            gifts=gifts,
            stats={
                'total_users': total_users,
                'total_balance': total_balance,
                'total_withdrawn': total_withdrawn,
                'pending_count': len(pending_withdrawals)
            },
            upi_balance=upi_balance,
            admin_id=user_id,
            timestamp=int(time.time())
        )
    
    except Exception as e:
        logger.error(f"Admin panel error: {e}")
        return f"Error: {str(e)}", 500

@app.route('/admin/update_settings', methods=['POST'])
def admin_update_settings():
    """Update bot settings"""
    try:
        data = request.json
        settings = Storage.get_settings()
        
        # Update basic settings
        for key in ['bot_name', 'app_name', 'min_withdrawal', 'welcome_bonus', 
                    'min_refer_reward', 'max_refer_reward']:
            if key in data:
                settings[key] = data[key]
        
        # Update toggle settings
        for key in ['bots_disabled', 'auto_withdraw', 'ignore_device_check', 
                    'withdraw_disabled', 'disable_channel_verification', 
                    'auto_accept_private', 'hide_verify_button']:
            if key in data:
                settings[key] = bool(data[key])
        
        Storage.save_settings(settings)
        return jsonify({'ok': True})
    
    except Exception as e:
        logger.error(f"Update settings error: {e}")
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/admin/update_upi_settings', methods=['POST'])
def admin_update_upi_settings():
    """Update UPI payment settings"""
    try:
        data = request.json
        settings = Storage.get_settings()
        
        settings['upi_enabled'] = bool(data.get('upi_enabled', False))
        settings['upi_token'] = data.get('upi_token', '')
        settings['upi_key'] = data.get('upi_key', '')
        settings['upi_receiver'] = data.get('upi_receiver', '')
        settings['upi_mode'] = data.get('upi_mode', 'manual')
        settings['upi_api_url'] = data.get('upi_api_url', 'https://easepay.site/upiapi.php')
        
        Storage.save_settings(settings)
        return jsonify({'ok': True})
    
    except Exception as e:
        logger.error(f"Update UPI settings error: {e}")
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/admin/check_upi_balance')
def admin_check_upi_balance():
    """Check UPI wallet balance"""
    try:
        result = UPIPayment.check_balance()
        return jsonify(result)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/admin/channels', methods=['POST'])
def admin_channels():
    """Manage channels"""
    try:
        data = request.json
        action = data.get('action')
        settings = Storage.get_settings()
        
        if action == 'add':
            settings['channels'].append({
                'btn_name': data.get('name', 'Channel'),
                'link': data.get('link', '#'),
                'id': data.get('id', ''),
                'disabled': False
            })
        elif action == 'delete':
            index = int(data.get('index', -1))
            if 0 <= index < len(settings['channels']):
                del settings['channels'][index]
        elif action == 'toggle':
            index = int(data.get('index', -1))
            if 0 <= index < len(settings['channels']):
                settings['channels'][index]['disabled'] = not settings['channels'][index].get('disabled', False)
        
        Storage.save_settings(settings)
        return jsonify({'ok': True})
    
    except Exception as e:
        logger.error(f"Channels error: {e}")
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/admin/process_withdrawal', methods=['POST'])
def admin_process_withdrawal():
    """Process withdrawal (approve/reject)"""
    try:
        data = request.json
        tx_id = data.get('tx_id')
        action = data.get('action')  # approve, reject
        utr = data.get('utr', '')
        
        # Get all withdrawals
        withdrawals = Storage.get_withdrawals()
        target_withdrawal = None
        
        for w in withdrawals:
            if w.get('tx_id') == tx_id:
                target_withdrawal = w
                break
        
        if not target_withdrawal:
            return jsonify({'ok': False, 'msg': 'Withdrawal not found'})
        
        if action == 'approve':
            # Update withdrawal status
            target_withdrawal['status'] = 'completed'
            target_withdrawal['utr'] = utr
            target_withdrawal['completed_at'] = datetime.now().isoformat()
            
            # Update in database
            Storage.update_withdrawal(tx_id, {
                'status': 'completed',
                'utr': utr,
                'completed_at': datetime.now().isoformat()
            })
            
            # Update user's total withdrawn
            user = Storage.get_user(target_withdrawal['user_id'])
            if user:
                user['total_withdrawn'] = float(user.get('total_withdrawn', 0)) + float(target_withdrawal['amount'])
                Storage.save_user(user)
            
            # Notify user
            safe_send_message(
                target_withdrawal['user_id'],
                f"✅ *Withdrawal Approved!*\n\nAmount: ₹{target_withdrawal['amount']}\nUTR: `{utr}`\nTxID: `{tx_id}`"
            )
        
        elif action == 'reject':
            # Refund amount to user
            user = Storage.get_user(target_withdrawal['user_id'])
            if user:
                user['balance'] = float(user.get('balance', 0)) + float(target_withdrawal['amount'])
                Storage.save_user(user)
            
            # Update withdrawal status
            target_withdrawal['status'] = 'rejected'
            target_withdrawal['rejected_at'] = datetime.now().isoformat()
            
            Storage.update_withdrawal(tx_id, {
                'status': 'rejected',
                'rejected_at': datetime.now().isoformat()
            })
            
            # Notify user
            safe_send_message(
                target_withdrawal['user_id'],
                f"❌ *Withdrawal Rejected*\n\nAmount: ₹{target_withdrawal['amount']} has been refunded to your balance.\nTxID: `{tx_id}`"
            )
        
        return jsonify({'ok': True})
    
    except Exception as e:
        logger.error(f"Process withdrawal error: {e}")
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/admin/create_gift', methods=['POST'])
def admin_create_gift():
    """Create gift code"""
    try:
        data = request.json
        
        # Generate code if auto
        code = data.get('code', '').upper()
        if data.get('auto_generate') or not code:
            code = generate_code(5)
        
        # Check if code exists
        existing = Storage.get_gift_code(code)
        if existing:
            return jsonify({'ok': False, 'msg': 'Code already exists'})
        
        # Calculate expiry
        expiry_hours = int(data.get('expiry_hours', 2))
        expiry = datetime.now() + timedelta(hours=expiry_hours)
        
        gift_data = {
            'code': code,
            'min_amount': float(data.get('min_amount', 10)),
            'max_amount': float(data.get('max_amount', 50)),
            'expiry': expiry.isoformat(),
            'total_uses': int(data.get('total_uses', 1)),
            'used_by': [],
            'is_active': True,
            'expired': False,
            'created_at': datetime.now().isoformat()
        }
        
        Storage.create_gift_code(gift_data)
        
        return jsonify({'ok': True, 'code': code})
    
    except Exception as e:
        logger.error(f"Create gift error: {e}")
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/admin/toggle_gift', methods=['POST'])
def admin_toggle_gift():
    """Toggle gift code status"""
    try:
        data = request.json
        code = data.get('code')
        action = data.get('action')  # toggle, delete
        
        gift = Storage.get_gift_code(code)
        if not gift:
            return jsonify({'ok': False, 'msg': 'Gift code not found'})
        
        if action == 'toggle':
            Storage.update_gift_code(code, {'is_active': not gift.get('is_active', True)})
        elif action == 'delete':
            Storage.update_gift_code(code, {'expired': True, 'is_active': False})
        
        return jsonify({'ok': True})
    
    except Exception as e:
        logger.error(f"Toggle gift error: {e}")
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/admin/broadcast', methods=['POST'])
def admin_broadcast():
    """Broadcast message to all users"""
    try:
        message = request.form.get('message', '')
        image = request.files.get('image')
        
        if not message:
            return jsonify({'ok': False, 'msg': 'Message required'})
        
        users = Storage.get_all_users()
        sent_count = 0
        
        for user in users:
            try:
                if image:
                    # Reset file pointer for each send
                    image_data = image.read()
                    image.seek(0)
                    
                    from io import BytesIO
                    bio = BytesIO(image_data)
                    bio.name = image.filename
                    
                    bot.send_photo(user['user_id'], bio, caption=message)
                else:
                    bot.send_message(user['user_id'], message)
                sent_count += 1
            except Exception as e:
                logger.error(f"Broadcast to {user['user_id']} error: {e}")
        
        return jsonify({'ok': True, 'sent': sent_count, 'total': len(users)})
    
    except Exception as e:
        logger.error(f"Broadcast error: {e}")
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/admin/send_to_user', methods=['POST'])
def admin_send_to_user():
    """Send message to specific user"""
    try:
        target_user_id = request.form.get('user_id')
        message = request.form.get('message', '')
        image = request.files.get('image')
        
        if not target_user_id or not message:
            return jsonify({'ok': False, 'msg': 'User ID and message required'})
        
        try:
            if image:
                bot.send_photo(target_user_id, image, caption=message)
            else:
                bot.send_message(target_user_id, message)
        except Exception as e:
            return jsonify({'ok': False, 'msg': f'Failed to send: {str(e)}'})
        
        return jsonify({'ok': True})
    
    except Exception as e:
        logger.error(f"Send to user error: {e}")
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/admin/upload_logo', methods=['POST'])
def admin_upload_logo():
    """Upload bot logo"""
    try:
        if 'logo' not in request.files:
            return jsonify({'ok': False, 'msg': 'No file uploaded'})
        
        file = request.files['logo']
        if file.filename == '':
            return jsonify({'ok': False, 'msg': 'No file selected'})
        
        # Save file
        filename = f"logo_{int(time.time())}.png"
        file.save(os.path.join(STATIC_DIR, filename))
        
        # Update settings
        settings = Storage.get_settings()
        settings['logo_filename'] = filename
        Storage.save_settings(settings)
        
        return jsonify({'ok': True, 'filename': filename})
    
    except Exception as e:
        logger.error(f"Upload logo error: {e}")
        return jsonify({'ok': False, 'msg': str(e)})

# ==================== STATIC FILES ====================
@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serve static files"""
    return send_from_directory(STATIC_DIR, filename)

@app.route('/get_pfp')
def get_pfp():
    """Get user profile photo"""
    try:
        user_id = request.args.get('uid')
        if not user_id:
            return "No user ID", 400
        
        photos = bot.get_user_profile_photos(user_id)
        if photos.total_count > 0:
            file_id = photos.photos[0][-1].file_id
            file_info = bot.get_file(file_id)
            file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
            
            response = requests.get(file_url, timeout=5)
            return Response(response.content, mimetype='image/jpeg')
        
        return "No photo", 404
    
    except Exception as e:
        logger.error(f"PFP error: {e}")
        return "Error", 500

# ==================== WEBHOOK SETUP ====================
@app.route('/setup_webhook')
def setup_webhook():
    """Setup telegram webhook"""
    try:
        webhook_url = f"https://{BASE_URL}/webhook"
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(url=webhook_url)
        return f"✅ Webhook set to {webhook_url}"
    except Exception as e:
        return f"❌ Error: {str(e)}"

@app.route('/webhook', methods=['POST'])
def webhook():
    """Telegram webhook handler"""
    if request.headers.get('content-type') == 'application/json':
        try:
            json_string = request.get_data().decode('utf-8')
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return 'OK', 200
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return 'Error', 500
    return 'OK', 200

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'mongo': mongo.is_connected(),
        'bot': 'running'
    })

# ==================== HTML TEMPLATES ====================
MINI_APP_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>{{ settings.app_name }}</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }

        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            padding: 15px;
        }

        .app-container {
            max-width: 500px;
            width: 100%;
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 30px;
            padding: 20px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            position: relative;
            margin: 10px 0;
        }

        /* Loading Screen */
        .loading-screen {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            justify-content: center;
            align-items: center;
            z-index: 9999;
            transition: opacity 0.5s;
        }

        .loading-screen.hidden {
            opacity: 0;
            pointer-events: none;
        }

        .loading-content {
            text-align: center;
            color: white;
        }

        .loading-spinner {
            width: 60px;
            height: 60px;
            border: 5px solid rgba(255, 255, 255, 0.3);
            border-top-color: white;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 20px auto;
        }

        .loading-progress {
            width: 250px;
            height: 6px;
            background: rgba(255, 255, 255, 0.2);
            border-radius: 10px;
            margin: 20px auto;
            overflow: hidden;
        }

        .loading-progress-bar {
            height: 100%;
            background: white;
            width: 0%;
            transition: width 0.3s;
            border-radius: 10px;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        /* Header */
        .header {
            display: flex;
            align-items: center;
            gap: 15px;
            margin-bottom: 20px;
            padding: 10px;
            background: white;
            border-radius: 20px;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1);
        }

        .profile-pic {
            width: 60px;
            height: 60px;
            border-radius: 50%;
            object-fit: cover;
            border: 3px solid #667eea;
        }

        .profile-icon {
            width: 60px;
            height: 60px;
            border-radius: 50%;
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 30px;
        }

        .user-info {
            flex: 1;
        }

        .user-name {
            font-size: 18px;
            font-weight: 700;
            margin-bottom: 5px;
        }

        .contact-admin {
            font-size: 12px;
            color: #667eea;
            text-decoration: none;
            display: flex;
            align-items: center;
            gap: 5px;
            cursor: pointer;
        }

        /* Balance Card */
        .balance-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 25px;
            padding: 25px;
            margin-bottom: 20px;
            color: white;
            position: relative;
            overflow: hidden;
            box-shadow: 0 10px 30px rgba(102, 126, 234, 0.4);
        }

        .balance-card::before {
            content: '';
            position: absolute;
            top: -50%;
            right: -50%;
            width: 200%;
            height: 200%;
            background: radial-gradient(circle, rgba(255,255,255,0.2) 0%, transparent 70%);
            animation: rotate 20s linear infinite;
        }

        @keyframes rotate {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }

        .balance-label {
            font-size: 14px;
            opacity: 0.9;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 5px;
        }

        .balance-amount {
            font-size: 48px;
            font-weight: 800;
            margin-bottom: 20px;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.2);
        }

        .withdraw-btn {
            background: white;
            color: #667eea;
            border: none;
            padding: 15px 30px;
            border-radius: 15px;
            font-weight: 700;
            font-size: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            width: 100%;
            cursor: pointer;
            transition: all 0.3s;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.2);
        }

        .withdraw-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(0, 0, 0, 0.3);
        }

        .withdraw-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }

        /* Locked Overlay */
        .locked-overlay {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.8);
            backdrop-filter: blur(5px);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            z-index: 10;
            border-radius: 25px;
            padding: 20px;
            text-align: center;
        }

        .locked-icon {
            font-size: 50px;
            color: #ffd700;
            margin-bottom: 15px;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.1); }
        }

        .locked-title {
            font-size: 20px;
            font-weight: 700;
            color: white;
            margin-bottom: 10px;
        }

        .locked-text {
            color: #aaa;
            font-size: 14px;
            margin-bottom: 20px;
        }

        .verify-btn {
            background: linear-gradient(135deg, #ffd700, #ffaa00);
            color: #333;
            border: none;
            padding: 15px 30px;
            border-radius: 15px;
            font-weight: 700;
            font-size: 16px;
            display: flex;
            align-items: center;
            gap: 10px;
            cursor: pointer;
            transition: all 0.3s;
        }

        .verify-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(255, 215, 0, 0.4);
        }

        /* Navigation Bar - Fixed */
        .nav-bar {
            display: flex;
            background: white;
            padding: 10px;
            border-radius: 20px;
            margin-bottom: 20px;
            gap: 5px;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1);
        }

        .nav-item {
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 5px;
            padding: 12px 5px;
            border-radius: 15px;
            cursor: pointer;
            transition: all 0.3s;
            color: #888;
            background: transparent;
            border: none;
        }

        .nav-item i {
            font-size: 20px;
        }

        .nav-item span {
            font-size: 12px;
            font-weight: 600;
        }

        .nav-item.active {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }

        /* Tabs */
        .tab {
            display: none;
            animation: fadeIn 0.3s;
        }

        .tab.active {
            display: block;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        /* Section */
        .section {
            background: white;
            border-radius: 20px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1);
        }

        .section-title {
            font-size: 16px;
            font-weight: 700;
            margin-bottom: 15px;
            color: #333;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        /* History Items */
        .history-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 15px;
            margin-bottom: 10px;
            border-left: 5px solid;
            animation: slideIn 0.3s;
        }

        @keyframes slideIn {
            from { opacity: 0; transform: translateX(-20px); }
            to { opacity: 1; transform: translateX(0); }
        }

        .history-item.completed {
            border-left-color: #28a745;
        }

        .history-item.pending {
            border-left-color: #ffc107;
        }

        .history-item.rejected {
            border-left-color: #dc3545;
        }

        .history-info h4 {
            font-size: 15px;
            font-weight: 600;
            margin-bottom: 5px;
        }

        .history-info p {
            font-size: 12px;
            color: #666;
        }

        .history-amount {
            font-size: 18px;
            font-weight: 700;
        }

        .history-amount.completed {
            color: #28a745;
        }

        .history-amount.pending {
            color: #ffc107;
        }

        .history-amount.rejected {
            color: #dc3545;
        }

        .history-status {
            font-size: 11px;
            padding: 3px 8px;
            border-radius: 10px;
            background: #f0f0f0;
            display: inline-block;
            margin-top: 5px;
        }

        /* Gift Card */
        .gift-input {
            width: 100%;
            padding: 20px;
            font-size: 32px;
            font-weight: 700;
            letter-spacing: 10px;
            text-align: center;
            background: #f8f9fa;
            border: 2px dashed #667eea;
            border-radius: 15px;
            margin-bottom: 15px;
            text-transform: uppercase;
        }

        .gift-input:focus {
            outline: none;
            border-color: #764ba2;
            background: white;
        }

        .gift-result {
            text-align: center;
            padding: 15px;
            border-radius: 15px;
            margin-top: 15px;
            font-weight: 600;
            animation: popIn 0.3s;
        }

        @keyframes popIn {
            from { transform: scale(0.9); opacity: 0; }
            to { transform: scale(1); opacity: 1; }
        }

        .gift-result.success {
            background: #d4edda;
            color: #155724;
        }

        .gift-result.error {
            background: #f8d7da;
            color: #721c24;
        }

        /* Referral Card */
        .refer-card {
            background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
            border-radius: 20px;
            padding: 25px;
            color: white;
            text-align: center;
            margin-bottom: 20px;
        }

        .refer-code {
            font-size: 36px;
            font-weight: 800;
            letter-spacing: 5px;
            background: rgba(255, 255, 255, 0.2);
            padding: 20px;
            border-radius: 15px;
            margin: 20px 0;
            cursor: pointer;
            transition: all 0.3s;
            border: 2px dashed white;
        }

        .refer-code:hover {
            background: rgba(255, 255, 255, 0.3);
            transform: scale(1.02);
        }

        .refer-stats {
            display: flex;
            gap: 15px;
            margin: 20px 0;
        }

        .refer-stat {
            flex: 1;
            background: rgba(255, 255, 255, 0.2);
            padding: 15px;
            border-radius: 15px;
        }

        .refer-stat-value {
            font-size: 24px;
            font-weight: 700;
        }

        .refer-stat-label {
            font-size: 12px;
            opacity: 0.9;
        }

        /* Leaderboard */
        .leaderboard-item {
            display: flex;
            align-items: center;
            gap: 15px;
            padding: 12px;
            background: #f8f9fa;
            border-radius: 15px;
            margin-bottom: 8px;
            transition: all 0.3s;
        }

        .leaderboard-item:hover {
            transform: translateX(5px);
            background: #f0f0f0;
        }

        .leaderboard-item.highlight {
            background: linear-gradient(135deg, #667eea20 0%, #764ba220 100%);
            border-left: 5px solid #667eea;
        }

        .leaderboard-rank {
            width: 35px;
            height: 35px;
            background: white;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }

        .leaderboard-rank.gold {
            background: #ffd700;
            color: #333;
        }

        .leaderboard-info {
            flex: 1;
        }

        .leaderboard-name {
            font-weight: 600;
            margin-bottom: 2px;
        }

        .leaderboard-stats {
            font-size: 11px;
            color: #666;
        }

        .leaderboard-balance {
            font-weight: 700;
            color: #28a745;
        }

        /* Referrals List */
        .referrals-list {
            max-height: 400px;
            overflow-y: auto;
            padding-right: 5px;
        }

        .referral-item {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 15px;
            margin-bottom: 10px;
            border-left: 5px solid;
        }

        .referral-item.verified {
            border-left-color: #28a745;
        }

        .referral-item.pending {
            border-left-color: #ffc107;
        }

        .referral-header {
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
        }

        .referral-name {
            font-weight: 600;
        }

        .referral-status {
            font-size: 11px;
            padding: 3px 8px;
            border-radius: 10px;
        }

        .referral-status.verified {
            background: #d4edda;
            color: #155724;
        }

        .referral-status.pending {
            background: #fff3cd;
            color: #856404;
        }

        .referral-id {
            font-size: 11px;
            color: #666;
            font-family: monospace;
        }

        /* Modal */
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            backdrop-filter: blur(5px);
            z-index: 1000;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }

        .modal.active {
            display: flex;
        }

        .modal-content {
            background: white;
            border-radius: 25px;
            padding: 25px;
            width: 100%;
            max-width: 400px;
            max-height: 90vh;
            overflow-y: auto;
            animation: modalSlide 0.3s;
        }

        @keyframes modalSlide {
            from { transform: translateY(-50px); opacity: 0; }
            to { transform: translateY(0); opacity: 1; }
        }

        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }

        .modal-header h3 {
            font-size: 20px;
            color: #333;
        }

        .modal-close {
            background: none;
            border: none;
            font-size: 24px;
            cursor: pointer;
            color: #666;
        }

        .modal-close:hover {
            color: #dc3545;
        }

        /* Verification Modal */
        .verification-steps {
            margin: 20px 0;
        }

        .step {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px;
            background: #f8f9fa;
            border-radius: 12px;
            margin-bottom: 8px;
            animation: stepAppear 0.3s;
        }

        @keyframes stepAppear {
            from { opacity: 0; transform: translateX(-20px); }
            to { opacity: 1; transform: translateX(0); }
        }

        .step-icon {
            width: 30px;
            height: 30px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 14px;
        }

        .step.checking .step-icon {
            background: #ffc107;
            color: white;
        }

        .step.passed .step-icon {
            background: #28a745;
            color: white;
        }

        .step.failed .step-icon {
            background: #dc3545;
            color: white;
        }

        .step-info {
            flex: 1;
        }

        .step-title {
            font-weight: 600;
            font-size: 14px;
            margin-bottom: 2px;
        }

        .step-message {
            font-size: 12px;
            color: #666;
        }

        /* Channel List */
        .channel-item {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px;
            background: #f8f9fa;
            border-radius: 12px;
            margin-bottom: 8px;
            cursor: pointer;
            transition: all 0.3s;
            border: 2px solid transparent;
        }

        .channel-item:hover {
            border-color: #667eea;
            transform: translateX(5px);
        }

        .channel-icon {
            width: 40px;
            height: 40px;
            background: linear-gradient(135deg, #667eea, #764ba2);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
        }

        .channel-info {
            flex: 1;
        }

        .channel-name {
            font-weight: 600;
            margin-bottom: 2px;
        }

        .channel-status {
            font-size: 11px;
            color: #666;
        }

        /* Forms */
        input, textarea {
            width: 100%;
            padding: 15px;
            margin: 8px 0;
            border: 2px solid #e0e0e0;
            border-radius: 15px;
            font-size: 14px;
            transition: all 0.3s;
        }

        input:focus, textarea:focus {
            outline: none;
            border-color: #667eea;
        }

        /* Buttons */
        .btn {
            width: 100%;
            padding: 15px;
            border: none;
            border-radius: 15px;
            font-weight: 700;
            font-size: 16px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            transition: all 0.3s;
            margin: 8px 0;
        }

        .btn-primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }

        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
        }

        .btn-success {
            background: #28a745;
            color: white;
        }

        .btn-danger {
            background: #dc3545;
            color: white;
        }

        .btn-warning {
            background: #ffc107;
            color: #333;
        }

        /* Action Loader */
        .action-loader {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.9);
            z-index: 10000;
            justify-content: center;
            align-items: center;
            flex-direction: column;
        }

        .action-loader.active {
            display: flex;
        }

        .action-spinner {
            width: 50px;
            height: 50px;
            border: 5px solid rgba(255, 255, 255, 0.3);
            border-top-color: white;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-bottom: 20px;
        }

        .action-text {
            color: white;
            font-size: 18px;
            font-weight: 600;
        }

        /* Toast */
        .toast {
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: white;
            padding: 15px 30px;
            border-radius: 50px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
            display: none;
            align-items: center;
            gap: 10px;
            z-index: 10001;
            font-weight: 500;
            border-left: 5px solid;
        }

        .toast.show {
            display: flex;
            animation: toastSlide 0.3s;
        }

        @keyframes toastSlide {
            from { transform: translateX(-50%) translateY(100px); opacity: 0; }
            to { transform: translateX(-50%) translateY(0); opacity: 1; }
        }

        .toast.success {
            border-left-color: #28a745;
        }

        .toast.error {
            border-left-color: #dc3545;
        }

        .toast.info {
            border-left-color: #667eea;
        }

        /* Skeleton Loading */
        .skeleton {
            background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
            background-size: 200% 100%;
            animation: loading 1.5s infinite;
            border-radius: 10px;
            height: 70px;
            margin-bottom: 10px;
        }

        @keyframes loading {
            0% { background-position: 200% 0; }
            100% { background-position: -200% 0; }
        }

        /* Empty States */
        .empty-state {
            text-align: center;
            padding: 40px 20px;
            color: #aaa;
        }

        .empty-state i {
            font-size: 50px;
            margin-bottom: 15px;
        }

        /* Device Error */
        .device-error {
            background: #f8d7da;
            color: #721c24;
            padding: 15px;
            border-radius: 12px;
            margin: 15px 0;
            text-align: center;
        }

        .retry-btn {
            background: #dc3545;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 10px;
            margin-top: 10px;
            cursor: pointer;
            font-weight: 600;
        }

        /* Responsive */
        @media (max-width: 400px) {
            .app-container {
                padding: 15px;
            }
            
            .balance-amount {
                font-size: 36px;
            }
            
            .refer-code {
                font-size: 28px;
                letter-spacing: 3px;
            }
            
            .nav-item span {
                font-size: 10px;
            }
        }
    </style>
</head>
<body>
    <!-- Loading Screen -->
    <div id="loadingScreen" class="loading-screen">
        <div class="loading-content">
            <img src="https://{{ base_url }}/static/{{ settings.logo_filename }}?v={{ timestamp }}" style="width: 100px; height: 100px; border-radius: 20px; margin-bottom: 20px;">
            <div class="loading-spinner"></div>
            <h3>{{ settings.bot_name }}</h3>
            <div class="loading-progress">
                <div id="loadingProgress" class="loading-progress-bar" style="width: 0%;"></div>
            </div>
            <p id="loadingText">Loading resources...</p>
        </div>
    </div>

    <!-- Action Loader -->
    <div id="actionLoader" class="action-loader">
        <div class="action-spinner"></div>
        <div id="actionText" class="action-text">Processing...</div>
    </div>

    <!-- Toast Notification -->
    <div id="toast" class="toast">
        <i class="fas fa-info-circle"></i>
        <span id="toastMessage"></span>
    </div>

    <!-- Verification Modal -->
    <div id="verifyModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3><i class="fas fa-shield-alt"></i> Verification Required</h3>
                <button class="modal-close" onclick="closeVerifyModal()">&times;</button>
            </div>
            
            <div id="verifyError" class="device-error" style="display: none;"></div>
            
            <div id="verifySteps" class="verification-steps">
                <!-- Steps will be added here -->
            </div>
            
            <div id="channelList" class="channel-list" style="display: none;">
                <!-- Channel list will be added here -->
            </div>
            
            <button id="retryDeviceBtn" class="retry-btn" style="display: none;" onclick="retryDeviceVerification()">
                <i class="fas fa-redo"></i> Retry Device Check
            </button>
            
            <button class="btn btn-primary" onclick="closeVerifyModal()">
                <i class="fas fa-times"></i> Close
            </button>
        </div>
    </div>

    <!-- Withdraw Modal -->
    <div id="withdrawModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3><i class="fas fa-money-bill-wave"></i> Withdraw Money</h3>
                <button class="modal-close" onclick="closeModal('withdrawModal')">&times;</button>
            </div>
            
            <input type="text" id="upiId" placeholder="Enter UPI ID (e.g., name@okhdfcbank)">
            <input type="number" id="withdrawAmount" placeholder="Amount (Min: ₹{{ settings.min_withdrawal }})">
            
            <button class="btn btn-success" onclick="submitWithdraw()">
                <i class="fas fa-paper-plane"></i> Submit Request
            </button>
            <button class="btn btn-danger" onclick="closeModal('withdrawModal')">
                <i class="fas fa-times"></i> Cancel
            </button>
        </div>
    </div>

    <!-- Contact Modal -->
    <div id="contactModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3><i class="fas fa-headset"></i> Contact Admin</h3>
                <button class="modal-close" onclick="closeModal('contactModal')">&times;</button>
            </div>
            
            <textarea id="contactMessage" rows="4" placeholder="Type your message..."></textarea>
            <input type="file" id="contactImage" accept="image/*">
            
            <button class="btn btn-primary" onclick="sendContact()">
                <i class="fas fa-paper-plane"></i> Send Message
            </button>
            <button class="btn btn-danger" onclick="closeModal('contactModal')">
                <i class="fas fa-times"></i> Cancel
            </button>
        </div>
    </div>

    <!-- Main App Container -->
    <div id="app" class="app-container" style="display: none;">
        <!-- Header -->
        <div class="header">
            <img src="/get_pfp?uid={{ user_id }}" class="profile-pic" onerror="this.style.display='none'; document.querySelector('.profile-icon').style.display='flex';">
            <div class="profile-icon" style="display: none;">
                <i class="fas fa-user"></i>
            </div>
            
            <div class="user-info">
                <div class="user-name">{{ user.name }}</div>
                <div class="contact-admin" onclick="openModal('contactModal')">
                    <i class="fas fa-headset"></i> Contact Admin
                </div>
            </div>
        </div>

        <!-- Balance Card -->
        <div class="balance-card" id="balanceCard">
            {% if user_status != 'verified' and not settings.hide_verify_button %}
            <div class="locked-overlay" id="lockedOverlay">
                <i class="fas fa-lock locked-icon"></i>
                <div class="locked-title">Account Locked</div>
                <div class="locked-text">Complete verification to access your wallet</div>
                <button class="verify-btn" onclick="startVerification()">
                    <i class="fas fa-unlock-alt"></i> VERIFY NOW
                </button>
            </div>
            {% endif %}
            
            <div class="balance-label">
                <i class="fas fa-wallet"></i> Wallet Balance
            </div>
            <div class="balance-amount" id="balanceAmount">₹{{ "%.2f"|format(user.balance) }}</div>
            
            <button class="withdraw-btn" id="withdrawBtn" onclick="openModal('withdrawModal')" {% if user_status != 'verified' %}disabled{% endif %}>
                <i class="fas fa-money-bill-wave"></i> WITHDRAW
            </button>
        </div>

        <!-- Navigation Bar - Fixed -->
        <div class="nav-bar">
            <button class="nav-item active" onclick="switchTab('home', this)">
                <i class="fas fa-home"></i>
                <span>HOME</span>
            </button>
            <button class="nav-item" onclick="switchTab('gift', this)">
                <i class="fas fa-gift"></i>
                <span>GIFT</span>
            </button>
            <button class="nav-item" onclick="switchTab('refer', this)">
                <i class="fas fa-users"></i>
                <span>REFER</span>
            </button>
            <button class="nav-item" onclick="switchTab('rank', this)">
                <i class="fas fa-trophy"></i>
                <span>RANK</span>
            </button>
        </div>

        <!-- Home Tab -->
        <div id="tab-home" class="tab active">
            <div class="section">
                <div class="section-title">
                    <i class="fas fa-history"></i> Recent Activity
                </div>
                <div id="historyList">
                    <!-- History items will be loaded here -->
                    <div class="skeleton"></div>
                    <div class="skeleton"></div>
                </div>
            </div>
        </div>

        <!-- Gift Tab -->
        <div id="tab-gift" class="tab">
            <div class="section">
                <div class="section-title">
                    <i class="fas fa-gift"></i> Claim Gift Code
                </div>
                
                <input type="text" id="giftCode" class="gift-input" maxlength="5" placeholder="ABCDE" oninput="this.value = this.value.toUpperCase()">
                
                <button class="btn btn-primary" onclick="claimGift()">
                    <i class="fas fa-gift"></i> CLAIM GIFT
                </button>
                
                <div id="giftResult" class="gift-result" style="display: none;"></div>
            </div>
        </div>

        <!-- Refer Tab -->
        <div id="tab-refer" class="tab">
            <div class="refer-card">
                <i class="fas fa-users" style="font-size: 40px; margin-bottom: 15px;"></i>
                <h3>Refer & Earn</h3>
                
                <div class="refer-code" id="referCode" onclick="copyReferCode()">
                    LOADING...
                </div>
                
                <div class="refer-stats">
                    <div class="refer-stat">
                        <div class="refer-stat-value" id="totalRefers">0</div>
                        <div class="refer-stat-label">Total</div>
                    </div>
                    <div class="refer-stat">
                        <div class="refer-stat-value" id="verifiedRefers">0</div>
                        <div class="refer-stat-label">Verified</div>
                    </div>
                    <div class="refer-stat">
                        <div class="refer-stat-value" id="pendingRefers">0</div>
                        <div class="refer-stat-label">Pending</div>
                    </div>
                </div>
                
                <button class="btn btn-warning" onclick="shareReferLink()">
                    <i class="fas fa-share-alt"></i> Share Link
                </button>
            </div>
            
            <div class="section">
                <div class="section-title">
                    <i class="fas fa-user-friends"></i> Your Referrals
                </div>
                
                <div id="referralsList" class="referrals-list">
                    <!-- Referrals will be loaded here -->
                    <div class="empty-state">
                        <i class="fas fa-users"></i>
                        <p>No referrals yet</p>
                    </div>
                </div>
            </div>
        </div>

        <!-- Rank Tab -->
        <div id="tab-rank" class="tab">
            <div class="section">
                <div class="section-title">
                    <i class="fas fa-trophy"></i> Top Earners
                </div>
                
                <div id="leaderboardList">
                    {% for user in leaderboard %}
                    <div class="leaderboard-item {% if user.user_id == user_id %}highlight{% endif %}">
                        <div class="leaderboard-rank {% if loop.index <= 3 %}gold{% endif %}">
                            {{ loop.index }}
                        </div>
                        <div class="leaderboard-info">
                            <div class="leaderboard-name">{{ user.name[:20] }}{% if user.name|length > 20 %}...{% endif %}</div>
                            <div class="leaderboard-stats">
                                <i class="fas fa-users"></i> {{ user.total_refers }} refers
                            </div>
                        </div>
                        <div class="leaderboard-balance">₹{{ "%.2f"|format(user.balance) }}</div>
                    </div>
                    {% else %}
                    <div class="empty-state">
                        <i class="fas fa-trophy"></i>
                        <p>No data available</p>
                    </div>
                    {% endfor %}
                </div>
            </div>
        </div>
    </div>

    <script>
        // Configuration
        const USER_ID = "{{ user_id }}";
        const USER_STATUS = "{{ user_status }}";
        const IS_VERIFIED = {{ user.verified|lower }};
        const DEVICE_VERIFIED = {{ user.device_verified|lower }};
        const HIDE_VERIFY_BUTTON = {{ settings.hide_verify_button|lower }};
        const MIN_WITHDRAWAL = {{ settings.min_withdrawal }};
        
        // State
        let deviceFingerprint = '';
        let currentBalance = {{ user.balance }};
        let currentStep = 0;
        let verificationInProgress = false;
        
        // Initialize
        document.addEventListener('DOMContentLoaded', function() {
            generateDeviceFingerprint();
            startLoadingProgress();
            
            // Load data
            loadHistory();
            loadReferInfo();
            
            // Auto-verify if needed
            if (HIDE_VERIFY_BUTTON && USER_STATUS !== 'verified') {
                setTimeout(() => {
                    startVerification();
                }, 500);
            }
        });
        
        // Loading progress
        function startLoadingProgress() {
            let progress = 0;
            const loadingBar = document.getElementById('loadingProgress');
            const loadingText = document.getElementById('loadingText');
            
            const interval = setInterval(() => {
                progress += 5;
                loadingBar.style.width = progress + '%';
                
                if (progress <= 30) {
                    loadingText.textContent = 'Loading resources...';
                } else if (progress <= 60) {
                    loadingText.textContent = 'Preparing interface...';
                } else if (progress <= 90) {
                    loadingText.textContent = 'Almost ready...';
                } else {
                    loadingText.textContent = 'Welcome!';
                }
                
                if (progress >= 100) {
                    clearInterval(interval);
                    setTimeout(() => {
                        document.getElementById('loadingScreen').classList.add('hidden');
                        document.getElementById('app').style.display = 'block';
                    }, 300);
                }
            }, 50);
        }
        
        // Generate device fingerprint
        function generateDeviceFingerprint() {
            const userAgent = navigator.userAgent;
            const language = navigator.language;
            const platform = navigator.platform;
            const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
            
            const data = `${userAgent}|${language}|${platform}|${timezone}|${screen.width}x${screen.height}`;
            
            let hash = 0;
            for (let i = 0; i < data.length; i++) {
                const char = data.charCodeAt(i);
                hash = ((hash << 5) - hash) + char;
                hash = hash & hash;
            }
            
            deviceFingerprint = Math.abs(hash).toString(36);
        }
        
        // Toast notifications
        function showToast(message, type = 'info', duration = 3000) {
            const toast = document.getElementById('toast');
            const toastMessage = document.getElementById('toastMessage');
            
            toast.className = 'toast ' + type;
            toastMessage.textContent = message;
            toast.classList.add('show');
            
            setTimeout(() => {
                toast.classList.remove('show');
            }, duration);
        }
        
        // Action loader
        function showLoader(text = 'Processing...') {
            document.getElementById('actionText').textContent = text;
            document.getElementById('actionLoader').classList.add('active');
        }
        
        function hideLoader() {
            document.getElementById('actionLoader').classList.remove('active');
        }
        
        // Modal functions
        function openModal(modalId) {
            document.getElementById(modalId).classList.add('active');
        }
        
        function closeModal(modalId) {
            document.getElementById(modalId).classList.remove('active');
        }
        
        function closeVerifyModal() {
            document.getElementById('verifyModal').classList.remove('active');
            if (verificationInProgress) {
                verificationInProgress = false;
            }
        }
        
        // Tab switching - Fixed
        function switchTab(tabName, element) {
            // Remove active class from all nav items
            document.querySelectorAll('.nav-item').forEach(item => {
                item.classList.remove('active');
            });
            
            // Add active class to clicked item
            element.classList.add('active');
            
            // Hide all tabs
            document.querySelectorAll('.tab').forEach(tab => {
                tab.classList.remove('active');
            });
            
            // Show selected tab
            document.getElementById('tab-' + tabName).classList.add('active');
            
            // Load tab-specific data
            if (tabName === 'rank') {
                loadLeaderboard();
            } else if (tabName === 'refer') {
                loadReferInfo();
            }
        }
        
        // Verification
        function startVerification() {
            if (verificationInProgress) return;
            
            verificationInProgress = true;
            currentStep = 0;
            
            document.getElementById('verifySteps').innerHTML = '';
            document.getElementById('verifyError').style.display = 'none';
            document.getElementById('retryDeviceBtn').style.display = 'none';
            document.getElementById('channelList').style.display = 'none';
            
            openModal('verifyModal');
            addVerificationStep('Starting verification...', 'checking');
            
            showLoader('Verifying...');
            
            fetch('/api/verify', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    user_id: USER_ID,
                    fp: deviceFingerprint
                })
            })
            .then(r => r.json())
            .then(data => {
                hideLoader();
                
                if (data.ok) {
                    // Show steps
                    if (data.steps) {
                        data.steps.forEach(step => {
                            addVerificationStep(step.message, step.status);
                        });
                    }
                    
                    // Success
                    setTimeout(() => {
                        closeVerifyModal();
                        showToast('Verification successful!', 'success');
                        
                        // Update UI
                        document.getElementById('balanceAmount').textContent = '₹' + data.balance.toFixed(2);
                        currentBalance = data.balance;
                        
                        // Remove locked overlay
                        const overlay = document.getElementById('lockedOverlay');
                        if (overlay) {
                            overlay.remove();
                        }
                        
                        // Enable withdraw button
                        document.getElementById('withdrawBtn').disabled = false;
                        
                        // Show bonus confetti
                        if (data.bonus > 0) {
                            showToast(`✨ ₹${data.bonus} bonus added!`, 'success', 5000);
                            if (typeof confetti === 'function') {
                                confetti({particleCount: 200, spread: 100, origin: { y: 0.6 }});
                            }
                        }
                        
                        // Reload data
                        loadHistory();
                        loadReferInfo();
                    }, 1000);
                    
                } else {
                    // Show error
                    addVerificationStep(data.msg || 'Verification failed', 'failed');
                    
                    if (data.type === 'device' && data.retry) {
                        document.getElementById('retryDeviceBtn').style.display = 'block';
                        document.getElementById('verifyError').style.display = 'block';
                        document.getElementById('verifyError').textContent = data.msg;
                    }
                    
                    if (data.type === 'channels') {
                        // Show channels to join
                        document.getElementById('channelList').style.display = 'block';
                        // Add channel list here
                    }
                }
                
                verificationInProgress = false;
            })
            .catch(err => {
                hideLoader();
                addVerificationStep('Network error', 'failed');
                verificationInProgress = false;
                showToast('Verification failed. Try again.', 'error');
            });
        }
        
        function addVerificationStep(message, status) {
            const steps = document.getElementById('verifySteps');
            const step = document.createElement('div');
            step.className = 'step ' + status;
            
            let icon = '⏳';
            if (status === 'passed') icon = '✓';
            else if (status === 'failed') icon = '✗';
            
            step.innerHTML = `
                <div class="step-icon">${icon}</div>
                <div class="step-info">
                    <div class="step-title">${message}</div>
                </div>
            `;
            
            steps.appendChild(step);
            steps.scrollTop = steps.scrollHeight;
        }
        
        function retryDeviceVerification() {
            deviceFingerprint = '';
            generateDeviceFingerprint();
            closeVerifyModal();
            setTimeout(() => startVerification(), 500);
        }
        
        // Withdraw
        function submitWithdraw() {
            const upi = document.getElementById('upiId').value.trim();
            const amount = parseFloat(document.getElementById('withdrawAmount').value);
            
            if (!upi) {
                showToast('Please enter UPI ID', 'error');
                return;
            }
            
            if (!amount || amount < MIN_WITHDRAWAL) {
                showToast(`Minimum withdrawal is ₹${MIN_WITHDRAWAL}`, 'error');
                return;
            }
            
            if (amount > currentBalance) {
                showToast('Insufficient balance', 'error');
                return;
            }
            
            closeModal('withdrawModal');
            showLoader('Processing withdrawal...');
            
            fetch('/api/withdraw', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    user_id: USER_ID,
                    amount: amount,
                    upi: upi
                })
            })
            .then(r => r.json())
            .then(data => {
                hideLoader();
                
                if (data.ok) {
                    showToast(data.msg || 'Withdrawal request submitted!', 'success');
                    
                    // Update balance
                    if (data.new_balance) {
                        document.getElementById('balanceAmount').textContent = '₹' + data.new_balance.toFixed(2);
                        currentBalance = data.new_balance;
                    }
                    
                    // Clear form
                    document.getElementById('upiId').value = '';
                    document.getElementById('withdrawAmount').value = '';
                    
                    // Reload history
                    loadHistory();
                    
                    // Show confetti for auto payments
                    if (data.mode === 'auto' || data.mode === 'fake') {
                        if (typeof confetti === 'function') {
                            confetti({particleCount: 200, spread: 100, origin: { y: 0.6 }});
                        }
                    }
                } else {
                    showToast(data.msg || 'Withdrawal failed', 'error');
                }
            })
            .catch(err => {
                hideLoader();
                showToast('Network error. Try again.', 'error');
            });
        }
        
        // Contact admin
        function sendContact() {
            const message = document.getElementById('contactMessage').value.trim();
            const image = document.getElementById('contactImage').files[0];
            
            if (!message) {
                showToast('Please enter a message', 'error');
                return;
            }
            
            closeModal('contactModal');
            showLoader('Sending message...');
            
            const formData = new FormData();
            formData.append('user_id', USER_ID);
            formData.append('message', message);
            if (image) {
                formData.append('image', image);
            }
            
            fetch('/api/contact', {
                method: 'POST',
                body: formData
            })
            .then(r => r.json())
            .then(data => {
                hideLoader();
                
                if (data.ok) {
                    showToast('Message sent to admin!', 'success');
                    document.getElementById('contactMessage').value = '';
                    document.getElementById('contactImage').value = '';
                } else {
                    showToast(data.msg || 'Failed to send', 'error');
                }
            })
            .catch(err => {
                hideLoader();
                showToast('Network error', 'error');
            });
        }
        
        // History
        function loadHistory() {
            fetch('/api/history?user_id=' + USER_ID)
            .then(r => r.json())
            .then(data => {
                const container = document.getElementById('historyList');
                
                if (!data || data.length === 0) {
                    container.innerHTML = `
                        <div class="empty-state">
                            <i class="fas fa-history"></i>
                            <p>No transactions yet</p>
                        </div>
                    `;
                    return;
                }
                
                container.innerHTML = data.map(item => `
                    <div class="history-item ${item.status}">
                        <div class="history-info">
                            <h4>${item.name || 'Transaction'}</h4>
                            <p>${item.created_at ? item.created_at.slice(0, 16) : ''}</p>
                            ${item.tx_id && !item.tx_id.startsWith('BONUS') ? 
                                `<p class="history-status">${item.tx_id}</p>` : ''}
                        </div>
                        <div class="history-amount ${item.status}">
                            ₹${(item.amount || 0).toFixed(2)}
                        </div>
                    </div>
                `).join('');
            })
            .catch(() => {
                document.getElementById('historyList').innerHTML = `
                    <div class="empty-state">
                        <i class="fas fa-exclamation-circle"></i>
                        <p>Failed to load history</p>
                    </div>
                `;
            });
        }
        
        // Referral
        function loadReferInfo() {
            fetch('/api/get_refer_info?user_id=' + USER_ID)
            .then(r => r.json())
            .then(data => {
                if (!data.ok) return;
                
                // Update refer code
                document.getElementById('referCode').textContent = data.refer_code || 'ERROR';
                
                // Update stats
                document.getElementById('totalRefers').textContent = data.total_refers || 0;
                document.getElementById('verifiedRefers').textContent = data.verified_refers || 0;
                document.getElementById('pendingRefers').textContent = data.pending_refers || 0;
                
                // Update referrals list
                const list = document.getElementById('referralsList');
                
                if (!data.referred_users || data.referred_users.length === 0) {
                    list.innerHTML = `
                        <div class="empty-state">
                            <i class="fas fa-users"></i>
                            <p>No referrals yet</p>
                        </div>
                    `;
                    return;
                }
                
                list.innerHTML = data.referred_users.map(user => `
                    <div class="referral-item ${user.verified ? 'verified' : 'pending'}">
                        <div class="referral-header">
                            <span class="referral-name">${user.name}</span>
                            <span class="referral-status ${user.verified ? 'verified' : 'pending'}">
                                ${user.verified ? '✅ Verified' : '⏳ Pending'}
                            </span>
                        </div>
                        <div class="referral-id">ID: ${user.id}</div>
                        ${user.username ? `<div class="referral-id">@${user.username}</div>` : ''}
                    </div>
                `).join('');
            })
            .catch(() => {
                document.getElementById('referCode').textContent = 'ERROR';
            });
        }
        
        function copyReferCode() {
            const code = document.getElementById('referCode').textContent;
            navigator.clipboard.writeText(code)
                .then(() => showToast('Referral code copied!', 'success'))
                .catch(() => showToast('Failed to copy', 'error'));
        }
        
        function shareReferLink() {
            const code = document.getElementById('referCode').textContent;
            const botUsername = "{{ bot.get_me().username }}";
            const link = `https://t.me/${botUsername}?start=${code}`;
            const text = `Join and earn money! Use my referral code: ${code}`;
            
            window.open(`https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(text)}`, '_blank');
        }
        
        // Gift codes
        function claimGift() {
            const code = document.getElementById('giftCode').value.trim().toUpperCase();
            
            if (!code || code.length !== 5) {
                showToast('Please enter a valid 5-digit code', 'error');
                return;
            }
            
            showLoader('Claiming gift...');
            
            fetch('/api/claim_gift', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    user_id: USER_ID,
                    code: code
                })
            })
            .then(r => r.json())
            .then(data => {
                hideLoader();
                
                const resultDiv = document.getElementById('giftResult');
                resultDiv.style.display = 'block';
                
                if (data.ok) {
                    resultDiv.className = 'gift-result success';
                    resultDiv.innerHTML = `<i class="fas fa-check-circle"></i> ${data.msg}`;
                    
                    // Update balance
                    if (data.new_balance) {
                        document.getElementById('balanceAmount').textContent = '₹' + data.new_balance.toFixed(2);
                        currentBalance = data.new_balance;
                    }
                    
                    // Clear input
                    document.getElementById('giftCode').value = '';
                    
                    // Show confetti
                    if (typeof confetti === 'function') {
                        confetti({particleCount: 200, spread: 100, origin: { y: 0.6 }});
                    }
                    
                    // Reload history
                    loadHistory();
                } else {
                    resultDiv.className = 'gift-result error';
                    resultDiv.innerHTML = `<i class="fas fa-exclamation-circle"></i> ${data.msg}`;
                }
                
                setTimeout(() => {
                    resultDiv.style.display = 'none';
                }, 5000);
            })
            .catch(err => {
                hideLoader();
                showToast('Network error', 'error');
            });
        }
        
        // Leaderboard
        function loadLeaderboard() {
            fetch('/api/leaderboard')
            .then(r => r.json())
            .then(data => {
                const container = document.getElementById('leaderboardList');
                
                if (!data.data || data.data.length === 0) {
                    container.innerHTML = `
                        <div class="empty-state">
                            <i class="fas fa-trophy"></i>
                            <p>No data available</p>
                        </div>
                    `;
                    return;
                }
                
                container.innerHTML = data.data.map((user, index) => `
                    <div class="leaderboard-item ${user.user_id == USER_ID ? 'highlight' : ''}">
                        <div class="leaderboard-rank ${index < 3 ? 'gold' : ''}">
                            ${index + 1}
                        </div>
                        <div class="leaderboard-info">
                            <div class="leaderboard-name">${(user.name || '').substring(0, 20)}${(user.name || '').length > 20 ? '...' : ''}</div>
                            <div class="leaderboard-stats">
                                <i class="fas fa-users"></i> ${user.total_refers || 0} refers
                            </div>
                        </div>
                        <div class="leaderboard-balance">₹${(user.balance || 0).toFixed(2)}</div>
                    </div>
                `).join('');
            })
            .catch(() => {});
        }
        
        // Update balance periodically
        setInterval(() => {
            fetch('/api/get_balance?user_id=' + USER_ID)
            .then(r => r.json())
            .then(data => {
                if (data.ok && data.balance !== currentBalance) {
                    document.getElementById('balanceAmount').textContent = '₹' + data.balance.toFixed(2);
                    currentBalance = data.balance;
                }
            })
            .catch(() => {});
        }, 30000);
    </script>
</body>
</html>
"""

ADMIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Panel - {{ settings.bot_name }}</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }
        
        body {
            background: #1a1a1a;
            color: #fff;
            min-height: 100vh;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }
        
        /* Header */
        .header {
            background: #2d2d2d;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-left: 5px solid #4CAF50;
        }
        
        .header h1 {
            font-size: 24px;
            color: #4CAF50;
        }
        
        .header .stats {
            display: flex;
            gap: 20px;
        }
        
        .stat-badge {
            background: #3d3d3d;
            padding: 8px 15px;
            border-radius: 20px;
            font-size: 14px;
        }
        
        .stat-badge i {
            margin-right: 5px;
            color: #4CAF50;
        }
        
        /* Navigation */
        .nav {
            background: #2d2d2d;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        
        .nav-btn {
            background: #3d3d3d;
            border: none;
            color: #aaa;
            padding: 12px 25px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 600;
            transition: all 0.3s;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .nav-btn i {
            font-size: 16px;
        }
        
        .nav-btn:hover {
            background: #4d4d4d;
            color: #fff;
        }
        
        .nav-btn.active {
            background: #4CAF50;
            color: #fff;
        }
        
        /* Tabs */
        .tab {
            display: none;
            animation: fadeIn 0.3s;
        }
        
        .tab.active {
            display: block;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        /* Cards */
        .card {
            background: #2d2d2d;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            border: 1px solid #3d3d3d;
        }
        
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 1px solid #3d3d3d;
        }
        
        .card-header h2 {
            font-size: 18px;
            color: #4CAF50;
        }
        
        .card-header h2 i {
            margin-right: 8px;
        }
        
        /* Forms */
        .form-group {
            margin-bottom: 15px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 5px;
            color: #aaa;
            font-size: 13px;
            font-weight: 600;
        }
        
        .form-control {
            width: 100%;
            padding: 12px 15px;
            background: #3d3d3d;
            border: 1px solid #4d4d4d;
            border-radius: 8px;
            color: #fff;
            font-size: 14px;
            transition: all 0.3s;
        }
        
        .form-control:focus {
            outline: none;
            border-color: #4CAF50;
            background: #454545;
        }
        
        .form-row {
            display: flex;
            gap: 15px;
            margin-bottom: 15px;
        }
        
        .form-row .form-group {
            flex: 1;
        }
        
        /* Buttons */
        .btn {
            padding: 12px 25px;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }
        
        .btn-primary {
            background: #4CAF50;
            color: #fff;
        }
        
        .btn-primary:hover {
            background: #45a049;
            transform: translateY(-2px);
        }
        
        .btn-danger {
            background: #f44336;
            color: #fff;
        }
        
        .btn-danger:hover {
            background: #da190b;
        }
        
        .btn-warning {
            background: #ff9800;
            color: #fff;
        }
        
        .btn-warning:hover {
            background: #e68a00;
        }
        
        .btn-info {
            background: #2196F3;
            color: #fff;
        }
        
        .btn-info:hover {
            background: #0b7dda;
        }
        
        .btn-sm {
            padding: 6px 12px;
            font-size: 12px;
        }
        
        /* Tables */
        .table-responsive {
            overflow-x: auto;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
        }
        
        th {
            text-align: left;
            padding: 12px;
            background: #3d3d3d;
            color: #aaa;
            font-size: 13px;
            font-weight: 600;
        }
        
        td {
            padding: 12px;
            border-bottom: 1px solid #3d3d3d;
            font-size: 14px;
        }
        
        tr:hover td {
            background: #353535;
        }
        
        /* Status badges */
        .badge {
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
            display: inline-block;
        }
        
        .badge-success {
            background: rgba(76, 175, 80, 0.2);
            color: #4CAF50;
        }
        
        .badge-warning {
            background: rgba(255, 152, 0, 0.2);
            color: #ff9800;
        }
        
        .badge-danger {
            background: rgba(244, 67, 54, 0.2);
            color: #f44336;
        }
        
        .badge-info {
            background: rgba(33, 150, 243, 0.2);
            color: #2196F3;
        }
        
        /* Grid */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        
        .stat-card {
            background: #2d2d2d;
            padding: 20px;
            border-radius: 10px;
            border-left: 4px solid #4CAF50;
        }
        
        .stat-card .stat-value {
            font-size: 28px;
            font-weight: 700;
            margin-bottom: 5px;
        }
        
        .stat-card .stat-label {
            color: #aaa;
            font-size: 13px;
        }
        
        .stat-card .stat-icon {
            float: right;
            font-size: 40px;
            color: #4CAF50;
            opacity: 0.3;
        }
        
        /* Channel list */
        .channel-item {
            background: #353535;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .channel-info h4 {
            margin-bottom: 5px;
        }
        
        .channel-info p {
            color: #aaa;
            font-size: 12px;
        }
        
        .channel-info p i {
            margin-right: 5px;
            color: #4CAF50;
        }
        
        .channel-actions {
            display: flex;
            gap: 5px;
        }
        
        /* Gift code items */
        .gift-item {
            background: #353535;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .gift-code {
            font-family: monospace;
            font-size: 18px;
            font-weight: 700;
            color: #4CAF50;
        }
        
        .gift-details {
            color: #aaa;
            font-size: 12px;
            margin-top: 5px;
        }
        
        .gift-details span {
            margin-right: 15px;
        }
        
        .gift-expired {
            opacity: 0.5;
            text-decoration: line-through;
        }
        
        /* Withdrawal items */
        .withdrawal-item {
            background: #353535;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 10px;
        }
        
        .withdrawal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        
        .withdrawal-id {
            font-family: monospace;
            color: #4CAF50;
        }
        
        .withdrawal-amount {
            font-size: 18px;
            font-weight: 700;
        }
        
        .withdrawal-details {
            display: flex;
            gap: 20px;
            color: #aaa;
            font-size: 12px;
            margin-bottom: 10px;
        }
        
        .withdrawal-actions {
            display: flex;
            gap: 10px;
        }
        
        /* User items */
        .user-item {
            background: #353535;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 10px;
            cursor: pointer;
            transition: all 0.3s;
        }
        
        .user-item:hover {
            background: #3d3d3d;
            transform: translateX(5px);
        }
        
        .user-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        
        .user-name {
            font-weight: 600;
        }
        
        .user-id {
            color: #aaa;
            font-size: 11px;
            font-family: monospace;
        }
        
        .user-balance {
            color: #4CAF50;
            font-weight: 700;
        }
        
        .user-stats {
            display: flex;
            gap: 15px;
            color: #aaa;
            font-size: 12px;
        }
        
        /* Modal */
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.8);
            z-index: 1000;
            justify-content: center;
            align-items: center;
        }
        
        .modal.active {
            display: flex;
        }
        
        .modal-content {
            background: #2d2d2d;
            border-radius: 10px;
            padding: 25px;
            width: 90%;
            max-width: 500px;
            max-height: 90vh;
            overflow-y: auto;
        }
        
        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 1px solid #3d3d3d;
        }
        
        .modal-header h3 {
            color: #4CAF50;
        }
        
        .modal-close {
            background: none;
            border: none;
            color: #aaa;
            font-size: 20px;
            cursor: pointer;
        }
        
        .modal-close:hover {
            color: #f44336;
        }
        
        /* Toast notifications */
        .toast {
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: #2d2d2d;
            color: #fff;
            padding: 15px 25px;
            border-radius: 8px;
            display: none;
            align-items: center;
            gap: 10px;
            z-index: 1001;
            border-left: 4px solid #4CAF50;
            box-shadow: 0 5px 15px rgba(0,0,0,0.3);
        }
        
        .toast.show {
            display: flex;
            animation: slideIn 0.3s;
        }
        
        .toast.success {
            border-left-color: #4CAF50;
        }
        
        .toast.error {
            border-left-color: #f44336;
        }
        
        .toast.warning {
            border-left-color: #ff9800;
        }
        
        @keyframes slideIn {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        
        /* Loader */
        .loader {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.7);
            z-index: 2000;
            justify-content: center;
            align-items: center;
            flex-direction: column;
        }
        
        .loader.active {
            display: flex;
        }
        
        .spinner {
            width: 50px;
            height: 50px;
            border: 5px solid #3d3d3d;
            border-top-color: #4CAF50;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-bottom: 15px;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        .loader-text {
            color: #fff;
            font-size: 16px;
        }
        
        /* Search */
        .search-box {
            position: relative;
            margin-bottom: 20px;
        }
        
        .search-box i {
            position: absolute;
            left: 15px;
            top: 50%;
            transform: translateY(-50%);
            color: #aaa;
        }
        
        .search-box input {
            width: 100%;
            padding: 12px 15px 12px 45px;
            background: #3d3d3d;
            border: 1px solid #4d4d4d;
            border-radius: 8px;
            color: #fff;
            font-size: 14px;
        }
        
        .search-box input:focus {
            outline: none;
            border-color: #4CAF50;
        }
        
        /* Toggle switch */
        .toggle-switch {
            position: relative;
            display: inline-block;
            width: 50px;
            height: 24px;
        }
        
        .toggle-switch input {
            opacity: 0;
            width: 0;
            height: 0;
        }
        
        .toggle-slider {
            position: absolute;
            cursor: pointer;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-color: #3d3d3d;
            transition: .3s;
            border-radius: 24px;
        }
        
        .toggle-slider:before {
            position: absolute;
            content: "";
            height: 18px;
            width: 18px;
            left: 3px;
            bottom: 3px;
            background-color: white;
            transition: .3s;
            border-radius: 50%;
        }
        
        input:checked + .toggle-slider {
            background-color: #4CAF50;
        }
        
        input:checked + .toggle-slider:before {
            transform: translateX(26px);
        }
        
        .toggle-label {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin: 10px 0;
        }
        
        /* Responsive */
        @media (max-width: 768px) {
            .nav {
                flex-direction: column;
            }
            
            .form-row {
                flex-direction: column;
            }
            
            .stats-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <h1><i class="fas fa-crown"></i> {{ settings.bot_name }} - Admin Panel</h1>
            <div class="stats">
                <div class="stat-badge"><i class="fas fa-users"></i> {{ stats.total_users }} Users</div>
                <div class="stat-badge"><i class="fas fa-clock"></i> {{ stats.pending_count }} Pending</div>
                <div class="stat-badge"><i class="fas fa-wallet"></i> ₹{{ "%.2f"|format(upi_balance.balance) }}</div>
            </div>
        </div>
        
        <!-- Navigation -->
        <div class="nav">
            <button class="nav-btn active" onclick="switchTab('dashboard')"><i class="fas fa-home"></i> Dashboard</button>
            <button class="nav-btn" onclick="switchTab('withdrawals')"><i class="fas fa-money-bill-wave"></i> Withdrawals</button>
            <button class="nav-btn" onclick="switchTab('users')"><i class="fas fa-users"></i> Users</button>
            <button class="nav-btn" onclick="switchTab('channels')"><i class="fas fa-tv"></i> Channels</button>
            <button class="nav-btn" onclick="switchTab('gifts')"><i class="fas fa-gift"></i> Gift Codes</button>
            <button class="nav-btn" onclick="switchTab('settings')"><i class="fas fa-cog"></i> Settings</button>
            <button class="nav-btn" onclick="switchTab('upi')"><i class="fas fa-credit-card"></i> UPI Settings</button>
            <button class="nav-btn" onclick="switchTab('broadcast')"><i class="fas fa-broadcast-tower"></i> Broadcast</button>
        </div>
        
        <!-- Loader -->
        <div id="loader" class="loader">
            <div class="spinner"></div>
            <div id="loaderText" class="loader-text">Processing...</div>
        </div>
        
        <!-- Toast -->
        <div id="toast" class="toast">
            <i class="fas fa-info-circle"></i>
            <span id="toastMessage"></span>
        </div>
        
        <!-- Dashboard Tab -->
        <div id="tab-dashboard" class="tab active">
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-icon"><i class="fas fa-users"></i></div>
                    <div class="stat-value">{{ stats.total_users }}</div>
                    <div class="stat-label">Total Users</div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon"><i class="fas fa-check-circle"></i></div>
                    <div class="stat-value">{{ users|selectattr('verified', 'equalto', True)|list|length }}</div>
                    <div class="stat-label">Verified Users</div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon"><i class="fas fa-clock"></i></div>
                    <div class="stat-value">{{ stats.pending_count }}</div>
                    <div class="stat-label">Pending Withdrawals</div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon"><i class="fas fa-rupee-sign"></i></div>
                    <div class="stat-value">₹{{ "%.2f"|format(stats.total_balance) }}</div>
                    <div class="stat-label">Total Balance</div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon"><i class="fas fa-history"></i></div>
                    <div class="stat-value">₹{{ "%.2f"|format(stats.total_withdrawn) }}</div>
                    <div class="stat-label">Total Withdrawn</div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon"><i class="fas fa-gift"></i></div>
                    <div class="stat-value">{{ gifts|length }}</div>
                    <div class="stat-label">Active Gift Codes</div>
                </div>
            </div>
            
            <div class="card">
                <div class="card-header">
                    <h2><i class="fas fa-clock"></i> Recent Pending Withdrawals</h2>
                    <button class="btn btn-sm btn-primary" onclick="switchTab('withdrawals')">View All</button>
                </div>
                <div class="table-responsive">
                    <table>
                        <thead>
                            <tr>
                                <th>TxID</th>
                                <th>User</th>
                                <th>Amount</th>
                                <th>UPI</th>
                                <th>Date</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for w in pending_withdrawals[:5] %}
                            <tr>
                                <td><span class="badge badge-info">{{ w.tx_id }}</span></td>
                                <td>{{ w.name }}<br><small class="badge">{{ w.user_id }}</small></td>
                                <td><span class="badge badge-warning">₹{{ w.amount }}</span></td>
                                <td>{{ w.upi }}</td>
                                <td>{{ w.created_at[:10] }}</td>
                                <td>
                                    <button class="btn btn-sm btn-success" onclick="openApproveModal('{{ w.tx_id }}')"><i class="fas fa-check"></i></button>
                                    <button class="btn btn-sm btn-danger" onclick="rejectWithdrawal('{{ w.tx_id }}')"><i class="fas fa-times"></i></button>
                                </td>
                            </tr>
                            {% else %}
                            <tr>
                                <td colspan="6" style="text-align: center; padding: 30px; color: #aaa;">
                                    <i class="fas fa-check-circle" style="font-size: 40px; margin-bottom: 10px; display: block;"></i>
                                    No pending withdrawals
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        
        <!-- Withdrawals Tab -->
        <div id="tab-withdrawals" class="tab">
            <div class="card">
                <div class="card-header">
                    <h2><i class="fas fa-list"></i> All Withdrawals</h2>
                    <div>
                        <select id="withdrawFilter" class="form-control" style="width: auto; display: inline-block;" onchange="filterWithdrawals()">
                            <option value="all">All</option>
                            <option value="pending">Pending</option>
                            <option value="completed">Completed</option>
                            <option value="rejected">Rejected</option>
                        </select>
                    </div>
                </div>
                <div class="table-responsive">
                    <table id="withdrawalsTable">
                        <thead>
                            <tr>
                                <th>TxID</th>
                                <th>User</th>
                                <th>Amount</th>
                                <th>UPI</th>
                                <th>Status</th>
                                <th>Date</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for w in withdrawals %}
                            <tr data-status="{{ w.status }}">
                                <td><span class="badge badge-info">{{ w.tx_id }}</span></td>
                                <td>{{ w.name }}<br><small>{{ w.user_id }}</small></td>
                                <td><span class="badge {% if w.status == 'completed' %}badge-success{% elif w.status == 'pending' %}badge-warning{% else %}badge-danger{% endif %}">₹{{ w.amount }}</span></td>
                                <td>{{ w.upi }}</td>
                                <td>
                                    <span class="badge {% if w.status == 'completed' %}badge-success{% elif w.status == 'pending' %}badge-warning{% else %}badge-danger{% endif %}">
                                        {{ w.status|upper }}
                                    </span>
                                </td>
                                <td>{{ w.created_at[:10] }}</td>
                                <td>
                                    {% if w.status == 'pending' %}
                                    <button class="btn btn-sm btn-success" onclick="openApproveModal('{{ w.tx_id }}')"><i class="fas fa-check"></i></button>
                                    <button class="btn btn-sm btn-danger" onclick="rejectWithdrawal('{{ w.tx_id }}')"><i class="fas fa-times"></i></button>
                                    {% elif w.status == 'completed' %}
                                    <span class="badge badge-success">{{ w.utr }}</span>
                                    {% endif %}
                                </td>
                            </tr>
                            {% else %}
                            <tr>
                                <td colspan="7" style="text-align: center; padding: 30px; color: #aaa;">
                                    <i class="fas fa-inbox" style="font-size: 40px; margin-bottom: 10px; display: block;"></i>
                                    No withdrawals found
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        
        <!-- Users Tab -->
        <div id="tab-users" class="tab">
            <div class="card">
                <div class="card-header">
                    <h2><i class="fas fa-users"></i> Users Management</h2>
                    <div class="search-box" style="width: 300px;">
                        <i class="fas fa-search"></i>
                        <input type="text" id="userSearch" placeholder="Search users..." onkeyup="searchUsers()">
                    </div>
                </div>
                <div id="usersList">
                    {% for user in users %}
                    <div class="user-item" onclick="openUserModal('{{ user.user_id }}', '{{ user.name }}', '{{ user.username }}', {{ user.balance }}, {{ user.verified }}, {{ user.device_verified }}, '{{ user.refer_code }}', {{ user.referred_users|length }})">
                        <div class="user-header">
                            <div>
                                <span class="user-name">{{ user.name }}</span>
                                {% if user.username %}
                                <span style="color: #aaa; font-size: 12px;"> @{{ user.username }}</span>
                                {% endif %}
                            </div>
                            <span class="user-balance">₹{{ "%.2f"|format(user.balance) }}</span>
                        </div>
                        <div class="user-stats">
                            <span><i class="fas fa-id-card"></i> {{ user.user_id[:8] }}...</span>
                            <span><i class="fas fa-code"></i> {{ user.refer_code }}</span>
                            <span><i class="fas fa-users"></i> {{ user.referred_users|length }} refers</span>
                            <span>
                                {% if user.verified %}
                                <span class="badge badge-success"><i class="fas fa-check-circle"></i> Verified</span>
                                {% else %}
                                <span class="badge badge-warning"><i class="fas fa-clock"></i> Pending</span>
                                {% endif %}
                            </span>
                        </div>
                    </div>
                    {% else %}
                    <div style="text-align: center; padding: 50px; color: #aaa;">
                        <i class="fas fa-users" style="font-size: 50px; margin-bottom: 15px; display: block;"></i>
                        No users found
                    </div>
                    {% endfor %}
                </div>
            </div>
        </div>
        
        <!-- Channels Tab -->
        <div id="tab-channels" class="tab">
            <div class="card">
                <div class="card-header">
                    <h2><i class="fas fa-plus-circle"></i> Add New Channel</h2>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>Channel Name</label>
                        <input type="text" id="channelName" class="form-control" placeholder="e.g., News Channel">
                    </div>
                    <div class="form-group">
                        <label>Channel Link</label>
                        <input type="text" id="channelLink" class="form-control" placeholder="https://t.me/...">
                    </div>
                    <div class="form-group">
                        <label>Channel ID</label>
                        <input type="text" id="channelId" class="form-control" placeholder="@channel or -100...">
                    </div>
                </div>
                <button class="btn btn-primary" onclick="addChannel()"><i class="fas fa-plus"></i> Add Channel</button>
            </div>
            
            <div class="card">
                <div class="card-header">
                    <h2><i class="fas fa-list"></i> Current Channels</h2>
                </div>
                <div id="channelsList">
                    {% for ch in settings.channels %}
                    <div class="channel-item">
                        <div class="channel-info">
                            <h4>{{ ch.btn_name }}</h4>
                            <p><i class="fas fa-link"></i> {{ ch.link[:50] }}{% if ch.link|length > 50 %}...{% endif %}</p>
                            <p><i class="fas fa-id-card"></i> {{ ch.id }}</p>
                            {% if ch.disabled %}
                            <span class="badge badge-danger">Disabled</span>
                            {% else %}
                            <span class="badge badge-success">Active</span>
                            {% endif %}
                        </div>
                        <div class="channel-actions">
                            <button class="btn btn-sm btn-warning" onclick="toggleChannel({{ loop.index0 }})">
                                <i class="fas {% if ch.disabled %}fa-play{% else %}fa-pause{% endif %}"></i>
                            </button>
                            <button class="btn btn-sm btn-danger" onclick="deleteChannel({{ loop.index0 }})">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </div>
                    {% else %}
                    <div style="text-align: center; padding: 30px; color: #aaa;">
                        <i class="fas fa-tv" style="font-size: 40px; margin-bottom: 10px; display: block;"></i>
                        No channels added yet
                    </div>
                    {% endfor %}
                </div>
            </div>
        </div>
        
        <!-- Gift Codes Tab -->
        <div id="tab-gifts" class="tab">
            <div class="card">
                <div class="card-header">
                    <h2><i class="fas fa-gift"></i> Create Gift Code</h2>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>Gift Code</label>
                        <div style="display: flex; gap: 10px;">
                            <input type="text" id="giftCode" class="form-control" placeholder="5-digit code" maxlength="5" style="text-transform: uppercase;">
                            <button class="btn btn-info" onclick="generateCode()"><i class="fas fa-random"></i> Generate</button>
                        </div>
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>Min Amount (₹)</label>
                        <input type="number" id="giftMin" class="form-control" value="10" step="0.01">
                    </div>
                    <div class="form-group">
                        <label>Max Amount (₹)</label>
                        <input type="number" id="giftMax" class="form-control" value="50" step="0.01">
                    </div>
                    <div class="form-group">
                        <label>Expiry (Hours)</label>
                        <input type="number" id="giftExpiry" class="form-control" value="24">
                    </div>
                    <div class="form-group">
                        <label>Total Uses</label>
                        <input type="number" id="giftUses" class="form-control" value="1">
                    </div>
                </div>
                <button class="btn btn-primary" onclick="createGift()"><i class="fas fa-plus"></i> Create Gift Code</button>
            </div>
            
            <div class="card">
                <div class="card-header">
                    <h2><i class="fas fa-list"></i> Active Gift Codes</h2>
                </div>
                <div id="giftsList">
                    {% for gift in gifts %}
                    <div class="gift-item {% if gift.expired %}gift-expired{% endif %}">
                        <div>
                            <div class="gift-code">{{ gift.code }}</div>
                            <div class="gift-details">
                                <span><i class="fas fa-rupee-sign"></i> ₹{{ gift.min_amount }} - ₹{{ gift.max_amount }}</span>
                                <span><i class="fas fa-clock"></i> Expires: {{ gift.expiry[:10] }}</span>
                                <span><i class="fas fa-users"></i> {{ gift.used_by|length }}/{{ gift.total_uses }} uses</span>
                            </div>
                        </div>
                        <div>
                            <button class="btn btn-sm btn-warning" onclick="toggleGift('{{ gift.code }}')">
                                <i class="fas {% if gift.is_active %}fa-pause{% else %}fa-play{% endif %}"></i>
                            </button>
                            <button class="btn btn-sm btn-danger" onclick="deleteGift('{{ gift.code }}')">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </div>
                    {% else %}
                    <div style="text-align: center; padding: 30px; color: #aaa;">
                        <i class="fas fa-gift" style="font-size: 40px; margin-bottom: 10px; display: block;"></i>
                        No gift codes created yet
                    </div>
                    {% endfor %}
                </div>
            </div>
        </div>
        
        <!-- Settings Tab -->
        <div id="tab-settings" class="tab">
            <div class="card">
                <div class="card-header">
                    <h2><i class="fas fa-cog"></i> Bot Settings</h2>
                </div>
                <div class="form-group">
                    <label>Bot Name</label>
                    <input type="text" id="botName" class="form-control" value="{{ settings.bot_name }}">
                </div>
                <div class="form-group">
                    <label>App Display Name</label>
                    <input type="text" id="appName" class="form-control" value="{{ settings.app_name }}">
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>Min Withdrawal (₹)</label>
                        <input type="number" id="minWithdrawal" class="form-control" value="{{ settings.min_withdrawal }}" step="0.01">
                    </div>
                    <div class="form-group">
                        <label>Welcome Bonus (₹)</label>
                        <input type="number" id="welcomeBonus" class="form-control" value="{{ settings.welcome_bonus }}" step="0.01">
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>Min Refer Reward (₹)</label>
                        <input type="number" id="minRefer" class="form-control" value="{{ settings.min_refer_reward }}" step="0.01">
                    </div>
                    <div class="form-group">
                        <label>Max Refer Reward (₹)</label>
                        <input type="number" id="maxRefer" class="form-control" value="{{ settings.max_refer_reward }}" step="0.01">
                    </div>
                </div>
                
                <div class="toggle-label">
                    <span>Disable Bot for Users</span>
                    <label class="toggle-switch">
                        <input type="checkbox" id="botsDisabled" {% if settings.bots_disabled %}checked{% endif %}>
                        <span class="toggle-slider"></span>
                    </label>
                </div>
                
                <div class="toggle-label">
                    <span>Auto Withdraw (Instant Payment)</span>
                    <label class="toggle-switch">
                        <input type="checkbox" id="autoWithdraw" {% if settings.auto_withdraw %}checked{% endif %}>
                        <span class="toggle-slider"></span>
                    </label>
                </div>
                
                <div class="toggle-label">
                    <span>Ignore Device Check (Allow multiple accounts)</span>
                    <label class="toggle-switch">
                        <input type="checkbox" id="ignoreDevice" {% if settings.ignore_device_check %}checked{% endif %}>
                        <span class="toggle-slider"></span>
                    </label>
                </div>
                
                <div class="toggle-label">
                    <span>Disable Withdrawals</span>
                    <label class="toggle-switch">
                        <input type="checkbox" id="withdrawDisabled" {% if settings.withdraw_disabled %}checked{% endif %}>
                        <span class="toggle-slider"></span>
                    </label>
                </div>
                
                <div class="toggle-label">
                    <span>Disable Channel Verification</span>
                    <label class="toggle-switch">
                        <input type="checkbox" id="disableChannelVerification" {% if settings.disable_channel_verification %}checked{% endif %}>
                        <span class="toggle-slider"></span>
                    </label>
                </div>
                
                <div class="toggle-label">
                    <span>Auto Accept Private Channels</span>
                    <label class="toggle-switch">
                        <input type="checkbox" id="autoAcceptPrivate" {% if settings.auto_accept_private %}checked{% endif %}>
                        <span class="toggle-slider"></span>
                    </label>
                </div>
                
                <div class="toggle-label">
                    <span>Hide Verify Button in App</span>
                    <label class="toggle-switch">
                        <input type="checkbox" id="hideVerifyButton" {% if settings.hide_verify_button %}checked{% endif %}>
                        <span class="toggle-slider"></span>
                    </label>
                </div>
                
                <button class="btn btn-primary" onclick="saveSettings()"><i class="fas fa-save"></i> Save Settings</button>
            </div>
            
            <div class="card">
                <div class="card-header">
                    <h2><i class="fas fa-image"></i> Upload Logo</h2>
                </div>
                <div class="form-group">
                    <label>Select Logo Image</label>
                    <input type="file" id="logoFile" class="form-control" accept="image/*">
                </div>
                <button class="btn btn-primary" onclick="uploadLogo()"><i class="fas fa-upload"></i> Upload Logo</button>
                <p style="color: #aaa; margin-top: 10px; font-size: 12px;">Current: {{ settings.logo_filename }}</p>
            </div>
        </div>
        
        <!-- UPI Settings Tab -->
        <div id="tab-upi" class="tab">
            <div class="card">
                <div class="card-header">
                    <h2><i class="fas fa-credit-card"></i> UPI Payment Settings</h2>
                </div>
                
                <div class="toggle-label">
                    <span>Enable UPI Payments</span>
                    <label class="toggle-switch">
                        <input type="checkbox" id="upiEnabled" {% if settings.upi_enabled %}checked{% endif %}>
                        <span class="toggle-slider"></span>
                    </label>
                </div>
                
                <div class="form-group">
                    <label>Payment Mode</label>
                    <select id="upiMode" class="form-control">
                        <option value="manual" {% if settings.upi_mode == 'manual' %}selected{% endif %}>Manual (Admin Approval)</option>
                        <option value="auto" {% if settings.upi_mode == 'auto' %}selected{% endif %}>Auto (API Payment)</option>
                        <option value="fake" {% if settings.upi_mode == 'fake' %}selected{% endif %}>Fake (Test Mode)</option>
                    </select>
                </div>
                
                <div class="form-group">
                    <label>API Token</label>
                    <input type="text" id="upiToken" class="form-control" value="{{ settings.upi_token }}">
                </div>
                
                <div class="form-group">
                    <label>API Key</label>
                    <input type="text" id="upiKey" class="form-control" value="{{ settings.upi_key }}">
                </div>
                
                <div class="form-group">
                    <label>Receiver UPI ID</label>
                    <input type="text" id="upiReceiver" class="form-control" value="{{ settings.upi_receiver }}" placeholder="receiver@upi">
                </div>
                
                <div class="form-group">
                    <label>API URL</label>
                    <input type="text" id="upiApiUrl" class="form-control" value="{{ settings.upi_api_url }}">
                </div>
                
                <button class="btn btn-info" onclick="checkUPIBalance()"><i class="fas fa-wallet"></i> Check Balance</button>
                <button class="btn btn-primary" onclick="saveUPISettings()"><i class="fas fa-save"></i> Save UPI Settings</button>
                
                <div id="balanceInfo" style="margin-top: 20px; padding: 15px; background: #353535; border-radius: 8px; display: none;">
                    <h3><i class="fas fa-info-circle"></i> Balance Info</h3>
                    <p id="balanceAmount" style="font-size: 24px; color: #4CAF50;">₹0.00</p>
                    <p id="balanceStatus"></p>
                </div>
            </div>
        </div>
        
        <!-- Broadcast Tab -->
        <div id="tab-broadcast" class="tab">
            <div class="card">
                <div class="card-header">
                    <h2><i class="fas fa-broadcast-tower"></i> Send Broadcast</h2>
                </div>
                <div class="form-group">
                    <label>Message</label>
                    <textarea id="broadcastMessage" class="form-control" rows="5" placeholder="Enter your message..."></textarea>
                </div>
                <div class="form-group">
                    <label>Image (Optional)</label>
                    <input type="file" id="broadcastImage" class="form-control" accept="image/*">
                </div>
                <button class="btn btn-primary" onclick="sendBroadcast()"><i class="fas fa-paper-plane"></i> Send to All Users ({{ stats.total_users }})</button>
            </div>
        </div>
    </div>
    
    <!-- Approve Modal -->
    <div id="approveModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3><i class="fas fa-check-circle"></i> Approve Withdrawal</h3>
                <button class="modal-close" onclick="closeModal('approveModal')">&times;</button>
            </div>
            <div class="form-group">
                <label>UTR Number</label>
                <input type="text" id="utrNumber" class="form-control" placeholder="Enter UTR/Transaction ID">
            </div>
            <button class="btn btn-success" onclick="approveWithdrawal()"><i class="fas fa-check"></i> Approve Payment</button>
            <button class="btn btn-danger" onclick="closeModal('approveModal')" style="margin-top: 10px;">Cancel</button>
        </div>
    </div>
    
    <!-- User Message Modal -->
    <div id="userModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3><i class="fas fa-user"></i> Send Message to User</h3>
                <button class="modal-close" onclick="closeModal('userModal')">&times;</button>
            </div>
            <div id="userInfo" style="background: #353535; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                <!-- User info will be inserted here -->
            </div>
            <div class="form-group">
                <label>Message</label>
                <textarea id="userMessage" class="form-control" rows="4" placeholder="Type your message..."></textarea>
            </div>
            <div class="form-group">
                <label>Image (Optional)</label>
                <input type="file" id="userImage" class="form-control" accept="image/*">
            </div>
            <button class="btn btn-primary" onclick="sendUserMessage()"><i class="fas fa-paper-plane"></i> Send Message</button>
            <button class="btn btn-danger" onclick="closeModal('userModal')" style="margin-top: 10px;">Cancel</button>
        </div>
    </div>
    
    <script>
        // Current state
        let currentTxId = '';
        let currentUserId = '';
        
        // Tab switching
        function switchTab(tabName) {
            document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
            document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
            
            document.getElementById('tab-' + tabName).classList.add('active');
            event.target.closest('.nav-btn').classList.add('active');
        }
        
        // Loader functions
        function showLoader(text = 'Processing...') {
            document.getElementById('loaderText').textContent = text;
            document.getElementById('loader').classList.add('active');
        }
        
        function hideLoader() {
            document.getElementById('loader').classList.remove('active');
        }
        
        // Toast functions
        function showToast(message, type = 'success') {
            const toast = document.getElementById('toast');
            const toastMessage = document.getElementById('toastMessage');
            
            toast.className = 'toast ' + type;
            toastMessage.textContent = message;
            toast.classList.add('show');
            
            setTimeout(() => {
                toast.classList.remove('show');
            }, 3000);
        }
        
        // Modal functions
        function openModal(modalId) {
            document.getElementById(modalId).classList.add('active');
        }
        
        function closeModal(modalId) {
            document.getElementById(modalId).classList.remove('active');
        }
        
        // Withdrawal functions
        function openApproveModal(txId) {
            currentTxId = txId;
            document.getElementById('utrNumber').value = '';
            openModal('approveModal');
        }
        
        function approveWithdrawal() {
            const utr = document.getElementById('utrNumber').value.trim();
            if (!utr) {
                showToast('Please enter UTR number', 'error');
                return;
            }
            
            showLoader('Processing approval...');
            
            fetch('/admin/process_withdrawal', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    tx_id: currentTxId,
                    action: 'approve',
                    utr: utr
                })
            })
            .then(r => r.json())
            .then(data => {
                hideLoader();
                closeModal('approveModal');
                if (data.ok) {
                    showToast('Withdrawal approved successfully!');
                    setTimeout(() => location.reload(), 1000);
                } else {
                    showToast(data.msg || 'Error approving withdrawal', 'error');
                }
            })
            .catch(err => {
                hideLoader();
                showToast('Error: ' + err.message, 'error');
            });
        }
        
        function rejectWithdrawal(txId) {
            if (!confirm('Are you sure you want to reject this withdrawal?')) return;
            
            showLoader('Rejecting withdrawal...');
            
            fetch('/admin/process_withdrawal', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    tx_id: txId,
                    action: 'reject'
                })
            })
            .then(r => r.json())
            .then(data => {
                hideLoader();
                if (data.ok) {
                    showToast('Withdrawal rejected and refunded');
                    setTimeout(() => location.reload(), 1000);
                } else {
                    showToast(data.msg || 'Error rejecting withdrawal', 'error');
                }
            })
            .catch(err => {
                hideLoader();
                showToast('Error: ' + err.message, 'error');
            });
        }
        
        function filterWithdrawals() {
            const filter = document.getElementById('withdrawFilter').value;
            const rows = document.querySelectorAll('#withdrawalsTable tbody tr');
            
            rows.forEach(row => {
                if (filter === 'all' || row.dataset.status === filter) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            });
        }
        
        // User functions
        function openUserModal(userId, name, username, balance, verified, deviceVerified, referCode, referCount) {
            currentUserId = userId;
            
            const userInfo = document.getElementById('userInfo');
            userInfo.innerHTML = `
                <p><strong>ID:</strong> ${userId}</p>
                <p><strong>Name:</strong> ${name} ${username ? '(@' + username + ')' : ''}</p>
                <p><strong>Balance:</strong> ₹${balance.toFixed(2)}</p>
                <p><strong>Status:</strong> ${verified ? '✅ Verified' : '⏳ Pending'}</p>
                <p><strong>Device:</strong> ${deviceVerified ? '✅ Verified' : '❌ Not Verified'}</p>
                <p><strong>Refer Code:</strong> ${referCode}</p>
                <p><strong>Referrals:</strong> ${referCount}</p>
            `;
            
            document.getElementById('userMessage').value = '';
            document.getElementById('userImage').value = '';
            
            openModal('userModal');
        }
        
        function sendUserMessage() {
            const message = document.getElementById('userMessage').value.trim();
            const image = document.getElementById('userImage').files[0];
            
            if (!message) {
                showToast('Please enter a message', 'error');
                return;
            }
            
            showLoader('Sending message...');
            
            const formData = new FormData();
            formData.append('user_id', currentUserId);
            formData.append('message', message);
            if (image) {
                formData.append('image', image);
            }
            
            fetch('/admin/send_to_user', {
                method: 'POST',
                body: formData
            })
            .then(r => r.json())
            .then(data => {
                hideLoader();
                closeModal('userModal');
                if (data.ok) {
                    showToast('Message sent successfully!');
                } else {
                    showToast(data.msg || 'Error sending message', 'error');
                }
            })
            .catch(err => {
                hideLoader();
                showToast('Error: ' + err.message, 'error');
            });
        }
        
        function searchUsers() {
            const search = document.getElementById('userSearch').value.toLowerCase();
            const users = document.querySelectorAll('.user-item');
            
            users.forEach(user => {
                const text = user.textContent.toLowerCase();
                if (text.includes(search)) {
                    user.style.display = '';
                } else {
                    user.style.display = 'none';
                }
            });
        }
        
        // Channel functions
        function addChannel() {
            const name = document.getElementById('channelName').value.trim();
            const link = document.getElementById('channelLink').value.trim();
            const id = document.getElementById('channelId').value.trim();
            
            if (!name || !link || !id) {
                showToast('Please fill all fields', 'error');
                return;
            }
            
            showLoader('Adding channel...');
            
            fetch('/admin/channels', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    action: 'add',
                    name: name,
                    link: link,
                    id: id
                })
            })
            .then(r => r.json())
            .then(data => {
                hideLoader();
                if (data.ok) {
                    showToast('Channel added successfully!');
                    setTimeout(() => location.reload(), 1000);
                } else {
                    showToast(data.msg || 'Error adding channel', 'error');
                }
            })
            .catch(err => {
                hideLoader();
                showToast('Error: ' + err.message, 'error');
            });
        }
        
        function toggleChannel(index) {
            showLoader('Toggling channel...');
            
            fetch('/admin/channels', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    action: 'toggle',
                    index: index
                })
            })
            .then(r => r.json())
            .then(data => {
                hideLoader();
                if (data.ok) {
                    location.reload();
                } else {
                    showToast(data.msg || 'Error toggling channel', 'error');
                }
            })
            .catch(err => {
                hideLoader();
                showToast('Error: ' + err.message, 'error');
            });
        }
        
        function deleteChannel(index) {
            if (!confirm('Are you sure you want to delete this channel?')) return;
            
            showLoader('Deleting channel...');
            
            fetch('/admin/channels', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    action: 'delete',
                    index: index
                })
            })
            .then(r => r.json())
            .then(data => {
                hideLoader();
                if (data.ok) {
                    location.reload();
                } else {
                    showToast(data.msg || 'Error deleting channel', 'error');
                }
            })
            .catch(err => {
                hideLoader();
                showToast('Error: ' + err.message, 'error');
            });
        }
        
        // Gift code functions
        function generateCode() {
            const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
            let code = '';
            for (let i = 0; i < 5; i++) {
                code += chars.charAt(Math.floor(Math.random() * chars.length));
            }
            document.getElementById('giftCode').value = code;
        }
        
        function createGift() {
            const code = document.getElementById('giftCode').value.trim().toUpperCase();
            const minAmt = parseFloat(document.getElementById('giftMin').value);
            const maxAmt = parseFloat(document.getElementById('giftMax').value);
            const expiry = parseInt(document.getElementById('giftExpiry').value);
            const uses = parseInt(document.getElementById('giftUses').value);
            
            if (!code || code.length !== 5) {
                showToast('Please enter a valid 5-character code', 'error');
                return;
            }
            
            if (minAmt >= maxAmt) {
                showToast('Max amount must be greater than min amount', 'error');
                return;
            }
            
            showLoader('Creating gift code...');
            
            fetch('/admin/create_gift', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    code: code,
                    min_amount: minAmt,
                    max_amount: maxAmt,
                    expiry_hours: expiry,
                    total_uses: uses
                })
            })
            .then(r => r.json())
            .then(data => {
                hideLoader();
                if (data.ok) {
                    showToast('Gift code created: ' + data.code);
                    setTimeout(() => location.reload(), 1000);
                } else {
                    showToast(data.msg || 'Error creating gift code', 'error');
                }
            })
            .catch(err => {
                hideLoader();
                showToast('Error: ' + err.message, 'error');
            });
        }
        
        function toggleGift(code) {
            showLoader('Toggling gift code...');
            
            fetch('/admin/toggle_gift', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    code: code,
                    action: 'toggle'
                })
            })
            .then(r => r.json())
            .then(data => {
                hideLoader();
                if (data.ok) {
                    location.reload();
                } else {
                    showToast(data.msg || 'Error toggling gift code', 'error');
                }
            })
            .catch(err => {
                hideLoader();
                showToast('Error: ' + err.message, 'error');
            });
        }
        
        function deleteGift(code) {
            if (!confirm('Are you sure you want to delete this gift code?')) return;
            
            showLoader('Deleting gift code...');
            
            fetch('/admin/toggle_gift', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    code: code,
                    action: 'delete'
                })
            })
            .then(r => r.json())
            .then(data => {
                hideLoader();
                if (data.ok) {
                    location.reload();
                } else {
                    showToast(data.msg || 'Error deleting gift code', 'error');
                }
            })
            .catch(err => {
                hideLoader();
                showToast('Error: ' + err.message, 'error');
            });
        }
        
        // Settings functions
        function saveSettings() {
            const data = {
                bot_name: document.getElementById('botName').value,
                app_name: document.getElementById('appName').value,
                min_withdrawal: parseFloat(document.getElementById('minWithdrawal').value),
                welcome_bonus: parseFloat(document.getElementById('welcomeBonus').value),
                min_refer_reward: parseFloat(document.getElementById('minRefer').value),
                max_refer_reward: parseFloat(document.getElementById('maxRefer').value),
                bots_disabled: document.getElementById('botsDisabled').checked,
                auto_withdraw: document.getElementById('autoWithdraw').checked,
                ignore_device_check: document.getElementById('ignoreDevice').checked,
                withdraw_disabled: document.getElementById('withdrawDisabled').checked,
                disable_channel_verification: document.getElementById('disableChannelVerification').checked,
                auto_accept_private: document.getElementById('autoAcceptPrivate').checked,
                hide_verify_button: document.getElementById('hideVerifyButton').checked
            };
            
            showLoader('Saving settings...');
            
            fetch('/admin/update_settings', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            })
            .then(r => r.json())
            .then(data => {
                hideLoader();
                if (data.ok) {
                    showToast('Settings saved successfully!');
                } else {
                    showToast(data.msg || 'Error saving settings', 'error');
                }
            })
            .catch(err => {
                hideLoader();
                showToast('Error: ' + err.message, 'error');
            });
        }
        
        function uploadLogo() {
            const file = document.getElementById('logoFile').files[0];
            if (!file) {
                showToast('Please select a file', 'error');
                return;
            }
            
            showLoader('Uploading logo...');
            
            const formData = new FormData();
            formData.append('logo', file);
            
            fetch('/admin/upload_logo', {
                method: 'POST',
                body: formData
            })
            .then(r => r.json())
            .then(data => {
                hideLoader();
                if (data.ok) {
                    showToast('Logo uploaded successfully!');
                    setTimeout(() => location.reload(), 1000);
                } else {
                    showToast(data.msg || 'Error uploading logo', 'error');
                }
            })
            .catch(err => {
                hideLoader();
                showToast('Error: ' + err.message, 'error');
            });
        }
        
        // UPI functions
        function saveUPISettings() {
            const data = {
                upi_enabled: document.getElementById('upiEnabled').checked,
                upi_mode: document.getElementById('upiMode').value,
                upi_token: document.getElementById('upiToken').value,
                upi_key: document.getElementById('upiKey').value,
                upi_receiver: document.getElementById('upiReceiver').value,
                upi_api_url: document.getElementById('upiApiUrl').value
            };
            
            showLoader('Saving UPI settings...');
            
            fetch('/admin/update_upi_settings', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            })
            .then(r => r.json())
            .then(data => {
                hideLoader();
                if (data.ok) {
                    showToast('UPI settings saved successfully!');
                } else {
                    showToast(data.msg || 'Error saving UPI settings', 'error');
                }
            })
            .catch(err => {
                hideLoader();
                showToast('Error: ' + err.message, 'error');
            });
        }
        
        function checkUPIBalance() {
            showLoader('Checking balance...');
            
            fetch('/admin/check_upi_balance')
            .then(r => r.json())
            .then(data => {
                hideLoader();
                
                const balanceInfo = document.getElementById('balanceInfo');
                const balanceAmount = document.getElementById('balanceAmount');
                const balanceStatus = document.getElementById('balanceStatus');
                
                if (data.status === 'success') {
                    balanceAmount.textContent = '₹' + data.balance.toFixed(2);
                    balanceStatus.textContent = 'Balance updated successfully';
                    balanceStatus.style.color = '#4CAF50';
                } else if (data.status === 'manual') {
                    balanceAmount.textContent = 'N/A';
                    balanceStatus.textContent = 'Manual mode - balance check not available';
                    balanceStatus.style.color = '#ff9800';
                } else {
                    balanceAmount.textContent = 'Error';
                    balanceStatus.textContent = data.message || 'Failed to check balance';
                    balanceStatus.style.color = '#f44336';
                }
                
                balanceInfo.style.display = 'block';
            })
            .catch(err => {
                hideLoader();
                showToast('Error: ' + err.message, 'error');
            });
        }
        
        // Broadcast functions
        function sendBroadcast() {
            const message = document.getElementById('broadcastMessage').value.trim();
            const image = document.getElementById('broadcastImage').files[0];
            
            if (!message) {
                showToast('Please enter a message', 'error');
                return;
            }
            
            if (!confirm('Send this message to all users?')) return;
            
            showLoader('Sending broadcast...');
            
            const formData = new FormData();
            formData.append('message', message);
            if (image) {
                formData.append('image', image);
            }
            
            fetch('/admin/broadcast', {
                method: 'POST',
                body: formData
            })
            .then(r => r.json())
            .then(data => {
                hideLoader();
                if (data.ok) {
                    showToast(`Broadcast sent to ${data.sent}/${data.total} users`);
                    document.getElementById('broadcastMessage').value = '';
                    document.getElementById('broadcastImage').value = '';
                } else {
                    showToast(data.msg || 'Error sending broadcast', 'error');
                }
            })
            .catch(err => {
                hideLoader();
                showToast('Error: ' + err.message, 'error');
            });
        }
        
        // Close modals when clicking outside
        window.onclick = function(event) {
            if (event.target.classList.contains('modal')) {
                event.target.classList.remove('active');
            }
        }
        
        // Generate initial code on page load
        window.onload = function() {
            generateCode();
        }
    </script>
</body>
</html>
"""

# ==================== START APP ====================
if __name__ == '__main__':
    # Create default logo if not exists
    default_logo_path = os.path.join(STATIC_DIR, 'logo_default.png')
    if not os.path.exists(default_logo_path):
        # Create a simple default logo
        try:
            from PIL import Image, ImageDraw
            img = Image.new('RGB', (512, 512), color=(102, 126, 234))
            d = ImageDraw.Draw(img)
            d.text((256, 256), "💰", fill=(255, 255, 255), anchor="mm", font_size=200)
            img.save(default_logo_path)
        except:
            # If PIL not available, create a simple text file
            with open(default_logo_path, 'wb') as f:
                f.write(b'')
    
    # Set webhook on startup
    with app.app_context():
        try:
            webhook_url = f"https://{BASE_URL}/webhook"
            bot.remove_webhook()
            time.sleep(1)
            bot.set_webhook(url=webhook_url)
            logger.info(f"✅ Webhook set to {webhook_url}")
        except Exception as e:
            logger.error(f"❌ Failed to set webhook: {e}")
    
    # Start Flask app
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
