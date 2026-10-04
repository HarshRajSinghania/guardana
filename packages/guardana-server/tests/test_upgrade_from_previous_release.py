"""The upgrade `docs/deployment.md` describes, from the schema an older release shipped.

The database starts at the migration count of the oldest release in
`historical/releases.json` that both wrote a stored envelope and shipped migrations,
holding what an operator of that release would have: a tenant, a key and a run with
a finding. It is migrated forward with the runner the `migrate` command uses, and
then the key issued before the upgrade sends every stored envelope through the real
route. Everything, the pre-upgrade run included, has to come back through the
scoped store.
"""

import json
from typing import Any

import psycopg
import pytest
from conftest import DbConnection
from guardana.server.db.migrations import apply_pending, load_migrations, read_state
from guardana.server.envelope import Submission
from test_historical_envelopes import (
    HISTORICAL,
    bearer,
    issue_key,
    serve,
    stored_envelopes,
    tenant,
)
from test_migrations import _apply_through

_OK = 200
_IDENTITY = "sha256:" + "a" * 64


def _release_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def oldest_upgradable_release() -> tuple[str, int]:
    """The oldest release that stored an envelope and shipped a schema, with its migration count."""
    releases: dict[str, Any] = json.loads(
        (HISTORICAL / "releases.json").read_text(encoding="utf-8")
    )
    for version in sorted(releases, key=_release_key):
        release = releases[version]
        count = int(release["collector_migrations"])
        if release["kinds"]["envelope"].get("stored") and count > 0:
            return version, count
    raise AssertionError("no release in releases.json stored an envelope and shipped migrations")


def _a_run_from_before_the_upgrade(connection: DbConnection, project_id: int) -> None:
    """One submission and its finding, written with only the columns the old schema has."""
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into submissions (project_id, received_at, source, schema_version, rules_run) "
            "values (%s, now() - interval '1 day', 'before-the-upgrade', 7, 1) returning id",
            (project_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise AssertionError("the pre-upgrade submission was not written")
        cursor.execute(
            "insert into findings (submission_id, channel, position, rule_id, severity, title, "
            "target_ref, evidence_summary, identity) values "
            "(%s, 'findings', 0, 'guardana.supply_chain.pickle_opcode', 'CRITICAL', "
            "'Dangerous pickle opcode', 'model.pkl', 'imports os.system', %s)",
            (row[0], _IDENTITY),
        )
    connection.commit()


def test_the_oldest_upgradable_release_is_older_than_this_build() -> None:
    _, count = oldest_upgradable_release()

    assert 0 < count < len(load_migrations()), (
        "the upgrade below starts where this build already is, so it upgrades nothing"
    )


def test_a_collector_upgraded_from_an_older_release_keeps_its_data_and_takes_every_envelope(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, count = oldest_upgradable_release()
    with psycopg.connect(database_url) as connection:
        _apply_through(connection, count)
    project_id = tenant(database_url)
    token = issue_key(database_url, project_id, name="issued-before-the-upgrade")
    with psycopg.connect(database_url) as connection:
        _a_run_from_before_the_upgrade(connection, project_id)

        apply_pending(connection)

        assert read_state(connection).is_current
    collector = serve(database_url, project_id, monkeypatch, token=token)
    envelopes = [document for _, document in stored_envelopes()]
    for document in envelopes:
        response = collector.client.post(
            "/findings", json=document, headers=bearer(collector.token)
        )
        assert response.status_code == _OK, response.text

    before, *after = [record.submission for record in collector.store.records(collector.scope)]

    assert before.source == "before-the-upgrade"
    assert [finding.identity for finding in before.findings] == [_IDENTITY]
    assert after == [Submission.model_validate(document) for document in envelopes]
    assert [stored.schema_version for stored in after] == [
        document["schema_version"] for document in envelopes
    ]
