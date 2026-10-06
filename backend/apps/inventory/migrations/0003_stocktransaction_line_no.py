"""Deterministic per-part ledger numbering (timestamps can tie on coarse clocks)."""
from django.db import migrations, models


def backfill(apps, schema_editor):
    StockTransaction = apps.get_model("inventory", "StockTransaction")
    counters = {}
    for tx in StockTransaction.objects.order_by("part_id", "created_at", "pk").only("pk", "part_id"):
        counters[tx.part_id] = counters.get(tx.part_id, 0) + 1
        StockTransaction.objects.filter(pk=tx.pk).update(line_no=counters[tx.part_id])


class Migration(migrations.Migration):
    dependencies = [("inventory", "0002_initial")]

    operations = [
        migrations.AddField(model_name="stocktransaction", name="line_no",
                            field=models.PositiveIntegerField(null=True)),
        migrations.RunPython(backfill, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="stocktransaction", name="line_no",
            field=models.PositiveIntegerField(help_text="1, 2, 3… per part — assigned under the part row lock"),
        ),
        migrations.AlterModelOptions(name="stocktransaction", options={"ordering": ("part", "-line_no")}),
        migrations.AddConstraint(
            model_name="stocktransaction",
            constraint=models.UniqueConstraint(fields=("part", "line_no"), name="stock_tx_unique_line"),
        ),
    ]
