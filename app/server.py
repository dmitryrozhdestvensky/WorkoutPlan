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
        from urllib.parse import urlsplit
        self.path = urlsplit(self.path).path
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
                            'tags':[dict(row) for row in c.execute('SELECT * FROM tags ORDER BY id')]})
                    name = body.get('name','').strip()
                    if body.get('action') == 'batch':
                        group = int(body['group'])
                        tags = body['tags']
                        existing = {row['id'] for row in c.execute('SELECT id FROM tags WHERE group_id=?',(group,))}
                        names = [tag['name'].strip() for tag in tags]
                        if {tag['id'] for tag in tags} != existing or len(tags)!=len(existing) or any(not 1<=len(value)<=80 for value in names) or len({value.casefold() for value in names})!=len(names):
                            raise ValueError('Проверьте названия тегов или обновите справочник')
                        for tag, name in zip(tags,names):
                            c.execute('UPDATE tags SET name=? WHERE id=? AND group_id=?',(name,tag['id'],group))
                        c.commit()
                        return self.respond(200, {'ok':True})
                    if body.get('action') == 'delete':
                        c.execute('DELETE FROM tags WHERE id=?',(int(body['id']),))
                    else:
                        group = int(body['group'])
                        if not 1 <= len(name) <= 80 or not c.execute('SELECT 1 FROM tag_groups WHERE id=?',(group,)).fetchone():
                            raise ValueError('Проверьте группу и название')
                        duplicate = any(row['name'].casefold()==name.casefold() and row['id']!=body.get('id') for row in c.execute('SELECT id,name FROM tags WHERE group_id=?',(group,)))
                        if duplicate:
                            raise ValueError('Такой тег уже существует')
                        if body.get('id'):
                            c.execute('UPDATE tags SET name=? WHERE id=? AND group_id=?',(name,int(body['id']),group))
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
                if self.path=='/api/state':
                    users=[dict(x) for x in c.execute('SELECT id,name,email,role,coach,phone,surname,given_name,patronymic,profile_media,coach_bio,is_del FROM users') if role=='admin' or (not x['is_del'] and (x['id']==uid or (role=='coach' and x['coach']==uid)))]
                    workouts=[dict(x) for x in c.execute('SELECT * FROM workouts') if role=='admin' or x['client']==uid or (role=='coach' and x['coach']==uid and (x['client'] is None or any(client['id']==x['client'] for client in users)))]
                    for w in workouts:
                        w['details']=json.loads(w['details']); w['items']=json.loads(w['items']); r=c.execute('SELECT payload,updated FROM results WHERE workout=? AND client=?',(w['id'],w['client'])).fetchone();w['result']=json.loads(r['payload']) if r else {};w['updated']=r['updated'] if r else None
                    return self.respond(200,dict(user=dict(u),users=users,exercises=[dict(x) for x in c.execute('SELECT * FROM exercises')],workouts=workouts))
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
