"""Local accounts and revocable server-side sessions. No default credentials."""
import hashlib
import hmac
import re
import secrets
import time

ITERATIONS = 600_000
SESSION_SECONDS = 8 * 3600
IDLE_SECONDS = 30 * 60
LOCK_SECONDS = 15 * 60


def normalize_username(value):
    value = value.strip().casefold()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_.@+-]{2,79}', value):
        raise ValueError('Usuario deve ter 3 a 80 caracteres: letras, numeros, . _ @ + -')
    return value


def password_hash(password):
    if not 12 <= len(password) <= 256:
        raise ValueError('Senha deve ter entre 12 e 256 caracteres')
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return f'pbkdf2_sha256${ITERATIONS}${salt}${digest}'


def verify_password(password, encoded):
    try:
        kind, rounds, salt, expected = encoded.split('$')
        if kind != 'pbkdf2_sha256' or not 100_000 <= int(rounds) <= 1_000_000:
            return False
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(rounds)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


DUMMY_HASH = password_hash(secrets.token_urlsafe(32))


class Auth:
    def __init__(self, store):
        self.store = store
        with store.db() as c:
            c.executescript('''
                CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY, password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('admin','reader')), active INTEGER NOT NULL DEFAULT 1, email TEXT);
                CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, username TEXT NOT NULL,
                    csrf TEXT NOT NULL, expires REAL NOT NULL, last_seen REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS password_resets(token_hash TEXT PRIMARY KEY, username TEXT NOT NULL,
                    expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS login_limits(key TEXT PRIMARY KEY, attempts INTEGER NOT NULL,
                    until_time REAL NOT NULL);
            ''')

            if 'email' not in {row['name'] for row in c.execute('PRAGMA table_info(users)')}:
                c.execute('ALTER TABLE users ADD COLUMN email TEXT')

    def create_user(self, username, password, role='reader', email=None):
        username = normalize_username(username)
        if role not in {'admin', 'reader'}:
            raise ValueError('Perfil invalido')
        if email and (not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or len(email)>254):
            raise ValueError('Email invalido')
        encoded = password_hash(password)
        with self.store.db() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('INSERT INTO users(username,password_hash,role,email) VALUES(?,?,?,?)', (username,encoded,role,email))
            self.store._audit(c, {'action':'criar_usuario','actor':'administracao_local','user':username,'result':'confirmado'})
        return username

    def reset_password(self, username, password):
        username = normalize_username(username); encoded = password_hash(password)
        with self.store.db() as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute('UPDATE users SET password_hash=? WHERE username=?',(encoded,username)).rowcount != 1:
                raise ValueError('Usuario inexistente')
            c.execute('DELETE FROM sessions WHERE username=?',(username,))
            c.execute('DELETE FROM password_resets WHERE username=?',(username,))
            c.execute('DELETE FROM login_limits WHERE key=?',('user:'+username,))
            self.store._audit(c, {'action':'redefinir_senha','actor':'administracao_local','user':username,'result':'confirmado'})

    def login(self, username, password, client):
        try: username = normalize_username(username)
        except ValueError: username = 'invalid-' + hashlib.sha256(username.encode()).hexdigest()
        stamp = time.time(); keys = ['user:'+username, 'client:'+client]
        with self.store.db() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('DELETE FROM login_limits WHERE until_time<=?',(stamp,))
            c.execute('DELETE FROM sessions WHERE expires<=? OR last_seen<=?',(stamp,stamp-IDLE_SECONDS))
            for key in keys:
                row=c.execute('SELECT attempts FROM login_limits WHERE key=?',(key,)).fetchone()
                if row and row[0]>=5: return None, 'limited'
            for key in keys:
                c.execute('INSERT INTO login_limits VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET attempts=attempts+1', (key,stamp+LOCK_SECONDS))
            user=c.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
        good=verify_password(password,user['password_hash'] if user else DUMMY_HASH)
        if not good or not user or not user['active']:
            self.store.event(action='login',result='recusado')
            return None,'invalid'
        token=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(32)
        with self.store.db() as c:
            c.execute('BEGIN IMMEDIATE')
            # Prevent a concurrent administrative reset from retaining old credentials.
            current=c.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
            if not current or not current['active'] or current['password_hash']!=user['password_hash']:
                return None,'invalid'
            c.executemany('DELETE FROM login_limits WHERE key=?',[(k,) for k in keys])
            c.execute('INSERT INTO sessions VALUES(?,?,?,?,?)', (hashlib.sha256(token.encode()).hexdigest(),username,csrf,stamp+SESSION_SECONDS,stamp))
            self.store._audit(c, {'action':'login','actor':username,'result':'confirmado'})
        return {'token':token,'csrf':csrf,'username':username,'role':user['role']},None

    def session(self, token):
        if not token or len(token)>128: return None
        digest=hashlib.sha256(token.encode()).hexdigest();stamp=time.time()
        with self.store.db() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT sessions.*,users.role,users.active FROM sessions JOIN users USING(username) WHERE token_hash=?',(digest,)).fetchone()
            if not row: return None
            if not row['active'] or row['expires']<=stamp or row['last_seen']<=stamp-IDLE_SECONDS:
                c.execute('DELETE FROM sessions WHERE token_hash=?',(digest,));return None
            c.execute('UPDATE sessions SET last_seen=? WHERE token_hash=?',(stamp,digest))
            return {'username':row['username'],'role':row['role'],'csrf':row['csrf']}

    def logout(self, token, username):
        with self.store.db() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),))
            self.store._audit(c, {'action':'logout','actor':username,'result':'confirmado'})


    def request_reset(self, username, client):
        try: username=normalize_username(username)
        except ValueError: username='invalid'
        stamp=time.time()
        with self.store.db() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('DELETE FROM login_limits WHERE until_time<=?',(stamp,))
            for key in ['reset-client:'+client,'reset-user:'+username]:
                row=c.execute('SELECT attempts FROM login_limits WHERE key=?',(key,)).fetchone()
                if row and row[0]>=3:return None
            for key in ['reset-client:'+client,'reset-user:'+username]:
                c.execute('INSERT INTO login_limits VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET attempts=attempts+1',(key,stamp+LOCK_SECONDS))
            user=c.execute('SELECT * FROM users WHERE username=? AND active=1',(username,)).fetchone()
            if not user or not user['email']:return None
            token=secrets.token_urlsafe(32)
            c.execute('DELETE FROM password_resets WHERE expires<=?',(stamp,))
            c.execute('INSERT INTO password_resets VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),username,stamp+1800))
            return {'token':token,'email':user['email'],'username':username}

    def discard_reset(self, token):
        with self.store.db() as c:
            c.execute('DELETE FROM password_resets WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),))

    def consume_reset(self, token, password):
        if not token or len(token)>128:raise ValueError('Link invalido ou expirado')
        digest=hashlib.sha256(token.encode()).hexdigest()
        with self.store.db() as c:
            row=c.execute('SELECT expires FROM password_resets WHERE token_hash=?',(digest,)).fetchone()
            if not row or row['expires']<=time.time():raise ValueError('Link invalido ou expirado')
        encoded=password_hash(password)
        with self.store.db() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT password_resets.* FROM password_resets JOIN users USING(username) WHERE token_hash=? AND active=1',(digest,)).fetchone()
            if not row or row['expires']<=time.time():raise ValueError('Link invalido ou expirado')
            username=row['username']
            c.execute('UPDATE users SET password_hash=? WHERE username=?',(encoded,username))
            c.execute('DELETE FROM password_resets WHERE username=?',(username,))
            c.execute('DELETE FROM sessions WHERE username=?',(username,))
            c.execute('DELETE FROM login_limits WHERE key=?',('user:'+username,))
            self.store._audit(c,{'action':'redefinir_senha_por_email','actor':username,'result':'confirmado'})
