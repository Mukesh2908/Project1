"""The 9-sheet report — project.md section 16.

Every value comes from the same facts dictionary the UI renders, so the report
and the screen cannot disagree. Verdicts carry a symbol and a label as well as
a fill, so they survive a greyscale print and a colourblind reader.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import xlsxwriter

from app.schemas.enums import DIMENSION_LABELS, DIMENSIONS, VERDICT_LABELS, VERDICT_STYLE
from app.schemas.jd import JDConfig
from app.schemas.result import WeightConfig
from app.services.matching_engine import RunResult

APP_VERSION = "0.1.0"


def build_report(
    run: RunResult,
    jd: JDConfig,
    weights: WeightConfig,
    path: Path | str,
    use_real_names: bool = True,
    include_quotes: bool = True,
    models: dict[str, str] | None = None,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    book = xlsxwriter.Workbook(str(path), {"constant_memory": False})
    fmt = _formats(book)

    _summary(book, fmt, run, jd, weights)
    _comparison(book, fmt, run, use_real_names)
    _breakdown(book, fmt, run, weights)
    _skill_matrix(book, fmt, run, jd)
    _evidence(book, fmt, run, include_quotes)
    _gaps(book, fmt, run)
    _review(book, fmt, run)
    _config(book, fmt, jd, weights)
    _audit(book, fmt, run, jd, models or {})

    book.close()
    return path


def _formats(book: xlsxwriter.Workbook) -> dict:
    base = {"font_name": "Calibri", "font_size": 11}
    formats = {
        "title": book.add_format({**base, "bold": True, "font_size": 15}),
        "header": book.add_format(
            {
                **base,
                "bold": True,
                "bg_color": "#F2F0EA",
                "border": 1,
                "text_wrap": True,
                "valign": "vcenter",
            }
        ),
        "cell": book.add_format({**base, "valign": "top"}),
        "wrap": book.add_format({**base, "text_wrap": True, "valign": "top"}),
        "pct": book.add_format({**base, "num_format": "0.0\\%"}),
        "num": book.add_format({**base, "num_format": "0.00"}),
        "bold": book.add_format({**base, "bold": True}),
        "note": book.add_format(
            {**base, "italic": True, "font_color": "#666666", "text_wrap": True}
        ),
    }
    for verdict, style in VERDICT_STYLE.items():
        formats[f"verdict_{verdict}"] = book.add_format(
            {**base, "bg_color": style["colour"], "font_color": style["text"], "bold": True}
        )
    return formats


def _verdict_cell(verdict: str) -> str:
    style = VERDICT_STYLE.get(verdict, {})
    return f"{style.get('symbol', '')} {VERDICT_LABELS.get(verdict, verdict)}".strip()


def _write_header(sheet, fmt, headers: list[str], widths: list[int] | None = None) -> None:
    for column, title in enumerate(headers):
        sheet.write(0, column, title, fmt["header"])
    sheet.freeze_panes(1, 0)
    if headers:
        sheet.autofilter(0, 0, 0, len(headers) - 1)
    for column, width in enumerate(widths or []):
        sheet.set_column(column, column, width)
    sheet.set_landscape()
    sheet.fit_to_pages(1, 0)
    sheet.repeat_rows(0)


def _summary(book, fmt, run: RunResult, jd: JDConfig, weights: WeightConfig) -> None:
    sheet = book.add_worksheet("Summary")
    sheet.set_column(0, 0, 26)
    sheet.set_column(1, 1, 70)
    sheet.write(0, 0, "Profile Match Engine", fmt["title"])

    rows = [
        ("JD title", jd.job_title),
        ("Role intent", jd.role_intent),
        ("Primary skill", ", ".join(p.skill for p in jd.primaries) or "—"),
        ("Dual primary mode", jd.dual_primary_mode),
        ("JD confidence", f"{jd.confidence}% ({jd.confidence_band})"),
        ("Run date", datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("Profiles scored", run.scored_count),
        ("Excluded by stage 1", len(run.excluded)),
        ("Needs human review", len(run.review_queue)),
    ]
    for index, (label, value) in enumerate(rows, start=2):
        sheet.write(index, 0, label, fmt["bold"])
        sheet.write(index, 1, value, fmt["wrap"])

    row = len(rows) + 3
    sheet.write(row, 0, "Scoring matrix", fmt["bold"])
    row += 1
    for dimension in DIMENSIONS:
        weight = weights.weight_of(dimension)
        if not weight:
            continue
        sheet.write(row, 0, DIMENSION_LABELS[dimension], fmt["cell"])
        sheet.write(
            row, 1, f"{weight}%  —  {jd.derived_weight_reasons.get(dimension, '')}", fmt["wrap"]
        )
        row += 1

    row += 1
    sheet.write(row, 0, "Verdicts", fmt["bold"])
    row += 1
    for verdict in VERDICT_LABELS:
        sheet.write(row, 0, _verdict_cell(verdict), fmt[f"verdict_{verdict}"])
        sheet.write(row, 1, len(run.by_verdict(verdict)), fmt["cell"])
        row += 1

    row += 1
    sheet.write(row, 0, "Top 5", fmt["bold"])
    row += 1
    for result in run.results[:5]:
        sheet.write(row, 0, result.display_name, fmt["cell"])
        sheet.write(
            row, 1, f"{result.match_score:.1f}%  {_verdict_cell(result.verdict)}", fmt["cell"]
        )
        row += 1

    if run.results:
        chart = book.add_chart({"type": "bar"})
        top = run.results[:10]
        start = row + 2
        for index, result in enumerate(top):
            sheet.write(start + index, 0, result.display_name)
            sheet.write(start + index, 1, result.match_score)
        chart.add_series(
            {
                "name": "Match score",
                "categories": ["Summary", start, 0, start + len(top) - 1, 0],
                "values": ["Summary", start, 1, start + len(top) - 1, 1],
                "fill": {"color": "#5BA88E"},
            }
        )
        chart.set_title({"name": "Top candidates"})
        chart.set_legend({"none": True})
        sheet.insert_chart(2, 3, chart, {"x_scale": 1.2, "y_scale": 1.4})


def _comparison(book, fmt, run: RunResult, use_real_names: bool) -> None:
    sheet = book.add_worksheet("Comparison")
    headers = [
        "Candidate",
        "Match Score",
        "Verdict",
        "Confidence",
        "Primary evidence",
        "Candidate Primary",
        "Primary Score",
        "Core",
        "Projects",
        "Experience",
        "Certification",
        "Domain",
        "Main Strength",
        "Main Gap",
        "Flags",
    ]
    _write_header(sheet, fmt, headers, [16, 12, 18, 12, 16, 18, 13, 10, 10, 12, 12, 10, 30, 36, 30])

    for index, result in enumerate(run.results, start=1):
        facts = result.facts
        name = result.display_name if use_real_names else result.profile_id
        strength = result.explanation.strengths[0] if result.explanation.strengths else "—"
        gap = (
            result.explanation.why_not_higher[0]["dimension"]
            if result.explanation.why_not_higher
            else "—"
        )
        sheet.write(index, 0, name, fmt["cell"])
        sheet.write(index, 1, result.match_score, fmt["num"])
        sheet.write(index, 2, _verdict_cell(result.verdict), fmt[f"verdict_{result.verdict}"])
        sheet.write(
            index, 3, f"{result.analysis_confidence}% ({result.confidence_band})", fmt["cell"]
        )
        sheet.write(index, 4, "yes" if result.prefilter_passed else "none", fmt["cell"])
        sheet.write(index, 5, facts.get("candidate_primary") or "—", fmt["cell"])
        for column, dimension in enumerate(
            [
                "primary_skill",
                "core_skills",
                "project_experience",
                "relevant_experience",
                "certification",
                "domain_fit",
            ],
            start=6,
        ):
            score = result.dimension_scores.get(dimension)
            sheet.write(
                index,
                column,
                "N/A" if score is None else round(score, 1),
                fmt["cell"] if score is None else fmt["num"],
            )
        sheet.write(index, 12, strength, fmt["wrap"])
        sheet.write(index, 13, gap, fmt["wrap"])
        sheet.write(index, 14, "; ".join(result.review_flags[:2]), fmt["wrap"])
        sheet.write_url(index, 0, "internal:Evidence!A1", string=name)

    if run.results:
        sheet.conditional_format(
            1, 1, len(run.results), 1, {"type": "data_bar", "bar_color": "#5BA88E"}
        )
        sheet.conditional_format(1, 6, len(run.results), 11, {"type": "3_color_scale"})


def _breakdown(book, fmt, run: RunResult, weights: WeightConfig) -> None:
    sheet = book.add_worksheet("Score Breakdown")
    _write_header(
        sheet,
        fmt,
        ["Candidate", "Dimension", "Weight %", "Score %", "Contribution", "Note"],
        [16, 22, 10, 10, 13, 40],
    )
    row = 1
    for result in run.results:
        for dimension in DIMENSIONS:
            score = result.dimension_scores.get(dimension)
            weight = weights.weight_of(dimension)
            if weight == 0 and score is None:
                continue
            note = ""
            if score is None and weight:
                note = "N/A for this JD — weight redistributed across the rest"
            entry = next((d for d in result.facts["dimensions"] if d["name"] == dimension), None)
            sheet.write(row, 0, result.display_name, fmt["cell"])
            sheet.write(row, 1, DIMENSION_LABELS[dimension], fmt["cell"])
            sheet.write(row, 2, round(entry["weight"], 1) if entry else weight, fmt["num"])
            sheet.write(
                row,
                3,
                "N/A" if score is None else round(score, 1),
                fmt["cell"] if score is None else fmt["num"],
            )
            sheet.write(row, 4, result.dimension_contributions.get(dimension, 0), fmt["num"])
            sheet.write(row, 5, note, fmt["note"])
            row += 1


def _skill_matrix(book, fmt, run: RunResult, jd: JDConfig) -> None:
    sheet = book.add_worksheet("Skill Matrix")
    skills = [r for r in jd.requirements if r.category == "skill"]
    order = {"primary": 0, "core": 1, "secondary": 2}
    skills.sort(key=lambda r: (order.get(r.tier or "secondary", 3), -(r.focus_score or 0)))

    sheet.write(0, 0, "Candidate", fmt["header"])
    for column, requirement in enumerate(skills, start=1):
        label = f"{requirement.skill}\n({requirement.tier})"
        if not requirement.scored:
            label += "\nnot scored"
        sheet.write(0, column, label, fmt["header"])
    sheet.set_column(0, 0, 18)
    sheet.set_column(1, len(skills), 13)
    sheet.freeze_panes(1, 1)

    for index, result in enumerate(run.results, start=1):
        sheet.write(index, 0, result.display_name, fmt["cell"])
        by_skill = {f.skill: f for f in result.skill_fits}
        for column, requirement in enumerate(skills, start=1):
            fit = by_skill.get(requirement.skill)
            sheet.write(index, column, fit.fit_pct if fit else 0, fmt["num"])
    if run.results and skills:
        sheet.conditional_format(1, 1, len(run.results), len(skills), {"type": "3_color_scale"})


def _evidence(book, fmt, run: RunResult, include_quotes: bool) -> None:
    sheet = book.add_worksheet("Evidence")
    headers = [
        "Candidate",
        "Skill",
        "Tier",
        "Scored",
        "Needed",
        "Found",
        "Projects",
        "Last used",
        "Production",
        "Ownership",
        "Match",
        "Fit %",
        "Source",
    ]
    if include_quotes:
        headers.append("Evidence quotes")
    _write_header(sheet, fmt, headers, [16, 14, 11, 9, 13, 18, 9, 14, 11, 11, 11, 9, 10, 60])

    row = 1
    for result in run.results:
        for skill in result.facts["skills"]:
            fit = next((f for f in result.skill_fits if f.skill == skill["skill"]), None)
            values = [
                result.display_name,
                skill["skill"],
                skill["tier"] or "—",
                "yes" if skill["scored"] else "no",
                skill["needs"],
                skill["found"],
                skill["projects"],
                skill["last_used"],
                "yes" if fit and fit.production else "unknown",
                fit.ownership if fit else "—",
                skill["relation"],
                skill["fit"],
                "Verified" if fit and any("Verified" in e for e in fit.evidence) else "Parsed",
            ]
            if include_quotes:
                values.append(" · ".join(skill["evidence"]))
            for column, value in enumerate(values):
                sheet.write(row, column, value, fmt["wrap"] if column >= 12 else fmt["cell"])
            row += 1


def _gaps(book, fmt, run: RunResult) -> None:
    sheet = book.add_worksheet("Gaps & Paths")
    _write_header(sheet, fmt, ["Candidate", "Type", "Detail", "Points lost"], [16, 22, 80, 12])
    row = 1
    for result in run.results:
        for entry in result.explanation.why_not_higher:
            sheet.write(row, 0, result.display_name, fmt["cell"])
            sheet.write(row, 1, f"Why not higher — {entry['dimension']}", fmt["cell"])
            sheet.write(row, 2, entry["detail"], fmt["wrap"])
            sheet.write(row, 3, entry["lost"], fmt["num"])
            row += 1
        for step in result.explanation.path_to_deployable:
            sheet.write(row, 0, result.display_name, fmt["cell"])
            sheet.write(row, 1, "Path to deployable", fmt["cell"])
            sheet.write(row, 2, step, fmt["wrap"])
            row += 1
        for item in result.explanation.requires_verification:
            sheet.write(row, 0, result.display_name, fmt["cell"])
            sheet.write(row, 1, "Requires verification", fmt["cell"])
            sheet.write(row, 2, item, fmt["wrap"])
            row += 1


def _review(book, fmt, run: RunResult) -> None:
    sheet = book.add_worksheet("Human Review")
    _write_header(
        sheet,
        fmt,
        ["Candidate", "Verdict", "Confidence", "Trigger", "Manager action", "Note"],
        [16, 18, 12, 60, 16, 30],
    )
    row = 1
    for result in run.review_queue:
        for flag in result.review_flags:
            sheet.write(row, 0, result.display_name, fmt["cell"])
            sheet.write(row, 1, _verdict_cell(result.verdict), fmt[f"verdict_{result.verdict}"])
            sheet.write(row, 2, result.analysis_confidence, fmt["cell"])
            sheet.write(row, 3, flag, fmt["wrap"])
            sheet.write(row, 4, "", fmt["cell"])
            sheet.write(row, 5, "", fmt["cell"])
            row += 1
    if row == 1:
        sheet.write(1, 0, "No candidates flagged for review in this run.", fmt["note"])


def _config(book, fmt, jd: JDConfig, weights: WeightConfig) -> None:
    sheet = book.add_worksheet("JD & Config")
    _write_header(
        sheet,
        fmt,
        ["Item", "Tier", "Importance", "Needs", "Scored", "Source", "Why / note"],
        [26, 12, 12, 14, 9, 12, 50],
    )
    row = 1
    for requirement in jd.requirements:
        sheet.write(row, 0, requirement.skill, fmt["cell"])
        sheet.write(row, 1, requirement.tier or requirement.category, fmt["cell"])
        sheet.write(row, 2, requirement.importance, fmt["cell"])
        sheet.write(
            row, 3, f"L{requirement.required_depth}·{requirement.required_years:g}y", fmt["cell"]
        )
        sheet.write(row, 4, "yes" if requirement.scored else "no (beyond tier cap)", fmt["cell"])
        sheet.write(row, 5, requirement.source, fmt["cell"])
        sheet.write(row, 6, requirement.why or requirement.notes or "", fmt["wrap"])
        row += 1

    row += 1
    sheet.write(row, 0, "Conflicts", fmt["bold"])
    row += 1
    for conflict in jd.conflicts:
        sheet.write(row, 0, conflict.kind, fmt["cell"])
        sheet.write(row, 1, "resolved" if conflict.resolved else "open", fmt["cell"])
        sheet.write(row, 2, conflict.message, fmt["wrap"])
        row += 1

    row += 1
    sheet.write(row, 0, "Weights (derived → final)", fmt["bold"])
    row += 1
    for dimension in DIMENSIONS:
        derived = jd.derived_weights.get(dimension, 0)
        final = weights.weight_of(dimension)
        sheet.write(row, 0, DIMENSION_LABELS[dimension], fmt["cell"])
        sheet.write(row, 1, derived, fmt["cell"])
        sheet.write(row, 2, final, fmt["cell"])
        sheet.write(row, 3, "edited" if derived != final else "as derived", fmt["cell"])
        sheet.write(row, 6, jd.derived_weight_reasons.get(dimension, ""), fmt["wrap"])
        row += 1

    row += 1
    sheet.write(row, 0, "Advanced settings", fmt["bold"])
    row += 1
    for label, value in [
        ("Gate threshold", weights.gate_threshold),
        ("Deployable threshold", weights.deployable_threshold),
        ("Trainable threshold", weights.trainable_threshold),
        ("Listed-only cap", weights.listed_only_cap),
        ("Tier skill cap", weights.tier_skill_cap),
        ("Borderline band", weights.borderline_band),
        ("Dual primary mode", jd.dual_primary_mode),
    ]:
        sheet.write(row, 0, label, fmt["cell"])
        sheet.write(row, 1, value, fmt["cell"])
        row += 1


def _audit(book, fmt, run: RunResult, jd: JDConfig, models: dict[str, str]) -> None:
    sheet = book.add_worksheet("Audit")
    sheet.set_column(0, 0, 26)
    sheet.set_column(1, 1, 60)
    first = run.results[0] if run.results else None
    rows = [
        ("Run ID", run.run_id),
        ("JD ID", jd.jd_id),
        ("JD config version", jd.version),
        ("Weights hash", first.weights_hash if first else "—"),
        ("Taxonomy version", first.taxonomy_version if first else "—"),
        ("Equivalence version", first.equivalence_version if first else "—"),
        ("App version", APP_VERSION),
        ("Generated", datetime.now().isoformat(timespec="seconds")),
    ]
    for agent, model in models.items():
        rows.append((f"Model — {agent}", model))
    for index, (label, value) in enumerate(rows):
        sheet.write(index, 0, label, fmt["bold"])
        sheet.write(index, 1, str(value), fmt["cell"])
    sheet.write(
        len(rows) + 1,
        0,
        "Taxonomy and equivalence versions are recorded so a later YAML edit "
        "cannot silently change what this run meant.",
        fmt["note"],
    )
