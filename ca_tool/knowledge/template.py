"""The Competitive Analysis template, encoded from `Prismm Comp Analysis v1.xlsx`
(Company Analysis + Feature Comparison sheets) and PDD step 12 (Company Overview page).

Each metric's `question` is the template's "What it means?" column; it doubles as the
research instruction given to the AI.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Metric:
    key: str
    group: str          # column A of the Company Analysis sheet
    label: str          # column B
    question: str       # column C "What it means?"


# Company Overview page fields (PDD step 12 / deck "<Company> Overview" slides)
OVERVIEW = [
    Metric("founding_year", "Overview", "Founding Year", "What year was the company founded?"),
    Metric("headquarters", "Overview", "Headquarters Location", "Where is the company headquartered (city, country)?"),
    Metric("geographies", "Overview", "Geographies", "Which regions/countries does the company operate or sell in?"),
    Metric("employees", "Overview", "Number of Employees", "How many employees (exact or LinkedIn range)?"),
    Metric("target_market", "Overview", "Target Market", "Which industries, company sizes and buyer roles does it target?"),
    Metric("use_cases", "Overview", "Primary Use Cases", "What are the main use cases of the product?"),
    Metric("deployment", "Overview", "Deployment", "How is the product delivered (SaaS/cloud, on-prem, mobile app, managed service) and how fast can a customer start?"),
]

# Company Analysis sheet rows
COMPANY_ANALYSIS = [
    Metric("description", "Overview", "Description", "Background and overview of the company and what it sells."),
    Metric("brand_position", "Market Position", "Brand Position", "What is the overall company image? How does it describe itself and its positioning?"),
    Metric("services", "Market Position", "Services", "Beyond product sales, what additional services does the company offer to gain a competitive advantage (auxiliary services)?"),
    Metric("usvp", "Market Position", "Unique Selling Value Proposition (USVP)", "What is the unique differentiator that sets the company apart?"),
    Metric("customer_focus", "Market Position", "Customer Focus", "Who are the target audiences and what are their specific needs?"),
    Metric("positive_reviews", "Market Position", "Positive Reviews", "What do customers like? Summarise themes from reviews (G2, Capterra, Trustpilot, Reddit)."),
    Metric("negative_reviews", "Market Position", "Negative Reviews", "What do customers dislike? Summarise themes from reviews."),
    Metric("innovation", "Market Position", "Innovation", "What new products/features have been launched recently? Any innovation awards?"),
    Metric("customer_service", "Market Position", "Customer Service", "Review scores/ratings and how the company supports customers (help centre, live chat, account managers)."),
    Metric("partnerships", "Market Position", "Relationships and Partnerships", "What collaborations, integrations, acquisitions or channel partnerships exist?"),
    Metric("marketing_channels", "Marketing Audit", "Marketing Channels", "Which marketing channels and content does the company use (LinkedIn, YouTube, blog, webinars, events, SEO)?"),
    Metric("hiring_signals", "Marketing Audit", "Hiring Signals", "What do current job listings suggest about priorities and growth plans?"),
    Metric("tech_stack", "Technologies", "Tech Stack", "What technologies/platforms does the product use or integrate with?"),
    Metric("funding", "Funding", "Capitalization", "What type of funding does the company have (debt/equity/public)? Total raised, most recent round and date, key investors."),
]

ALL_METRICS = OVERVIEW + COMPANY_ANALYSIS
METRIC_BY_KEY = {m.key: m for m in ALL_METRICS}

PRICING = [
    Metric("pricing_tiers", "Pricing", "Pricing Tiers", "Which plans/tiers exist (e.g. Standard, Premium, Enterprise) and what distinguishes them?"),
    Metric("recurring_fees", "Pricing", "Standard recurring fees", "Published prices per tier, or 'Request quote'."),
    Metric("trial", "Pricing", "Trial Period", "Is there a free trial or free plan, and how long?"),
]

SWOT_KEYS = ["strengths", "weaknesses", "opportunities", "threats"]
SWOT_QUESTIONS = {
    "strengths": "What are the key competitive advantages where the company excels?",
    "weaknesses": "What operational, strategic and product/service areas can be improved?",
    "opportunities": "Which avenues can the company explore to increase market share? New products? Geographic expansion? Strategic partnerships?",
    "threats": "What are the challenges and risks?",
}

# Feature Comparison sheet: tier columns + terminology
TIERS = ["standard", "premium", "enterprise"]
TIER_TERMINOLOGY = {
    "standard": "Basic plan with core features",
    "premium": "Basic plan + advanced features",
    "enterprise": "Full suite, unlimited access + support",
}
