"""Offline regression suite: no network and no project files are modified."""
import unittest
from unittest.mock import patch
import social_enrichment as se

SOURCE='https://regymsport.ru/trenery/varzaeva-anastasiya-pavlovna/'
HTML='''<html><head><title>Варзаева Анастасия Павловна</title></head><body>
<h1>Варзаева Анастасия Павловна</h1>
<div class="trainer-info"><a href="https://m.vk.ru/id2242272">Тренер во «ВКонтакте»</a>
<a href="https://t.me/nefs_up">Тренер в Telegram</a></div>
<footer><a href="https://vk.com/club">ВКонтакте</a><a href="https://t.me/club">Telegram</a></footer>
<section><h2>Другие тренеры</h2><a href="https://t.me/other">Тренер в Telegram</a></section>
<a href="https://t.me/share/url">Тренер в Telegram</a>
</body></html>'''

class Response:
    def __init__(self,code,location=None,body=HTML):
        self.status_code=code; self.headers={'Content-Type':'text/html'}
        if location:self.headers['Location']=location
        self.text=body
    def raise_for_status(self):
        if self.status_code>=400: raise RuntimeError(str(self.status_code))

class Client:
    def get(self,url,timeout,allow_redirects):
        if url.endswith('/robots.txt'): return Response(200,body='User-agent: *\nAllow: /')
        if url.endswith('varzaeva-anastasiya-pavlovna'):return Response(301,location='/trenery/varzaeva-anastasiya-pavlovna/')
        return Response(200)

class V14Tests(unittest.TestCase):
    def test_vk_and_telegram(self):
        links=se.extract(HTML,SOURCE,'Варзаева Анастасия Павловна')
        self.assertIn(('VK','https://m.vk.ru/id2242272'),[(x['platform'],x['profile_url']) for x in links])
        self.assertIn(('Telegram','https://t.me/nefs_up'),[(x['platform'],x['profile_url']) for x in links])
    def test_club_footer_and_invalid_skipped(self):
        links=se.extract(HTML,SOURCE,'Варзаева Анастасия Павловна')
        self.assertEqual(len(links),2)
    def test_wrong_name_skipped(self):
        self.assertEqual(se.extract(HTML,SOURCE,'Иван Иванов'),[])
    def test_trailing_slash_redirect(self):
        html,final=se.get_public_html(Client(),SOURCE.rstrip('/'),{})
        self.assertEqual(final,SOURCE)
        self.assertEqual(len(se.extract(html,final,'Варзаева Анастасия Павловна')),2)
    def test_shared_sites_rejected(self):
        self.assertEqual(se.extract(HTML,'https://tenchat.ru/vacancy','Варзаева Анастасия Павловна'),[])
    def test_profile_url_validation(self):
        self.assertEqual(se.platform_of('https://t.me/share/url'),None)
        self.assertEqual(se.platform_of('https://t.me/nefs_up'),'Telegram')
    def test_cross_domain_redirect_blocked(self):
        class Bad:
            def get(self,url,timeout,allow_redirects):
                if url.endswith('/robots.txt'):return Response(200,body='User-agent: *\nAllow: /')
                return Response(302,location='https://elsewhere.example/path')
        with self.assertRaises(se.UnsafeRedirect):se.get_public_html(Bad(),SOURCE,{})

if __name__=='__main__':unittest.main(verbosity=2)
