import unittest

from src.browser.fetch_x import extract_posts_from_html
from src.browser.runner import BrowserRunner, StaticHtmlAdapter
from src.config import Settings


SAMPLE_HTML = '''
<html><body>
  <article data-post-id="1" data-author="Addy Osmani" data-handle="addyosmani" data-followers="400000">
    <a href="https://x.com/addyosmani/status/1">link</a>
    Addy explains browser performance today.
  </article>
  <article data-post-id="2" data-author="Matt Pocock" data-handle="mattpocockuk" data-followers="120000">
    <a href="https://x.com/mattpocockuk/status/2">link</a>
    Typescript tooling is getting better.
  </article>
</body></html>
'''


class BrowserRunnerTests(unittest.TestCase):
    def test_extract_posts_prefers_tweet_text(self):
        html = '''
        <html><body>
          <article data-post-id="9" data-author="Tak" data-handle="cherry_mx_reds" data-followers="1234">
            <div data-testid="tweetText">
              <span>Tak @cherry_mx_reds · Apr 12</span>
              <span>It’s really hard to use Azure.</span>
              <span>104 8 235 52K</span>
            </div>
            <a href="/cherry_mx_reds/status/9">link</a>
          </article>
        </body></html>
        '''
        posts = extract_posts_from_html(html)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].text, 'It’s really hard to use Azure.')
        self.assertEqual(posts[0].url, 'https://x.com/cherry_mx_reds/status/9')

    def test_collect_home_uses_adapter_and_parser(self):
        settings = Settings(scroll_count=3, scroll_pause_seconds=0.0)
        runner = BrowserRunner(settings)
        adapter = StaticHtmlAdapter(SAMPLE_HTML)
        posts = runner.collect_home(adapter)
        self.assertEqual(len(posts), 2)
        self.assertEqual(adapter.current_url, 'https://x.com/')
        self.assertEqual(adapter.scrolled, 3)
        self.assertEqual(posts[0].author, 'Addy Osmani')
        self.assertEqual(posts[0].url, 'https://x.com/addyosmani/status/1')
        self.assertEqual(posts[1].handle, 'mattpocockuk')
        self.assertEqual(posts[1].url, 'https://x.com/mattpocockuk/status/2')
