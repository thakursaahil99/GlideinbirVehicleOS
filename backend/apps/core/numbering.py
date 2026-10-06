from django.db import transaction
from django.utils import timezone

from .models import NumberSequence


def next_number(prefix):
    """
    Return the next ``<PREFIX>-<YYYY>-<NNNNNN>`` number.

    The counter row is locked with SELECT ... FOR UPDATE, so concurrent callers
    get distinct, gap-free numbers. Call inside the business transaction so a
    rolled-back booking/invoice also rolls back its number.
    """
    year = timezone.localdate().year
    with transaction.atomic():
        NumberSequence.objects.get_or_create(prefix=prefix, year=year)
        seq = NumberSequence.objects.select_for_update().get(prefix=prefix, year=year)
        seq.last_value += 1
        seq.save(update_fields=["last_value"])
        return f"{prefix}-{year}-{seq.last_value:06d}"
