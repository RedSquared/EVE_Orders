#!/usr/bin/env python3
"""
EVE Orders Widget — personal desktop tool
Requires: pip install requests

Setup:
  http://localhost:8080/oauth/callback must be registered in your EVE app.

Keys / mouse:
  ← →  or  scroll wheel      navigate orders
  Mouse button 8 / 9          prev / next  (side buttons — may vary by driver)
  1 / 2 / 3                   select competitor price row
  Enter                       copy undercut price to clipboard

Token + settings stored in ~/.eve_widget_tokens.json
"""

import tkinter as tk
from tkinter import font as tkfont
import threading, json, os, math, secrets, hashlib, base64, webbrowser, time
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse, urlencode

# ── Config ────────────────────────────────────────────────────────────────────
CLIENT_ID     = '4c2fbc9d96714465a2a773366e9e8b2a'
CALLBACK_PORT = 8080
CALLBACK_PATH = '/oauth/callback'
REDIRECT_URI  = f'http://localhost:{CALLBACK_PORT}{CALLBACK_PATH}'
TOKEN_FILE    = os.path.expanduser('~/.eve_widget_tokens.json')
SCOPES        = 'esi-markets.read_character_orders.v1'
SSO           = 'https://login.eveonline.com'
ESI           = 'https://esi.evetech.net/latest'

# ── Colours ───────────────────────────────────────────────────────────────────
BG, BG2, BG3     = '#070710', '#0e0e1c', '#141428'
BORDER           = '#232340'
TEXT, DIM        = '#c0c8d8', '#68707e'
GOLD             = '#c6a227'
BLUE, GREEN, RED = '#4a9eed', '#3dba6e', '#d14040'


# ── Persistent data ───────────────────────────────────────────────────────────
# File structure:
# {
#   "active_char": "12345678",
#   "ticks": 1,
#   "scope": "station",
#   "characters": {
#     "12345678": {
#       "access_token": "...", "refresh_token": "...",
#       "expires_at": 1234567890.0,
#       "char_name": "My Pilot", "char_id": 12345678
#     }
#   }
# }

def load_data():
    try:
        with open(TOKEN_FILE) as f:
            data = json.load(f)
    except FileNotFoundError:
        return {'active_char': None, 'ticks': 1, 'scope': 'station', 'characters': {}}
    # Migrate old single-char flat format
    if 'characters' not in data and 'access_token' in data:
        cid  = str(data.get('char_id', 'unknown'))
        data = {
            'active_char': cid,
            'ticks': 1,
            'scope': 'station',
            'characters': {cid: data},
        }
        save_data(data)
    data.setdefault('ticks', 1)
    data.setdefault('scope', 'station')
    data.setdefault('characters', {})
    return data

def save_data(data):
    with open(TOKEN_FILE, 'w') as f:
        json.dump(data, f, indent=2)


# ── Auth helpers ──────────────────────────────────────────────────────────────

def pkce_pair():
    verifier  = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b'=').decode()
    return verifier, challenge

def get_access_token(data):
    active_id = str(data.get('active_char', ''))
    acct = data.get('characters', {}).get(active_id)
    if not acct:
        raise RuntimeError('No active character — please log in.')
    if time.time() < acct.get('expires_at', 0):
        return acct['access_token']
    # Refresh
    r = requests.post(f'{SSO}/v2/oauth/token', data={
        'grant_type':    'refresh_token',
        'refresh_token': acct['refresh_token'],
        'client_id':     CLIENT_ID,
    })
    r.raise_for_status()
    t = r.json()
    acct.update({
        'access_token':  t['access_token'],
        'refresh_token': t.get('refresh_token', acct['refresh_token']),
        'expires_at':    time.time() + t.get('expires_in', 1200) - 30,
    })
    data['characters'][active_id] = acct
    save_data(data)
    return acct['access_token']


# ── ESI helpers ───────────────────────────────────────────────────────────────

def esi_get(path, data):
    at = get_access_token(data)
    r  = requests.get(f'{ESI}{path}', headers={'Authorization': f'Bearer {at}'})
    r.raise_for_status()
    return r.json()

def resolve_names(ids):
    if not ids:
        return {}
    r = requests.post(f'{ESI}/universe/names/', json=list(ids)[:999])
    return {item['id']: item['name'] for item in (r.json() if r.ok else [])}

def fetch_market(region_id, type_id, cache):
    key = (region_id, type_id)
    if key in cache:
        return cache[key]
    url  = f'{ESI}/markets/{region_id}/orders/?type_id={type_id}&page='
    r1   = requests.get(url + '1')
    r1.raise_for_status()
    pages = min(int(r1.headers.get('X-Pages', 1)), 20)
    rows  = r1.json()
    for p in range(2, pages + 1):
        rp = requests.get(url + str(p))
        if rp.ok:
            rows.extend(rp.json())
    cache[key] = rows
    return rows


# ── Price helpers ─────────────────────────────────────────────────────────────

def top3_prices(order, all_market, scope):
    is_buy = order['is_buy_order']
    our_id = order['order_id']
    if scope == 'station':
        loc    = order['location_id']
        prices = [m['price'] for m in all_market
                  if m['is_buy_order'] == is_buy
                  and m['order_id'] != our_id
                  and m['location_id'] == loc]
    else:
        prices = [m['price'] for m in all_market
                  if m['is_buy_order'] == is_buy and m['order_id'] != our_id]
    prices.sort(reverse=is_buy)
    return prices[:3]

def undercut_price(price, is_buy, ticks):
    if not price or price <= 0:
        return None
    scale = 10 ** (math.floor(math.log10(price)) - 3)
    sig4  = math.floor(price / scale + 1e-9)
    adj   = sig4 + ticks if is_buy else sig4 - ticks
    return round(adj * scale, 2)

def fmt_isk(v):
    return f'{v:,.2f}'

def fmt_diff(diff):
    sign = '+' if diff >= 0 else '−'
    a    = abs(diff)
    if a >= 1e9: return f'{sign}{a/1e9:.2f}B'
    if a >= 1e6: return f'{sign}{a/1e6:.2f}M'
    if a >= 1e3: return f'{sign}{a/1e3:.1f}K'
    return f'{sign}{a:.2f}'


# ── OAuth callback server ─────────────────────────────────────────────────────

class _OAuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not self.path.startswith(CALLBACK_PATH):
            self.send_response(404); self.end_headers(); return
        qs = parse_qs(urlparse(self.path).query)
        self.server.auth_code = qs.get('code', [None])[0]
        body = (b'<html><body style="background:#070710;color:#c0c8d8;'
                b'font:14px sans-serif;text-align:center;padding:40px">'
                b'<h2>Login complete &#8212; you can close this tab.</h2>'
                b'</body></html>')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass

def wait_for_oauth_code():
    srv = HTTPServer(('localhost', CALLBACK_PORT), _OAuthHandler)
    srv.auth_code = None
    srv.timeout   = 180
    while srv.auth_code is None:
        srv.handle_request()
    srv.server_close()
    return srv.auth_code


# ── Widget ────────────────────────────────────────────────────────────────────

class EVEWidget:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('EVE Widget')
        self.root.attributes('-topmost', True)
        self.root.resizable(False, False)
        self.root.configure(bg=BG)

        sf   = 'Segoe UI' if os.name == 'nt' else 'SF Pro Text'
        mono = 'Consolas'  if os.name == 'nt' else 'Menlo'
        self.f     = tkfont.Font(family=sf,   size=9)
        self.f_b   = tkfont.Font(family=sf,   size=9, weight='bold')
        self.f_sm  = tkfont.Font(family=sf,   size=7)
        self.f_m   = tkfont.Font(family=mono, size=9)
        self.f_mb  = tkfont.Font(family=mono, size=9,  weight='bold')
        self.f_big = tkfont.Font(family=mono, size=11, weight='bold')

        # Live state
        self.data    = load_data()
        self.ticks   = self.data['ticks']
        self.scope   = self.data['scope']
        self.orders  = []
        self.names   = {}
        self.idx     = 0
        self.sel_idx = 0
        self.mkt_cache = {}
        self.raw_mkt   = None   # cached raw market rows for current order
        self.mkt       = None   # {'prices': list[float]}

        self._build_ui()
        self._bind_keys()
        self.root.after(100, self._startup)
        self.root.mainloop()

    # ── Keyboard / mouse bindings ─────────────────────────────────────────────

    def _bind_keys(self):
        r = self.root
        r.bind('<Left>',   lambda _: self._nav(-1))
        r.bind('<Right>',  lambda _: self._nav(1))
        r.bind('1', lambda _: self._select(0))
        r.bind('2', lambda _: self._select(1))
        r.bind('3', lambda _: self._select(2))
        r.bind('<Return>', lambda _: self._copy())

        # Scroll wheel — works on any platform
        r.bind('<MouseWheel>', self._on_scroll)   # Windows / macOS
        r.bind('<Button-4>',   lambda _: self._nav(-1))  # Linux scroll up
        r.bind('<Button-5>',   lambda _: self._nav(1))   # Linux scroll down

        # Mouse side buttons — exact number varies by OS / driver.
        # Common mappings: 8=back, 9=forward.  Adjust if yours differ.
        r.bind('<Button-8>', lambda _: self._nav(-1))
        r.bind('<Button-9>', lambda _: self._nav(1))

    def _on_scroll(self, event):
        # Windows: event.delta is ±120; macOS: ±1
        self._nav(-1 if event.delta > 0 else 1)

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = self.root

        # ── Nav bar ──
        nav = tk.Frame(root, bg=BG)
        nav.pack(fill='x', padx=5, pady=(5, 2))

        self.btn_prev = self._mk_nav_btn(nav, '◀', lambda: self._nav(-1))
        self.btn_prev.pack(side='left')

        self.lbl_name = tk.Label(nav, text='Loading…', bg=BG, fg=GOLD,
                                  font=self.f_b, width=20, anchor='center')
        self.lbl_name.pack(side='left', expand=True, fill='x', padx=3)

        self.lbl_counter = tk.Label(nav, text='', bg=BG, fg=DIM, font=self.f_sm)
        self.lbl_counter.pack(side='left', padx=1)

        self.lbl_type = tk.Label(nav, text='', bg='#3a1010', fg=RED,
                                  font=self.f_sm, padx=3)
        self.lbl_type.pack(side='left', padx=2)

        self.btn_refresh = tk.Button(nav, text='⟳', command=self._refresh,
                                      bg=BG, fg=DIM, relief='flat', font=self.f_b,
                                      bd=0, activebackground=BG, activeforeground=TEXT)
        self.btn_refresh.pack(side='left')

        self.btn_next = self._mk_nav_btn(nav, '▶', lambda: self._nav(1))
        self.btn_next.pack(side='left')

        # ── Separator ──
        tk.Frame(root, bg=BORDER, height=1).pack(fill='x', padx=5)

        # ── Your price ──
        row = tk.Frame(root, bg=BG)
        row.pack(fill='x', padx=5, pady=(3, 1))
        tk.Label(row, text='Your price:', bg=BG, fg=DIM, font=self.f).pack(side='left')
        self.lbl_your = tk.Label(row, text='—', bg=BG, fg=TEXT, font=self.f_mb)
        self.lbl_your.pack(side='right')

        # ── Competitors ──
        tk.Label(root, text='COMPETITORS', bg=BG, fg=DIM, font=self.f_sm,
                 anchor='w').pack(fill='x', padx=5)

        self.price_frames = []
        self.lbl_prices   = []
        self.lbl_diffs    = []
        for i in range(3):
            f = tk.Frame(root, bg=BG2, padx=4, pady=3)
            tk.Label(f, text=f'#{i+1}', bg=BG2, fg=DIM, font=self.f_sm, width=2).pack(side='left')
            lp = tk.Label(f, text='', bg=BG2, fg=TEXT, font=self.f_mb, width=15, anchor='e')
            lp.pack(side='left', padx=(4, 0))
            ld = tk.Label(f, text='', bg=BG2, fg=DIM, font=self.f_m, width=10, anchor='e')
            ld.pack(side='left', padx=(3, 0))
            for w in (f, lp, ld) + tuple(f.winfo_children()):
                w.bind('<Button-1>', lambda e, n=i: self._select(n))
            self.price_frames.append(f)
            self.lbl_prices.append(lp)
            self.lbl_diffs.append(ld)

        self.lbl_mkt_msg = tk.Label(root, text='', bg=BG, fg=DIM, font=self.f, pady=4)

        # ── Separator ──
        tk.Frame(root, bg=BORDER, height=1).pack(fill='x', padx=5, pady=(4, 0))

        # ── Copy bar ──
        bar = tk.Frame(root, bg=BG)
        bar.pack(fill='x', padx=5, pady=5)
        info = tk.Frame(bar, bg=BG)
        info.pack(side='left', expand=True, fill='x')
        self.lbl_uc_lbl   = tk.Label(info, text='Undercut #1:', bg=BG, fg=DIM, font=self.f_sm)
        self.lbl_uc_lbl.pack(anchor='w')
        self.lbl_uc_price = tk.Label(info, text='—', bg=BG, fg=GOLD, font=self.f_big)
        self.lbl_uc_price.pack(anchor='w')
        self.btn_copy = tk.Button(bar, text='Copy', command=self._copy,
                                   bg=BLUE, fg='white', font=self.f_b,
                                   relief='flat', padx=12, pady=5,
                                   activebackground='#5aaefd', activeforeground='white')
        self.btn_copy.pack(side='right', padx=(6, 0))

        # ── Separator ──
        tk.Frame(root, bg=BORDER, height=1).pack(fill='x', padx=5)

        # ── Settings bar ──
        cfg = tk.Frame(root, bg=BG2, pady=4, padx=5)
        cfg.pack(fill='x')

        # Character selector
        self._char_var = tk.StringVar(value='—')
        self.char_menu = tk.OptionMenu(cfg, self._char_var, '—',
                                        command=self._on_char_select)
        self.char_menu.config(bg=BG3, fg=TEXT, font=self.f_sm, relief='flat',
                               highlightthickness=0, bd=0, width=12,
                               activebackground=BG, activeforeground=TEXT)
        self.char_menu['menu'].config(bg=BG3, fg=TEXT, font=self.f_sm,
                                       activebackground=BLUE, activeforeground='white')
        self.char_menu.pack(side='left')

        tk.Button(cfg, text='+', command=self._add_char,
                  bg=BG3, fg=GREEN, font=self.f_b, relief='flat',
                  padx=4, bd=1, activebackground=BG2, activeforeground=GREEN
                  ).pack(side='left', padx=(2, 6))

        # Scope toggle
        self.btn_scope = tk.Button(cfg, text=self._scope_label(),
                                    command=self._toggle_scope,
                                    bg=BG3, fg=BLUE, font=self.f_sm,
                                    relief='flat', padx=5, bd=1,
                                    activebackground=BG2, activeforeground=BLUE)
        self.btn_scope.pack(side='left', padx=(0, 6))

        # Ticks
        tk.Label(cfg, text='Ticks:', bg=BG2, fg=DIM, font=self.f_sm).pack(side='left')
        tk.Button(cfg, text='−', command=self._dec_ticks,
                  bg=BG3, fg=TEXT, font=self.f_sm, relief='flat',
                  padx=4, bd=1, activebackground=BG2, activeforeground='white'
                  ).pack(side='left', padx=(2, 0))
        self.lbl_ticks = tk.Label(cfg, text=str(self.ticks),
                                   bg=BG2, fg=TEXT, font=self.f_b, width=2, anchor='center')
        self.lbl_ticks.pack(side='left', padx=1)
        tk.Button(cfg, text='+', command=self._inc_ticks,
                  bg=BG3, fg=TEXT, font=self.f_sm, relief='flat',
                  padx=4, bd=1, activebackground=BG2, activeforeground='white'
                  ).pack(side='left')

        # Status / error line
        self.lbl_status = tk.Label(root, text='', bg=BG, fg=DIM,
                                    font=self.f, wraplength=290, justify='center')
        self.lbl_status.pack(padx=5, pady=(2, 5))

    def _mk_nav_btn(self, parent, text, cmd):
        return tk.Button(parent, text=text, command=cmd, bg=BG3, fg=TEXT,
                         relief='flat', font=self.f, activebackground=BG2,
                         activeforeground='white', padx=6, pady=2, bd=1)

    def _scope_label(self):
        return 'STA' if self.scope == 'station' else 'REG'

    # ── Settings actions ──────────────────────────────────────────────────────

    def _toggle_scope(self):
        self.scope = 'region' if self.scope == 'station' else 'station'
        self.btn_scope.config(text=self._scope_label())
        self._save_settings()
        # Re-filter already-fetched market data — no extra network call needed
        if self.raw_mkt is not None and self.orders:
            self.mkt     = {'prices': top3_prices(self.orders[self.idx], self.raw_mkt, self.scope)}
            self.sel_idx = 0
            self._render_prices()
        elif self.orders:
            self._load_market()

    def _inc_ticks(self):
        self.ticks = min(self.ticks + 1, 20)
        self.lbl_ticks.config(text=str(self.ticks))
        self._save_settings()
        self._render_prices()

    def _dec_ticks(self):
        self.ticks = max(self.ticks - 1, 1)
        self.lbl_ticks.config(text=str(self.ticks))
        self._save_settings()
        self._render_prices()

    def _save_settings(self):
        self.data['ticks'] = self.ticks
        self.data['scope'] = self.scope
        save_data(self.data)

    # ── Character switcher ────────────────────────────────────────────────────

    def _rebuild_char_menu(self):
        chars  = self.data.get('characters', {})
        active = str(self.data.get('active_char', ''))
        cur    = chars.get(active, {}).get('char_name', '—')
        self._char_var.set(cur)
        menu = self.char_menu['menu']
        menu.delete(0, 'end')
        for info in chars.values():
            name = info['char_name']
            menu.add_command(label=name,
                             command=tk._setit(self._char_var, name, self._on_char_select))
        menu.add_separator()
        menu.add_command(label='+ Add character', command=self._add_char)

    def _on_char_select(self, selection):
        chars = self.data.get('characters', {})
        for cid, info in chars.items():
            if info.get('char_name') == selection:
                if str(self.data.get('active_char')) != str(cid):
                    self.data['active_char'] = cid
                    save_data(self.data)
                    self.mkt_cache = {}
                    self.raw_mkt   = None
                    self._load_orders()
                return

    # ── Auth ──────────────────────────────────────────────────────────────────

    def _startup(self):
        self._rebuild_char_menu()
        if self.data.get('characters'):
            self._load_orders()
        else:
            self._do_login()

    def _add_char(self):
        self._do_login()

    def _do_login(self):
        self._set_status('Opening browser for EVE login…')
        verifier, challenge = pkce_pair()
        state  = secrets.token_urlsafe(16)
        params = urlencode({
            'response_type':         'code',
            'client_id':             CLIENT_ID,
            'redirect_uri':          REDIRECT_URI,
            'scope':                 SCOPES,
            'code_challenge':        challenge,
            'code_challenge_method': 'S256',
            'state':                 state,
        })
        webbrowser.open(f'{SSO}/v2/oauth/authorize?{params}')

        def worker():
            try:
                code = wait_for_oauth_code()
                r    = requests.post(f'{SSO}/v2/oauth/token', data={
                    'grant_type':    'authorization_code',
                    'code':          code,
                    'redirect_uri':  REDIRECT_URI,
                    'client_id':     CLIENT_ID,
                    'code_verifier': verifier,
                })
                r.raise_for_status()
                t    = r.json()
                at   = t['access_token']
                info = requests.get(f'{SSO}/v2/oauth/verify',
                                    headers={'Authorization': f'Bearer {at}'}).json()
                cid  = str(info['CharacterID'])
                self.data['characters'][cid] = {
                    'access_token':  at,
                    'refresh_token': t['refresh_token'],
                    'expires_at':    time.time() + t.get('expires_in', 1200) - 30,
                    'char_name':     info.get('CharacterName', 'Pilot'),
                    'char_id':       int(cid),
                }
                self.data['active_char'] = cid
                save_data(self.data)
                self.root.after(0, self._after_login)
            except Exception as e:
                self.root.after(0, lambda: self._set_status(f'Login failed: {e}'))

        threading.Thread(target=worker, daemon=True).start()

    def _after_login(self):
        self._set_status('')
        self._rebuild_char_menu()
        self.mkt_cache = {}
        self._load_orders()

    # ── Load orders ───────────────────────────────────────────────────────────

    def _load_orders(self):
        self._set_status('Loading orders…')
        data = load_data()
        self.data = data

        def worker():
            try:
                active = str(data.get('active_char', ''))
                acct   = data.get('characters', {}).get(active, {})
                cid    = acct.get('char_id')
                raw    = esi_get(f'/characters/{cid}/orders/', data)
                orders = [o for o in raw if not o.get('is_corporation')]
                names  = resolve_names(list({o['type_id'] for o in orders}))
                self.root.after(0, lambda: self._on_orders(orders, names))
            except Exception as e:
                self.root.after(0, lambda: self._set_status(f'Error: {e}'))

        threading.Thread(target=worker, daemon=True).start()

    def _on_orders(self, orders, names):
        self.orders  = orders
        self.names   = names
        self.idx     = 0
        self.sel_idx = 0
        self._set_status('')
        if not orders:
            self._set_status('No personal orders found.')
            return
        self._load_market()

    # ── Load market ───────────────────────────────────────────────────────────

    def _load_market(self):
        self.mkt     = None
        self.raw_mkt = None
        self._render_nav()
        self._clear_prices()
        self._show_mkt_msg('Fetching market…')
        o = self.orders[self.idx]

        def worker():
            try:
                rows = fetch_market(o['region_id'], o['type_id'], self.mkt_cache)
                self.root.after(0, lambda: self._on_market(rows, o))
            except Exception as e:
                self.root.after(0, lambda: self._show_mkt_msg(f'Market error: {e}'))

        threading.Thread(target=worker, daemon=True).start()

    def _on_market(self, rows, order):
        self.raw_mkt = rows
        self.mkt     = {'prices': top3_prices(order, rows, self.scope)}
        self.sel_idx = 0
        self._show_mkt_msg('')
        self._render_prices()

    # ── Navigation ────────────────────────────────────────────────────────────

    def _nav(self, d):
        if not self.orders:
            return
        self.idx     = (self.idx + d) % len(self.orders)
        self.sel_idx = 0
        self._load_market()

    def _select(self, i):
        if not self.mkt or i >= len(self.mkt['prices']):
            return
        self.sel_idx = i
        self._render_prices()

    def _refresh(self):
        self.mkt_cache = {}
        self.raw_mkt   = None
        self.orders    = []
        self._clear_prices()
        self._load_orders()

    # ── Copy ──────────────────────────────────────────────────────────────────

    def _copy(self):
        if not self.mkt or not self.mkt['prices']:
            return
        price = self.mkt['prices'][self.sel_idx]
        o     = self.orders[self.idx]
        val   = undercut_price(price, o['is_buy_order'], self.ticks)
        if val is None:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(f'{val:.2f}')
        self.btn_copy.config(text='✓', bg=GREEN)
        self.root.after(2500, lambda: self.btn_copy.config(text='Copy', bg=BLUE))

    # ── Render ────────────────────────────────────────────────────────────────

    def _render_nav(self):
        if not self.orders:
            self.lbl_name.config(text='No orders')
            self.lbl_counter.config(text='')
            self.lbl_type.config(text='', bg=BG)
            self.lbl_your.config(text='—')
            return
        o      = self.orders[self.idx]
        is_buy = o['is_buy_order']
        self.lbl_name.config(text=self.names.get(o['type_id'], f"#{o['type_id']}")[:30])
        self.lbl_counter.config(text=f"{self.idx+1}/{len(self.orders)}")
        self.lbl_your.config(text=fmt_isk(o['price']))
        if is_buy:
            self.lbl_type.config(text='BUY',  bg='#0e2a0e', fg=GREEN)
        else:
            self.lbl_type.config(text='SELL', bg='#3a1010', fg=RED)

    def _clear_prices(self):
        for f in self.price_frames:
            f.pack_forget()
        self.lbl_uc_lbl.config(text='Undercut #1:')
        self.lbl_uc_price.config(text='—')

    def _show_mkt_msg(self, text):
        if text:
            self.lbl_mkt_msg.config(text=text)
            self.lbl_mkt_msg.pack(fill='x', padx=5)
        else:
            self.lbl_mkt_msg.config(text='')
            self.lbl_mkt_msg.pack_forget()

    def _render_prices(self):
        self._render_nav()
        self._clear_prices()
        if not self.mkt or not self.mkt['prices']:
            self._show_mkt_msg('No competitors found')
            return
        o      = self.orders[self.idx]
        is_buy = o['is_buy_order']
        for i, price in enumerate(self.mkt['prices']):
            f      = self.price_frames[i]
            diff   = price - o['price']
            bad    = (diff > 0) if is_buy else (diff < 0)
            row_bg = BG3 if i == self.sel_idx else BG2
            self.lbl_prices[i].config(text=fmt_isk(price), bg=row_bg)
            self.lbl_diffs[i].config(text=fmt_diff(diff),
                                      fg=RED if bad else GREEN, bg=row_bg)
            f.config(bg=row_bg)
            for w in f.winfo_children():
                try: w.config(bg=row_bg)
                except tk.TclError: pass
            f.pack(fill='x', padx=5, pady=1)
        uc  = undercut_price(self.mkt['prices'][self.sel_idx], is_buy, self.ticks)
        lbl = 'Outbid' if is_buy else 'Undercut'
        self.lbl_uc_lbl.config(text=f'{lbl} #{self.sel_idx+1}:')
        self.lbl_uc_price.config(text=fmt_isk(uc) if uc else '—')

    def _set_status(self, msg):
        self.lbl_status.config(text=msg)


if __name__ == '__main__':
    EVEWidget()
