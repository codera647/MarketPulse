"""Whole-date quarantine for confirmed boundary failures, never UNKNOWN work."""

from __future__ import annotations

from datetime import date

from trailforge.runtime import Harness

from marketpulse.outcomes import MissingOutcomeBoundary, outcome_binding, regular_outcomes
from marketpulse.storage import RawStore, digest

QUALITY_POLICY = "quarantine-missing-boundaries/1"


def boundary_exclusion(pipeline, contract: dict, contract_hash: str, session: str) -> dict:
    binding = outcome_binding(date.fromisoformat(session), contract["feed"],
                              contract["adjustment"],
                              getattr(pipeline.client, "base_url", "https://data.alpaca.markets"))
    key = digest(binding)
    job = pipeline.store.get_job(key)
    if not job or job["status"] != "FAILED":
        raise ValueError("only a confirmed failed outcome can be quarantined")
    harness = Harness(pipeline.harness_path, tenant_id="local-demo",
                      resource_id=f"marketpulse:regular_outcome:{key}", adapters=[],
                      tenant_limit=100000, global_limit=1000000)
    record = harness.inspect(job["run_id"])
    fetch, verify = record["tasks"]["fetch"], record["tasks"]["verify"]
    if (record["state"] != "FAILED" or record["goal"]["tasks"][-1]["input"] != binding
            or (verify.get("result") or {}).get("verdict") != "FAIL"
            or fetch["status"] != "DONE" or not verify.get("receipt")):
        raise ValueError("quarantine requires terminal typed verification failure")
    hashes = fetch["result"]["hashes"]
    if fetch["result"]["pages"] != len(hashes):
        raise ValueError("cannot quarantine an incomplete capture")
    try:
        regular_outcomes(pipeline.raw, hashes, binding)
    except MissingOutcomeBoundary:
        pass
    else:
        raise ValueError("outcome does not have a confirmed missing boundary")
    return {"schema": QUALITY_POLICY, "contract_hash": contract_hash,
            "session": session, "symbols": contract["symbols"],
            "reason": "missing_exact_opening_or_closing_minute",
            "binding": binding, "outcome_job_key": key, "run_id": job["run_id"],
            "raw_page_digests": hashes, "verify_receipt": verify["receipt"],
            "labels_fabricated": False}


def record_exclusion(pipeline, contract: dict, contract_hash: str, session: str) -> dict:
    exclusion = boundary_exclusion(pipeline, contract, contract_hash, session)
    key = RawStore(pipeline.data_dir / "exclusions").put(exclusion)
    with pipeline.store.connect() as db:
        db.execute("INSERT OR IGNORE INTO dataset_exclusions VALUES (?,?,?)",
                   (contract_hash, session, key))
        saved = db.execute("SELECT exclusion_hash FROM dataset_exclusions "
                           "WHERE contract_hash=? AND session=?",
                           (contract_hash, session)).fetchone()
        if saved[0] != key:
            raise ValueError("immutable quarantine evidence changed")
    return {"session": session, "exclusion_hash": key}


def validated_exclusions(pipeline, contract: dict, contract_hash: str) -> list[dict]:
    with pipeline.store.connect() as db:
        entries = [dict(row) for row in db.execute(
            "SELECT session,exclusion_hash FROM dataset_exclusions WHERE contract_hash=? "
            "ORDER BY session", (contract_hash,))]
    if entries and contract.get("quality_policy") != QUALITY_POLICY:
        raise ValueError("unapproved quarantine policy")
    store = RawStore(pipeline.data_dir / "exclusions")
    for entry in entries:
        if store.get(entry["exclusion_hash"]) != boundary_exclusion(
                pipeline, contract, contract_hash, entry["session"]):
            raise ValueError("quarantine no longer matches failed source evidence")
    return entries
