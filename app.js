
const { Telegraf, session: telegrafSession, Markup } = require('telegraf');
const { MongoClient, ObjectId } = require('mongodb');
const schedule = require('node-schedule');
const express = require('express');
const path = require('path');
const crypto = require('crypto');
const fs = require('fs');
const axios = require('axios');
const multer = require('multer');
const moment = require('moment-timezone');

// ==========================================
// ⚙️ CONFIGURATION
// ==========================================
const BOT_TOKEN = '8280352331:AAHQ4EvZlvP6lMY7XgNaCxWEs0lX2B-Iwqs';
const MONGODB_URI = 'mongodb+srv://sandip:9E9AISFqTfU3VI5i@cluster0.p8irtov.mongodb.net/refer_earn';
const PORT = process.env.PORT || 8080;
const WEB_APP_URL = 'https://web-production-3dfc9.up.railway.app';
const ADMIN_IDS = [8469993808]; // Add your admin IDs here
const EASEPAY_API = 'https://easepay.site/upiapi.php?token=0127d8b8b09c9f3c6674dd5d676a6e17&key=25d33a0508f8249ebf03ee2b36cc019e&upiid={upi_id}&amount={amount}';

// ==========================================
// 🕐 TIMEZONE (IST)
// ==========================================
const IST_OFFSET_MS = (5 * 60 + 30) * 60 * 1000;

const app = express();
const upload = multer({ dest: 'uploads/' });

// ==========================================
// 📁 DIRECTORY SETUP
// ==========================================
const viewsDir = path.join(__dirname, 'views');
const publicDir = path.join(__dirname, 'public');
const uploadsDir = path.join(__dirname, 'uploads');

[viewsDir, publicDir, uploadsDir].forEach(dir => {
    if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
    }
});

app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(express.static(publicDir));
app.use('/uploads', express.static(uploadsDir));

app.set('view engine', 'ejs');
app.set('views', viewsDir);

// ==========================================
// 🕐 TIME FUNCTIONS
// ==========================================
function getIST() {
    const now = new Date();
    return new Date(now.getTime() + IST_OFFSET_MS);
}

function formatIST(date) {
    if (!date) return '';
    const ist = new Date(date.getTime() + IST_OFFSET_MS);
    return ist.toISOString().replace('T', ' ').substring(0, 19);
}

// ==========================================
// 🗄️ DATABASE CONNECTION
// ==========================================
let db;
let client;

async function connectDB() {
    try {
        client = new MongoClient(MONGODB_URI);
        await client.connect();
        db = client.db('refer_earn');
        
        // Create indexes
        await db.collection('users').createIndex({ userId: 1 }, { unique: true });
        await db.collection('users').createIndex({ referCode: 1 }, { unique: true });
        await db.collection('users').createIndex({ deviceId: 1 });
        await db.collection('users').createIndex({ ip: 1 });
        
        await db.collection('channels').createIndex({ position: 1 });
        
        await db.collection('giftCodes').createIndex({ code: 1 }, { unique: true });
        await db.collection('giftCodes').createIndex({ expiresAt: 1 });
        
        await db.collection('withdrawals').createIndex({ status: 1 });
        await db.collection('withdrawals').createIndex({ userId: 1 });
        
        await db.collection('transactions').createIndex({ userId: 1 });
        await db.collection('transactions').createIndex({ createdAt: -1 });
        
        await db.collection('referrals').createIndex({ referrerId: 1 });
        await db.collection('referrals').createIndex({ referredId: 1 }, { unique: true });
        
        await db.collection('settings').createIndex({ key: 1 }, { unique: true });
        
        // Initialize settings
        await initializeSettings();
        
        console.log('✅ MongoDB Connected');
        return true;
    } catch (error) {
        console.error('❌ MongoDB Error:', error.message);
        return false;
    }
}

async function initializeSettings() {
    const defaultSettings = {
        botName: 'Auto VFX Bot',
        botLogo: 'https://via.placeholder.com/100',
        minWithdraw: 50,
        maxWithdraw: 10000,
        referBonus: 10,
        welcomeBonus: 5,
        withdrawTax: 5, // percentage
        minGiftAmount: 10,
        maxGiftAmount: 1000,
        
        // Toggles
        botEnabled: true,
        deviceVerification: true,
        autoWithdraw: false,
        withdrawalsEnabled: true,
        channelVerification: true,
        autoAcceptPrivate: false,
        
        // UPI Settings
        upiEnabled: true,
        upiId: '',
        upiName: '',
        
        // Admin
        adminIds: ADMIN_IDS
    };
    
    for (const [key, value] of Object.entries(defaultSettings)) {
        await db.collection('settings').updateOne(
            { key },
            { $setOnInsert: { value } },
            { upsert: true }
        );
    }
}

// ==========================================
// 🎨 EJS TEMPLATES
// ==========================================
function createEJSFiles() {
    // Main Web App Template
    const mainEJS = `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=yes">
    <title><%= settings.botName %></title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        :root {
            --bg: #0f172a;
            --card: #1e293b;
            --text: #f8fafc;
            --text-secondary: #cbd5e1;
            --border: #334155;
            --accent: #60a5fa;
            --accent-soft: #1e3a5f;
            --success: #34d399;
            --warning: #fbbf24;
            --danger: #f87171;
            --gold: #fbbf24;
            --silver: #94a3b8;
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }
        
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
        
        body {
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
            font-size: 14px;
        }
        
        .app-header {
            background: var(--card);
            border-bottom: 1px solid var(--border);
            padding: 12px 16px;
            position: sticky;
            top: 0;
            z-index: 100;
        }
        
        .nav-container {
            max-width: 1200px;
            margin: 0 auto;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        
        .nav-links {
            display: flex;
            gap: 4px;
            background: var(--bg);
            padding: 3px;
            border-radius: 100px;
        }
        
        .nav-btn {
            padding: 8px 20px;
            border-radius: 100px;
            border: none;
            background: transparent;
            color: var(--text-secondary);
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .nav-btn.active {
            background: var(--card);
            color: var(--accent);
        }
        
        .main-content {
            max-width: 1200px;
            margin: 20px auto;
            padding: 0 16px;
            padding-bottom: 80px;
        }
        
        .logo-section {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 20px;
        }
        
        .logo {
            width: 50px;
            height: 50px;
            border-radius: 12px;
        }
        
        .bot-name {
            font-size: 1.5rem;
            font-weight: 700;
            color: var(--accent);
        }
        
        /* Golden Card */
        .golden-card {
            background: linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%);
            border-radius: 16px;
            padding: 16px;
            margin-bottom: 20px;
            color: #000;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        
        .user-avatar {
            width: 50px;
            height: 50px;
            border-radius: 50%;
            background: rgba(255,255,255,0.2);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5rem;
        }
        
        .contact-admin-btn {
            background: rgba(0,0,0,0.2);
            border: none;
            color: white;
            padding: 8px 16px;
            border-radius: 100px;
            cursor: pointer;
            font-weight: 600;
        }
        
        /* Silver Credit Card */
        .credit-card {
            background: linear-gradient(135deg, #e2e8f0 0%, #cbd5e1 100%);
            border-radius: 20px;
            padding: 24px;
            margin-bottom: 20px;
            color: #1e293b;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            position: relative;
            overflow: hidden;
            animation: shine 3s infinite;
        }
        
        @keyframes shine {
            0% { background-position: -100% 0; }
            100% { background-position: 200% 0; }
        }
        
        .credit-card::after {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
            animation: shine 3s infinite;
        }
        
        .card-balance {
            font-size: 2rem;
            font-weight: 700;
            margin: 10px 0;
        }
        
        .progress-bar {
            height: 10px;
            background: rgba(0,0,0,0.1);
            border-radius: 10px;
            overflow: hidden;
            margin: 15px 0;
        }
        
        .progress-fill {
            height: 100%;
            background: var(--accent);
            border-radius: 10px;
            transition: width 0.3s;
        }
        
        .withdraw-btn {
            background: var(--accent);
            color: white;
            border: none;
            padding: 15px;
            border-radius: 12px;
            font-size: 1.2rem;
            font-weight: 700;
            width: 100%;
            cursor: pointer;
            margin-bottom: 20px;
            transition: transform 0.2s;
        }
        
        .withdraw-btn:active {
            transform: scale(0.98);
        }
        
        .gift-box {
            background: var(--card);
            border: 2px solid var(--gold);
            border-radius: 12px;
            padding: 16px;
            display: flex;
            gap: 10px;
        }
        
        .gift-input {
            flex: 1;
            background: var(--bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 12px;
            color: var(--text);
            font-size: 1rem;
            text-transform: uppercase;
        }
        
        .claim-btn {
            background: var(--gold);
            color: #000;
            border: none;
            padding: 0 20px;
            border-radius: 8px;
            font-weight: 700;
            cursor: pointer;
        }
        
        /* Refer Card */
        .refer-card {
            background: var(--card);
            border-radius: 16px;
            padding: 20px;
            margin-bottom: 20px;
            text-align: center;
        }
        
        .refer-code {
            font-size: 2rem;
            font-weight: 700;
            color: var(--accent);
            letter-spacing: 5px;
            margin: 10px 0;
            padding: 10px;
            background: var(--bg);
            border-radius: 12px;
        }
        
        .copy-btn {
            background: var(--accent);
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
        }
        
        /* Transaction History */
        .history-item {
            background: var(--card);
            border-radius: 12px;
            padding: 12px;
            margin-bottom: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .history-amount {
            font-weight: 700;
        }
        
        .credit { color: var(--success); }
        .debit { color: var(--danger); }
        
        /* Modals */
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.8);
            align-items: center;
            justify-content: center;
            z-index: 1000;
        }
        
        .modal-content {
            background: var(--card);
            border-radius: 24px;
            padding: 24px;
            width: 90%;
            max-width: 400px;
        }
        
        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        
        .close-btn {
            background: none;
            border: none;
            color: var(--text);
            font-size: 1.5rem;
            cursor: pointer;
        }
        
        .form-group {
            margin-bottom: 15px;
        }
        
        .form-control {
            width: 100%;
            padding: 12px;
            border-radius: 8px;
            border: 1px solid var(--border);
            background: var(--bg);
            color: var(--text);
        }
        
        .btn {
            padding: 12px 20px;
            border-radius: 8px;
            border: none;
            font-weight: 600;
            cursor: pointer;
            width: 100%;
        }
        
        .btn-primary {
            background: var(--accent);
            color: white;
        }
        
        .btn-success {
            background: var(--success);
            color: white;
        }
        
        /* Toast */
        .toast-container {
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 9999;
        }
        
        .toast {
            background: var(--card);
            color: white;
            padding: 12px 24px;
            border-radius: 8px;
            margin-bottom: 10px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            animation: slideIn 0.3s;
        }
        
        @keyframes slideIn {
            from { transform: translateX(100%); }
            to { transform: translateX(0); }
        }
        
        /* Loader */
        .loader {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.8);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 9998;
        }
        
        .spinner {
            width: 50px;
            height: 50px;
            border: 4px solid var(--border);
            border-top: 4px solid var(--accent);
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        /* Confetti */
        .confetti {
            position: fixed;
            width: 10px;
            height: 10px;
            background: var(--gold);
            animation: confetti 3s ease-out forwards;
            z-index: 9999;
        }
        
        @keyframes confetti {
            0% { transform: translateY(-100vh) rotate(0deg); opacity: 1; }
            100% { transform: translateY(100vh) rotate(720deg); opacity: 0; }
        }
        
        /* Channels List */
        .channel-item {
            display: flex;
            align-items: center;
            gap: 12px;
            background: var(--card);
            border-radius: 12px;
            padding: 12px;
            margin-bottom: 8px;
        }
        
        .channel-icon {
            width: 40px;
            height: 40px;
            border-radius: 8px;
            background: var(--accent-soft);
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .channel-info {
            flex: 1;
        }
        
        .channel-name {
            font-weight: 600;
        }
        
        .channel-join {
            background: var(--accent);
            color: white;
            border: none;
            padding: 6px 12px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.9rem;
        }
        
        .channel-joined {
            background: var(--success);
        }
        
        /* Responsive */
        @media (max-width: 768px) {
            .nav-links {
                width: 100%;
            }
            
            .nav-btn {
                flex: 1;
                padding: 8px 12px;
            }
        }
    </style>
</head>
<body>
    <div class="loader" id="loader">
        <div class="spinner"></div>
    </div>
    
    <div class="toast-container" id="toastContainer"></div>
    
    <div class="app-header">
        <div class="nav-container">
            <div class="nav-links">
                <button class="nav-btn <%= currentPage === 'home' ? 'active' : '' %>" onclick="switchPage('home')">
                    <i class="fas fa-home"></i> Home
                </button>
                <button class="nav-btn <%= currentPage === 'refer' ? 'active' : '' %>" onclick="switchPage('refer')">
                    <i class="fas fa-users"></i> Refer
                </button>
                <button class="nav-btn <%= currentPage === 'history' ? 'active' : '' %>" onclick="switchPage('history')">
                    <i class="fas fa-history"></i> History
                </button>
            </div>
        </div>
    </div>
    
    <div class="main-content" id="mainContent"></div>
    
    <!-- Contact Admin Modal -->
    <div class="modal" id="contactModal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>Contact Admin</h3>
                <button class="close-btn" onclick="closeModal('contactModal')">&times;</button>
            </div>
            <form onsubmit="submitContact(event)">
                <div class="form-group">
                    <label>Message</label>
                    <textarea class="form-control" name="message" rows="4" required></textarea>
                </div>
                <div class="form-group">
                    <label>Image (Optional)</label>
                    <input type="file" class="form-control" name="image" accept="image/*" id="contactImage">
                </div>
                <button type="submit" class="btn btn-primary">Send</button>
            </form>
        </div>
    </div>
    
    <!-- Withdraw Modal -->
    <div class="modal" id="withdrawModal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>Withdraw Funds</h3>
                <button class="close-btn" onclick="closeModal('withdrawModal')">&times;</button>
            </div>
            <div class="form-group">
                <label>Balance: ₹<span id="currentBalance"></span></label>
            </div>
            <div class="form-group">
                <label>Min: ₹<%= settings.minWithdraw %> | Max: ₹<%= settings.maxWithdraw %></label>
            </div>
            <div class="form-group">
                <label>Tax: <%= settings.withdrawTax %>%</label>
            </div>
            <form onsubmit="submitWithdraw(event)">
                <div class="form-group">
                    <input type="number" class="form-control" name="amount" placeholder="Enter amount" min="<%= settings.minWithdraw %>" max="<%= settings.maxWithdraw %>" required>
                </div>
                <div class="form-group">
                    <input type="text" class="form-control" name="upiId" placeholder="UPI ID" required>
                </div>
                <button type="submit" class="btn btn-success">Withdraw</button>
            </form>
        </div>
    </div>
    
    <script>
        const tg = window.Telegram.WebApp;
        tg.ready();
        tg.expand();
        
        let currentPage = '<%= currentPage %>';
        let user = <%- JSON.stringify(user) %>;
        let settings = <%- JSON.stringify(settings) %>;
        let transactions = <%- JSON.stringify(transactions || []) %>;
        let referrals = <%- JSON.stringify(referrals || []) %>;
        let channels = <%- JSON.stringify(channels || []) %>;
        
        function showToast(message, type = 'success') {
            const container = document.getElementById('toastContainer');
            const toast = document.createElement('div');
            toast.className = 'toast';
            if (type === 'error') toast.style.background = 'var(--danger)';
            else if (type === 'warning') toast.style.background = 'var(--warning)';
            toast.innerHTML = '<i class="fas fa-' + (type === 'success' ? 'check-circle' : 'exclamation-circle') + '"></i> ' + message;
            container.appendChild(toast);
            setTimeout(() => {
                toast.style.opacity = '0';
                toast.style.transform = 'translateX(100%)';
                toast.style.transition = 'all 0.3s';
                setTimeout(() => toast.remove(), 300);
            }, 3000);
        }
        
        function showLoader() {
            document.getElementById('loader').style.display = 'flex';
        }
        
        function hideLoader() {
            document.getElementById('loader').style.display = 'none';
        }
        
        function openModal(modalId) {
            document.getElementById(modalId).style.display = 'flex';
        }
        
        function closeModal(modalId) {
            document.getElementById(modalId).style.display = 'none';
        }
        
        function switchPage(page) {
            showLoader();
            fetch('/api/page/' + page)
                .then(res => res.json())
                .then(data => {
                    currentPage = page;
                    user = data.user;
                    transactions = data.transactions || [];
                    referrals = data.referrals || [];
                    renderPage();
                    hideLoader();
                })
                .catch(err => {
                    console.error(err);
                    showToast('Error loading page', 'error');
                    hideLoader();
                });
        }
        
        function renderPage() {
            const content = document.getElementById('mainContent');
            
            if (currentPage === 'home') {
                content.innerHTML = renderHome();
            } else if (currentPage === 'refer') {
                content.innerHTML = renderRefer();
            } else if (currentPage === 'history') {
                content.innerHTML = renderHistory();
            }
            
            document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.nav-btn').forEach(btn => {
                if (btn.innerText.toLowerCase().includes(currentPage)) {
                    btn.classList.add('active');
                }
            });
        }
        
        function renderHome() {
            const progress = Math.min(100, (user.balance / settings.minWithdraw) * 100);
            
            return \`
                <div class="logo-section">
                    <img src="\${settings.botLogo}" class="logo" alt="logo">
                    <span class="bot-name">\${settings.botName}</span>
                </div>
                
                <div class="golden-card">
                    <div class="user-avatar">
                        <i class="fas fa-user"></i>
                    </div>
                    <div>
                        <div>\${user.userId}</div>
                        <button class="contact-admin-btn" onclick="openModal('contactModal')">
                            <i class="fas fa-headset"></i> Contact Admin
                        </button>
                    </div>
                </div>
                
                <div class="credit-card">
                    <div>\${user.fullName || 'User'}</div>
                    <div class="card-balance">₹\${user.balance}</div>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: \${progress}%"></div>
                    </div>
                    <div>Min Withdraw: ₹\${settings.minWithdraw}</div>
                </div>
                
                <button class="withdraw-btn" onclick="openWithdrawModal()">
                    <i class="fas fa-wallet"></i> Withdraw Funds
                </button>
                
                <div style="margin-bottom: 20px;">
                    <h3>Join Channels</h3>
                    \${renderChannels()}
                </div>
                
                <div class="gift-box">
                    <input type="text" class="gift-input" id="giftCode" placeholder="Enter 5-digit code" maxlength="5">
                    <button class="claim-btn" onclick="claimGift()">Claim</button>
                </div>
            \`;
        }
        
        function renderChannels() {
            if (!channels || channels.length === 0) {
                return '<div class="channel-item">No channels to join</div>';
            }
            
            return channels.map(channel => {
                const joined = user.joinedChannels && user.joinedChannels.includes(channel.channelId);
                return \`
                    <div class="channel-item">
                        <div class="channel-icon">
                            <i class="fab fa-telegram"></i>
                        </div>
                        <div class="channel-info">
                            <div class="channel-name">\${channel.name}</div>
                            <div>\${channel.description || ''}</div>
                        </div>
                        <button class="channel-join \${joined ? 'channel-joined' : ''}" 
                                onclick="joinChannel('\${channel.channelId}')"
                                \${joined ? 'disabled' : ''}>
                            \${joined ? 'Joined' : 'Join'}
                        </button>
                    </div>
                \`;
            }).join('');
        }
        
        function renderRefer() {
            return \`
                <div class="refer-card">
                    <h3>Your Referral Code</h3>
                    <div class="refer-code" id="referCode">\${user.referCode}</div>
                    <button class="copy-btn" onclick="copyReferCode()">
                        <i class="fas fa-copy"></i> Copy Code
                    </button>
                    <p style="margin-top: 10px; color: var(--text-secondary);">
                        Earn ₹\${settings.referBonus} per referral after they join all channels and verify
                    </p>
                </div>
                
                <div style="margin-top: 20px;">
                    <h3>Your Referrals (\${referrals.length})</h3>
                    \${referrals.length === 0 ? 
                        '<div class="history-item">No referrals yet</div>' : 
                        referrals.map(ref => \`
                            <div class="history-item">
                                <div>
                                    <div>\${ref.referredName || 'User'}</div>
                                    <div style="font-size: 0.8rem; color: var(--text-secondary);">
                                        \${new Date(ref.joinedAt).toLocaleDateString()}
                                    </div>
                                </div>
                                <div class="\${ref.verified ? 'credit' : 'text-secondary'}">
                                    \${ref.verified ? '✓ Verified' : '⏳ Pending'}
                                </div>
                            </div>
                        \`).join('')
                    }
                </div>
            \`;
        }
        
        function renderHistory() {
            return \`
                <h3>Transaction History</h3>
                \${transactions.length === 0 ?
                    '<div class="history-item">No transactions yet</div>' :
                    transactions.map(tx => \`
                        <div class="history-item">
                            <div>
                                <div>\${tx.description}</div>
                                <div style="font-size: 0.8rem; color: var(--text-secondary);">
                                    \${new Date(tx.createdAt).toLocaleString()}
                                </div>
                            </div>
                            <div class="history-amount \${tx.type === 'credit' ? 'credit' : 'debit'}">
                                \${tx.type === 'credit' ? '+' : '-'} ₹\${tx.amount}
                            </div>
                        </div>
                    \`).join('')
                }
            \`;
        }
        
        function openWithdrawModal() {
            if (!settings.withdrawalsEnabled) {
                showToast('Withdrawals are currently disabled', 'error');
                return;
            }
            
            if (user.balance < settings.minWithdraw) {
                showToast('Insufficient balance for withdrawal', 'error');
                return;
            }
            
            document.getElementById('currentBalance').innerText = user.balance;
            openModal('withdrawModal');
        }
        
        function submitWithdraw(event) {
            event.preventDefault();
            const formData = new FormData(event.target);
            const amount = parseFloat(formData.get('amount'));
            const upiId = formData.get('upiId');
            
            if (amount < settings.minWithdraw || amount > settings.maxWithdraw) {
                showToast('Invalid amount range', 'error');
                return;
            }
            
            if (amount > user.balance) {
                showToast('Insufficient balance', 'error');
                return;
            }
            
            showLoader();
            fetch('/api/withdraw', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ amount, upiId })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    showToast('Withdrawal request submitted');
                    closeModal('withdrawModal');
                    setTimeout(() => switchPage('home'), 1000);
                } else {
                    showToast(data.error, 'error');
                }
                hideLoader();
            })
            .catch(err => {
                console.error(err);
                showToast('Error submitting withdrawal', 'error');
                hideLoader();
            });
        }
        
        function submitContact(event) {
            event.preventDefault();
            const formData = new FormData(event.target);
            
            showLoader();
            fetch('/api/contact', {
                method: 'POST',
                body: formData
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    showToast('Message sent to admin');
                    closeModal('contactModal');
                } else {
                    showToast(data.error, 'error');
                }
                hideLoader();
            })
            .catch(err => {
                console.error(err);
                showToast('Error sending message', 'error');
                hideLoader();
            });
        }
        
        function claimGift() {
            const code = document.getElementById('giftCode').value.toUpperCase();
            if (code.length !== 5) {
                showToast('Enter valid 5-digit code', 'error');
                return;
            }
            
            showLoader();
            fetch('/api/claim-gift', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    showToast('Gift claimed! ₹' + data.amount);
                    createConfetti();
                    setTimeout(() => switchPage('home'), 1000);
                } else {
                    showToast(data.error, 'error');
                }
                hideLoader();
            })
            .catch(err => {
                console.error(err);
                showToast('Error claiming gift', 'error');
                hideLoader();
            });
        }
        
        function createConfetti() {
            for (let i = 0; i < 50; i++) {
                const confetti = document.createElement('div');
                confetti.className = 'confetti';
                confetti.style.left = Math.random() * 100 + 'vw';
                confetti.style.background = \`hsl(\${Math.random() * 360}, 100%, 50%)\`;
                confetti.style.animationDelay = Math.random() * 2 + 's';
                document.body.appendChild(confetti);
                setTimeout(() => confetti.remove(), 3000);
            }
        }
        
        function joinChannel(channelId) {
            fetch('/api/join-channel', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ channelId })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    showToast('Channel joined');
                    switchPage('home');
                } else {
                    showToast(data.error, 'error');
                    if (data.link) {
                        window.open(data.link, '_blank');
                    }
                }
            })
            .catch(err => {
                console.error(err);
                showToast('Error joining channel', 'error');
            });
        }
        
        function copyReferCode() {
            const code = document.getElementById('referCode').innerText;
            navigator.clipboard.writeText(code).then(() => {
                showToast('Referral code copied!');
            });
        }
        
        // Initial render
        document.addEventListener('DOMContentLoaded', renderPage);
    </script>
</body>
</html>`;

    fs.writeFileSync(path.join(viewsDir, 'index.ejs'), mainEJS);

    // Admin Panel Template
    const adminEJS = `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Panel - <%= settings.botName %></title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {
            --bg: #0f172a;
            --card: #1e293b;
            --text: #f8fafc;
            --border: #334155;
            --accent: #60a5fa;
            --success: #34d399;
            --warning: #fbbf24;
            --danger: #f87171;
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Inter', sans-serif;
        }
        
        body {
            background: var(--bg);
            color: var(--text);
            padding: 20px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
        }
        
        .nav-tabs {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin-bottom: 20px;
            background: var(--card);
            padding: 10px;
            border-radius: 12px;
        }
        
        .nav-tab {
            padding: 10px 20px;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .nav-tab:hover {
            background: var(--border);
        }
        
        .nav-tab.active {
            background: var(--accent);
            color: white;
        }
        
        .tab-content {
            display: none;
        }
        
        .tab-content.active {
            display: block;
        }
        
        .cards-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .stat-card {
            background: var(--card);
            border-radius: 12px;
            padding: 20px;
            border: 1px solid var(--border);
        }
        
        .stat-value {
            font-size: 2rem;
            font-weight: 700;
            margin-top: 10px;
        }
        
        .table {
            width: 100%;
            border-collapse: collapse;
            background: var(--card);
            border-radius: 12px;
            overflow: hidden;
        }
        
        .table th {
            background: var(--border);
            padding: 12px;
            text-align: left;
        }
        
        .table td {
            padding: 12px;
            border-bottom: 1px solid var(--border);
        }
        
        .btn {
            padding: 8px 16px;
            border-radius: 6px;
            border: none;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.2s;
        }
        
        .btn-primary {
            background: var(--accent);
            color: white;
        }
        
        .btn-success {
            background: var(--success);
            color: white;
        }
        
        .btn-danger {
            background: var(--danger);
            color: white;
        }
        
        .btn-warning {
            background: var(--warning);
            color: black;
        }
        
        .form-group {
            margin-bottom: 15px;
        }
        
        .form-control {
            width: 100%;
            padding: 10px;
            border-radius: 6px;
            border: 1px solid var(--border);
            background: var(--bg);
            color: var(--text);
        }
        
        .toggle-switch {
            position: relative;
            display: inline-block;
            width: 60px;
            height: 34px;
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
            background-color: var(--border);
            transition: .4s;
            border-radius: 34px;
        }
        
        .toggle-slider:before {
            position: absolute;
            content: "";
            height: 26px;
            width: 26px;
            left: 4px;
            bottom: 4px;
            background-color: white;
            transition: .4s;
            border-radius: 50%;
        }
        
        input:checked + .toggle-slider {
            background-color: var(--success);
        }
        
        input:checked + .toggle-slider:before {
            transform: translateX(26px);
        }
        
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.8);
            align-items: center;
            justify-content: center;
            z-index: 1000;
        }
        
        .modal-content {
            background: var(--card);
            border-radius: 12px;
            padding: 20px;
            max-width: 500px;
            width: 90%;
            max-height: 80vh;
            overflow-y: auto;
        }
        
        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        
        .close-btn {
            background: none;
            border: none;
            color: var(--text);
            font-size: 1.5rem;
            cursor: pointer;
        }
        
        .item-list {
            margin-top: 20px;
        }
        
        .item-card {
            background: var(--bg);
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .item-actions {
            display: flex;
            gap: 5px;
        }
        
        .icon-btn {
            background: none;
            border: none;
            color: var(--text);
            cursor: pointer;
            padding: 5px;
            border-radius: 4px;
        }
        
        .icon-btn:hover {
            background: var(--border);
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Admin Panel - <%= settings.botName %></h1>
            <button class="btn btn-danger" onclick="logout()">Logout</button>
        </div>
        
        <div class="nav-tabs">
            <div class="nav-tab active" onclick="switchTab('dashboard')">Dashboard</div>
            <div class="nav-tab" onclick="switchTab('withdrawals')">Withdrawals</div>
            <div class="nav-tab" onclick="switchTab('users')">Users</div>
            <div class="nav-tab" onclick="switchTab('channels')">Channels</div>
            <div class="nav-tab" onclick="switchTab('giftCodes')">Gift Codes</div>
            <div class="nav-tab" onclick="switchTab('settings')">Settings</div>
            <div class="nav-tab" onclick="switchTab('upi')">UPI Settings</div>
            <div class="nav-tab" onclick="switchTab('broadcast')">Broadcast</div>
        </div>
        
        <!-- Dashboard Tab -->
        <div class="tab-content active" id="dashboard">
            <div class="cards-grid">
                <div class="stat-card">
                    <i class="fas fa-users"></i>
                    <div>Total Users</div>
                    <div class="stat-value"><%= stats.totalUsers %></div>
                </div>
                <div class="stat-card">
                    <i class="fas fa-check-circle"></i>
                    <div>Verified Users</div>
                    <div class="stat-value"><%= stats.verifiedUsers %></div>
                </div>
                <div class="stat-card">
                    <i class="fas fa-wallet"></i>
                    <div>Total Balance</div>
                    <div class="stat-value">₹<%= stats.totalBalance %></div>
                </div>
                <div class="stat-card">
                    <i class="fas fa-clock"></i>
                    <div>Pending Withdrawals</div>
                    <div class="stat-value"><%= stats.pendingWithdrawals %></div>
                </div>
                <div class="stat-card">
                    <i class="fas fa-gift"></i>
                    <div>Active Gift Codes</div>
                    <div class="stat-value"><%= stats.activeGiftCodes %></div>
                </div>
                <div class="stat-card">
                    <i class="fas fa-exchange-alt"></i>
                    <div>Total Transactions</div>
                    <div class="stat-value"><%= stats.totalTransactions %></div>
                </div>
            </div>
            
            <h2>Recent Users</h2>
            <table class="table">
                <thead>
                    <tr>
                        <th>User ID</th>
                        <th>Username</th>
                        <th>Balance</th>
                        <th>Verified</th>
                        <th>Joined</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody>
                    <% users.slice(0, 10).forEach(user => { %>
                    <tr>
                        <td><%= user.userId %></td>
                        <td><%= user.fullName || 'N/A' %></td>
                        <td>₹<%= user.balance %></td>
                        <td><%= user.verified ? '✅' : '❌' %></td>
                        <td><%= new Date(user.createdAt).toLocaleDateString() %></td>
                        <td><button class="btn btn-primary" onclick="viewUser('<%= user.userId %>')">View</button></td>
                    </tr>
                    <% }) %>
                </tbody>
            </table>
        </div>
        
        <!-- Withdrawals Tab -->
        <div class="tab-content" id="withdrawals">
            <div style="margin-bottom: 20px;">
                <button class="btn btn-primary" onclick="loadWithdrawals('pending')">Pending</button>
                <button class="btn btn-success" onclick="loadWithdrawals('completed')">Completed</button>
                <button class="btn btn-danger" onclick="loadWithdrawals('rejected')">Rejected</button>
            </div>
            
            <table class="table" id="withdrawalsTable">
                <thead>
                    <tr>
                        <th>User</th>
                        <th>Amount</th>
                        <th>UPI ID</th>
                        <th>Tax</th>
                        <th>Net Amount</th>
                        <th>Status</th>
                        <th>Date</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody id="withdrawalsBody"></tbody>
            </table>
        </div>
        
        <!-- Users Tab -->
        <div class="tab-content" id="users">
            <div style="margin-bottom: 20px;">
                <input type="text" class="form-control" style="max-width: 300px;" placeholder="Search by User ID" id="searchUser">
                <button class="btn btn-primary" onclick="searchUsers()">Search</button>
            </div>
            
            <table class="table">
                <thead>
                    <tr>
                        <th>User ID</th>
                        <th>Username</th>
                        <th>Balance</th>
                        <th>Refer Code</th>
                        <th>Referrals</th>
                        <th>Verified</th>
                        <th>Joined</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody>
                    <% users.forEach(user => { %>
                    <tr>
                        <td><%= user.userId %></td>
                        <td><%= user.fullName || 'N/A' %></td>
                        <td>₹<%= user.balance %></td>
                        <td><%= user.referCode %></td>
                        <td><%= user.referralCount || 0 %></td>
                        <td><%= user.verified ? '✅' : '❌' %></td>
                        <td><%= new Date(user.createdAt).toLocaleDateString() %></td>
                        <td><button class="btn btn-primary" onclick="viewUser('<%= user.userId %>')">View</button></td>
                    </tr>
                    <% }) %>
                </tbody>
            </table>
        </div>
        
        <!-- Channels Tab -->
        <div class="tab-content" id="channels">
            <button class="btn btn-primary" style="margin-bottom: 20px;" onclick="openChannelModal()">
                <i class="fas fa-plus"></i> Add Channel
            </button>
            
            <div id="channelsList"></div>
        </div>
        
        <!-- Gift Codes Tab -->
        <div class="tab-content" id="giftCodes">
            <button class="btn btn-primary" style="margin-bottom: 20px;" onclick="openGiftModal()">
                <i class="fas fa-plus"></i> Generate Gift Code
            </button>
            
            <table class="table">
                <thead>
                    <tr>
                        <th>Code</th>
                        <th>Min Amount</th>
                        <th>Max Amount</th>
                        <th>Total Users</th>
                        <th>Used</th>
                        <th>Expires</th>
                        <th>Status</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody id="giftCodesBody"></tbody>
            </table>
        </div>
        
        <!-- Settings Tab -->
        <div class="tab-content" id="settings">
            <form onsubmit="saveSettings(event)">
                <div class="cards-grid">
                    <div class="stat-card">
                        <h3>Bot Settings</h3>
                        <div class="form-group">
                            <label>Bot Name</label>
                            <input type="text" class="form-control" name="botName" value="<%= settings.botName %>">
                        </div>
                        <div class="form-group">
                            <label>Bot Logo URL</label>
                            <input type="url" class="form-control" name="botLogo" value="<%= settings.botLogo %>">
                        </div>
                        <div class="form-group">
                            <label>Min Withdraw (₹)</label>
                            <input type="number" class="form-control" name="minWithdraw" value="<%= settings.minWithdraw %>">
                        </div>
                        <div class="form-group">
                            <label>Max Withdraw (₹)</label>
                            <input type="number" class="form-control" name="maxWithdraw" value="<%= settings.maxWithdraw %>">
                        </div>
                        <div class="form-group">
                            <label>Refer Bonus (₹)</label>
                            <input type="number" class="form-control" name="referBonus" value="<%= settings.referBonus %>">
                        </div>
                        <div class="form-group">
                            <label>Welcome Bonus (₹)</label>
                            <input type="number" class="form-control" name="welcomeBonus" value="<%= settings.welcomeBonus %>">
                        </div>
                        <div class="form-group">
                            <label>Withdraw Tax (%)</label>
                            <input type="number" class="form-control" name="withdrawTax" value="<%= settings.withdrawTax %>">
                        </div>
                    </div>
                    
                    <div class="stat-card">
                        <h3>Toggle Settings</h3>
                        <div class="form-group">
                            <label>Bot Enabled</label>
                            <label class="toggle-switch">
                                <input type="checkbox" name="botEnabled" <%= settings.botEnabled ? 'checked' : '' %>>
                                <span class="toggle-slider"></span>
                            </label>
                        </div>
                        <div class="form-group">
                            <label>Device Verification</label>
                            <label class="toggle-switch">
                                <input type="checkbox" name="deviceVerification" <%= settings.deviceVerification ? 'checked' : '' %>>
                                <span class="toggle-slider"></span>
                            </label>
                        </div>
                        <div class="form-group">
                            <label>Auto Withdraw (API)</label>
                            <label class="toggle-switch">
                                <input type="checkbox" name="autoWithdraw" <%= settings.autoWithdraw ? 'checked' : '' %>>
                                <span class="toggle-slider"></span>
                            </label>
                        </div>
                        <div class="form-group">
                            <label>Withdrawals Enabled</label>
                            <label class="toggle-switch">
                                <input type="checkbox" name="withdrawalsEnabled" <%= settings.withdrawalsEnabled ? 'checked' : '' %>>
                                <span class="toggle-slider"></span>
                            </label>
                        </div>
                        <div class="form-group">
                            <label>Channel Verification</label>
                            <label class="toggle-switch">
                                <input type="checkbox" name="channelVerification" <%= settings.channelVerification ? 'checked' : '' %>>
                                <span class="toggle-slider"></span>
                            </label>
                        </div>
                        <div class="form-group">
                            <label>Auto Accept Private</label>
                            <label class="toggle-switch">
                                <input type="checkbox" name="autoAcceptPrivate" <%= settings.autoAcceptPrivate ? 'checked' : '' %>>
                                <span class="toggle-slider"></span>
                            </label>
                        </div>
                    </div>
                    
                    <div class="stat-card">
                        <h3>Admin Settings</h3>
                        <div class="form-group">
                            <label>Add Admin (User ID)</label>
                            <input type="number" class="form-control" id="newAdminId" placeholder="Enter User ID">
                            <button type="button" class="btn btn-primary" style="margin-top: 10px;" onclick="addAdmin()">Add Admin</button>
                        </div>
                        <div class="form-group">
                            <label>Current Admins</label>
                            <div id="adminsList"></div>
                        </div>
                    </div>
                </div>
                
                <button type="submit" class="btn btn-success" style="width: 100%;">Save Settings</button>
            </form>
        </div>
        
        <!-- UPI Settings Tab -->
        <div class="tab-content" id="upi">
            <form onsubmit="saveUPISettings(event)">
                <div class="cards-grid">
                    <div class="stat-card">
                        <h3>UPI Settings</h3>
                        <div class="form-group">
                            <label>Enable UPI Payments</label>
                            <label class="toggle-switch">
                                <input type="checkbox" name="upiEnabled" <%= settings.upiEnabled ? 'checked' : '' %>>
                                <span class="toggle-slider"></span>
                            </label>
                        </div>
                        <div class="form-group">
                            <label>Default UPI ID</label>
                            <input type="text" class="form-control" name="upiId" value="<%= settings.upiId %>">
                        </div>
                        <div class="form-group">
                            <label>UPI Name</label>
                            <input type="text" class="form-control" name="upiName" value="<%= settings.upiName %>">
                        </div>
                    </div>
                </div>
                <button type="submit" class="btn btn-success">Save UPI Settings</button>
            </form>
        </div>
        
        <!-- Broadcast Tab -->
        <div class="tab-content" id="broadcast">
            <form onsubmit="sendBroadcast(event)" enctype="multipart/form-data">
                <div class="cards-grid">
                    <div class="stat-card">
                        <h3>Send Broadcast</h3>
                        <div class="form-group">
                            <label>Message</label>
                            <textarea class="form-control" name="message" rows="6" required></textarea>
                        </div>
                        <div class="form-group">
                            <label>Image (Optional)</label>
                            <input type="file" class="form-control" name="image" accept="image/*">
                        </div>
                        <div class="form-group">
                            <label>Button Text (Optional)</label>
                            <input type="text" class="form-control" name="buttonText">
                        </div>
                        <div class="form-group">
                            <label>Button URL (Optional)</label>
                            <input type="url" class="form-control" name="buttonUrl">
                        </div>
                        <button type="submit" class="btn btn-primary">Send to All Users</button>
                    </div>
                </div>
            </form>
        </div>
    </div>
    
    <!-- Channel Modal -->
    <div class="modal" id="channelModal">
        <div class="modal-content">
            <div class="modal-header">
                <h3 id="channelModalTitle">Add Channel</h3>
                <button class="close-btn" onclick="closeChannelModal()">&times;</button>
            </div>
            <form onsubmit="saveChannel(event)">
                <input type="hidden" name="channelId" id="channelId">
                <div class="form-group">
                    <label>Channel Name</label>
                    <input type="text" class="form-control" name="name" id="channelName" required>
                </div>
                <div class="form-group">
                    <label>Channel ID</label>
                    <input type="text" class="form-control" name="channelId" id="channelChannelId" required>
                </div>
                <div class="form-group">
                    <label>Button Text</label>
                    <input type="text" class="form-control" name="buttonText" id="channelButtonText" value="Join Channel">
                </div>
                <div class="form-group">
                    <label>Link</label>
                    <input type="url" class="form-control" name="link" id="channelLink" required>
                </div>
                <div class="form-group">
                    <label>Description</label>
                    <input type="text" class="form-control" name="description" id="channelDescription">
                </div>
                <div class="form-group">
                    <label>Position</label>
                    <input type="number" class="form-control" name="position" id="channelPosition" value="0">
                </div>
                <div class="form-group">
                    <label>
                        <input type="checkbox" name="autoAccept" id="channelAutoAccept">
                        Auto Accept (for private channels)
                    </label>
                </div>
                <div class="form-group">
                    <label>
                        <input type="checkbox" name="enabled" id="channelEnabled" checked>
                        Enabled
                    </label>
                </div>
                <button type="submit" class="btn btn-success">Save</button>
            </form>
        </div>
    </div>
    
    <!-- Gift Code Modal -->
    <div class="modal" id="giftModal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>Generate Gift Code</h3>
                <button class="close-btn" onclick="closeGiftModal()">&times;</button>
            </div>
            <form onsubmit="saveGiftCode(event)">
                <input type="hidden" name="codeId" id="codeId">
                <div class="form-group">
                    <label>Code (5 digits)</label>
                    <input type="text" class="form-control" name="code" id="code" maxlength="5" pattern="[A-Z0-9]{5}" required>
                    <button type="button" class="btn btn-primary" style="margin-top: 5px;" onclick="generateCode()">Generate</button>
                </div>
                <div class="form-group">
                    <label>Min Amount</label>
                    <input type="number" class="form-control" name="minAmount" id="minAmount" required>
                </div>
                <div class="form-group">
                    <label>Max Amount</label>
                    <input type="number" class="form-control" name="maxAmount" id="maxAmount" required>
                </div>
                <div class="form-group">
                    <label>Total Users</label>
                    <input type="number" class="form-control" name="totalUsers" id="totalUsers" required>
                </div>
                <div class="form-group">
                    <label>Expiry (minutes)</label>
                    <input type="number" class="form-control" name="expiryMinutes" id="expiryMinutes" value="1440" required>
                </div>
                <button type="submit" class="btn btn-success">Save</button>
            </form>
        </div>
    </div>
    
    <!-- User View Modal -->
    <div class="modal" id="userModal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>User Details</h3>
                <button class="close-btn" onclick="closeUserModal()">&times;</button>
            </div>
            <div id="userDetails"></div>
            <div style="margin-top: 20px;">
                <h4>Add Balance</h4>
                <div class="form-group">
                    <input type="number" class="form-control" id="addBalanceAmount" placeholder="Amount">
                    <input type="text" class="form-control" id="addBalanceReason" placeholder="Reason" style="margin-top: 10px;">
                    <button class="btn btn-primary" style="margin-top: 10px;" onclick="addUserBalance()">Add Balance</button>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        let currentUserId = null;
        let withdrawals = [];
        let giftCodes = [];
        let channels = <%- JSON.stringify(channels) %>;
        let settings = <%- JSON.stringify(settings) %>;
        
        function switchTab(tab) {
            document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelector('.nav-tab[onclick*="' + tab + '"]').classList.add('active');
            document.getElementById(tab).classList.add('active');
            
            if (tab === 'withdrawals') loadWithdrawals('pending');
            if (tab === 'channels') renderChannels();
            if (tab === 'giftCodes') loadGiftCodes();
            if (tab === 'settings') renderAdmins();
        }
        
        function loadWithdrawals(status) {
            fetch('/api/admin/withdrawals?status=' + status)
                .then(res => res.json())
                .then(data => {
                    withdrawals = data;
                    renderWithdrawals();
                });
        }
        
        function renderWithdrawals() {
            const tbody = document.getElementById('withdrawalsBody');
            tbody.innerHTML = withdrawals.map(w => \`
                <tr>
                    <td>\${w.userId}</td>
                    <td>₹\${w.amount}</td>
                    <td>\${w.upiId}</td>
                    <td>₹\${w.tax}</td>
                    <td>₹\${w.netAmount}</td>
                    <td>\${w.status}</td>
                    <td>\${new Date(w.createdAt).toLocaleString()}</td>
                    <td>
                        \${w.status === 'pending' ? \`
                            <button class="btn btn-success" onclick="acceptWithdrawal('\${w._id}')">Accept</button>
                            <button class="btn btn-danger" onclick="rejectWithdrawal('\${w._id}')">Reject</button>
                        \` : ''}
                    </td>
                </tr>
            \`).join('');
        }
        
        function acceptWithdrawal(id) {
            if (!confirm('Accept this withdrawal?')) return;
            
            fetch('/api/admin/withdrawals/' + id + '/accept', { method: 'POST' })
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        alert('Withdrawal accepted');
                        loadWithdrawals('pending');
                    } else {
                        alert(data.error);
                    }
                });
        }
        
        function rejectWithdrawal(id) {
            if (!confirm('Reject this withdrawal?')) return;
            
            fetch('/api/admin/withdrawals/' + id + '/reject', { method: 'POST' })
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        alert('Withdrawal rejected');
                        loadWithdrawals('pending');
                    } else {
                        alert(data.error);
                    }
                });
        }
        
        function renderChannels() {
            const list = document.getElementById('channelsList');
            list.innerHTML = channels.sort((a, b) => a.position - b.position).map(c => \`
                <div class="item-card">
                    <div>
                        <strong>\${c.name}</strong>
                        <div>\${c.description || ''}</div>
                        <small>Position: \${c.position}</small>
                    </div>
                    <div class="item-actions">
                        <button class="icon-btn" onclick="editChannel('\${c.channelId}')">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="icon-btn" onclick="deleteChannel('\${c.channelId}')">
                            <i class="fas fa-trash"></i>
                        </button>
                        <button class="icon-btn" onclick="moveChannel('\${c.channelId}', 'up')">
                            <i class="fas fa-arrow-up"></i>
                        </button>
                        <button class="icon-btn" onclick="moveChannel('\${c.channelId}', 'down')">
                            <i class="fas fa-arrow-down"></i>
                        </button>
                    </div>
                </div>
            \`).join('');
        }
        
        function openChannelModal() {
            document.getElementById('channelModalTitle').innerText = 'Add Channel';
            document.getElementById('channelId').value = '';
            document.getElementById('channelName').value = '';
            document.getElementById('channelChannelId').value = '';
            document.getElementById('channelButtonText').value = 'Join Channel';
            document.getElementById('channelLink').value = '';
            document.getElementById('channelDescription').value = '';
            document.getElementById('channelPosition').value = channels.length;
            document.getElementById('channelAutoAccept').checked = false;
            document.getElementById('channelEnabled').checked = true;
            document.getElementById('channelModal').style.display = 'flex';
        }
        
        function closeChannelModal() {
            document.getElementById('channelModal').style.display = 'none';
        }
        
        function saveChannel(event) {
            event.preventDefault();
            const formData = new FormData(event.target);
            const data = Object.fromEntries(formData);
            data.enabled = formData.get('enabled') === 'on';
            data.autoAccept = formData.get('autoAccept') === 'on';
            
            fetch('/api/admin/channels', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            })
            .then(res => res.json())
            .then(res => {
                if (res.success) {
                    alert('Channel saved');
                    closeChannelModal();
                    location.reload();
                } else {
                    alert(res.error);
                }
            });
        }
        
        function editChannel(id) {
            const channel = channels.find(c => c.channelId === id);
            if (!channel) return;
            
            document.getElementById('channelModalTitle').innerText = 'Edit Channel';
            document.getElementById('channelId').value = channel._id || '';
            document.getElementById('channelName').value = channel.name;
            document.getElementById('channelChannelId').value = channel.channelId;
            document.getElementById('channelButtonText').value = channel.buttonText || 'Join Channel';
            document.getElementById('channelLink').value = channel.link;
            document.getElementById('channelDescription').value = channel.description || '';
            document.getElementById('channelPosition').value = channel.position || 0;
            document.getElementById('channelAutoAccept').checked = channel.autoAccept || false;
            document.getElementById('channelEnabled').checked = channel.enabled !== false;
            document.getElementById('channelModal').style.display = 'flex';
        }
        
        function deleteChannel(id) {
            if (!confirm('Delete this channel?')) return;
            
            fetch('/api/admin/channels/' + id, { method: 'DELETE' })
                .then(res => res.json())
                .then(res => {
                    if (res.success) {
                        alert('Channel deleted');
                        location.reload();
                    } else {
                        alert(res.error);
                    }
                });
        }
        
        function moveChannel(id, direction) {
            fetch('/api/admin/channels/' + id + '/move', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ direction })
            })
            .then(res => res.json())
            .then(res => {
                if (res.success) {
                    location.reload();
                } else {
                    alert(res.error);
                }
            });
        }
        
        function openGiftModal() {
            document.getElementById('codeId').value = '';
            document.getElementById('code').value = '';
            document.getElementById('minAmount').value = settings.minGiftAmount;
            document.getElementById('maxAmount').value = settings.maxGiftAmount;
            document.getElementById('totalUsers').value = 1;
            document.getElementById('expiryMinutes').value = 1440;
            document.getElementById('giftModal').style.display = 'flex';
        }
        
        function closeGiftModal() {
            document.getElementById('giftModal').style.display = 'none';
        }
        
        function generateCode() {
            const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
            let code = '';
            for (let i = 0; i < 5; i++) {
                code += chars[Math.floor(Math.random() * chars.length)];
            }
            document.getElementById('code').value = code;
        }
        
        function loadGiftCodes() {
            fetch('/api/admin/gift-codes')
                .then(res => res.json())
                .then(data => {
                    giftCodes = data;
                    renderGiftCodes();
                });
        }
        
        function renderGiftCodes() {
            const tbody = document.getElementById('giftCodesBody');
            tbody.innerHTML = giftCodes.map(g => \`
                <tr>
                    <td>\${g.code}</td>
                    <td>₹\${g.minAmount}</td>
                    <td>₹\${g.maxAmount}</td>
                    <td>\${g.totalUsers}</td>
                    <td>\${g.usedCount || 0}</td>
                    <td>\${new Date(g.expiresAt).toLocaleString()}</td>
                    <td>\${new Date() > new Date(g.expiresAt) ? 'Expired' : 'Active'}</td>
                    <td>
                        <button class="btn btn-warning" onclick="editGiftCode('\${g._id}')">Edit</button>
                        <button class="btn btn-danger" onclick="deleteGiftCode('\${g._id}')">Delete</button>
                    </td>
                </tr>
            \`).join('');
        }
        
        function saveGiftCode(event) {
            event.preventDefault();
            const formData = new FormData(event.target);
            const data = Object.fromEntries(formData);
            
            fetch('/api/admin/gift-codes', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            })
            .then(res => res.json())
            .then(res => {
                if (res.success) {
                    alert('Gift code saved');
                    closeGiftModal();
                    loadGiftCodes();
                } else {
                    alert(res.error);
                }
            });
        }
        
        function editGiftCode(id) {
            const code = giftCodes.find(g => g._id === id);
            if (!code) return;
            
            document.getElementById('codeId').value = code._id;
            document.getElementById('code').value = code.code;
            document.getElementById('minAmount').value = code.minAmount;
            document.getElementById('maxAmount').value = code.maxAmount;
            document.getElementById('totalUsers').value = code.totalUsers;
            document.getElementById('expiryMinutes').value = 1440; // Not stored, just default
            document.getElementById('giftModal').style.display = 'flex';
        }
        
        function deleteGiftCode(id) {
            if (!confirm('Delete this gift code?')) return;
            
            fetch('/api/admin/gift-codes/' + id, { method: 'DELETE' })
                .then(res => res.json())
                .then(res => {
                    if (res.success) {
                        alert('Gift code deleted');
                        loadGiftCodes();
                    } else {
                        alert(res.error);
                    }
                });
        }
        
        function saveSettings(event) {
            event.preventDefault();
            const formData = new FormData(event.target);
            const data = {};
            
            for (const [key, value] of formData.entries()) {
                if (key === 'botEnabled' || key === 'deviceVerification' || key === 'autoWithdraw' || 
                    key === 'withdrawalsEnabled' || key === 'channelVerification' || key === 'autoAcceptPrivate') {
                    data[key] = value === 'on';
                } else {
                    data[key] = value;
                }
            }
            
            fetch('/api/admin/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            })
            .then(res => res.json())
            .then(res => {
                if (res.success) {
                    alert('Settings saved');
                } else {
                    alert(res.error);
                }
            });
        }
        
        function saveUPISettings(event) {
            event.preventDefault();
            const formData = new FormData(event.target);
            const data = {
                upiEnabled: formData.get('upiEnabled') === 'on',
                upiId: formData.get('upiId'),
                upiName: formData.get('upiName')
            };
            
            fetch('/api/admin/upi-settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            })
            .then(res => res.json())
            .then(res => {
                if (res.success) {
                    alert('UPI settings saved');
                } else {
                    alert(res.error);
                }
            });
        }
        
        function renderAdmins() {
            const list = document.getElementById('adminsList');
            list.innerHTML = settings.adminIds.map(id => \`
                <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                    <span>\${id}</span>
                    <button class="btn btn-danger btn-sm" onclick="removeAdmin('\${id}')">Remove</button>
                </div>
            \`).join('');
        }
        
        function addAdmin() {
            const newId = document.getElementById('newAdminId').value;
            if (!newId) return;
            
            settings.adminIds.push(parseInt(newId));
            renderAdmins();
        }
        
        function removeAdmin(id) {
            settings.adminIds = settings.adminIds.filter(a => a != id);
            renderAdmins();
        }
        
        function sendBroadcast(event) {
            event.preventDefault();
            const formData = new FormData(event.target);
            
            if (!confirm('Send broadcast to all users?')) return;
            
            fetch('/api/admin/broadcast', {
                method: 'POST',
                body: formData
            })
            .then(res => res.json())
            .then(res => {
                if (res.success) {
                    alert('Broadcast sent to ' + res.sent + ' users');
                } else {
                    alert(res.error);
                }
            });
        }
        
        function viewUser(userId) {
            currentUserId = userId;
            fetch('/api/admin/users/' + userId)
                .then(res => res.json())
                .then(user => {
                    document.getElementById('userDetails').innerHTML = \`
                        <p><strong>User ID:</strong> \${user.userId}</p>
                        <p><strong>Username:</strong> \${user.fullName || 'N/A'}</p>
                        <p><strong>Balance:</strong> ₹\${user.balance}</p>
                        <p><strong>Refer Code:</strong> \${user.referCode}</p>
                        <p><strong>Referrals:</strong> \${user.referralCount || 0}</p>
                        <p><strong>Verified:</strong> \${user.verified ? 'Yes' : 'No'}</p>
                        <p><strong>Device ID:</strong> \${user.deviceId || 'N/A'}</p>
                        <p><strong>IP:</strong> \${user.ip || 'N/A'}</p>
                        <p><strong>Joined:</strong> \${new Date(user.createdAt).toLocaleString()}</p>
                        <p><strong>Channels Joined:</strong> \${(user.joinedChannels || []).length}</p>
                    \`;
                    document.getElementById('userModal').style.display = 'flex';
                });
        }
        
        function closeUserModal() {
            document.getElementById('userModal').style.display = 'none';
        }
        
        function addUserBalance() {
            const amount = document.getElementById('addBalanceAmount').value;
            const reason = document.getElementById('addBalanceReason').value;
            
            if (!amount || !reason) {
                alert('Enter amount and reason');
                return;
            }
            
            fetch('/api/admin/users/' + currentUserId + '/add-balance', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ amount: parseFloat(amount), reason })
            })
            .then(res => res.json())
            .then(res => {
                if (res.success) {
                    alert('Balance added');
                    viewUser(currentUserId);
                } else {
                    alert(res.error);
                }
            });
        }
        
        function searchUsers() {
            const query = document.getElementById('searchUser').value;
            if (!query) return;
            
            fetch('/api/admin/users/search?q=' + query)
                .then(res => res.json())
                .then(user => {
                    if (user) {
                        viewUser(user.userId);
                    } else {
                        alert('User not found');
                    }
                });
        }
        
        function logout() {
            window.location.href = '/';
        }
    </script>
</body>
</html>`;

    fs.writeFileSync(path.join(viewsDir, 'admin.ejs'), adminEJS);
    
    console.log('✅ EJS templates created');
}

createEJSFiles();

// ==========================================
// 🛠️ UTILITY FUNCTIONS
// ==========================================
function generateReferCode() {
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
    let code = '';
    for (let i = 0; i < 5; i++) {
        code += chars[Math.floor(Math.random() * chars.length)];
    }
    return code;
}

function generateDeviceId(req) {
    const ip = req.headers['x-forwarded-for'] || req.socket.remoteAddress;
    const userAgent = req.headers['user-agent'];
    const timestamp = Date.now();
    return crypto.createHash('sha256').update(ip + userAgent + timestamp).digest('hex').substring(0, 32);
}

async function checkDeviceVerification(req, userId) {
    const settings = await db.collection('settings').findOne({ key: 'deviceVerification' });
    if (!settings || !settings.value) return true;
    
    const ip = req.headers['x-forwarded-for'] || req.socket.remoteAddress;
    const deviceId = generateDeviceId(req);
    
    const existingUser = await db.collection('users').findOne({
        $or: [
            { deviceId, userId: { $ne: userId } },
            { ip, userId: { $ne: userId } }
        ]
    });
    
    return !existingUser;
}

async function checkChannelMembership(ctx, userId, channelId) {
    try {
        const chatMember = await ctx.telegram.getChatMember(channelId, userId);
        return ['member', 'administrator', 'creator'].includes(chatMember.status);
    } catch (error) {
        console.error('Channel membership check error:', error);
        return false;
    }
}

async function processAutoWithdraw(amount, upiId) {
    try {
        const settings = await db.collection('settings').findOne({ key: 'autoWithdraw' });
        if (!settings || !settings.value) return false;
        
        const upiSettings = await db.collection('settings').findOne({ key: 'upiEnabled' });
        if (!upiSettings || !upiSettings.value) return false;
        
        const apiUrl = EASEPAY_API.replace('{upi_id}', upiId).replace('{amount}', amount);
        const response = await axios.get(apiUrl);
        
        return response.data && response.data.status === 'success';
    } catch (error) {
        console.error('Auto withdraw error:', error);
        return false;
    }
}

// ==========================================
// 🤖 BOT SETUP
// ==========================================
const bot = new Telegraf(BOT_TOKEN);

bot.use(telegrafSession());

// Device verification middleware
bot.use(async (ctx, next) => {
    if (!ctx.from) return next();
    
    try {
        const settings = await db.collection('settings').findOne({ key: 'botEnabled' });
        if (settings && !settings.value) {
            await ctx.reply('❌ Bot is currently disabled. Please try again later.');
            return;
        }
        
        ctx.session = ctx.session || {};
        ctx.session.userId = ctx.from.id;
        next();
    } catch (error) {
        console.error('Bot middleware error:', error);
        next();
    }
});

// ==========================================
// 🎯 START COMMAND
// ==========================================
bot.command('start', async (ctx) => {
    const userId = ctx.from.id;
    const referrerCode = ctx.message.text.split(' ')[1];
    
    try {
        // Check if user exists
        let user = await db.collection('users').findOne({ userId });
        
        if (!user) {
            // Device verification
            const ip = ctx.message?.chat?.id ? ctx.from.id.toString() : 'unknown';
            const deviceId = generateDeviceId({ headers: { 'x-forwarded-for': ip }, socket: { remoteAddress: ip } });
            
            const existingDevice = await db.collection('users').findOne({
                $or: [
                    { deviceId },
                    { ip }
                ]
            });
            
            const settings = await db.collection('settings').findOne({ key: 'deviceVerification' });
            if (settings && settings.value && existingDevice) {
                return ctx.reply('❌ This device has already been used. Only one account per device is allowed.');
            }
            
            // Create new user
            const referCode = generateReferCode();
            const welcomeBonus = (await db.collection('settings').findOne({ key: 'welcomeBonus' }))?.value || 5;
            
            user = {
                userId,
                fullName: ctx.from.first_name + (ctx.from.last_name ? ' ' + ctx.from.last_name : ''),
                username: ctx.from.username,
                balance: welcomeBonus,
                referCode,
                referredBy: null,
                verified: false,
                joinedChannels: [],
                deviceId,
                ip,
                createdAt: new Date(),
                updatedAt: new Date()
            };
            
            await db.collection('users').insertOne(user);
            
            // Add welcome bonus transaction
            await db.collection('transactions').insertOne({
                userId,
                amount: welcomeBonus,
                type: 'credit',
                description: 'Welcome bonus',
                createdAt: new Date()
            });
            
            // Process referral if exists
            if (referrerCode) {
                const referrer = await db.collection('users').findOne({ referCode: referrerCode });
                if (referrer && referrer.userId !== userId) {
                    await db.collection('referrals').insertOne({
                        referrerId: referrer.userId,
                        referredId: userId,
                        referredName: user.fullName,
                        joinedAt: new Date(),
                        verified: false
                    });
                    
                    user.referredBy = referrer.userId;
                    await db.collection('users').updateOne(
                        { userId },
                        { $set: { referredBy: referrer.userId } }
                    );
                }
            }
        }
        
        // Show channels first
        await showChannels(ctx, user);
        
    } catch (error) {
        console.error('Start command error:', error);
        await ctx.reply('❌ An error occurred. Please try again.');
    }
});

async function showChannels(ctx, user) {
    const channels = await db.collection('channels').find({ enabled: true }).sort({ position: 1 }).toArray();
    const settings = await getSettings();
    
    if (!settings.channelVerification || channels.length === 0) {
        // Skip channels if disabled or no channels
        user.verified = true;
        await db.collection('users').updateOne({ userId: user.userId }, { $set: { verified: true } });
        return showMainMenu(ctx, user);
    }
    
    const text = `
📢 <b>Join Required Channels</b>

Please join all the channels below to continue:

You will earn ₹${settings.welcomeBonus} welcome bonus after verification.
    `;
    
    const buttons = [];
    
    for (const channel of channels) {
        const joined = user.joinedChannels.includes(channel.channelId);
        buttons.push([
            Markup.button.url(channel.buttonText || 'Join Channel', channel.link),
            Markup.button.callback(
                joined ? '✅ Joined' : 'Verify',
                `verify_channel_${channel.channelId}`
            )
        ]);
    }
    
    buttons.push([Markup.button.callback('✅ Check All', 'check_all_channels')]);
    
    await ctx.reply(text, {
        parse_mode: 'HTML',
        ...Markup.inlineKeyboard(buttons)
    });
}

bot.action(/^verify_channel_(.+)$/, async (ctx) => {
    const channelId = ctx.match[1];
    const userId = ctx.from.id;
    
    try {
        const channel = await db.collection('channels').findOne({ channelId });
        if (!channel) {
            return ctx.answerCbQuery('❌ Channel not found');
        }
        
        const isMember = await checkChannelMembership(ctx, userId, channelId);
        
        if (isMember || channel.autoAccept) {
            await db.collection('users').updateOne(
                { userId },
                { $addToSet: { joinedChannels: channelId } }
            );
            
            await ctx.answerCbQuery('✅ Channel verified!');
            
            // Check if all channels are joined
            const user = await db.collection('users').findOne({ userId });
            const channels = await db.collection('channels').find({ enabled: true }).toArray();
            const allJoined = channels.every(c => user.joinedChannels.includes(c.channelId));
            
            if (allJoined && !user.verified) {
                const settings = await getSettings();
                
                await db.collection('users').updateOne(
                    { userId },
                    { $set: { verified: true } }
                );
                
                // Add welcome bonus if not already added
                await db.collection('transactions').insertOne({
                    userId,
                    amount: settings.welcomeBonus,
                    type: 'credit',
                    description: 'Channel verification bonus',
                    createdAt: new Date()
                });
                
                await db.collection('users').updateOne(
                    { userId },
                    { $inc: { balance: settings.welcomeBonus } }
                );
                
                // Process referral if pending
                const referral = await db.collection('referrals').findOne({ referredId: userId });
                if (referral && !referral.verified) {
                    await db.collection('referrals').updateOne(
                        { referredId: userId },
                        { $set: { verified: true } }
                    );
                    
                    // Add referral bonus to referrer
                    await db.collection('users').updateOne(
                        { userId: referral.referrerId },
                        { $inc: { balance: settings.referBonus } }
                    );
                    
                    await db.collection('transactions').insertOne({
                        userId: referral.referrerId,
                        amount: settings.referBonus,
                        type: 'credit',
                        description: 'Referral bonus for ' + user.fullName,
                        createdAt: new Date()
                    });
                }
                
                await ctx.answerCbQuery('✅ All channels verified! Welcome bonus added!');
                await showMainMenu(ctx, user);
            }
        } else {
            await ctx.answerCbQuery('❌ You haven\'t joined the channel yet!');
            if (channel.link) {
                await ctx.reply(`Please join the channel first:\n${channel.link}`);
            }
        }
    } catch (error) {
        console.error('Channel verification error:', error);
        await ctx.answerCbQuery('❌ Error verifying channel');
    }
});

bot.action('check_all_channels', async (ctx) => {
    const userId = ctx.from.id;
    
    try {
        const user = await db.collection('users').findOne({ userId });
        const channels = await db.collection('channels').find({ enabled: true }).toArray();
        const settings = await getSettings();
        
        let allJoined = true;
        const newlyJoined = [];
        
        for (const channel of channels) {
            if (!user.joinedChannels.includes(channel.channelId)) {
                const isMember = await checkChannelMembership(ctx, userId, channel.channelId);
                if (isMember || channel.autoAccept) {
                    newlyJoined.push(channel.channelId);
                } else {
                    allJoined = false;
                }
            }
        }
        
        if (newlyJoined.length > 0) {
            await db.collection('users').updateOne(
                { userId },
                { $addToSet: { joinedChannels: { $each: newlyJoined } } }
            );
        }
        
        if (allJoined && !user.verified) {
            await db.collection('users').updateOne(
                { userId },
                { $set: { verified: true } }
            );
            
            await db.collection('transactions').insertOne({
                userId,
                amount: settings.welcomeBonus,
                type: 'credit',
                description: 'Channel verification bonus',
                createdAt: new Date()
            });
            
            await db.collection('users').updateOne(
                { userId },
                { $inc: { balance: settings.welcomeBonus } }
            );
            
            // Process referral
            const referral = await db.collection('referrals').findOne({ referredId: userId });
            if (referral && !referral.verified) {
                await db.collection('referrals').updateOne(
                    { referredId: userId },
                    { $set: { verified: true } }
                );
                
                await db.collection('users').updateOne(
                    { userId: referral.referrerId },
                    { $inc: { balance: settings.referBonus } }
                );
                
                await db.collection('transactions').insertOne({
                    userId: referral.referrerId,
                    amount: settings.referBonus,
                    type: 'credit',
                    description: 'Referral bonus for ' + user.fullName,
                    createdAt: new Date()
                });
            }
            
            await ctx.answerCbQuery('✅ All channels verified!');
            await showMainMenu(ctx, user);
        } else if (allJoined) {
            await ctx.answerCbQuery('✅ You have already joined all channels!');
            await showMainMenu(ctx, user);
        } else {
            await ctx.answerCbQuery('❌ Please join all channels first!');
        }
    } catch (error) {
        console.error('Check all channels error:', error);
        await ctx.answerCbQuery('❌ Error checking channels');
    }
});

async function showMainMenu(ctx, user) {
    const settings = await getSettings();
    
    const text = `
┌─━━━━━━━━━━━━━━━─┐
│   ✧ ${settings.botName} ✧    │
└─━━━━━━━━━━━━━━━─┘

👋 Welcome, ${user.fullName || 'User'}!
💰 Balance: ₹${user.balance}
🏷️ Refer Code: ${user.referCode}
✅ Verified: ${user.verified ? 'Yes' : 'No'}

🌟 <b>Main Menu</b>
    `;
    
    const keyboard = Markup.inlineKeyboard([
        [Markup.button.webApp('🌐 Open Web App', WEB_APP_URL)],
        [
            Markup.button.callback('🏠 Home', 'web_home'),
            Markup.button.callback('👥 Refer', 'web_refer'),
            Markup.button.callback('📊 History', 'web_history')
        ],
        [Markup.button.callback('🔄 Reorder Channels', 'reorder_channels')]
    ]);
    
    await ctx.reply(text, { parse_mode: 'HTML', ...keyboard });
}

bot.action('web_home', async (ctx) => {
    const userId = ctx.from.id;
    const user = await db.collection('users').findOne({ userId });
    await showMainMenu(ctx, user);
});

bot.action('web_refer', async (ctx) => {
    const userId = ctx.from.id;
    const user = await db.collection('users').findOne({ userId });
    
    const referrals = await db.collection('referrals').find({ referrerId: userId }).toArray();
    const settings = await getSettings();
    
    let text = `
👥 <b>Your Referrals</b>

🔗 Referral Link:
https://t.me/${bot.botInfo.username}?start=${user.referCode}

💰 Earn ₹${settings.referBonus} per verified referral
📊 Total Referrals: ${referrals.length}
    `;
    
    if (referrals.length > 0) {
        text += '\n\n<b>Recent Referrals:</b>\n';
        referrals.slice(-5).forEach(ref => {
            text += `\n${ref.referredName || 'User'} - ${ref.verified ? '✅' : '⏳'}`;
        });
    }
    
    const keyboard = Markup.inlineKeyboard([
        [Markup.button.callback('🔙 Back', 'web_home')]
    ]);
    
    await safeEdit(ctx, text, keyboard);
});

bot.action('web_history', async (ctx) => {
    const userId = ctx.from.id;
    
    const transactions = await db.collection('transactions')
        .find({ userId })
        .sort({ createdAt: -1 })
        .limit(10)
        .toArray();
    
    let text = '📊 <b>Transaction History</b>\n\n';
    
    if (transactions.length === 0) {
        text += 'No transactions yet';
    } else {
        transactions.forEach(tx => {
            const sign = tx.type === 'credit' ? '+' : '-';
            text += `\n${sign} ₹${tx.amount} - ${tx.description}\n📅 ${formatIST(tx.createdAt)}\n`;
        });
    }
    
    const keyboard = Markup.inlineKeyboard([
        [Markup.button.callback('🔙 Back', 'web_home')]
    ]);
    
    await safeEdit(ctx, text, keyboard);
});

bot.action('reorder_channels', async (ctx) => {
    const channels = await db.collection('channels').find({ enabled: true }).sort({ position: 1 }).toArray();
    
    if (channels.length < 2) {
        return ctx.answerCbQuery('❌ Need at least 2 channels to reorder');
    }
    
    let text = '🔄 <b>Reorder Channels</b>\n\nSelect a channel to move:';
    
    const keyboard = [];
    channels.forEach((c, i) => {
        keyboard.push([{
            text: `${i + 1}. ${c.name}`,
            callback_data: `reorder_channel_select_${c.channelId}`
        }]);
    });
    
    keyboard.push([{ text: '🔙 Back', callback_data: 'web_home' }]);
    
    await safeEdit(ctx, text, Markup.inlineKeyboard(keyboard));
});

bot.action(/^reorder_channel_select_(.+)$/, async (ctx) => {
    const channelId = ctx.match[1];
    const channels = await db.collection('channels').find({ enabled: true }).sort({ position: 1 }).toArray();
    const selectedIndex = channels.findIndex(c => c.channelId === channelId);
    
    ctx.session.reorderChannel = {
        channelId,
        selectedIndex,
        channels
    };
    
    let text = '🔄 <b>Reorder Channels</b>\n\n';
    channels.forEach((c, i) => {
        if (i === selectedIndex) {
            text += `<blockquote>${i + 1}. ${c.name}</blockquote>\n`;
        } else {
            text += `${i + 1}. ${c.name}\n`;
        }
    });
    
    const keyboard = [];
    if (selectedIndex > 0) {
        keyboard.push([{ text: '⬆️ Move Up', callback_data: 'reorder_channel_up' }]);
    }
    if (selectedIndex < channels.length - 1) {
        if (selectedIndex > 0) {
            keyboard[keyboard.length - 1].push({ text: '⬇️ Move Down', callback_data: 'reorder_channel_down' });
        } else {
            keyboard.push([{ text: '⬇️ Move Down', callback_data: 'reorder_channel_down' }]);
        }
    }
    keyboard.push([{ text: '✅ Save', callback_data: 'reorder_channel_save' }, { text: '🔙 Back', callback_data: 'reorder_channels' }]);
    
    await safeEdit(ctx, text, Markup.inlineKeyboard(keyboard));
});

bot.action('reorder_channel_up', async (ctx) => {
    if (!ctx.session.reorderChannel) return;
    
    const { selectedIndex, channels } = ctx.session.reorderChannel;
    if (selectedIndex <= 0) return;
    
    [channels[selectedIndex], channels[selectedIndex - 1]] = [channels[selectedIndex - 1], channels[selectedIndex]];
    ctx.session.reorderChannel.selectedIndex = selectedIndex - 1;
    ctx.session.reorderChannel.channels = channels;
    
    await showReorderPreview(ctx);
});

bot.action('reorder_channel_down', async (ctx) => {
    if (!ctx.session.reorderChannel) return;
    
    const { selectedIndex, channels } = ctx.session.reorderChannel;
    if (selectedIndex >= channels.length - 1) return;
    
    [channels[selectedIndex], channels[selectedIndex + 1]] = [channels[selectedIndex + 1], channels[selectedIndex]];
    ctx.session.reorderChannel.selectedIndex = selectedIndex + 1;
    ctx.session.reorderChannel.channels = channels;
    
    await showReorderPreview(ctx);
});

async function showReorderPreview(ctx) {
    const { selectedIndex, channels } = ctx.session.reorderChannel;
    
    let text = '🔄 <b>Reorder Channels</b>\n\n';
    channels.forEach((c, i) => {
        if (i === selectedIndex) {
            text += `<blockquote>${i + 1}. ${c.name}</blockquote>\n`;
        } else {
            text += `${i + 1}. ${c.name}\n`;
        }
    });
    
    const keyboard = [];
    if (selectedIndex > 0) {
        keyboard.push([{ text: '⬆️ Move Up', callback_data: 'reorder_channel_up' }]);
    }
    if (selectedIndex < channels.length - 1) {
        if (selectedIndex > 0) {
            keyboard[keyboard.length - 1].push({ text: '⬇️ Move Down', callback_data: 'reorder_channel_down' });
        } else {
            keyboard.push([{ text: '⬇️ Move Down', callback_data: 'reorder_channel_down' }]);
        }
    }
    keyboard.push([{ text: '✅ Save', callback_data: 'reorder_channel_save' }, { text: '🔙 Back', callback_data: 'reorder_channels' }]);
    
    await safeEdit(ctx, text, Markup.inlineKeyboard(keyboard));
}

bot.action('reorder_channel_save', async (ctx) => {
    if (!ctx.session.reorderChannel) return;
    
    const { channels } = ctx.session.reorderChannel;
    
    for (let i = 0; i < channels.length; i++) {
        await db.collection('channels').updateOne(
            { channelId: channels[i].channelId },
            { $set: { position: i } }
        );
    }
    
    delete ctx.session.reorderChannel;
    await ctx.answerCbQuery('✅ Channel order saved!');
    await showMainMenu(ctx, await db.collection('users').findOne({ userId: ctx.from.id }));
});

// ==========================================
// 📱 WEB APP ROUTES
// ==========================================
async function getSettings() {
    const settings = {};
    const cursor = db.collection('settings').find();
    await cursor.forEach(doc => {
        settings[doc.key] = doc.value;
    });
    return settings;
}

// Device verification middleware for web
app.use(async (req, res, next) => {
    const userId = req.query.userId || req.body.userId;
    if (!userId) return next();
    
    try {
        const user = await db.collection('users').findOne({ userId: parseInt(userId) });
        if (!user) return next();
        
        const settings = await getSettings();
        
        if (settings.deviceVerification) {
            const ip = req.headers['x-forwarded-for'] || req.socket.remoteAddress;
            const deviceId = generateDeviceId(req);
            
            if (user.deviceId && user.deviceId !== deviceId) {
                return res.status(403).json({ error: 'Device verification failed' });
            }
            
            if (user.ip && user.ip !== ip) {
                return res.status(403).json({ error: 'IP address mismatch' });
            }
        }
        
        req.user = user;
        next();
    } catch (error) {
        console.error('Device verification error:', error);
        next();
    }
});

app.get('/', (req, res) => {
    res.redirect('/webapp?page=home');
});

app.get('/webapp', async (req, res) => {
    const userId = req.query.userId || req.query.startParam;
    const page = req.query.page || 'home';
    
    if (!userId) {
        return res.send('Please open from Telegram bot');
    }
    
    try {
        const user = await db.collection('users').findOne({ userId: parseInt(userId) });
        if (!user) {
            return res.send('User not found');
        }
        
        const settings = await getSettings();
        const channels = await db.collection('channels').find({ enabled: true }).sort({ position: 1 }).toArray();
        
        let transactions = [];
        let referrals = [];
        
        if (page === 'history') {
            transactions = await db.collection('transactions')
                .find({ userId: user.userId })
                .sort({ createdAt: -1 })
                .limit(50)
                .toArray();
        } else if (page === 'refer') {
            referrals = await db.collection('referrals')
                .find({ referrerId: user.userId })
                .sort({ joinedAt: -1 })
                .toArray();
        }
        
        res.render('index', {
            currentPage: page,
            user,
            settings,
            channels,
            transactions,
            referrals
        });
    } catch (error) {
        console.error('Web app error:', error);
        res.status(500).send('Error loading page');
    }
});

app.get('/admin', async (req, res) => {
    const userId = req.query.userId;
    
    if (!userId) {
        return res.send('Please open from Telegram bot');
    }
    
    try {
        const settings = await getSettings();
        if (!settings.adminIds.includes(parseInt(userId))) {
            return res.send('Unauthorized');
        }
        
        const users = await db.collection('users').find().sort({ createdAt: -1 }).toArray();
        const channels = await db.collection('channels').find().sort({ position: 1 }).toArray();
        
        const stats = {
            totalUsers: users.length,
            verifiedUsers: users.filter(u => u.verified).length,
            totalBalance: users.reduce((sum, u) => sum + u.balance, 0),
            pendingWithdrawals: await db.collection('withdrawals').countDocuments({ status: 'pending' }),
            activeGiftCodes: await db.collection('giftCodes').countDocuments({ expiresAt: { $gt: new Date() } }),
            totalTransactions: await db.collection('transactions').countDocuments()
        };
        
        res.render('admin', {
            users,
            channels,
            settings,
            stats
        });
    } catch (error) {
        console.error('Admin panel error:', error);
        res.status(500).send('Error loading admin panel');
    }
});

// API Routes
app.get('/api/page/:page', async (req, res) => {
    const userId = req.query.userId;
    const page = req.params.page;
    
    if (!userId) {
        return res.status(401).json({ error: 'Unauthorized' });
    }
    
    try {
        const user = await db.collection('users').findOne({ userId: parseInt(userId) });
        if (!user) {
            return res.status(404).json({ error: 'User not found' });
        }
        
        const settings = await getSettings();
        const channels = await db.collection('channels').find({ enabled: true }).sort({ position: 1 }).toArray();
        
        let transactions = [];
        let referrals = [];
        
        if (page === 'history') {
            transactions = await db.collection('transactions')
                .find({ userId: user.userId })
                .sort({ createdAt: -1 })
                .limit(50)
                .toArray();
        } else if (page === 'refer') {
            referrals = await db.collection('referrals')
                .find({ referrerId: user.userId })
                .sort({ joinedAt: -1 })
                .toArray();
        }
        
        res.json({
            user,
            settings,
            channels,
            transactions,
            referrals
        });
    } catch (error) {
        console.error('API error:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

app.post('/api/withdraw', async (req, res) => {
    const { userId, amount, upiId } = req.body;
    
    if (!userId || !amount || !upiId) {
        return res.status(400).json({ error: 'Missing fields' });
    }
    
    try {
        const user = await db.collection('users').findOne({ userId: parseInt(userId) });
        if (!user) {
            return res.status(404).json({ error: 'User not found' });
        }
        
        const settings = await getSettings();
        
        if (!settings.withdrawalsEnabled) {
            return res.json({ error: 'Withdrawals are currently disabled' });
        }
        
        if (amount < settings.minWithdraw || amount > settings.maxWithdraw) {
            return res.json({ error: 'Invalid amount range' });
        }
        
        if (amount > user.balance) {
            return res.json({ error: 'Insufficient balance' });
        }
        
        const tax = (amount * settings.withdrawTax) / 100;
        const netAmount = amount - tax;
        
        const withdrawal = {
            userId: user.userId,
            amount,
            tax,
            netAmount,
            upiId,
            status: 'pending',
            createdAt: new Date()
        };
        
        await db.collection('withdrawals').insertOne(withdrawal);
        
        // Deduct balance
        await db.collection('users').updateOne(
            { userId: user.userId },
            { $inc: { balance: -amount } }
        );
        
        await db.collection('transactions').insertOne({
            userId: user.userId,
            amount,
            type: 'debit',
            description: `Withdrawal request (Tax: ₹${tax})`,
            createdAt: new Date()
        });
        
        // Auto withdraw if enabled
        if (settings.autoWithdraw && settings.upiEnabled) {
            const success = await processAutoWithdraw(netAmount, upiId);
            if (success) {
                await db.collection('withdrawals').updateOne(
                    { _id: withdrawal._id },
                    { $set: { status: 'completed', processedAt: new Date() } }
                );
            }
        }
        
        // Notify admins
        for (const adminId of settings.adminIds) {
            try {
                await bot.telegram.sendMessage(adminId, 
                    `💰 <b>New Withdrawal Request</b>\n\n` +
                    `User: ${user.fullName || user.userId}\n` +
                    `Amount: ₹${amount}\n` +
                    `Tax: ₹${tax}\n` +
                    `Net: ₹${netAmount}\n` +
                    `UPI: ${upiId}\n` +
                    `Date: ${formatIST(new Date())}`,
                    { parse_mode: 'HTML' }
                );
            } catch (e) {}
        }
        
        res.json({ success: true, withdrawal });
    } catch (error) {
        console.error('Withdraw error:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

app.post('/api/contact', upload.single('image'), async (req, res) => {
    const { userId, message } = req.body;
    const image = req.file;
    
    if (!userId || !message) {
        return res.status(400).json({ error: 'Missing fields' });
    }
    
    try {
        const user = await db.collection('users').findOne({ userId: parseInt(userId) });
        if (!user) {
            return res.status(404).json({ error: 'User not found' });
        }
        
        const settings = await getSettings();
        
        // Send to all admins
        for (const adminId of settings.adminIds) {
            try {
                const text = 
                    `📬 <b>New Support Message</b>\n\n` +
                    `From: ${user.fullName || 'User'}\n` +
                    `User ID: <code>${user.userId}</code>\n` +
                    `Message: ${message}\n\n` +
                    `Reply to this message to respond to the user.`;
                
                if (image) {
                    await bot.telegram.sendPhoto(adminId, { source: fs.createReadStream(image.path) }, {
                        caption: text,
                        parse_mode: 'HTML'
                    });
                } else {
                    await bot.telegram.sendMessage(adminId, text, { parse_mode: 'HTML' });
                }
            } catch (e) {}
        }
        
        // Clean up uploaded file
        if (image) {
            fs.unlinkSync(image.path);
        }
        
        res.json({ success: true });
    } catch (error) {
        console.error('Contact error:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

// Handle admin replies
bot.on('text', async (ctx) => {
    if (!ctx.message.reply_to_message) return;
    
    const repliedMessage = ctx.message.reply_to_message;
    if (!repliedMessage.text || !repliedMessage.text.includes('User ID:')) return;
    
    // Extract user ID from replied message
    const match = repliedMessage.text.match(/User ID: <code>(\d+)<\/code>/);
    if (!match) return;
    
    const targetUserId = parseInt(match[1]);
    const adminId = ctx.from.id;
    
    const settings = await getSettings();
    if (!settings.adminIds.includes(adminId)) return;
    
    try {
        await bot.telegram.sendMessage(targetUserId,
            `📬 <b>Admin Response</b>\n\n${ctx.message.text}`,
            { parse_mode: 'HTML' }
        );
        await ctx.reply('✅ Reply sent to user');
    } catch (error) {
        await ctx.reply('❌ Failed to send reply. User may have blocked the bot.');
    }
});

app.post('/api/claim-gift', async (req, res) => {
    const { userId, code } = req.body;
    
    if (!userId || !code) {
        return res.status(400).json({ error: 'Missing fields' });
    }
    
    try {
        const user = await db.collection('users').findOne({ userId: parseInt(userId) });
        if (!user) {
            return res.status(404).json({ error: 'User not found' });
        }
        
        const giftCode = await db.collection('giftCodes').findOne({
            code: code.toUpperCase(),
            expiresAt: { $gt: new Date() },
            $or: [
                { usedCount: { $lt: '$totalUsers' } },
                { usedCount: { $exists: false } }
            ]
        });
        
        if (!giftCode) {
            return res.json({ error: 'Invalid or expired gift code' });
        }
        
        // Check if user already claimed this code
        const alreadyClaimed = await db.collection('giftClaims').findOne({
            userId: user.userId,
            giftCodeId: giftCode._id
        });
        
        if (alreadyClaimed) {
            return res.json({ error: 'You have already claimed this gift code' });
        }
        
        // Generate random amount between min and max
        const amount = Math.floor(
            Math.random() * (giftCode.maxAmount - giftCode.minAmount + 1)
        ) + giftCode.minAmount;
        
        // Add to user balance
        await db.collection('users').updateOne(
            { userId: user.userId },
            { $inc: { balance: amount } }
        );
        
        // Record transaction
        await db.collection('transactions').insertOne({
            userId: user.userId,
            amount,
            type: 'credit',
            description: `Gift code: ${code}`,
            createdAt: new Date()
        });
        
        // Record claim
        await db.collection('giftClaims').insertOne({
            userId: user.userId,
            giftCodeId: giftCode._id,
            code,
            amount,
            claimedAt: new Date()
        });
        
        // Update gift code usage
        await db.collection('giftCodes').updateOne(
            { _id: giftCode._id },
            { $inc: { usedCount: 1 } }
        );
        
        res.json({ success: true, amount });
    } catch (error) {
        console.error('Claim gift error:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

app.post('/api/join-channel', async (req, res) => {
    const { userId, channelId } = req.body;
    
    if (!userId || !channelId) {
        return res.status(400).json({ error: 'Missing fields' });
    }
    
    try {
        const user = await db.collection('users').findOne({ userId: parseInt(userId) });
        if (!user) {
            return res.status(404).json({ error: 'User not found' });
        }
        
        const channel = await db.collection('channels').findOne({ channelId });
        if (!channel) {
            return res.json({ error: 'Channel not found' });
        }
        
        // For now, just mark as joined (actual verification happens in bot)
        await db.collection('users').updateOne(
            { userId: user.userId },
            { $addToSet: { joinedChannels: channelId } }
        );
        
        res.json({ success: true, link: channel.link });
    } catch (error) {
        console.error('Join channel error:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

// ==========================================
// 👑 ADMIN API ROUTES
// ==========================================
app.use('/api/admin/*', async (req, res, next) => {
    const userId = req.body.userId || req.query.userId;
    if (!userId) {
        return res.status(401).json({ error: 'Unauthorized' });
    }
    
    const settings = await getSettings();
    if (!settings.adminIds.includes(parseInt(userId))) {
        return res.status(403).json({ error: 'Forbidden' });
    }
    
    next();
});

app.get('/api/admin/withdrawals', async (req, res) => {
    const { status } = req.query;
    
    try {
        const withdrawals = await db.collection('withdrawals')
            .find(status ? { status } : {})
            .sort({ createdAt: -1 })
            .toArray();
        
        res.json(withdrawals);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.post('/api/admin/withdrawals/:id/accept', async (req, res) => {
    const { id } = req.params;
    
    try {
        const withdrawal = await db.collection('withdrawals').findOne({ _id: new ObjectId(id) });
        if (!withdrawal) {
            return res.status(404).json({ error: 'Withdrawal not found' });
        }
        
        const settings = await getSettings();
        
        // Process payment via API if enabled
        let paymentSuccess = false;
        if (settings.autoWithdraw && settings.upiEnabled) {
            paymentSuccess = await processAutoWithdraw(withdrawal.netAmount, withdrawal.upiId);
        }
        
        await db.collection('withdrawals').updateOne(
            { _id: new ObjectId(id) },
            { 
                $set: { 
                    status: paymentSuccess ? 'completed' : 'pending',
                    processedAt: new Date(),
                    processedBy: req.body.userId,
                    paymentMethod: paymentSuccess ? 'api' : 'manual'
                }
            }
        );
        
        // Notify user
        try {
            await bot.telegram.sendMessage(withdrawal.userId,
                `✅ <b>Withdrawal ${paymentSuccess ? 'Completed' : 'Processing'}</b>\n\n` +
                `Amount: ₹${withdrawal.amount}\n` +
                `Net: ₹${withdrawal.netAmount}\n` +
                `UPI: ${withdrawal.upiId}\n` +
                `Status: ${paymentSuccess ? 'Payment sent via API' : 'Being processed manually'}`,
                { parse_mode: 'HTML' }
            );
        } catch (e) {}
        
        res.json({ success: true, paymentSuccess });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.post('/api/admin/withdrawals/:id/reject', async (req, res) => {
    const { id } = req.params;
    
    try {
        const withdrawal = await db.collection('withdrawals').findOne({ _id: new ObjectId(id) });
        if (!withdrawal) {
            return res.status(404).json({ error: 'Withdrawal not found' });
        }
        
        await db.collection('withdrawals').updateOne(
            { _id: new ObjectId(id) },
            { $set: { status: 'rejected', processedAt: new Date() } }
        );
        
        // Refund balance
        await db.collection('users').updateOne(
            { userId: withdrawal.userId },
            { $inc: { balance: withdrawal.amount } }
        );
        
        await db.collection('transactions').insertOne({
            userId: withdrawal.userId,
            amount: withdrawal.amount,
            type: 'credit',
            description: 'Withdrawal refund (rejected)',
            createdAt: new Date()
        });
        
        // Notify user
        try {
            await bot.telegram.sendMessage(withdrawal.userId,
                `❌ <b>Withdrawal Rejected</b>\n\n` +
                `Amount: ₹${withdrawal.amount} has been refunded to your balance.`,
                { parse_mode: 'HTML' }
            );
        } catch (e) {}
        
        res.json({ success: true });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.get('/api/admin/users/:userId', async (req, res) => {
    const { userId } = req.params;
    
    try {
        const user = await db.collection('users').findOne({ userId: parseInt(userId) });
        if (!user) {
            return res.status(404).json({ error: 'User not found' });
        }
        
        const referrals = await db.collection('referrals').find({ referrerId: user.userId }).toArray();
        user.referralCount = referrals.length;
        
        res.json(user);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.get('/api/admin/users/search', async (req, res) => {
    const { q } = req.query;
    
    try {
        const user = await db.collection('users').findOne({
            $or: [
                { userId: parseInt(q) },
                { username: q },
                { referCode: q.toUpperCase() }
            ]
        });
        
        res.json(user);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.post('/api/admin/users/:userId/add-balance', async (req, res) => {
    const { userId } = req.params;
    const { amount, reason } = req.body;
    
    if (!amount || !reason) {
        return res.status(400).json({ error: 'Missing fields' });
    }
    
    try {
        await db.collection('users').updateOne(
            { userId: parseInt(userId) },
            { $inc: { balance: amount } }
        );
        
        await db.collection('transactions').insertOne({
            userId: parseInt(userId),
            amount,
            type: 'credit',
            description: `Admin added: ${reason}`,
            createdAt: new Date()
        });
        
        // Notify user
        try {
            await bot.telegram.sendMessage(parseInt(userId),
                `💰 <b>Balance Added</b>\n\n` +
                `Amount: ₹${amount}\n` +
                `Reason: ${reason}`,
                { parse_mode: 'HTML' }
            );
        } catch (e) {}
        
        res.json({ success: true });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.post('/api/admin/channels', async (req, res) => {
    const channel = req.body;
    
    try {
        if (channel._id) {
            // Update existing
            await db.collection('channels').updateOne(
                { _id: new ObjectId(channel._id) },
                { $set: { 
                    name: channel.name,
                    channelId: channel.channelId,
                    buttonText: channel.buttonText,
                    link: channel.link,
                    description: channel.description,
                    position: parseInt(channel.position),
                    autoAccept: channel.autoAccept,
                    enabled: channel.enabled
                }}
            );
        } else {
            // Create new
            await db.collection('channels').insertOne({
                ...channel,
                position: parseInt(channel.position),
                createdAt: new Date()
            });
        }
        
        res.json({ success: true });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.delete('/api/admin/channels/:id', async (req, res) => {
    const { id } = req.params;
    
    try {
        await db.collection('channels').deleteOne({ _id: new ObjectId(id) });
        res.json({ success: true });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.post('/api/admin/channels/:id/move', async (req, res) => {
    const { id } = req.params;
    const { direction } = req.body;
    
    try {
        const channels = await db.collection('channels').find().sort({ position: 1 }).toArray();
        const currentIndex = channels.findIndex(c => c._id.toString() === id);
        
        if (direction === 'up' && currentIndex > 0) {
            const tempPos = channels[currentIndex].position;
            channels[currentIndex].position = channels[currentIndex - 1].position;
            channels[currentIndex - 1].position = tempPos;
            
            await db.collection('channels').updateOne(
                { _id: channels[currentIndex]._id },
                { $set: { position: channels[currentIndex].position } }
            );
            
            await db.collection('channels').updateOne(
                { _id: channels[currentIndex - 1]._id },
                { $set: { position: channels[currentIndex - 1].position } }
            );
        } else if (direction === 'down' && currentIndex < channels.length - 1) {
            const tempPos = channels[currentIndex].position;
            channels[currentIndex].position = channels[currentIndex + 1].position;
            channels[currentIndex + 1].position = tempPos;
            
            await db.collection('channels').updateOne(
                { _id: channels[currentIndex]._id },
                { $set: { position: channels[currentIndex].position } }
            );
            
            await db.collection('channels').updateOne(
                { _id: channels[currentIndex + 1]._id },
                { $set: { position: channels[currentIndex + 1].position } }
            );
        }
        
        res.json({ success: true });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.get('/api/admin/gift-codes', async (req, res) => {
    try {
        const codes = await db.collection('giftCodes').find().sort({ createdAt: -1 }).toArray();
        res.json(codes);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.post('/api/admin/gift-codes', async (req, res) => {
    const { codeId, code, minAmount, maxAmount, totalUsers, expiryMinutes } = req.body;
    
    try {
        const expiresAt = new Date(Date.now() + parseInt(expiryMinutes) * 60 * 1000);
        
        if (codeId) {
            // Update existing
            await db.collection('giftCodes').updateOne(
                { _id: new ObjectId(codeId) },
                { $set: { 
                    code: code.toUpperCase(),
                    minAmount: parseFloat(minAmount),
                    maxAmount: parseFloat(maxAmount),
                    totalUsers: parseInt(totalUsers),
                    expiresAt,
                    updatedAt: new Date()
                }}
            );
        } else {
            // Create new
            await db.collection('giftCodes').insertOne({
                code: code.toUpperCase(),
                minAmount: parseFloat(minAmount),
                maxAmount: parseFloat(maxAmount),
                totalUsers: parseInt(totalUsers),
                usedCount: 0,
                expiresAt,
                createdAt: new Date()
            });
        }
        
        res.json({ success: true });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.delete('/api/admin/gift-codes/:id', async (req, res) => {
    const { id } = req.params;
    
    try {
        await db.collection('giftCodes').deleteOne({ _id: new ObjectId(id) });
        res.json({ success: true });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.post('/api/admin/settings', async (req, res) => {
    const settings = req.body;
    
    try {
        for (const [key, value] of Object.entries(settings)) {
            await db.collection('settings').updateOne(
                { key },
                { $set: { value } },
                { upsert: true }
            );
        }
        
        res.json({ success: true });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.post('/api/admin/upi-settings', async (req, res) => {
    const { upiEnabled, upiId, upiName } = req.body;
    
    try {
        await db.collection('settings').updateOne(
            { key: 'upiEnabled' },
            { $set: { value: upiEnabled } },
            { upsert: true }
        );
        
        await db.collection('settings').updateOne(
            { key: 'upiId' },
            { $set: { value: upiId } },
            { upsert: true }
        );
        
        await db.collection('settings').updateOne(
            { key: 'upiName' },
            { $set: { value: upiName } },
            { upsert: true }
        );
        
        res.json({ success: true });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.post('/api/admin/broadcast', upload.single('image'), async (req, res) => {
    const { message, buttonText, buttonUrl } = req.body;
    const image = req.file;
    
    try {
        const users = await db.collection('users').find().toArray();
        let sent = 0;
        
        const keyboard = buttonText && buttonUrl ? {
            reply_markup: {
                inline_keyboard: [[{ text: buttonText, url: buttonUrl }]]
            }
        } : {};
        
        for (const user of users) {
            try {
                if (image) {
                    await bot.telegram.sendPhoto(user.userId, { source: fs.createReadStream(image.path) }, {
                        caption: message,
                        parse_mode: 'HTML',
                        ...keyboard
                    });
                } else {
                    await bot.telegram.sendMessage(user.userId, message, {
                        parse_mode: 'HTML',
                        ...keyboard
                    });
                }
                sent++;
                
                // Small delay to avoid rate limits
                await new Promise(resolve => setTimeout(resolve, 50));
            } catch (e) {
                console.error(`Failed to send to ${user.userId}:`, e.message);
            }
        }
        
        if (image) {
            fs.unlinkSync(image.path);
        }
        
        res.json({ success: true, sent });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// ==========================================
// ⏰ SCHEDULED JOBS
// ==========================================
let autoCompleteJob;
let statsJob;

function scheduleJobs() {
    // Check expired gift codes every hour
    schedule.scheduleJob('0 * * * *', async () => {
        try {
            await db.collection('giftCodes').deleteMany({
                expiresAt: { $lt: new Date() }
            });
            console.log('✅ Expired gift codes cleaned up');
        } catch (error) {
            console.error('Gift code cleanup error:', error);
        }
    });
    
    // Send daily stats to admins at 23:59 IST
    autoCompleteJob = schedule.scheduleJob('29 18 * * *', async () => {
        try {
            const settings = await getSettings();
            const today = new Date();
            today.setHours(0, 0, 0, 0);
            
            const stats = {
                newUsers: await db.collection('users').countDocuments({ createdAt: { $gte: today } }),
                withdrawals: await db.collection('withdrawals').countDocuments({ createdAt: { $gte: today } }),
                totalWithdrawn: await db.collection('withdrawals').aggregate([
                    { $match: { createdAt: { $gte: today }, status: 'completed' } },
                    { $group: { _id: null, total: { $sum: '$netAmount' } } }
                ]).toArray(),
                giftClaims: await db.collection('giftClaims').countDocuments({ claimedAt: { $gte: today } })
            };
            
            const text = 
                `📊 <b>Daily Stats (${formatIST(today)})</b>\n\n` +
                `👥 New Users: ${stats.newUsers}\n` +
                `💰 Withdrawals: ${stats.withdrawals}\n` +
                `💸 Total Withdrawn: ₹${stats.totalWithdrawn[0]?.total || 0}\n` +
                `🎁 Gift Claims: ${stats.giftClaims}`;
            
            for (const adminId of settings.adminIds) {
                try {
                    await bot.telegram.sendMessage(adminId, text, { parse_mode: 'HTML' });
                } catch (e) {}
            }
        } catch (error) {
            console.error('Daily stats error:', error);
        }
    });
    
    console.log('✅ Scheduled jobs started');
}

// ==========================================
// 🚀 START SERVER
// ==========================================
async function safeEdit(ctx, text, keyboard = null) {
    try {
        const options = { 
            parse_mode: 'HTML',
            ...(keyboard && { reply_markup: keyboard.reply_markup })
        };
        await ctx.editMessageText(text, options);
    } catch (err) {
        if (err.description && (
            err.description.includes("message is not modified") || 
            err.description.includes("message can't be edited")
        )) {
            try {
                const options = { 
                    parse_mode: 'HTML',
                    ...(keyboard && { reply_markup: keyboard.reply_markup })
                };
                await ctx.reply(text, options);
            } catch (e) { 
                console.error('SafeEdit Reply Error:', e.message);
            }
            return;
        }
        console.error('SafeEdit Error:', err.message);
    }
}

let isShuttingDown = false;

async function start() {
    try {
        if (await connectDB()) {
            scheduleJobs();
            
            const server = app.listen(PORT, '0.0.0.0', () => {
                console.log('🌐 Web server running on port ' + PORT);
                console.log('📱 Web URL: ' + WEB_APP_URL);
                console.log('🤖 Bot: @auto_vfx_bot');
            });
            
            await bot.launch();
            console.log('✅ Bot started successfully');
            
            // Set bot commands
            await bot.telegram.setMyCommands([
                { command: 'start', description: 'Start the bot' }
            ]);
        }
    } catch (error) {
        console.error('❌ Start error:', error);
        setTimeout(start, 5000);
    }
}

function gracefulShutdown(signal) {
    if (isShuttingDown) return;
    isShuttingDown = true;
    
    console.log(`🛑 ${signal} received, shutting down...`);
    
    if (autoCompleteJob) autoCompleteJob.cancel();
    if (statsJob) statsJob.cancel();
    
    bot.stop(signal);
    if (client) client.close();
    
    process.exit(0);
}

process.once('SIGINT', () => gracefulShutdown('SIGINT'));
process.once('SIGTERM', () => gracefulShutdown('SIGTERM'));

process.on('uncaughtException', (error) => {
    console.error('❌ Uncaught Exception:', error);
});

process.on('unhandledRejection', (reason, promise) => {
    console.error('❌ Unhandled Rejection at:', promise, 'reason:', reason);
});

start();
