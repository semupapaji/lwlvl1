# app.py — JUBAYER HOSTING (Manual + Optional Auto + Level EXP + Accounts Delete + ALL CLEAN)
from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify, send_file
import os, sys, json, subprocess, threading, time, shutil, zipfile, hashlib, re, uuid, io
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = 'jubayer-super-secret-key-2026'
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024

# ============================================
# PATHS
# ============================================
DATA_DIR        = 'data'
SERVERS_DIR     = 'servers'
TEMPLATES_BOT   = 'templates_bot'
CONFIG_FILE     = os.path.join(DATA_DIR, 'config.json')
SERVERS_FILE    = os.path.join(DATA_DIR, 'servers.json')
ROTATION_FILE   = os.path.join(DATA_DIR, 'rotation.json')
ACCOUNTS_FILE   = 'accounts.json'
LEVEL_EXP_FILE  = 'level_exp.json'

MAX_SERVERS     = 40
BATCH_SIZE      = 5
BATCH_DURATION  = 7 * 3600

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(SERVERS_DIR, exist_ok=True)
os.makedirs(TEMPLATES_BOT, exist_ok=True)

MASTER_USERNAME      = 'SEMY'
MASTER_PASSWORD_HASH = hashlib.sha256('M4X'.encode()).hexdigest()

# ============================================
# LEVEL EXP DATA
# ============================================
_LEVEL_DATA = {}

def load_level_exp():
    global _LEVEL_DATA
    try:
        if os.path.exists(LEVEL_EXP_FILE):
            with open(LEVEL_EXP_FILE, 'r', encoding='utf-8') as f:
                _LEVEL_DATA = json.load(f)
            print(f"[level_exp] ✅ Loaded {len(_LEVEL_DATA)} levels")
        else:
            print(f"[level_exp] ⚠️ {LEVEL_EXP_FILE} not found")
            _LEVEL_DATA = {}
    except Exception as e:
        print(f"[level_exp] ❌ load error: {e}")
        _LEVEL_DATA = {}

def get_next_level_info(current_level, current_exp):
    info = {
        'level': current_level,
        'exp_current': current_exp,
        'exp_for_next': 0,
        'exp_in_level': 0,
        'percent': 0.0,
        'next_level': current_level + 1
    }
    if not _LEVEL_DATA:
        return info
    lvl_key = str(current_level)
    if lvl_key not in _LEVEL_DATA:
        return info
    lvl_data = _LEVEL_DATA[lvl_key]
    start_exp  = lvl_data.get('exp', 0)
    need_total = lvl_data.get('exp_needed_for_next_level', 0)
    exp_in_level = max(0, current_exp - start_exp)
    info['exp_in_level'] = exp_in_level
    info['exp_for_next']  = need_total
    if need_total > 0:
        pct = (exp_in_level / need_total) * 100.0
        info['percent'] = round(min(pct, 100.0), 1)
    return info

# ============================================
# JSON STORAGE
# ============================================
def load_config():
    if not os.path.exists(CONFIG_FILE):
        d = {'username': 'admin',
             'password_hash': hashlib.sha256('admin123'.encode()).hexdigest()}
        save_config(d); return d
    with open(CONFIG_FILE) as f: return json.load(f)

def save_config(d):
    with open(CONFIG_FILE, 'w') as f: json.dump(d, f, indent=4)

def load_servers():
    if not os.path.exists(SERVERS_FILE): return {'servers': []}
    with open(SERVERS_FILE) as f: return json.load(f)

def save_servers(d):
    with open(SERVERS_FILE, 'w') as f: json.dump(d, f, indent=4)

def get_server(sid):
    for s in load_servers()['servers']:
        if s['id'] == sid: return s
    return None

def update_server(sid, patch):
    d = load_servers()
    for s in d['servers']:
        if s['id'] == sid: s.update(patch); break
    save_servers(d)

def verify_user_login(u, p):
    c = load_config()
    return u == c.get('username') and \
           hashlib.sha256(p.encode()).hexdigest() == c.get('password_hash')

def verify_master_login(u, p):
    return u == MASTER_USERNAME and \
           hashlib.sha256(p.encode()).hexdigest() == MASTER_PASSWORD_HASH

def login_required(f):
    @wraps(f)
    def deco(*a, **k):
        if 'logged_in' not in session: return redirect(url_for('login'))
        return f(*a, **k)
    return deco

def safe_join(base, sub):
    p = os.path.abspath(os.path.join(base, sub))
    if not p.startswith(os.path.abspath(base)): return None
    return p

def server_folder(sid):
    s = get_server(sid)
    if not s: return None
    return os.path.join(SERVERS_DIR, s['folder'])

# ============================================
# LOG PARSER — NEW main.py LOG FORMAT
# ============================================
def parse_stats_from_log(folder):
    st = {
        'nickname': '—',
        'level': 0,
        'exp_total': 0,      # current total exp (e.g. 8560)
        'exp_start': 0,      # starting exp (e.g. 8481)
        'exp_gained': 0,     # +79
        'uid': '—',
        'exp_for_next': 0,
        'exp_in_level': 0,
        'percent': 0.0,
    }
    lf = os.path.join(folder, 'output.log')
    if not os.path.exists(lf):
        return st

    # "  👤 SEMY-G⁰⁰¹ (UID 18686972729)"
    nick_re = re.compile(r'👤\s+(.+?)\s+\(UID\s+(\d+)\)')

    # "     IND | Lvl 12 | Matches 2"
    lvl_re = re.compile(r'\|\s*Lvl\s+(\d+)\s*\|')

    # "     EXP 8481 → 8560 | +79"
    # Group1=start, Group2=current_total, Group3=gained
    exp_re = re.compile(r'EXP\s+(\d+)\s*→\s*(\d+)\s*\|\s*\+?(\d+)')

    # "    💰 EXP +79 | Total +79 | Lvl 12"
    exp2_re = re.compile(r'💰\s*EXP\s*\+?(\d+)\s*\|\s*Total\s*\+?(\d+)\s*\|\s*Lvl\s+(\d+)')

    try:
        with open(lf, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                m = nick_re.search(line)
                if m:
                    st['nickname'] = m.group(1).strip()
                    st['uid'] = m.group(2)

                m = lvl_re.search(line)
                if m:
                    st['level'] = max(st['level'], int(m.group(1)))

                m = exp_re.search(line)
                if m:
                    st['exp_start']  = int(m.group(1))
                    st['exp_total']  = int(m.group(2))
                    st['exp_gained'] = int(m.group(3))

                m = exp2_re.search(line)
                if m:
                    st['exp_gained'] = int(m.group(1))
                    st['exp_total']  = int(m.group(2))
                    st['level']      = max(st['level'], int(m.group(3)))
    except Exception:
        pass

    lvl_info = get_next_level_info(st['level'], st['exp_total'])
    st['exp_for_next'] = lvl_info['exp_for_next']
    st['exp_in_level'] = lvl_info['exp_in_level']
    st['percent']      = lvl_info['percent']
    return st

# ============================================
# TEMPLATE DEFAULTS
# ============================================
def ensure_template_defaults():
    main_py = os.path.join(TEMPLATES_BOT, 'main.py')
    if not os.path.exists(main_py):
        with open(main_py, 'w', encoding='utf-8') as f:
            f.write('''import time
print("Bot started on JUBAYER HOSTING")
i=0
while True:
    i+=1
    print(f"[{time.strftime('%I:%M:%S %p')}] Heartbeat #{i}")
    time.sleep(5)
''')
    req = os.path.join(TEMPLATES_BOT, 'requirements.txt')
    if not os.path.exists(req):
        with open(req, 'w', encoding='utf-8') as f:
            f.write('# add pip packages here\n')

# ============================================
# CREATE SERVER
# ============================================
def create_server_dir(sid):
    folder = os.path.join(SERVERS_DIR, sid)
    os.makedirs(folder, exist_ok=True)
    if os.path.exists(TEMPLATES_BOT):
        for item in os.listdir(TEMPLATES_BOT):
            if item.startswith('.'): continue
            if item == 'accounts.json': continue
            src = os.path.join(TEMPLATES_BOT, item)
            dst = os.path.join(folder, item)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
    acc = os.path.join(folder, 'accounts.json')
    if not os.path.exists(acc):
        with open(acc, 'w', encoding='utf-8') as f:
            f.write('[]\n')
    return folder

# ============================================
# RUN BOT
# ============================================
def kill_pid(pid):
    try:
        if sys.platform == 'win32':
            subprocess.run(['taskkill', '/F', '/PID', str(pid)], capture_output=True)
        else:
            import signal
            os.killpg(os.getpgid(pid), signal.SIGTERM)
    except Exception:
        try: os.kill(pid, 15)
        except Exception: pass

def run_bot_server(server_id):
    s = get_server(server_id)
    if not s: return None, "Server not found"
    folder    = os.path.join(SERVERS_DIR, s['folder'])
    main_file = s.get('main_file', 'main.py')
    main_path = os.path.join(folder, main_file)
    log_file  = os.path.join(folder, 'output.log')
    if not os.path.exists(main_path):
        return None, f"{main_file} not found"
    open(log_file, 'w').close()
    py = sys.executable
    ts = lambda: datetime.now().strftime('%I:%M:%S %p')
    def log(m):
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(m + '\n'); f.flush()
        except Exception: pass
    log(f"[{ts()}] Starting bot...")
    log("")
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUNBUFFERED'] = '1'
    env['TERM'] = 'xterm'
    try:
        proc = subprocess.Popen(
            [py, os.path.abspath(main_path)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            cwd=folder, text=True, encoding='utf-8',
            errors='replace', bufsize=1, env=env,
            start_new_session=True
        )
        log(f"[{ts()}] Server started (PID: {proc.pid})")
        def stream():
            try:
                with open(log_file, 'a', encoding='utf-8') as f:
                    while True:
                        line = proc.stdout.readline()
                        if not line and proc.poll() is not None: break
                        if line:
                            f.write(f"[{datetime.now().strftime('%I:%M:%S %p')}] {line.rstrip()}\n")
                            f.flush()
            except Exception: pass
        threading.Thread(target=stream, daemon=True).start()
        def monitor():
            proc.wait(); time.sleep(2)
            cur = get_server(server_id) or {}
            if cur.get('stopped_by_user') or cur.get('rate_limit_exceeded'): return
            if cur.get('auto_batch'): return
            new_pid, err = run_bot_server(server_id)
            if new_pid:
                update_server(server_id, {
                    'status': 'running', 'pid': new_pid,
                    'started_at': str(datetime.now())
                })
        threading.Thread(target=monitor, daemon=True).start()
        return proc.pid, None
    except Exception as e:
        log(f"[{ts()}] Error: {e}")
        return None, str(e)

# ============================================
# OPTIONAL BATCH ROTATOR
# ============================================
class BatchRotator:
    def __init__(self):
        self.thread = None
        self.stop_flag = False
        self.enabled = False
        self.accounts = []
        self.current_index = 0
        self.lock = threading.Lock()
        self.batch_started_at = None

    def is_enabled(self):
        return self.enabled

    def toggle(self, on: bool):
        self.enabled = bool(on)
        if self.enabled:
            self.stop_flag = False
            self._load_state()
            if not self.thread or not self.thread.is_alive():
                self.thread = threading.Thread(target=self._loop, daemon=True)
                self.thread.start()
            print("[rotator] ▶ Enabled")
        else:
            self.stop_flag = True
            print("[rotator] ⏸ Disabled")
        self._save_state()
        return self.enabled

    def _load_state(self):
        if os.path.exists(ROTATION_FILE):
            try:
                with open(ROTATION_FILE) as f:
                    st = json.load(f)
                    self.current_index = st.get('index', 0)
                    self.batch_started_at = st.get('batch_started_at')
                    self.enabled = st.get('enabled', False)
            except Exception: pass

    def _save_state(self):
        try:
            with open(ROTATION_FILE, 'w') as f:
                json.dump({
                    'enabled': self.enabled,
                    'index': self.current_index,
                    'total': len(self.accounts),
                    'batch_started_at': self.batch_started_at
                }, f)
        except Exception: pass

    def reload_accounts(self):
        try:
            if not os.path.exists(ACCOUNTS_FILE):
                with self.lock:
                    self.accounts = []
                return 0
            with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            with self.lock:
                self.accounts = [a for a in data if a.get('uid') and a.get('password')]
            return len(self.accounts)
        except Exception as e:
            print(f"[rotator] load error: {e}")
            return 0

    def _stop_all_auto(self):
        d = load_servers()
        for s in d['servers']:
            if s.get('auto_batch'):
                if s.get('pid'): kill_pid(s['pid'])
                s['status'] = 'stopped'
                s['pid'] = None
                s['stopped_by_user'] = True
        save_servers(d)

    def _run_batch(self):
        with self.lock:
            if not self.accounts: return False
            batch = []
            for _ in range(BATCH_SIZE):
                if self.current_index >= len(self.accounts):
                    self.current_index = 0
                    print("[rotator] ♻️  Cycle restart")
                batch.append(self.accounts[self.current_index])
                self.current_index += 1
            self.batch_started_at = datetime.now().isoformat()
            self._save_state()

        print(f"\n[rotator] 🚀 Batch {self.current_index - BATCH_SIZE + 1}-{self.current_index}")
        self._stop_all_auto()
        time.sleep(3)

        for acc in batch:
            try:
                name = f"Auto-{str(acc['uid'])[-4:]}"
                sid = f"server_{uuid.uuid4().hex[:6]}"
                create_server_dir(sid)
                base = os.path.join(SERVERS_DIR, sid)
                with open(os.path.join(base, 'accounts.json'), 'w', encoding='utf-8') as f:
                    json.dump([{'uid': acc['uid'], 'password': acc['password']}],
                              f, indent=2, ensure_ascii=False)
                d = load_servers()
                d['servers'].append({
                    'id': sid, 'name': name, 'folder': sid,
                    'status': 'stopped', 'pid': None, 'started_at': None,
                    'main_file': 'main.py', 'requirements_file': 'requirements.txt',
                    'cpu_limit': 90, 'stopped_by_user': False,
                    'rate_limit_exceeded': False, 'auto_batch': True,
                    'created_at': str(datetime.now())
                })
                save_servers(d)
                pid, err = run_bot_server(sid)
                if pid:
                    update_server(sid, {'status': 'running', 'pid': pid,
                                        'started_at': str(datetime.now())})
                    print(f"[rotator]   ✅ {name} started")
                time.sleep(2)
            except Exception as e:
                print(f"[rotator]   ❌ {e}")
        print(f"[rotator] ✅ Batch running\n")
        return True

    def _loop(self):
        while not self.stop_flag and self.enabled:
            with self.lock:
                if not self.accounts:
                    self.reload_accounts()
                    if not self.accounts:
                        time.sleep(30); continue
            self._run_batch()
            end_time = time.time() + BATCH_DURATION
            while time.time() < end_time and not self.stop_flag and self.enabled:
                time.sleep(60)

rotator = BatchRotator()

# ============================================
# BASE CSS
# ============================================
BASE_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0a0e14;color:#e6edf3;font-family:'Segoe UI',system-ui,sans-serif;
     margin:0;padding:20px;font-size:14px;line-height:1.5;min-height:100vh}
a{color:#58a6ff;text-decoration:none}
h1{color:#58a6ff;margin:0 0 18px;font-size:24px;font-weight:700}
h3{color:#58a6ff;margin:0 0 10px;font-size:16px}
.btn{background:linear-gradient(135deg,#238636,#2ea043);color:#fff;padding:9px 18px;
     border:none;border-radius:8px;font-weight:600;cursor:pointer;font-size:13px;
     display:inline-flex;align-items:center;gap:6px;font-family:inherit;transition:.15s}
.btn:hover{transform:translateY(-1px)}
.btn.red{background:linear-gradient(135deg,#da3633,#f85149)}
.btn.gray{background:#21262d;color:#e6edf3}
.btn.blue{background:linear-gradient(135deg,#1f6feb,#388bfd)}
.btn.small{padding:5px 10px;font-size:11px}
input,textarea,select{width:100%;padding:10px 12px;background:#0d1117;border:1px solid #30363d;
     color:#e6edf3;border-radius:8px;margin:6px 0;font-family:inherit;font-size:13px}
input:focus,textarea:focus{outline:none;border-color:#58a6ff}
textarea{font-family:'Consolas',monospace;resize:vertical;min-height:80px}
.topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;
        flex-wrap:wrap;gap:12px;padding-bottom:16px;border-bottom:1px solid #21262d}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}
.card{background:linear-gradient(180deg,#161b22,#0d1117);border:1px solid #30363d;
      border-radius:14px;padding:18px;transition:.2s}
.card:hover{border-color:#58a6ff}
.stat{display:flex;justify-content:space-between;padding:5px 0;font-size:13px;
      border-bottom:1px solid #21262d}
.stat:last-child{border-bottom:none}
.stat span:first-child{color:#8b949e;font-weight:500}
.stat span:last-child{font-weight:600}
.badge{padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;
       letter-spacing:.3px;text-transform:uppercase}
.badge.run{background:rgba(63,185,80,.15);color:#3fb950;border:1px solid rgba(63,185,80,.3)}
.badge.stop{background:rgba(248,81,73,.15);color:#f85149;border:1px solid rgba(248,81,73,.3)}
.row{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;align-items:center}
pre{background:#010409;color:#c9d1d9;padding:16px;border-radius:10px;
    max-height:540px;overflow:auto;font-size:12.5px;line-height:1.6;
    border:1px solid #21262d;white-space:pre-wrap;word-break:break-word;
    font-family:'Consolas',monospace;margin:0}
.modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.8);
       align-items:center;justify-content:center;z-index:100;padding:16px}
.modal.on{display:flex}
.modal-box{background:linear-gradient(180deg,#161b22,#0d1117);padding:26px;
           border-radius:14px;width:480px;max-width:96%;max-height:90vh;
           overflow:auto;border:1px solid #30363d}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:16px 0}
.metric{background:linear-gradient(180deg,#161b22,#0d1117);border:1px solid #30363d;
        border-radius:12px;padding:14px}
.metric .lbl{color:#8b949e;font-size:11px;text-transform:uppercase;
             letter-spacing:.6px;font-weight:600}
.metric .val{font-size:19px;font-weight:700;margin-top:6px}
.err{color:#f85149;margin:10px 0;padding:10px 14px;background:rgba(248,81,73,.1);
     border:1px solid rgba(248,81,73,.3);border-radius:8px;font-size:13px}
.ok{color:#3fb950;margin:10px 0;padding:10px 14px;background:rgba(63,185,80,.1);
    border:1px solid rgba(63,185,80,.3);border-radius:8px;font-size:13px}
.tabs{display:flex;gap:4px;border-bottom:1px solid #21262d;margin-bottom:18px;flex-wrap:wrap}
.tab{padding:10px 18px;cursor:pointer;border-bottom:2px solid transparent;
     color:#8b949e;font-weight:600;font-size:13px}
.tab.active{color:#58a6ff;border-bottom-color:#58a6ff}
.file-row{display:grid;grid-template-columns:1fr auto auto;align-items:center;
          padding:10px 14px;border-bottom:1px solid #21262d;font-size:13px;gap:12px}
.acc-row{display:grid;grid-template-columns:1fr 2fr auto 30px;gap:10px;
         margin:8px 0;align-items:center}
.acc-row input{margin:0}
.drop{border:2px dashed #30363d;border-radius:12px;padding:30px;text-align:center;
      color:#8b949e;cursor:pointer;transition:.2s;background:#0d1117;margin:10px 0}
.drop:hover{border-color:#58a6ff;background:rgba(88,166,255,.05);color:#58a6ff}
.login-box{max-width:420px;margin:80px auto;
           background:linear-gradient(180deg,#161b22,#0d1117);
           padding:36px;border-radius:16px;border:1px solid #30363d}
.login-box h1{text-align:center;font-size:26px;margin-bottom:24px}
.muted{color:#8b949e;font-size:12px}
.switch{position:relative;display:inline-block;width:60px;height:32px;vertical-align:middle}
.switch input{display:none}
.slider{position:absolute;cursor:pointer;inset:0;background:#30363d;
        transition:.3s;border-radius:32px}
.slider:before{position:absolute;content:"";height:24px;width:24px;left:4px;bottom:4px;
               background:#8b949e;transition:.3s;border-radius:50%}
input:checked+.slider{background:#238636}
input:checked+.slider:before{transform:translateX(28px);background:#fff}
.progress-bar{width:100%;height:10px;background:#21262d;border-radius:5px;
              overflow:hidden;margin-top:6px}
.progress-fill{height:100%;background:linear-gradient(90deg,#58a6ff,#3fb950);
               transition:width .3s}
"""

# ============================================
# HTML TEMPLATES
# ============================================
LOGIN_HTML = """
<!DOCTYPE html><html><head><title>Login — JUBAYER HOSTING</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>""" + BASE_CSS + """</style></head><body>
<div class="login-box">
<h1>🚀 JUBAYER HOSTING</h1>
{% if error %}<div class="err">{{ error }}</div>{% endif %}
<form method="POST">
  <input name="username" placeholder="👤 Username" required autofocus>
  <input name="password" type="password" placeholder="🔒 Password" required>
  <button class="btn" style="width:100%;margin-top:12px;padding:13px;justify-content:center">Login</button>
</form>
</div></body></html>
"""

DASH_HTML = """
<!DOCTYPE html><html><head><title>Dashboard</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>""" + BASE_CSS + """</style></head><body>
<div class="topbar">
  <h1>🚀 JUBAYER HOSTING</h1>
  <div class="row" style="margin:0">
    <span class="muted">👤 {{ username }}</span>
    <a class="btn gray" href="{{ url_for('templates_page') }}">🧩 Templates</a>
    <a class="btn gray" href="{{ url_for('profile') }}">⚙ Profile</a>
    <button class="btn red" onclick="allClean()">🧹 All Clean</button>
    <a class="btn red" href="{{ url_for('logout') }}">Logout</a>
  </div>
</div>

<div class="card" style="margin-bottom:20px">
  <h3>🔄 Auto Batch Rotation (Optional)</h3>
  <div class="row" style="margin-top:12px;align-items:center">
    <label class="switch">
      <input type="checkbox" id="autoToggle" {% if auto_enabled %}checked{% endif %}
             onchange="toggleAuto(this.checked)">
      <span class="slider"></span>
    </label>
    <span style="margin-left:8px" id="autoStatus">
      {% if auto_enabled %}✅ Enabled — auto rotation running{% else %}⏸ Disabled — manual mode{% endif %}
    </span>
  </div>
  <div class="stat"><span>Batch Size</span><span>{{ batch_size }} servers</span></div>
  <div class="stat"><span>Duration</span><span>{{ batch_hours }} hours</span></div>
  <div class="stat"><span>Accounts Pool</span><span>{{ accounts_count }}</span></div>
  <div class="stat"><span>Current Index</span><span>{{ current_index }}</span></div>
  <p class="muted" style="margin-top:10px">OFF rakho → sab manual. ON karo → {{ batch_hours }}-hour auto rotation.</p>
</div>

<div class="row">
  <button class="btn" onclick="document.getElementById('cm').classList.add('on')">
    ➕ Create Server ({{ servers|length }}/{{ max_servers }})
  </button>
</div>

<div class="grid" style="margin-top:16px">
  {% for s in servers %}
  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
      <h3 style="margin:0;font-size:17px">{{ s.name }}</h3>
      <span class="badge {{ 'run' if s.status=='running' else 'stop' }}">{{ s.status }}</span>
    </div>
    <div class="stat"><span>Nickname</span><span>{{ s.nickname }}</span></div>
    <div class="stat"><span>Level</span><span>Lvl {{ s.level }}</span></div>
    <div class="stat"><span>Exp</span>
      <span style="color:#3fb950">+{{ s.exp_in_level }} / {{ s.exp_for_next }}</span>
    </div>
    <div class="stat"><span>Progress</span><span style="color:#58a6ff">{{ s.percent }}%</span></div>
    <div class="progress-bar"><div class="progress-fill" style="width:{{ s.percent }}%"></div></div>
    {% if s.auto_batch %}<div class="stat" style="margin-top:8px"><span>Type</span><span style="color:#f0b400">AUTO</span></div>{% endif %}
    <div class="row" style="margin-top:14px">
      <a class="btn" href="{{ url_for('server_page', sid=s.id) }}">📂 Open</a>
      {% if s.status=='running' %}
      <button class="btn red small" onclick="srvAction('{{ s.id }}','stop')">■ Stop</button>
      {% else %}
      <button class="btn small" onclick="srvAction('{{ s.id }}','run')">▶ Run</button>
      {% endif %}
      <button class="btn gray small" onclick="delSrv('{{ s.id }}','{{ s.name }}')">🗑</button>
    </div>
  </div>
  {% endfor %}
  {% if not servers %}
  <div class="card" style="grid-column:1/-1;text-align:center;padding:50px">
    <div style="font-size:48px">📦</div>
    <h3 style="color:#8b949e;font-weight:400">Koi server nahi</h3>
  </div>
  {% endif %}
</div>

<div class="modal" id="cm"><div class="modal-box">
  <h3>➕ Create New Server</h3>
  <input id="sname" placeholder="Server name" autofocus>
  <div class="row" style="margin-top:16px">
    <button class="btn" onclick="createSrv()">✓ Create</button>
    <button class="btn gray" onclick="document.getElementById('cm').classList.remove('on')">Cancel</button>
  </div>
</div></div>

<script>
async function toggleAuto(on){
  const r = await fetch('/api/rotation/toggle', {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify({on})});
  const j = await r.json();
  document.getElementById('autoStatus').textContent = j.enabled ?
    '✅ Enabled — auto rotation running' : '⏸ Disabled — manual mode';
}
async function createSrv(){
  const name = document.getElementById('sname').value.trim() || 'Server';
  const r = await fetch('/api/servers/create', {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify({name})});
  const j = await r.json();
  if (j.success) location.reload(); else alert(j.error||'Failed');
}
async function delSrv(id,name){
  if(!confirm('Delete "'+name+'" ?')) return;
  const r = await fetch('/api/servers/delete', {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify({id})});
  const j = await r.json();
  if (j.success) location.reload(); else alert(j.error);
}
async function srvAction(id,action){
  await fetch('/api/server/'+id+'/'+action, {method:'POST'});
  location.reload();
}
async function allClean(){
  if(!confirm('⚠️⚠️⚠️ ALL CLEAN — FULL RESET ⚠️⚠️⚠️\\n\\nYe SAB kuch delete karega:\\n• Saare servers (running bots bhi)\\n• accounts.json\\n• templates_bot ke saare files\\n• Auto rotation OFF\\n• Rotation state reset\\n\\n✅ Login (username/password) SAFE rahega\\n✅ level_exp.json SAFE rahega\\n\\nPakka karna hai?')) return;
  if(!confirm('🚨 FINAL CONFIRM 🚨\\n\\nSab kuch permanently delete ho jayega.\\nWapas nahi aa sakta!\\n\\nLast chance — Confirm karo?')) return;
  try{
    const r = await fetch('/api/all-clean', {method:'POST'});
    const j = await r.json();
    if(j.success){
      alert('✅ ALL CLEAN SUCCESS!\\n\\n' +
            '🗑 Servers deleted: ' + j.deleted_servers + '\\n' +
            '🧩 Templates cleared\\n' +
            '📋 Accounts pool cleared\\n' +
            '🔄 Auto rotation OFF\\n\\n' +
            'System ab fresh new jaisa hai 🎉');
      location.reload();
    } else {
      alert('❌ Error: ' + (j.error||'Failed'));
    }
  }catch(e){ alert('❌ Network error: ' + e); }
}
setTimeout(()=>location.reload(), 20000);
</script></body></html>
"""

SERVER_HTML = """
<!DOCTYPE html><html><head><title>{{ server.name }}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>""" + BASE_CSS + """</style></head><body>
<a href="{{ url_for('dashboard') }}">← Back</a>
<h1 style="margin-top:12px">{{ server.name }} <span id="badge" class="badge stop">…</span></h1>

<div class="row">
  <button class="btn" onclick="runSrv()">▶ Run</button>
  <button class="btn red" onclick="stopSrv()">■ Stop</button>
  <button class="btn gray" onclick="clearLogs()">🧹 Clear Logs</button>
  <button class="btn blue" onclick="downloadServer()">⬇ Download</button>
</div>

<div class="metrics">
  <div class="metric"><div class="lbl">CPU</div><div class="val" id="cpu">0%</div></div>
  <div class="metric"><div class="lbl">RAM</div><div class="val" id="ram">0 MB</div></div>
  <div class="metric"><div class="lbl">Net In</div><div class="val" id="nin">0 KB</div></div>
  <div class="metric"><div class="lbl">Net Out</div><div class="val" id="nout">0 KB</div></div>
  <div class="metric"><div class="lbl">Uptime</div><div class="val" id="uptime">—</div></div>
  <div class="metric"><div class="lbl">Nickname</div><div class="val" id="nick">—</div></div>
  <div class="metric"><div class="lbl">Level</div><div class="val" id="lvl">Lvl 0</div></div>
  <div class="metric"><div class="lbl">Exp (current/next)</div>
    <div class="val" id="exp" style="color:#3fb950">+0 / 0</div></div>
  <div class="metric"><div class="lbl">Next Level Need</div>
    <div class="val" id="expNext" style="color:#f0b400">+0</div></div>
  <div class="metric"><div class="lbl">Progress</div>
    <div class="val" id="progress" style="color:#58a6ff">0%</div></div>
</div>

<div class="progress-bar" style="margin-bottom:16px">
  <div class="progress-fill" id="progressBar" style="width:0%"></div>
</div>

<div class="tabs">
  <div class="tab active" data-t="logs" onclick="tab('logs')">📜 Logs</div>
  <div class="tab" data-t="files" onclick="tab('files')">📁 Files</div>
  <div class="tab" data-t="accounts" onclick="tab('accounts')">👤 Accounts</div>
  <div class="tab" data-t="startup" onclick="tab('startup')">⚙ Startup</div>
</div>

<div id="tab-logs"><pre id="logs">Loading…</pre></div>

<div id="tab-files" style="display:none">
  <div class="drop" id="drop" onclick="document.getElementById('finput').click()">
    📤 Files upload karo
    <input type="file" id="finput" multiple style="display:none" onchange="doUpload(this.files)">
  </div>
  <div id="fileList" style="margin-top:12px">Loading…</div>
</div>

<div id="tab-accounts" style="display:none">
  <p class="muted">accounts.json edit karo</p>
  <div id="accList"></div>
  <div class="row" style="margin-top:14px">
    <button class="btn" onclick="addAcc()">➕ Add</button>
    <button class="btn blue" onclick="saveAcc()">💾 Save</button>
  </div>
  <div id="accMsg"></div>
</div>

<div id="tab-startup" style="display:none">
  <label class="muted">Main File</label>
  <input id="mainFile" placeholder="main.py">
  <label class="muted">Requirements File</label>
  <input id="reqFile" placeholder="requirements.txt">
  <button class="btn" style="margin-top:12px" onclick="saveStartup()">💾 Save</button>
  <div id="startMsg"></div>
</div>

<script>
const SID = "{{ server.id }}";
function tab(name){
  document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active', t.dataset.t===name));
  ['logs','files','accounts','startup'].forEach(n=>{
    document.getElementById('tab-'+n).style.display = (n===name?'block':'none');
  });
  if (name==='files') loadFiles();
  if (name==='accounts') loadAccounts();
  if (name==='startup') loadStartup();
}
async function stats(){
  try{
    const j = await (await fetch(`/api/server/${SID}/stats`)).json();
    cpu.textContent=j.cpu; ram.textContent=j.ram;
    nin.textContent=j.net_in; nout.textContent=j.net_out;
    uptime.textContent=j.uptime; nick.textContent=j.nickname;
    lvl.textContent='Lvl '+j.level;
    exp.textContent = '+' + (j.exp_in_level||0) + ' / ' + (j.exp_for_next||0);
    document.getElementById('expNext').textContent = '+' + (j.exp_for_next||0);
    document.getElementById('progress').textContent = (j.percent||0) + '%';
    document.getElementById('progressBar').style.width = (j.percent||0) + '%';
    const b=document.getElementById('badge');
    b.textContent=j.status;
    b.className='badge '+(j.status==='running'?'run':'stop');
  }catch(e){}
}
async function logs(){
  try{
    const j = await (await fetch(`/api/server/${SID}/logs`)).json();
    const el=document.getElementById('logs');
    const bottom=el.scrollTop+el.clientHeight>=el.scrollHeight-40;
    el.textContent=j.logs||'(empty)';
    if(bottom) el.scrollTop=el.scrollHeight;
  }catch(e){}
}
async function runSrv(){ await fetch(`/api/server/${SID}/run`,{method:'POST'}); stats(); }
async function stopSrv(){ await fetch(`/api/server/${SID}/stop`,{method:'POST'}); stats(); }
async function clearLogs(){ if(!confirm('Clear?'))return; await fetch(`/api/server/${SID}/clear_logs`,{method:'POST'}); logs(); }
function downloadServer(){ window.location = `/api/server/${SID}/download`; }
async function loadFiles(){
  const j = await (await fetch(`/api/server/${SID}/files`)).json();
  let html='';
  (j.files||[]).forEach(f=>{
    html+=`<div class="file-row">
      <span>${f.is_dir?'📁':'📄'} <a href="#" onclick="editFile('${f.name}');return false">${f.name}</a></span>
      <span class="muted">${(f.size/1024).toFixed(1)} KB</span>
      <span><button class="btn red small" onclick="delFile('${f.name}')">Del</button></span>
    </div>`;
  });
  if (!html) html='<div class="muted">(empty)</div>';
  document.getElementById('fileList').innerHTML=html;
}
async function doUpload(files){
  const fd=new FormData();
  for(const f of files) fd.append('files', f);
  await fetch(`/api/server/${SID}/upload`, {method:'POST', body:fd});
  loadFiles();
}
async function delFile(name){
  if(!confirm('Delete '+name+'?'))return;
  await fetch(`/api/server/${SID}/file`, {method:'DELETE',
    headers:{'Content-Type':'application/json'}, body:JSON.stringify({filename:name})});
  loadFiles();
}
async function editFile(name){
  const j = await (await fetch(`/api/server/${SID}/file?filename=${encodeURIComponent(name)}`)).json();
  const modal=document.createElement('div');
  modal.className='modal on';
  modal.innerHTML=`<div class="modal-box" style="width:760px">
    <h3>📝 ${name}</h3>
    <textarea id="ed" style="height:440px">${(j.content||'').replace(/</g,'&lt;')}</textarea>
    <div class="row" style="margin-top:14px">
      <button class="btn" id="sv">💾 Save</button>
      <button class="btn gray" id="cl">Close</button>
    </div></div>`;
  document.body.appendChild(modal);
  modal.querySelector('#sv').onclick=async()=>{
    await fetch(`/api/server/${SID}/file`, {method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({filename:name, content:modal.querySelector('#ed').value})});
    modal.remove(); loadFiles();
  };
  modal.querySelector('#cl').onclick=()=>modal.remove();
}
let accData=[];
async function loadAccounts(){
  const j = await (await fetch(`/api/server/${SID}/accounts`)).json();
  accData=j.accounts||[];
  renderAcc();
}
function renderAcc(){
  const box=document.getElementById('accList');
  if(!accData.length){box.innerHTML='<div class="muted">No accounts</div>';return;}
  box.innerHTML=accData.map((a,i)=>`
    <div class="acc-row">
      <input value="${a.uid||''}" oninput="accData[${i}].uid=this.value" placeholder="UID">
      <input value="${a.password||''}" oninput="accData[${i}].password=this.value" placeholder="Password">
      <button class="btn red small" onclick="delAcc(${i})">🗑</button>
      <span class="muted">#${i+1}</span>
    </div>`).join('');
}
function addAcc(){accData.push({uid:'',password:''});renderAcc();}
function delAcc(i){accData.splice(i,1);renderAcc();}
async function saveAcc(){
  await fetch(`/api/server/${SID}/accounts`, {method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({accounts:accData})});
  document.getElementById('accMsg').innerHTML='<div class="ok">✅ Saved</div>';
}
async function loadStartup(){
  const j = await (await fetch(`/api/server/${SID}/startup`)).json();
  document.getElementById('mainFile').value=j.main_file||'main.py';
  document.getElementById('reqFile').value=j.requirements_file||'requirements.txt';
}
async function saveStartup(){
  await fetch(`/api/server/${SID}/startup`, {method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({
      main_file:document.getElementById('mainFile').value,
      requirements_file:document.getElementById('reqFile').value
    })});
  document.getElementById('startMsg').innerHTML='<div class="ok">✅ Saved</div>';
}
setInterval(stats, 2000); setInterval(logs, 2000);
stats(); logs();
</script></body></html>
"""

TEMPLATES_HTML = """
<!DOCTYPE html><html><head><title>Templates</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>""" + BASE_CSS + """</style></head><body>
<a href="{{ url_for('dashboard') }}">← Back</a>
<h1 style="margin-top:12px">🧩 Templates & Accounts</h1>

<div class="card" style="margin-bottom:20px">
  <h3>📋 Accounts JSON (Root Pool)</h3>
  <p class="muted">Ye file manual + auto rotation dono ke liye source hai.</p>

  <div id="accStatus" style="margin:10px 0;padding:12px;background:#0d1117;
       border-radius:8px;border:1px solid #30363d">
    {% if accounts_count %}
      <span style="color:#3fb950">✅ {{ accounts_count }} accounts loaded</span>
    {% else %}
      <span style="color:#8b949e">⚠️ No accounts.json found</span>
    {% endif %}
  </div>

  <div class="row">
    <button class="btn blue" onclick="document.getElementById('accFile').click()">
      📤 Upload / Replace accounts.json
    </button>
    <button class="btn gray" onclick="downloadAccounts()">⬇ Download</button>
    <button class="btn red" onclick="deleteAccounts()">🗑 Delete accounts.json</button>
    <input type="file" id="accFile" accept=".json" style="display:none"
           onchange="uploadAccounts(this.files[0])">
  </div>
  <div id="accMsg" style="margin-top:10px"></div>
</div>

<div class="card">
  <h3>🧩 Template Files</h3>
  <div class="drop" onclick="document.getElementById('finput').click()">
    📤 Files upload karo (templates_bot/)
    <input type="file" id="finput" multiple style="display:none" onchange="doUpload(this.files)">
  </div>
  <div class="row">
    <button class="btn" onclick="newFile()">➕ New File</button>
    <button class="btn gray" onclick="document.getElementById('zipin').click()">📦 Upload .zip</button>
    <input type="file" id="zipin" accept=".zip" style="display:none" onchange="uploadZip(this.files[0])">
  </div>
  <div id="fileList" style="margin-top:12px">Loading…</div>
</div>

<script>
async function uploadAccounts(file){
  if(!file) return;
  const fd = new FormData(); fd.append('file', file);
  const r = await fetch('/api/templates/upload_accounts', {method:'POST', body:fd});
  const j = await r.json();
  const msg = document.getElementById('accMsg');
  if(j.success){
    msg.innerHTML = `<div class="ok">✅ Replaced! ${j.count} accounts loaded</div>`;
    document.getElementById('accStatus').innerHTML =
      `<span style="color:#3fb950">✅ ${j.count} accounts loaded</span>`;
    setTimeout(()=>location.reload(), 1200);
  } else {
    msg.innerHTML = `<div class="err">❌ ${j.error||'Failed'}</div>`;
  }
}
async function deleteAccounts(){
  if(!confirm('⚠️ accounts.json delete karna hai?\\n\\nIsse rotation pool khaali ho jayega aur auto rotation OFF ho jayega.')) return;
  const r = await fetch('/api/templates/accounts', {method:'DELETE'});
  const j = await r.json();
  const msg = document.getElementById('accMsg');
  if(j.success){
    msg.innerHTML = `<div class="ok">🗑 accounts.json deleted + pool cleared</div>`;
    document.getElementById('accStatus').innerHTML =
      `<span style="color:#8b949e">⚠️ No accounts.json found</span>`;
    setTimeout(()=>location.reload(), 1200);
  } else {
    msg.innerHTML = `<div class="err">❌ ${j.error||'Failed'}</div>`;
  }
}
function downloadAccounts(){
  window.location = '/api/templates/accounts/download';
}
async function loadFiles(){
  const j=await (await fetch('/api/templates/files')).json();
  let html='';
  (j.files||[]).forEach(f=>{
    const icon=f.is_dir?'📁':(f.name.endsWith('.py')?'🐍':'📄');
    html+=`<div class="file-row">
      <span>${icon} <a href="#" onclick="editFile('${f.name}');return false">${f.name}</a></span>
      <span class="muted">${(f.size/1024).toFixed(1)} KB</span>
      <span><button class="btn red small" onclick="delFile('${f.name}')">Del</button></span>
    </div>`;
  });
  if(!html)html='<div class="muted">(empty)</div>';
  document.getElementById('fileList').innerHTML=html;
}
async function doUpload(files){
  const fd=new FormData();
  for(const f of files) fd.append('files',f);
  await fetch('/api/templates/upload',{method:'POST',body:fd});
  loadFiles();
}
async function uploadZip(file){
  if(!file)return;
  const fd=new FormData(); fd.append('file',file);
  await fetch('/api/templates/upload_zip',{method:'POST',body:fd});
  loadFiles();
}
async function delFile(name){
  if(!confirm('Delete?'))return;
  await fetch('/api/templates/file',{method:'DELETE',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:name})});
  loadFiles();
}
async function newFile(){
  const name=prompt('File name:');
  if(!name)return;
  await fetch('/api/templates/file',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({filename:name,content:''})});
  loadFiles();
}
async function editFile(name){
  const j=await (await fetch(`/api/templates/file?filename=${encodeURIComponent(name)}`)).json();
  const modal=document.createElement('div');
  modal.className='modal on';
  modal.innerHTML=`<div class="modal-box" style="width:760px">
    <h3>📝 ${name}</h3>
    <textarea id="ed" style="height:440px">${(j.content||'').replace(/</g,'&lt;')}</textarea>
    <div class="row" style="margin-top:14px">
      <button class="btn" id="sv">💾 Save</button>
      <button class="btn gray" id="cl">Close</button>
    </div></div>`;
  document.body.appendChild(modal);
  modal.querySelector('#sv').onclick=async()=>{
    await fetch('/api/templates/file',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({filename:name,content:modal.querySelector('#ed').value})});
    modal.remove(); loadFiles();
  };
  modal.querySelector('#cl').onclick=()=>modal.remove();
}
loadFiles();
</script></body></html>
"""

PROFILE_HTML = """
<!DOCTYPE html><html><head><title>Profile</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>""" + BASE_CSS + """</style></head><body>
<a href="{{ url_for('dashboard') }}">← Back</a>
<h1 style="margin-top:12px">👤 Profile</h1>
{% if error %}<div class="err">{{ error }}</div>{% endif %}
{% if success %}<div class="ok">{{ success }}</div>{% endif %}
<form method="POST" style="max-width:420px">
  <label class="muted">Username</label>
  <input name="new_username" value="{{ current_username }}">
  <label class="muted">Current Password *</label>
  <input name="current_password" type="password" required>
  <label class="muted">New Password</label>
  <input name="new_password" type="password">
  <button class="btn" style="width:100%;margin-top:14px;justify-content:center">💾 Save</button>
</form>
</body></html>
"""

# ============================================
# PAGE ROUTES
# ============================================
@app.route('/')
def index():
    return redirect(url_for('dashboard') if 'logged_in' in session else url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        u = request.form.get('username','').strip()
        p = request.form.get('password','').strip()
        if verify_master_login(u,p):
            session.update(logged_in=True, user_type='master', username=u)
            return redirect(url_for('dashboard'))
        if verify_user_login(u,p):
            session.update(logged_in=True, user_type='user', username=u)
            return redirect(url_for('dashboard'))
        return render_template_string(LOGIN_HTML, error="Invalid!")
    return render_template_string(LOGIN_HTML, error=None)

@app.route('/logout')
def logout():
    session.clear(); return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    out = []
    for s in load_servers()['servers']:
        folder = os.path.join(SERVERS_DIR, s['folder'])
        st = parse_stats_from_log(folder)
        s2 = dict(s)
        s2['nickname']     = st['nickname']
        s2['level']        = st['level']
        s2['exp_total']    = st['exp_total']
        s2['exp_in_level'] = st['exp_in_level']
        s2['exp_for_next'] = st['exp_for_next']
        s2['percent']      = st['percent']
        out.append(s2)
    return render_template_string(DASH_HTML,
        username=session.get('username'),
        servers=out, max_servers=MAX_SERVERS,
        auto_enabled=rotator.is_enabled(),
        batch_size=BATCH_SIZE, batch_hours=BATCH_DURATION//3600,
        accounts_count=len(rotator.accounts),
        current_index=rotator.current_index)

@app.route('/server/<sid>')
@login_required
def server_page(sid):
    s = get_server(sid)
    if not s: return redirect(url_for('dashboard'))
    return render_template_string(SERVER_HTML, server=s)

@app.route('/templates')
@login_required
def templates_page():
    return render_template_string(TEMPLATES_HTML,
        accounts_count=len(rotator.accounts))

@app.route('/profile', methods=['GET','POST'])
@login_required
def profile():
    if request.method == 'POST':
        cur   = request.form.get('current_password','')
        new_p = request.form.get('new_password','')
        new_u = request.form.get('new_username','').strip()
        cfg = load_config()
        if hashlib.sha256(cur.encode()).hexdigest() != cfg.get('password_hash'):
            return render_template_string(PROFILE_HTML, error="Wrong password",
                success=None, current_username=cfg.get('username'))
        if new_u and new_u != cfg.get('username'):
            cfg['username'] = new_u; session['username'] = new_u
        if new_p:
            cfg['password_hash'] = hashlib.sha256(new_p.encode()).hexdigest()
        save_config(cfg)
        return render_template_string(PROFILE_HTML, error=None,
            success="Updated!", current_username=cfg.get('username'))
    cfg = load_config()
    return render_template_string(PROFILE_HTML, error=None, success=None,
        current_username=cfg.get('username'))

# ============================================
# API — SERVERS
# ============================================
@app.route('/api/servers/create', methods=['POST'])
@login_required
def api_create_server():
    d = load_servers()
    if len(d['servers']) >= MAX_SERVERS:
        return jsonify({'error': f'Max {MAX_SERVERS} servers!'}), 400
    name = (request.json.get('name') or 'Server').strip()[:30]
    sid = f"server_{uuid.uuid4().hex[:6]}"
    create_server_dir(sid)
    d['servers'].append({
        'id': sid, 'name': name, 'folder': sid,
        'status': 'stopped', 'pid': None, 'started_at': None,
        'main_file': 'main.py', 'requirements_file': 'requirements.txt',
        'cpu_limit': 90, 'stopped_by_user': False,
        'rate_limit_exceeded': False, 'auto_batch': False,
        'created_at': str(datetime.now())
    })
    save_servers(d)
    return jsonify({'success': True, 'id': sid})

@app.route('/api/servers/delete', methods=['POST'])
@login_required
def api_delete_server():
    sid = request.json.get('id')
    s = get_server(sid)
    if not s: return jsonify({'error': 'Not found'}), 404
    if s.get('pid'): kill_pid(s['pid'])
    shutil.rmtree(os.path.join(SERVERS_DIR, s['folder']), ignore_errors=True)
    d = load_servers()
    d['servers'] = [x for x in d['servers'] if x['id'] != sid]
    save_servers(d)
    return jsonify({'success': True})

# ============================================
# API — RUN / STOP / LOGS / STATS
# ============================================
@app.route('/api/server/<sid>/run', methods=['POST'])
@login_required
def api_run(sid):
    s = get_server(sid)
    if not s: return jsonify({'error': 'Not found'}), 404
    if s.get('status') == 'running': return jsonify({'error': 'Already running'})
    update_server(sid, {'stopped_by_user': False, 'rate_limit_exceeded': False})
    pid, err = run_bot_server(sid)
    if pid:
        update_server(sid, {'status':'running','pid':pid,
                            'started_at': str(datetime.now())})
        return jsonify({'success': True})
    return jsonify({'error': err}), 500

@app.route('/api/server/<sid>/stop', methods=['POST'])
@login_required
def api_stop(sid):
    s = get_server(sid)
    if not s: return jsonify({'error': 'Not found'}), 404
    if s.get('pid'): kill_pid(s['pid'])
    update_server(sid, {'status':'stopped','pid':None,'stopped_by_user':True})
    return jsonify({'success': True})

@app.route('/api/server/<sid>/logs')
@login_required
def api_logs(sid):
    s = get_server(sid)
    if not s: return jsonify({'logs':''})
    lf = os.path.join(SERVERS_DIR, s['folder'], 'output.log')
    if os.path.exists(lf):
        with open(lf, 'r', encoding='utf-8', errors='ignore') as f:
            return jsonify({'logs': f.read()})
    return jsonify({'logs': ''})

@app.route('/api/server/<sid>/clear_logs', methods=['POST'])
@login_required
def api_clear_logs(sid):
    s = get_server(sid)
    if not s: return jsonify({'error':'Not found'}), 404
    try:
        open(os.path.join(SERVERS_DIR, s['folder'], 'output.log'), 'w').close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/server/<sid>/stats')
@login_required
def api_stats(sid):
    s = get_server(sid)
    if not s: return jsonify({'error':'Not found'}), 404
    folder = os.path.join(SERVERS_DIR, s['folder'])
    parsed = parse_stats_from_log(folder)
    cpu, ram, nin, nout, uptime = "0%", "0 MB", "0 KB", "0 KB", "—"
    try:
        import psutil
        if s.get('status')=='running' and s.get('pid'):
            p = psutil.Process(s['pid'])
            cpu = f"{p.cpu_percent(interval=0.3):.1f}%"
            mem = p.memory_info().rss / 1024 / 1024
            ram = f"{mem:.1f} MB" if mem < 1024 else f"{mem/1024:.2f} GB"
            io = p.io_counters()
            nin  = fmt_bytes(io.read_bytes); nout = fmt_bytes(io.write_bytes)
    except Exception: pass
    if s.get('status')=='running' and s.get('started_at'):
        try:
            st = datetime.strptime(s['started_at'], '%Y-%m-%d %H:%M:%S.%f')
            d = datetime.now() - st
            uptime = f"{d.days}d {d.seconds//3600}h {(d.seconds%3600)//60}m"
        except Exception: pass
    return jsonify({
        'status': s.get('status'),
        'cpu': cpu, 'ram': ram, 'net_in': nin, 'net_out': nout, 'uptime': uptime,
        'nickname': parsed['nickname'], 'level': parsed['level'],
        'exp_total': parsed['exp_total'], 'exp_gained': parsed['exp_gained'],
        'exp_for_next': parsed['exp_for_next'],
        'exp_in_level': parsed['exp_in_level'],
        'percent': parsed['percent'],
    })

def fmt_bytes(b):
    for u in ['B','KB','MB','GB','TB']:
        if b < 1024: return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.2f} PB"

# ============================================
# API — FILES / ACCOUNTS / STARTUP (per server)
# ============================================
@app.route('/api/server/<sid>/files')
@login_required
def api_files(sid):
    base = server_folder(sid)
    if not base: return jsonify({'files': []})
    out = []
    for it in sorted(os.listdir(base)):
        if it.startswith('.'): continue
        p = os.path.join(base, it)
        out.append({'name': it, 'is_dir': os.path.isdir(p),
                    'size': os.path.getsize(p) if os.path.isfile(p) else 0})
    return jsonify({'files': out})

@app.route('/api/server/<sid>/file', methods=['GET'])
@login_required
def api_get_file(sid):
    base = server_folder(sid)
    fp = safe_join(base, request.args.get('filename','')) if base else None
    if not fp or not os.path.isfile(fp): return jsonify({'error':'Not found'}), 404
    try:
        with open(fp, 'r', encoding='utf-8', errors='replace') as f:
            return jsonify({'content': f.read()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/server/<sid>/file', methods=['POST'])
@login_required
def api_save_file(sid):
    base = server_folder(sid)
    if not base: return jsonify({'error':'Not found'}), 404
    data = request.get_json() or {}
    fp = safe_join(base, data.get('filename',''))
    if not fp: return jsonify({'error':'Access denied'}), 403
    with open(fp, 'w', encoding='utf-8') as f:
        f.write(data.get('content',''))
    return jsonify({'success': True})

@app.route('/api/server/<sid>/file', methods=['DELETE'])
@login_required
def api_del_file(sid):
    base = server_folder(sid)
    if not base: return jsonify({'error':'Not found'}), 404
    data = request.get_json() or {}
    fp = safe_join(base, data.get('filename',''))
    if not fp: return jsonify({'error':'Access denied'}), 403
    try:
        if os.path.isdir(fp): shutil.rmtree(fp)
        elif os.path.isfile(fp): os.remove(fp)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/server/<sid>/upload', methods=['POST'])
@login_required
def api_upload(sid):
    base = server_folder(sid)
    if not base: return jsonify({'error':'Not found'}), 404
    files = request.files.getlist('files')
    up = []
    for f in files:
        if not f.filename: continue
        safe_name = os.path.basename(f.filename)
        f.save(os.path.join(base, safe_name)); up.append(safe_name)
    return jsonify({'success': True, 'uploaded': up})

@app.route('/api/server/<sid>/download')
@login_required
def api_download(sid):
    base = server_folder(sid)
    if not base or not os.path.exists(base): return "Not found", 404
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(base):
            for file in files:
                if file == 'output.log': continue
                full = os.path.join(root, file)
                zf.write(full, os.path.relpath(full, base))
    mem.seek(0)
    return send_file(mem, mimetype='application/zip', as_attachment=True,
                     download_name=f"{sid}.zip")

@app.route('/api/server/<sid>/accounts', methods=['GET'])
@login_required
def api_get_accounts(sid):
    base = server_folder(sid)
    if not base: return jsonify({'accounts': []})
    fp = os.path.join(base, 'accounts.json')
    if not os.path.exists(fp): return jsonify({'accounts': []})
    try:
        with open(fp, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, list): data = []
        return jsonify({'accounts': data})
    except Exception:
        return jsonify({'accounts': []})

@app.route('/api/server/<sid>/accounts', methods=['POST'])
@login_required
def api_save_accounts(sid):
    base = server_folder(sid)
    if not base: return jsonify({'error':'Not found'}), 404
    data = request.get_json() or {}
    accounts = data.get('accounts', [])
    clean = [{'uid': str(a.get('uid','')).strip(),
              'password': str(a.get('password','')).strip()} for a in accounts]
    with open(os.path.join(base, 'accounts.json'), 'w', encoding='utf-8') as f:
        json.dump(clean, f, indent=2, ensure_ascii=False)
    return jsonify({'success': True})

@app.route('/api/server/<sid>/startup', methods=['GET'])
@login_required
def api_get_startup(sid):
    s = get_server(sid)
    if not s: return jsonify({'error':'Not found'}), 404
    return jsonify({'main_file': s.get('main_file','main.py'),
                    'requirements_file': s.get('requirements_file','requirements.txt')})

@app.route('/api/server/<sid>/startup', methods=['POST'])
@login_required
def api_set_startup(sid):
    d = request.get_json() or {}
    update_server(sid, {
        'main_file': (d.get('main_file') or 'main.py').strip(),
        'requirements_file': (d.get('requirements_file') or 'requirements.txt').strip(),
    })
    return jsonify({'success': True})

# ============================================
# API — TEMPLATES
# ============================================
def _tpl_base(): return os.path.abspath(TEMPLATES_BOT)

@app.route('/api/templates/files')
@login_required
def api_tpl_files():
    base = _tpl_base()
    if not os.path.exists(base): return jsonify({'files': []})
    out = []
    for it in sorted(os.listdir(base)):
        if it.startswith('.'): continue
        p = os.path.join(base, it)
        out.append({'name': it, 'is_dir': os.path.isdir(p),
                    'size': os.path.getsize(p) if os.path.isfile(p) else 0})
    return jsonify({'files': out})

@app.route('/api/templates/file', methods=['GET'])
@login_required
def api_tpl_get_file():
    fp = safe_join(_tpl_base(), request.args.get('filename',''))
    if not fp or not os.path.isfile(fp): return jsonify({'error':'Not found'}), 404
    try:
        with open(fp, 'r', encoding='utf-8', errors='replace') as f:
            return jsonify({'content': f.read()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/templates/file', methods=['POST'])
@login_required
def api_tpl_save_file():
    data = request.get_json() or {}
    fp = safe_join(_tpl_base(), data.get('filename',''))
    if not fp: return jsonify({'error':'Access denied'}), 403
    with open(fp, 'w', encoding='utf-8') as f:
        f.write(data.get('content',''))
    return jsonify({'success': True})

@app.route('/api/templates/file', methods=['DELETE'])
@login_required
def api_tpl_del_file():
    data = request.get_json() or {}
    fp = safe_join(_tpl_base(), data.get('filename',''))
    if not fp: return jsonify({'error':'Access denied'}), 403
    try:
        if os.path.isdir(fp): shutil.rmtree(fp)
        elif os.path.isfile(fp): os.remove(fp)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/templates/upload', methods=['POST'])
@login_required
def api_tpl_upload():
    target = _tpl_base(); os.makedirs(target, exist_ok=True)
    files = request.files.getlist('files')
    up = []
    for f in files:
        if not f.filename: continue
        safe_name = os.path.basename(f.filename)
        f.save(os.path.join(target, safe_name)); up.append(safe_name)
    return jsonify({'success': True, 'uploaded': up})

@app.route('/api/templates/upload_zip', methods=['POST'])
@login_required
def api_tpl_upload_zip():
    target = _tpl_base(); os.makedirs(target, exist_ok=True)
    f = request.files.get('file')
    if not f: return jsonify({'error':'No file'}), 400
    tmp = os.path.join(target, f.filename); f.save(tmp)
    try:
        with zipfile.ZipFile(tmp, 'r') as zf: zf.extractall(target)
        os.remove(tmp); return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/templates/upload_accounts', methods=['POST'])
@login_required
def api_templates_upload_accounts():
    f = request.files.get('file')
    if not f: return jsonify({'error': 'No file'}), 400
    try:
        data = json.load(f.stream)
        if not isinstance(data, list):
            return jsonify({'error': 'Must be list'}), 400
        clean = [{'uid': str(a.get('uid','')).strip(),
                  'password': str(a.get('password','')).strip()}
                 for a in data if a.get('uid') and a.get('password')]
        with open(ACCOUNTS_FILE, 'w', encoding='utf-8') as out:
            json.dump(clean, out, indent=2, ensure_ascii=False)
        count = rotator.reload_accounts()
        return jsonify({'success': True, 'count': count})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/templates/accounts', methods=['DELETE'])
@login_required
def api_templates_delete_accounts():
    """accounts.json delete + rotator pool clear + auto rotation OFF."""
    try:
        if os.path.exists(ACCOUNTS_FILE):
            os.remove(ACCOUNTS_FILE)
        with rotator.lock:
            rotator.accounts = []
            rotator.current_index = 0
            rotator.batch_started_at = None
        if rotator.enabled:
            rotator.toggle(False)
        else:
            rotator._save_state()
        print("[accounts] 🗑 accounts.json deleted + pool cleared")
        return jsonify({'success': True, 'count': 0})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/templates/accounts/download')
@login_required
def api_templates_download_accounts():
    if not os.path.exists(ACCOUNTS_FILE):
        return "accounts.json not found", 404
    return send_file(
        os.path.abspath(ACCOUNTS_FILE),
        mimetype='application/json',
        as_attachment=True,
        download_name='accounts.json'
    )

# ============================================
# API — ROTATION TOGGLE
# ============================================
@app.route('/api/rotation/toggle', methods=['POST'])
@login_required
def api_rotation_toggle():
    data = request.get_json() or {}
    on = bool(data.get('on'))
    rotator.reload_accounts()
    enabled = rotator.toggle(on)
    return jsonify({'success': True, 'enabled': enabled})

@app.route('/api/rotation/status')
@login_required
def api_rotation_status():
    return jsonify({
        'enabled': rotator.is_enabled(),
        'accounts': len(rotator.accounts),
        'index': rotator.current_index,
        'batch_size': BATCH_SIZE,
        'batch_hours': BATCH_DURATION // 3600,
    })

# ============================================
# API — ALL CLEAN (Full Reset)
# ============================================
@app.route('/api/all-clean', methods=['POST'])
@login_required
def api_all_clean():
    """Full reset — servers, accounts, templates, rotation sab fresh.
       LOGIN aur LEVEL_EXP safe rahenge."""
    try:
        deleted_servers = 0

        # 1. Saare running bots kill karo
        try:
            for s in load_servers().get('servers', []):
                if s.get('pid'):
                    kill_pid(s['pid'])
            time.sleep(2)
        except Exception: pass

        # 2. Auto rotation OFF
        try:
            if rotator.enabled:
                rotator.toggle(False)
            rotator.stop_flag = True
        except Exception: pass

        # 3. Saare servers folders delete
        try:
            if os.path.exists(SERVERS_DIR):
                for folder in os.listdir(SERVERS_DIR):
                    fp = os.path.join(SERVERS_DIR, folder)
                    if os.path.isdir(fp):
                        shutil.rmtree(fp, ignore_errors=True)
                        deleted_servers += 1
        except Exception as e:
            print(f"[all-clean] servers del err: {e}")

        # 4. servers.json reset
        save_servers({'servers': []})

        # 5. accounts.json delete
        if os.path.exists(ACCOUNTS_FILE):
            try: os.remove(ACCOUNTS_FILE)
            except Exception: pass

        # 6. Rotator pool empty
        with rotator.lock:
            rotator.accounts = []
            rotator.current_index = 0
            rotator.batch_started_at = None
        rotator._save_state()

        # 7. templates_bot contents clean
        try:
            if os.path.exists(TEMPLATES_BOT):
                for item in os.listdir(TEMPLATES_BOT):
                    ip = os.path.join(TEMPLATES_BOT, item)
                    if os.path.isdir(ip):
                        shutil.rmtree(ip, ignore_errors=True)
                    else:
                        os.remove(ip)
        except Exception as e:
            print(f"[all-clean] templates err: {e}")

        # 8. Fresh default template files recreate
        ensure_template_defaults()

        # 9. rotation.json delete (fresh state)
        if os.path.exists(ROTATION_FILE):
            try: os.remove(ROTATION_FILE)
            except Exception: pass

        print(f"[all-clean] ✅ Full reset done. Servers deleted: {deleted_servers}")
        return jsonify({
            'success': True,
            'deleted_servers': deleted_servers,
            'message': 'Full reset complete — fresh new state'
        })
    except Exception as e:
        print(f"[all-clean] ❌ Error: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================
# MAIN
# ============================================
if __name__ == '__main__':
    ensure_template_defaults()
    load_level_exp()
    rotator.reload_accounts()

    print("\n" + "="*55)
    print("🚀 JUBAYER HOSTING — MANUAL + OPTIONAL AUTO")
    print("="*55)
    print("📍 Local     : http://localhost:5000")
    print("🔐 MASTER    : SEMY / M4X")
    print("👤 USER      : admin / admin123")
    print(f"📊 Levels    : {len(_LEVEL_DATA)} loaded")
    print(f"📋 Accounts  : {len(rotator.accounts)} loaded")
    print("="*55)
    print("\n💡 Auto Rotation dashboard pe toggle se ON/OFF karo")
    print("💡 Templates page se accounts.json delete/replace")
    print("💡 Dashboard pe 🧹 All Clean = FULL RESET\n")

    app.run(debug=False, host='0.0.0.0', port=5000)