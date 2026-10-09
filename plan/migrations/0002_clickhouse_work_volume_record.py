from django.db import migrations


def create_clickhouse_tables(apps, schema_editor):
    from plan.clickhouse import create_tables

    create_tables()


class Migration(migrations.Migration):

    dependencies = [
        ("plan", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_clickhouse_tables, migrations.RunPython.noop),
    ]
