import unittest
from social_enrichment import platform_of, source_is_shared_listing, candidate_reason, extract
class Tests(unittest.TestCase):
 def test_unsafe_links(self):
  for u in ['https://tenchat.ru/media/123','https://tenchat.ru/vacancy','https://tenchat.ru/wallet/partners','https://t.me/abc/1576','https://ok.ru/dk','https://ok.ru/profile/123/members']:
   self.assertIsNone(platform_of(u),u)
 def test_valid_profiles(self):
  for u in ['https://t.me/tanya_yourfit_recipes','https://www.instagram.com/tanya_yourfit','https://tenchat.ru/denischernoguzov','https://ok.ru/profile/123']:
   self.assertIsNotNone(platform_of(u),u)
 def test_listing(self):
  self.assertTrue(source_is_shared_listing('https://tenchat.ru/resume/moskva/trener-po-fitnesu'))
  self.assertTrue(source_is_shared_listing('https://ok.ru/group/70000003305405'))
  self.assertTrue(source_is_shared_listing('https://t.me/s/shugaev999'))
  self.assertFalse(source_is_shared_listing('https://4yourfit.pro/tg'))
 def test_extract_listing(self):
  html='<h1>Иван Иванов</h1><a href="https://tenchat.ru/stranger">Ссылка</a>'
  self.assertEqual(extract(html,'https://tenchat.ru/resume/moskva/trener-po-fitnesu','Иван Иванов'),[])
 def test_candidate(self):
  self.assertTrue(candidate_reason({'platform':'TenChat','profile_url':'https://tenchat.ru/abc','evidence_page':'https://tenchat.ru/resume/moskva/trener-po-fitnesu'}).startswith('reject_'))
  self.assertEqual(candidate_reason({'platform':'Instagram','profile_url':'https://instagram.com/tanya_yourfit','evidence_page':'https://4yourfit.pro/tg'}),'review_source_link_not_owner_verified')
if __name__=='__main__': unittest.main()
