import operator
from typing import Annotated, TypedDict


class SynState(TypedDict):
    # Identity
    run_id: str
    started_at: str

    # Planner output
    targets: list[dict]       # [{query, source, priority, reason}]
    plan_reasoning: str

    # Researcher output
    raw_results: Annotated[list[dict], operator.add]   # accumulation
    sources_searched: Annotated[list[str], operator.add]

    # Analyzer output
    analysis: str
    key_findings: list[dict]   # [{finding, evidence, importance: high|med|low}]
    competitor_updates: list[dict]

    # Writer output
    report_title: str
    report_body: str           # Markdown complet
    report_summary: str        # 3 phrases max pour Discord

    # Routing & control
    errors: Annotated[list[str], operator.add]
    current_agent: str
    status: str                # planning|researching|analyzing|writing|done|failed
