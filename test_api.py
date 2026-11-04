"""Exercise HTTP handlers in process without network permissions."""
import io
import json
import unittest
import tempfile
from pathlib import Path
import server

class ApiTest(unittest.TestCase):
    def test_roles_and_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = server.DB
            server.DB = Path(tmp) / 'test.sqlite3'
            try:
                server.init()
                def call(path, payload=None, cookie=''):
                    handler = object.__new__(server.Handler)
                    raw = json.dumps(payload).encode() if payload is not None else b''
                    handler.path = '/api/' + path
                    handler.headers = {'Content-Length': str(len(raw)), 'Cookie': cookie}
                    handler.rfile, handler.wfile = io.BytesIO(raw), io.BytesIO()
                    captured = {}
                    handler.send_response = lambda code: captured.update(code=code)
                    handler.send_header = lambda key, value: captured.update({key:value})
                    handler.end_headers = lambda: None
                    handler.api('POST' if payload is not None else 'GET')
                    return captured, json.loads(handler.wfile.getvalue())
                def login(role):
                    headers, _ = call('login', {'email':role+'@demo.local','password':(server.DB.parent / 'demo-password.txt').read_text().strip()})
                    self.assertEqual(headers['code'], 200)
                    return headers['Set-Cookie'].split(';')[0]
                user, coach, admin = login('user'), login('coach'), login('admin')
                self.assertEqual(call('state')[0]['code'],401)
                self.assertEqual(call('exercises', {'name':'Forbidden'},user)[0]['code'],403)
                result = {'0':{'sets':[{'weight':60,'reps':10,'done':True}],'done':True}}
                self.assertEqual(call('results',{'workout':1,'result':result},user)[0]['code'],200)
                self.assertEqual(call('state',cookie=coach)[1]['workouts'][0]['result'],result)
                self.assertEqual(call('exercises',{'name':'New','instruction':'Test','media':''},admin)[0]['code'],200)
                self.assertEqual(len(call('state',cookie=user)[1]['exercises']),13)
                item = {'exercise':1,'sets':3,'reps':'8'}
                self.assertEqual(call('workouts', {'title':'Before','items':[item]},coach)[0]['code'],200)
                template = next(w for w in call('state',cookie=coach)[1]['workouts'] if w['client'] is None)
                self.assertEqual(call('template-media', {'id':template['id'],'title':'After','description':'Line one\nLine two'},coach)[0]['code'],200)
                saved = next(w for w in call('state',cookie=coach)[1]['workouts'] if w['id']==template['id'])
                self.assertEqual((saved['title'],saved['details']['description']), ('After','Line one\nLine two'))
                with server.connect() as db:
                    self.assertEqual(json.loads(db.execute('SELECT payload FROM results').fetchone()[0]),result)
            finally:
                server.DB = original
                server.SESSIONS.clear()

if __name__ == '__main__':
    unittest.main()
