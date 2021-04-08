import gzip
import urllib.parse
from bs4 import BeautifulSoup
import typing
import requests

import logging

from common import (
    Page,
    CheckResult,
    get_alts_for_link,
    get_hreflang_for_link,
    HrefLang,
)

logger = logging.getLogger(__name__)


class Sitemap:
    def __init__(self, page):
        self.current_page = page
        self.parsed_uri = urllib.parse.urlparse(page)
        self.home_page = "{uri.scheme}://{uri.netloc}/".format(uri=self.parsed_uri)
        self.roboter = self.home_page + "robots.txt"

    def check_robots_for_sitemap(self):
        """get the sitemaps, this will only return what is pointed to in robots, if they are sitemap indexes then that is what is returned"""
        sitemaps = []
        r = requests.get(self.roboter)
        lines = r.content.split(b"\n")
        for line in lines:
            if "Sitemap:" in line.decode("utf-8"):
                sitemaps.append(line.decode("utf-8").split(" ")[1].replace("\r", ""))
        if len(sitemaps) == 0:
            logger.info("no sitemaps in the robots file")
            return False
        else:
            return sitemaps

    def get_sitemaps(self) -> typing.List[str]:
        """this checks if the robots sitemaps are sitemap indexes and if so, parses them to get the actual sitemaps
        it only checks on one level, so if you a sitemap index of sitemap indexes this gets wonky
        """
        sitemaps_now = self.check_robots_for_sitemap()
        sitemaps = []
        if sitemaps_now is not False:
            for sitemap in sitemaps_now:
                r = requests.get(sitemap)
                soup = BeautifulSoup(r.content, "lxml")
                if soup.find("sitemapindex"):
                    sitemaps.extend(loc.text for loc in soup.find_all("loc"))
                else:
                    sitemaps.append(sitemap)
        else:
            logger.info("no sitemaps in the robots file")
        return sitemaps

    def get_pages(self, sitemaps: typing.List[str]) -> typing.Iterable[Page]:
        """does the heavy lifting, grabs all sitemaps, parses them into a workable dictionary"""
        for sitemap in sitemaps:
            logger.info("downloading sitemap :" + sitemap)
            r = requests.get(sitemap)
            if "Content-Type" in r.headers and "gz" in r.headers["Content-Type"]:
                content = gzip.decompress(r.content)
            else:
                content = r.content
            soup = BeautifulSoup(content, "lxml")
            for url in soup.find_all("url"):
                yield Page(
                    url=url.find("loc").text,
                    alts=[
                        HrefLang(href=alt["href"], language=alt["hreflang"])
                        for alt in url.find_all(attrs={"rel": "alternate"})
                    ],
                )

    def check_self_ref(self, page: Page) -> typing.Iterable[CheckResult]:
        """checks all sitemap urls with hreflang for a self reference"""
        msg = f"{page.url} is missing self reference"
        valid = False
        if page.url in [_.href for _ in page.alts]:
            msg = f"{page.url} has self reference"
            valid = True
        yield CheckResult(msg=msg, valid=valid)

    def check_link_in_map(
        self, page: Page, pages: typing.List[Page]
    ) -> typing.Iterable[CheckResult]:
        """checks that links pointed to in hreflang are also in the sitemap"""
        urls = list(_.url for _ in pages)
        for alt in page.alts:
            msg = alt.href + " is is pointed to but has no corresponding url element"
            valid = False
            if alt.href in urls:
                valid = True
                msg = alt.href + " is in and has a corresponding url element"
            yield CheckResult(msg=msg, valid=valid)

    def check_return(
        self, page: Page, pages: typing.List[Page]
    ) -> typing.Iterable[CheckResult]:
        """checks if alternates exist and have alternates pointing back to the origin"""
        for alt in page.alts:
            msg = page.url + " points to " + alt.href + " but not return"
            valid = False

            if page.url in [_.href for _ in get_alts_for_link(alt.href, pages)]:
                msg = (
                    page.url
                    + " points to "
                    + alt.href
                    + " and has link pointing back to it"
                )
                valid = True
            yield CheckResult(msg=msg, valid=valid)

    def check_target(
        self, page: Page, pages: typing.List[Page]
    ) -> typing.Iterable[CheckResult]:
        """checks if alternates exist, then if they do ensures that the origins
        targeting is the same as the targeting applied by the alternate"""
        urls = [_.url for _ in pages]
        for alt in page.alts:
            if alt.href not in urls:
                continue  # Ensure link in map: check_link_in_map
            backlinks = get_alts_for_link(alt.href, pages)
            if page.url not in [_.href for _ in backlinks]:
                continue  # Ensure alternates exist an point back: check_return

            hreflang = get_hreflang_for_link(alt.href, backlinks)
            msg = (
                page.url
                + "url with target "
                + alt.language
                + " is pointed to with target "
                + hreflang.language
            )
            valid = hreflang and alt.language == hreflang.language
            yield CheckResult(msg=msg, valid=valid)

    def check_data(self) -> typing.Iterable[CheckResult]:
        """loops through each url in sitemap applying checks to each, updates dict with "checks" which have data on errors"""
        sitemaps = self.get_sitemaps()
        pages = list(self.get_pages(sitemaps))
        logger.info(f"Found {len(sitemaps)} sitemaps referencing {len(pages)} pages")
        for page in pages:
            yield from self.check_self_ref(page)
            yield from self.check_link_in_map(page, pages)
            yield from self.check_return(page, pages)
            yield from self.check_target(page, pages)
