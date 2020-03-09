from unittest import mock

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.exceptions import ValidationError
from django.template import Context, Template
from django.test import RequestFactory, TestCase

from itou.prescribers.factories import PrescriberOrganizationWithMembershipFactory
from itou.prescribers.models import PrescriberOrganization
from itou.siaes.factories import SiaeFactory, SiaeWithMembershipFactory
from itou.users.factories import JobSeekerFactory, PrescriberFactory
from itou.utils.apis.geocoding import process_geocoding_data
from itou.utils.apis.siret import process_siret_data
from itou.utils.mocks.geocoding import BAN_GEOCODING_API_RESULT_MOCK
from itou.utils.mocks.siret import API_INSEE_SIRET_RESULT_MOCK
from itou.utils.perms.context_processors import get_current_organization_and_perms
from itou.utils.perms.user import (
    KIND_JOB_SEEKER,
    KIND_PRESCRIBER,
    KIND_SIAE_STAFF,
    get_user_info,
)
from itou.utils.templatetags import format_filters
from itou.utils.urls import get_safe_url
from itou.utils.validators import (
    alphanumeric,
    validate_naf,
    validate_pole_emploi_id,
    validate_post_code,
    validate_siret,
)


class ContextProcessorsGetCurrentOrganizationAndPermsTest(TestCase):
    """Test `itou.utils.perms.context_processors.get_current_organization_and_perms` processor."""

    def test_siae_one_membership(self):

        siae = SiaeWithMembershipFactory()
        user = siae.members.first()
        self.assertTrue(user.siaemembership_set.get(siae=siae).is_siae_admin)

        factory = RequestFactory()
        request = factory.get("/")
        request.user = user
        middleware = SessionMiddleware()
        middleware.process_request(request)
        request.session[settings.ITOU_SESSION_CURRENT_SIAE_KEY] = siae.pk
        request.session.save()

        with self.assertNumQueries(1):
            result = get_current_organization_and_perms(request)
            expected = {
                "current_prescriber_organization": None,
                "current_siae": siae,
                "user_is_prescriber_org_admin": False,
                "user_is_siae_admin": True,
                "user_siae_set": [siae],
            }
            self.assertDictEqual(expected, result)

    def test_siae_multiple_memberships(self):

        siae1 = SiaeWithMembershipFactory()
        user = siae1.members.first()
        self.assertTrue(user.siaemembership_set.get(siae=siae1).is_siae_admin)

        siae2 = SiaeFactory()
        siae2.members.add(user)
        self.assertFalse(user.siaemembership_set.get(siae=siae2).is_siae_admin)

        siae3 = SiaeFactory()
        siae3.members.add(user)
        self.assertFalse(user.siaemembership_set.get(siae=siae3).is_siae_admin)

        factory = RequestFactory()
        request = factory.get("/")
        request.user = user
        middleware = SessionMiddleware()
        middleware.process_request(request)
        request.session[settings.ITOU_SESSION_CURRENT_SIAE_KEY] = siae3.pk
        request.session.save()

        with self.assertNumQueries(1):
            result = get_current_organization_and_perms(request)
            expected = {
                "current_prescriber_organization": None,
                "current_siae": siae3,
                "user_is_prescriber_org_admin": False,
                "user_is_siae_admin": False,
                "user_siae_set": [siae1, siae2, siae3],
            }
            self.assertDictEqual(expected, result)

    def test_prescriber_organization_one_membership(self):

        organization = PrescriberOrganizationWithMembershipFactory()
        user = organization.members.first()
        self.assertTrue(
            user.prescribermembership_set.get(organization=organization).is_admin
        )

        factory = RequestFactory()
        request = factory.get("/")
        request.user = user
        middleware = SessionMiddleware()
        middleware.process_request(request)
        request.session[
            settings.ITOU_SESSION_CURRENT_PRESCRIBER_ORG_KEY
        ] = organization.pk
        request.session.save()

        with self.assertNumQueries(1):
            result = get_current_organization_and_perms(request)
            expected = {
                "current_prescriber_organization": organization,
                "current_siae": None,
                "user_is_prescriber_org_admin": True,
                "user_is_siae_admin": False,
                "user_siae_set": [],
            }
            self.assertDictEqual(expected, result)


class UtilsAddressMixinTest(TestCase):
    @mock.patch(
        "itou.utils.apis.geocoding.call_ban_geocoding_api",
        return_value=BAN_GEOCODING_API_RESULT_MOCK,
    )
    def test_set_coords(self, mock_call_ban_geocoding_api):
        """
        Test `AddressMixin.set_coords()`.
        Use `PrescriberOrganization` which inherits from abstract `AddressMixin`.
        """
        prescriber = PrescriberOrganization.objects.create(siret="12000015300011")

        self.assertEqual(prescriber.address_line_1, "")
        self.assertEqual(prescriber.address_line_2, "")
        self.assertEqual(prescriber.post_code, "")
        self.assertEqual(prescriber.city, "")
        self.assertEqual(prescriber.coords, None)
        self.assertEqual(prescriber.geocoding_score, None)
        self.assertEqual(prescriber.latitude, None)
        self.assertEqual(prescriber.longitude, None)

        prescriber.set_coords("10 PL 5 MARTYRS LYCEE BUFFON", post_code="75015")
        prescriber.save()

        # Expected data comes from BAN_GEOCODING_API_RESULT_MOCK.
        expected_coords = "SRID=4326;POINT (2.316754 48.838411)"
        expected_latitude = 48.838411
        expected_longitude = 2.316754
        expected_geocoding_score = 0.587663373207207

        self.assertEqual(prescriber.coords, expected_coords)
        self.assertEqual(prescriber.geocoding_score, expected_geocoding_score)
        self.assertEqual(prescriber.latitude, expected_latitude)
        self.assertEqual(prescriber.longitude, expected_longitude)

    @mock.patch(
        "itou.utils.apis.geocoding.call_ban_geocoding_api",
        return_value=BAN_GEOCODING_API_RESULT_MOCK,
    )
    def test_set_coords_and_address(self, mock_call_ban_geocoding_api):
        """
        Test `AddressMixin.set_coords_and_address()`.
        Use `PrescriberOrganization` which inherits from abstract `AddressMixin`.
        """
        prescriber = PrescriberOrganization.objects.create(siret="12000015300011")

        self.assertEqual(prescriber.address_line_1, "")
        self.assertEqual(prescriber.address_line_2, "")
        self.assertEqual(prescriber.post_code, "")
        self.assertEqual(prescriber.city, "")
        self.assertEqual(prescriber.coords, None)
        self.assertEqual(prescriber.geocoding_score, None)
        self.assertEqual(prescriber.latitude, None)
        self.assertEqual(prescriber.longitude, None)

        prescriber.set_coords_and_address(
            "10 PL 5 MARTYRS LYCEE BUFFON", post_code="75015"
        )
        prescriber.save()

        # Expected data comes from BAN_GEOCODING_API_RESULT_MOCK.
        expected_address_line_1 = "10 Pl des Cinq Martyrs du Lycee Buffon"
        expected_post_code = "75015"
        expected_city = "Paris"
        expected_coords = "SRID=4326;POINT (2.316754 48.838411)"
        expected_latitude = 48.838411
        expected_longitude = 2.316754
        expected_geocoding_score = 0.587663373207207

        self.assertEqual(prescriber.address_line_1, expected_address_line_1)
        self.assertEqual(prescriber.address_line_2, "")
        self.assertEqual(prescriber.post_code, expected_post_code)
        self.assertEqual(prescriber.city, expected_city)
        self.assertEqual(prescriber.coords, expected_coords)
        self.assertEqual(prescriber.geocoding_score, expected_geocoding_score)
        self.assertEqual(prescriber.latitude, expected_latitude)
        self.assertEqual(prescriber.longitude, expected_longitude)


class UtilsGeocodingTest(TestCase):
    @mock.patch(
        "itou.utils.apis.geocoding.call_ban_geocoding_api",
        return_value=BAN_GEOCODING_API_RESULT_MOCK,
    )
    def test_process_geocoding_data(self, mock_call_ban_geocoding_api):
        geocoding_data = mock_call_ban_geocoding_api()
        result = process_geocoding_data(geocoding_data)
        # Expected data comes from BAN_GEOCODING_API_RESULT_MOCK.
        expected = {
            "score": 0.587663373207207,
            "address_line_1": "10 Pl des Cinq Martyrs du Lycee Buffon",
            "post_code": "75015",
            "city": "Paris",
            "longitude": 2.316754,
            "latitude": 48.838411,
            "coords": GEOSGeometry("POINT(2.316754 48.838411)"),
        }
        self.assertEqual(result, expected)


class UtilsSiretTest(TestCase):
    @mock.patch(
        "itou.utils.apis.siret.call_insee_api", return_value=API_INSEE_SIRET_RESULT_MOCK
    )
    def test_process_siret_data(self, mock_call_insee_api):
        siret_data = mock_call_insee_api()
        result = process_siret_data(siret_data)
        # Expected data comes from API_INSEE_SIRET_RESULT_MOCK.
        expected = {
            "name": "DELEGATION GENERALE A L'EMPLOI ET A LA FORMATION PROFESSIONNELLE",
            "address": "10 PL 5 MARTYRS LYCEE BUFFON",
            "post_code": "75015",
        }
        self.assertEqual(result, expected)


class UtilsValidatorsTest(TestCase):
    def test_validate_alphanumeric(self):
        self.assertRaises(ValidationError, alphanumeric, "1245a_89871")
        alphanumeric("6201Z")

    def test_validate_naf(self):
        self.assertRaises(ValidationError, validate_naf, "1")
        self.assertRaises(ValidationError, validate_naf, "12254")
        self.assertRaises(ValidationError, validate_naf, "abcde")
        self.assertRaises(ValidationError, validate_naf, "1245789871")
        validate_naf("6201Z")

    def test_validate_siret(self):
        self.assertRaises(ValidationError, validate_siret, "1200001530001")
        self.assertRaises(ValidationError, validate_siret, "120000153000111")
        self.assertRaises(ValidationError, validate_siret, "1200001530001a")
        self.assertRaises(ValidationError, validate_siret, "azertyqwerty")
        validate_siret("12000015300011")

    def test_validate_post_code(self):
        self.assertRaises(ValidationError, validate_post_code, "")
        self.assertRaises(ValidationError, validate_post_code, "1234")
        self.assertRaises(ValidationError, validate_post_code, "123456")
        self.assertRaises(ValidationError, validate_post_code, "1234X")
        validate_post_code("12345")

    def test_validate_pole_emploi_id(self):
        self.assertRaises(ValidationError, validate_pole_emploi_id, "A2345678")
        self.assertRaises(ValidationError, validate_pole_emploi_id, "1234")
        self.assertRaises(ValidationError, validate_pole_emploi_id, "123412345654")
        self.assertRaises(ValidationError, validate_pole_emploi_id, "A234567É")
        validate_pole_emploi_id("12345678")
        validate_pole_emploi_id("1234567E")


class UtilsTemplateTagsTestCase(TestCase):
    def test_url_add_query(self):
        """Test `url_add_query` template tag."""

        # Full URL.
        context = {
            "url": "https://inclusion.beta.gouv.fr/siae/search?distance=100&city=aubervilliers-93&page=55&page=1"
        }
        template = Template("{% load url_add_query %}" "{% url_add_query url page=2 %}")
        out = template.render(Context(context))
        expected = "https://inclusion.beta.gouv.fr/siae/search?distance=100&amp;city=aubervilliers-93&amp;page=2"
        self.assertEqual(out, expected)

        # Relative URL.
        context = {"url": "/siae/search?distance=50&city=metz-57"}
        template = Template(
            "{% load url_add_query %}" "{% url_add_query url page=22 %}"
        )
        out = template.render(Context(context))
        expected = "/siae/search?distance=50&amp;city=metz-57&amp;page=22"
        self.assertEqual(out, expected)

        # Empty URL.
        context = {"url": ""}
        template = Template("{% load url_add_query %}" "{% url_add_query url page=1 %}")
        out = template.render(Context(context))
        expected = "?page=1"
        self.assertEqual(out, expected)


class UtilsTemplateFiltersTestCase(TestCase):
    def test_format_phone(self):
        """Test `format_phone` template filter."""
        self.assertEqual(format_filters.format_phone(""), "")
        self.assertEqual(format_filters.format_phone("0102030405"), "01 02 03 04 05")


class UtilsEmailsTestCase(TestCase):
    def test_get_safe_url(self):
        """Test `urls.get_safe_url()`."""

        request = RequestFactory().get(
            "/?next=/siae/search%3Fdistance%3D100%26city%3Dstrasbourg-67"
        )
        url = get_safe_url(request, "next")
        expected = "/siae/search?distance=100&city=strasbourg-67"
        self.assertEqual(url, expected)

        request = RequestFactory().post(
            "/", data={"next": "/siae/search?distance=100&city=strasbourg-67"}
        )
        url = get_safe_url(request, "next")
        expected = "/siae/search?distance=100&city=strasbourg-67"
        self.assertEqual(url, expected)

        request = RequestFactory().get("/?next=https://evil.com/siae/search")
        url = get_safe_url(request, "next")
        expected = None
        self.assertEqual(url, expected)

        request = RequestFactory().post("/", data={"next": "https://evil.com"})
        url = get_safe_url(request, "next", fallback_url="/fallback")
        expected = "/fallback"
        self.assertEqual(url, expected)


class PermsUserTest(TestCase):
    def test_get_user_info_for_siae_staff(self):
        siae = SiaeWithMembershipFactory()
        user = siae.members.first()

        factory = RequestFactory()
        request = factory.get("/")
        request.user = user
        middleware = SessionMiddleware()
        middleware.process_request(request)
        # Simulate ItouCurrentOrganizationMiddleware.
        request.session[settings.ITOU_SESSION_CURRENT_SIAE_KEY] = siae.pk
        request.session.save()

        user_info = get_user_info(request)
        self.assertEqual(user_info.user, user)
        self.assertEqual(user_info.kind, KIND_SIAE_STAFF)
        self.assertEqual(user_info.prescriber_organization, None)
        self.assertEqual(user_info.is_authorized_prescriber, False)
        self.assertEqual(user_info.siae, siae)

    def test_get_user_info_for_prescriber(self):
        prescriber_organization = PrescriberOrganizationWithMembershipFactory()
        user = prescriber_organization.members.first()

        factory = RequestFactory()
        request = factory.get("/")
        request.user = user
        middleware = SessionMiddleware()
        middleware.process_request(request)
        # Simulate ItouCurrentOrganizationMiddleware.
        request.session[
            settings.ITOU_SESSION_CURRENT_PRESCRIBER_ORG_KEY
        ] = prescriber_organization.pk
        request.session.save()

        user_info = get_user_info(request)
        self.assertEqual(user_info.user, user)
        self.assertEqual(user_info.kind, KIND_PRESCRIBER)
        self.assertEqual(user_info.prescriber_organization, prescriber_organization)
        self.assertEqual(user_info.is_authorized_prescriber, False)
        self.assertEqual(user_info.siae, None)

    def test_get_user_info_for_authorized_prescriber(self):
        prescriber_organization = PrescriberOrganizationWithMembershipFactory(
            is_authorized=True
        )
        user = prescriber_organization.members.first()

        factory = RequestFactory()
        request = factory.get("/")
        request.user = user
        middleware = SessionMiddleware()
        middleware.process_request(request)
        # Simulate ItouCurrentOrganizationMiddleware.
        request.session[
            settings.ITOU_SESSION_CURRENT_PRESCRIBER_ORG_KEY
        ] = prescriber_organization.pk
        request.session.save()

        user_info = get_user_info(request)
        self.assertEqual(user_info.user, user)
        self.assertEqual(user_info.kind, KIND_PRESCRIBER)
        self.assertEqual(user_info.prescriber_organization, prescriber_organization)
        self.assertEqual(user_info.is_authorized_prescriber, True)
        self.assertEqual(user_info.siae, None)

    def test_get_user_info_for_prescriber_without_organisation(self):
        user = PrescriberFactory()

        factory = RequestFactory()
        request = factory.get("/")
        request.user = user
        middleware = SessionMiddleware()
        middleware.process_request(request)
        request.session.save()

        user_info = get_user_info(request)
        self.assertEqual(user_info.user, user)
        self.assertEqual(user_info.kind, KIND_PRESCRIBER)
        self.assertEqual(user_info.prescriber_organization, None)
        self.assertEqual(user_info.is_authorized_prescriber, False)
        self.assertEqual(user_info.siae, None)

    def test_get_user_info_for_job_seeker(self):
        user = JobSeekerFactory()

        factory = RequestFactory()
        request = factory.get("/")
        request.user = user
        middleware = SessionMiddleware()
        middleware.process_request(request)
        request.session.save()

        user_info = get_user_info(request)
        self.assertEqual(user_info.user, user)
        self.assertEqual(user_info.kind, KIND_JOB_SEEKER)
        self.assertEqual(user_info.prescriber_organization, None)
        self.assertEqual(user_info.is_authorized_prescriber, False)
        self.assertEqual(user_info.siae, None)
