"""One explicit schema initializer for an empty or upgraded installation.

The API calls this at startup so a fresh database has every table before the
first request. It is deliberately data-free: no orgs, users, forms, or demo
rows are created.
"""
from __future__ import annotations


def init_all_schema() -> None:
    from core import state
    from core.auth_store import init_auth_db
    from core.commercial_store import init_commercial_db
    from core.company_context import init_context_db
    from core.form_store import init_form_db
    from core.jobs_store import init_jobs_db
    from core.marketing_store import init_marketing_db
    from core.ops_store import init_db as init_ops_db
    from core.plan_governance import init_governance_db
    from core.plan_input import _init_inputs_db
    from core.publishers_store import init_publishers_db
    from core.quotas import _init_usage_db
    from core.sales_store import init_sales_db
    from core.validation_plan import init_validation_db
    from core.workflow_store import init_db as init_workflow_db
    from core.worlddata_store import init_worlddata_db

    state.init_db()
    init_sales_db()
    init_marketing_db()
    init_workflow_db()
    init_ops_db()
    init_form_db()
    init_auth_db()
    init_jobs_db()
    init_publishers_db()
    init_context_db()
    init_validation_db()
    init_governance_db()
    init_commercial_db()
    init_worlddata_db()
    _init_inputs_db()
    _init_usage_db()
