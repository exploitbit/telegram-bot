// index.js - Complete Refer & Earn Bot with Advanced Admin Panel
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
const WEB_APP_URL = 'https://web-production-41e72.up.railway.app';
const EASEPAY_API = 'https://easepay.site/upiapi.php?token=0127d8b8b09c9f3c6674dd5d676a6e17&key=25d33a0508f8249ebf03ee2b36cc019e&upiid={upi_id}&amount={amount}';

// ==========================================
// 🕐 TIMEZONE (IST)
// ==========================================
const IST_OFFSET_MS = (5 * 60 + 30) * 60 * 1000;

const app = express();

// Configure multer for file uploads
const storage = multer.diskStorage({
    destination: function (req, file, cb) {
        const uploadDir = path.join(__dirname, 'uploads');
        if (!fs.existsSync(uploadDir)) {
            fs.mkdirSync(uploadDir, { recursive: true });
        }
        cb(null, uploadDir);
    },
    filename: function (req, file, cb) {
        const uniqueSuffix = Date.now() + '-' + Math.round(Math.random() * 1E9);
        cb(null, uniqueSuffix + path.extname(file.originalname));
    }
});

const upload = multer({ 
    storage: storage,
    limits: { fileSize: 5 * 1024 * 1024 }, // 5MB limit
    fileFilter: (req, file, cb) => {
        if (file.mimetype.startsWith('image/')) {
            cb(null, true);
        } else {
            cb(new Error('Only images are allowed'));
        }
    }
});

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
        
        // Create giftClaims collection for tracking
        await db.collection('giftClaims').createIndex({ userId: 1, giftCodeId: 1 }, { unique: true });
        
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
        botLogo: '', // Will be set when uploaded
        minWithdraw: 50,
        maxWithdraw: 10000,
        referBonus: 10,
        welcomeBonus: 5,
        withdrawTax: 5,
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
        adminIds: [8469993808]
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
// 🛠️ UTILITY FUNCTIONS
// ==========================================
function generateReferCode() {
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
    let code = '';
    for (let i = 0; i < 6; i++) {
        code += chars[Math.floor(Math.random() * chars.length)];
    }
    return code;
}

async function getSettings() {
    const settings = {};
    const cursor = db.collection('settings').find();
    await cursor.forEach(doc => {
        settings[doc.key] = doc.value;
    });
    return settings;
}

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
            object-fit: cover;
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
            background: rgba(0,0,0,0.2);
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
        
        @keyframes shine {
            0% { transform: translateX(-100%); }
            100% { transform: translateX(100%); }
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
            max-height: 90vh;
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
        
        .btn-danger {
            background: var(--danger);
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
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
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
        
        .empty-state {
            text-align: center;
            padding: 40px;
            color: var(--text-secondary);
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
            <form id="contactForm" onsubmit="submitContact(event)">
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
            <form id="withdrawForm" onsubmit="submitWithdraw(event)">
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
            fetch('/api/page/' + page + '?userId=' + user.userId)
                .then(res => res.json())
                .then(data => {
                    if (data.error) {
                        showToast(data.error, 'error');
                        return;
                    }
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
            const logoUrl = settings.botLogo ? settings.botLogo + '?t=' + new Date().getTime() : 'https://via.placeholder.com/100';
            
            return \`
                <div class="logo-section">
                    <img src="\${logoUrl}" class="logo" alt="logo" onerror="this.src='https://via.placeholder.com/100'">
                    <span class="bot-name">\${settings.botName}</span>
                </div>
                
                <div class="golden-card">
                    <div class="user-avatar">
                        <i class="fas fa-user"></i>
                    </div>
                    <div>
                        <div>\${user.fullName || 'User'}</div>
                        <div style="font-size: 0.8rem;">ID: \${user.userId}</div>
                        <button class="contact-admin-btn" onclick="openModal('contactModal')">
                            <i class="fas fa-headset"></i> Contact Admin
                        </button>
                    </div>
                </div>
                
                <div class="credit-card">
                    <div>\${user.fullName || 'User'}</div>
                    <div class="card-balance">₹\${user.balance.toFixed(2)}</div>
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
                    <input type="text" class="gift-input" id="giftCode" placeholder="Enter 6-digit code" maxlength="6">
                    <button class="claim-btn" onclick="claimGift()">Claim</button>
                </div>
            \`;
        }
        
        function renderChannels() {
            if (!channels || channels.length === 0) {
                return '<div class="empty-state">No channels to join</div>';
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
                        '<div class="empty-state">No referrals yet</div>' : 
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
                    '<div class="empty-state">No transactions yet</div>' :
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
                body: JSON.stringify({ 
                    userId: user.userId, 
                    amount, 
                    upiId 
                })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    showToast('Withdrawal request submitted');
                    closeModal('withdrawModal');
                    setTimeout(() => switchPage('home'), 1000);
                } else {
                    showToast(data.error || 'Error submitting withdrawal', 'error');
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
            formData.append('userId', user.userId);
            
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
                    document.getElementById('contactForm').reset();
                } else {
                    showToast(data.error || 'Error sending message', 'error');
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
            if (code.length !== 6) {
                showToast('Enter valid 6-digit code', 'error');
                return;
            }
            
            showLoader();
            fetch('/api/claim-gift', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    userId: user.userId, 
                    code 
                })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    showToast('Gift claimed! ₹' + data.amount);
                    createConfetti();
                    setTimeout(() => switchPage('home'), 1000);
                } else {
                    showToast(data.error || 'Invalid gift code', 'error');
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
                confetti.style.animationDuration = (2 + Math.random() * 2) + 's';
                document.body.appendChild(confetti);
                setTimeout(() => confetti.remove(), 5000);
            }
        }
        
        function joinChannel(channelId) {
            fetch('/api/join-channel', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    userId: user.userId, 
                    channelId 
                })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    showToast('Channel joined');
                    switchPage('home');
                } else {
                    showToast(data.error || 'Error joining channel', 'error');
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

    // Advanced Admin Panel Template - COMPLETE VERSION
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
            --text-secondary: #cbd5e1;
            --border: #334155;
            --accent: #60a5fa;
            --success: #34d399;
            --warning: #fbbf24;
            --danger: #f87171;
            --info: #60a5fa;
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
            max-width: 1600px;
            margin: 0 auto;
        }
        
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            background: var(--card);
            padding: 20px 30px;
            border-radius: 16px;
            border: 1px solid var(--border);
        }
        
        .header h1 {
            font-size: 1.8rem;
            background: linear-gradient(135deg, #60a5fa, #34d399);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .nav-tabs {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin-bottom: 30px;
            background: var(--card);
            padding: 15px;
            border-radius: 50px;
            border: 1px solid var(--border);
        }
        
        .nav-tab {
            padding: 12px 24px;
            border-radius: 40px;
            cursor: pointer;
            transition: all 0.3s;
            background: var(--bg);
            color: var(--text-secondary);
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .nav-tab:hover {
            background: var(--border);
            color: var(--text);
            transform: translateY(-2px);
        }
        
        .nav-tab.active {
            background: var(--accent);
            color: white;
        }
        
        .tab-content {
            display: none;
            animation: fadeIn 0.3s;
        }
        
        .tab-content.active {
            display: block;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .cards-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 25px;
            margin-bottom: 30px;
        }
        
        .stat-card {
            background: var(--card);
            border-radius: 20px;
            padding: 25px;
            border: 1px solid var(--border);
            transition: all 0.3s;
            position: relative;
            overflow: hidden;
        }
        
        .stat-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 30px rgba(96, 165, 250, 0.2);
            border-color: var(--accent);
        }
        
        .stat-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: linear-gradient(90deg, var(--accent), var(--success));
        }
        
        .stat-icon {
            font-size: 2.5rem;
            color: var(--accent);
            margin-bottom: 15px;
        }
        
        .stat-label {
            color: var(--text-secondary);
            font-size: 0.95rem;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .stat-value {
            font-size: 2.5rem;
            font-weight: 700;
            margin-top: 10px;
            color: var(--text);
        }
        
        .table-container {
            background: var(--card);
            border-radius: 20px;
            padding: 25px;
            border: 1px solid var(--border);
            overflow-x: auto;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
        }
        
        th {
            background: var(--bg);
            padding: 15px;
            text-align: left;
            font-weight: 600;
            color: var(--text-secondary);
            border-radius: 12px 12px 0 0;
        }
        
        td {
            padding: 15px;
            border-bottom: 1px solid var(--border);
        }
        
        tr:hover {
            background: var(--bg);
        }
        
        .btn {
            padding: 10px 20px;
            border-radius: 12px;
            border: none;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.3s;
            margin: 2px;
            font-size: 0.9rem;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }
        
        .btn-sm {
            padding: 8px 16px;
            font-size: 0.85rem;
        }
        
        .btn-primary {
            background: var(--accent);
            color: white;
        }
        
        .btn-primary:hover {
            background: #3b82f6;
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(96, 165, 250, 0.4);
        }
        
        .btn-success {
            background: var(--success);
            color: white;
        }
        
        .btn-success:hover {
            background: #10b981;
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(52, 211, 153, 0.4);
        }
        
        .btn-danger {
            background: var(--danger);
            color: white;
        }
        
        .btn-danger:hover {
            background: #ef4444;
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(248, 113, 113, 0.4);
        }
        
        .btn-warning {
            background: var(--warning);
            color: black;
        }
        
        .btn-warning:hover {
            background: #f59e0b;
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(251, 191, 36, 0.4);
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-control {
            width: 100%;
            padding: 14px;
            border-radius: 12px;
            border: 1px solid var(--border);
            background: var(--bg);
            color: var(--text);
            font-size: 1rem;
            transition: all 0.3s;
        }
        
        .form-control:focus {
            outline: none;
            border-color: var(--accent);
            box-shadow: 0 0 0 3px rgba(96, 165, 250, 0.2);
        }
        
        .form-label {
            display: block;
            margin-bottom: 8px;
            color: var(--text-secondary);
            font-weight: 500;
        }
        
        .toggle-switch {
            position: relative;
            display: inline-block;
            width: 70px;
            height: 36px;
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
            border-radius: 36px;
        }
        
        .toggle-slider:before {
            position: absolute;
            content: "";
            height: 28px;
            width: 28px;
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
            transform: translateX(34px);
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
            backdrop-filter: blur(5px);
        }
        
        .modal-content {
            background: var(--card);
            border-radius: 24px;
            padding: 35px;
            max-width: 600px;
            width: 90%;
            max-height: 90vh;
            overflow-y: auto;
            border: 1px solid var(--border);
            box-shadow: 0 20px 60px rgba(0,0,0,0.5);
        }
        
        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 25px;
        }
        
        .modal-header h3 {
            font-size: 1.5rem;
            color: var(--accent);
        }
        
        .close-btn {
            background: none;
            border: none;
            color: var(--text);
            font-size: 2rem;
            cursor: pointer;
            transition: all 0.3s;
        }
        
        .close-btn:hover {
            color: var(--danger);
            transform: rotate(90deg);
        }
        
        .badge {
            background: var(--accent);
            color: white;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 600;
        }
        
        .badge-success {
            background: var(--success);
        }
        
        .badge-warning {
            background: var(--warning);
            color: black;
        }
        
        .badge-danger {
            background: var(--danger);
        }
        
        .search-box {
            display: flex;
            gap: 10px;
            margin-bottom: 25px;
        }
        
        .search-box input {
            flex: 1;
        }
        
        .filter-buttons {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }
        
        .filter-btn {
            padding: 8px 20px;
            border-radius: 30px;
            background: var(--bg);
            color: var(--text-secondary);
            cursor: pointer;
            transition: all 0.3s;
            border: 1px solid var(--border);
        }
        
        .filter-btn:hover, .filter-btn.active {
            background: var(--accent);
            color: white;
            border-color: var(--accent);
        }
        
        .item-card {
            background: var(--bg);
            border-radius: 16px;
            padding: 20px;
            margin-bottom: 15px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border: 1px solid var(--border);
            transition: all 0.3s;
        }
        
        .item-card:hover {
            border-color: var(--accent);
            transform: translateX(5px);
        }
        
        .avatar {
            width: 50px;
            height: 50px;
            border-radius: 50%;
            background: var(--accent);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5rem;
            color: white;
        }
        
        .stats-mini {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }
        
        .stat-mini-card {
            background: var(--bg);
            padding: 15px;
            border-radius: 12px;
            border: 1px solid var(--border);
        }
        
        .stat-mini-card .label {
            color: var(--text-secondary);
            font-size: 0.85rem;
        }
        
        .stat-mini-card .value {
            font-size: 1.3rem;
            font-weight: 700;
            margin-top: 5px;
        }
        
        @media (max-width: 768px) {
            .nav-tabs {
                flex-direction: column;
                border-radius: 20px;
            }
            
            .nav-tab {
                width: 100%;
                justify-content: center;
            }
            
            .header {
                flex-direction: column;
                gap: 15px;
                text-align: center;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h1><i class="fas fa-crown" style="color: var(--warning);"></i> <%= settings.botName %> Admin</h1>
                <p style="color: var(--text-secondary); margin-top: 5px;">
                    <i class="fas fa-clock"></i> Last updated: <%= new Date().toLocaleString() %>
                </p>
            </div>
            <button class="btn btn-danger" onclick="logout()">
                <i class="fas fa-sign-out-alt"></i> Logout
            </button>
        </div>
        
        <div class="nav-tabs">
            <div class="nav-tab active" onclick="switchTab('dashboard')">
                <i class="fas fa-chart-line"></i> Dashboard
            </div>
            <div class="nav-tab" onclick="switchTab('withdrawals')">
                <i class="fas fa-wallet"></i> Withdrawals
                <span class="badge badge-warning" id="pendingCount">0</span>
            </div>
            <div class="nav-tab" onclick="switchTab('users')">
                <i class="fas fa-users"></i> Users
            </div>
            <div class="nav-tab" onclick="switchTab('channels')">
                <i class="fas fa-tv"></i> Channels
            </div>
            <div class="nav-tab" onclick="switchTab('giftCodes')">
                <i class="fas fa-gift"></i> Gift Codes
            </div>
            <div class="nav-tab" onclick="switchTab('settings')">
                <i class="fas fa-cog"></i> Settings
            </div>
            <div class="nav-tab" onclick="switchTab('upi')">
                <i class="fas fa-credit-card"></i> UPI
            </div>
            <div class="nav-tab" onclick="switchTab('broadcast')">
                <i class="fas fa-broadcast-tower"></i> Broadcast
            </div>
        </div>
        
        <!-- Dashboard Tab -->
        <div class="tab-content active" id="dashboard">
            <div class="cards-grid">
                <div class="stat-card">
                    <div class="stat-icon"><i class="fas fa-users"></i></div>
                    <div class="stat-label">Total Users</div>
                    <div class="stat-value" id="totalUsers"><%= stats.totalUsers %></div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon"><i class="fas fa-check-circle"></i></div>
                    <div class="stat-label">Verified Users</div>
                    <div class="stat-value" id="verifiedUsers"><%= stats.verifiedUsers %></div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon"><i class="fas fa-rupee-sign"></i></div>
                    <div class="stat-label">Total Balance</div>
                    <div class="stat-value" id="totalBalance">₹<%= stats.totalBalance.toFixed(2) %></div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon"><i class="fas fa-clock"></i></div>
                    <div class="stat-label">Pending Withdrawals</div>
                    <div class="stat-value" id="pendingWithdrawals"><%= stats.pendingWithdrawals %></div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon"><i class="fas fa-gift"></i></div>
                    <div class="stat-label">Active Gift Codes</div>
                    <div class="stat-value" id="activeGiftCodes"><%= stats.activeGiftCodes %></div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon"><i class="fas fa-exchange-alt"></i></div>
                    <div class="stat-label">Total Transactions</div>
                    <div class="stat-value" id="totalTransactions"><%= stats.totalTransactions %></div>
                </div>
            </div>
            
            <div class="stats-mini">
                <div class="stat-mini-card">
                    <div class="label"><i class="fas fa-calendar-day"></i> Today's Users</div>
                    <div class="value" id="todayUsers">0</div>
                </div>
                <div class="stat-mini-card">
                    <div class="label"><i class="fas fa-calendar-day"></i> Today's Withdrawals</div>
                    <div class="value" id="todayWithdrawals">0</div>
                </div>
                <div class="stat-mini-card">
                    <div class="label"><i class="fas fa-calendar-day"></i> Today's Earnings</div>
                    <div class="value" id="todayEarnings">₹0</div>
                </div>
            </div>
            
            <div class="table-container">
                <h2 style="margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center;">
                    <span><i class="fas fa-history"></i> Recent Users</span>
                    <button class="btn btn-primary btn-sm" onclick="refreshDashboard()">
                        <i class="fas fa-sync-alt"></i> Refresh
                    </button>
                </h2>
                <table id="recentUsersTable">
                    <thead>
                        <tr>
                            <th>User ID</th>
                            <th>Name</th>
                            <th>Balance</th>
                            <th>Refer Code</th>
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
                            <td>₹<%= user.balance.toFixed(2) %></td>
                            <td><%= user.referCode %></td>
                            <td><%= user.verified ? '✅' : '❌' %></td>
                            <td><%= new Date(user.createdAt).toLocaleDateString() %></td>
                            <td>
                                <button class="btn btn-primary btn-sm" onclick="viewUser('<%= user.userId %>')">
                                    <i class="fas fa-eye"></i>
                                </button>
                            </td>
                        </tr>
                        <% }) %>
                    </tbody>
                </table>
            </div>
        </div>
        
        <!-- Withdrawals Tab -->
        <div class="tab-content" id="withdrawals">
            <div class="filter-buttons">
                <button class="filter-btn active" onclick="loadWithdrawals('pending')">
                    <i class="fas fa-clock"></i> Pending
                </button>
                <button class="filter-btn" onclick="loadWithdrawals('completed')">
                    <i class="fas fa-check-circle"></i> Completed
                </button>
                <button class="filter-btn" onclick="loadWithdrawals('rejected')">
                    <i class="fas fa-times-circle"></i> Rejected
                </button>
                <button class="filter-btn" onclick="loadWithdrawals('all')">
                    <i class="fas fa-list"></i> All
                </button>
            </div>
            
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>User</th>
                            <th>Amount</th>
                            <th>Tax</th>
                            <th>Net</th>
                            <th>UPI ID</th>
                            <th>Status</th>
                            <th>Date</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody id="withdrawalsBody"></tbody>
                </table>
            </div>
        </div>
        
        <!-- Users Tab -->
        <div class="tab-content" id="users">
            <div class="search-box">
                <input type="text" class="form-control" placeholder="Search by User ID, Name, Username, or Refer Code" id="searchUser">
                <button class="btn btn-primary" onclick="searchUsers()">
                    <i class="fas fa-search"></i> Search
                </button>
                <button class="btn btn-success" onclick="exportUsers()">
                    <i class="fas fa-download"></i> Export CSV
                </button>
            </div>
            
            <div class="table-container">
                <table id="usersTable">
                    <thead>
                        <tr>
                            <th>User ID</th>
                            <th>Name</th>
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
                            <td>@<%= user.username || 'N/A' %></td>
                            <td>₹<%= user.balance.toFixed(2) %></td>
                            <td><%= user.referCode %></td>
                            <td><%= user.referralCount || 0 %></td>
                            <td><%= user.verified ? '✅' : '❌' %></td>
                            <td><%= new Date(user.createdAt).toLocaleDateString() %></td>
                            <td>
                                <button class="btn btn-primary btn-sm" onclick="viewUser('<%= user.userId %>')">
                                    <i class="fas fa-eye"></i>
                                </button>
                                <button class="btn btn-success btn-sm" onclick="addBalanceModal('<%= user.userId %>')">
                                    <i class="fas fa-plus-circle"></i>
                                </button>
                            </td>
                        </tr>
                        <% }) %>
                    </tbody>
                </table>
            </div>
        </div>
        
        <!-- Channels Tab -->
        <div class="tab-content" id="channels">
            <button class="btn btn-primary" style="margin-bottom: 20px;" onclick="openChannelModal()">
                <i class="fas fa-plus"></i> Add Channel
            </button>
            
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Position</th>
                            <th>Name</th>
                            <th>Channel ID</th>
                            <th>Button Text</th>
                            <th>Auto Accept</th>
                            <th>Status</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody id="channelsList"></tbody>
                </table>
            </div>
        </div>
        
        <!-- Gift Codes Tab -->
        <div class="tab-content" id="giftCodes">
            <button class="btn btn-primary" style="margin-bottom: 20px;" onclick="openGiftModal()">
                <i class="fas fa-plus"></i> Generate Gift Code
            </button>
            
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Code</th>
                            <th>Range</th>
                            <th>Total</th>
                            <th>Used</th>
                            <th>Expires</th>
                            <th>Status</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody id="giftCodesBody"></tbody>
                </table>
            </div>
        </div>
        
        <!-- Settings Tab -->
        <div class="tab-content" id="settings">
            <form id="settingsForm" onsubmit="saveSettings(event)">
                <div class="cards-grid">
                    <div class="stat-card">
                        <h3><i class="fas fa-robot"></i> Bot Settings</h3>
                        <div class="form-group">
                            <label class="form-label">Bot Name</label>
                            <input type="text" class="form-control" name="botName" value="<%= settings.botName %>" required>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Bot Logo</label>
                            <input type="file" class="form-control" name="botLogo" accept="image/*" id="botLogo">
                            <% if (settings.botLogo) { %>
                                <div style="margin-top: 15px; text-align: center;">
                                    <img src="<%= settings.botLogo %>" style="width: 80px; height: 80px; border-radius: 16px; border: 2px solid var(--accent);" alt="Current Logo">
                                    <p style="color: var(--text-secondary); font-size: 0.85rem; margin-top: 5px;">Current Logo</p>
                                </div>
                            <% } %>
                        </div>
                    </div>
                    
                    <div class="stat-card">
                        <h3><i class="fas fa-coins"></i> Financial Settings</h3>
                        <div class="form-group">
                            <label class="form-label">Min Withdraw (₹)</label>
                            <input type="number" class="form-control" name="minWithdraw" value="<%= settings.minWithdraw %>" min="1" required>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Max Withdraw (₹)</label>
                            <input type="number" class="form-control" name="maxWithdraw" value="<%= settings.maxWithdraw %>" min="1" required>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Refer Bonus (₹)</label>
                            <input type="number" class="form-control" name="referBonus" value="<%= settings.referBonus %>" min="0" required>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Welcome Bonus (₹)</label>
                            <input type="number" class="form-control" name="welcomeBonus" value="<%= settings.welcomeBonus %>" min="0" required>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Withdraw Tax (%)</label>
                            <input type="number" class="form-control" name="withdrawTax" value="<%= settings.withdrawTax %>" min="0" max="100" required>
                        </div>
                    </div>
                    
                    <div class="stat-card">
                        <h3><i class="fas fa-gift"></i> Gift Settings</h3>
                        <div class="form-group">
                            <label class="form-label">Min Gift Amount (₹)</label>
                            <input type="number" class="form-control" name="minGiftAmount" value="<%= settings.minGiftAmount %>" min="1" required>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Max Gift Amount (₹)</label>
                            <input type="number" class="form-control" name="maxGiftAmount" value="<%= settings.maxGiftAmount %>" min="1" required>
                        </div>
                    </div>
                    
                    <div class="stat-card">
                        <h3><i class="fas fa-toggle-on"></i> Toggle Settings</h3>
                        <div class="form-group">
                            <label class="form-label">Bot Enabled</label>
                            <label class="toggle-switch">
                                <input type="checkbox" name="botEnabled" <%= settings.botEnabled ? 'checked' : '' %>>
                                <span class="toggle-slider"></span>
                            </label>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Device Verification</label>
                            <label class="toggle-switch">
                                <input type="checkbox" name="deviceVerification" <%= settings.deviceVerification ? 'checked' : '' %>>
                                <span class="toggle-slider"></span>
                            </label>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Auto Withdraw (API)</label>
                            <label class="toggle-switch">
                                <input type="checkbox" name="autoWithdraw" <%= settings.autoWithdraw ? 'checked' : '' %>>
                                <span class="toggle-slider"></span>
                            </label>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Withdrawals Enabled</label>
                            <label class="toggle-switch">
                                <input type="checkbox" name="withdrawalsEnabled" <%= settings.withdrawalsEnabled ? 'checked' : '' %>>
                                <span class="toggle-slider"></span>
                            </label>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Channel Verification</label>
                            <label class="toggle-switch">
                                <input type="checkbox" name="channelVerification" <%= settings.channelVerification ? 'checked' : '' %>>
                                <span class="toggle-slider"></span>
                            </label>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Auto Accept Private</label>
                            <label class="toggle-switch">
                                <input type="checkbox" name="autoAcceptPrivate" <%= settings.autoAcceptPrivate ? 'checked' : '' %>>
                                <span class="toggle-slider"></span>
                            </label>
                        </div>
                    </div>
                    
                    <div class="stat-card">
                        <h3><i class="fas fa-user-shield"></i> Admin Settings</h3>
                        <div class="form-group">
                            <label class="form-label">Add Admin (User ID)</label>
                            <div class="search-box">
                                <input type="number" class="form-control" id="newAdminId" placeholder="Enter User ID">
                                <button type="button" class="btn btn-primary" onclick="addAdmin()">Add</button>
                            </div>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Current Admins</label>
                            <div id="adminsList"></div>
                        </div>
                    </div>
                </div>
                
                <button type="submit" class="btn btn-success" style="width: 100%; padding: 16px; font-size: 1.2rem; margin-top: 20px;">
                    <i class="fas fa-save"></i> Save All Settings
                </button>
            </form>
        </div>
        
        <!-- UPI Settings Tab -->
        <div class="tab-content" id="upi">
            <form id="upiForm" onsubmit="saveUPISettings(event)">
                <div class="cards-grid">
                    <div class="stat-card">
                        <h3><i class="fas fa-credit-card"></i> UPI Configuration</h3>
                        <div class="form-group">
                            <label class="form-label">Enable UPI Payments</label>
                            <label class="toggle-switch">
                                <input type="checkbox" name="upiEnabled" <%= settings.upiEnabled ? 'checked' : '' %>>
                                <span class="toggle-slider"></span>
                            </label>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Default UPI ID</label>
                            <input type="text" class="form-control" name="upiId" value="<%= settings.upiId || '' %>" placeholder="example@okhdfcbank">
                        </div>
                        <div class="form-group">
                            <label class="form-label">UPI Name</label>
                            <input type="text" class="form-control" name="upiName" value="<%= settings.upiName || '' %>" placeholder="Account Holder Name">
                        </div>
                        <div class="form-group">
                            <label class="form-label">API URL</label>
                            <input type="text" class="form-control" value="<%= EASEPAY_API %>" readonly disabled>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Test Payment</label>
                            <button type="button" class="btn btn-primary" onclick="testPayment()">
                                <i class="fas fa-vial"></i> Test API
                            </button>
                        </div>
                    </div>
                </div>
                <button type="submit" class="btn btn-success" style="width: 100%; padding: 16px; font-size: 1.2rem; margin-top: 20px;">
                    <i class="fas fa-save"></i> Save UPI Settings
                </button>
            </form>
        </div>
        
        <!-- Broadcast Tab -->
        <div class="tab-content" id="broadcast">
            <form id="broadcastForm" onsubmit="sendBroadcast(event)" enctype="multipart/form-data">
                <div class="cards-grid">
                    <div class="stat-card">
                        <h3><i class="fas fa-bullhorn"></i> Compose Message</h3>
                        <div class="form-group">
                            <label class="form-label">Message</label>
                            <textarea class="form-control" name="message" rows="8" placeholder="Enter your message here... Supports HTML formatting" required></textarea>
                            <small style="color: var(--text-secondary);">HTML tags: &lt;b&gt;, &lt;i&gt;, &lt;a href=""&gt; are supported</small>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Image (Optional)</label>
                            <input type="file" class="form-control" name="image" accept="image/*">
                        </div>
                        <div class="form-group">
                            <label class="form-label">Button Text (Optional)</label>
                            <input type="text" class="form-control" name="buttonText" placeholder="Click Here">
                        </div>
                        <div class="form-group">
                            <label class="form-label">Button URL (Optional)</label>
                            <input type="url" class="form-control" name="buttonUrl" placeholder="https://example.com">
                        </div>
                        <div class="form-group">
                            <label class="form-label">Preview</label>
                            <div style="background: var(--bg); padding: 20px; border-radius: 12px; border: 1px solid var(--border);" id="preview">
                                <div id="previewText">Your message will appear here</div>
                                <div id="previewButton" style="margin-top: 15px;"></div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="stat-card">
                        <h3><i class="fas fa-chart-pie"></i> Broadcast Stats</h3>
                        <div class="stat-value" style="font-size: 3rem;"><%= stats.totalUsers %></div>
                        <div class="stat-label">Total Recipients</div>
                        <p style="margin-top: 20px; color: var(--warning); padding: 15px; background: rgba(251, 191, 36, 0.1); border-radius: 12px;">
                            <i class="fas fa-exclamation-triangle"></i> 
                            Broadcasting to all users may take some time depending on the number of users.
                        </p>
                        <button type="submit" class="btn btn-primary" style="width: 100%; padding: 16px; font-size: 1.2rem;">
                            <i class="fas fa-paper-plane"></i> Send to All Users
                        </button>
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
            <form id="channelForm" onsubmit="saveChannel(event)">
                <input type="hidden" name="channelId" id="channelId">
                <div class="form-group">
                    <label class="form-label">Channel Name</label>
                    <input type="text" class="form-control" name="name" id="channelName" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Channel ID/Username</label>
                    <input type="text" class="form-control" name="channelId" id="channelChannelId" placeholder="@channel or -100123456789" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Button Text</label>
                    <input type="text" class="form-control" name="buttonText" id="channelButtonText" value="Join Channel">
                </div>
                <div class="form-group">
                    <label class="form-label">Invite Link</label>
                    <input type="url" class="form-control" name="link" id="channelLink" placeholder="https://t.me/..." required>
                </div>
                <div class="form-group">
                    <label class="form-label">Description</label>
                    <input type="text" class="form-control" name="description" id="channelDescription">
                </div>
                <div class="form-group">
                    <label class="form-label">Position</label>
                    <input type="number" class="form-control" name="position" id="channelPosition" value="0">
                </div>
                <div class="form-group">
                    <label class="form-label">
                        <input type="checkbox" name="autoAccept" id="channelAutoAccept">
                        Auto Accept (for private channels)
                    </label>
                </div>
                <div class="form-group">
                    <label class="form-label">
                        <input type="checkbox" name="enabled" id="channelEnabled" checked>
                        Enabled
                    </label>
                </div>
                <button type="submit" class="btn btn-success">Save Channel</button>
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
            <form id="giftForm" onsubmit="saveGiftCode(event)">
                <input type="hidden" name="codeId" id="codeId">
                <div class="form-group">
                    <label class="form-label">Code (6 digits)</label>
                    <div class="search-box">
                        <input type="text" class="form-control" name="code" id="code" maxlength="6" pattern="[A-Z0-9]{6}" required>
                        <button type="button" class="btn btn-primary" onclick="generateCode()">Generate</button>
                    </div>
                </div>
                <div class="form-group">
                    <label class="form-label">Min Amount (₹)</label>
                    <input type="number" class="form-control" name="minAmount" id="minAmount" min="1" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Max Amount (₹)</label>
                    <input type="number" class="form-control" name="maxAmount" id="maxAmount" min="1" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Total Users</label>
                    <input type="number" class="form-control" name="totalUsers" id="totalUsers" min="1" value="1" required>
                </div>
                <div class="form-group">
                    <label class="form-label">Expiry (minutes)</label>
                    <input type="number" class="form-control" name="expiryMinutes" id="expiryMinutes" min="1" value="1440" required>
                </div>
                <button type="submit" class="btn btn-success">Generate Code</button>
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
            <div id="userDetails" style="margin-bottom: 25px;"></div>
            
            <h4><i class="fas fa-plus-circle" style="color: var(--success);"></i> Add Balance</h4>
            <div class="form-group">
                <input type="number" class="form-control" id="addBalanceAmount" placeholder="Amount">
                <input type="text" class="form-control" id="addBalanceReason" placeholder="Reason" style="margin-top: 10px;">
                <button class="btn btn-primary" style="margin-top: 15px; width: 100%;" onclick="addUserBalance()">
                    <i class="fas fa-plus-circle"></i> Add Balance
                </button>
            </div>
            
            <h4 style="margin-top: 25px;"><i class="fas fa-history"></i> Recent Transactions</h4>
            <div id="userTransactions" style="max-height: 250px; overflow-y: auto;"></div>
        </div>
    </div>
    
    <!-- Add Balance Modal (for users list) -->
    <div class="modal" id="addBalanceModal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>Add Balance</h3>
                <button class="close-btn" onclick="closeAddBalanceModal()">&times;</button>
            </div>
            <div class="form-group">
                <label class="form-label">User ID: <span id="balanceUserId"></span></label>
                <input type="number" class="form-control" id="balanceAmount" placeholder="Amount">
                <input type="text" class="form-control" id="balanceReason" placeholder="Reason" style="margin-top: 10px;">
                <button class="btn btn-success" style="margin-top: 20px; width: 100%;" onclick="submitAddBalance()">
                    <i class="fas fa-plus-circle"></i> Add Balance
                </button>
            </div>
        </div>
    </div>
    
    <script>
        const urlParams = new URLSearchParams(window.location.search);
        const adminUserId = urlParams.get('userId');
        
        if (!adminUserId) {
            window.location.href = '/admin-login';
        }
        
        let currentWithdrawalStatus = 'pending';
        let channels = <%- JSON.stringify(channels || []) %>;
        let settings = <%- JSON.stringify(settings) %>;
        let withdrawals = [];
        let giftCodes = [];
        let users = <%- JSON.stringify(users || []) %>;
        let currentUserId = null;
        
        // Initialize
        document.addEventListener('DOMContentLoaded', () => {
            updatePendingCount();
            loadTodayStats();
            renderAdmins();
            renderChannels();
            loadGiftCodes();
            setupPreview();
        });
        
        function updatePendingCount() {
            fetch('/api/admin/withdrawals?status=pending&userId=' + adminUserId)
                .then(res => res.json())
                .then(data => {
                    document.getElementById('pendingCount').textContent = data.length;
                });
        }
        
        function loadTodayStats() {
            const today = new Date().toDateString();
            
            // Today's users
            const todayUsers = users.filter(u => new Date(u.createdAt).toDateString() === today).length;
            document.getElementById('todayUsers').textContent = todayUsers;
            
            // Today's withdrawals and earnings would need separate API calls
            fetch('/api/admin/stats/today?userId=' + adminUserId)
                .then(res => res.json())
                .then(data => {
                    document.getElementById('todayWithdrawals').textContent = data.withdrawals || 0;
                    document.getElementById('todayEarnings').textContent = '₹' + (data.earnings || 0);
                })
                .catch(err => console.error(err));
        }
        
        function refreshDashboard() {
            window.location.reload();
        }
        
        function switchTab(tab) {
            document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            
            document.querySelector(`.nav-tab[onclick="switchTab('${tab}')"]`).classList.add('active');
            document.getElementById(tab).classList.add('active');
            
            if (tab === 'withdrawals') loadWithdrawals('pending');
            if (tab === 'channels') renderChannels();
            if (tab === 'giftCodes') loadGiftCodes();
            if (tab === 'settings') renderAdmins();
        }
        
        function loadWithdrawals(status) {
            currentWithdrawalStatus = status;
            fetch('/api/admin/withdrawals?status=' + (status !== 'all' ? status : '') + '&userId=' + adminUserId)
                .then(res => res.json())
                .then(data => {
                    withdrawals = data;
                    renderWithdrawals();
                    
                    // Update filter buttons
                    document.querySelectorAll('.filter-btn').forEach(btn => {
                        btn.classList.remove('active');
                        if (btn.textContent.toLowerCase().includes(status)) {
                            btn.classList.add('active');
                        }
                    });
                })
                .catch(err => {
                    console.error(err);
                    alert('Error loading withdrawals');
                });
        }
        
        function renderWithdrawals() {
            const tbody = document.getElementById('withdrawalsBody');
            if (!tbody) return;
            
            if (withdrawals.length === 0) {
                tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; padding: 40px;">No withdrawals found</td></tr>';
                return;
            }
            
            tbody.innerHTML = withdrawals.map(w => {
                const statusColor = w.status === 'pending' ? 'var(--warning)' : 
                                   w.status === 'completed' ? 'var(--success)' : 'var(--danger)';
                return `
                <tr>
                    <td><strong>${w.userId}</strong></td>
                    <td>₹${w.amount}</td>
                    <td>₹${w.tax}</td>
                    <td><strong>₹${w.netAmount}</strong></td>
                    <td>${w.upiId}</td>
                    <td><span class="badge" style="background: ${statusColor}">${w.status}</span></td>
                    <td>${new Date(w.createdAt).toLocaleString()}</td>
                    <td>
                        ${w.status === 'pending' ? `
                            <button class="btn btn-success btn-sm" onclick="acceptWithdrawal('${w._id}')">
                                <i class="fas fa-check"></i>
                            </button>
                            <button class="btn btn-danger btn-sm" onclick="rejectWithdrawal('${w._id}')">
                                <i class="fas fa-times"></i>
                            </button>
                        ` : ''}
                    </td>
                </tr>
            `}).join('');
        }
        
        function acceptWithdrawal(id) {
            if (!confirm('Accept this withdrawal?')) return;
            
            fetch('/api/admin/withdrawals/' + id + '/accept', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ userId: adminUserId })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    alert('Withdrawal accepted' + (data.paymentSuccess ? ' and payment sent' : ''));
                    loadWithdrawals(currentWithdrawalStatus);
                    updatePendingCount();
                } else {
                    alert(data.error || 'Error accepting withdrawal');
                }
            })
            .catch(err => {
                console.error(err);
                alert('Error accepting withdrawal');
            });
        }
        
        function rejectWithdrawal(id) {
            if (!confirm('Reject this withdrawal?')) return;
            
            fetch('/api/admin/withdrawals/' + id + '/reject', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ userId: adminUserId })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    alert('Withdrawal rejected');
                    loadWithdrawals(currentWithdrawalStatus);
                    updatePendingCount();
                } else {
                    alert(data.error || 'Error rejecting withdrawal');
                }
            })
            .catch(err => {
                console.error(err);
                alert('Error rejecting withdrawal');
            });
        }
        
        function renderChannels() {
            const tbody = document.getElementById('channelsList');
            if (!tbody) return;
            
            if (!channels || channels.length === 0) {
                tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; padding: 40px;">No channels added yet</td></tr>';
                return;
            }
            
            tbody.innerHTML = channels.sort((a, b) => (a.position || 0) - (b.position || 0)).map(c => `
                <tr>
                    <td>${c.position || 0}</td>
                    <td><strong>${c.name}</strong></td>
                    <td>${c.channelId}</td>
                    <td>${c.buttonText || 'Join Channel'}</td>
                    <td>${c.autoAccept ? '✅' : '❌'}</td>
                    <td>${c.enabled !== false ? '✅' : '❌'}</td>
                    <td>
                        <button class="btn btn-primary btn-sm" onclick="editChannel('${c._id}')">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="btn btn-danger btn-sm" onclick="deleteChannel('${c._id}')">
                            <i class="fas fa-trash"></i>
                        </button>
                        <button class="btn btn-warning btn-sm" onclick="moveChannel('${c._id}', 'up')">
                            <i class="fas fa-arrow-up"></i>
                        </button>
                        <button class="btn btn-warning btn-sm" onclick="moveChannel('${c._id}', 'down')">
                            <i class="fas fa-arrow-down"></i>
                        </button>
                    </td>
                </tr>
            `).join('');
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
            data.userId = adminUserId;
            
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
                    alert(res.error || 'Error saving channel');
                }
            })
            .catch(err => {
                console.error(err);
                alert('Error saving channel');
            });
        }
        
        function editChannel(id) {
            const channel = channels.find(c => c._id === id);
            if (!channel) return;
            
            document.getElementById('channelModalTitle').innerText = 'Edit Channel';
            document.getElementById('channelId').value = channel._id;
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
            
            fetch('/api/admin/channels/' + id + '?userId=' + adminUserId, { 
                method: 'DELETE' 
            })
            .then(res => res.json())
            .then(res => {
                if (res.success) {
                    alert('Channel deleted');
                    location.reload();
                } else {
                    alert(res.error || 'Error deleting channel');
                }
            })
            .catch(err => {
                console.error(err);
                alert('Error deleting channel');
            });
        }
        
        function moveChannel(id, direction) {
            fetch('/api/admin/channels/' + id + '/move', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ direction, userId: adminUserId })
            })
            .then(res => res.json())
            .then(res => {
                if (res.success) {
                    location.reload();
                } else {
                    alert(res.error || 'Error moving channel');
                }
            })
            .catch(err => {
                console.error(err);
                alert('Error moving channel');
            });
        }
        
        function openGiftModal() {
            document.getElementById('codeId').value = '';
            document.getElementById('code').value = '';
            document.getElementById('minAmount').value = settings.minGiftAmount || 10;
            document.getElementById('maxAmount').value = settings.maxGiftAmount || 1000;
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
            for (let i = 0; i < 6; i++) {
                code += chars[Math.floor(Math.random() * chars.length)];
            }
            document.getElementById('code').value = code;
        }
        
        function loadGiftCodes() {
            fetch('/api/admin/gift-codes?userId=' + adminUserId)
                .then(res => res.json())
                .then(data => {
                    giftCodes = data;
                    renderGiftCodes();
                })
                .catch(err => {
                    console.error(err);
                });
        }
        
        function renderGiftCodes() {
            const tbody = document.getElementById('giftCodesBody');
            if (!tbody) return;
            
            if (giftCodes.length === 0) {
                tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; padding: 40px;">No gift codes generated</td></tr>';
                return;
            }
            
            tbody.innerHTML = giftCodes.map(g => {
                const isExpired = new Date() > new Date(g.expiresAt);
                return `
                <tr>
                    <td><strong>${g.code}</strong></td>
                    <td>₹${g.minAmount} - ₹${g.maxAmount}</td>
                    <td>${g.totalUsers}</td>
                    <td>${g.usedCount || 0}</td>
                    <td>${new Date(g.expiresAt).toLocaleString()}</td>
                    <td><span class="badge" style="background: ${isExpired ? 'var(--danger)' : 'var(--success)'}">${isExpired ? 'Expired' : 'Active'}</span></td>
                    <td>
                        <button class="btn btn-danger btn-sm" onclick="deleteGiftCode('${g._id}')">
                            <i class="fas fa-trash"></i>
                        </button>
                    </td>
                </tr>
            `}).join('');
        }
        
        function saveGiftCode(event) {
            event.preventDefault();
            const formData = new FormData(event.target);
            const data = Object.fromEntries(formData);
            data.userId = adminUserId;
            
            fetch('/api/admin/gift-codes', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            })
            .then(res => res.json())
            .then(res => {
                if (res.success) {
                    alert('Gift code generated');
                    closeGiftModal();
                    loadGiftCodes();
                } else {
                    alert(res.error || 'Error generating gift code');
                }
            })
            .catch(err => {
                console.error(err);
                alert('Error generating gift code');
            });
        }
        
        function deleteGiftCode(id) {
            if (!confirm('Delete this gift code?')) return;
            
            fetch('/api/admin/gift-codes/' + id + '?userId=' + adminUserId, { 
                method: 'DELETE' 
            })
            .then(res => res.json())
            .then(res => {
                if (res.success) {
                    alert('Gift code deleted');
                    loadGiftCodes();
                } else {
                    alert(res.error || 'Error deleting gift code');
                }
            })
            .catch(err => {
                console.error(err);
                alert('Error deleting gift code');
            });
        }
        
        function saveSettings(event) {
            event.preventDefault();
            const formData = new FormData(event.target);
            const data = {};
            
            // Handle file upload separately
            const logoFile = formData.get('botLogo');
            if (logoFile && logoFile.size > 0) {
                const logoFormData = new FormData();
                logoFormData.append('logo', logoFile);
                logoFormData.append('userId', adminUserId);
                
                fetch('/api/admin/upload-logo', {
                    method: 'POST',
                    body: logoFormData
                })
                .then(res => res.json())
                .then(res => {
                    if (res.success) {
                        data.botLogo = res.url;
                    }
                    saveSettingsData(formData, data);
                })
                .catch(err => {
                    console.error(err);
                    saveSettingsData(formData, data);
                });
            } else {
                saveSettingsData(formData, data);
            }
        }
        
        function saveSettingsData(formData, additionalData = {}) {
            const data = { ...additionalData, userId: adminUserId };
            
            for (const [key, value] of formData.entries()) {
                if (key !== 'botLogo') {
                    if (key === 'botEnabled' || key === 'deviceVerification' || key === 'autoWithdraw' || 
                        key === 'withdrawalsEnabled' || key === 'channelVerification' || key === 'autoAcceptPrivate' ||
                        key === 'upiEnabled') {
                        data[key] = value === 'on';
                    } else {
                        data[key] = value;
                    }
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
                    alert(res.error || 'Error saving settings');
                }
            })
            .catch(err => {
                console.error(err);
                alert('Error saving settings');
            });
        }
        
        function saveUPISettings(event) {
            event.preventDefault();
            const formData = new FormData(event.target);
            const data = {
                userId: adminUserId,
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
                    alert(res.error || 'Error saving UPI settings');
                }
            })
            .catch(err => {
                console.error(err);
                alert('Error saving UPI settings');
            });
        }
        
        function testPayment() {
            const upiId = document.querySelector('input[name="upiId"]').value;
            if (!upiId) {
                alert('Please enter a UPI ID first');
                return;
            }
            
            fetch('/api/admin/test-payment', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ upiId, userId: adminUserId })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    alert('API is working!');
                } else {
                    alert('API test failed: ' + (data.error || 'Unknown error'));
                }
            })
            .catch(err => {
                alert('API test failed: ' + err.message);
            });
        }
        
        function renderAdmins() {
            const list = document.getElementById('adminsList');
            if (!list) return;
            
            if (!settings.adminIds || settings.adminIds.length === 0) {
                list.innerHTML = '<p style="color: var(--text-secondary);">No admins added</p>';
                return;
            }
            
            list.innerHTML = (settings.adminIds || []).map(id => `
                <div style="display: flex; justify-content: space-between; align-items: center; background: var(--bg); padding: 12px 15px; border-radius: 12px; margin-bottom: 8px;">
                    <span><i class="fas fa-user-shield" style="color: var(--accent);"></i> ${id}</span>
                    <button class="btn btn-danger btn-sm" onclick="removeAdmin('${id}')">Remove</button>
                </div>
            `).join('');
        }
        
        function addAdmin() {
            const newId = document.getElementById('newAdminId').value;
            if (!newId) return;
            
            if (!settings.adminIds) settings.adminIds = [];
            if (!settings.adminIds.includes(parseInt(newId))) {
                settings.adminIds.push(parseInt(newId));
                renderAdmins();
            }
            document.getElementById('newAdminId').value = '';
        }
        
        function removeAdmin(id) {
            if (id == adminUserId) {
                alert('You cannot remove yourself');
                return;
            }
            settings.adminIds = settings.adminIds.filter(a => a != id);
            renderAdmins();
        }
        
        function sendBroadcast(event) {
            event.preventDefault();
            const formData = new FormData(event.target);
            formData.append('userId', adminUserId);
            
            if (!confirm('Send broadcast to all ' + <%= stats.totalUsers %> + ' users?')) return;
            
            fetch('/api/admin/broadcast', {
                method: 'POST',
                body: formData
            })
            .then(res => res.json())
            .then(res => {
                if (res.success) {
                    alert('Broadcast sent to ' + res.sent + ' users');
                    document.getElementById('broadcastForm').reset();
                } else {
                    alert(res.error || 'Error sending broadcast');
                }
            })
            .catch(err => {
                console.error(err);
                alert('Error sending broadcast');
            });
        }
        
        function setupPreview() {
            const messageInput = document.querySelector('textarea[name="message"]');
            const buttonTextInput = document.querySelector('input[name="buttonText"]');
            const buttonUrlInput = document.querySelector('input[name="buttonUrl"]');
            
            function updatePreview() {
                const previewText = document.getElementById('previewText');
                const previewButton = document.getElementById('previewButton');
                
                previewText.innerHTML = messageInput.value || 'Your message will appear here';
                
                if (buttonTextInput.value && buttonUrlInput.value) {
                    previewButton.innerHTML = `<button class="btn btn-primary" style="width: auto;" onclick="window.open('${buttonUrlInput.value}', '_blank')">${buttonTextInput.value}</button>`;
                } else {
                    previewButton.innerHTML = '';
                }
            }
            
            messageInput.addEventListener('input', updatePreview);
            buttonTextInput.addEventListener('input', updatePreview);
            buttonUrlInput.addEventListener('input', updatePreview);
        }
        
        function viewUser(userId) {
            fetch('/api/admin/users/' + userId + '?userId=' + adminUserId)
                .then(res => res.json())
                .then(user => {
                    document.getElementById('userDetails').innerHTML = `
                        <div style="display: flex; align-items: center; gap: 20px; margin-bottom: 20px;">
                            <div class="avatar">
                                <i class="fas fa-user"></i>
                            </div>
                            <div>
                                <h2 style="margin-bottom: 5px;">${user.fullName || 'User'}</h2>
                                <p style="color: var(--text-secondary);">@${user.username || 'N/A'}</p>
                            </div>
                        </div>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
                            <div style="background: var(--bg); padding: 15px; border-radius: 12px;">
                                <div style="color: var(--text-secondary);">User ID</div>
                                <div style="font-weight: bold;">${user.userId}</div>
                            </div>
                            <div style="background: var(--bg); padding: 15px; border-radius: 12px;">
                                <div style="color: var(--text-secondary);">Balance</div>
                                <div style="font-weight: bold; color: var(--success);">₹${user.balance.toFixed(2)}</div>
                            </div>
                            <div style="background: var(--bg); padding: 15px; border-radius: 12px;">
                                <div style="color: var(--text-secondary);">Refer Code</div>
                                <div style="font-weight: bold;">${user.referCode}</div>
                            </div>
                            <div style="background: var(--bg); padding: 15px; border-radius: 12px;">
                                <div style="color: var(--text-secondary);">Referrals</div>
                                <div style="font-weight: bold;">${user.referralCount || 0}</div>
                            </div>
                            <div style="background: var(--bg); padding: 15px; border-radius: 12px;">
                                <div style="color: var(--text-secondary);">Verified</div>
                                <div style="font-weight: bold;">${user.verified ? '✅ Yes' : '❌ No'}</div>
                            </div>
                            <div style="background: var(--bg); padding: 15px; border-radius: 12px;">
                                <div style="color: var(--text-secondary);">Joined</div>
                                <div style="font-weight: bold;">${new Date(user.createdAt).toLocaleString()}</div>
                            </div>
                        </div>
                        <div style="margin-top: 20px;">
                            <p><strong>Device ID:</strong> ${user.deviceId || 'N/A'}</p>
                            <p><strong>Channels Joined:</strong> ${(user.joinedChannels || []).length}</p>
                        </div>
                    `;
                    
                    // Load transactions
                    fetch('/api/admin/users/' + userId + '/transactions?userId=' + adminUserId)
                        .then(res => res.json())
                        .then(transactions => {
                            const txDiv = document.getElementById('userTransactions');
                            if (transactions.length === 0) {
                                txDiv.innerHTML = '<p style="color: var(--text-secondary);">No transactions yet</p>';
                            } else {
                                txDiv.innerHTML = transactions.map(tx => `
                                    <div style="background: var(--bg); padding: 12px; border-radius: 12px; margin-bottom: 8px;">
                                        <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                                            <span>${tx.description}</span>
                                            <span style="color: ${tx.type === 'credit' ? 'var(--success)' : 'var(--danger)'}; font-weight: bold;">
                                                ${tx.type === 'credit' ? '+' : '-'} ₹${tx.amount}
                                            </span>
                                        </div>
                                        <div style="color: var(--text-secondary); font-size: 0.85rem;">
                                            ${new Date(tx.createdAt).toLocaleString()}
                                        </div>
                                    </div>
                                `).join('');
                            }
                        });
                    
                    document.getElementById('userModal').style.display = 'flex';
                    window.currentUserId = userId;
                })
                .catch(err => {
                    console.error(err);
                    alert('Error loading user details');
                });
        }
        
        function closeUserModal() {
            document.getElementById('userModal').style.display = 'none';
        }
        
        function addBalanceModal(userId) {
            document.getElementById('balanceUserId').textContent = userId;
            document.getElementById('addBalanceModal').style.display = 'flex';
            window.currentUserId = userId;
        }
        
        function closeAddBalanceModal() {
            document.getElementById('addBalanceModal').style.display = 'none';
            document.getElementById('balanceAmount').value = '';
            document.getElementById('balanceReason').value = '';
        }
        
        function submitAddBalance() {
            const amount = document.getElementById('balanceAmount').value;
            const reason = document.getElementById('balanceReason').value;
            
            if (!amount || !reason) {
                alert('Enter amount and reason');
                return;
            }
            
            fetch('/api/admin/users/' + window.currentUserId + '/add-balance', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    amount: parseFloat(amount), 
                    reason,
                    userId: adminUserId 
                })
            })
            .then(res => res.json())
            .then(res => {
                if (res.success) {
                    alert('Balance added');
                    closeAddBalanceModal();
                    location.reload();
                } else {
                    alert(res.error || 'Error adding balance');
                }
            })
            .catch(err => {
                console.error(err);
                alert('Error adding balance');
            });
        }
        
        function addUserBalance() {
            const amount = document.getElementById('addBalanceAmount').value;
            const reason = document.getElementById('addBalanceReason').value;
            
            if (!amount || !reason) {
                alert('Enter amount and reason');
                return;
            }
            
            fetch('/api/admin/users/' + window.currentUserId + '/add-balance', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    amount: parseFloat(amount), 
                    reason,
                    userId: adminUserId 
                })
            })
            .then(res => res.json())
            .then(res => {
                if (res.success) {
                    alert('Balance added');
                    viewUser(window.currentUserId);
                    document.getElementById('addBalanceAmount').value = '';
                    document.getElementById('addBalanceReason').value = '';
                } else {
                    alert(res.error || 'Error adding balance');
                }
            })
            .catch(err => {
                console.error(err);
                alert('Error adding balance');
            });
        }
        
        function searchUsers() {
            const query = document.getElementById('searchUser').value;
            if (!query) return;
            
            fetch('/api/admin/users/search?q=' + encodeURIComponent(query) + '&userId=' + adminUserId)
                .then(res => res.json())
                .then(users => {
                    if (users && users.length > 0) {
                        const tbody = document.querySelector('#usersTable tbody');
                        tbody.innerHTML = users.map(user => `
                            <tr>
                                <td>${user.userId}</td>
                                <td>${user.fullName || 'N/A'}</td>
                                <td>@${user.username || 'N/A'}</td>
                                <td>₹${user.balance.toFixed(2)}</td>
                                <td>${user.referCode}</td>
                                <td>${user.referralCount || 0}</td>
                                <td>${user.verified ? '✅' : '❌'}</td>
                                <td>${new Date(user.createdAt).toLocaleDateString()}</td>
                                <td>
                                    <button class="btn btn-primary btn-sm" onclick="viewUser('${user.userId}')">
                                        <i class="fas fa-eye"></i>
                                    </button>
                                    <button class="btn btn-success btn-sm" onclick="addBalanceModal('${user.userId}')">
                                        <i class="fas fa-plus-circle"></i>
                                    </button>
                                </td>
                            </tr>
                        `).join('');
                    } else {
                        alert('No users found');
                    }
                })
                .catch(err => {
                    console.error(err);
                    alert('Error searching users');
                });
        }
        
        function exportUsers() {
            window.location.href = '/api/admin/export-users?userId=' + adminUserId;
        }
        
        function logout() {
            window.location.href = '/admin-login';
        }
    </script>
</body>
</html>`;

    fs.writeFileSync(path.join(viewsDir, 'admin.ejs'), adminEJS);
    
    // Admin Login Page
    const adminLoginEJS = `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Login</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Inter', sans-serif;
        }
        
        body {
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            color: white;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            padding: 20px;
        }
        
        .login-container {
            background: rgba(30, 41, 59, 0.8);
            backdrop-filter: blur(10px);
            padding: 50px;
            border-radius: 30px;
            width: 100%;
            max-width: 450px;
            box-shadow: 0 30px 60px rgba(0,0,0,0.5);
            border: 1px solid rgba(96, 165, 250, 0.2);
            text-align: center;
        }
        
        .logo {
            width: 100px;
            height: 100px;
            background: linear-gradient(135deg, #60a5fa, #34d399);
            border-radius: 30px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 30px;
            font-size: 3rem;
            color: white;
            box-shadow: 0 10px 30px rgba(96, 165, 250, 0.3);
        }
        
        h1 {
            color: #60a5fa;
            margin-bottom: 30px;
            font-size: 2.2rem;
        }
        
        .form-group {
            margin-bottom: 25px;
            text-align: left;
        }
        
        label {
            display: block;
            margin-bottom: 10px;
            color: #cbd5e1;
            font-weight: 500;
            font-size: 0.95rem;
        }
        
        input {
            width: 100%;
            padding: 16px 20px;
            border-radius: 15px;
            border: 1px solid #334155;
            background: #0f172a;
            color: white;
            font-size: 1rem;
            transition: all 0.3s;
        }
        
        input:focus {
            outline: none;
            border-color: #60a5fa;
            box-shadow: 0 0 0 4px rgba(96, 165, 250, 0.2);
        }
        
        button {
            width: 100%;
            padding: 16px;
            background: linear-gradient(135deg, #60a5fa, #3b82f6);
            color: white;
            border: none;
            border-radius: 15px;
            font-size: 1.2rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
        }
        
        button:hover {
            transform: translateY(-3px);
            box-shadow: 0 10px 30px rgba(96, 165, 250, 0.4);
        }
        
        .info {
            margin-top: 25px;
            color: #94a3b8;
            font-size: 0.9rem;
        }
        
        .info a {
            color: #60a5fa;
            text-decoration: none;
        }
        
        .info a:hover {
            text-decoration: underline;
        }
        
        .error {
            color: #f87171;
            margin-top: 15px;
            padding: 12px;
            background: rgba(248, 113, 113, 0.1);
            border-radius: 10px;
            display: none;
        }
        
        .demo {
            margin-top: 20px;
            padding: 15px;
            background: rgba(96, 165, 250, 0.1);
            border-radius: 12px;
            font-size: 0.9rem;
            color: #cbd5e1;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <div class="logo">
            <i class="fas fa-crown"></i>
        </div>
        
        <h1>Admin Login</h1>
        
        <div class="form-group">
            <label><i class="fas fa-user"></i> Telegram User ID</label>
            <input type="text" id="userId" placeholder="Enter your Telegram User ID" value="8469993808">
        </div>
        
        <button onclick="login()">
            <i class="fas fa-sign-in-alt"></i> Access Admin Panel
        </button>
        
        <div class="error" id="errorMsg">Invalid User ID or not authorized</div>
        
        <div class="demo">
            <i class="fas fa-info-circle"></i> Demo Admin ID: <strong>8469993808</strong>
        </div>
        
        <div class="info">
            <p>Don't know your User ID?</p>
            <p>Message <a href="https://t.me/userinfobot" target="_blank">@userinfobot</a> on Telegram</p>
        </div>
    </div>
    
    <script src="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/js/all.min.js"></script>
    <script>
        function login() {
            const userId = document.getElementById('userId').value.trim();
            if (!userId) {
                showError('Please enter User ID');
                return;
            }
            
            window.location.href = '/admin?userId=' + userId;
        }
        
        function showError(msg) {
            const errorEl = document.getElementById('errorMsg');
            errorEl.style.display = 'block';
            errorEl.textContent = msg;
            setTimeout(() => {
                errorEl.style.display = 'none';
            }, 3000);
        }
        
        // Check URL for error param
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.get('error')) {
            showError('Unauthorized access');
        }
    </script>
</body>
</html>`;

    fs.writeFileSync(path.join(viewsDir, 'admin-login.ejs'), adminLoginEJS);
    
    console.log('✅ All EJS templates created successfully');
}

createEJSFiles();

// ==========================================

// ==========================================
// 🤖 BOT SETUP
// ==========================================
const bot = new Telegraf(BOT_TOKEN);

bot.use(telegrafSession());

// Device verification middleware
bot.use(async (ctx, next) => {
    if (!ctx.from) return next();
    
    try {
        const settings = await getSettings();
        if (settings.botEnabled === false) {
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
            // Generate device ID based on user ID (more reliable for Telegram)
            const deviceId = `tg_${userId}`;
            
            const settings = await getSettings();
            
            // Fix: Only check for exact same device ID, not IP
            if (settings.deviceVerification) {
                const existingDevice = await db.collection('users').findOne({
                    deviceId
                });
                
                if (existingDevice) {
                    return ctx.reply('❌ This device has already been used. Only one account per device is allowed.');
                }
            }
            
            // Create new user
            const referCode = generateReferCode();
            const welcomeBonus = settings.welcomeBonus || 5;
            
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
            if (referrerCode && referrerCode !== referCode) {
                const referrer = await db.collection('users').findOne({ referCode: referrerCode.toUpperCase() });
                if (referrer && referrer.userId !== userId) {
                    await db.collection('referrals').insertOne({
                        referrerId: referrer.userId,
                        referredId: userId,
                        referredName: user.fullName,
                        joinedAt: new Date(),
                        verified: false
                    });
                    
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
    
    if (!settings.channelVerification || channels.length === 0 || user.verified) {
        return showMainMenu(ctx, user);
    }
    
    const text = `
📢 <b>Join Required Channels</b>

Please join all the channels below to continue:

💰 You will earn ₹${settings.welcomeBonus} welcome bonus after verification.
    `;
    
    const buttons = [];
    
    for (const channel of channels) {
        const joined = user.joinedChannels && user.joinedChannels.includes(channel.channelId);
        buttons.push([
            Markup.button.url(channel.buttonText || 'Join Channel', channel.link),
            Markup.button.callback(
                joined ? '✅ Joined' : '✓ Verify',
                `verify_${channel.channelId}`
            )
        ]);
    }
    
    buttons.push([Markup.button.callback('✅ Check All', 'check_all')]);
    
    await ctx.reply(text, {
        parse_mode: 'HTML',
        ...Markup.inlineKeyboard(buttons)
    });
}

bot.action(/^verify_(.+)$/, async (ctx) => {
    const channelId = ctx.match[1];
    const userId = ctx.from.id;
    
    try {
        const channel = await db.collection('channels').findOne({ channelId });
        if (!channel) {
            return ctx.answerCbQuery('❌ Channel not found');
        }
        
        // Check membership
        let isMember = false;
        try {
            const chatMember = await ctx.telegram.getChatMember(channelId, userId);
            isMember = ['member', 'administrator', 'creator'].includes(chatMember.status);
        } catch (e) {
            console.error('Membership check error:', e);
        }
        
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
                
                // Add verification bonus
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
                
                await ctx.answerCbQuery('✅ All channels verified! Welcome bonus added!');
                await showMainMenu(ctx, user);
            }
        } else {
            await ctx.answerCbQuery('❌ You haven\'t joined the channel yet!');
        }
    } catch (error) {
        console.error('Channel verification error:', error);
        await ctx.answerCbQuery('❌ Error verifying channel');
    }
});

bot.action('check_all', async (ctx) => {
    const userId = ctx.from.id;
    
    try {
        const user = await db.collection('users').findOne({ userId });
        const channels = await db.collection('channels').find({ enabled: true }).toArray();
        const settings = await getSettings();
        
        let allJoined = true;
        const newlyJoined = [];
        
        for (const channel of channels) {
            if (!user.joinedChannels.includes(channel.channelId)) {
                try {
                    const chatMember = await ctx.telegram.getChatMember(channel.channelId, userId);
                    const isMember = ['member', 'administrator', 'creator'].includes(chatMember.status);
                    if (isMember || channel.autoAccept) {
                        newlyJoined.push(channel.channelId);
                    } else {
                        allJoined = false;
                    }
                } catch (e) {
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
        console.error('Check all error:', error);
        await ctx.answerCbQuery('❌ Error checking channels');
    }
});

async function showMainMenu(ctx, user) {
    const settings = await getSettings();
    const channels = await db.collection('channels').find({ enabled: true }).toArray(); // FIX: Define channels here
    const isAdmin = settings.adminIds.includes(ctx.from.id);
    
    const text = `
┌─━━━━━━━━━━━━━━━─┐
│   ✧ ${settings.botName} ✧    │
└─━━━━━━━━━━━━━━━─┘

👋 Welcome, ${user.fullName || 'User'}!
💰 Balance: ₹${user.balance.toFixed(2)}
🏷️ Refer Code: ${user.referCode}
✅ Verified: ${user.verified ? 'Yes' : 'No'}

🌟 <b>Main Menu</b>
    `;
    
    const buttons = [
        [Markup.button.webApp('🌐 Open Web App', `${WEB_APP_URL}/webapp?userId=${ctx.from.id}`)],
        [
            Markup.button.callback('🏠 Home', 'web_home'),
            Markup.button.callback('👥 Refer', 'web_refer'),
            Markup.button.callback('📊 History', 'web_history')
        ]
    ];
    
    if (channels && channels.length > 1) {
        buttons.push([Markup.button.callback('🔄 Reorder Channels', 'reorder_channels')]);
    }
    
    if (isAdmin) {
        buttons.push([Markup.button.webApp('👑 Admin Panel', `${WEB_APP_URL}/admin?userId=${ctx.from.id}`)]);
    }
    
    await ctx.reply(text, {
        parse_mode: 'HTML',
        ...Markup.inlineKeyboard(buttons)
    });
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
https://t.me/${ctx.botInfo.username}?start=${user.referCode}

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
        .limit(20)
        .toArray();
    
    let text = '📊 <b>Transaction History</b>\n\n';
    
    if (transactions.length === 0) {
        text += 'No transactions yet';
    } else {
        transactions.forEach(tx => {
            const sign = tx.type === 'credit' ? '+' : '-';
            text += `\n${sign} ₹${tx.amount} - ${tx.description}\n📅 ${new Date(tx.createdAt).toLocaleString()}\n`;
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
            callback_data: `reorder_select_${c._id}`
        }]);
    });
    
    keyboard.push([{ text: '🔙 Back', callback_data: 'web_home' }]);
    
    await safeEdit(ctx, text, Markup.inlineKeyboard(keyboard));
});

bot.action(/^reorder_select_(.+)$/, async (ctx) => {
    const channelId = ctx.match[1];
    const channels = await db.collection('channels').find({ enabled: true }).sort({ position: 1 }).toArray();
    const selectedIndex = channels.findIndex(c => c._id.toString() === channelId);
    
    ctx.session.reorderData = {
        channels: channels.map(c => ({ _id: c._id.toString(), name: c.name })),
        selectedIndex
    };
    
    await showReorderMenu(ctx);
});

async function showReorderMenu(ctx) {
    const data = ctx.session.reorderData;
    if (!data) return;
    
    const { channels, selectedIndex } = data;
    
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
        keyboard.push([{ text: '⬆️ Move Up', callback_data: 'reorder_up' }]);
    }
    if (selectedIndex < channels.length - 1) {
        if (selectedIndex > 0) {
            keyboard[keyboard.length - 1].push({ text: '⬇️ Move Down', callback_data: 'reorder_down' });
        } else {
            keyboard.push([{ text: '⬇️ Move Down', callback_data: 'reorder_down' }]);
        }
    }
    keyboard.push([{ text: '✅ Save', callback_data: 'reorder_save' }, { text: '🔙 Back', callback_data: 'reorder_channels' }]);
    
    await safeEdit(ctx, text, Markup.inlineKeyboard(keyboard));
}

bot.action('reorder_up', async (ctx) => {
    const data = ctx.session.reorderData;
    if (!data || data.selectedIndex <= 0) return;
    
    const channels = data.channels;
    [channels[data.selectedIndex], channels[data.selectedIndex - 1]] = 
        [channels[data.selectedIndex - 1], channels[data.selectedIndex]];
    data.selectedIndex--;
    
    await showReorderMenu(ctx);
});

bot.action('reorder_down', async (ctx) => {
    const data = ctx.session.reorderData;
    if (!data || data.selectedIndex >= data.channels.length - 1) return;
    
    const channels = data.channels;
    [channels[data.selectedIndex], channels[data.selectedIndex + 1]] = 
        [channels[data.selectedIndex + 1], channels[data.selectedIndex]];
    data.selectedIndex++;
    
    await showReorderMenu(ctx);
});

bot.action('reorder_save', async (ctx) => {
    const data = ctx.session.reorderData;
    if (!data) return;
    
    for (let i = 0; i < data.channels.length; i++) {
        await db.collection('channels').updateOne(
            { _id: new ObjectId(data.channels[i]._id) },
            { $set: { position: i } }
        );
    }
    
    delete ctx.session.reorderData;
    await ctx.answerCbQuery('✅ Channel order saved!');
    
    const user = await db.collection('users').findOne({ userId: ctx.from.id });
    await showMainMenu(ctx, user);
});

// Handle admin replies
bot.on('text', async (ctx) => {
    if (!ctx.message.reply_to_message) return;
    
    const repliedMessage = ctx.message.reply_to_message;
    if (!repliedMessage.text || !repliedMessage.text.includes('User ID:')) return;
    
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

// ==========================================
// 📱 WEB APP ROUTES
// ==========================================
app.get('/', (req, res) => {
    res.redirect('/admin-login');
});

app.get('/webapp', async (req, res) => {
    const userId = req.query.userId;
    
    if (!userId) {
        return res.send(`
            <html>
                <head>
                    <style>
                        body { background: #0f172a; color: white; font-family: Arial; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
                        .container { text-align: center; padding: 20px; }
                        h1 { color: #60a5fa; }
                        button { background: #60a5fa; color: white; border: none; padding: 15px 30px; border-radius: 10px; font-size: 16px; cursor: pointer; margin-top: 20px; }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1>❌ Access Denied</h1>
                        <p>Please open this web app from the Telegram bot:</p>
                        <p><b>@auto_vfx_bot</b></p>
                        <button onclick="window.location.href='https://t.me/auto_vfx_bot'">
                            Open Telegram Bot
                        </button>
                    </div>
                </body>
            </html>
        `);
    }
    
    try {
        const user = await db.collection('users').findOne({ userId: parseInt(userId) });
        if (!user) {
            return res.send('User not found');
        }
        
        const settings = await getSettings();
        const channels = await db.collection('channels').find({ enabled: true }).sort({ position: 1 }).toArray();
        
        const transactions = await db.collection('transactions')
            .find({ userId: user.userId })
            .sort({ createdAt: -1 })
            .limit(50)
            .toArray();
        
        const referrals = await db.collection('referrals')
            .find({ referrerId: user.userId })
            .sort({ joinedAt: -1 })
            .toArray();
        
        res.render('index', {
            currentPage: 'home',
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

app.get('/admin-login', (req, res) => {
    res.render('admin-login');
});

app.get('/admin', async (req, res) => {
    const userId = req.query.userId;
    
    if (!userId) {
        return res.redirect('/admin-login?error=1');
    }
    
    try {
        const settings = await getSettings();
        if (!settings.adminIds.includes(parseInt(userId))) {
            return res.redirect('/admin-login?error=1');
        }
        
        const users = await db.collection('users').find().sort({ createdAt: -1 }).toArray();
        const channels = await db.collection('channels').find().sort({ position: 1 }).toArray();
        
        // Add referral count to users
        for (const user of users) {
            user.referralCount = await db.collection('referrals').countDocuments({ referrerId: user.userId });
        }
        
        const stats = {
            totalUsers: users.length,
            verifiedUsers: users.filter(u => u.verified).length,
            totalBalance: users.reduce((sum, u) => sum + (u.balance || 0), 0),
            pendingWithdrawals: await db.collection('withdrawals').countDocuments({ status: 'pending' }),
            activeGiftCodes: await db.collection('giftCodes').countDocuments({ expiresAt: { $gt: new Date() } }),
            totalTransactions: await db.collection('transactions').countDocuments()
        };
        
        res.render('admin', {
            users,
            channels,
            settings,
            stats,
            EASEPAY_API
        });
    } catch (error) {
        console.error('Admin panel error:', error);
        res.status(500).send('Error loading admin panel');
    }
});

// ==========================================
// API ROUTES
// ==========================================
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
        
        if (!user.verified) {
            return res.json({ error: 'Please join all channels first' });
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
        let paymentSuccess = false;
        if (settings.autoWithdraw && settings.upiEnabled) {
            try {
                const apiUrl = EASEPAY_API
                    .replace('{upi_id}', encodeURIComponent(upiId))
                    .replace('{amount}', netAmount);
                const response = await axios.get(apiUrl);
                paymentSuccess = response.data && response.data.status === 'success';
                
                if (paymentSuccess) {
                    await db.collection('withdrawals').updateOne(
                        { _id: withdrawal._id },
                        { $set: { status: 'completed', processedAt: new Date(), autoPaid: true } }
                    );
                }
            } catch (e) {
                console.error('Auto withdraw error:', e);
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
                    `Status: ${paymentSuccess ? 'Auto-paid' : 'Pending'}\n` +
                    `Date: ${new Date().toLocaleString()}`,
                    { parse_mode: 'HTML' }
                );
            } catch (e) {}
        }
        
        res.json({ success: true, autoPaid: paymentSuccess });
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
        
        if (image) {
            fs.unlinkSync(image.path);
        }
        
        res.json({ success: true });
    } catch (error) {
        console.error('Contact error:', error);
        res.status(500).json({ error: 'Internal server error' });
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
            expiresAt: { $gt: new Date() }
        });
        
        if (!giftCode) {
            return res.json({ error: 'Invalid or expired gift code' });
        }
        
        const alreadyClaimed = await db.collection('giftClaims').findOne({
            userId: user.userId,
            giftCodeId: giftCode._id
        });
        
        if (alreadyClaimed) {
            return res.json({ error: 'You have already claimed this gift code' });
        }
        
        if (giftCode.usedCount >= giftCode.totalUsers) {
            return res.json({ error: 'Gift code has reached maximum usage' });
        }
        
        const amount = Math.floor(
            Math.random() * (giftCode.maxAmount - giftCode.minAmount + 1)
        ) + giftCode.minAmount;
        
        await db.collection('users').updateOne(
            { userId: user.userId },
            { $inc: { balance: amount } }
        );
        
        await db.collection('transactions').insertOne({
            userId: user.userId,
            amount,
            type: 'credit',
            description: `Gift code: ${code}`,
            createdAt: new Date()
        });
        
        await db.collection('giftClaims').insertOne({
            userId: user.userId,
            giftCodeId: giftCode._id,
            code,
            amount,
            claimedAt: new Date()
        });
        
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

app.post('/api/admin/upload-logo', upload.single('logo'), async (req, res) => {
    try {
        if (!req.file) {
            return res.status(400).json({ error: 'No file uploaded' });
        }
        
        const fileUrl = `${WEB_APP_URL}/uploads/${req.file.filename}`;
        
        await db.collection('settings').updateOne(
            { key: 'botLogo' },
            { $set: { value: fileUrl } },
            { upsert: true }
        );
        
        res.json({ success: true, url: fileUrl });
    } catch (error) {
        console.error('Logo upload error:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

app.get('/api/admin/withdrawals', async (req, res) => {
    const { status } = req.query;
    
    try {
        const query = status ? { status } : {};
        const withdrawals = await db.collection('withdrawals')
            .find(query)
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
        
        let paymentSuccess = false;
        if (settings.autoWithdraw && settings.upiEnabled) {
            try {
                const apiUrl = EASEPAY_API
                    .replace('{upi_id}', encodeURIComponent(withdrawal.upiId))
                    .replace('{amount}', withdrawal.netAmount);
                const response = await axios.get(apiUrl);
                paymentSuccess = response.data && response.data.status === 'success';
            } catch (e) {
                console.error('Auto withdraw error:', e);
            }
        }
        
        await db.collection('withdrawals').updateOne(
            { _id: new ObjectId(id) },
            { 
                $set: { 
                    status: paymentSuccess ? 'completed' : 'completed',
                    processedAt: new Date(),
                    processedBy: req.body.userId,
                    paymentMethod: paymentSuccess ? 'api' : 'manual'
                }
            }
        );
        
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

app.get('/api/admin/users/:userId/transactions', async (req, res) => {
    const { userId } = req.params;
    
    try {
        const transactions = await db.collection('transactions')
            .find({ userId: parseInt(userId) })
            .sort({ createdAt: -1 })
            .limit(20)
            .toArray();
        
        res.json(transactions);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.get('/api/admin/users/search', async (req, res) => {
    const { q } = req.query;
    
    try {
        const query = {
            $or: [
                { userId: parseInt(q) || 0 },
                { fullName: { $regex: q, $options: 'i' } },
                { username: { $regex: q, $options: 'i' } },
                { referCode: q.toUpperCase() }
            ]
        };
        
        const users = await db.collection('users').find(query).limit(20).toArray();
        res.json(users);
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

app.get('/api/admin/export-users', async (req, res) => {
    try {
        const users = await db.collection('users').find().toArray();
        
        let csv = 'User ID,Name,Username,Balance,Refer Code,Verified,Created At\n';
        
        users.forEach(u => {
            csv += `${u.userId},${u.fullName || ''},${u.username || ''},${u.balance},${u.referCode},${u.verified},${u.createdAt}\n`;
        });
        
        res.setHeader('Content-Type', 'text/csv');
        res.setHeader('Content-Disposition', 'attachment; filename=users.csv');
        res.send(csv);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.post('/api/admin/channels', async (req, res) => {
    const channel = req.body;
    
    try {
        if (channel._id) {
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
            if (key !== 'userId' && key !== 'botLogo') {
                await db.collection('settings').updateOne(
                    { key },
                    { $set: { value } },
                    { upsert: true }
                );
            }
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
function scheduleJobs() {
    // Clean expired gift codes every hour
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
    
    // Send daily stats at 23:59 IST
    schedule.scheduleJob('29 18 * * *', async () => {
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
                `📊 <b>Daily Stats (${new Date().toLocaleDateString()})</b>\n\n` +
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
let isShuttingDown = false;

async function start() {
    try {
        if (await connectDB()) {
            scheduleJobs();
            
            const server = app.listen(PORT, '0.0.0.0', () => {
                console.log('🌐 Server running on port ' + PORT);
                console.log('📱 Web URL: ' + WEB_APP_URL);
                console.log('🤖 Bot: @auto_vfx_bot');
                console.log('👑 Admin: ' + WEB_APP_URL + '/admin-login');
            });
            
            await bot.launch();
            console.log('✅ Bot started successfully');
            
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
