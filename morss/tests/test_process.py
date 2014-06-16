from unittest import TestCase, main as unittest_main

from morss import morss


class TestProcess(TestCase):
    def test_news_com_au(self):
        result = morss.process('http://feeds.news.com.au/public/rss/2.0/news_national_3354.xml')
        self.assertGreaterEqual(result.count('description'), 1)


if __name__ == '__main__':
    unittest_main()
