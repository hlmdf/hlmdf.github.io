import io
import json
import unittest
from unittest.mock import patch, Mock
import server


class SearchTests(unittest.TestCase):
    def fetch(self, items, total, start=0):
        payload = {'items': items, 'total': total}
        with patch.object(server.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps(payload).encode())) as request:
            page = server.suggest_douban('假面骑士', start)
        self.assertIn('start=' + str(start), request.call_args.args[0].full_url)
        return page

    def test_full_page_and_last_page(self):
        items = [{'target_type': 'tv', 'target': {'id': str(i), 'title': '剧集'}} for i in range(10)]
        page = self.fetch(items, 12)
        self.assertEqual(len(page['results']), 10)
        self.assertEqual(page['nextStart'], 10)
        self.assertTrue(page['hasMore'])
        last = self.fetch(items[:2], 12, 10)
        self.assertFalse(last['hasMore'])
        self.assertEqual(last['nextStart'], 12)
        self.assertFalse(self.fetch([], 0)['hasMore'])

    def test_cursor_counts_filtered_raw_entries(self):
        items = [{'target_type': 'person', 'target': {'id': '1'}}, {'target_type': 'movie', 'target': {'id': '2'}}]
        page = self.fetch(items, 20, 10)
        self.assertEqual(page['nextStart'], 12)
        self.assertEqual(len(page['results']), 1)
        self.assertTrue(page['hasMore'])

    def test_invalid_offset(self):
        for start in ('-1', 'bad', '100001'):
            handler = Mock()
            server.Handler.handle_suggest(handler, 'test', start)
            self.assertEqual(handler.send_json.call_args.args[1], 400)


if __name__ == '__main__':
    unittest.main()
