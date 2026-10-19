from pathlib import Path

path = Path('etl4/database/tests/test_database_contracts.py')
s = path.read_text(encoding='utf-8')
needle = "                cls.a=make_synthetic(c,cls.first,1); cls.b=make_synthetic(c,cls.first,2)"
s = s.replace(needle, '''                from _publication import stage_release
                members = [{'dataset_id': h['metadata']['dataset']['id'],
                            'dataset_revision_id': h['metadata']['dataset_revision']['id']} for h in cls.prepared]
                cls.base_release = stage_release(c, members, 'local_base_v2')
                cls.single_release = stage_release(c, members[:1], 'local_base_v2')
''' + needle)
s = s.replace("        with connection() as c: active=str(c.execute('SELECT release_id FROM core.active_release').fetchone()['release_id'])\n        with TestClient(create_app()) as client:", "        active = self.base_release\n        with TestClient(create_app(self.lab)) as client:")
a = s.index('        with connection() as c: before=')
b = s.index('    def test_previous_single_hole_release_remains_readable', a)
s = s[:a] + '''        with connection(dbname=self.lab) as c:
            c.execute('INSERT INTO core.active_release(singleton,release_id) VALUES (true,%s)', (self.base_release,))
        try:
            with patch('_verification.api_checks',side_effect=ValueError('simulated API verification failure')):
                with self.assertRaisesRegex(ValueError,'simulated API verification failure'):
                    verify_and_publish(['05KCD001'], dbname=self.lab, check_api=True)
            with connection(dbname=self.lab) as c:
                after = str(c.execute('SELECT release_id FROM core.active_release').fetchone()['release_id'])
            self.assertEqual(self.base_release, after)
        finally:
            with connection(dbname=self.lab) as c:
                c.execute('DELETE FROM core.active_release')

''' + s[b:]
s = s.replace("previous=read(REPORTS/'10_verified_05KCD001.json')['release_id']\n        with TestClient(create_app()) as client:", "previous=self.single_release\n        with TestClient(create_app(self.lab)) as client:")
path.write_text(s, encoding='utf-8')
