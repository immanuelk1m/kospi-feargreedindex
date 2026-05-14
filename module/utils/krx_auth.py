"""Authenticated KRX request helpers.

KRX MDC returns ``LOGOUT`` for many direct API calls unless the request is made
with a logged-in MDC session.  This module mirrors the session shape used by
newer pykrx releases while keeping credentials outside the repository: callers
must provide ``KRX_ID`` and ``KRX_PW`` through the environment.
"""

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

logger = logging.getLogger(__name__)

LOGIN_PAGE = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001.cmd"
LOGIN_JSP = "https://data.krx.co.kr/contents/MDC/COMS/client/view/login.jsp?site=mdc"
LOGIN_URL = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001D1.cmd"
KRX_HOST = "data.krx.co.kr"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_auth_session = None
_pykrx_proxy_installed = False


@dataclass
class KRXSession:
    """KRX authenticated session with bounded lifetime."""

    session: requests.Session = field(default_factory=requests.Session)
    login_time: float = field(default_factory=time.time)
    expiry_time: float = field(default_factory=lambda: time.time() + 3600)
    is_authenticated: bool = False

    def is_valid(self, buffer_seconds: int = 300) -> bool:
        return self.is_authenticated and time.time() < (self.expiry_time - buffer_seconds)

    def refresh(self, login_id: str, login_pw: str) -> bool:
        try:
            self.session.close()
        except Exception:
            logger.debug("KRX session close failed", exc_info=True)

        self.session = requests.Session()
        warmup_krx_session(self.session)
        success = login_krx(login_id, login_pw, self.session)

        if success:
            self.login_time = time.time()
            self.expiry_time = time.time() + 3600
            self.is_authenticated = True
            # MDC browser sessions include this flag after login. Supplying it is
            # harmless when KRX already set it, and keeps API requests aligned with
            # the logged-in browser request shape.
            if "mdc.client_session" not in self.session.cookies:
                self.session.cookies.set(
                    "mdc.client_session", "true", domain=KRX_HOST, path="/"
                )
        return success

    def get_headers(self) -> dict:
        return {
            "User-Agent": USER_AGENT,
            "Referer": "https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd",
            "Origin": "https://data.krx.co.kr",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        }

    def get(self, url: str, headers: Optional[dict] = None, params: Optional[dict] = None, **kwargs):
        merged_headers = self.get_headers()
        if headers:
            merged_headers.update(headers)
        return self.session.get(url, headers=merged_headers, params=params, **kwargs)

    def post(self, url: str, headers: Optional[dict] = None, data: Optional[dict] = None, **kwargs):
        merged_headers = self.get_headers()
        if headers:
            merged_headers.update(headers)
        return self.session.post(url, headers=merged_headers, data=data, **kwargs)


def normalize_krx_url(url: str) -> str:
    if url.startswith("http://data.krx.co.kr/"):
        return "https://" + url[len("http://") :]
    return url


def warmup_krx_session(session: requests.Session) -> None:
    session.get(LOGIN_PAGE, headers={"User-Agent": USER_AGENT}, timeout=15)
    session.get(
        LOGIN_JSP,
        headers={"User-Agent": USER_AGENT, "Referer": LOGIN_PAGE},
        timeout=15,
    )


def login_krx(login_id: str, login_pw: str, session: Optional[requests.Session] = None) -> bool:
    if session is None:
        session = requests.Session()
    warmup_krx_session(session)

    payload = {
        "mbrNm": "",
        "telNo": "",
        "di": "",
        "certType": "",
        "mbrId": login_id,
        "pw": login_pw,
    }
    headers = {"User-Agent": USER_AGENT, "Referer": LOGIN_PAGE}

    resp = session.post(LOGIN_URL, data=payload, headers=headers, timeout=15)
    data = resp.json()
    error_code = data.get("_error_code", "")
    error_message = data.get("_error_message", "")

    if error_code == "CD010":
        logger.error("KRX password change is required: %s", error_message)
        return False

    if error_code == "CD011":
        payload["skipDup"] = "Y"
        resp = session.post(LOGIN_URL, data=payload, headers=headers, timeout=15)
        data = resp.json()
        error_code = data.get("_error_code", "")
        error_message = data.get("_error_message", "")

    if error_code != "CD001":
        logger.error("KRX login failed: code=%s message=%s", error_code, error_message)
        return False

    return True


def build_krx_session(login_id: Optional[str] = None, login_pw: Optional[str] = None) -> Optional[KRXSession]:
    login_id = login_id or os.getenv("KRX_ID")
    login_pw = login_pw or os.getenv("KRX_PW")
    if not (login_id and login_pw):
        logger.info("KRX_ID/KRX_PW are not set; using unauthenticated KRX requests")
        return None

    krxs = KRXSession()
    if krxs.refresh(login_id, login_pw):
        logger.info("KRX login succeeded; session expires at %s", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(krxs.expiry_time)))
        return krxs
    return None


def get_auth_session() -> Optional[KRXSession]:
    global _auth_session
    if _auth_session is None:
        _auth_session = build_krx_session()
        return _auth_session

    if not _auth_session.is_valid():
        login_id = os.getenv("KRX_ID")
        login_pw = os.getenv("KRX_PW")
        if not (login_id and login_pw):
            return None
        logger.info("KRX session expired; refreshing")
        if not _auth_session.refresh(login_id, login_pw):
            _auth_session = None
    return _auth_session


def krx_post(url: str, headers: Optional[dict] = None, data: Optional[dict] = None, timeout: int = 30):
    url = normalize_krx_url(url)
    krxs = get_auth_session()
    if krxs is not None:
        return krxs.post(url, headers=headers, data=data, timeout=timeout)
    return requests.post(url, headers=headers, data=data, timeout=timeout)


def krx_post_json(url: str, headers: Optional[dict] = None, data: Optional[dict] = None, timeout: int = 30):
    response = krx_post(url, headers=headers, data=data, timeout=timeout)
    response.raise_for_status()
    return response.json()


class _RequestsProxy:
    """requests-like proxy for old pykrx webio.py.

    pykrx 1.0.x calls ``requests.get/post`` directly.  Installing this proxy lets
    those calls reuse the authenticated MDC session without editing site-packages.
    """

    @staticmethod
    def get(url, headers=None, params=None, **kwargs):
        url = normalize_krx_url(url)
        krxs = get_auth_session() if KRX_HOST in url else None
        if krxs is not None:
            return krxs.get(url, headers=headers, params=params, **kwargs)
        return requests.get(url, headers=headers, params=params, **kwargs)

    @staticmethod
    def post(url, headers=None, data=None, **kwargs):
        url = normalize_krx_url(url)
        krxs = get_auth_session() if KRX_HOST in url else None
        if krxs is not None:
            return krxs.post(url, headers=headers, data=data, **kwargs)
        return requests.post(url, headers=headers, data=data, **kwargs)


def install_pykrx_auth_proxy() -> None:
    global _pykrx_proxy_installed
    if _pykrx_proxy_installed:
        return
    try:
        import pykrx.website.comm.webio as pykrx_webio

        pykrx_webio.requests = _RequestsProxy
        _pykrx_proxy_installed = True
        logger.info("Installed authenticated KRX request proxy for pykrx")
    except Exception:
        logger.debug("Unable to install pykrx KRX auth proxy", exc_info=True)
