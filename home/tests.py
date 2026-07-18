from django.test import TestCase
from django.urls import reverse


class FaviconTests(TestCase):
    def test_pages_reference_logo_favicon(self):
        response = self.client.get(reverse("home:index"))

        self.assertContains(
            response,
            'rel="icon" type="image/png" sizes="any" '
            'href="/static/images/hug-kerb-favicon-rounded.png"',
        )

    def test_browser_default_favicon_url_redirects_to_logo(self):
        response = self.client.get(reverse("favicon"))

        self.assertRedirects(
            response,
            "/static/images/hug-kerb-favicon-rounded.png",
            status_code=301,
            fetch_redirect_response=False,
        )
