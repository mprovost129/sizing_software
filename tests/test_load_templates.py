from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from beams.models import BeamLoadTemplate


def _management_data(prefix):
    return {
        f"{prefix}-TOTAL_FORMS": "6",
        f"{prefix}-INITIAL_FORMS": "0",
        f"{prefix}-MIN_NUM_FORMS": "6",
        f"{prefix}-MAX_NUM_FORMS": "1000",
    }


class BeamLoadTemplateTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="templates@example.com",
            password="test-password",
        )
        self.client.force_login(self.user)

    def _template_post_data(self):
        data = {
            "load_template_name": "Typical Floor",
            "uniform_load_basis": "psf",
            "spacing_in": "16",
            "dead_load_plf": "10",
            "live_load_plf": "40",
            "snow_load_plf": "0",
            "roof_live_load_plf": "0",
            "wind_load_plf": "0",
            "pl-0-p": "850",
            "pl-0-location_ft": "5",
            "pl-0-load_type": "live",
            "dl-0-w": "15",
            "dl-0-start_ft": "2",
            "dl-0-end_ft": "8",
            "dl-0-load_type": "dead",
        }
        data.update(_management_data("pl"))
        data.update(_management_data("dl"))
        return data

    def test_create_and_update_named_load_template(self):
        response = self.client.post(reverse("beams:create_load_template"), self._template_post_data())

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["created"])
        template = BeamLoadTemplate.objects.get(user=self.user, name="Typical Floor")
        self.assertEqual(template.uniform_load_basis, "psf")
        self.assertEqual(template.point_loads[0]["p"], 850)
        self.assertEqual(template.distributed_loads[0]["start_ft"], 2)

        updated_data = self._template_post_data()
        updated_data["live_load_plf"] = "50"
        update_response = self.client.post(reverse("beams:create_load_template"), updated_data)

        self.assertEqual(update_response.status_code, 200)
        self.assertFalse(update_response.json()["created"])
        self.assertEqual(BeamLoadTemplate.objects.filter(user=self.user).count(), 1)
        template.refresh_from_db()
        self.assertEqual(template.live_load_plf, 50)

    def test_template_delete_is_scoped_to_owner(self):
        other_user = get_user_model().objects.create_user(
            email="other-template-user@example.com",
            password="test-password",
        )
        template = BeamLoadTemplate.objects.create(
            user=other_user,
            name="Private Loads",
            live_load_plf=40,
        )

        response = self.client.post(reverse("beams:delete_load_template", args=[template.pk]))

        self.assertEqual(response.status_code, 404)
        self.assertTrue(BeamLoadTemplate.objects.filter(pk=template.pk).exists())
