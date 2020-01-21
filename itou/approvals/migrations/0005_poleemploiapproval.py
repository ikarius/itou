# Generated by Django 2.2.9 on 2020-01-21 12:48

from django.db import migrations, models
import django.utils.timezone
import itou.approvals.models


class Migration(migrations.Migration):

    dependencies = [("approvals", "0004_auto_20191218_1337")]

    operations = [
        migrations.CreateModel(
            name="PoleEmploiApproval",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "pe_structure_code",
                    models.CharField(
                        max_length=5, verbose_name="Code structure Pôle emploi"
                    ),
                ),
                (
                    "pe_regional_id",
                    models.CharField(
                        max_length=8, verbose_name="Code regional Pôle emploi"
                    ),
                ),
                (
                    "number",
                    models.CharField(max_length=15, unique=True, verbose_name="Numéro"),
                ),
                (
                    "first_name",
                    models.CharField(
                        db_index=True, max_length=150, verbose_name="Prénom"
                    ),
                ),
                (
                    "last_name",
                    models.CharField(db_index=True, max_length=150, verbose_name="Nom"),
                ),
                (
                    "birth_name",
                    models.CharField(
                        db_index=True, max_length=150, verbose_name="Nom de naissance"
                    ),
                ),
                (
                    "birthdate",
                    models.DateField(
                        blank=True,
                        db_index=True,
                        null=True,
                        verbose_name="Date de naissance",
                    ),
                ),
                ("start_at", models.DateField(verbose_name="Date de début")),
                ("end_at", models.DateField(verbose_name="Date de fin")),
                (
                    "created_at",
                    models.DateTimeField(
                        default=django.utils.timezone.now,
                        verbose_name="Date de création",
                    ),
                ),
            ],
            options={
                "verbose_name": "Agrément Pôle emploi",
                "verbose_name_plural": "Agréments Pôle emploi",
                "ordering": ["-start_at"],
            },
            bases=(models.Model, itou.approvals.models.CommonApprovalMixin),
        )
    ]