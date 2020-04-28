import os

from bs4 import BeautifulSoup
import pytest

from .integration_test import IntegrationTestClient


@pytest.fixture
def config():
    config = {}
    urls = {}
    urls["uaa"] = os.environ["UAA_URL"]
    urls["extras"] = os.environ["EXTRAS_URL"]
    urls["idp"] = os.environ["IDP_URL"]
    for url in urls:
        if not urls[url][0:4] == "http":
            urls[url] = "https://" + urls[url]
    config["urls"] = urls
    config["idp_name"] = os.environ["IDP_NAME"]
    return config


@pytest.fixture
def user():
    user = {}
    user["name"] = os.environ["TEST_USERNAME"]
    user["password"] = os.environ["TEST_PASSWORD"]
    user["token"] = os.getenv("TEST_TOKEN")
    return user


@pytest.fixture
def unauthenticated(config):
    itc = IntegrationTestClient(
        config["urls"]["extras"],
        config["urls"]["idp"],
        config["urls"]["uaa"],
        config["idp_name"],
    )
    return itc


@pytest.fixture
def authenticated(unauthenticated, user):
    token, changed = unauthenticated.log_in(
        user["name"], user["password"], user["token"]
    )
    if changed:
        os.environ["TEST_TOKEN"] = token
    return unauthenticated


def get_csrf(page_text) -> str:
    page = BeautifulSoup(page_text, features="html.parser")
    csrf = page.find(attrs={"name": "_csrf_token"}).attrs["value"]
    return csrf


@pytest.mark.parametrize("page", ["/invite", "/change-password", "/first-login"])
def test_unauthenticated_pages_redirect(unauthenticated, page, config):
    r = unauthenticated.get_page(page)
    assert r.status_code == 200
    assert r.url == config["urls"]["uaa"] + "/login"


# NOTE: Needs to be first test as long as we do not have a totp-reset method
def test_login_no_totp(unauthenticated, config, user):
    # log in to get/set our totp
    token, changed = unauthenticated.log_in(user["name"], user["password"])
    os.environ["TEST_TOKEN"] = token
    assert changed
    # log out, so log in will work
    unauthenticated.log_out()

    # log in again to make sure we have the right totp
    _, changed = unauthenticated.log_in(user["name"], user["password"], token)
    assert not changed


def test_reset_totp(authenticated, user):
    # get the page so we have a CSRF
    r = authenticated.get_page("/reset-totp")
    assert r.status_code == 200

    csrf = get_csrf(r.text)
    # actually reset our totp
    r = authenticated.post_to_page("/reset-totp", data={"_csrf_token": csrf})
    assert r.status_code == 200

    # reset-totp is supposed to log a user out. Logging in should reset our totp
    token, changed = r.log_in(user["name"], user["password"])
    assert changed
    os.environ["TEST_TOKEN"] = token


@pytest.mark.parametrize("page", ["/invite", "/change-password"])
def test_authenticated_pages_work(authenticated, page, config):
    r = authenticated.get_page(page)
    assert r.status_code == 200
    assert r.url == config["urls"]["extras"] + page


def test_change_password(authenticated, config, user):
    r = authenticated.get_page("/change-password")
    soup = BeautifulSoup(r.text, features="html.parser")
    csrf = soup.find(attrs={"name": "_csrf_token"}).attrs["value"]
    data = {
        "old_password": user["password"],
        "new_password": "a_severely_insecure_password",
        "repeat_password": "a_severely_insecure_password",
        "_csrf_token": csrf,
    }
    r = authenticated.post_to_page("/reset-password", data=data)
    assert r.status_code == 200

    # set the password back so we don't confuse the other tests
    r = authenticated.get_page("/change-password")
    csrf = get_csrf(r.text)
    data = {
        "old_password": "a_severely_insecure_password",
        "new_password": user["password"],
        "repeat_password": user["password"],
        "_csrf_token": csrf,
    }


@pytest.mark.skip("Not done yet")
def test_invites_happy_path(authenticated, config):
    if "dev" in config["urls"]["uaa"]:
        # alternate path: use dev, but expect the request to fail
        # email fails, but its also the last thing to happen, so the user
        # is created and their invite info can still be fetched from Redis
        pytest.skip("Can't test functions that require email in dev")
    r = authenticated.get_page("/invite")
    csrf = get_csrf(r.text)
    soup = BeautifulSoup(r.text, features="html.parser")
    form = soup.find("form")
    url = form.attrs["action"]
    payload = {"email": "", "_csrf_token": csrf}
    r = authenticated.post_to_page(url, data=payload)
    soup = BeautifulSoup(r.text, features="html.parser")
    # TODO: finish this.
    # Happy path sketch:
    # - get the invite info straight from Redis
    # - redeem invite
    # - log in for the first time

    # other tests to run:
    # - bad email
    # - bad csrf
    # - no csrf
