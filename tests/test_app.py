import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent.parent


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Path(self.temp.name)
        salt = '00' * 16
        config = {'secret': 'ab' * 32, 'salt': salt, 'password': hashlib.pbkdf2_hmac('sha256', b'test-password', bytes.fromhex(salt), 600000).hex()}
        (self.store / 'config.json').write_text(json.dumps(config))
        self.cookie = ''

    def tearDown(self):
        self.temp.cleanup()

    def request(self, route, form=None, cookie=None, query=''):
        body = urlencode(form or {}).encode()
        env = dict(os.environ, BUDGET_STORAGE=str(self.store), SCRIPT_NAME='/budget/' + route + '.cgi', REQUEST_METHOD='POST' if form is not None else 'GET', CONTENT_LENGTH=str(len(body)), HTTP_COOKIE=self.cookie if cookie is None else cookie, QUERY_STRING=query)
        proc = subprocess.run(['python3', str(ROOT / 'public' / (route + '.cgi'))], input=body, env=env, capture_output=True, check=True)
        headers, content = proc.stdout.decode().split('\r\n\r\n', 1)
        return headers, content

    def login_and_projects(self):
        headers, content = self.request('admin')
        self.cookie = re.search(r'Set-Cookie: (budget_voter=[^;]+)', headers)[1]
        csrf = re.search(r'name="csrf" value="([^"]+)"', content)[1]
        headers, _ = self.request('admin', {'csrf': csrf, 'action': 'login', 'password': 'test-password'})
        self.cookie += '; ' + re.search(r'Set-Cookie: (budget_admin=[^;]+)', headers)[1]
        _, content = self.request('admin', {'csrf': csrf, 'action': 'save', 'items': 'Zeleň\nŠkoly\n<script>alert(1)</script>'})
        self.assertIn('Položky byly uloženy', content)
        return csrf

    def ballot(self, cookie=None):
        headers, content = self.request('index', cookie=cookie)
        voter_cookie = re.search(r'Set-Cookie: (budget_voter=[^;]+)', headers)[1]
        return voter_cookie, {name: re.search('name="' + name + '" value="([^"]+)"', content)[1] for name in ('csrf', 'revision')}

    def test_vote_validation_duplicate_totals_and_reset(self):
        csrf = self.login_and_projects()
        cookie, fields = self.ballot()
        fields.update({'amount-0': '2000', 'amount-1': '1000', 'amount-2': '0'})
        headers, _ = self.request('api', fields, cookie)
        self.assertIn('400 Bad Request', headers)
        fields['amount-2'] = '1000'
        _, content = self.request('api', fields, cookie)
        self.assertTrue(json.loads(content)['ok'])
        headers, _ = self.request('api', fields, cookie)
        self.assertIn('400 Bad Request', headers)
        _, content = self.request('api')
        self.assertEqual(json.loads(content)['totals'], [2000, 1000, 1000])
        _, content = self.request('admin', {'csrf': csrf, 'action': 'save', 'items': 'Nový'})
        self.assertIn('zahájením nového kola', content)
        self.request('admin', {'csrf': csrf, 'action': 'reset', 'items': 'Nový'})
        headers, _ = self.request('api', fields, cookie)
        self.assertIn('400 Bad Request', headers)
        self.assertEqual(json.loads(self.request('api')[1])['count'], 0)

    def test_csrf_unauthorized_and_escaping(self):
        self.login_and_projects()
        _, content = self.request('index', cookie='')
        self.assertIn('&lt;script&gt;', content)
        self.assertNotIn('<script>alert', content)
        headers, _ = self.request('admin', {'action': 'reset'}, cookie='')
        self.assertIn('400 Bad Request', headers)
        cookie, fields = self.ballot(cookie='')
        headers, _ = self.request('admin', dict(fields, action='reset', items='Oops'), cookie)
        self.assertIn('400 Bad Request', headers)

    def test_parallel_votes_are_not_lost(self):
        self.login_and_projects()
        ballots = [self.ballot(cookie='') for _ in range(12)]
        def cast(ballot):
            cookie, fields = ballot
            return self.request('api', dict(fields, **{'amount-0': '4000', 'amount-1': '0', 'amount-2': '0'}), cookie)
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            for headers, content in pool.map(cast, ballots):
                self.assertTrue(json.loads(content)['ok'])
        result = json.loads(self.request('api')[1])
        self.assertEqual(result['count'], 12)
        self.assertEqual(result['totals'], [48000, 0, 0])

    def test_missing_setup(self):
        (self.store / 'config.json').unlink()
        headers, content = self.request('index')
        self.assertIn('503 Service Unavailable', headers)
        self.assertIn('setup.py', content)

    def test_assets_work_without_config_and_reject_other_files(self):
        (self.store / 'config.json').unlink()
        for filename, mime in [('style.css', 'text/css'), ('app.js', 'application/javascript')]:
            headers, content = self.request('assets', query='file=' + filename)
            self.assertIn('200 OK', headers)
            self.assertIn(mime, headers)
            self.assertTrue(content)
        headers, _ = self.request('assets', query='file=../storage/config.json')
        self.assertIn('404 Not Found', headers)

    def test_index_serves_assets_without_config_with_executable_mime(self):
        (self.store / 'config.json').unlink()
        for filename, mime in [('app.js', 'application/javascript'), ('style.css', 'text/css')]:
            headers, body = self.request('index', query='asset=' + filename + '&v=4000')
            self.assertIn('200 OK', headers)
            self.assertIn('Content-Type: ' + mime, headers)
            self.assertNotIn('<!doctype html>', body)
        headers, _ = self.request('index', query='asset=../storage/config.json')
        self.assertIn('404 Not Found', headers)

    def test_million_precision_and_budget_limits(self):
        self.login_and_projects()
        cookie, fields = self.ballot()
        for values in [('4001', '0', '0'), ('-1', '4001', '0'), ('3999.5', '0.5', '0'), ('4', '0', '0')]:
            form = dict(fields, **{'amount-' + str(i): v for i, v in enumerate(values)})
            self.assertIn('400 Bad Request', self.request('api', form, cookie)[0])
        form = dict(fields, **{'amount-0': '2501', 'amount-1': '1499', 'amount-2': '0'})
        self.assertTrue(json.loads(self.request('api', form, cookie)[1])['ok'])
        result = json.loads(self.request('api')[1])
        self.assertEqual(result['total'], 4000)
        self.assertEqual(result['totals'], [2501, 1499, 0])

    def test_previous_budget_requires_new_round_without_losing_votes(self):
        self.login_and_projects()
        path = self.store / 'state.json'
        data = json.loads(path.read_text())
        data.pop('budget')
        data['votes']['old-voter'] = [2, 1, 1]
        path.write_text(json.dumps(data))
        self.assertIn('Připravujeme nové kolo', self.request('index')[1])
        result = json.loads(self.request('api')[1])
        self.assertEqual(result['total'], 4)
        self.assertEqual(result['count'], 1)

    def test_corrupt_storage_has_specific_diagnostic(self):
        (self.store / 'state.json').write_text('{broken')
        headers, content = self.request('api')
        self.assertIn('503 Service Unavailable', headers)
        self.assertIn('Soubor s hlasy je poškozený', json.loads(content)['error'])
        self.assertEqual((self.store / 'state.json').read_text(), '{broken')

    def test_corrupt_configuration_has_specific_diagnostic(self):
        (self.store / 'config.json').write_text('{}')
        headers, content = self.request('api')
        self.assertIn('503 Service Unavailable', headers)
        self.assertIn('Konfigurace úložiště je poškozená', json.loads(content)['error'])


if __name__ == '__main__':
    unittest.main()
