import asyncio

from app.schemas.trial import TrialCreate
from app.services import trial_service


class Result:
    def __init__(self, inserted):
        self.inserted = inserted

    def scalar_one(self):
        return self.inserted


class Session:
    def __init__(self, inserted):
        self.inserted = inserted
        self.committed = False

    async def execute(self, statement):
        assert "xmax = 0" in str(statement)
        return Result(self.inserted)

    async def commit(self):
        self.committed = True


def test_upsert_distinguishes_insert_from_update(monkeypatch):
    monkeypatch.setattr(trial_service, "_embed", lambda text: [0.1])

    async def upsert_trial(**kwargs):
        pass

    monkeypatch.setattr(trial_service.qdrant_service, "upsert_trial", upsert_trial)
    trial = TrialCreate(nct_id="NCT12345678", title="Study")
    inserted = Session(True)
    updated = Session(False)
    assert asyncio.run(trial_service.upsert_trial(inserted, trial)) == (
        "NCT12345678",
        True,
    )
    assert asyncio.run(trial_service.upsert_trial(updated, trial)) == (
        "NCT12345678",
        False,
    )
    assert inserted.committed and updated.committed
