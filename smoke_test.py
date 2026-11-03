from pathlib import Path
import urllib.request, urllib.error, json, http.cookiejar

BASE = 'http://127.0.0.1:18743'

def client(email):
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    def req(path, data=None):
        request = urllib.request.Request(BASE+'/api/'+path, data=json.dumps(data).encode() if data is not None else None, headers={'Content-Type':'application/json'})
        return json.load(opener.open(request, timeout=10))
    req('login', {'email':email+'@demo.local','password':(Path(__file__).parent / 'data' / 'demo-password.txt').read_text().strip()})
    return req

u, c, a = client('user'), client('coach'), client('admin')
state = u('state')
assert len(state['workouts']) >= 3
w = state['workouts'][0]
old = w['result']
value = {'0':{'sets':[{'weight':'60','reps':'10','done':True}],'note':'Smoke test','done':True}}
try:
    u('results', {'workout':w['id'],'result':value})
    assert next(x for x in c('state')['workouts'] if x['id']==w['id'])['result'] == value
    try:
        u('exercises', {'name':'Forbidden'})
    except urllib.error.HTTPError as e:
        assert e.code == 403
    else:
        raise AssertionError('Role check failed')
finally:
    u('results', {'workout':w['id'],'result':old})
assert len(a('state')['users']) >= 3
assert urllib.request.urlopen(BASE, timeout=10).status == 200
print('PASS: login, roles, server save, coach visibility, restore, page serves')
