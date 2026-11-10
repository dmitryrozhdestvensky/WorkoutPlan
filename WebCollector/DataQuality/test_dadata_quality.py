import unittest
from dadata_quality import norm,selection
class Tests(unittest.TestCase):
 def test_norm(self): self.assertEqual(norm('  Иван   Петров '),'иван петров')
 def test_selection(self):
  rows=[{'row':2,'original_name':'Анна Иванова','city':'','clubs':''},{'row':3,'original_name':'Петров Иван Иванович','city':'Москва','clubs':''}]
  self.assertEqual(selection(rows,1)[0]['row'],2)
if __name__=='__main__':unittest.main()
