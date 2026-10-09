import atexit
import time

import clickhouse_connect
from django.conf import settings

client = None


def connect():
    global client
    if client is not None:
        return
    client = clickhouse_connect.get_client(
        host=settings.CLICKHOUSE["HOST"],
        port=settings.CLICKHOUSE["PORT"],
        username=settings.CLICKHOUSE["USER"],
        password=settings.CLICKHOUSE["PASSWORD"],
        database=settings.CLICKHOUSE["DATABASE"],
    )
    client.command(
        """
        CREATE TABLE IF NOT EXISTS work_volume_record (
            id UInt64,
            factory UUID,
            start Date,
            finish Date,
            weight Int32,
            author UInt64,
            created Date
        )
        ENGINE = MergeTree
        ORDER BY (factory, start, finish, id)
        """
    )


def close():
    global client
    if client is None:
        return
    client.close()
    client = None


def save_work_volume_record(factory, start, finish, weight, author, created):
    client.insert(
        "work_volume_record",
        [
            [
                time.time_ns(),
                factory.external_id,
                start,
                finish,
                weight,
                author,
                created,
            ]
        ],
        column_names=[
            "id",
            "factory",
            "start",
            "finish",
            "weight",
            "author",
            "created",
        ],
    )


atexit.register(close)
