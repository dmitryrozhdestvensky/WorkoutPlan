import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import collect_spiritfitness as m

class CollectorTests(unittest.TestCase):
    def test_regions(self):
        self.assertEqual(m.trainer_url('https://spiritfit.ru/coaches/kosareva-stanislava/', 'Санкт-Петербург'), 'https://spiritfit.ru/spb/coaches/kosareva-stanislava/')
        self.assertEqual(m.trainer_url('https://spiritfit.ru/coaches/name/', 'Екатеринбург'), 'https://spiritfit.ru/ekb/coaches/name/')
        self.assertEqual(m.trainer_url('https://spiritfit.ru/coaches/name/', 'Москва'), 'https://spiritfit.ru/coaches/name/')
        self.assertEqual(m.trainer_url('https://spiritfit.ru/coaches/specialization/functional', 'Москва'), '')
    def test_names(self):
        self.assertFalse(m.valid_profile_name('Страница не найдена'))
        self.assertFalse(m.valid_profile_name('404 Not Found'))
        self.assertTrue(m.valid_profile_name('КОРОЛЕВА ЕКАТЕРИНА'))
    def test_migrate_without_deleting(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(m, 'ROOT', Path(d)), patch.object(m,'DB',Path(d)/'test.sqlite3'), patch.object(m,'CSV',Path(d)/'out.csv'), patch.object(m,'ERRORS',Path(d)/'errors.csv'):
                con=m.connect()
                url='https://spiritfit.ru/coaches/kosareva-stanislava/'
                m.discover(con,url,'Санкт-Петербург',m.CITY_PAGES['Санкт-Петербург'])
                con.execute("UPDATE source_profiles SET status='collected',name='Страница не найдена' WHERE url=?",(url,))
                con.commit()
                result=m.repair_db(con)
                self.assertEqual(result['requeued_regional'],1)
                target=m.trainer_url(url,'Санкт-Петербург')
                self.assertEqual(con.execute('SELECT status FROM source_profiles WHERE url=?',(url,)).fetchone()[0],'superseded')
                self.assertEqual(con.execute('SELECT status FROM source_profiles WHERE url=?',(target,)).fetchone()[0],'queued')
                self.assertEqual(m.write_csv(con),0)
                self.assertEqual(m.repair_db(con)['requeued_regional'],0)
                self.assertEqual(con.execute('SELECT count(*) FROM source_profiles').fetchone()[0],2)
                con.close()
if __name__=='__main__': unittest.main()
