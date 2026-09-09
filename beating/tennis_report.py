"""Render the complete frozen N2/N3 metrics without selecting new strategies."""
import argparse
import json
from pathlib import Path


def number(value, places=6):
    return "unavailable" if value is None else f"{value:.{places}f}"


def bounds(value):
    if value is None or any(x is None for x in value):
        return "unavailable"
    return "[" + ", ".join(number(x) for x in value) + "]"


def annual_status(record):
    """Describe the registered years, including empty or wholly ungraded folds.

    This is reporting scope, not an additional statistical selection gate.
    """
    lines, complete = [], True
    folds = record.get("fit", {}).get("annual_models", {})
    nodes = list(record.get("models", {}).values())
    for year in ("2024", "2025"):
        fold = folds.get(year, {})
        status = fold.get("status", "not_evaluated")
        annual = [node.get("by_year", {}).get(year, {}) for node in nodes]
        events = annual[0].get("events", 0) if annual else 0
        graded = annual[0].get("settled_events", 0) if annual else 0
        unavailable = len(fold.get("model_unavailable_event_ids", []))
        evaluable = (status == "fitted" and bool(annual)
                     and all(node.get("events", 0) > 0 and node.get("settled_events", 0) > 0
                             for node in annual))
        complete &= evaluable
        lines.append(f"- **{year}:** `{status}`; forecasts / graded: {events} / {graded}; "
                     f"quotes unavailable at model selection: {unavailable}; "
                     f"graded comparison available: {'yes' if evaluable else 'no'}.")
    if not complete:
        lines += ["", "The declared 2024–2025 evaluation is incomplete. A screen on the available forecasts "
                  "cannot be described as a successful two-year evaluation. This scope statement does not change the statistical gates."]
    return lines


def render(records):
    if [r["experiment"] for r in records] != ["N2", "N3"]:
        raise ValueError("Report requires both N2 and N3 in protocol order")
    screened = [(r["experiment"], name) for r in records
                for name, node in r.get("models", {}).items()
                if name != "market" and node.get("favorable_evidence_unblocked")]
    if all(r["status"] == "insufficient_evaluable_data" for r in records):
        opening = "Neither experiment had enough evaluable data for a fitted historical holdout comparison."
    elif screened:
        opening = ("At least one candidate passed the recorded historical research screen on its available forecasts. "
                   "Declared annual coverage is reported below; this does not establish an executable FanDuel edge.")
    else:
        opening = "No candidate demonstrated an unblocked historical edge under the recorded research screen."
    lines = ["# Frozen ATP Challenger total-games research", "", opening,
             "No prospective FanDuel qualification, betting notification or wager is enabled.", "",
             "Both experiments concern standard best-of-three men's Challenger matches at exactly 21.5 total games. "
             "N2 infers serving rates from prior tiebreak history and synchronized opening moneyline prices; "
             "N3 replaces that moneyline input with prior set Elo. Entries and closes are historical Pinnacle prices. "
             "All candidate and annual results below are retained; validation chooses the research candidate before holdout evaluation.", "",
             "[N2 protocol](../docs/protocol-tennis-v1.md), [N3 protocol](../docs/protocol-tennis-independent-v1.md), "
             "[pre-result implementation review](../docs/tennis-implementation-review.md).", ""]
    for record in records:
        name = record["experiment"]
        acquisition = record["acquisition"]
        audit = record["feature_audit"]["counts"]
        lines += [f"## {name}", "",
                  f"Required daily pages: {acquisition['daily_dates_required']}; "
                  f"frozen unique sampled events: {acquisition['sampled_unique_events']}; "
                  f"parsed details: {acquisition['parsed_details']}; "
                  f"entry-feature-valid events: {audit.get('feature_accepted', 0)}.", ""]
        blocks = record["source_evidence_blocks"]
        lines += ["Source evidence blocks: " + (", ".join(blocks) if blocks else "none recorded") + ".", ""]
        lines += ["Declared holdout-year status:", "", *annual_status(record), ""]
        if record["status"] == "insufficient_evaluable_data":
            lines += [f"**Insufficient evaluable data:** {record['reason']}. No fitted holdout comparison is available.", "",
                      f"[Full source and feature audit](tennis-{name.lower()}-metrics.json).", ""]
            continue
        fit = record["fit"]
        lines += [f"Validation-selected research candidate: **{fit['selected_research_candidate']}**. "
                  f"Validation selection was available at {fit['selection_available_at']}. "
                  "The final post-holdout refits are separate from the annual models that generated these forecasts.", "",
                  "| Candidate | Forecasts / graded | Bets / graded | Model log loss | Paired loss delta | Haircut ROI | Closing EV |",
                  "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for candidate, node in record["models"].items():
            lines.append(f"| {candidate} | {node['events']} / {node['settled_events']} | "
                         f"{node['bets']} / {node['settled_bets']} | {number(node['log_loss'])} | "
                         f"{number(node['paired_log_loss_delta'])} | {number(node['haircut_roi'])} | "
                         f"{number(node['closing_pinnacle']['mean_closing_ev'])} |")
        confidence = next(iter(record["models"].values()))["confidence"]
        lines += ["", f"Corrected intervals use {confidence:.8%} confidence and calendar-week resampling. "
                  "A negative paired loss delta favors the model. ROI is unavailable when there are no bets or unresolved selected outcomes. "
                  "Closing EV uses only covered selected bets; its missing coverage can block the research screen.", "",
                  "| Candidate | Paired loss interval | Haircut ROI interval | Closing EV interval | Selected closes | Historical screen unblocked |",
                  "| --- | --- | --- | --- | ---: | --- |"]
        for candidate, node in record["models"].items():
            close = node["closing_pinnacle"]
            lines.append(f"| {candidate} | {bounds(node.get('paired_log_loss_delta_ci'))} | "
                         f"{bounds(node.get('haircut_roi_ci'))} | {bounds(close.get('mean_closing_ev_ci'))} | "
                         f"{close['covered_bets']} / {node['bets']} | {node['favorable_evidence_unblocked']} |")
        lines += ["", "Selected turnover includes unresolved outcomes. The bounds below assign every unresolved selected bet "
                  "a loss or a win; they are outcome bounds, not confidence intervals. The complete-match simulation "
                  "uses its smaller settled denominator.", "",
                  "| Candidate | Turnover units | Ungraded bets | Haircut ROI worst / best | Complete-match bets | Complete-match haircut ROI |",
                  "| --- | ---: | ---: | --- | ---: | ---: |"]
        for candidate, node in record["models"].items():
            completed = node["complete_match_simulation"]
            lines.append(f"| {candidate} | {node['turnover_units']} | {node['unsettled_bets']} | "
                         f"{bounds(node['haircut_roi_unresolved_outcome_bounds'])} | {completed['bets']} | "
                         f"{number(completed['haircut_roi'])} |")
        lines += ["", "### Annual holdout results", "",
                  "| Year | Candidate | Forecasts / graded | Bets / graded | Paired loss delta | Haircut ROI | Closing EV |",
                  "| --- | --- | ---: | ---: | ---: | ---: | ---: |"]
        for candidate, node in record["models"].items():
            for year, annual in node["by_year"].items():
                lines.append(f"| {year} | {candidate} | {annual['events']} / {annual['settled_events']} | "
                             f"{annual['bets']} / {annual['settled_bets']} | {number(annual['paired_log_loss_delta'])} | "
                             f"{number(annual['haircut_roi'])} | {number(annual['closing_pinnacle']['mean_closing_ev'])} |")
        unavailable = sum(len(fold.get("model_unavailable_event_ids", [])) for fold in fit["annual_models"].values())
        lines += ["", f"Quotes preceding completed validation selection: {unavailable}; "
                  "these remain explicitly model-unavailable in the fit audit. "
                  "Ungraded selected exposure stays in turnover, with worst/best outcome bounds in the metrics. "
                  "The complete-match-only sensitivity excludes that exposure and is labeled separately.", ""]
        slug = name.lower()
        lines += [f"[Full metrics](tennis-{slug}-metrics.json), [fit and validation trials](tennis-{slug}-fit.json), "
                  f"[annual forecasts](tennis-{slug}-forecasts.csv).", ""]
    lines += ["## Evidence limits", "",
              "Historical source timestamps and final-price labels do not prove that an offer was executable, "
              "nor that a present-day FanDuel market uses the same retirement rules. Retirements and unclear scores "
              "remain ungraded instead of being assigned convenient outcomes. Complete acquisition attempts do not "
              "guarantee complete underlying history. See the individual source failures, identities, timestamp checks "
              "and content hashes in the metrics.", "",
              "Any promising historical candidate still requires a frozen prospective FanDuel cohort with verified "
              "entry and closing quotes, immutable predictions, and the unchanged ROI, closing-EV and log-loss promotion gates. "
              "These results cannot authorize a betting alert.", ""]
    return "\n".join(lines)


def write_report(output):
    output = Path(output)
    records = [json.loads((output/f"tennis-{name}-metrics.json").read_text()) for name in ("n2", "n3")]
    path = output/"tennis-research-report.md"
    path.write_text(render(records))
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("reports"))
    print(write_report(parser.parse_args().output))
