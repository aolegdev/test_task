import uuid

from django.db import models
from django.conf import settings


# ЗМК
class Factory(models.Model):
    external_id = models.UUIDField(unique=True, default=uuid.uuid4)
    name = models.CharField(max_length=255)


# Пользователь завода (ЗМК)
class FactoryUser(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    factory = models.ForeignKey(Factory, on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "factory"], name="unique_factory_user"
            )
        ]


# Объём работы
class WorkVolume(models.Model):
    factory = models.ForeignKey(Factory, on_delete=models.CASCADE)
    start = models.DateField()
    finish = models.DateField()
    weight = models.IntegerField()
    created = models.DateField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["factory", "start", "finish"], name="unique_work_volume_period"
            )
        ]
