from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


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
