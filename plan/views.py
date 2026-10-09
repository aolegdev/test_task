from datetime import datetime, timezone
from django.utils import timezone as django_timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from plan.models import Factory, FactoryUser, WorkVolume
from plan.clickhouse import save_work_volume_record


REPRESENTATIVE = "Представитель ЗМК"
MANAGER = "Менеджер по взаимодействию с ЗМК"
FIELDS = ["factory", "start", "finish", "weight", "author"]


def error(status, code):
    return Response({"errorCode": code}, status=status)


class WorkVolumeListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data
        if not isinstance(data, dict):
            return error(406, 279)

        values = {}
        for field in FIELDS:
            if field not in data or data[field] is None:
                return error(406, 279)

            number = data[field]
            if isinstance(number, bool) or not isinstance(number, int):
                return error(406, 279)
            values[field] = number

        try:
            factory = Factory.objects.get(pk=values["factory"])
        except Factory.DoesNotExist:
            return error(404, 174)

        user = request.user
        if user.groups.filter(name=REPRESENTATIVE).exists():
            if not FactoryUser.objects.filter(user=user, factory=factory).exists():
                return error(404, 174)
        elif not user.groups.filter(name=MANAGER).exists():
            return Response(status=403)

        start = datetime.fromtimestamp(values["start"], tz=timezone.utc).date()
        finish = datetime.fromtimestamp(values["finish"], tz=timezone.utc).date()
        created = django_timezone.now().date()

        volume = WorkVolume.objects.filter(
            factory=factory,
            start=start,
            finish=finish,
        ).first()
        if volume is None:
            WorkVolume.objects.create(
                factory=factory,
                start=start,
                finish=finish,
                weight=values["weight"],
                created=created,
            )
        else:
            volume.weight = values["weight"]
            volume.created = created
            volume.save(update_fields=["weight", "created"])

        save_work_volume_record(
            factory,
            start,
            finish,
            values["weight"],
            values["author"],
            created,
        )
        return Response(status=201)
