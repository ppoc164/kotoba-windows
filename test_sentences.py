import unittest
from sentences import split_sentences, to_srt


class SentenceTests(unittest.TestCase):
    def test_punctuation_and_pause(self):
        rows = split_sentences([dict(words=[
            dict(start=0, end=.5, text='你好。'), dict(start=.6, end=1, text=' Hello'),
            dict(start=1, end=2, text=' world!'), dict(start=4, end=5, text='尾句')])])
        self.assertEqual([r['text'] for r in rows], ['你好。', 'Hello world!', '尾句'])
        self.assertEqual(rows[1]['start'], .6)
        self.assertEqual(rows[1]['end'], 2)

    def test_cross_segment_sentence(self):
        rows = split_sentences([dict(start=0, end=1, text=' A'), dict(start=1.1, end=2, text=' sentence.')])
        self.assertEqual(rows, [dict(start=0, end=2, text='A sentence.')])

    def test_empty_and_subtitles(self):
        self.assertEqual(split_sentences([]), [])
        self.assertIn('00:00:01,250 --> 00:00:02,500', to_srt([dict(start=1.25, end=2.5, text='测试')]))


if __name__ == '__main__':
    unittest.main()
