"""Drive the complete analytical workflow through the API.

This exercises the journey a signed-in user actually performs:

    catalogue -> brief -> sites -> score -> explanation -> comparison
    -> requirements -> property -> brokerage -> scenarios -> sensitivity
    -> data quality -> exports (PDF / CSV / Excel / JSON)

Every step asserts the response shape it expects, so a regression is a
failure rather than a silently wrong payload.  The token is read from the
environment.
"""

from __future__ import annotations

import io
import json
import os
import sys
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from platform_env import load_environment  # noqa: E402

load_environment()

BASE = os.getenv("API_AUDIT_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
TOKEN = os.getenv("API_AUDIT_TOKEN", "")

PASSED: list[str] = []
FAILED: list[tuple[str, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"  PASS  {name}")
    else:
        FAILED.append((name, detail))
        print(f"  FAIL  {name}  {detail}")


def call(method: str, path: str, **kwargs) -> requests.Response:
    headers = {"Accept": "application/json", **kwargs.pop("headers", {})}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    return requests.request(method, f"{BASE}{path}", headers=headers, timeout=180, **kwargs)


def main() -> int:
    if not TOKEN:
        print("API_AUDIT_TOKEN is not set.")
        return 2

    # ------------------------------------------------------------------
    print("1. The requirement catalogue")
    response = call("GET", "/requirements/catalog")
    catalogue = response.json() if response.status_code == 200 else {}
    check("catalogue responds", response.status_code == 200, str(response.status_code))
    check(
        "catalogue carries the business types",
        bool(catalogue.get("business_types")),
        "no business_types in the payload",
    )
    business_types = [b.get("key") for b in catalogue.get("business_types", [])]
    print(f"      business types: {business_types[:6]}")

    business_type = business_types[0] if business_types else "grocery"

    response = call("GET", f"/requirements/profile/{business_type}")
    check(
        "the business profile resolves",
        response.status_code == 200,
        f"{response.status_code} {response.text[:120]}",
    )

    # ------------------------------------------------------------------
    print("2. The candidate sites")
    response = call("GET", "/sites")
    sites = response.json() if response.status_code == 200 else {}
    site_list = sites.get("sites", [])
    check("sites respond", response.status_code == 200, str(response.status_code))
    check("sites are returned", len(site_list) > 0, "no sites")
    site_ids = [s.get("site_id") for s in site_list]
    print(f"      sites: {site_ids}")

    # ------------------------------------------------------------------
    print("3. The criteria tree and the weight roll-up")
    response = call("GET", "/criteria")
    tree = response.json() if response.status_code == 200 else {}
    check("criteria respond", response.status_code == 200, str(response.status_code))

    response = call("GET", "/criteria/scorable")
    check(
        "the scorable criteria resolve",
        response.status_code == 200,
        f"{response.status_code} {response.text[:120]}",
    )

    # ------------------------------------------------------------------
    print("4. The ranking")
    weights = {
        "site_and_property": 0.5,
        "competition": 0.3,
        "accessibility": 0.2,
    }
    body = {
        "method": "weighted_sum",
        "level_weights": {"category_weights": weights, "leaf_weights": None},
    }
    response = call("POST", "/score", json=body)
    score = response.json() if response.status_code == 200 else {}
    check("the ranking responds", response.status_code == 200, str(response.status_code))
    ranked = score.get("sites", [])
    check("the ranking has rows", len(ranked) > 0, "no ranking rows")
    check(
        "the ranking identifies the sites",
        all(r.get("site_id") in site_ids for r in ranked),
        f"unknown site ids in {ranked}",
    )
    check(
        "the ranks are a sequence",
        [r.get("rank") for r in ranked] == list(range(1, len(ranked) + 1)),
        f"ranks are {[r.get('rank') for r in ranked]}",
    )
    check(
        "the scores are within [0, 1]",
        all(0.0 <= float(r.get("score", -1)) <= 1.0 for r in ranked),
        f"scores are {[r.get('score') for r in ranked]}",
    )
    print(f"      ranking: {[(r['rank'], r['site_id'], r['score']) for r in ranked]}")
    print(f"      coverage: {score.get('coverage')}, dropped: {len(score.get('dropped_criteria', []))}")

    for method in ("weighted_product", "distance_to_ideal"):
        response = call(
            "POST", "/score", json={**body, "method": method}
        )
        check(
            f"the ranking also works with {method}",
            response.status_code == 200,
            f"{response.status_code} {response.text[:160]}",
        )

    # ------------------------------------------------------------------
    print("5. The decomposition and the explanation")
    top_site = ranked[0]["site_id"] if ranked else None
    if top_site:
        params = {
            "weights": json.dumps(score.get("effective_weights", {})),
            "method": "weighted_sum",
        }
        response = call(
            "GET", f"/sites/{top_site}/decomposition", params=params
        )
        check(
            "the decomposition responds",
            response.status_code == 200,
            f"{response.status_code} {response.text[:160]}",
        )

        response = call(
            "POST",
            "/explanations/site",
            json={
                "site_id": top_site,
                "method": "weighted_sum",
                "level_weights": {
                    "category_weights": weights,
                    "leaf_weights": None,
                },
                "include_stability": True,
            },
        )
        explanation = response.json() if response.status_code == 200 else {}
        check(
            "the explanation responds",
            response.status_code == 200,
            f"{response.status_code} {response.text[:200]}",
        )
        check(
            "the explanation names the site",
            str(explanation.get("site_id")) == str(top_site),
            f"site_id is {explanation.get('site_id')}",
        )
        print(f"      explanation keys: {sorted(explanation.keys())[:12]}")

    # ------------------------------------------------------------------
    print("6. The requirement evaluation")
    requirements = {
        "acquisition_mode": "either",
        "parking": {
            "minCarSpaces": 10,
            "minTwoWheelerSpaces": 5,
            "behaviour": "preference",
            "scope": "site",
        },
        "facilities": [],
        "business_requirements": [],
        "financial": {
            "budgets": [],
            "budgetBehaviour": "penalise",
            "horizonMonths": 60,
        },
    }
    response = call(
        "POST", "/requirements/evaluate", json={"requirements": requirements}
    )
    evaluation = response.json() if response.status_code == 200 else {}
    check(
        "the evaluation responds",
        response.status_code == 200,
        f"{response.status_code} {response.text[:200]}",
    )
    check(
        "the evaluation covers the sites",
        len(evaluation.get("sites", [])) == len(site_list),
        f"{len(evaluation.get('sites', []))} of {len(site_list)}",
    )
    first = (evaluation.get("sites") or [{}])[0]
    check(
        "the evaluation reports the cost",
        isinstance(first.get("evaluation", {}).get("cost"), dict),
        "no cost block",
    )
    cost = first.get("evaluation", {}).get("cost", {})
    lines = cost.get("lines", [])
    check(
        "every cost line carries its provenance",
        all("provenance" in line for line in lines),
        f"lines are {lines}",
    )
    print(f"      cost lines: {[(l.get('key'), l.get('provenance')) for l in lines]}")

    # ------------------------------------------------------------------
    print("7. The property and brokerage intelligence")
    response = call("GET", "/properties/sources")
    check(
        "the property sources respond",
        response.status_code == 200,
        f"{response.status_code} {response.text[:160]}",
    )

    response = call(
        "POST",
        "/properties/search",
        json={"site_ids": site_ids[:2], "radius_m": 5000, "limit_per_site": 5},
    )
    check(
        "the property search responds",
        response.status_code == 200,
        f"{response.status_code} {response.text[:200]}",
    )

    response = call("GET", "/brokerage/sources")
    check(
        "the brokerage sources respond",
        response.status_code == 200,
        f"{response.status_code} {response.text[:160]}",
    )

    response = call(
        "GET",
        "/brokerage/search-sites",
        params={"site_ids": ",".join(site_ids[:3]), "radius_m": 5000, "limit_per_site": 5},
    )
    check(
        "the brokerage search responds",
        response.status_code == 200,
        f"{response.status_code} {response.text[:200]}",
    )

    # ------------------------------------------------------------------
    print("8. The scenarios")
    response = call(
        "POST",
        "/scenarios",
        json={
            "name": "Operational audit scenario",
            "weight_set": score.get("effective_weights", {}),
            "aggregation_method": "weighted_sum",
        },
    )
    check(
        "a scenario can be saved",
        response.status_code == 201,
        f"{response.status_code} {response.text[:200]}",
    )
    scenario = response.json() if response.status_code == 201 else {}
    scenario_id = scenario.get("scenario_id")

    response = call("GET", "/scenarios")
    check(
        "the scenarios can be listed",
        response.status_code == 200,
        f"{response.status_code} {response.text[:200]}",
    )
    check(
        "the saved scenario is listed",
        any(s.get("scenario_id") == scenario_id for s in response.json()),
        f"scenario {scenario_id} is missing",
    )

    if scenario_id is not None:
        response = call("GET", f"/scenarios/{scenario_id}")
        check(
            "a scenario can be read back",
            response.status_code == 200,
            f"{response.status_code} {response.text[:200]}",
        )
        check(
            "the scenario carries a ranking",
            bool(response.json().get("ranking")),
            "no ranking",
        )

    # ------------------------------------------------------------------
    print("9. The sensitivity analysis")
    query = {
        "weights": json.dumps(score.get("effective_weights", {})),
        "method": "weighted_sum",
    }
    for path in (
        "/sensitivity/thresholds",
        "/sensitivity/stability",
        "/sensitivity/near-ties",
        "/sensitivity/cross-method",
        "/sensitivity/rank-reversals",
        "/sensitivity/monte-carlo",
    ):
        response = call("GET", path, params=query)
        check(
            f"{path} responds",
            response.status_code == 200,
            f"{response.status_code} {response.text[:160]}",
        )

    # ------------------------------------------------------------------
    print("10. The data quality")
    response = call("GET", "/data-quality")
    quality = response.json() if response.status_code == 200 else {}
    check(
        "the data quality responds",
        response.status_code == 200,
        str(response.status_code),
    )
    check(
        "the data quality lists its sources",
        len(quality.get("sources", [])) > 0,
        "no sources",
    )
    check(
        "the data quality reports the matrix release",
        quality.get("coverage", {}).get("latest_release") is not None,
        "no matrix release",
    )

    # ------------------------------------------------------------------
    print("11. The report exports")
    response = call("GET", "/reports/export/formats")
    formats = response.json() if response.status_code == 200 else {}
    check(
        "the export formats respond",
        response.status_code == 200,
        str(response.status_code),
    )
    available = formats.get("formats", [])
    print(f"      formats: {[f.get('key') for f in available]}")

    # The report is generated first, and the export renders exactly that
    # payload, which is what the interface does.
    response = call(
        "POST",
        "/reports/generate",
        json={
            "analysis": {
                "name": "Operational audit analysis",
                "business_type": business_type,
                "acquisition_mode": "either",
                "location": {"city": "Chennai"},
                "aggregation_method": "weighted_sum",
                "weights": score.get("effective_weights", {}),
            },
            "ranking": ranked,
            "explanations": [explanation] if explanation else [],
            "cost_assessments": [
                site.get("evaluation", {}).get("cost")
                for site in evaluation.get("sites", [])
                if site.get("evaluation", {}).get("cost")
            ],
            "data_quality": quality,
        },
    )
    report = response.json() if response.status_code == 200 else {}
    check(
        "the report is generated",
        response.status_code == 200,
        f"{response.status_code} {response.text[:200]}",
    )
    check(
        "the report carries the ranking",
        bool(report.get("top_sites")),
        f"report keys: {sorted(report.keys())[:14]}",
    )
    check(
        "the report carries the weighting configuration",
        bool(report.get("analysis", {}).get("weights")),
        f"analysis keys: {sorted(report.get('analysis', {}).keys())[:10]}",
    )
    check(
        "the report states the aggregation method",
        bool(report.get("methodology", {}).get("aggregation_method")),
        f"methodology keys: {sorted(report.get('methodology', {}).keys())[:10]}",
    )
    check(
        "the report states its assumptions",
        bool(report.get("assumptions")),
        "no assumptions",
    )
    check(
        "the report carries the data-quality information",
        bool(report.get("data_quality")),
        "no data quality",
    )

    for export_format in ("pdf", "csv", "xlsx", "json"):
        response = call(
            "POST",
            "/reports/export",
            json={"format": export_format, "report": report},
        )
        ok = response.status_code == 200
        check(
            f"the {export_format} export responds",
            ok,
            f"{response.status_code} {response.text[:200]}",
        )
        if not ok:
            continue
        content = response.content
        if export_format == "pdf":
            check("the PDF is a PDF", content[:4] == b"%PDF", repr(content[:8]))
        elif export_format == "xlsx":
            check("the Excel file is a zip", content[:2] == b"PK", repr(content[:8]))
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    names = archive.namelist()
                check(
                    "the Excel file has a workbook",
                    any(name.startswith("xl/workbook") for name in names),
                    f"{names[:5]}",
                )
            except zipfile.BadZipFile as exc:
                check("the Excel file opens", False, str(exc))
        elif export_format == "csv":
            check("the CSV has rows", len(content.splitlines()) > 1, repr(content[:120]))
        else:
            try:
                payload = json.loads(content)
                check("the JSON export parses", isinstance(payload, dict), type(payload).__name__)
            except json.JSONDecodeError as exc:
                check("the JSON export parses", False, str(exc))
        print(f"      {export_format}: {len(content)} bytes")

    # ------------------------------------------------------------------
    print("12. The analysis persistence")
    response = call(
        "POST",
        "/projects",
        json={
            "name": "Operational audit analysis",
            "business_type": business_type,
            "acquisition_mode": "either",
            "location": {"city": "Chennai", "area": "Anna Nagar"},
            "weights": score.get("effective_weights", {}),
            "aggregation_method": "weighted_sum",
            "requirements": [],
            "facilities": [],
            "parking": {},
            "financial": {"budgets": [], "horizonMonths": 60},
        },
    )
    check(
        "an analysis can be saved",
        response.status_code == 201,
        f"{response.status_code} {response.text[:300]}",
    )
    project = response.json() if response.status_code == 201 else {}
    project_id = project.get("id")

    if project_id:
        response = call("GET", f"/projects/{project_id}")
        check(
            "the analysis can be read back",
            response.status_code == 200,
            f"{response.status_code} {response.text[:200]}",
        )
        check(
            "the analysis keeps its name",
            response.json().get("name") == "Operational audit analysis",
            f"name is {response.json().get('name')}",
        )

        response = call(
            "PATCH",
            f"/projects/{project_id}",
            json={"name": "Operational audit analysis (updated)"},
        )
        check(
            "the analysis can be updated",
            response.status_code == 200,
            f"{response.status_code} {response.text[:200]}",
        )

        response = call("GET", "/projects")
        check(
            "the analyses can be listed",
            response.status_code == 200,
            f"{response.status_code} {response.text[:200]}",
        )
        check(
            "the saved analysis is listed",
            any(p.get("id") == project_id for p in response.json().get("projects", [])),
            f"analysis {project_id} is missing",
        )

        response = call("DELETE", f"/projects/{project_id}")
        check(
            "the analysis can be deleted",
            response.status_code in (200, 204),
            f"{response.status_code} {response.text[:200]}",
        )

    # ------------------------------------------------------------------
    print()
    print(f"{len(PASSED)} passed, {len(FAILED)} failed")
    for name, detail in FAILED:
        print(f"  FAILED: {name}  {detail}")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    raise SystemExit(main())
