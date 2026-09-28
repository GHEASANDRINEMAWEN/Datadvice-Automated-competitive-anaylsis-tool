"""Datadvise Feature Scoring Guide (0–5), verbatim from the Competitive Analysis template."""

SCORING_GUIDE = {
    0: ("Absent", {
        "Presence": "The feature is not present in the competitor's product.",
        "Quality": "Not applicable, as the feature does not exist.",
        "Maturity": "Not applicable, as the feature does not exist.",
    }),
    1: ("Basic", {
        "Presence": "The feature exists but is in its most basic form or initial stage of development.",
        "Quality": "The implementation is minimal, potentially buggy, or not user-friendly, indicating a low level of investment or sophistication.",
        "Maturity": "The feature shows a lack of evolution or refinement, suggesting it is either newly introduced or not a priority for development.",
    }),
    2: ("Developing", {
        "Presence": "The feature is present and has received some development effort beyond the basics.",
        "Quality": "The feature works with moderate effectiveness but may lack polish, depth, or full integration into the overall product.",
        "Maturity": "The feature has seen some updates or improvements but is still evolving and not yet considered mature or fully reliable.",
    }),
    3: ("Competent", {
        "Presence": "The feature is well-established within the product offering.",
        "Quality": "The implementation is solid, offering a good user experience and meeting users' needs effectively. Minor issues may exist, but they do not significantly detract from the overall utility.",
        "Maturity": "The feature demonstrates a good level of development, having been refined through updates and feedback, though it may still have room for enhancement.",
    }),
    4: ("Advanced", {
        "Presence": "The feature is fully present and may offer more functionality than basic industry standards.",
        "Quality": "High-quality implementation, with attention to detail, user experience, and reliability. The feature integrates well with the rest of the product and enhances its overall value.",
        "Maturity": "The feature is mature, having been through several rounds of refinement and optimization. It is stable, with ongoing support indicating a commitment to excellence.",
    }),
    5: ("Leading", {
        "Presence": "The feature sets the standard in the industry, possibly offering unique capabilities not found in competing products.",
        "Quality": "Exceptional quality, with superior design, usability, and performance. The feature significantly exceeds user expectations and contributes to a competitive advantage.",
        "Maturity": "Highly mature, with a history of continuous improvement. The feature is recognized as a market leader, reflecting the company's innovation and leadership in that area.",
    }),
}

APPLICATION_RULES = [
    "Comprehensive Research: Gather detailed information on each competitor's features through product trials, demos, user feedback, and market reports.",
    "Objective Scoring: Apply the scoring criteria objectively, avoiding bias towards your own product.",
    "Contextual Analysis: A high score in one dimension (e.g., quality) may compensate for a lower score in another (e.g., presence), depending on the feature's strategic importance.",
]


def label(score: float | None) -> str:
    if score is None:
        return "?"
    return SCORING_GUIDE[int(round(score))][0]


def guide_text() -> str:
    lines = ["DATADVISE FEATURE SCORING GUIDE (0-5)"]
    for s, (name, dims) in SCORING_GUIDE.items():
        lines.append(f"{s} - {name}")
        lines += [f"   {k}: {v}" for k, v in dims.items()]
    lines.append("Application of the scale:")
    lines += [f" - {r}" for r in APPLICATION_RULES]
    return "\n".join(lines)
