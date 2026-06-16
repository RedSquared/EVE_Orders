#!/usr/bin/env python3
"""
EVE Orders Widget — personal desktop tool
Requires: pip install requests

Setup:
  1. Go to https://developers.eveonline.com/ and edit your EVE application.
     Add  http://localhost:7849/callback  to the list of callback URLs.
  2. Set CLIENT_ID below (same value as in index.html is fine once you add the callback).
  3. python widget.py
     First run opens a browser for EVE login; tokens are saved to ~/.eve_widget_tokens.json.

Keyboard shortcuts:
  Left / Right   navigate orders
  1 / 2 / 3      select competitor price
  Enter          copy undercut price to clipboard
"""

import tkinter as tk
from tkinter import font as tkfont
import threading, json, os, math, secrets, hashlib, base64, webbrowser, time
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse, urlencode

# ── Config ────────────────────────────────────────────────────────────────────
CLIENT_ID     = 'a46cb3ebd7d843c7ac95f827a43f5e56'   # from index.html
CALLBACK_PORT = 7849
REDIRECT_URI  = f'http://localhost:{CALLBACK_PORT}/callback'
TOKEN_FILE    = os.path.expanduser('~/.eve_widget_tokens.json')
SCOPES        = 'esi-markets.read_character_orders.v1'
SSO           = 'https://login.eveonline.com'
ESI           = 'https://esi.evetech.net/latest'
TICKS         = 1   # price ticks to move when computing undercut

# ── Colours (matches the web app theme) ──────────────────────────────────────
BG, BG2, BG3   = '#070710', '#0e0e1c', '#141428'
BORDER         = '#232340'
TEXT, DIM      = '#c0c8d8', '#68707e'
GOLD           = '#c6a227'
BLUE, GREEN, RED = '#4a9eed', '#3dba6e', '#d14040'


# ── Token helpers ─────────────────────────────────────────────────────────────

def load_tokens():
    try:
        with open(TOKEN_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return None

def save_tokens(data):
    with open(TOKEN_FILE, 'w') as f:
        json.dump(data, f)

def pkce_pair():
    verifier  = secrets.token_urlsafe(64)
    digest    = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b'=').decode()
    return verifier, challenge

def do_token_exchange(code, verifier):
    r = requests.post(f'{SSO}/v2/oauth/token', data={
        'grant_type':    'authorization_code',
        'code':          code,
        'redirect_uri':  REDIRECT_URI,
        'client_id':     CLIENT_ID,
        'code_verifier': verifier,
    })
    r.raise_for_status()
    return r.json()

def do_token_refresh(rt):
    r = requests.post(f'{SSO}/v2/oauth/token', data={
        'grant_type':    'refresh_token',
        'refresh_token': rt,
        'client_id':     CLIENT_ID,
    })
    r.raise_for_status()
    return r.json()

def get_access_token():
    tokens = load_tokens()
    if not tokens:
        raise RuntimeError('Not logged in')
    if time.time() < tokens.get('expires_at', 0):
        return tokens['access_token']
    t = do_token_refresh(tokens['refresh_token'])
    tokens.update({
        'access_token':  t['access_token'],
        'refresh_token': t.get('refresh_token', tokens['refresh_token']),
        'expires_at':    time.time() + t.get('expires_in', 1200) - 30,
    })
    save_tokens(tokens)
    return tokens['access_token']


# ── ESI helpers ───────────────────────────────────────────────────────────────

def esi_get(path):
    at = get_access_token()
    r  = requests.get(f'{ESI}{path}', headers={'Authorization': f'Bearer {at}'})
    r.raise_for_status()
    return r.json()

def resolve_names(ids):
    if not ids:
        return {}
    r = requests.post(f'{ESI}/universe/names/', json=list(ids)[:999])
    if not r.ok:
        return {}
    return {item['id']: item['name'] for item in r.json()}

def fetch_market(region_id, type_id, cache):
    key = (region_id, type_id)
    if key in cache:
        return cache[key]
    url  = f'{ESI}/markets/{region_id}/orders/?type_id={type_id}&page='
    r1   = requests.get(url + '1')
    r1.raise_for_status()
    pages = min(int(r1.headers.get('X-Pages', 1)), 20)
    data  = r1.json()
    for p in range(2, pages + 1):
        rp = requests.get(url + str(p))
        if rp.ok:
            data.extend(rp.json())
    cache[key] = data
    return data

def top3_prices(order, all_market):
    """Return (prices, scope) where prices are up to 3 best competitor prices."""
    is_buy = order['is_buy_order']
    our_id = order['order_id']
    loc    = order['location_id']

    station = [m['price'] for m in all_market
               if m['is_buy_order'] == is_buy
               and m['order_id'] != our_id
               and m['location_id'] == loc]
    if station:
        station.sort(reverse=is_buy)
        return station[:3], 'station'

    region = [m['price'] for m in all_market
              if m['is_buy_order'] == is_buy and m['order_id'] != our_id]
    region.sort(reverse=is_buy)
    return region[:3], 'region'


# ── Price math ────────────────────────────────────────────────────────────────

def undercut_price(price, is_buy, ticks=TICKS):
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
        qs = parse_qs(urlparse(self.path).query)
        self.server.auth_code = qs.get('code', [None])[0]
        body = b'<html><body style="background:#070710;color:#c0c8d8;font:14px sans-serif;text-align:center;padding:40px"><h2>Login complete — you can close this tab.</h2></body></html>'
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass   # silence console noise

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

        # Fonts
        sf   = 'Segoe UI' if os.name == 'nt' else 'SF Pro Text'
        mono = 'Consolas'  if os.name == 'nt' else 'Menlo'
        self.f_ui   = tkfont.Font(family=sf,   size=9)
        self.f_ui_b = tkfont.Font(family=sf,   size=9, weight='bold')
        self.f_sm   = tkfont.Font(family=sf,   size=7)
        self.f_mono = tkfont.Font(family=mono, size=9)
        self.f_mono_b = tkfont.Font(family=mono, size=9,  weight='bold')
        self.f_big  = tkfont.Font(family=mono, size=11, weight='bold')

        # State
        self.orders    = []
        self.idx       = 0
        self.sel_idx   = 0
        self.mkt_cache = {}
        self.mkt       = None   # {'prices': list, 'scope': str} or None

        self._build_ui()

        # Keyboard shortcuts
        self.root.bind('<Left>',  lambda _: self._nav(-1))
        self.root.bind('<Right>', lambda _: self._nav(1))
        self.root.bind('1', lambda _: self._select(0))
        self.root.bind('2', lambda _: self._select(1))
        self.root.bind('3', lambda _: self._select(2))
        self.root.bind('<Return>', lambda _: self._copy())

        self.root.after(100, self._startup)
        self.root.mainloop()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = self.root

        # Nav bar
        nav = tk.Frame(root, bg=BG)
        nav.pack(fill='x', padx=5, pady=(5, 2))

        self.btn_prev = self._nav_btn(nav, '◀', lambda: self._nav(-1))
        self.btn_prev.pack(side='left')

        self.lbl_name = tk.Label(nav, text='Loading…', bg=BG, fg=GOLD,
                                  font=self.f_ui_b, width=22, anchor='center')
        self.lbl_name.pack(side='left', expand=True, fill='x', padx=3)

        self.lbl_counter = tk.Label(nav, text='', bg=BG, fg=DIM, font=self.f_sm)
        self.lbl_counter.pack(side='left', padx=1)

        self.lbl_type = tk.Label(nav, text='', bg='#3a1010', fg=RED,
                                  font=self.f_sm, padx=3)
        self.lbl_type.pack(side='left', padx=2)

        self.btn_refresh = tk.Button(nav, text='⟳', command=self._refresh,
                                      bg=BG, fg=DIM, relief='flat',
                                      font=self.f_ui_b, bd=0,
                                      activebackground=BG, activeforeground=TEXT)
        self.btn_refresh.pack(side='left')

        self.btn_next = self._nav_btn(nav, '▶', lambda: self._nav(1))
        self.btn_next.pack(side='left')

        # Separator
        tk.Frame(root, bg=BORDER, height=1).pack(fill='x', padx=5)

        # Your price
        row = tk.Frame(root, bg=BG)
        row.pack(fill='x', padx=5, pady=(3, 1))
        tk.Label(row, text='Your price:', bg=BG, fg=DIM, font=self.f_ui).pack(side='left')
        self.lbl_your = tk.Label(row, text='—', bg=BG, fg=TEXT,
                                  font=self.f_mono_b)
        self.lbl_your.pack(side='right')

        # Competitors header
        tk.Label(root, text='COMPETITORS', bg=BG, fg=DIM, font=self.f_sm,
                 anchor='w').pack(fill='x', padx=5)

        # Three price rows (hidden until market data loads)
        self.price_frames = []
        self.lbl_prices   = []
        self.lbl_diffs    = []
        for i in range(3):
            f = tk.Frame(root, bg=BG2, padx=4, pady=3)
            tk.Label(f, text=f'#{i+1}', bg=BG2, fg=DIM,
                     font=self.f_sm, width=2).pack(side='left')
            lp = tk.Label(f, text='', bg=BG2, fg=TEXT,
                          font=self.f_mono_b, width=15, anchor='e')
            lp.pack(side='left', padx=(4, 0))
            ld = tk.Label(f, text='', bg=BG2, fg=DIM,
                          font=self.f_mono, width=10, anchor='e')
            ld.pack(side='left', padx=(3, 0))
            # Bind click on the whole row
            for w in (f, lp, ld) + tuple(f.winfo_children()):
                w.bind('<Button-1>', lambda e, n=i: self._select(n))
            self.price_frames.append(f)
            self.lbl_prices.append(lp)
            self.lbl_diffs.append(ld)

        self.lbl_mkt_msg = tk.Label(root, text='', bg=BG, fg=DIM,
                                     font=self.f_ui, pady=4)

        # Separator
        tk.Frame(root, bg=BORDER, height=1).pack(fill='x', padx=5, pady=(4, 0))

        # Copy bar
        bar = tk.Frame(root, bg=BG)
        bar.pack(fill='x', padx=5, pady=5)

        info = tk.Frame(bar, bg=BG)
        info.pack(side='left', expand=True, fill='x')
        self.lbl_uc_lbl   = tk.Label(info, text='Undercut #1:', bg=BG, fg=DIM, font=self.f_sm)
        self.lbl_uc_lbl.pack(anchor='w')
        self.lbl_uc_price = tk.Label(info, text='—', bg=BG, fg=GOLD, font=self.f_big)
        self.lbl_uc_price.pack(anchor='w')

        self.btn_copy = tk.Button(bar, text='Copy', command=self._copy,
                                   bg=BLUE, fg='white', font=self.f_ui_b,
                                   relief='flat', padx=12, pady=5,
                                   activebackground='#5aaefd', activeforeground='white')
        self.btn_copy.pack(side='right', padx=(6, 0))

        # Status line (errors, loading)
        self.lbl_status = tk.Label(root, text='', bg=BG, fg=DIM,
                                    font=self.f_ui, wraplength=290, justify='center')
        self.lbl_status.pack(padx=5, pady=(0, 4))

    def _nav_btn(self, parent, text, cmd):
        return tk.Button(parent, text=text, command=cmd,
                         bg=BG3, fg=TEXT, relief='flat', font=self.f_ui,
                         activebackground=BG2, activeforeground='white',
                         padx=6, pady=2, bd=1)

    # ── Startup / login ───────────────────────────────────────────────────────

    def _startup(self):
        if load_tokens():
            self._load_orders()
        else:
            self._do_login()

    def _do_login(self):
        self._set_status('Opening browser for EVE SSO login…')
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
                code   = wait_for_oauth_code()
                tokens = do_token_exchange(code, verifier)
                at     = tokens['access_token']
                info   = requests.get(f'{SSO}/v2/oauth/verify',
                                      headers={'Authorization': f'Bearer {at}'}).json()
                save_tokens({
                    'access_token':  at,
                    'refresh_token': tokens['refresh_token'],
                    'expires_at':    time.time() + tokens.get('expires_in', 1200) - 30,
                    'char_name':     info.get('CharacterName', 'Pilot'),
                    'char_id':       info.get('CharacterID'),
                })
                self.root.after(0, self._load_orders)
            except Exception as e:
                self.root.after(0, lambda: self._set_status(f'Login failed: {e}'))

        threading.Thread(target=worker, daemon=True).start()

    # ── Load orders ───────────────────────────────────────────────────────────

    def _load_orders(self):
        self._set_status('Loading orders…')

        def worker():
            try:
                tokens  = load_tokens()
                char_id = tokens['char_id']
                raw     = esi_get(f'/characters/{char_id}/orders/')
                orders  = [o for o in raw if not o.get('is_corporation')]
                type_ids = list({o['type_id'] for o in orders})
                names    = resolve_names(type_ids)
                self.root.after(0, lambda: self._on_orders(orders, names))
            except Exception as e:
                self.root.after(0, lambda: self._set_status(f'Error: {e}'))

        threading.Thread(target=worker, daemon=True).start()

    def _on_orders(self, orders, names):
        self.orders   = orders
        self.names    = names
        self.idx      = 0
        self.sel_idx  = 0
        self._set_status('')
        if not orders:
            self._set_status('No personal orders found.')
            return
        self._load_market()

    # ── Load market ───────────────────────────────────────────────────────────

    def _load_market(self):
        self.mkt = None
        self._render_nav()
        self._clear_prices()
        self._show_mkt_msg('Fetching market…')
        o = self.orders[self.idx]

        def worker():
            try:
                data           = fetch_market(o['region_id'], o['type_id'], self.mkt_cache)
                prices, scope  = top3_prices(o, data)
                self.root.after(0, lambda: self._on_market(prices, scope))
            except Exception as e:
                self.root.after(0, lambda: self._show_mkt_msg(f'Market error: {e}'))

        threading.Thread(target=worker, daemon=True).start()

    def _on_market(self, prices, scope):
        self.mkt     = {'prices': prices, 'scope': scope}
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
        self.orders    = []
        self._clear_prices()
        self._load_orders()

    # ── Copy ──────────────────────────────────────────────────────────────────

    def _copy(self):
        if not self.mkt or not self.mkt['prices']:
            return
        price = self.mkt['prices'][self.sel_idx]
        o     = self.orders[self.idx]
        val   = undercut_price(price, o['is_buy_order'])
        if val is None:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(f'{val:.2f}')
        self.btn_copy.config(text='✓', bg=GREEN)
        self.root.after(2500, lambda: self.btn_copy.config(text='Copy', bg=BLUE))

    # ── Render helpers ────────────────────────────────────────────────────────

    def _render_nav(self):
        if not self.orders:
            self.lbl_name.config(text='No orders')
            self.lbl_counter.config(text='')
            self.lbl_type.config(text='')
            self.lbl_your.config(text='—')
            return
        o      = self.orders[self.idx]
        name   = self.names.get(o['type_id'], f"#{o['type_id']}")
        is_buy = o['is_buy_order']
        self.lbl_name.config(text=name[:32])
        self.lbl_counter.config(text=f"{self.idx + 1}/{len(self.orders)}")
        self.lbl_your.config(text=fmt_isk(o['price']))
        if is_buy:
            self.lbl_type.config(text='BUY', bg='#0e2a0e', fg=GREEN)
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
            f   = self.price_frames[i]
            diff = price - o['price']
            bad  = (diff > 0) if is_buy else (diff < 0)
            row_bg   = BG3 if i == self.sel_idx else BG2
            diff_fg  = RED if bad else GREEN

            f.config(bg=row_bg)
            for w in f.winfo_children():
                try:
                    w.config(bg=row_bg)
                except tk.TclError:
                    pass

            self.lbl_prices[i].config(text=fmt_isk(price), bg=row_bg)
            self.lbl_diffs[i].config(text=fmt_diff(diff), fg=diff_fg, bg=row_bg)
            f.pack(fill='x', padx=5, pady=1)

        # Copy bar
        price = self.mkt['prices'][self.sel_idx]
        uc    = undercut_price(price, is_buy)
        lbl   = 'Outbid' if is_buy else 'Undercut'
        self.lbl_uc_lbl.config(text=f'{lbl} #{self.sel_idx + 1}:')
        self.lbl_uc_price.config(text=fmt_isk(uc) if uc else '—')

    def _set_status(self, msg):
        self.lbl_status.config(text=msg)


if __name__ == '__main__':
    EVEWidget()
