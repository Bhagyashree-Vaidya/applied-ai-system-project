"""Sample household shared by the CLI demo and the eval script."""
from __future__ import annotations

from datetime import datetime

from pawpal_system import Owner, Pet, Task


def sample_owner(now: datetime) -> Owner:
    """Jordan's household: three pets, one time conflict and one task over budget."""
    at = lambda h, m=0: now.replace(hour=h, minute=m, second=0, microsecond=0)
    owner = Owner("Jordan", available_minutes_per_day=90)
    biscuit, whiskers, nibbles = Pet("Biscuit", "dog", 3), Pet("Whiskers", "cat", 12), Pet("Nibbles", "rabbit", 1)
    for p in (biscuit, whiskers, nibbles):
        owner.add_pet(p)
    biscuit.add_task(Task("Morning walk", at(8), 30, "high", "daily"))
    whiskers.add_task(Task("Feeding", at(8, 15), 10, "high", "daily"))  # overlaps the walk
    nibbles.add_task(Task("Hay and water", at(9), 10, "high", "daily"))
    whiskers.add_task(Task("Grooming", at(14), 60, "low"))  # will not fit the 90-min budget
    return owner
