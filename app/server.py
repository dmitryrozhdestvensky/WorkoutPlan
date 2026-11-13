import re, json, secrets, hashlib, os
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from http.cookies import SimpleCookie

ROOT = Path(__file__).parent
DATA_DIR = Path(os.environ.get('WORKOUTPLAN_DATA_DIR', ROOT / 'data'))
SESSIONS = {}
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    raise RuntimeError('DATABASE_URL is required for PostgreSQL')

import postgres_backend

INTEGRITY_ERRORS = (postgres_backend.psycopg.IntegrityError,)


def connect():
    return postgres_backend.connect(DATABASE_URL)


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
        if path.parent != ROOT/'web' or not path.is_file():self.send_error(404);return
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
        (folder / name).write_bytes(raw)
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
                    t=secrets.token_hex(32);SESSIONS[t]=u['id'];return self.respond(200,{'ok':True},f'session={t}; HttpOnly; SameSite=Strict; Path=/')
                if not uid:return self.respond(401,{'error':'Войдите в аккаунт'})
                u=c.execute('SELECT id,name,email,role,coach,surname,given_name,patronymic,phone,profile_media,coach_bio FROM users WHERE id=? AND is_del=0',(uid,)).fetchone()
                if not u: return self.respond(401, {'error':'Войдите в аккаунт'})
                role=u['role']
                if method == 'GET' and self.path == '/api/geography':
                    query = self.query.get('q', [''])[0].strip()[:100]
                    try:
                        return self.respond(200, city_query(query))
                    except OSError:
                        return self.respond(503, {'error':'Подсказки городов временно недоступны'})
                if self.path == '/api/state':
                    u.update(c.execute("""
                        SELECT profile_location FROM users WHERE id=?
                    """, (uid,)).fetchone())
                if self.path=='/api/logout':
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
                    if role != 'admin':
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
                    if role not in ('admin', 'coach') or (coaches and role != 'admin'):
                        return self.respond(403, {'error':'Нет доступа'})
                    requested = max(1, int(self.query.get('page', ['1'])[0]))
                    page_size = 10
                    scope = "role='coach'" if coaches else "role='user'"
                    params = ()
                    if role == 'coach':
                        scope += ' AND coach=? AND is_del=0'
                        params = (uid,)
                    total = c.execute(f'SELECT count(*) FROM users WHERE {scope}', params).fetchone()[0]
                    pages = max(1, (total + page_size - 1) // page_size)
                    current = min(requested, pages)
                    offset = (current - 1) * page_size
                    clients = [dict(row) for row in c.execute(
                        f'SELECT id,name,email,phone,surname,given_name,patronymic,profile_media,is_del '
                        f'FROM users WHERE {scope} ORDER BY id LIMIT ? OFFSET ?',
                        (*params, page_size, offset))]
                    if coaches:
                        for coach in clients:
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
                               count(*) FILTER (WHERE EXISTS (
                                   SELECT 1 FROM jsonb_array_elements(gallery::jsonb) AS photo
                                   WHERE photo->>'type' = 'photo' AND COALESCE(photo->>'url', '') <> ''
                               ) OR split_part(split_part(media, chr(63), 1), '#', 1)
                                 ~* '[.](jpg|jpeg|png|webp|gif|avif)$') AS with_photo,
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
                    return self.respond(200,dict(user=dict(u),users=users,exercises=[dict(x) for x in c.execute('SELECT e.*, ARRAY(SELECT tag_id FROM exercise_tags WHERE exercise_id=e.id ORDER BY tag_id) AS tag_ids, ARRAY(SELECT t.name FROM exercise_tags et JOIN tags t ON t.id=et.tag_id WHERE et.exercise_id=e.id AND t.archived_at IS NULL ORDER BY t.group_id,t.id) AS tag_names, ARRAY(SELECT t.name FROM exercise_tags et JOIN tags t ON t.id=et.tag_id JOIN tag_groups g ON g.id=t.group_id WHERE et.exercise_id=e.id AND t.archived_at IS NULL AND g.name=? ORDER BY t.id) AS load_types FROM exercises e', ('Тип нагрузки',))],workouts=workouts))
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
                    if not all(parts[:2]) or any(len(part)>50 for part in parts):
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
                        c.execute('UPDATE users SET profile_location=?::jsonb, location_country=?, location_city=?, '
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
                elif self.path=='/api/exercises' and role=='admin':
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
                        exercise = c.execute('SELECT media FROM exercises WHERE id=?', (int(body['id']),)).fetchone()
                        if not exercise:
                            return self.respond(404, {'error':'Упражнение не найдено'})
                        if 'gallery' in body:
                            c.execute('UPDATE exercises SET name=?,instruction=?,media=?,gallery=? WHERE id=?',
                                      (name,body.get('instruction',''),media,json.dumps(gallery),int(body['id'])))
                        else:
                            c.execute('UPDATE exercises SET name=?,instruction=? WHERE id=?',
                                      (name,body.get('instruction',''),int(body['id'])))
                    else:
                        c.execute('INSERT INTO exercises(name,instruction,media,gallery) VALUES(?,?,?,?)',
                                  (name,body.get('instruction',''),media,json.dumps(gallery)))
                    if 'id' in body and 'tag_ids' in body:
                        exercise_id = int(body['id'])
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
                        from datetime import date
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
                    c.execute('INSERT INTO results(workout,client,payload) VALUES(?,?,?) ON CONFLICT(workout,client) DO UPDATE SET payload=excluded.payload,updated=CURRENT_TIMESTAMP',(w['id'],uid,json.dumps(body['result'])))
                else:return self.respond(403,{'error':'Нет доступа к этому действию'})
                return self.respond(200,{'ok':True})
        except (ValueError,KeyError,TypeError) + INTEGRITY_ERRORS as e:self.respond(400,{'error':str(e) if not isinstance(e,INTEGRITY_ERRORS) else 'Такая почта уже зарегистрирована'})

if __name__=='__main__':
    init()
    port = int(os.environ.get('PORT','18743'))
    print(f'ПланТренировок: http://127.0.0.1:{port}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()
