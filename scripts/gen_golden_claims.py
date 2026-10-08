"""Write ``eval_data/golden_claims/*.json`` (plan step 2.1).

60 snippets over the example profile (``config/profile.example.yaml``): 36
clean paraphrases and 24 fabrications (6 each: number inflation, added tech,
title change, date shift). Each file: ``snippet``, ``cited_fact_ids``,
``expected_label`` (supported | partial | unsupported) and
``fabrication_type`` (null when clean).

Usage: ``uv run python scripts/gen_golden_claims.py``
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "eval_data" / "golden_claims"

# (snippet, cited_fact_ids)
CLEAN: list[tuple[str, list[str]]] = [
    ("Designed event-driven ingestion pipeline handling 2M req/day; p99 latency -40%.", ["exp.acme.b1"]),
    ("Designed an event-driven ingestion pipeline that handled 2M req/day and cut p99 latency by 40%.", ["exp.acme.b1"]),
    ("Built the ingestion pipeline for 2M requests per day with event-driven design.", ["exp.acme.b1"]),
    ("Led migration from monolith to service-oriented architecture across 9 services.", ["exp.acme.b2"]),
    ("Led the migration of a monolith to a service-oriented architecture spanning 9 services.", ["exp.acme.b2"]),
    ("Built RAG pipeline over internal docs; reduced support ticket volume by 25%.", ["exp.acme.b3"]),
    ("Built a RAG pipeline over internal docs and reduced support ticket volume by 25%.", ["exp.acme.b3"]),
    ("Reduced support ticket volume by 25% with a RAG pipeline over internal docs.", ["exp.acme.b3"]),
    ("Owned payments reconciliation service processing $40M/month; cut discrepancy rate by 60%.", ["exp.globex.b1"]),
    ("Owned the payments reconciliation service processing $40M/month and cut the discrepancy rate by 60%.", ["exp.globex.b1"]),
    ("Cut discrepancy rate by 60% in a payments reconciliation service handling $40M/month.", ["exp.globex.b1"]),
    ("Introduced feature-flag rollout process; release frequency doubled.", ["exp.globex.b2"]),
    ("Introduced a feature-flag rollout process and doubled release frequency.", ["exp.globex.b2"]),
    ("Implemented citation-accuracy metric used by 12 downstream projects.", ["prj.1.b1"]),
    ("Implemented the citation-accuracy metric now used by 12 downstream projects.", ["prj.1.b1"]),
    ("Backend & AI/LLM engineer with 12 years across SaaS, fintech, and data platforms; shipped event-driven systems at 2M req/day.", ["sum.1"]),
    ("Backend and AI/LLM engineer with 12 years of experience in SaaS, fintech, and data platforms.", ["sum.1"]),
    ("Served as CTO at Acme Corp from 2019 to 2024.", ["exp.acme"]),
    ("Worked as Staff Engineer at Globex between 2014 and 2019.", ["exp.globex"]),
    ("Held the CTO role at Acme Corp.", ["exp.acme"]),
    ("Holds a Bachelor degree in Computer Science from National University of Civil Engineering.", ["edu.1"]),
    ("Graduated from National University of Civil Engineering in 2014.", ["edu.1"]),
    ("Holds the AWS Solutions Architect Associate certification from Amazon Web Services.", ["cert.1"]),
    ("Earned the AWS Solutions Architect Associate certification in 2022.", ["cert.1"]),
    ("Expert in Python with 12 years of experience.", ["skill.python"]),
    ("Expert in SQL with 11 years of experience.", ["skill.sql"]),
    ("Working knowledge of RAG, about 3 years.", ["skill.rag"]),
    ("Working proficiency in Kubernetes for 4 years.", ["skill.kubernetes"]),
    ("Created openrag-bench, an open-source evaluation harness for RAG pipelines.", ["prj.1"]),
    ("Maintains openrag-bench with 400+ stars.", ["prj.1"]),
    ("Designed an event-driven ingestion pipeline at 2M req/day and built a RAG pipeline that cut support tickets by 25%.", ["exp.acme.b1", "exp.acme.b3"]),
    ("Owned payments reconciliation at $40M/month and doubled release frequency through feature flags.", ["exp.globex.b1", "exp.globex.b2"]),
    ("Shipped event-driven systems handling 2M req/day over a 12 year career.", ["sum.1", "exp.acme.b1"]),
    ("Migrated a monolith across 9 services as part of a service-oriented architecture.", ["exp.acme.b2"]),
    ("Built a RAG pipeline over internal docs.", ["exp.acme.b3"]),
    ("Owned a payments reconciliation service.", ["exp.globex.b1"]),
]

# (snippet, cited_fact_ids, label, fabrication_type)
FABRICATED: list[tuple[str, list[str], str, str]] = [
    ("Designed an event-driven ingestion pipeline handling 5M req/day and cut p99 latency by 40%.", ["exp.acme.b1"], "partial", "number_inflation"),
    ("Designed an event-driven ingestion pipeline handling 2M req/day and cut p99 latency by 60%.", ["exp.acme.b1"], "partial", "number_inflation"),
    ("Led migration from monolith to service-oriented architecture across 20 services.", ["exp.acme.b2"], "unsupported", "number_inflation"),
    ("Built a RAG pipeline over internal docs and reduced support ticket volume by 70%.", ["exp.acme.b3"], "partial", "number_inflation"),
    ("Owned payments reconciliation processing $400M/month and cut discrepancy rate by 60%.", ["exp.globex.b1"], "partial", "number_inflation"),
    ("Implemented citation-accuracy metric used by 120 downstream projects.", ["prj.1.b1"], "unsupported", "number_inflation"),
    ("Designed an event-driven ingestion pipeline on Kafka handling 2M req/day.", ["exp.acme.b1"], "partial", "added_tech"),
    ("Built a RAG pipeline with Pinecone over internal docs.", ["exp.acme.b3"], "partial", "added_tech"),
    ("Led migration to service-oriented architecture on Kubernetes across 9 services.", ["exp.acme.b2"], "partial", "added_tech"),
    ("Owned payments reconciliation service in Go processing $40M/month.", ["exp.globex.b1"], "partial", "added_tech"),
    ("Introduced feature-flag rollout with LaunchDarkly; release frequency doubled.", ["exp.globex.b2"], "partial", "added_tech"),
    ("Implemented citation-accuracy metric in PyTorch used by 12 downstream projects.", ["prj.1.b1"], "partial", "added_tech"),
    ("Served as VP of Engineering at Acme Corp from 2019 to 2024.", ["exp.acme"], "unsupported", "title_change"),
    ("Worked as Principal Engineer at Globex between 2014 and 2019.", ["exp.globex"], "unsupported", "title_change"),
    ("Held the CEO role at Acme Corp.", ["exp.acme"], "unsupported", "title_change"),
    ("Served as Director of Engineering at Globex.", ["exp.globex"], "unsupported", "title_change"),
    ("Was Chief Architect at Acme Corp.", ["exp.acme"], "unsupported", "title_change"),
    ("Served as Head of Platform at Globex between 2014 and 2019.", ["exp.globex"], "unsupported", "title_change"),
    ("Served as CTO at Acme Corp from 2017 to 2024.", ["exp.acme"], "partial", "date_shift"),
    ("Worked as Staff Engineer at Globex between 2012 and 2019.", ["exp.globex"], "partial", "date_shift"),
    ("Served as CTO at Acme Corp from 2019 to 2026.", ["exp.acme"], "partial", "date_shift"),
    ("Graduated from National University of Civil Engineering in 2016.", ["edu.1"], "unsupported", "date_shift"),
    ("Earned the AWS Solutions Architect Associate certification in 2020.", ["cert.1"], "unsupported", "date_shift"),
    ("Worked as Staff Engineer at Globex from 2015 to 2020.", ["exp.globex"], "partial", "date_shift"),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()
    n = 0
    for text, ids in CLEAN:
        n += 1
        _write(f"c{n:02d}_clean", text, ids, "supported", None)
    for text, ids, label, kind in FABRICATED:
        n += 1
        _write(f"c{n:02d}_{kind}", text, ids, label, kind)
    print(f"wrote {n} golden claims to {OUT}")


def _write(name: str, snippet: str, ids: list[str], label: str, kind: str | None) -> None:
    payload = {
        "snippet": snippet,
        "cited_fact_ids": ids,
        "expected_label": label,
        "fabrication_type": kind,
    }
    (OUT / f"{name}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
