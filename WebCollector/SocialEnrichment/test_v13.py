"""Offline regression tests; no network and no changes to Excel/CSV."""
import unittest
from unittest.mock import patch
import social_enrichment as se

class Response:
    def __init__(self,code,location=None,body='<html><h1>Айдерханов Вадим Амирович</h1><a href="https://vk.com/athlete_vadim">Тренер во «ВКонтакте»</a><footer><a href="https://vk.com/club">ВКонтакте</a></footer><h2>Другие тренеры</h2><a href="https://vk.com/other">Другой</a></html>'):
        self.status_code=code;self.headers={'Content-Type':'text/html'}
        if location:self.headers['Location']=location
        self.text=body
    def raise_for_status(self):
        if self.status_code>=400:raise RuntimeError(f'HTTP {self.status_code}')

class Client:
    def __init__(self):self.urls=[]
    def get(self,url,timeout,allow_redirects):
        self.urls.append(url)
        if url.endswith('/robots.txt'):return Response(200,body='User-agent: *\nAllow: /')
        if url.endswith('/ayderhanov-vadim-amirovich'):return Response(301,location='/trenery/ayderhanov-vadim-amirovich/')
        return Response(200)

class Tests(unittest.TestCase):
    def test_slash_redirect(self):
        c=Client()
        html,url=se.get_public_html(c,'https://regymsport.ru/trenery/ayderhanov-vadim-amirovich',{})
        self.assertEqual(url,'https://regymsport.ru/trenery/ayderhanov-vadim-amirovich/')
        self.assertEqual(len(c.urls),3)
        links=se.extract(html,url,'Айдерханов Вадим Амирович')
        self.assertEqual([x['profile_url'] for x in links],['https://vk.com/athlete_vadim'])
    def test_name_mismatch(self):
        url='https://regymsport.ru/trenery/test/'
        self.assertEqual(se.extract(Response(200).text,url,'Другой Тренер'),[])
    def test_unsafe_cross_site(self):
        c=Client()
        def get(url,timeout,allow_redirects):
            if url.endswith('robots.txt'):return Response(200,body='User-agent: *\nAllow: /')
            return Response(301,location='https://different-site.example/private')
        c.get=get
        with self.assertRaises(se.UnsafeRedirect):
            se.get_public_html(c,'https://regymsport.ru/trenery/test',{})
    def test_fetch_preserves_query_and_slash(self):
        self.assertEqual(se.safe_fetch_url('https://regymsport.ru/trenery/test/?x=1'), 'https://regymsport.ru/trenery/test/?x=1')
        self.assertEqual(se.normalized('https://regymsport.ru/trenery/test/?x=1'), 'https://regymsport.ru/trenery/test')
    def test_disallow_still_blocks(self):
        class C:
            def get(self,url,timeout,allow_redirects):
                if url.endswith('robots.txt'):return Response(200,body='User-agent: *\nDisallow: /trenery/')
                raise AssertionError('should not fetch disallowed page')
        with self.assertRaises(se.RobotsDisallowed):
            se.get_public_html(C(),'https://regymsport.ru/trenery/test/',{})

if __name__=='__main__':unittest.main(verbosity=2)
