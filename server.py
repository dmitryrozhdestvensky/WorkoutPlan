import re, json, sqlite3, secrets, hashlib, os
from contextlib import contextmanager
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from http.cookies import SimpleCookie

ROOT = Path(__file__).parent
DB = ROOT / 'data' / 'app.sqlite3'
SESSIONS = {}
@contextmanager
def connect():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    try:
        with c:
            yield c
    finally:
        c.close()
def password(value, salt):
    return hashlib.pbkdf2_hmac('sha256', value.encode(), salt.encode(), 200000).hex()
def init():
    DB.parent.mkdir(exist_ok=True)
    demo_file = DB.parent / 'demo-password.txt'
    new_demo_password = not demo_file.exists()
    if new_demo_password:
        demo_file.write_text(secrets.token_urlsafe(18), encoding='utf8')
    demo_password = demo_file.read_text(encoding='utf8').strip()
    with connect() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,name TEXT,email TEXT UNIQUE,role TEXT,salt TEXT,hash TEXT,coach INTEGER);
CREATE TABLE IF NOT EXISTS exercises(id INTEGER PRIMARY KEY,name TEXT,instruction TEXT,media TEXT);
CREATE TABLE IF NOT EXISTS workouts(id INTEGER PRIMARY KEY,title TEXT,client INTEGER,coach INTEGER,items TEXT);
CREATE TABLE IF NOT EXISTS results(workout INTEGER,client INTEGER,payload TEXT,updated TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(workout,client));''')
        user_columns = {row['name'] for row in c.execute('PRAGMA table_info(users)')}
        for field in ('surname', 'given_name', 'patronymic', 'phone', 'profile_media'):
            if field not in user_columns:
                c.execute(f"ALTER TABLE users ADD COLUMN {field} TEXT NOT NULL DEFAULT ''")
        columns = {row['name'] for row in c.execute('PRAGMA table_info(workouts)')}
        if 'details' not in columns:
            c.execute("ALTER TABLE workouts ADD COLUMN details TEXT NOT NULL DEFAULT '{}'")
        if c.execute('SELECT count(*) FROM users').fetchone()[0]:
            if new_demo_password:
                for role in ('user', 'coach', 'admin'):
                    salt = secrets.token_hex(16)
                    c.execute('UPDATE users SET salt=?,hash=? WHERE email=? AND role=?',
                              (salt, password(demo_password, salt), role+'@demo.local', role))
            return
        for name,email,role,coach in [('Дмитрий','user@demo.local','user',2),('Тренер','coach@demo.local','coach',None),('Администратор','admin@demo.local','admin',None)]:
            salt=secrets.token_hex(16); c.execute('INSERT INTO users(name,email,role,salt,hash,coach) VALUES(?,?,?,?,?,?)',(name,email,role,salt,password(demo_password,salt),coach))
        names=['Присед со штангой','Жим ногами с широкой постановкой ног','Выпады на месте с гантелями','Скручивания лёжа с весом','Жим лёжа со штангой','Жим гантелей сидя','Разведения гантелей стоя','Подъёмы ног лёжа','Становая тяга со штангой','Тяга вертикального блока широким хватом','Подъём гантелей на бицепс с ротацией','Планка']
        for n in names: c.execute('INSERT INTO exercises(name,instruction,media) VALUES(?,?,?)',(n,'Инструкцию и материалы по технике добавляет администратор.',''))
        for day in range(3):
            items=[dict(exercise=day*4+i+1,sets=4 if i==3 else (4 if day==0 and i==0 else 3 if i==0 else 5),reps='60 сек' if day==2 and i==3 else '12–15',warmup=1 if day==0 else 2,media='',note='') for i in range(4)]
            c.execute('INSERT INTO workouts(title,client,coach,items) VALUES(?,?,?,?)',(f'Неделя 1 · Тренировка {day+1}',1,2,json.dumps(items)))

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
        if re.fullmatch(r'/uploads/(?:(?:coach|user)/[0-9]{4}/[0-9]{2}/[0-9]{2}/)?[a-f0-9]{32}[.](jpg|png|webp|mp4|webm)', self.path):
            path = DB.parent / 'uploads' / self.path.removeprefix('/uploads/')
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
            user = db.execute('SELECT role FROM users WHERE id=?', (uid,)).fetchone()
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
        folder = DB.parent / 'uploads' / relative_folder
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
                    u=c.execute('SELECT * FROM users WHERE email=?',(body.get('email'),)).fetchone()
                    if not u or not secrets.compare_digest(u['hash'],password(body.get('password',''),u['salt'])):return self.respond(401,{'error':'Неверная почта или пароль'})
                    t=secrets.token_hex(32);SESSIONS[t]=u['id'];return self.respond(200,{'ok':True},f'session={t}; HttpOnly; SameSite=Strict; Path=/')
                if not uid:return self.respond(401,{'error':'Войдите в аккаунт'})
                u=c.execute('SELECT id,name,email,role,coach,surname,given_name,patronymic,phone,profile_media FROM users WHERE id=?',(uid,)).fetchone();role=u['role']
                if self.path=='/api/logout':
                    SESSIONS.pop(token.value,None);return self.respond(200,{'ok':True},'session=; Max-Age=0; Path=/')
                if self.path=='/api/state':
                    users=[dict(x) for x in c.execute('SELECT id,name,email,role,coach,phone,surname,given_name,patronymic,profile_media FROM users') if role=='admin' or x['id']==uid or (role=='coach' and x['coach']==uid)]
                    workouts=[dict(x) for x in c.execute('SELECT * FROM workouts') if role=='admin' or x['client']==uid or (role=='coach' and x['coach']==uid)]
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
                    if len(gallery)>20 or any(item['type']!='photo' or not re.fullmatch(r'/uploads/(?:(?:coach|user)/[0-9]{4}/[0-9]{2}/[0-9]{2}/)?[a-f0-9]{32}[.](jpg|png|webp)',item['url']) for item in gallery):
                        raise ValueError('Invalid photos')
                    if main is not None and (type(main) is not int or not 0 <= main < len(gallery)):
                        raise ValueError('Invalid main photo')
                    media = {'gallery':gallery,'cover':gallery[main]['url'] if main is not None else ''}
                    c.execute('UPDATE users SET profile_media=? WHERE id=?',(json.dumps(media),target_uid))
                    c.commit()
                    return self.respond(200, {'ok':True})
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
                    c.commit()
                    return self.respond(200, {'ok':True})
                if (self.path in ('/api/client-create','/api/client-edit') and role=='coach') or (self.path=='/api/coach-create' and role=='admin'):
                    account_role = 'coach' if self.path=='/api/coach-create' else 'user'
                    editing = self.path=='/api/client-edit'
                    client_id = body.get('id') if editing else None
                    if editing and not c.execute("SELECT 1 FROM users WHERE id=? AND coach=? AND role='user'",(client_id,uid)).fetchone():
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
                    c.execute('INSERT INTO users(name,email,role,salt,hash,coach,surname,given_name,patronymic,phone) VALUES(?,?,?,?,?,?,?,?,?,?)',
                              (name,email,account_role,salt,password(temporary_password,salt),uid if account_role=='user' else None,surname,given_name,patronymic,phone))
                    client_id = c.execute('SELECT last_insert_rowid()').fetchone()[0]
                    c.commit()
                    return self.respond(201, {'id':client_id,'email':email,'password':temporary_password})
                if self.path=='/api/client-search' and role=='coach':
                    query = body['query'].strip().casefold()
                    users = [dict(row) for row in c.execute("SELECT id,name,email,coach IS NULL AS available FROM users WHERE role='user'") if len(query)>=3 and any(query in row[key].casefold() for key in ('name','email'))]
                    return self.respond(200, users[:30])
                if self.path=='/api/client-link' and role=='coach':
                    updated = c.execute("UPDATE users SET coach=? WHERE id=? AND role='user' AND coach IS NULL", (uid,body['id']))
                    if not updated.rowcount:
                        return self.respond(409, {'error':'Client unavailable'})
                elif self.path=='/api/exercises' and role=='admin':
                    name=body['name'].strip(); media=body.get('media','')
                    if not name or (media and not media.startswith('https://')):raise ValueError('Укажите название и HTTPS-ссылку на медиа')
                    c.execute('INSERT INTO exercises(name,instruction,media) VALUES(?,?,?)',(name,body.get('instruction',''),media))
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
                        if len(gallery)>20 or any(m['type'] not in ('photo','video') or not (m['url'].startswith('https://') or re.fullmatch(r'/uploads/(?:(?:coach|user)/[0-9]{4}/[0-9]{2}/[0-9]{2}/)?[a-f0-9]{32}[.](jpg|png|webp|mp4|webm)',m['url'])) for m in gallery):
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
                            if start > end or client_id in seen or not c.execute("SELECT 1 FROM users WHERE id=? AND coach=? AND role='user'",(client_id,uid)).fetchone():
                                raise ValueError('Check client and assignment dates')
                            seen.add(client_id)
                            details = {**body['details'], 'period': {'from':start.isoformat(),'to':end.isoformat()}}
                            c.execute('INSERT INTO workouts(title,client,coach,items,details) VALUES(?,?,?,?,?)',
                                      (body['title'],client_id,uid,json.dumps(body['items']),json.dumps(details)))
                        return self.respond(200, {'ok':True})
                    client_id = body.get('client')
                    client=c.execute('SELECT id FROM users WHERE id=? AND coach=?',(int(client_id),uid)).fetchone() if client_id else None
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
                    if len(gallery) > 20 or any(m['type'] not in ('photo', 'video') or not (m['url'].startswith('https://') or re.fullmatch(r'/uploads/(?:(?:coach|user)/[0-9]{4}/[0-9]{2}/[0-9]{2}/)?[a-f0-9]{32}[.](jpg|png|webp|mp4|webm)', m['url'])) for m in gallery):
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
        except (ValueError,KeyError,TypeError,sqlite3.IntegrityError) as e:self.respond(400,{'error':str(e) if not isinstance(e,sqlite3.IntegrityError) else 'Такая почта уже зарегистрирована'})

if __name__=='__main__':
    init()
    port = int(os.environ.get('PORT','18743'))
    print(f'ПланТренировок: http://127.0.0.1:{port}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()
