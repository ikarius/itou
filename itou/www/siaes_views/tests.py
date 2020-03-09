from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils.html import escape

from itou.jobs.factories import create_test_romes_and_appellations
from itou.jobs.models import Appellation
from itou.siaes.factories import (
    SiaeWithMembershipAndJobsFactory,
    SiaeWithMembershipFactory,
)
from itou.siaes.models import Siae
from itou.users.factories import DEFAULT_PASSWORD
from itou.utils.mocks.geocoding import BAN_GEOCODING_API_RESULT_MOCK


class CardViewTest(TestCase):
    def test_card(self):
        siae = SiaeWithMembershipFactory()
        user = siae.members.first()
        self.client.login(username=user.email, password=DEFAULT_PASSWORD)
        url = reverse("siaes_views:card", kwargs={"siae_id": siae.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["siae"], siae)
        self.assertContains(response, escape(siae.display_name))
        self.assertContains(response, siae.email)
        self.assertContains(response, siae.phone)

    def test_card_legacy_route(self):
        siae = SiaeWithMembershipFactory()
        user = siae.members.first()
        self.client.login(username=user.email, password=DEFAULT_PASSWORD)
        url = reverse("siaes_views:card_legacy", kwargs={"siret": siae.siret})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 301)

        siret_without_siae = "12345678901234"
        self.assertFalse(Siae.objects.filter(siret=siret_without_siae).exists())
        url = reverse("siaes_views:card_legacy", kwargs={"siret": siret_without_siae})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)


class JobDescriptionCardViewTest(TestCase):
    def test_job_description_card(self):
        siae = SiaeWithMembershipAndJobsFactory()
        job_description = siae.job_description_through.first()
        job_description.description = (
            "Lorem ipsum dolor sit amet, consectetur adipiscing elit."
        )
        job_description.save()
        url = reverse(
            "siaes_views:job_description_card",
            kwargs={"job_description_id": job_description.pk},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["job"], job_description)
        self.assertEqual(response.context["siae"], siae)
        self.assertContains(response, job_description.description)
        self.assertContains(response, escape(job_description.display_name))
        self.assertContains(response, escape(siae.display_name))


class ConfigureJobsViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Set up data for the whole TestCase.

        siae = SiaeWithMembershipFactory()
        user = siae.members.first()

        create_test_romes_and_appellations(["N1101", "N1105", "N1103", "N4105"])
        appellations = Appellation.objects.filter(
            name__in=[
                "Agent / Agente cariste de livraison ferroviaire",
                "Agent / Agente de quai manutentionnaire",
                "Agent magasinier / Agente magasinière gestionnaire de stocks",
                "Chauffeur-livreur / Chauffeuse-livreuse",
            ]
        )
        siae.jobs.add(*appellations)

        cls.siae = siae
        cls.user = user

        cls.url = reverse("siaes_views:configure_jobs")

    def test_access(self):

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

        self.client.login(username=self.user.email, password=DEFAULT_PASSWORD)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_content(self):

        self.client.login(username=self.user.email, password=DEFAULT_PASSWORD)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

        self.assertEqual(self.siae.jobs.count(), 4)
        response_content = str(response.content)
        for appellation in self.siae.jobs.all():
            self.assertIn(f'value="{appellation.code}"', response_content)
            self.assertIn(f'name="is_active-{appellation.code}"', response_content)

    def test_update(self):

        self.client.login(username=self.user.email, password=DEFAULT_PASSWORD)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

        post_data = {
            # List of appellations codes that we will operate on.
            "code": ["10357", "10579", "10750", "10877", "16361"],
            # Do nothing for "Agent / Agente cariste de livraison ferroviaire"
            "is_active-10357": "on",  # "on" is set when the checkbox is checked.
            # Update "Agent / Agente de quai manutentionnaire"
            "custom-name-10579": "Agent de quai",
            "description-10579": "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
            "is_active-10579": "",
            # Update "Agent magasinier / Agente magasinière gestionnaire de stocks"
            "is_active-10750": "",
            "custom-name-10750": "",
            "description-10750": "",
            # Delete for "Chauffeur-livreur / Chauffeuse-livreuse"
            # Exclude code `11999` from POST payload.
            # Add "Aide-livreur / Aide-livreuse"
            "is_active-10877": "on",
            "custom-name-10877": "Aide-livreur hebdomadaire",
            "description-10877": "Pellentesque ex ex, elementum sed sollicitudin sit amet, dictum vel elit.",
            # Add "Manutentionnaire"
            "is_active-16361": "",
        }

        response = self.client.post(self.url, data=post_data)
        self.assertEqual(response.status_code, 302)

        self.assertEqual(self.siae.jobs.count(), 5)
        self.assertEqual(self.siae.job_description_through.count(), 5)

        self.assertTrue(
            self.siae.job_description_through.get(appellation_id=10357, is_active=True)
        )
        self.assertTrue(
            self.siae.job_description_through.get(
                appellation_id=10579,
                is_active=False,
                custom_name=post_data["custom-name-10579"],
                description=post_data["description-10579"],
            )
        )
        self.assertTrue(
            self.siae.job_description_through.get(
                appellation_id=10750,
                is_active=False,
                custom_name=post_data["custom-name-10750"],
                description=post_data["description-10750"],
            )
        )
        self.assertTrue(
            self.siae.job_description_through.get(
                appellation_id=10877,
                is_active=True,
                custom_name=post_data["custom-name-10877"],
                description=post_data["description-10877"],
            )
        )
        self.assertTrue(
            self.siae.job_description_through.get(appellation_id=16361, is_active=False)
        )


class CreateSiaeViewTest(TestCase):
    def test_create_siae_outside_of_siren_fails(self):

        siae = SiaeWithMembershipFactory()
        user = siae.members.first()

        self.client.login(username=user.email, password=DEFAULT_PASSWORD)

        url = reverse("siaes_views:create_siae")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        new_siren = "9876543210"
        new_siret = f"{new_siren}1234"
        self.assertNotEqual(siae.siren, new_siren)

        post_data = {
            "siret": new_siret,
            "kind": Siae.KIND_ETTI,
            "name": "FAMOUS SIAE SUB STRUCTURE",
            "source": Siae.SOURCE_USER_CREATED,
            "address_line_1": "2 Rue de Soufflenheim",
            "city": "Betschdorf",
            "post_code": "67660",
            "department": "67",
            "email": "",
            "phone": "0610203050",
            "website": "https://famous-siae.com",
            "description": "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
        }
        response = self.client.post(url, data=post_data)
        self.assertEqual(response.status_code, 200)

        self.assertFalse(Siae.objects.filter(siret=post_data["siret"]).exists())

    def test_cannot_create_siae_with_same_siret_and_same_type(self):

        siae = SiaeWithMembershipFactory()
        user = siae.members.first()

        self.client.login(username=user.email, password=DEFAULT_PASSWORD)

        url = reverse("siaes_views:create_siae")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        post_data = {
            "siret": siae.siret,
            "kind": siae.kind,
            "name": "FAMOUS SIAE SUB STRUCTURE",
            "source": Siae.SOURCE_USER_CREATED,
            "address_line_1": "2 Rue de Soufflenheim",
            "city": "Betschdorf",
            "post_code": "67660",
            "department": "67",
            "email": "",
            "phone": "0610203050",
            "website": "https://famous-siae.com",
            "description": "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
        }
        response = self.client.post(url, data=post_data)
        self.assertEqual(response.status_code, 200)

        self.assertEqual(Siae.objects.filter(siret=post_data["siret"]).count(), 1)

    @mock.patch(
        "itou.utils.apis.geocoding.call_ban_geocoding_api",
        return_value=BAN_GEOCODING_API_RESULT_MOCK,
    )
    def test_can_create_siae_with_same_siret_and_different_type(
        self, mock_call_ban_geocoding_api
    ):
        siae = SiaeWithMembershipFactory()
        siae.kind = Siae.KIND_ETTI
        siae.save()
        user = siae.members.first()

        self.client.login(username=user.email, password=DEFAULT_PASSWORD)

        url = reverse("siaes_views:create_siae")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        post_data = {
            "siret": siae.siret,
            "kind": Siae.KIND_ACI,
            "name": "FAMOUS SIAE SUB STRUCTURE",
            "source": Siae.SOURCE_USER_CREATED,
            "address_line_1": "2 Rue de Soufflenheim",
            "city": "Betschdorf",
            "post_code": "67660",
            "department": "67",
            "email": "",
            "phone": "0610203050",
            "website": "https://famous-siae.com",
            "description": "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
        }
        response = self.client.post(url, data=post_data)
        self.assertEqual(response.status_code, 302)

        new_siae = Siae.objects.get(name=post_data["name"])

        self.assertNotEqual(new_siae.pk, siae.pk)
        self.assertEqual(siae.source, Siae.SOURCE_ASP)
        self.assertEqual(new_siae.source, Siae.SOURCE_USER_CREATED)
        self.assertTrue(user.siaemembership_set.get(siae=new_siae).is_siae_admin)
        self.assertEqual(new_siae.siret, post_data["siret"])
        self.assertEqual(new_siae.kind, post_data["kind"])
        self.assertEqual(new_siae.name, post_data["name"])
        self.assertEqual(new_siae.address_line_1, post_data["address_line_1"])
        self.assertEqual(new_siae.address_line_2, "")
        self.assertEqual(new_siae.city, post_data["city"])
        self.assertEqual(new_siae.post_code, post_data["post_code"])
        self.assertEqual(new_siae.department, post_data["department"])
        self.assertEqual(new_siae.email, post_data["email"])
        self.assertEqual(new_siae.phone, post_data["phone"])
        self.assertEqual(new_siae.website, post_data["website"])
        self.assertEqual(new_siae.description, post_data["description"])
        self.assertEqual(new_siae.created_by, user)
        self.assertEqual(new_siae.source, Siae.SOURCE_USER_CREATED)

        # This data comes from BAN_GEOCODING_API_RESULT_MOCK.
        self.assertEqual(new_siae.coords, "SRID=4326;POINT (2.316754 48.838411)")
        self.assertEqual(new_siae.latitude, 48.838411)
        self.assertEqual(new_siae.longitude, 2.316754)
        self.assertEqual(new_siae.geocoding_score, 0.587663373207207)

    @mock.patch(
        "itou.utils.apis.geocoding.call_ban_geocoding_api",
        return_value=BAN_GEOCODING_API_RESULT_MOCK,
    )
    def test_create_siae_with_different_siret(self, mock_call_ban_geocoding_api):
        siae = SiaeWithMembershipFactory()
        user = siae.members.first()

        self.client.login(username=user.email, password=DEFAULT_PASSWORD)

        url = reverse("siaes_views:create_siae")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        new_siret = siae.siren + "99999"
        self.assertNotEqual(siae.siret, new_siret)

        post_data = {
            "siret": new_siret,
            "kind": Siae.KIND_ACI,
            "name": "FAMOUS SIAE SUB STRUCTURE",
            "source": Siae.SOURCE_USER_CREATED,
            "address_line_1": "2 Rue de Soufflenheim",
            "city": "Betschdorf",
            "post_code": "67660",
            "department": "67",
            "email": "",
            "phone": "0610203050",
            "website": "https://famous-siae.com",
            "description": "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
        }
        response = self.client.post(url, data=post_data)
        self.assertEqual(response.status_code, 302)

        new_siae = Siae.objects.get(siret=new_siret)
        self.assertTrue(user.siaemembership_set.get(siae=new_siae).is_siae_admin)
        self.assertEqual(siae.source, Siae.SOURCE_ASP)
        self.assertEqual(new_siae.source, Siae.SOURCE_USER_CREATED)
        self.assertEqual(new_siae.siret, post_data["siret"])
        self.assertEqual(new_siae.kind, post_data["kind"])
        self.assertEqual(new_siae.name, post_data["name"])
        self.assertEqual(new_siae.address_line_1, post_data["address_line_1"])
        self.assertEqual(new_siae.city, post_data["city"])
        self.assertEqual(new_siae.post_code, post_data["post_code"])
        self.assertEqual(new_siae.department, post_data["department"])
        self.assertEqual(new_siae.email, post_data["email"])
        self.assertEqual(new_siae.phone, post_data["phone"])
        self.assertEqual(new_siae.website, post_data["website"])
        self.assertEqual(new_siae.description, post_data["description"])
        self.assertEqual(new_siae.created_by, user)
        self.assertEqual(new_siae.source, Siae.SOURCE_USER_CREATED)

        # This data comes from BAN_GEOCODING_API_RESULT_MOCK.
        self.assertEqual(new_siae.coords, "SRID=4326;POINT (2.316754 48.838411)")
        self.assertEqual(new_siae.latitude, 48.838411)
        self.assertEqual(new_siae.longitude, 2.316754)
        self.assertEqual(new_siae.geocoding_score, 0.587663373207207)


class EditSiaeViewTest(TestCase):
    @mock.patch(
        "itou.utils.apis.geocoding.call_ban_geocoding_api",
        return_value=BAN_GEOCODING_API_RESULT_MOCK,
    )
    def test_edit(self, mock_call_ban_geocoding_api):

        siae = SiaeWithMembershipFactory()
        user = siae.members.first()

        self.client.login(username=user.email, password=DEFAULT_PASSWORD)

        url = reverse("siaes_views:edit_siae")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        post_data = {
            "brand": "NEW FAMOUS SIAE BRAND NAME",
            "description": "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
            "phone": "0610203050",
            "email": "",
            "website": "https://famous-siae.com",
            "address_line_1": "1 Rue Jeanne d'Arc",
            "address_line_2": "",
            "post_code": "62000",
            "city": "Arras",
            "department": "62",
        }
        response = self.client.post(url, data=post_data)
        self.assertEqual(response.status_code, 302)

        siae = Siae.objects.get(siret=siae.siret)

        self.assertEqual(siae.brand, post_data["brand"])
        self.assertEqual(siae.description, post_data["description"])
        self.assertEqual(siae.email, post_data["email"])
        self.assertEqual(siae.phone, post_data["phone"])
        self.assertEqual(siae.website, post_data["website"])

        self.assertEqual(siae.address_line_1, post_data["address_line_1"])
        self.assertEqual(siae.address_line_2, post_data["address_line_2"])
        self.assertEqual(siae.post_code, post_data["post_code"])
        self.assertEqual(siae.city, post_data["city"])
        self.assertEqual(siae.department, post_data["department"])

        # This data comes from BAN_GEOCODING_API_RESULT_MOCK.
        self.assertEqual(siae.coords, "SRID=4326;POINT (2.316754 48.838411)")
        self.assertEqual(siae.latitude, 48.838411)
        self.assertEqual(siae.longitude, 2.316754)
        self.assertEqual(siae.geocoding_score, 0.587663373207207)
