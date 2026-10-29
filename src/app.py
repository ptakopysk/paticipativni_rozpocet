"""Participatory budgeting, standard-library CGI application (Python 3.9+)."""
import base64
import fcntl
import hashlib
import hmac
import html
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import time
from http.cookies import SimpleCookie
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parent.parent
STORE = Path(os.environ.get('BUDGET_STORAGE', str(ROOT / 'storage')))


def escape(value):
    return html.escape(str(value), quote=True)


def initial():
    return {'revision': secrets.token_hex(16), 'items': [], 'votes': {}}


def transaction(callback, write=False):
    with (STORE / 'state.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX if write else fcntl.LOCK_SH)
        path = STORE / 'state.json'
        data = json.loads(path.read_text()) if path.exists() else initial()
        result = callback(data)
        if write:
            fd, name = tempfile.mkstemp(dir=STORE, prefix='state-')
            try:
                with os.fdopen(fd, 'w') as out:
                    json.dump(data, out, ensure_ascii=False)
                    out.flush()
                    os.fsync(out.fileno())
                os.replace(name, path)
            finally:
                if os.path.exists(name):
                    os.unlink(name)
        return result


def sign(secret, value):
    return hmac.new(secret, value.encode(), hashlib.sha256).hexdigest()


def verify_password(password, config):
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(config['salt']), 600000).hex()
    return hmac.compare_digest(digest, config['password'])


def page(title, body, kind=''):
    return f'''<!doctype html><html lang="cs"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)} · Společný rozpočet</title><link rel="stylesheet" href="assets/style.css"><script src="assets/app.js" defer></script></head><body class="{kind}"><header><a class="brand" href="index.cgi"><span class="brand-icon">↗</span> Společný rozpočet</a><nav aria-label="Hlavní navigace"><a href="index.cgi">Hlasování</a><a href="results.cgi">Výsledky</a><a href="admin.cgi">Správa</a></nav></header><main>{body}</main><footer>Participativní rozpočet <span>Společně rozhodujeme o tom, co má smysl.</span></footer></body></html>'''


def hidden(name, value):
    return f'<input type="hidden" name="{name}" value="{escape(value)}">'


def vote_page(data, voter, csrf):
    intro = '<section class="intro"><p class="eyebrow">VAŠE MĚSTO. VAŠE ROZHODNUTÍ.</p><h1>Kam pošleme<br><span>4 miliony eur?</span></h1><p class="lead">Vyberte, co je pro vás důležité. Rozdělte společný rozpočet mezi projekty a pomozte určit naše priority.</p></section>'
    if voter in data['votes']:
        return intro + '<section class="panel success"><span class="success-icon">✓</span><h2>Děkujeme za váš hlas.</h2><p>Vaše rozdělení rozpočtu je započítané.</p><a class="button" href="results.cgi">Zobrazit výsledky ↗</a></section>'
    if not data['items']:
        return intro + '<section class="panel"><h2>Projekty se připravují</h2><p>Jakmile správce zadá položky rozpočtu, můžete začít hlasovat.</p></section>'
    projects = ''
    for i, item in enumerate(data['items']):
        projects += f'''<article class="project panel"><div class="project-top"><span class="project-number">{i+1:02}</span><label for="item-{i}">{escape(item)}</label><output for="item-{i}" id="value-{i}">0 <small>mil. EUR</small></output></div><input type="range" id="item-{i}" name="amount-{i}" min="0" max="4" step="1" value="0" aria-describedby="range-help"><div class="range-labels"><span>0 EUR</span><span>4 mil. EUR</span></div></article>'''
    return intro + f'''<form id="vote-form" class="vote-layout" action="api.cgi" method="post">{hidden('csrf', csrf)}{hidden('revision', data['revision'])}<section class="projects"><div class="section-heading"><h2>Na čem vám záleží?</h2><span>{len(data['items'])} projektů</span></div>{projects}<p class="hint" id="range-help">Každý krok představuje 1 milion EUR. Posuňte jezdec nebo použijte šipky na klávesnici.</p></section><aside class="panel budget"><p class="eyebrow">VÁŠ ROZPOČET</p><div class="budget-amount">4 000 000 <span>EUR</span></div><div class="budget-track"><div id="budget-fill"></div></div><div class="budget-line"><span>Rozděleno</span><strong id="allocated">0 mil. EUR</strong></div><div class="budget-line remaining"><span>Zbývá rozdělit</span><strong id="remaining">4 mil. EUR</strong></div><p id="budget-status" role="status" aria-live="polite">Rozdělte ještě 4 mil. EUR.</p><button type="submit" id="submit-vote" disabled>Odeslat můj hlas ↗</button><p class="hint">Hlas lze z tohoto prohlížeče odevzdat jednou za kolo.</p><p id="vote-error" class="error" role="alert"></p></aside></form>'''


def results_page():
    return '''<section class="results-intro"><div><p class="eyebrow">SPOLEČNĚ TVOŘÍME PRIORITY</p><h1>Takto rozhodujeme.</h1><p class="lead">Součet rozpočtů všech účastníků v aktuálním kole.</p></div><button class="secondary" id="fullscreen">Celá obrazovka ⛶</button></section><div class="result-stats"><div class="panel"><span>Odevzdaných hlasů</span><strong id="vote-count">—</strong></div><div class="panel"><span>Celkem rozděleno</span><strong id="total-money">—</strong></div><div class="live"><span class="live-dot"></span><span id="live-status" role="status">Načítám výsledky…</span></div></div><section id="results" class="results-list" aria-label="Výsledky projektů"></section><p class="hint">Částky jsou součtem hlasů. Podíl ukazuje část ze všech rozdělených prostředků.</p>'''


def admin_page(data, csrf, admin, message='', error=''):
    body = '<section class="intro compact"><p class="eyebrow">ADMINISTRACE</p><h1>Připravte společný rozpočet.</h1><p class="lead">Zadejte projekty a otevřete prostor pro společné rozhodování.</p></section>'
    if message:
        body += f'<p class="notice" role="status">{escape(message)}</p>'
    if error:
        body += f'<p class="notice error" role="alert">{escape(error)}</p>'
    fields = hidden('csrf', csrf)
    if not admin:
        return body + f'<form method="post" class="panel admin-panel">{fields}<h2>Přihlášení správce</h2><label for="password">Heslo</label><input id="password" type="password" name="password" required autocomplete="current-password"><button name="action" value="login">Přihlásit se ↗</button></form>'
    items = escape('\n'.join(data['items']))
    return body + f'''<form method="post" class="panel admin-panel" id="admin-form">{fields}<div class="section-heading"><h2>Položky rozpočtu</h2><span>{len(data['votes'])} hlasů</span></div><label for="items">Jeden projekt na každý řádek</label><textarea name="items" id="items" rows="10" required placeholder="Zeleň a parky&#10;Bezpečné cyklostezky&#10;Kultura a komunitní život">{items}</textarea><p class="hint">Nejvýše 50 projektů. Po prvním hlasu lze položky změnit pouze zahájením nového kola. Nové kolo vymaže všechny hlasy. Předem případně zazálohujte storage/state.json.</p><button name="action" value="save">Uložit položky ↗</button><button class="danger" name="action" value="reset" id="reset-round">Vymazat hlasy a zahájit nové kolo</button></form><form method="post" class="logout">{fields}<button class="secondary" name="action" value="logout">Odhlásit se</button></form>'''


def run(route):
    headers = []
    status = '200 OK'
    mime = 'application/json' if route == 'api' else 'text/html'
    try:
        config = json.loads((STORE / 'config.json').read_text())
        secret = bytes.fromhex(config['secret'])
        cookies = SimpleCookie()
        try:
            cookies.load(os.environ.get('HTTP_COOKIE', ''))
        except Exception:
            pass
        token = cookies['budget_voter'].value if 'budget_voter' in cookies else ''
        parts = token.split('.')
        if len(parts) != 2 or len(parts[0]) != 64 or not hmac.compare_digest(sign(secret, 'voter:' + parts[0]), parts[1]):
            voter = secrets.token_hex(32)
            token = voter + '.' + sign(secret, 'voter:' + voter)
        else:
            voter = parts[0]
        secure = '; Secure' if os.environ.get('HTTPS', '').lower() in ('on', '1') else ''
        cookie_path = os.environ.get('SCRIPT_NAME', '/index.cgi').rsplit('/', 1)[0] + '/'
        def set_cookie(name, value, age):
            headers.append(('Set-Cookie', f'{name}={value}; Path={cookie_path}; Max-Age={age}; HttpOnly; SameSite=Lax{secure}'))
        set_cookie('budget_voter', token, 31536000)
        csrf = sign(secret, 'csrf:' + voter)
        admin_token = cookies['budget_admin'].value if 'budget_admin' in cookies else ''
        admin_parts = admin_token.split('.')
        admin = len(admin_parts) == 2 and admin_parts[0].isdigit() and int(admin_parts[0]) > time.time() and hmac.compare_digest(sign(secret, 'admin:' + voter + ':' + admin_parts[0]), admin_parts[1])
        method = os.environ.get('REQUEST_METHOD', 'GET')
        if method not in ('GET', 'POST'):
            raise ValueError('Nepodporovaná metoda.')
        form = {}
        if method == 'POST':
            length = int(os.environ.get('CONTENT_LENGTH', '0') or '0')
            if length < 0 or length > 32768:
                raise ValueError('Formulář je příliš velký.')
            form = parse_qs(sys.stdin.buffer.read(length).decode('utf-8'), keep_blank_values=True, max_num_fields=100)
            if any(len(values) != 1 for values in form.values()):
                raise ValueError('Neplatný formulář.')
            form = {key: values[0] for key, values in form.items()}
            if not hmac.compare_digest(csrf, form.get('csrf', '')):
                raise ValueError('Platnost formuláře vypršela. Obnovte stránku a povolte cookies.')
        message = ''
        error = ''
        if route == 'admin' and method == 'POST':
            action = form.get('action')
            if action == 'login':
                if not verify_password(form.get('password', ''), config):
                    time.sleep(1)
                    error = 'Nesprávné heslo.'
                else:
                    expiry = str(int(time.time()) + 28800)
                    set_cookie('budget_admin', expiry + '.' + sign(secret, 'admin:' + voter + ':' + expiry), 28800)
                    admin = True
            elif action == 'logout':
                set_cookie('budget_admin', '', 0)
                admin = False
            elif admin and action in ('save', 'reset'):
                try:
                    items = [line.strip() for line in form.get('items', '').splitlines() if line.strip()]
                    if not 1 <= len(items) <= 50 or any(len(item) > 150 for item in items) or len(set(items)) != len(items):
                        raise ValueError('Zadejte 1 až 50 různých projektů, každý do 150 znaků na samostatném řádku.')
                    def save(data):
                        if data['votes'] and action != 'reset' and items != data['items']:
                            raise ValueError('Po začátku hlasování změňte položky zahájením nového kola.')
                        if action == 'reset' or items != data['items']:
                            data.update(initial())
                            data['items'] = items
                    transaction(save, True)
                    message = 'Nové kolo bylo zahájeno. Předchozí hlasy byly vymazány.' if action == 'reset' else 'Položky byly uloženy.'
                except ValueError as exc:
                    error = str(exc)
            else:
                raise ValueError('Nejprve se přihlaste.')
        if route == 'api':
            if method == 'POST':
                def vote(data):
                    if data['revision'] != form.get('revision'):
                        raise ValueError('Hlasovací kolo se změnilo. Obnovte stránku.')
                    if voter in data['votes']:
                        raise ValueError('Váš hlas už byl v tomto kole přijat.')
                    keys = {'amount-' + str(i) for i in range(len(data['items']))}
                    if not keys or {k for k in form if k.startswith('amount-')} != keys:
                        raise ValueError('Neplatný seznam projektů.')
                    values = [form['amount-' + str(i)] for i in range(len(data['items']))]
                    if any(v not in ('0', '1', '2', '3', '4') for v in values):
                        raise ValueError('Částky musí být celé miliony od 0 do 4.')
                    amounts = list(map(int, values))
                    if sum(amounts) != 4:
                        raise ValueError('Rozdělte přesně 4 miliony EUR.')
                    data['votes'][voter] = amounts
                transaction(vote, True)
                result = {'ok': True}
            else:
                def totals(data):
                    amounts = [sum(v[i] for v in data['votes'].values()) for i in range(len(data['items']))]
                    return {'items': data['items'], 'totals': amounts, 'count': len(data['votes'])}
                result = transaction(totals)
            body = json.dumps(result, ensure_ascii=False)
        else:
            data = transaction(lambda d: d)
            content = admin_page(data, csrf, admin, message, error) if route == 'admin' else results_page() if route == 'results' else vote_page(data, voter, csrf)
            body = page({'admin': 'Správa rozpočtu', 'results': 'Živé výsledky', 'index': 'Rozdělte rozpočet'}[route], content, 'results-page' if route == 'results' else '')
    except ValueError as exc:
        status = '400 Bad Request'
        body = json.dumps({'error': str(exc)}, ensure_ascii=False) if route == 'api' else page('Chyba', f'<p class="notice error">{escape(exc)}</p><a href="index.cgi">Zpět na hlasování</a>')
    except Exception as exc:
        print(f'Budget CGI error: {exc}', file=sys.stderr)
        status = '503 Service Unavailable'
        message = 'Aplikace není připravena. Správce musí spustit python3 bin/setup.py a ověřit práva úložiště.'
        body = json.dumps({'error': message}, ensure_ascii=False) if route == 'api' else page('Nedostupné', f'<p class="notice error">{message}</p>')
    headers.extend([('Status', status), ('Content-Type', mime + '; charset=utf-8'), ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff'), ('Referrer-Policy', 'same-origin'), ('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")])
    output = ''.join(f'{key}: {value}\r\n' for key, value in headers) + '\r\n' + body
    sys.stdout.buffer.write(output.encode('utf-8'))
