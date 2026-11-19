import re, json, secrets, hashlib, os
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from datetime import date
from pathlib import Path
from http.cookies import SimpleCookie

ROOT = Path(__file__).parent
DATA_DIR = Path(os.environ.get('WORKOUTPLAN_DATA_DIR', ROOT / 'data'))
SESSIONS = {}
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    raise RuntimeError('DATABASE_URL is required for PostgreSQL')

import postgres_backend
from rich_text import validate_instruction

INTEGRITY_ERRORS = (postgres_backend.psycopg.IntegrityError,)


def connect():
    return postgres_backend.connect(DATABASE_URL)


PROMO_CODE_PATTERN = re.compile(r'[DFGJNQRSUVWZ23456789]{5}', re.ASCII | re.IGNORECASE)


def normalize_promo_code(value, optional=False):
    if isinstance(value, str):
        value = value.strip()
        if optional and not value:
            return ''
        if PROMO_CODE_PATTERN.fullmatch(value):
            return value.upper()
    raise ValueError('Введите промокод из пяти допустимых символов')


def password(value, salt):
    return hashlib.pbkdf2_hmac('sha256', value.encode(), salt.encode(), 200000).hex()
def save_coach_bio(db, user_id, body):
    if 'bio' not in body:
        return
    bio = body['bio']
    cleaned = {}
    for key in ('education', 'achievements', 'specializations'):
        items = bio.get(key, [])
        if not isinstance(items, list) or len(items) > 50 or any(
            not isinstance(item, str) or len(item) > 1000 for item in items
        ):
            raise ValueError('До 50 пунктов в каждом списке, до 1000 символов на пункт')
        cleaned[key] = [item.strip() for item in items if item.strip()]
    db.execute('UPDATE users SET coach_bio=? WHERE id=?', (json.dumps(cleaned), user_id))


LOCATION_KEY = secrets.token_bytes(32)

def city_query(query):
    from urllib.request import Request, urlopen
    key = os.environ.get('DADATA_API_KEY', '').strip()
    if not key:
        config = ROOT.parent / 'WebCollector' / 'Config' / '.env'
        if config.is_file():
            for line in config.read_text(encoding='utf-8-sig').splitlines():
                name, separator, value = line.partition('=')
                if separator and name.strip() == 'DADATA_API_KEY':
                    key = value.strip()
                    break
    key_file = DATA_DIR / 'dadata-api-key.txt'
    if not key and key_file.is_file():
        key = key_file.read_text(encoding='utf-8-sig').strip()
    if not key or len(query) < 2:
        return []
    import hmac
    language = 'en' if re.search(r'[a-zA-Z]', query) and not re.search(r'[А-Яа-яЁё]', query) else 'ru'
    request = Request(
        'https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/address',
        data=json.dumps({'query': query, 'count': 15, 'language': language,
                         'locations': [{'country': '*'}],
                         'from_bound': {'value': 'city'}, 'to_bound': {'value': 'settlement'}}).encode(),
        headers={'Authorization': 'Token ' + key, 'Content-Type': 'application/json'})
    with urlopen(request, timeout=4) as response:
        suggestions = json.load(response)['suggestions']
    results = {}
    for item in suggestions:
        data = item['data']
        city = data.get('settlement') or data.get('city')
        country = data.get('country')
        if not city or not country:
            continue
        location = {'country':country, 'code':data.get('country_iso_code'),
                    'region':data.get('region_with_type') or data.get('region'),
                    'city':city, 'id':data.get('fias_id') or data.get('geoname_id')}
        payload = json.dumps(location, ensure_ascii=False)
        token = hmac.digest(LOCATION_KEY, payload.encode(), 'sha256').hex() + ':' + payload
        label = country + ', ' + city
        if location['region'] and location['region'].casefold() != city.casefold():
            label += ' · ' + location['region']
        results.setdefault(label, token)
    return [{'label':label, 'token':token} for label,token in results.items()]


def audit_action(db, uid, role, module, subsection, action, entity, description):
    db.execute("""
        INSERT INTO audit_events(actor_id,actor_role,module,subsection,action,entity,description)
        VALUES(?,?,?,?,?,?,?)
    """, (uid, role, module, subsection, action, entity, description))


def init():
    with connect() as connection:
        postgres_backend.initialize(connection)


class Handler(BaseHTTPRequestHandler):
    def send_error(self, code, message=None, explain=None):
        if code != 404:
            return super().send_error(code, message, explain)
        raw = (ROOT / 'web' / '404.html').read_bytes()
        self.send_response(404)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
    def respond(self,code,data,cookie=None):
        raw=json.dumps(data,ensure_ascii=False).encode(); self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store')
        if cookie:self.send_header('Set-Cookie',cookie)
        self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        from urllib.parse import parse_qs, urlsplit
        url = urlsplit(self.path)
        self.query = parse_qs(url.query)
        self.path = url.path
        if self.path.startswith('/api/'):return self.api('GET')
        if re.fullmatch(r'/uploads/(?:(?:admin|coach|user)/[0-9]{4}/[0-9]{2}/[0-9]{2}/)?[a-f0-9]{32}[.](jpg|png|webp|mp4|webm)', self.path):
            path = DATA_DIR / 'uploads' / self.path.removeprefix('/uploads/')
            if not path.is_file():
                return self.send_error(404)
            import mimetypes, shutil
            self.send_response(200)
            self.send_header('Content-Type', mimetypes.guess_type(path.name)[0])
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Length', str(path.stat().st_size))
            self.end_headers()
            with path.open('rb') as source:
                shutil.copyfileobj(source, self.wfile)
            return
        path=ROOT/'web'/('index.html' if self.path=='/' else self.path.lstrip('/'))
        vendor_asset = self.path in ('/vendor/quill/quill.js', '/vendor/quill/quill.snow.css')
        if (path.parent != ROOT/'web' and not vendor_asset) or not path.is_file():self.send_error(404);return
        self.send_response(200);self.send_header('Content-Type',{'html':'text/html; charset=utf-8','css':'text/css','js':'text/javascript; charset=utf-8'}.get(path.suffix[1:],'text/plain'));self.end_headers();self.wfile.write(path.read_bytes())
    def do_POST(self):
        if self.path != '/api/upload':
            return self.api('POST')
        cookie = SimpleCookie(self.headers.get('Cookie', '')).get('session')
        uid = SESSIONS.get(cookie.value) if cookie else None
        with connect() as db:
            user = db.execute('SELECT role FROM users WHERE id=? AND is_del=0', (uid,)).fetchone()
        if not user or user['role'] not in ('coach','user','admin'):
            return self.respond(403, {'error': 'Upload forbidden'})
        suffix = {'image/jpeg':'jpg','image/png':'png','image/webp':'webp',
                  'video/mp4':'mp4','video/webm':'webm'}.get(self.headers.get_content_type())
        size = int(self.headers.get('Content-Length', '0'))
        if not suffix or not 0 < size <= 50 * 1024 * 1024:
            return self.respond(400, {'error': 'Unsupported file or size over 50 MB'})
        raw = self.rfile.read(size)
        valid = {'jpg':raw.startswith(bytes.fromhex('ffd8ff')),
                 'png':raw.startswith(bytes.fromhex('89504e470d0a1a0a')),
                 'webp':raw[:4]==b'RIFF' and raw[8:12]==b'WEBP',
                 'mp4':raw[4:8]==b'ftyp',
                 'webm':raw.startswith(bytes.fromhex('1a45dfa3'))}
        if len(raw) != size or not valid[suffix]:
            return self.respond(400, {'error': 'Invalid file content'})
        from datetime import datetime, timedelta, timezone
        day = datetime.now(timezone(timedelta(hours=3))).strftime('%Y/%m/%d')
        relative_folder = f"{user['role']}/{day}"
        folder = DATA_DIR / 'uploads' / relative_folder
        folder.mkdir(parents=True, exist_ok=True)
        name = secrets.token_hex(16) + '.' + suffix
        file = folder / name
        try:
            with connect() as db:
                file.write_bytes(raw)
                audit_action(db, uid, user['role'], 'Файлы', 'Загрузки', 'upload', 'file',
                             f'Загружен файл {suffix.upper()}, {size} байт')
        except Exception:
            file.unlink(missing_ok=True)
            raise
        return self.respond(200, {'url': f'/uploads/{relative_folder}/{name}'})
    def api(self,method):
        try:
            size=int(self.headers.get('Content-Length',0))
            if size>200000: return self.respond(413,{'error':'Слишком большой запрос'})
            body=json.loads(self.rfile.read(size)) if size else {}
            cookies=SimpleCookie(self.headers.get('Cookie','')); token=cookies.get('session'); uid=SESSIONS.get(token.value) if token else None
            with connect() as c:
                if self.path=='/api/login':
                    u=c.execute('SELECT * FROM users WHERE email=? AND is_del=0',(body.get('email'),)).fetchone()
                    if not u or not secrets.compare_digest(u['hash'],password(body.get('password',''),u['salt'])):return self.respond(401,{'error':'Неверная почта или пароль'})
                    audit_action(c, u['id'], u['role'], 'Учётная запись', 'Сессия', 'login', 'session', 'Вход выполнен')
                    c.commit()
                    t=secrets.token_hex(32);SESSIONS[t]=u['id'];return self.respond(200,{'ok':True},f'session={t}; HttpOnly; SameSite=Strict; Path=/')
                if self.path == '/api/email-confirm' and method == 'POST':
                    token = body.get('token')
                    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
                        return self.respond(400, {'error':'Ссылка недействительна или устарела'})
                    digest = hashlib.sha256(token.encode()).hexdigest()
                    account = c.execute("""
                        SELECT u.id,u.role FROM users u JOIN email_verifications v ON v.user_id=u.id
                        WHERE v.token_hash=? AND v.expires_at>CURRENT_TIMESTAMP AND u.is_del=0
                        FOR UPDATE OF u
                    """, (digest,)).fetchone()
                    if not account or not c.execute("""
                        DELETE FROM email_verifications WHERE user_id=? AND token_hash=?
                        AND expires_at>CURRENT_TIMESTAMP RETURNING user_id
                    """, (account['id'],digest)).fetchone():
                        return self.respond(400, {'error':'Ссылка недействительна или устарела'})
                    c.execute('UPDATE users SET email_verified_at=CURRENT_TIMESTAMP WHERE id=?', (account['id'],))
                    audit_action(c, account['id'], account['role'], 'Мой профиль', 'Личные сведения',
                                 'email_confirm', 'users', 'Почта подтверждена по одноразовой ссылке')
                    c.commit()
                    return self.respond(200, {'ok':True})
                if self.path == '/api/register' and method == 'POST':
                    role = body.get('role')
                    if role not in ('user', 'coach'):
                        raise ValueError('Выберите роль клиента или тренера')
                    values = [body.get(key, '') for key in ('email','surname','given_name','phone','password')]
                    if not all(isinstance(value, str) and chr(0) not in value for value in values):
                        raise ValueError('Проверьте поля регистрации')
                    email, surname, given, phone = (value.strip() for value in values[:4])
                    email = email.lower()
                    secret = values[4]
                    code = normalize_promo_code(body.get('code', ''), optional=True)
                    if not surname or not given or max(len(surname), len(given)) > 50:
                        raise ValueError('Укажите имя и фамилию')
                    if len(email) > 254 or email.endswith('@login.invalid') or not re.fullmatch(r'[^@\s]+@[^@\s]+[.][^@\s]+', email):
                        raise ValueError('Введите корректный email')
                    if phone and not re.fullmatch(r'[+][1-9][0-9]{6,14}', phone):
                        raise ValueError('Введите телефон в международном формате')
                    if not isinstance(secret, str) or not 8 <= len(secret) <= 128:
                        raise ValueError('Введите пароль от 8 до 128 символов')
                    if body.get('password_confirmation') != secret:
                        raise ValueError('Пароли не совпадают')
                    salt = secrets.token_hex(16)
                    digest = password(secret, salt)
                    if c.execute('SELECT 1 FROM users WHERE lower(email)=?', (email,)).fetchone():
                        return self.respond(409, {'error':'Этот email уже зарегистрирован'})
                    promo = None
                    if code:
                        promo = c.execute("""
                            SELECT p.id,p.owner_id,u.role FROM promo_codes p JOIN users u ON u.id=p.owner_id
                            WHERE p.code=? AND p.deleted_at IS NULL AND u.is_del=0
                            FOR SHARE OF p,u
                        """, (code,)).fetchone()
                        if not promo:
                            raise ValueError('Промокод не найден или больше не действует')
                    coach = promo['owner_id'] if promo and promo['role'] == 'coach' and role == 'user' else None
                    new_id = c.execute("""
                        INSERT INTO users(name,email,role,salt,hash,coach,surname,given_name,phone)
                        VALUES(?,?,?,?,?,?,?,?,?) RETURNING id
                    """, (f'{surname} {given}',email,role,salt,digest,coach,surname,given,phone)).fetchone()['id']
                    audit_action(c, new_id, role, 'Регистрация', 'Учётная запись', 'insert', 'users',
                                 f'Создан аккаунт ID {new_id}')
                    if promo:
                        c.execute('INSERT INTO promo_redemptions(user_id,promo_code_id) VALUES(?,?)', (new_id,promo['id']))
                        audit_action(c, new_id, role, 'Регистрация', 'Промокод', 'insert', 'promo_redemptions',
                                     f"Активирован промокод ID {promo['id']}")
                        c.execute("SELECT set_config('workoutplan.actor_id', ?, true), "
                                  "set_config('workoutplan.actor_role', ?, true)", (str(new_id),role))
                        c.execute('INSERT INTO star_awards(user_id,reason,amount) VALUES(?,?,5),(?,?,10)',
                                  (new_id,'promo_registration',promo['owner_id'],f'promo_invite_{new_id}'))
                    c.commit()
                    return self.respond(201, {'ok':True})
                if self.path == '/api/referral-check' and method == 'POST':
                    code = normalize_promo_code(body.get('code'))
                    active = c.execute("""
                        SELECT 1 FROM promo_codes p JOIN users u ON u.id=p.owner_id
                        WHERE p.code=? AND p.deleted_at IS NULL AND u.is_del=0
                    """, (code,)).fetchone()
                    return self.respond(200, {'valid': bool(active)})
                if not uid:return self.respond(401,{'error':'Войдите в аккаунт'})
                u=c.execute('SELECT id,name,email,role,coach,surname,given_name,patronymic,phone,profile_media,coach_bio FROM users WHERE id=? AND is_del=0',(uid,)).fetchone()
                if not u: return self.respond(401, {'error':'Войдите в аккаунт'})
                role=u['role']
                if role in ('user', 'coach'):
                    c.execute('UPDATE users SET last_activity_at=clock_timestamp() WHERE id=?', (uid,))
                if self.path == '/api/activity' and method == 'POST' and role in ('user', 'coach'):
                    c.commit()
                    return self.respond(200, {'ok':True})
                if method == 'POST':
                    c.execute("SELECT set_config('workoutplan.actor_id', ?, true), "
                              "set_config('workoutplan.actor_role', ?, true), "
                              "set_config('workoutplan.action_path', ?, true)",
                              (str(uid), role, self.path))
                if self.path == '/api/email-verification' and method == 'POST' and role in ('user','coach'):
                    from email_verification import send_verification
                    account = c.execute('SELECT email,email_verified_at FROM users WHERE id=? FOR UPDATE', (uid,)).fetchone()
                    email = account['email']
                    if not email or email.endswith('@login.invalid'):
                        raise ValueError('Сначала сохраните адрес электронной почты')
                    if account['email_verified_at']:
                        raise ValueError('Почта уже подтверждена')
                    if c.execute("SELECT 1 FROM email_verifications WHERE user_id=? AND expires_at>CURRENT_TIMESTAMP + INTERVAL '23 hours 59 minutes'", (uid,)).fetchone():
                        return self.respond(429, {'error':'Повторно отправить письмо можно через минуту'})
                    token = secrets.token_urlsafe(32)
                    c.execute("""
                        INSERT INTO email_verifications(user_id,token_hash,expires_at)
                        VALUES(?,?,CURRENT_TIMESTAMP + INTERVAL '24 hours')
                        ON CONFLICT(user_id) DO UPDATE SET token_hash=excluded.token_hash,expires_at=excluded.expires_at
                    """, (uid,hashlib.sha256(token.encode()).hexdigest()))
                    try:
                        send_verification(email, token)
                    except RuntimeError as error:
                        c.rollback()
                        return self.respond(503, {'error':str(error)})
                    audit_action(c, uid, role, 'Мой профиль', 'Личные сведения',
                                 'email_verification_sent', 'users', 'Отправлена ссылка подтверждения почты')
                    c.commit()
                    return self.respond(200, {'ok':True})

                if self.path == '/api/star-history' and method == 'GET':
                    if role not in ('user', 'coach'):
                        return self.respond(403, {'error':'Нет доступа'})
                    rows = c.execute("""
                        SELECT id, reason, amount, awarded_at::text AS awarded_at
                        FROM star_awards WHERE user_id=? ORDER BY awarded_at DESC, id DESC
                    """, (uid,))
                    return self.respond(200, [dict(row) for row in rows])

                if self.path == '/api/body-measurements':
                    if role != 'user':
                        return self.respond(403, {'error':'Нет доступа'})
                    if method == 'GET':
                        rows = c.execute("""
                            SELECT id, measured_on::text AS measured_on, measurements
                            FROM body_measurements WHERE client_id=? ORDER BY measured_on DESC
                        """, (uid,))
                        return self.respond(200, [dict(row) for row in rows])
                    from datetime import datetime
                    from datetime import timezone, timedelta
                    today = datetime.now(timezone(timedelta(hours=3))).date()
                    raw_date = body.get('measured_on')
                    if not isinstance(raw_date, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', raw_date):
                        raise ValueError('Укажите дату замера')
                    measured_on = date.fromisoformat(raw_date)
                    if measured_on > today:
                        raise ValueError('Дата замера не может быть в будущем')
                    values = body.get('measurements')
                    allowed = {'neck','chest','waist','abdomen','hips','shoulders','underbust'}
                    allowed.update(f'{part}_{side}' for part in ('arm','thigh','calf','forearm','wrist','knee','ankle') for side in ('left','right'))
                    if not isinstance(values, dict) or not values or values.keys() - allowed or any(
                        type(value) not in (int, float) or not 0 < value <= 500 or round(value, 1) != value
                        for value in values.values()
                    ):
                        raise ValueError('Введите хотя бы один обхват от 0,1 до 500 см, с точностью до 0,1 см')
                    entry = body.get('id')
                    if entry is None:
                        if not c.execute("""
                            INSERT INTO body_measurements(client_id,measured_on,measurements)
                            VALUES(?,?,?::jsonb) ON CONFLICT(client_id,measured_on) DO NOTHING RETURNING id
                        """, (uid, measured_on, json.dumps(values))).fetchone():
                            return self.respond(409, {'error':'За эту дату уже есть замеры. Откройте их для редактирования.'})
                    else:
                        if type(entry) is not int or not 1 <= entry <= 2147483647:
                            raise ValueError('Неверный номер записи')
                        previous = c.execute("""
                            SELECT measured_on FROM body_measurements WHERE id=? AND client_id=? FOR UPDATE
                        """, (entry, uid)).fetchone()
                        if not previous:
                            return self.respond(404, {'error':'Замеры не найдены'})
                        if previous['measured_on'] != measured_on:
                            raise ValueError('Дата сохранённой записи не меняется')
                        c.execute('UPDATE body_measurements SET measurements=?::jsonb WHERE id=? AND client_id=?',
                                  (json.dumps(values), entry, uid))
                    c.commit()
                    return self.respond(200, {'ok':True})
                if method == 'GET' and self.path == '/api/geography':
                    query = self.query.get('q', [''])[0].strip()[:100]
                    try:
                        return self.respond(200, city_query(query))
                    except OSError:
                        return self.respond(503, {'error':'Подсказки городов временно недоступны'})
                if self.path == '/api/state':
                    u.update(c.execute("""
                        SELECT profile_location, communication_languages, email_verified_at IS NOT NULL AS email_verified,
                               birth_date::text AS birth_date,
                               workoutplan_profile_points(users) AS profile_completion,
                               (SELECT coalesce(sum(amount), 0) FROM star_awards WHERE user_id=users.id) AS star_balance,
                               CASE WHEN last_activity_at >= CURRENT_TIMESTAMP - INTERVAL '10 minutes' THEN 'online'
                                    WHEN last_activity_at >= CURRENT_TIMESTAMP - INTERVAL '30 minutes' THEN 'recent'
                               END AS activity
                        FROM users WHERE id=?
                    """, (uid,)).fetchone())
                if self.path=='/api/logout':
                    audit_action(c, uid, role, 'Учётная запись', 'Сессия', 'logout', 'session', 'Выход выполнен')
                    c.commit()
                    SESSIONS.pop(token.value,None);return self.respond(200,{'ok':True},'session=; Max-Age=0; Path=/')
                if self.path == '/api/account-restore' and method == 'POST' and role == 'admin':
                    c.execute("UPDATE users SET is_del=0 WHERE id=? AND role='coach' AND is_del=1", (int(body['id']),))
                    c.commit()
                    return self.respond(200, {'ok':True})
                if self.path == '/api/account-delete' and method == 'POST' and role == 'admin':
                    c.execute("UPDATE users SET is_del=1 WHERE id=? AND role IN ('coach','user') AND is_del=0",
                              (int(body['id']),))
                    c.commit()
                    return self.respond(200, {'ok':True})
                if self.path=='/api/references':
                    if role != 'admin' and not (role == 'coach' and method == 'GET'):
                        return self.respond(403, {'error':'Нет доступа'})
                    if method == 'GET':
                        return self.respond(200, {
                            'groups':[dict(row) for row in c.execute('SELECT * FROM tag_groups ORDER BY id')],
                            'tags':[dict(row) for row in c.execute('SELECT id, group_id, name FROM tags WHERE archived_at IS NULL ORDER BY id')]})
                    name = body.get('name','').strip()
                    if body.get('action') == 'batch':
                        group = int(body['group'])
                        tags = body['tags']
                        existing = {row['id'] for row in c.execute('SELECT id FROM tags WHERE group_id=? AND archived_at IS NULL',(group,))}
                        names = [tag['name'].strip() for tag in tags]
                        if {tag['id'] for tag in tags} != existing or len(tags)!=len(existing) or any(not 1<=len(value)<=80 for value in names) or len({value.casefold() for value in names})!=len(names):
                            raise ValueError('Проверьте названия тегов или обновите справочник')
                        for tag, name in zip(tags,names):
                            c.execute('UPDATE tags SET name=? WHERE id=? AND group_id=? AND archived_at IS NULL',(name,tag['id'],group))
                        c.commit()
                        return self.respond(200, {'ok':True})
                    if body.get('action') == 'delete':
                        c.execute('UPDATE tags SET archived_at=CURRENT_TIMESTAMP WHERE id=? AND archived_at IS NULL',(int(body['id']),))
                    else:
                        group = int(body['group'])
                        if not 1 <= len(name) <= 80 or not c.execute('SELECT 1 FROM tag_groups WHERE id=?',(group,)).fetchone():
                            raise ValueError('Проверьте группу и название')
                        duplicate = any(row['name'].casefold()==name.casefold() and row['id']!=body.get('id') for row in c.execute('SELECT id,name FROM tags WHERE group_id=? AND archived_at IS NULL',(group,)))
                        if duplicate:
                            raise ValueError('Такой тег уже существует')
                        if body.get('id'):
                            c.execute('UPDATE tags SET name=? WHERE id=? AND group_id=? AND archived_at IS NULL',(name,int(body['id']),group))
                        else:
                            c.execute('INSERT INTO tags(group_id,name) VALUES(?,?)',(group,name))
                    c.commit()
                    return self.respond(200, {'ok':True})
                if self.path == '/api/audit-events' and method == 'GET':
                    if role != 'admin':
                        return self.respond(403, {'error':'Нет доступа'})
                    requested = max(1, int(self.query.get('page', ['1'])[0]))
                    page_size = 30
                    total = c.execute('SELECT count(*) FROM audit_events').fetchone()[0]
                    pages = max(1, (total + page_size - 1) // page_size)
                    current = min(requested, pages)
                    events = [dict(row) for row in c.execute("""
                        SELECT to_char(occurred_at AT TIME ZONE 'Europe/Moscow', 'DD.MM.YYYY HH24:MI:SS') AS occurred_local,
                               actor_id, actor_role, module, subsection, action, entity_id, description
                        FROM audit_events ORDER BY occurred_at DESC, id DESC LIMIT ? OFFSET ?
                    """, (page_size, (current - 1) * page_size))]
                    return self.respond(200, dict(events=events, page=current, pages=pages))
                if self.path == '/api/admin-dashboard' and method == 'GET':
                    if role != 'admin':
                        return self.respond(403, {'error':'Нет доступа'})
                    counts = {}
                    for account_role in ('coach', 'user'):
                        total = c.execute('SELECT COUNT(*) FROM users WHERE role=? AND is_del=0', (account_role,)).fetchone()[0]
                        changes = [
                            c.execute("SELECT COALESCE(SUM(delta),0) FROM account_count_events WHERE role=? AND occurred_at>=datetime('now',?)",
                                      (account_role, f'-{days} days')).fetchone()[0]
                            for days in (7, 30, 365)
                        ]
                        counts[account_role] = {'total':total, 'changes':changes}
                    started_at = c.execute('SELECT started_at FROM account_count_tracking').fetchone()[0]
                    return self.respond(200, {'counts':counts, 'started_at':started_at})
                if self.path in ('/api/clients', '/api/coaches') and method == 'GET':
                    coaches = self.path == '/api/coaches'
                    if (coaches and role not in ('admin', 'user')) or (not coaches and role not in ('admin', 'coach')):
                        return self.respond(403, {'error':'Нет доступа'})
                    page_value = self.query.get('page', ['1'])[0]
                    if not re.fullmatch(r'[0-9]{1,9}', page_value):
                        raise ValueError('Неверный номер страницы')
                    requested = max(1, int(page_value))
                    page_size = 10
                    scope = "role='coach'" if coaches else "role='user'"
                    params = ()
                    if role == 'coach':
                        scope += ' AND coach=? AND is_del=0'
                        params = (uid,)
                    invited_by = None
                    if coaches and role == 'user':
                        scope += ' AND is_del=0'
                        referral = c.execute("""
                            SELECT p.owner_id FROM promo_redemptions r
                            JOIN promo_codes p ON p.id=r.promo_code_id
                            JOIN users owner ON owner.id=p.owner_id
                            WHERE r.user_id=? AND owner.role='coach'
                        """, (uid,)).fetchone()
                        invited_by = referral['owner_id'] if referral else None
                    order = 'CASE WHEN id=? THEN 0 ELSE 1 END, id' if invited_by else 'id'
                    order_params = (invited_by,) if invited_by else ()
                    total = c.execute(f'SELECT count(*) FROM users WHERE {scope}', params).fetchone()[0]
                    pages = max(1, (total + page_size - 1) // page_size)
                    current = min(requested, pages)
                    offset = (current - 1) * page_size
                    clients = [dict(row) for row in c.execute(
                        f'SELECT id,name,email,phone,surname,given_name,patronymic,profile_media,is_del, '
                        "CASE WHEN is_del=0 AND last_activity_at>=CURRENT_TIMESTAMP - INTERVAL '10 minutes' THEN 'online' "
                        "WHEN is_del=0 AND last_activity_at>=CURRENT_TIMESTAMP - INTERVAL '30 minutes' THEN 'recent' END AS activity "
                        f'FROM users WHERE {scope} ORDER BY {order} LIMIT ? OFFSET ?',
                        (*params, *order_params, page_size, offset))]
                    if coaches:
                        for coach in clients:
                            coach['invited_you'] = coach['id'] == invited_by
                            coach['client_count'] = c.execute(
                                "SELECT count(*) FROM users WHERE role='user' AND is_del=0 AND coach=?",
                                (coach['id'],)).fetchone()[0]
                    elif role == 'coach':
                        for client in clients:
                            client['workouts'] = [row['title'] for row in c.execute(
                                'SELECT title FROM workouts WHERE coach=? AND client=? ORDER BY id',
                                (uid, client['id']))]
                    return self.respond(200, dict(clients=clients, page=current, pages=pages, offset=offset))
                if self.path == '/api/exercise-stats' and method == 'GET':
                    if role not in ('admin', 'coach'):
                        return self.respond(403, {'error':'Нет доступа'})
                    stats = dict(c.execute("""
                        SELECT count(*) AS total,
                               count(*) FILTER (WHERE moderation_status = 'approved') AS approved,
                               count(*) FILTER (WHERE moderation_status = 'pending') AS pending,
                               count(*) FILTER (WHERE EXISTS (
                                   SELECT 1 FROM jsonb_array_elements(gallery::jsonb) AS photo
                                   WHERE photo->>'type' = 'photo' AND COALESCE(photo->>'url', '') <> ''
                               ) OR split_part(split_part(media, chr(63), 1), '#', 1)
                                 ~* '[.](jpg|jpeg|png|webp|gif|avif)$') AS with_photo,
                               count(*) FILTER (WHERE regexp_replace(
                                   CASE WHEN instruction_format='html' THEN
                                       regexp_replace(coalesce(instruction,''), '<[^>]*>|&nbsp;|&#160;|&#[xX]0*[aA]0;', '', 'g')
                                   ELSE coalesce(instruction,'') END,
                                   '[[:space:]' || chr(160) || chr(8203) || chr(8204) || chr(8205) || chr(65279) || ']', '', 'g'
                               ) <> '') AS with_description,
                               count(*) FILTER (WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '1 month') AS recent,
                               count(*) FILTER (WHERE created_at IS NULL) AS unknown_dates
                        FROM exercises
                    """).fetchone())
                    stats['used'] = c.execute("""
                        SELECT count(DISTINCT e.id)
                        FROM workouts w
                        JOIN users u ON u.id=w.coach AND u.role='coach'
                        CROSS JOIN LATERAL jsonb_array_elements(w.items::jsonb) AS item
                        JOIN exercises e ON e.id = CASE
                            WHEN item->>'exercise' ~ '^[0-9]{1,10}$'
                            THEN (item->>'exercise')::bigint
                        END
                    """).fetchone()[0]
                    stats['load_types'] = [dict(row) for row in c.execute("""
                        SELECT t.name, count(et.exercise_id) AS total
                        FROM tags t
                        JOIN tag_groups g ON g.id=t.group_id
                        LEFT JOIN exercise_tags et ON et.tag_id=t.id
                        WHERE g.name=? AND t.archived_at IS NULL
                        GROUP BY t.id, t.name
                        ORDER BY t.id
                    """, ('Тип нагрузки',))]
                    return self.respond(200, stats)
                if self.path == '/api/promo-codes':
                    if role != 'coach':
                        return self.respond(403, {'error':'Нет доступа'})
                    if method == 'GET':
                        return self.respond(200, [dict(row) for row in c.execute("""
                            SELECT id,code,comment FROM promo_codes
                            WHERE owner_id=? AND deleted_at IS NULL ORDER BY id DESC
                        """, (uid,))])
                    if body.get('action') == 'delete':
                        deleted = c.execute("""
                            UPDATE promo_codes SET deleted_at=CURRENT_TIMESTAMP
                            WHERE id=? AND owner_id=? AND deleted_at IS NULL RETURNING code
                        """, (int(body['id']),uid)).fetchone()
                        if not deleted:
                            return self.respond(404, {'error':'Промокод не найден'})
                    elif body.get('action') == 'create':
                        comment = body.get('comment', '')
                        if not isinstance(comment, str) or len(comment) > 250:
                            raise ValueError('Комментарий должен содержать не более 250 символов')
                        for _ in range(20):
                            code = ''.join(secrets.choice('DFGJNQRSUVWZ23456789') for _ in range(5))
                            if c.execute("""
                                INSERT INTO promo_codes(owner_id, code, comment) VALUES(?,?,?)
                                ON CONFLICT (code) DO NOTHING RETURNING id
                            """, (uid,code,comment.strip())).fetchone():
                                break
                        else:
                            return self.respond(503, {'error':'Не удалось создать код. Попробуйте ещё раз'})
                    else:
                        raise ValueError('Неизвестное действие')
                    c.commit()
                    return self.respond(200, {'ok':True})
                if self.path == '/api/coach-programs':
                    if role != 'coach':
                        return self.respond(403, {'error':'Нет доступа'})
                    if method == 'GET':
                        programs = [dict(row) for row in c.execute(
                            'SELECT id, title, duration, items FROM coach_programs WHERE coach_id=? ORDER BY id DESC', (uid,))]
                        return self.respond(200, programs)
                    title = body['title'].strip()
                    duration = body['duration']
                    items = body['items']
                    if not 1 <= len(title) <= 100 or duration not in (7, 30) or not isinstance(items, list) or not 1 <= len(items) <= 90:
                        raise ValueError('Укажите название, срок и хотя бы одну тренировку')
                    if any(not isinstance(item, dict) or type(item.get('day')) is not int
                           or not 1 <= item['day'] <= duration or type(item.get('template')) is not int for item in items):
                        raise ValueError('Проверьте дни и тренировки программы')
                    template_ids = {item['template'] for item in items}
                    available = {row['id'] for row in c.execute(
                        'SELECT id FROM workouts WHERE coach=? AND client IS NULL AND id=ANY(?)',
                        (uid, list(template_ids)))}
                    if available != template_ids:
                        raise ValueError('Выберите шаблоны из своих тренировок')
                    if body.get('id') is None:
                        c.execute('INSERT INTO coach_programs(coach_id,title,duration,items) VALUES(?,?,?,?::jsonb)',
                                  (uid,title,duration,json.dumps(items)))
                    elif not c.execute('UPDATE coach_programs SET title=?,duration=?,items=?::jsonb WHERE id=? AND coach_id=? RETURNING id',
                                       (title,duration,json.dumps(items),int(body['id']),uid)).fetchone():
                        return self.respond(404, {'error':'Программа не найдена'})
                    c.commit()
                    return self.respond(200, {'ok':True})
                if self.path=='/api/state':
                    columns = 'id,name,email,role,coach,phone,surname,given_name,patronymic,profile_media,coach_bio,is_del'
                    if role == 'admin':
                        client_id = self.query.get('client', [''])[0]
                        client_id = int(client_id) if client_id.isdecimal() else None
                        coach_id = self.query.get('coach', [''])[0]
                        coach_id = int(coach_id) if coach_id.isdecimal() else None
                        users = [dict(row) for row in c.execute(
                            f"SELECT {columns} FROM users WHERE (role='coach' AND id=?) OR (role='user' AND id=?)",
                            (coach_id, client_id))]
                        workouts = [dict(row) for row in c.execute('SELECT * FROM workouts WHERE client=?', (client_id,))]
                    else:
                        users = [dict(row) for row in c.execute(
                            f'SELECT {columns} FROM users WHERE is_del=0 AND (id=? OR coach=?)',
                            (uid, uid if role == 'coach' else None))]
                        if role == 'coach':
                            workouts = [dict(row) for row in c.execute(
                                'SELECT w.* FROM workouts w WHERE w.coach=? AND (w.client IS NULL OR EXISTS '
                                '(SELECT 1 FROM users WHERE id=w.client AND coach=? AND is_del=0))', (uid, uid))]
                        else:
                            workouts = [dict(row) for row in c.execute('SELECT * FROM workouts WHERE client=?', (uid,))]
                    for w in workouts:
                        w['details']=json.loads(w['details']); w['items']=json.loads(w['items']); r=c.execute('SELECT payload,updated FROM results WHERE workout=? AND client=?',(w['id'],w['client'])).fetchone();w['result']=json.loads(r['payload']) if r else {};w['updated']=r['updated'] if r else None
                    return self.respond(200,dict(user=dict(u),users=users,exercises=[dict(x) for x in c.execute('SELECT e.*, ARRAY(SELECT tag_id FROM exercise_tags WHERE exercise_id=e.id ORDER BY tag_id) AS tag_ids, ARRAY(SELECT t.name FROM exercise_tags et JOIN tags t ON t.id=et.tag_id WHERE et.exercise_id=e.id AND t.archived_at IS NULL ORDER BY t.group_id,t.id) AS tag_names, ARRAY(SELECT t.name FROM exercise_tags et JOIN tags t ON t.id=et.tag_id JOIN tag_groups g ON g.id=t.group_id WHERE et.exercise_id=e.id AND t.archived_at IS NULL AND g.name=? ORDER BY t.id) AS load_types, (SELECT u.name FROM users u WHERE u.id=e.created_by AND u.role=\'coach\') AS coach_name FROM exercises e WHERE e.moderation_status<>? OR e.created_by=? OR ?=?', ('Тип нагрузки','draft',uid,role,'admin'))],workouts=workouts))
                if method!='POST':return self.respond(404,{'error':'Не найдено'})
                if self.path=='/api/profile-media' and role in ('coach','user','admin'):
                    target_uid = uid
                    if role == 'admin':
                        target_uid = int(body['coach'])
                        if not c.execute("SELECT 1 FROM users WHERE id=? AND role='coach'",(target_uid,)).fetchone():
                            return self.respond(404, {'error':'Coach unavailable'})
                    gallery = body['gallery']
                    main = body.get('main')
                    if len(gallery)>20 or any(item['type']!='photo' or not re.fullmatch(r'/uploads/(?:(?:admin|coach|user)/[0-9]{4}/[0-9]{2}/[0-9]{2}/)?[a-f0-9]{32}[.](jpg|png|webp)',item['url']) for item in gallery):
                        raise ValueError('Invalid photos')
                    if main is not None and (type(main) is not int or not 0 <= main < len(gallery)):
                        raise ValueError('Invalid main photo')
                    media = {'gallery':gallery,'cover':gallery[main]['url'] if main is not None else ''}
                    c.execute('UPDATE users SET profile_media=? WHERE id=?',(json.dumps(media),target_uid))
                    c.commit()
                    return self.respond(200, {'ok':True})
                if self.path == '/api/coach-bio' and method == 'POST' and role in ('coach', 'admin'):
                    target_uid = int(body['coach']) if role == 'admin' else uid
                    key = body['section']
                    if key not in ('education', 'achievements', 'specializations'):
                        raise ValueError('Неизвестный раздел профиля')
                    c.execute('BEGIN IMMEDIATE')
                    target = c.execute("SELECT coach_bio FROM users WHERE id=? AND role='coach'", (target_uid,)).fetchone()
                    if not target:
                        return self.respond(404, {'error':'Тренер не найден'})
                    bio = json.loads(target['coach_bio'] or '{}')
                    bio[key] = body['items']
                    save_coach_bio(c, target_uid, {'bio':bio})
                    c.commit()
                    return self.respond(200, {'bio':bio})
                if self.path=='/api/coach-profile' and role in ('coach','user','admin'):
                    target_uid = uid
                    if role == 'admin':
                        target_uid = int(body['coach'])
                        if not c.execute("SELECT 1 FROM users WHERE id=? AND role='coach'",(target_uid,)).fetchone():
                            return self.respond(404, {'error':'Coach unavailable'})
                    parts = [body[key].strip() for key in ('surname','given_name','patronymic')]
                    if not parts[0] or (role != 'user' and not parts[1]) or any(len(part)>50 for part in parts):
                        raise ValueError('Invalid profile name')
                    target = c.execute('SELECT email,phone FROM users WHERE id=?',(target_uid,)).fetchone()
                    email = body.get('email', target['email']).strip().lower() or target['email']
                    phone = body.get('phone', target['phone']).strip()
                    if len(email)>254 or not re.fullmatch(r'[^@\s]+@[^@\s]+[.][^@\s]+', email):
                        raise ValueError('Введите корректный email')
                    if phone and not re.fullmatch(r'[+][1-9][0-9]{6,14}', phone):
                        raise ValueError('Введите телефон в международном формате')
                    if c.execute('SELECT 1 FROM users WHERE lower(email)=? AND id<>?', (email,target_uid)).fetchone():
                        return self.respond(409, {'error':'Эта почта уже используется'})
                    c.execute('UPDATE users SET surname=?,given_name=?,patronymic=?,name=?,email=?,phone=? WHERE id=?',
                              (*parts, ' '.join(filter(None,parts)), email, phone, target_uid))
                    if role == 'user' and 'birth_date' in body:
                        value = body['birth_date']
                        birthday = None
                        if value != '':
                            if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
                                raise ValueError('Введите корректную дату рождения')
                            try:
                                birthday = date.fromisoformat(value)
                            except ValueError:
                                raise ValueError('Введите корректную дату рождения') from None
                            if birthday > date.today():
                                raise ValueError('Дата рождения не может быть в будущем')
                        c.execute('UPDATE users SET birth_date=? WHERE id=?', (birthday, uid))
                    if 'communication_languages' in body:
                        languages = body['communication_languages']
                        if not isinstance(languages, list) or len(languages) > 9 or any(
                            code not in ('ru', 'en', 'tt', 'uz', 'kk', 'pt', 'es', 'it', 'de') for code in languages
                        ):
                            raise ValueError('Выберите языки из списка')
                        c.execute('UPDATE users SET communication_languages=?::text[] WHERE id=?',
                                  (list(dict.fromkeys(languages)), target_uid))
                    if 'location_selection' in body:
                        import hmac
                        token = body['location_selection']
                        payload = None
                        if token:
                            signature, _, payload = token.partition(':')
                            expected = hmac.digest(LOCATION_KEY, payload.encode(), 'sha256').hex()
                            if not hmac.compare_digest(expected, signature):
                                raise ValueError('Выберите город из подсказок повторно')
                        location = json.loads(payload) if payload else {}
                        c.execute('UPDATE users SET profile_location=?::jsonb, location_country=?, location_city=? '
                                  'WHERE id=?',
                                  (payload, location.get('code') or location.get('country'), location.get('city'), target_uid))
                    if role in ('coach', 'admin'):
                        save_coach_bio(c, target_uid, body)
                    c.commit()
                    return self.respond(200, {'ok':True})
                if (self.path in ('/api/client-create','/api/client-edit') and role=='coach') or (self.path=='/api/coach-create' and role=='admin'):
                    account_role = 'coach' if self.path=='/api/coach-create' else 'user'
                    editing = self.path=='/api/client-edit'
                    client_id = body.get('id') if editing else None
                    if editing and not c.execute("SELECT 1 FROM users WHERE id=? AND coach=? AND role='user' AND is_del=0",(client_id,uid)).fetchone():
                        return self.respond(404, {'error':'Client unavailable'})
                    surname = body['surname'].strip()
                    given_name = body['given_name'].strip()
                    patronymic = body.get('patronymic','').strip()
                    phone = body['phone'].strip()
                    if not surname or not given_name or any(len(part)>50 for part in (surname,given_name,patronymic)):
                        raise ValueError('Invalid client name')
                    if not re.fullmatch(r'[+0-9() .-]{7,32}', phone) or not 7 <= len(re.sub(r'[^0-9]', '', phone)) <= 15:
                        raise ValueError('Invalid mobile phone')
                    name = ' '.join(filter(None, (surname,given_name,patronymic)))
                    email = body.get('email','').strip().lower() or (c.execute('SELECT email FROM users WHERE id=?',(client_id,)).fetchone()[0] if editing else f'athlete-{secrets.token_hex(8)}@login.invalid')
                    if not 1 <= len(name) <= 150 or not re.fullmatch(r'[^@\s]+@[^@\s]+[.][^@\s]+', email):
                        raise ValueError('Invalid client name or email')
                    if c.execute('SELECT 1 FROM users WHERE lower(email)=? AND id IS NOT ?', (email,client_id)).fetchone():
                        return self.respond(409, {'error':'Email already registered'})
                    if editing:
                        c.execute('UPDATE users SET name=?,email=?,surname=?,given_name=?,patronymic=?,phone=? WHERE id=? AND coach=?',
                                  (name,email,surname,given_name,patronymic,phone,client_id,uid))
                        c.commit()
                        return self.respond(200, {'email':email})
                    temporary_password = secrets.token_urlsafe(18)
                    salt = secrets.token_hex(16)
                    client_id = c.execute('INSERT INTO users(name,email,role,salt,hash,coach,surname,given_name,patronymic,phone) VALUES(?,?,?,?,?,?,?,?,?,?) RETURNING id',
                              (name,email,account_role,salt,password(temporary_password,salt),uid if account_role=='user' else None,surname,given_name,patronymic,phone)).fetchone()[0]
                    if account_role == 'coach':
                        save_coach_bio(c, client_id, body)
                    c.commit()
                    return self.respond(201, {'id':client_id,'email':email,'password':temporary_password})
                if self.path=='/api/client-search' and role=='coach':
                    query = body['query'].strip().casefold()
                    users = [dict(row) for row in c.execute("SELECT id,name,email,coach IS NULL AS available FROM users WHERE role='user' AND is_del=0") if len(query)>=3 and any(query in row[key].casefold() for key in ('name','email'))]
                    return self.respond(200, users[:30])
                if self.path=='/api/client-link' and role=='coach':
                    updated = c.execute("UPDATE users SET coach=? WHERE id=? AND role='user' AND is_del=0 AND coach IS NULL", (uid,body['id']))
                    if not updated.rowcount:
                        return self.respond(409, {'error':'Client unavailable'})
                elif self.path=='/api/exercises' and role in ('admin','coach'):
                    instruction_format = body.get('instruction_format', 'text')
                    instruction = validate_instruction(body.get('instruction',''), instruction_format)
                    name=body['name'].strip(); media=body.get('media','')
                    if not name or (media and not media.startswith('https://')):raise ValueError('Укажите название и HTTPS-ссылку на медиа')
                    gallery = body.get('gallery', [])
                    if not isinstance(gallery, list) or len(gallery) > 20 or any(
                        not isinstance(photo, dict) or photo.get('type') != 'photo'
                        or not re.fullmatch(r'/uploads/(?:(?:admin|coach|user)/[0-9]{4}/[0-9]{2}/[0-9]{2}/)?[a-f0-9]{32}[.](jpg|png|webp)', photo.get('url', ''))
                        for photo in gallery
                    ):
                        raise ValueError('Проверьте фотографии в галерее')
                    if gallery:
                        urls = [photo['url'] for photo in gallery]
                        media = body.get('cover') or urls[0]
                        if media not in urls:
                            raise ValueError('Выберите главное фото из галереи')
                    if 'id' in body:
                        exercise_id = int(body['id'])
                        exercise = c.execute('SELECT created_by, moderation_status FROM exercises WHERE id=? FOR UPDATE', (exercise_id,)).fetchone()
                        if not exercise:
                            return self.respond(404, {'error':'Упражнение не найдено'})
                        if role == 'coach' and (exercise['created_by'] != uid or exercise['moderation_status'] != 'draft'):
                            return self.respond(403, {'error':'Можно редактировать только свои черновики'})
                        if 'gallery' in body:
                            c.execute('UPDATE exercises SET name=?,instruction=?,instruction_format=?,media=?,gallery=? WHERE id=?',
                                      (name,instruction,instruction_format,media,json.dumps(gallery),int(body['id'])))
                        else:
                            c.execute('UPDATE exercises SET name=?,instruction=?,instruction_format=? WHERE id=?',
                                      (name,instruction,instruction_format,int(body['id'])))
                    else:
                        exercise_id = c.execute(
                            'INSERT INTO exercises(name,instruction,instruction_format,media,gallery,created_by,moderation_status) VALUES(?,?,?,?,?,?,?) RETURNING id',
                            (name,instruction,instruction_format,media,json.dumps(gallery),uid,'draft' if role=='coach' else 'approved')).fetchone()['id']
                    if 'tag_ids' in body:
                        tag_ids = body['tag_ids']
                        if not isinstance(tag_ids, list) or any(type(tag) is not int for tag in tag_ids):
                            raise ValueError('Проверьте выбранные теги')
                        existing = {row['id'] for row in c.execute(
                            'SELECT id FROM tags WHERE id = ANY(?) AND archived_at IS NULL FOR SHARE', (tag_ids,))}
                        if existing != set(tag_ids):
                            raise ValueError('Справочник изменился. Откройте упражнение заново.')
                        c.execute('DELETE FROM exercise_tags WHERE exercise_id=? AND tag_id IN (SELECT id FROM tags WHERE archived_at IS NULL)', (exercise_id,))
                        for tag_id in sorted(existing):
                            c.execute('INSERT INTO exercise_tags(exercise_id, tag_id) VALUES(?,?)',
                                      (exercise_id, tag_id))
                    if role == 'admin' and 'id' in body and 'moderation_status' in body:
                        status = body['moderation_status']
                        if status not in ('pending', 'approved', 'rejected'):
                            raise ValueError('Выберите допустимый статус модерации')
                        c.execute('UPDATE exercises SET moderation_status=? WHERE id=?', (status,exercise_id))
                    if role == 'coach' and 'id' in body and body.get('submit_for_moderation') is True:
                        c.execute("UPDATE exercises SET moderation_status='pending' WHERE id=?", (exercise_id,))
                    c.commit()
                elif self.path=='/api/trainers' and role=='admin':
                    if len(body['password'])<8:raise ValueError('Пароль должен содержать не менее 8 символов')
                    salt=secrets.token_hex(16);c.execute('INSERT INTO users(name,email,role,salt,hash) VALUES(?,?,?,?,?)',(body['name'],body['email'],'coach',salt,password(body['password'],salt)))
                elif self.path=='/api/template-media' and role=='coach':
                    row = c.execute('SELECT details FROM workouts WHERE id=? AND coach=? AND client IS NULL', (body['id'], uid)).fetchone()
                    if not row:
                        return self.respond(404, {'error':'Template unavailable'})
                    details = json.loads(row['details'])
                    gallery = details.get('gallery', [])
                    if 'items' in body:
                        items = body['items']
                        if not 1 <= len(items) <= 30:
                            raise ValueError('Add 1 to 30 exercises')
                        for item in items:
                            if not c.execute('SELECT id FROM exercises WHERE id=?', (item['exercise'],)).fetchone() or not 1 <= int(item['sets']) <= 20 or not isinstance(item['reps'], str) or not item['reps'].strip():
                                raise ValueError('Invalid exercise or sets')
                            if item.get('media') and not item['media'].startswith('https://'):
                                raise ValueError('HTTPS media URL required')
                        c.execute('UPDATE workouts SET items=? WHERE id=?', (json.dumps(items),body['id']))
                    elif 'title' in body:
                        title = body['title'].strip()
                        if not 1 <= len(title) <= 100:
                            raise ValueError('Invalid title')
                        details['description'] = body['description']
                        c.execute('UPDATE workouts SET title=?,details=? WHERE id=?', (title,json.dumps(details),body['id']))
                    else:
                        gallery = body['gallery']
                        main = body.get('main')
                        if len(gallery)>20 or any(m['type'] not in ('photo','video') or not (m['url'].startswith('https://') or re.fullmatch(r'/uploads/(?:(?:admin|coach|user)/[0-9]{4}/[0-9]{2}/[0-9]{2}/)?[a-f0-9]{32}[.](jpg|png|webp|mp4|webm)',m['url'])) for m in gallery):
                            raise ValueError('Invalid gallery')
                        if main is not None and (type(main) is not int or not 0 <= main < len(gallery)):
                            raise ValueError('Invalid main media')
                        details.update(gallery=gallery,cover=gallery[main]['url'] if main is not None else '')
                        c.execute('UPDATE workouts SET details=? WHERE id=?', (json.dumps(details),body['id']))
                elif self.path=='/api/workouts' and role=='coach':
                    if body.get('template'):
                        template = c.execute('SELECT * FROM workouts WHERE id=? AND coach=? AND client IS NULL', (body['template'], uid)).fetchone()
                        if not template:
                            raise ValueError('Шаблон недоступен')
                        body.update(title=template['title'], items=json.loads(template['items']), details=json.loads(template['details']))
                    if 'assignments' in body:
                        assignments = body['assignments']
                        if not body.get('template') or not assignments:
                            raise ValueError('Select clients')
                        seen = set()
                        for assignment in assignments:
                            client_id = int(assignment['client'])
                            start = date.fromisoformat(assignment['from'])
                            end = date.fromisoformat(assignment['to'])
                            if start > end or client_id in seen or not c.execute("SELECT 1 FROM users WHERE id=? AND coach=? AND role='user' AND is_del=0",(client_id,uid)).fetchone():
                                raise ValueError('Check client and assignment dates')
                            seen.add(client_id)
                            details = {**body['details'], 'period': {'from':start.isoformat(),'to':end.isoformat()}}
                            c.execute('INSERT INTO workouts(title,client,coach,items,details) VALUES(?,?,?,?,?)',
                                      (body['title'],client_id,uid,json.dumps(body['items']),json.dumps(details)))
                        return self.respond(200, {'ok':True})
                    client_id = body.get('client')
                    client=c.execute('SELECT id FROM users WHERE id=? AND coach=? AND is_del=0',(int(client_id),uid)).fetchone() if client_id else None
                    if client_id and not client:raise ValueError('Клиент недоступен')
                    items=body['items']
                    if not items or len(items)>30:raise ValueError('Добавьте от 1 до 30 упражнений')
                    for it in items:
                        if not c.execute('SELECT id FROM exercises WHERE id=?',(it['exercise'],)).fetchone() or not 1<=int(it['sets'])<=20:raise ValueError('Проверьте упражнение и подходы')
                        if it.get('media') and not it['media'].startswith('https://'):raise ValueError('Нужна HTTPS-ссылка')
                    title = body['title'].strip()
                    details = body.get('details', {})
                    gallery = details.get('gallery', [])
                    cover = details.get('cover', '')
                    if not title or len(title) > 100:
                        raise ValueError('Название должно содержать от 1 до 100 символов')
                    if len(gallery) > 20 or any(m['type'] not in ('photo', 'video') or not (m['url'].startswith('https://') or re.fullmatch(r'/uploads/(?:(?:admin|coach|user)/[0-9]{4}/[0-9]{2}/[0-9]{2}/)?[a-f0-9]{32}[.](jpg|png|webp|mp4|webm)', m['url'])) for m in gallery):
                        raise ValueError('Добавьте до 20 фото или видео по HTTPS-ссылкам')
                    if cover and not any(m['url']==cover for m in gallery):
                        raise ValueError('Выберите главное фото из галереи')
                    c.execute('INSERT INTO workouts(title,client,coach,items,details) VALUES(?,?,?,?,?)',
                              (title, client['id'] if client else None, uid, json.dumps(items), json.dumps(details)))
                elif self.path=='/api/results' and role=='user':
                    w=c.execute('SELECT * FROM workouts WHERE id=? AND client=?',(body['workout'],uid)).fetchone()
                    if not w:raise ValueError('Тренировка недоступна')
                    result = body['result']
                    items = json.loads(w['items'])
                    if not isinstance(result, dict) or any(key not in {str(i) for i in range(len(items))} for key in result):
                        raise ValueError('Неверные результаты тренировки')
                    for value in result.values():
                        if not isinstance(value, dict) or type(value.get('done', False)) is not bool:
                            raise ValueError('Неверный статус упражнения')
                    c.execute('INSERT INTO results(workout,client,payload) VALUES(?,?,?) ON CONFLICT(workout,client) DO UPDATE SET payload=excluded.payload,updated=CURRENT_TIMESTAMP',(w['id'],uid,json.dumps(result)))
                    awarded = 0
                    if items and all(result.get(str(i), {}).get('done') is True for i in range(len(items))):
                        award = c.execute("""
                            INSERT INTO star_awards(user_id,reason,amount) VALUES(?,?,5)
                            ON CONFLICT(user_id,reason) DO NOTHING RETURNING amount
                        """, (uid, 'workout_completed_' + str(w['id']))).fetchone()
                        awarded = award['amount'] if award else 0
                    c.commit()
                    return self.respond(200, {'ok':True, 'awarded_stars':awarded})
                else:return self.respond(403,{'error':'Нет доступа к этому действию'})
                return self.respond(200,{'ok':True})
        except (ValueError,KeyError,TypeError) + INTEGRITY_ERRORS as e:self.respond(400,{'error':str(e) if not isinstance(e,INTEGRITY_ERRORS) else 'Такая почта уже зарегистрирована'})

if __name__=='__main__':
    init()
    port = int(os.environ.get('PORT','18743'))
    print(f'ПланТренировок: http://127.0.0.1:{port}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()
