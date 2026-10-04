"""Deterministic fixtures for the governed market-validation path.

One realistic company, one realistic plan, and three synthetic prospects. Nothing
here contacts anyone: the fixtures exist so governance, the workflow engine, and
the simulated action can be exercised end to end without a provider.
"""

NORTHLIGHT_CONTEXT = {
    "company": {
        "name": "Northlight Ops",
        "description": "Northlight Ops runs a managed operations desk for small logistics teams.",
        "website": "https://northlight.example",
        "geography": "United States",
    },
    "product": {
        "name": "Managed Operations Desk",
        "description": "A guided setup and monthly review of the customer's operations handoffs.",
        "category": "Operations services",
        "value_proposition": "Operations teams get a clean handoff record in one week.",
    },
    "customer": {
        "ideal_customer": "Logistics companies with 20-200 people running dispatch on spreadsheets",
        "industry": "Logistics",
        "company_size": ["20-200"],
        "geography": ["United States"],
        "buyer_roles": ["Operations Director", "Founder"],
    },
    "market": {
        "market": "United States",
        "segment": "Small and midmarket logistics operators",
        "problem": "Dispatch handoffs live in spreadsheets, so missed loads are found late.",
        "urgency": "Missed loads are charged back within the same week.",
        "alternatives": ["Spreadsheet templates", "Freight broker software"],
    },
    "evidence": {
        "existing_customers": ["Two design partners running the desk since March"],
        "existing_demand": ["Eleven inbound emails after the LinkedIn post"],
        "previous_marketing": ["One LinkedIn post in March"],
        "testimonials": ["Operations Director, design partner: handoffs stopped falling through"],
        "traction": ["Two paid setups"],
        "other": ["Owner previously ran dispatch for six years"],
    },
    "offer": {
        "description": "A two-week managed operations setup plus monthly review.",
        "pricing": "$4,000 setup plus $1,500 per month",
        "business_model": "Subscription with a one-off setup fee",
    },
    "resources": {
        "channels": ["Email", "LinkedIn"],
        "assets": ["Two written case studies", "One short demo video"],
        "team": ["Founder", "One part-time operations contractor"],
        "budget": "$2,000 per month of paid distribution",
    },
    "constraints": {
        "geographic": ["United States only for the first year"],
        "brand": ["No claims about guaranteed load savings"],
        "budget": ["No sponsorships above $1,000"],
        "regulatory": [],
        "operational": ["Founder writes all outbound personally"],
    },
    "objective": {
        "primary_goal": "Get the first ten paying customers",
        "desired_outcome": "Ten paying customers and a repeatable weekly outreach habit",
    },
    "state": {"marketing_stage": "starting_from_zero"},
}

NORTHLIGHT_PLAN = {
    "workflow_template": "market_validation_v1",
    "hypothesis": {
        "customer": "Logistics companies with 20-200 people running dispatch on spreadsheets",
        "problem": "Dispatch handoffs live in spreadsheets, so missed loads are found late",
        "trigger": "Missed loads are charged back within the same week",
        "offer": "A two-week managed operations setup plus monthly review",
        "reason_to_believe": "Two design partners running the desk since March",
        "desired_action": "Book a 20-minute discovery call",
    },
    "market": {
        "target_customer": "Logistics companies with 20-200 people running dispatch on spreadsheets",
        "problem": "Dispatch handoffs live in spreadsheets, so missed loads are found late",
        "trigger": "Missed loads are charged back within the same week",
        "alternatives": "Spreadsheet templates and freight broker software",
    },
    "validation": {
        "method": "targeted_outbound",
        "channel": "email",
        "message": "I noticed your team runs dispatch on spreadsheets. How do you handle handoffs today?",
        "offer": "A two-week managed operations setup plus monthly review",
        "call_to_action": "Book a 20-minute discovery call",
        "validation_event": "Booked discovery call",
        "success_threshold": "At least 5 booked discovery calls from the first 50 targeted prospects",
        "time_window": "14 days",
    },
    "evidence": {
        "known_facts": ["Two design partners running the desk since March", "Two paid setups"],
        "assumptions": ["Operations directors will pay $4,000 setup plus $1,500 per month"],
        "unknowns": ["How many comparable operators run dispatch on spreadsheets"],
    },
    "reasoning": "The founder already writes outreach personally, has no paid budget, and has inbound demand, so targeted email measures demand fastest at no spend.",
    "next_action": "Review the plan and approve or reject the experiment",
    "limits": {
        "max_spend_usd": 0,
        "max_outreach_contacts": 50,
        "channel": "email",
        "duration_days": 14,
        "target_events": 5,
        "requires_approval": True,
    },
}

# Synthetic prospects. Names are invented and no address is ever resolved.
MOCK_PROSPECTS = [
    {"id": "sim_prospect_1", "company": "Harborline Freight", "role": "Operations Director"},
    {"id": "sim_prospect_2", "company": "Cedar Route Logistics", "role": "Founder"},
    {"id": "sim_prospect_3", "company": "Pinegate Carriers", "role": "Head of Operations"},
]


def plan_with(**limit_overrides) -> dict:
    """The Northlight plan with limit overrides, for governance tests."""
    return {
        **NORTHLIGHT_PLAN,
        "limits": {**NORTHLIGHT_PLAN["limits"], **limit_overrides},
    }


def plan_with_validation(**validation_overrides) -> dict:
    """The Northlight plan with validation-field overrides, for governance tests."""
    return {
        **NORTHLIGHT_PLAN,
        "validation": {**NORTHLIGHT_PLAN["validation"], **validation_overrides},
    }