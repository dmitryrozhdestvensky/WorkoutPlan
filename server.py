import json, sqlite3, secrets, hashlib, os
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
    def respond(self,code,data,cookie=None):
        raw=json.dumps(data,ensure_ascii=False).encode(); self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store')
        if cookie:self.send_header('Set-Cookie',cookie)
        self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        if self.path.startswith('/api/'):return self.api('GET')
        path=ROOT/'web'/('index.html' if self.path=='/' else self.path.lstrip('/'))
        if path.parent != ROOT/'web' or not path.is_file():self.send_error(404);return
        self.send_response(200);self.send_header('Content-Type',{'html':'text/html; charset=utf-8','css':'text/css','js':'text/javascript; charset=utf-8'}.get(path.suffix[1:],'text/plain'));self.end_headers();self.wfile.write(path.read_bytes())
    def do_POST(self):self.api('POST')
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
                u=c.execute('SELECT id,name,email,role,coach FROM users WHERE id=?',(uid,)).fetchone();role=u['role']
                if self.path=='/api/logout':
                    SESSIONS.pop(token.value,None);return self.respond(200,{'ok':True},'session=; Max-Age=0; Path=/')
                if self.path=='/api/state':
                    users=[dict(x) for x in c.execute('SELECT id,name,email,role,coach FROM users') if role=='admin' or x['id']==uid or (role=='coach' and x['coach']==uid)]
                    workouts=[dict(x) for x in c.execute('SELECT * FROM workouts') if role=='admin' or x['client']==uid or (role=='coach' and x['coach']==uid)]
                    for w in workouts:
                        w['details']=json.loads(w['details']); w['items']=json.loads(w['items']); r=c.execute('SELECT payload,updated FROM results WHERE workout=? AND client=?',(w['id'],w['client'])).fetchone();w['result']=json.loads(r['payload']) if r else {};w['updated']=r['updated'] if r else None
                    return self.respond(200,dict(user=dict(u),users=users,exercises=[dict(x) for x in c.execute('SELECT * FROM exercises')],workouts=workouts))
                if method!='POST':return self.respond(404,{'error':'Не найдено'})
                if self.path=='/api/exercises' and role=='admin':
                    name=body['name'].strip(); media=body.get('media','')
                    if not name or (media and not media.startswith('https://')):raise ValueError('Укажите название и HTTPS-ссылку на медиа')
                    c.execute('INSERT INTO exercises(name,instruction,media) VALUES(?,?,?)',(name,body.get('instruction',''),media))
                elif self.path=='/api/trainers' and role=='admin':
                    if len(body['password'])<8:raise ValueError('Пароль должен содержать не менее 8 символов')
                    salt=secrets.token_hex(16);c.execute('INSERT INTO users(name,email,role,salt,hash) VALUES(?,?,?,?,?)',(body['name'],body['email'],'coach',salt,password(body['password'],salt)))
                elif self.path=='/api/workouts' and role=='coach':
                    if body.get('template'):
                        template = c.execute('SELECT * FROM workouts WHERE id=? AND coach=? AND client IS NULL', (body['template'], uid)).fetchone()
                        if not template:
                            raise ValueError('Шаблон недоступен')
                        body.update(title=template['title'], items=json.loads(template['items']), details=json.loads(template['details']))
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
                    if len(gallery) > 20 or any(m['type'] not in ('photo', 'video') or not m['url'].startswith('https://') for m in gallery):
                        raise ValueError('Добавьте до 20 фото или видео по HTTPS-ссылкам')
                    if cover and not any(m['type']=='photo' and m['url']==cover for m in gallery):
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
