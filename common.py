import typing
from collections import UserList


class CheckResult(typing.NamedTuple):
    valid: bool
    msg: str


class CheckResults(UserList):
    @property
    def valid(self):
        return all(_.valid for _ in self.data)

    @property
    def msg(self):
        return ", ".join([str(_.msg) for _ in self.data])


class HrefLang(typing.NamedTuple):
    href: str
    language: str


class ValidatedLink(typing.NamedTuple):
    valid: bool
    url: typing.Optional[str]
    error: typing.Optional[str]


def is_page_in_hreflang(page: str, hreflangs: typing.List[HrefLang]) -> bool:
    return page in [_.href for _ in hreflangs]


def get_hreflang_for_page(
    page: str, hreflangs: typing.List[HrefLang]
) -> typing.Optional[HrefLang]:
    for h in hreflangs:
        if h.href == page:
            return h


class Page(typing.NamedTuple):
    url: str
    alts: typing.List[HrefLang]


class SitemapCheckResult(typing.NamedTuple):
    valid: bool
    msg: str


def get_alts_for_link(link: str, pages: typing.Iterable[Page]) -> typing.List[HrefLang]:
    return getattr(next(iter(_ for _ in pages if _.url == link), None), "alts", [])


def get_hreflang_for_link(
    link: str, hreflangs: typing.List[HrefLang]
) -> typing.Optional[HrefLang]:
    for hreflang in hreflangs:
        if link == hreflang.href:
            return hreflang
    return None
