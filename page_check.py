import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import re
import validators
import typing

from common import (
    CheckResult,
    CheckResults,
    HrefLang,
    ValidatedLink,
    is_page_in_hreflang,
    get_hreflang_for_page,
)
import logging

logger = logging.getLogger(__name__)


class PageCheck:
    def __init__(self, page: str, rp):
        """
        get all the page data, only want to do this once so stuck it in the init to have the data throughout
        :param page:
        :param rp:
        """
        self.page = page
        self.parsed_uri = urlparse(page)
        self.home_page = "{uri.scheme}://{uri.netloc}/".format(uri=self.parsed_uri)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
        }
        self.request = requests.get(
            self.page, allow_redirects=False, headers=self.headers
        )
        self.soup = BeautifulSoup(self.request.content, "lxml")
        self.rp = rp

    # returns true and 200 if 200, otherwise returns false and the status code
    def check_status(self) -> CheckResult:
        return CheckResult(
            valid=self.request.status_code == 200,
            msg=f"{self.page} returned status code {self.request.status_code}",
        )

    # returns true if none or the same as the page, returns false and the canonical otherwise
    def check_canonical(self) -> CheckResult:
        canonical_element = self.soup.find("link", {"rel": "canonical"}) or {}
        canonical_link = canonical_element.get("href", "No canonical link")
        valid = canonical_link == self.page
        return CheckResult(
            valid=valid, msg=f"{self.page} has canonical {canonical_link}"
        )

    # ensures the page is not blocked by robots returns Bool and directive
    def check_robots(self) -> CheckResult:
        robots_element = self.soup.find("meta", {"name": "robots"}) or {}
        robot_directive = robots_element.get("content", None)
        valid = robot_directive is None or any(
            x in robot_directive.lower() for x in ["no index", "noindex"]
        )
        return CheckResult(
            valid=valid,
            msg=f"{self.page} has robot {robot_directive or 'No robot info'}",
        )

    # ensures the page is not blocked by robots txt, is a little awkward cause the library is initialized globally to
    # avoid having to hit again for each page, hopefully will get a better solution later
    def check_txt(self) -> CheckResult:
        valid = self.rp.can_fetch("*", self.page)
        msg = "is allowed by robots.txt" if valid else "is forbidden by robots.txt"
        return CheckResult(valid=valid, msg=f"{self.page} {msg}")

    # calls the previous few functions to return a simple is it indexable or not
    def indexable(self) -> CheckResults:
        return CheckResults(
            [
                self.check_status(),
                self.check_canonical(),
                self.check_robots(),
                self.check_txt(),
            ]
        )

    # takes a few links formats and returns an absolute, may have missed some formats, it should notify if so
    def validate_link(self, link: str) -> ValidatedLink:
        link_parts = urlparse(link)
        valid = False
        error = "Nope"
        url = None
        if "#" in link:
            error = "Filtered fragment"
        elif "?" in link:
            error = f"Filtered because of query parameters {link}"
        elif not link.endswith((".html", "/")):
            error = f"Filtered because of extension {link}"
        elif (
            self.parsed_uri.scheme == link_parts.scheme
            and self.parsed_uri.netloc == link_parts.netloc
        ):
            valid = True
            url = link
        elif link_parts.scheme == "" and link_parts.netloc == "" and link[0] == "/":
            valid = True
            url = "{}://{}{}".format(
                self.parsed_uri.scheme, self.parsed_uri.netloc, link
            )
        elif link_parts.scheme == "" and link_parts.netloc == "":
            valid = True
            url = "{}://{}/{}".format(
                self.parsed_uri.scheme, self.parsed_uri.netloc, link
            )
        elif link_parts.scheme == "" and link_parts.netloc == self.parsed_uri.netloc:
            valid = True
            url = "{}:{}".format(self.parsed_uri.scheme, link)
        elif (
            link_parts.netloc is not None
            and link_parts.netloc != self.parsed_uri.netloc
        ):
            error = "nope"
        else:
            error = "did not account for this one:" + link

        return ValidatedLink(valid=valid, url=url, error=error)

    # grabs the links on the page, calls the validation on them so should only produce absolute links
    def get_links(self) -> typing.Set[str]:
        links = set()
        for link in self.soup.find_all("a", {"href": True}):
            checked_link = self.validate_link(link["href"].strip())
            if checked_link.valid:
                links.add(checked_link.url)
        return links

    # gets the hreflang data from a page
    def get_hreflangs(self) -> typing.List[HrefLang]:
        hreflangs: typing.List[HrefLang] = []
        for tag in self.soup.find_all("link", {"hreflang": re.compile(r".*")}):
            try:
                hreflangs.append(HrefLang(language=tag["hreflang"], href=tag["href"]))
            except KeyError:
                pass
        return hreflangs

    # checks the hreflang on a page includes a self referring tag
    def check_self(self) -> bool:
        return is_page_in_hreflang(self.page, self.get_hreflangs())

    def create_alt_instances(self) -> typing.Iterable["PageCheck"]:
        """create a new instance for each of the alts (yea recursion biatch)"""
        hreflangs = self.get_hreflangs()
        for hreflang in hreflangs:
            if validators.url(hreflang.href):
                yield PageCheck(hreflang.href, self.rp)
            else:
                logger.info("badly formed link " + hreflang.href)

    def check_return(self, alt: "PageCheck") -> CheckResult:
        """checks that alternate pages being pointed to also point back"""
        valid = is_page_in_hreflang(self.page, alt.get_hreflangs())
        if valid:
            msg = f"{self.page} has return link from {alt.page}"
        else:
            msg = f"{self.page} missing return link from {alt.page}"
        return CheckResult(valid=valid, msg=msg)

    def check_alts_self(self, alt: "PageCheck") -> CheckResult:
        """ensure alts have self referring tags"""
        valid = alt.check_self()
        if valid:
            msg = f"{self.page} points to page {alt.page} which has it's self-reference"
        else:
            msg = f"{self.page} points to page {alt.page} which is missing it's self references"
        return CheckResult(msg=msg, valid=valid)

    def check_alts_indexable(self, alt: "PageCheck") -> CheckResult:
        """ensure pages being pointed to are indexable"""
        valid = alt.indexable().valid
        if valid:
            msg = f"{self.page} points to indexable page {alt.page}"
        else:
            msg = f"{self.page} points to non-indexable page {alt.page}"
        return CheckResult(msg=msg, valid=valid)

    def check_targeting(self, alt: "PageCheck") -> CheckResult:
        """checks if alternate pages all use the same code as the page we are checking when pointing to it"""
        target = get_hreflang_for_page(self.page, self.get_hreflangs())
        hreflang = get_hreflang_for_page(self.page, alt.get_hreflangs())
        valid = hreflang == target
        if valid:
            msg = f"{self.page} has page {alt.page} pointing to it with hreflang {getattr(hreflang, 'language', 'Not found')}"
        else:
            msg = f"{self.page} has page {alt.page} pointing to it with the wrong locale {getattr(hreflang, 'language', 'Not found')}"
        return CheckResult(msg=msg, valid=valid)

    def validate_alts(self) -> typing.Iterable[CheckResult]:
        """calls a few hreflang checking functions for the page we are on"""
        for alt in self.create_alt_instances():
            yield self.check_return(alt)
            yield self.check_alts_self(alt)
            yield self.check_alts_indexable(alt)
            yield self.check_targeting(alt)
