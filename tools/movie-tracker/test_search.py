import io
import json
import unittest
from unittest.mock import patch, Mock
import server


class SearchTests(unittest.TestCase):
    def fetch(self, items, total, start=0):
        payload = {'items': items, 'total': total}
        with patch.object(server, 'attach_search_intros'), patch.object(server.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps(payload).encode())) as request:
            page = server.suggest_douban('假面骑士', start)
        self.assertIn('start=' + str(start), request.call_args.args[0].full_url)
        return page

    def test_subtitle_and_intro(self):
        payload = {'items': [{
            'target_type': 'movie',
            'target': {
                'id': '1292052',
                'title': '肖申克的救赎',
                'year': '1994',
                'card_subtitle': '1994 / 美国 / 剧情 犯罪 / 弗兰克·德拉邦特 / 蒂姆·罗宾斯 摩根·弗里曼',
            },
        }], 'total': 1}
        detail = {'intro': '一场谋杀案使银行家安迪蒙冤入狱。' * 20}

        def open_url(req, timeout=10):
            raw = detail if '/movie/1292052' in req.full_url else payload
            return io.BytesIO(json.dumps(raw).encode())

        with patch.object(server.urllib.request, 'urlopen', side_effect=open_url):
            page = server.suggest_douban('肖申克', 0)
        item = page['results'][0]
        self.assertEqual(item['director'], '弗兰克·德拉邦特')
        self.assertEqual(item['actors'], '蒂姆·罗宾斯 / 摩根·弗里曼')
        self.assertEqual(item['regions'], '美国')
        self.assertEqual(item['intro'], '一场谋杀案使银行家安迪蒙冤入狱。' * 20)

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
