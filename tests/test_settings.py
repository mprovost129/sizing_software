import tempfile
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image as PILImage


def _png_upload(name="logo.png", size=(120, 40)):
    buffer = BytesIO()
    PILImage.new("RGB", size, "white").save(buffer, "PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class SettingsViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="prep@example.com", password="test-password",
        )
        self.client.force_login(self.user)

    def test_settings_page_renders(self):
        response = self.client.get(reverse("beams:settings"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="firm_name"')
        self.assertContains(response, 'name="license_number"')

    def test_saving_report_identity(self):
        response = self.client.post(reverse("beams:settings"), {
            "first_name": "Ada", "last_name": "Lovelace",
            "firm_name": "Lovelace Structural", "license_number": "PE 9001",
            "phone": "555-000-1111", "firm_address": "1 Analytical Way",
        })
        self.assertRedirects(response, reverse("beams:settings"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.firm_name, "Lovelace Structural")
        self.assertEqual(self.user.license_number, "PE 9001")
        self.assertEqual(self.user.preparer_name(), "Ada Lovelace")
        self.assertTrue(self.user.has_report_identity())

    def test_preparer_name_falls_back_to_email(self):
        self.assertEqual(self.user.preparer_name(), "prep@example.com")
        self.assertFalse(self.user.has_report_identity())

    def test_logo_flowable_none_without_logo(self):
        from beams.pdf import _logo_flowable
        self.assertIsNone(_logo_flowable(self.user))

    def test_signature_block_builds(self):
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Table

        from beams.pdf import _signature_block_story
        # Builds for a bare user (blank identity) and one with identity.
        for u in (self.user, get_user_model()(email="pe@x.com", first_name="Grace", license_number="SE 42")):
            block = _signature_block_story(u, getSampleStyleSheet())
            self.assertTrue(any(isinstance(f, Table) for f in block))

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())
    def test_logo_upload_and_pdf_flowable(self):
        from reportlab.platypus import Image

        from beams.pdf import _logo_flowable
        response = self.client.post(reverse("beams:settings"), {
            "first_name": "Ada", "last_name": "Lovelace", "firm_name": "Lovelace Structural",
            "license_number": "", "phone": "", "firm_address": "",
            "logo": _png_upload(),
        })
        self.assertRedirects(response, reverse("beams:settings"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.logo)
        self.assertIsNotNone(self.user.logo_path())
        flowable = _logo_flowable(self.user)
        self.assertIsInstance(flowable, Image)
        # Aspect ratio preserved (120x40 = 3:1), scaled into the max box.
        self.assertAlmostEqual(flowable.drawWidth / flowable.drawHeight, 3.0, places=1)
