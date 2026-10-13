import io
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs
import server


class ReviewTests(unittest.TestCase):
    def test_optional_and_rating_separate(self):
        movie = server.clean_movie({'title': '测试', 'rating': 8.2, 'personalRating': 5}, 'test')
        self.assertEqual(movie['rating'], 8.2)
        self.assertEqual(movie['personalRating'], 5)
        fields = server.douban_interest_fields('test', 'watched')
        self.assertEqual(fields['rating'], '')
        self.assertEqual(fields['comment'], '')
        self.assertNotIn('private', fields)

    def test_review_validation(self):
        value = server.clean_review({'tags': '剧情  科幻\t剧情', 'comment': '😀' * 350})
        self.assertEqual(value['tags'], ['剧情', '科幻'])
        for invalid in ({'comment': '字' * 351}, {'personalRating': 6}, {'personalRating': True}, {'personalRating': 2.5}, {'doubanPrivate': 'false'}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                server.clean_review(invalid)

    def test_payload_and_other_statuses(self):
        review = {'personalRating': 4, 'tags': ['剧情', '科幻'], 'comment': '很好看', 'doubanPrivate': True}
        fields = server.douban_interest_fields('test', 'watched', review)
        self.assertEqual((fields['rating'], fields['tags'], fields['comment'], fields['private']), ('4', '剧情 科幻', '很好看', 'on'))
        for status, expected in [('want', 'wish'), ('doing', 'do')]:
            fields = server.douban_interest_fields('test', status)
            self.assertEqual(fields['interest'], expected)
            self.assertEqual(fields['rating'], '')
            self.assertNotIn('private', fields)

    def test_real_post_encodes_review(self):
        opener = Mock()
        opener.open.side_effect = [io.BytesIO(b''), io.BytesIO(b'{"r":0}')]
        with patch.object(server, 'opener_from_cookies', return_value=(opener, None)), patch.object(server, 'jar_dict', return_value={'ck': 'test'}), patch.object(server, 'save_douban_session'):
            server.mark_douban_interest({'ck': 'test'}, '123', 'watched', {'personalRating': 5, 'comment': '短评 & 测试', 'doubanPrivate': True})
        request = opener.open.call_args.args[0]
        body = parse_qs(request.data.decode())
        self.assertEqual(body['rating'], ['5'])
        self.assertEqual(body['comment'], ['短评 & 测试'])
        self.assertEqual(body['private'], ['on'])

    def test_legacy_edit_preserves_review(self):
        old = server.clean_movie({'title': '测试', 'personalRating': 4, 'tags': ['剧情'], 'comment': '保留', 'doubanPrivate': True}, 'test')
        handler = Mock()
        handler.require_auth.return_value = True
        handler.read_json.return_value = {'title': '改标题'}
        with patch.object(server, 'load_movies', return_value=[old]), patch.object(server, 'save_movies') as save, patch.object(server, 'enrich_movie', side_effect=lambda x: x):
            server.Handler.handle_update(handler, 'test')
        updated = save.call_args.args[0][0]
        for key in ('personalRating', 'tags', 'comment', 'doubanPrivate'):
            self.assertEqual(updated[key], old[key])


if __name__ == '__main__':
    unittest.main()
