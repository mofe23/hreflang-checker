from urllib.parse import urlparse
import time
from urllib.robotparser import RobotFileParser
import typing

import validators
import logging

from page_check import PageCheck
from common import CheckResult

logger = logging.getLogger(__name__)


class Crawler:
    def __init__(self, page):
        self.root = page
        self.parsed_uri = urlparse(page)
        self.home_page = "{uri.scheme}://{uri.netloc}/".format(uri=self.parsed_uri)
        self.to_crawl = set()
        self.crawled = set()
        rp = RobotFileParser()
        rp.set_url(self.home_page + "robots.txt")
        rp.read()
        self.rp = rp

    def crawl(self, page: str = None) -> typing.Iterable[CheckResult]:
        """the recursive crawler, it calls the hreflang check module, so if you want a free crawl validation, this is what you need"""
        page = page or self.root

        logger.info(
            f"{len(self.to_crawl)} pages in queue, {len(self.crawled)} done, current page {page}"
        )

        if validators.url(page):
            instance = PageCheck(page, self.rp)
            indexable = instance.indexable()
            yield from indexable
            if indexable.valid:
                yield from instance.validate_alts()
                self.to_crawl.update(instance.get_links().difference(self.crawled))
        else:
            yield CheckResult(valid=False, msg=f"{page} is a badly formed url")

        self.crawled.add(page)

        if len(self.to_crawl) > 0:
            yield from self.crawl(self.to_crawl.pop())
