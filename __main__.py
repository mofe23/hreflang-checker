import sys
import urllib.robotparser as robotparser
from crawler import Crawler
from sitemap import Sitemap
from common import CheckResult, CheckResults
import typing
import logging

logger = logging.getLogger(__name__)

usage = """\
python3 __main__.py https://www.femsense.com
"""


def exit_wrong_usage():
    print(usage)
    sys.exit(1)


def format_result(result: typing.Union[CheckResult, CheckResults]):
    symbol = "✅" if result.valid else "❌"
    return f"\t{symbol} {check.msg}"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 2:
        exit_wrong_usage()

    site = sys.argv[1]

    crawler = Crawler(site)
    sitemap = Sitemap(site)

    results = [*crawler.crawl()]
    print("Dere!")
    for n, check in enumerate(results):
        # if not check.valid:
        print(f"{n: 4d} {format_result(check)}")
