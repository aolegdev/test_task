from datetime import date
from unittest import mock

from django.contrib.auth.models import Group, User
from rest_framework.test import APIClient, APITestCase

from plan.models import Factory, FactoryUser, WorkVolume
from plan.views import MANAGER, REPRESENTATIVE

mock.patch("plan.clickhouse.create_tables").start()

URL = "/work-volume-list/"
START = 1767225600  # 2026-01-01
FINISH = 1769904000  # 2026-02-01


@mock.patch("plan.views.save_work_volume_record")
class WorkVolumeListViewTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.factory = Factory.objects.create(name="ЗМК 1")
        cls.other_factory = Factory.objects.create(name="ЗМК 2")

        cls.representative = User.objects.create_user("representative")
        cls.representative.groups.add(Group.objects.create(name=REPRESENTATIVE))
        FactoryUser.objects.create(user=cls.representative, factory=cls.factory)

        cls.manager = User.objects.create_user("manager")
        cls.manager.groups.add(Group.objects.create(name=MANAGER))

        cls.no_group_user = User.objects.create_user("no_group")

    def body(self, **overrides):
        data = {
            "factory": self.factory.pk,
            "start": START,
            "finish": FINISH,
            "weight": 1000,
            "author": self.manager.pk,
        }
        data.update(overrides)
        return data

    def post(self, user, data):
        self.client.force_authenticate(user)
        return self.client.post(URL, data, format="json")

    def test_unauthenticated(self, save_record):
        """Запрос без авторизации возвращает 401."""

        response = APIClient().post(URL, self.body(), format="json")

        self.assertEqual(response.status_code, 401)
        save_record.assert_not_called()

    def test_missing_field(self, save_record):
        """Отсутствие любого обязательного поля возвращает 406 с errorCode=279."""

        for field in ["factory", "start", "finish", "weight", "author"]:
            with self.subTest(field=field):
                data = self.body()
                del data[field]

                response = self.post(self.manager, data)

                self.assertEqual(response.status_code, 406)
                self.assertEqual(response.data, {"errorCode": 279})
        save_record.assert_not_called()

    def test_invalid_field_value(self, save_record):
        """Пустое или нецелочисленное значение поля возвращает 406 с errorCode=279."""

        for value in [None, "1000", 1000.5, True]:
            with self.subTest(value=value):
                response = self.post(self.manager, self.body(weight=value))

                self.assertEqual(response.status_code, 406)
                self.assertEqual(response.data, {"errorCode": 279})
        save_record.assert_not_called()

    def test_start_after_finish(self, save_record):
        """Начальная дата позже конечной возвращает 406 с errorCode=279."""

        response = self.post(self.manager, self.body(start=FINISH, finish=START))

        self.assertEqual(response.status_code, 406)
        self.assertEqual(response.data, {"errorCode": 279})
        self.assertFalse(WorkVolume.objects.exists())
        save_record.assert_not_called()

    def test_negative_weight(self, save_record):
        """Отрицательный вес возвращает 406 с errorCode=279."""

        response = self.post(self.manager, self.body(weight=-1))

        self.assertEqual(response.status_code, 406)
        self.assertEqual(response.data, {"errorCode": 279})
        self.assertFalse(WorkVolume.objects.exists())
        save_record.assert_not_called()

    def test_factory_not_found(self, save_record):
        """Несуществующий ЗМК возвращает 404 с errorCode=174."""

        response = self.post(self.manager, self.body(factory=999999))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data, {"errorCode": 174})
        save_record.assert_not_called()

    def test_representative_of_other_factory(self, save_record):
        """Представитель чужого ЗМК получает 404 с errorCode=174."""

        response = self.post(
            self.representative, self.body(factory=self.other_factory.pk)
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data, {"errorCode": 174})
        self.assertFalse(WorkVolume.objects.exists())
        save_record.assert_not_called()

    def test_user_without_group(self, save_record):
        """Пользователь без группы получает 403."""

        response = self.post(self.no_group_user, self.body())

        self.assertEqual(response.status_code, 403)
        self.assertFalse(WorkVolume.objects.exists())
        save_record.assert_not_called()

    def test_representative_creates_work_volume(self, save_record):
        """Представитель своего ЗМК создаёт объём работ и запись в ClickHouse."""

        response = self.post(self.representative, self.body())

        self.assertEqual(response.status_code, 201)
        volume = WorkVolume.objects.get()
        self.assertEqual(volume.factory, self.factory)
        self.assertEqual(volume.start, date(2026, 1, 1))
        self.assertEqual(volume.finish, date(2026, 2, 1))
        self.assertEqual(volume.weight, 1000)
        save_record.assert_called_once_with(
            self.factory,
            date(2026, 1, 1),
            date(2026, 2, 1),
            1000,
            self.manager.pk,
            volume.created,
        )

    def test_manager_creates_work_volume(self, save_record):
        """Менеджер создаёт объём работ для любого ЗМК."""

        response = self.post(self.manager, self.body(factory=self.other_factory.pk))

        self.assertEqual(response.status_code, 201)
        self.assertEqual(WorkVolume.objects.get().factory, self.other_factory)
        save_record.assert_called_once()

    def test_existing_period_is_updated(self, save_record):
        """Повторный запрос за тот же период обновляет weight и created."""

        WorkVolume.objects.create(
            factory=self.factory,
            start=date(2026, 1, 1),
            finish=date(2026, 2, 1),
            weight=1,
            created=date(2025, 1, 1),
        )

        response = self.post(self.manager, self.body(weight=2000))

        self.assertEqual(response.status_code, 201)
        volume = WorkVolume.objects.get()
        self.assertEqual(volume.weight, 2000)
        self.assertNotEqual(volume.created, date(2025, 1, 1))
        save_record.assert_called_once()

    def test_clickhouse_failure_rolls_back_postgres(self, save_record):
        """Ошибка записи в ClickHouse откатывает изменения в Postgres."""

        save_record.side_effect = ConnectionError

        with self.assertRaises(ConnectionError):
            self.post(self.manager, self.body())

        self.assertFalse(WorkVolume.objects.exists())
