#!/usr/bin/env python3
"""Post-processing utilities for FIVES counterflow diffusion flame campaigns.

The main entry point is ``load_campaign_step``.  It reads one campaign folder
such as ``examples/CH4/a_25``, filters the cases marked as successful in
``CampaignStatus.csv``, and loads the selected ``StepXX/Output/Solution.final.out``
files into pandas data frames.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence


SOLUTION_FILE_NAME = "Solution.final.out"
SOOT_FILE_NAME = "Solution.soot.out"
HEADER_PATTERN = re.compile(r"^(?P<name>.+?)(?:\[(?P<unit>.*?)\])?\((?P<number>\d+)\)$")
CASE_PATTERN = re.compile(
    r"^Alpha_(?P<alpha>[-+0-9.eE]+)_Beta_(?P<beta>[-+0-9.eE]+)_Gamma_(?P<gamma>[-+0-9.eE]+)$"
)


@dataclass
class CaseFailure:
    """Diagnostic record for one case-level loading or metric problem."""

    case: str
    source: str
    reason: str
    file: Optional[Path] = None
    detail: str = ""


@dataclass
class CampaignStepData:
    """Container returned by ``load_campaign_step``.

    Attributes:
        root: Campaign directory containing ``CampaignStatus.csv``.
        step: Normalized step folder name, for example ``Step07``.
        campaign_status: Complete campaign status table from ``CampaignStatus.csv``.
        cases: One row per successfully completed case considered for loading.
        columns: Metadata for the columns in ``Solution.final.out``.
        profiles: Mapping from case folder name to its pandas DataFrame.
        combined_profiles: Optional single DataFrame with all profiles stacked.
        missing_files: Successful cases whose ``Solution.final.out`` was missing.
        soot_columns: Metadata for optional ``Solution.soot.out`` columns.
        soot_profiles: Mapping from case folder name to optional soot DataFrames.
        missing_soot_files: Successful cases whose optional soot file was missing.
        load_failures: Successful cases whose result files were missing,
            incomplete, empty, or unreadable.
        temperature_failures: Cases explicitly marked as low-temperature failures
            in ``CampaignStatus.csv``.
        metric_failures: Cases skipped during metric extraction because the
            loaded profile did not contain the needed coordinate or variables.
    """

    root: Path
    step: str
    campaign_status: Any
    cases: Any
    columns: Any
    profiles: dict[str, Any]
    combined_profiles: Optional[Any]
    missing_files: list[Path]
    soot_columns: Any = None
    soot_profiles: Optional[dict[str, Any]] = None
    missing_soot_files: Optional[list[Path]] = None
    load_failures: Optional[list[CaseFailure]] = None
    temperature_failures: Optional[list[str]] = None
    metric_failures: Optional[list[CaseFailure]] = None


def _require_pandas() -> Any:
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError(
            "pandas is required for FIVES post-processing. Install it in your "
            "Python environment, for example with: python3 -m pip install pandas"
        ) from exc
    return pd


def _require_matplotlib() -> tuple[Any, Any]:
    """Import matplotlib and numpy only when plotting is requested."""

    cache_root = Path(tempfile.gettempdir()) / "fives_plot_cache"
    matplotlib_cache = cache_root / "matplotlib"
    xdg_cache = cache_root / "xdg"
    fontconfig_cache = xdg_cache / "fontconfig"
    for directory in (matplotlib_cache, fontconfig_cache):
        directory.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("MPLCONFIGDIR", str(matplotlib_cache))
    os.environ.setdefault("XDG_CACHE_HOME", str(xdg_cache))

    try:
        import matplotlib

        matplotlib.use(os.environ.get("MPLBACKEND", "Agg"), force=True)

        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "matplotlib and numpy are required for FIVES plotting. Install them "
            "with: python3 -m pip install matplotlib numpy"
        ) from exc

    return plt, np


def normalize_step(step: str | int) -> str:
    """Normalize ``7``, ``"7"``, ``"Step7"``, and ``"Step07"`` to ``"Step07"``."""

    if isinstance(step, int):
        if step < 0:
            raise ValueError("Step number must be non-negative.")
        return f"Step{step:02d}"

    text = str(step).strip()
    match = re.fullmatch(r"(?:[Ss]tep)?0*(\d+)", text)
    if match:
        return f"Step{int(match.group(1)):02d}"

    if re.fullmatch(r"[Ss]tep\d+", text):
        return f"Step{int(text[4:]):02d}"

    return text


def parse_case_parameters(case_name: str) -> dict[str, float]:
    """Extract alpha, beta, and gamma from an ``Alpha_X_Beta_Y_Gamma_Z`` name."""

    match = CASE_PATTERN.fullmatch(case_name)
    if not match:
        return {"alpha": float("nan"), "beta": float("nan"), "gamma": float("nan")}

    return {key: float(value) for key, value in match.groupdict().items()}


def parse_solution_header(solution_file: str | Path) -> list[dict[str, Any]]:
    """Parse the first line of ``Solution.final.out``.

    Returns one dictionary per column with the original tag, clean variable name,
    unit string, 1-based column number, and a unique pandas column label.
    """

    path = Path(solution_file)
    with path.open("r", encoding="utf-8") as handle:
        tokens = handle.readline().split()

    if not tokens:
        raise ValueError(f"No header found in result file: {path}")

    columns: list[dict[str, Any]] = []
    used_labels: set[str] = set()

    for position, token in enumerate(tokens, start=1):
        match = HEADER_PATTERN.fullmatch(token)
        if not match:
            name = token
            unit = ""
            number = position
        else:
            name = match.group("name")
            unit = match.group("unit") or ""
            number = int(match.group("number"))

        label = name
        if label in used_labels:
            label = f"{name}__{number}"
        used_labels.add(label)

        columns.append(
            {
                "column": number,
                "position": position,
                "tag": token,
                "name": name,
                "unit": unit,
                "label": label,
            }
        )

    return columns


def _column_metadata_frame(columns: list[dict[str, Any]]) -> Any:
    pd = _require_pandas()
    return pd.DataFrame(columns)


def _resolve_requested_columns(
    columns: list[dict[str, Any]],
    requested: Optional[Sequence[str | int]],
) -> Optional[list[str]]:
    if requested is None:
        return None

    by_label: dict[str, str] = {}
    by_name: dict[str, str] = {}
    by_tag: dict[str, str] = {}
    by_number: dict[str, str] = {}
    for item in columns:
        label = item["label"]
        by_label.setdefault(label, label)
        by_name.setdefault(item["name"], label)
        by_tag.setdefault(item["tag"], label)
        by_number.setdefault(str(item["column"]), label)

    resolved: list[str] = []
    unknown: list[str] = []

    for item in requested:
        key = str(item)
        label = by_label.get(key) or by_name.get(key) or by_tag.get(key) or by_number.get(key)
        if label is None:
            unknown.append(key)
        elif label not in resolved:
            resolved.append(label)

    if unknown:
        raise KeyError("Unknown Solution.final.out column(s): " + ", ".join(unknown))

    return resolved


def read_solution_file(
    solution_file: str | Path,
    columns: Optional[Sequence[str | int]] = None,
) -> tuple[Any, Any]:
    """Read a single ``Solution.final.out`` file.

    Args:
        solution_file: Path to the result file.
        columns: Optional selected columns. Each entry may be a clean name
            (``"T"``), original tag (``"T[K](3)"``), generated DataFrame label,
            or 1-based column number.

    Returns:
        ``(profile, column_metadata)`` where both elements are pandas DataFrames.
    """

    pd = _require_pandas()
    path = Path(solution_file)
    if not path.is_file():
        raise FileNotFoundError(f"Result file not found: {path}")
    if path.stat().st_size == 0:
        raise ValueError(f"Result file is empty: {path}")

    parsed_columns = parse_solution_header(path)
    names = [item["label"] for item in parsed_columns]
    usecols = _resolve_requested_columns(parsed_columns, columns)

    profile = pd.read_csv(
        path,
        sep=r"\s+",
        skiprows=1,
        names=names,
        usecols=usecols,
        engine="c",
    )

    if profile.empty:
        raise ValueError(f"Result file contains no profile rows: {path}")

    # OpenSMOKE++ profiles are numeric tables.  Force numeric dtype here so a
    # single nonstandard token, or a Fortran-style D exponent, cannot silently
    # turn a requested column into object data and later produce NaN metrics.
    for column in profile.columns:
        if profile[column].dtype == "object":
            profile[column] = profile[column].astype(str).str.replace(
                "D",
                "E",
                regex=False,
            ).str.replace(
                "d",
                "E",
                regex=False,
            )
        profile[column] = pd.to_numeric(profile[column], errors="coerce")

    profile.attrs["source_file"] = str(path)
    profile.attrs["column_units"] = {item["label"]: item["unit"] for item in parsed_columns}
    profile.attrs["column_tags"] = {item["label"]: item["tag"] for item in parsed_columns}

    return profile, _column_metadata_frame(parsed_columns)


def _read_definition(case_directory: Path) -> dict[str, Any]:
    definition_file = case_directory / "definition.json"
    if not definition_file.is_file():
        return {}

    with definition_file.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _case_metadata_from_definition(definition: dict[str, Any]) -> dict[str, Any]:
    parameters = definition.get("parameters", {})
    return {
        "fuel_name": definition.get("fuel_name"),
        "alpha": parameters.get("alpha"),
        "beta": parameters.get("beta"),
        "gamma": parameters.get("gamma"),
        "strain_rate": definition.get("strain_rate", {}).get("value"),
        "distance": definition.get("distance", {}).get("value"),
    }


def _add_column_source(columns: Any, source: str) -> Any:
    annotated = columns.copy()
    annotated["source"] = source
    return annotated


def _prefix_profile_columns(profile: Any, prefix: str) -> Any:
    if not prefix:
        return profile
    return profile.rename(columns={column: f"{prefix}{column}" for column in profile.columns})


def _prefix_profile_columns_except(profile: Any, prefix: str, keep_unprefixed: set[str]) -> Any:
    if not prefix:
        return profile
    return profile.rename(
        columns={
            column: column if column in keep_unprefixed else f"{prefix}{column}"
            for column in profile.columns
        }
    )


def _prefix_column_metadata(columns: Any, prefix: str, source: str) -> Any:
    annotated = _add_column_source(columns, source)
    if prefix:
        annotated["label"] = annotated["label"].map(lambda label: f"{prefix}{label}")
    return annotated


def _prefix_column_metadata_except(
    columns: Any,
    prefix: str,
    source: str,
    keep_unprefixed: set[str],
) -> Any:
    annotated = _add_column_source(columns, source)
    if prefix:
        annotated["label"] = annotated["label"].map(
            lambda label: label if label in keep_unprefixed else f"{prefix}{label}"
        )
    return annotated


def read_campaign_status(campaign_directory: str | Path) -> Any:
    """Read ``CampaignStatus.csv`` from a campaign directory."""

    pd = _require_pandas()
    root = Path(campaign_directory)
    status_file = root / "CampaignStatus.csv"
    if not status_file.is_file():
        raise FileNotFoundError(f"CampaignStatus.csv not found in {root}")

    status = pd.read_csv(status_file)
    status["exit_code"] = status["exit_code"].astype("string")
    status["status"] = status["status"].astype("string")
    return status


def successful_cases(status: Any) -> Any:
    """Return rows marked as completed with exit code zero."""

    pd = _require_pandas()
    completed = status["status"].fillna("").astype(str).str.upper().eq("COMPLETED")
    numeric_exit_code = pd.to_numeric(status["exit_code"], errors="coerce")
    textual_exit_code = status["exit_code"].fillna("").astype(str).str.strip()
    clean_exit = numeric_exit_code.eq(0) | textual_exit_code.isin({"0", "0.0"})
    return status.loc[completed & clean_exit].copy()


def _validate_missing_policy(policy: str, name: str) -> None:
    if policy not in {"warn", "ignore", "raise"}:
        raise ValueError(f"{name} must be one of: warn, ignore, raise")


def _case_name_from_status_row(status_row: Any) -> str:
    return str(status_row.get("case", ""))


def _is_low_temperature_failure(status_row: Any) -> bool:
    status_text = str(status_row.get("status", "")).upper()
    exit_code = str(status_row.get("exit_code", "")).strip()
    try:
        low_temperature_exit_code = float(exit_code) == 10.0
    except ValueError:
        low_temperature_exit_code = exit_code == "10"
    return "LOW_TEMPERATURE" in status_text or low_temperature_exit_code


def low_temperature_cases(status: Any) -> list[str]:
    """Return case names explicitly marked as low-temperature failures."""

    cases: list[str] = []
    for _, status_row in status.iterrows():
        if _is_low_temperature_failure(status_row):
            cases.append(_case_name_from_status_row(status_row))
    return cases


def _handle_case_failure(
    failures: list[CaseFailure],
    failure: CaseFailure,
    policy: str,
) -> None:
    failures.append(failure)
    if policy == "raise":
        file_text = f" ({failure.file})" if failure.file is not None else ""
        detail_text = f": {failure.detail}" if failure.detail else ""
        raise RuntimeError(
            f"{failure.reason} for {failure.case}{file_text}{detail_text}"
        )


def load_campaign_step(
    campaign_directory: str | Path,
    step: str | int,
    columns: Optional[Sequence[str | int]] = None,
    include_soot: bool = False,
    soot_columns: Optional[Sequence[str | int]] = None,
    soot_prefix: str = "soot_",
    combine: bool = False,
    missing: str = "warn",
    missing_soot: str = "ignore",
) -> CampaignStepData:
    """Load successful cases for one step of a FIVES campaign.

    Args:
        campaign_directory: Folder containing ``CampaignStatus.csv`` and the
            ``Alpha_X_Beta_Y_Gamma_Z`` case directories.
        step: Step folder to read, for example ``"Step07"`` or ``7``.
        columns: Optional subset of columns to read from each solution file.
        include_soot: If true, also read optional ``Solution.soot.out`` files.
        soot_columns: Optional subset of columns to read from soot files.
        soot_prefix: Prefix added to soot column labels before merging them into
            each profile. The default produces names such as ``soot_fv(tot)``.
        combine: If true, also build one stacked DataFrame with case metadata
            repeated on each grid-point row. This can be large.
        missing: How to handle successful cases without the requested solution
            file: ``"warn"``, ``"ignore"``, or ``"raise"``.
        missing_soot: How to handle missing soot files for successful cases:
            ``"warn"``, ``"ignore"``, or ``"raise"``.
    """

    pd = _require_pandas()
    _validate_missing_policy(missing, "missing")
    _validate_missing_policy(missing_soot, "missing_soot")

    root = Path(campaign_directory).expanduser().resolve()
    step_name = normalize_step(step)

    status = read_campaign_status(root)
    ok_cases = successful_cases(status)
    temperature_failures = low_temperature_cases(status)

    profiles: dict[str, Any] = {}
    case_records: list[dict[str, Any]] = []
    combined_frames: list[Any] = []
    missing_files: list[Path] = []
    missing_soot_files: list[Path] = []
    load_failures: list[CaseFailure] = []
    soot_profiles: dict[str, Any] = {}
    column_metadata = None
    soot_column_metadata = None

    for _, status_row in ok_cases.iterrows():
        case_name = str(status_row["case"])
        case_directory = root / case_name
        output_directory = case_directory / step_name / "Output"
        solution_file = output_directory / SOLUTION_FILE_NAME
        profile = None

        if not solution_file.is_file():
            missing_files.append(solution_file)
            _handle_case_failure(
                load_failures,
                CaseFailure(
                    case=case_name,
                    source="final",
                    reason="missing result file",
                    file=solution_file,
                ),
                missing,
            )
        else:
            try:
                profile, current_columns = read_solution_file(solution_file, columns=columns)
            except Exception as exc:
                _handle_case_failure(
                    load_failures,
                    CaseFailure(
                        case=case_name,
                        source="final",
                        reason="incomplete result file",
                        file=solution_file,
                        detail=str(exc),
                    ),
                    missing,
                )
            else:
                if column_metadata is None:
                    column_metadata = _add_column_source(current_columns, "final")

        if include_soot:
            soot_file = output_directory / SOOT_FILE_NAME
            if soot_file.is_file():
                try:
                    soot_profile, current_soot_columns = read_solution_file(
                        soot_file,
                        columns=soot_columns,
                    )
                    if profile is None:
                        soot_profile = _prefix_profile_columns_except(
                            soot_profile,
                            soot_prefix,
                            {"x"},
                        )
                    else:
                        if "x" in soot_profile.columns:
                            soot_profile = soot_profile.drop(columns=["x"])
                            current_soot_columns = current_soot_columns.loc[
                                current_soot_columns["label"] != "x"
                            ].copy()
                        soot_profile = _prefix_profile_columns(soot_profile, soot_prefix)
                    soot_profile = soot_profile.reset_index(drop=True)
                    if profile is None:
                        profile = soot_profile
                    else:
                        profile = pd.concat(
                            [profile.reset_index(drop=True), soot_profile],
                            axis=1,
                        )
                    soot_profiles[case_name] = soot_profile

                    if soot_column_metadata is None:
                        if profile is soot_profile:
                            soot_column_metadata = _prefix_column_metadata_except(
                                current_soot_columns,
                                soot_prefix,
                                "soot",
                                {"x"},
                            )
                        else:
                            soot_column_metadata = _prefix_column_metadata(
                                current_soot_columns,
                                soot_prefix,
                                "soot",
                            )
                except Exception as exc:
                    if missing_soot != "ignore":
                        _handle_case_failure(
                            load_failures,
                            CaseFailure(
                                case=case_name,
                                source="soot",
                                reason="incomplete soot result file",
                                file=soot_file,
                                detail=str(exc),
                            ),
                            missing_soot,
                        )
            else:
                missing_soot_files.append(soot_file)
                if missing_soot != "ignore":
                    _handle_case_failure(
                        load_failures,
                        CaseFailure(
                            case=case_name,
                            source="soot",
                            reason="missing soot result file",
                            file=soot_file,
                        ),
                            missing_soot,
                        )

        if profile is None:
            continue

        definition = _read_definition(case_directory)
        metadata = _case_metadata_from_definition(definition)
        parsed = parse_case_parameters(case_name)
        for key, value in parsed.items():
            metadata[key] = metadata[key] if metadata.get(key) is not None else value

        metadata.update(
            {
                "case": case_name,
                "case_directory": str(case_directory),
                "solution_file": str(solution_file),
                "soot_file": str(output_directory / SOOT_FILE_NAME)
                if include_soot and (output_directory / SOOT_FILE_NAME).is_file()
                else None,
                "status": status_row["status"],
                "exit_code": status_row["exit_code"],
                "max_temperature_K": status_row.get("max_temperature_K"),
                "n_grid_points": len(profile),
                "n_columns_loaded": profile.shape[1],
            }
        )

        profile.attrs["case"] = case_name
        profile.attrs["step"] = step_name
        profile.attrs["case_metadata"] = metadata
        profiles[case_name] = profile
        case_records.append(metadata)

        if combine:
            frame = profile.copy()
            frame.insert(0, "case", case_name)
            frame.insert(1, "alpha", metadata.get("alpha"))
            frame.insert(2, "beta", metadata.get("beta"))
            frame.insert(3, "gamma", metadata.get("gamma"))
            frame.insert(4, "step", step_name)
            combined_frames.append(frame)

    if missing_files:
        message = (
            f"{len(missing_files)} successful case(s) do not contain "
            f"{step_name}/Output/{SOLUTION_FILE_NAME}"
        )
        if missing == "warn":
            print("Warning:", message)

    if missing_soot_files:
        message = (
            f"{len(missing_soot_files)} successful case(s) do not contain "
            f"{step_name}/Output/{SOOT_FILE_NAME}"
        )
        if missing_soot == "warn":
            print("Warning:", message)

    if column_metadata is None:
        column_metadata = pd.DataFrame(
            columns=["column", "position", "tag", "name", "unit", "label", "source"]
        )
    if soot_column_metadata is None:
        soot_column_metadata = pd.DataFrame(
            columns=["column", "position", "tag", "name", "unit", "label", "source"]
        )

    all_columns = pd.concat([column_metadata, soot_column_metadata], ignore_index=True)

    cases = pd.DataFrame(case_records)
    combined_profiles = pd.concat(combined_frames, ignore_index=True) if combined_frames else None

    return CampaignStepData(
        root=root,
        step=step_name,
        campaign_status=status,
        cases=cases,
        columns=all_columns,
        profiles=profiles,
        combined_profiles=combined_profiles,
        missing_files=missing_files,
        soot_columns=soot_column_metadata,
        soot_profiles=soot_profiles,
        missing_soot_files=missing_soot_files,
        load_failures=load_failures,
        temperature_failures=temperature_failures,
        metric_failures=[],
    )


def _nan() -> float:
    return float("nan")


def _first_profile_columns(data: CampaignStepData) -> list[str]:
    columns: list[str] = []
    for profile in data.profiles.values():
        for column in profile.columns:
            if column not in columns:
                columns.append(column)
    return columns


def _resolve_summary_variables(
    data: CampaignStepData,
    variables: Optional[Sequence[str | int]],
    coordinate: str,
    include_coordinate_variable: bool,
) -> list[str]:
    loaded_columns = _first_profile_columns(data)

    if variables is None:
        selected = loaded_columns
    else:
        column_records = data.columns.to_dict("records")
        try:
            selected = _resolve_requested_columns(column_records, variables)
        except KeyError:
            # If every completed case failed to produce a readable profile, or
            # one requested variable is absent from all readable profiles, still
            # build the requested metric columns so the output CSV can report
            # NaN for the affected simulations instead of aborting.
            selected = [str(variable) for variable in variables]

    if selected is None:
        selected = []

    if not include_coordinate_variable:
        selected = [variable for variable in selected if variable != coordinate]

    return selected


def _trapezoidal_integral(profile: Any, variable: str, coordinate: str) -> float:
    values = profile[[coordinate, variable]].dropna()
    if len(values) < 2:
        return _nan()

    x = values[coordinate].to_numpy()
    y = values[variable].to_numpy()
    return float(((x[1:] - x[:-1]) * (y[1:] + y[:-1]) * 0.5).sum())


def _profile_metrics(profile: Any, variables: Sequence[str], coordinate: str) -> dict[str, float]:
    if coordinate not in profile.columns:
        raise KeyError(
            f"Coordinate column '{coordinate}' was not loaded. Include it in "
            "load_campaign_step(..., columns=[...]) before computing integrals."
        )

    metrics: dict[str, float] = {}

    for variable in variables:
        if variable not in profile.columns:
            metrics[f"{variable}_max"] = _nan()
            metrics[f"{variable}_{coordinate}_at_max"] = _nan()
            metrics[f"{variable}_integral"] = _nan()
            continue

        valid_for_max = profile[[coordinate, variable]].dropna()
        if valid_for_max.empty:
            maximum = _nan()
            x_at_max = _nan()
        else:
            maximum_index = valid_for_max[variable].idxmax()
            maximum = float(profile.at[maximum_index, variable])
            x_at_max = float(profile.at[maximum_index, coordinate])

        metrics[f"{variable}_max"] = maximum
        metrics[f"{variable}_{coordinate}_at_max"] = x_at_max
        metrics[f"{variable}_integral"] = _trapezoidal_integral(profile, variable, coordinate)

    return metrics


def summarize_campaign_step(
    data: CampaignStepData,
    variables: Optional[Sequence[str | int]] = None,
    coordinate: str = "x",
    include_coordinate_variable: bool = False,
    include_status: bool = False,
) -> Any:
    """Build one-row-per-simulation metrics for a loaded campaign step.

    The output includes every case listed in ``CampaignStatus.csv``.  Cases that
    did not complete successfully, or completed but have no loaded profile, keep
    their alpha/beta/gamma values and receive NaN for all metric columns.

    Args:
        data: Result returned by ``load_campaign_step``.
        variables: Variables to summarize. Values may be clean names, original
            tags, or 1-based column numbers. If omitted, all loaded variables are
            summarized except the coordinate column.
        coordinate: Spatial coordinate used for locations and integrals.
        include_coordinate_variable: Also summarize the coordinate itself.
        include_status: Include status and exit-code diagnostics in the output.

    Returns:
        A pandas DataFrame with one row per simulation.
    """

    pd = _require_pandas()
    data.metric_failures = []
    selected_variables = _resolve_summary_variables(
        data,
        variables=variables,
        coordinate=coordinate,
        include_coordinate_variable=include_coordinate_variable,
    )

    metric_columns: list[str] = []
    for variable in selected_variables:
        metric_columns.extend(
            [
                f"{variable}_max",
                f"{variable}_{coordinate}_at_max",
                f"{variable}_integral",
            ]
        )

    rows: list[dict[str, Any]] = []

    for _, status_row in data.campaign_status.iterrows():
        case_name = str(status_row["case"])
        parsed = parse_case_parameters(case_name)
        row: dict[str, Any] = {
            "alpha": parsed["alpha"],
            "beta": parsed["beta"],
            "gamma": parsed["gamma"],
        }

        if include_status:
            row.update(
                {
                    "case": case_name,
                    "status": status_row.get("status"),
                    "exit_code": status_row.get("exit_code"),
                }
            )
            if "source_case" in data.campaign_status.columns:
                row["source_case"] = status_row.get("source_case")

        row.update({column: _nan() for column in metric_columns})

        profile = data.profiles.get(case_name)
        if profile is not None:
            missing_variables = [
                variable for variable in selected_variables if variable not in profile.columns
            ]
            if missing_variables:
                data.metric_failures.append(
                    CaseFailure(
                        case=case_name,
                        source="metrics",
                        reason="metric variable not found",
                        detail=", ".join(missing_variables),
                    )
                )

            try:
                row.update(_profile_metrics(profile, selected_variables, coordinate))
            except Exception as exc:
                data.metric_failures.append(
                    CaseFailure(
                        case=case_name,
                        source="metrics",
                        reason="metric extraction failed",
                        detail=str(exc),
                    )
                )

        rows.append(row)

    leading_columns = ["alpha", "beta", "gamma"]
    if include_status:
        leading_columns.extend(["case", "status", "exit_code"])
        if "source_case" in data.campaign_status.columns:
            leading_columns.append("source_case")

    return pd.DataFrame(rows, columns=leading_columns + metric_columns)


def write_campaign_step_metrics(
    data: CampaignStepData,
    output_file: str | Path,
    variables: Optional[Sequence[str | int]] = None,
    coordinate: str = "x",
    include_coordinate_variable: bool = False,
    include_status: bool = False,
    na_rep: str = "NaN",
) -> Any:
    """Write campaign-step summary metrics to a CSV file.

    Returns the same DataFrame written to disk.
    """

    summary = summarize_campaign_step(
        data,
        variables=variables,
        coordinate=coordinate,
        include_coordinate_variable=include_coordinate_variable,
        include_status=include_status,
    )
    summary.to_csv(output_file, index=False, na_rep=na_rep)
    return summary


def load_and_write_campaign_step_metrics(
    campaign_directory: str | Path,
    step: str | int,
    output_file: str | Path,
    columns: Optional[Sequence[str | int]] = None,
    include_soot: bool = False,
    soot_columns: Optional[Sequence[str | int]] = None,
    soot_prefix: str = "soot_",
    variables: Optional[Sequence[str | int]] = None,
    coordinate: str = "x",
    include_status: bool = False,
    missing: str = "warn",
    missing_soot: str = "ignore",
) -> Any:
    """Convenience wrapper: load one step and immediately write its metrics CSV."""

    load_columns = list(columns) if columns is not None else None
    if load_columns is not None and coordinate not in [str(item) for item in load_columns]:
        load_columns.insert(0, coordinate)

    data = load_campaign_step(
        campaign_directory,
        step=step,
        columns=load_columns,
        include_soot=include_soot,
        soot_columns=soot_columns,
        soot_prefix=soot_prefix,
        combine=False,
        missing=missing,
        missing_soot=missing_soot,
    )
    return write_campaign_step_metrics(
        data,
        output_file=output_file,
        variables=variables,
        coordinate=coordinate,
        include_status=include_status,
    )


def _sorted_unique_values(frame: Any, column: str) -> list[Any]:
    values = list(frame[column].dropna().unique())
    try:
        return sorted(values)
    except TypeError:
        return sorted(values, key=str)


def _format_axis_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _summary_case_labels(frame: Any) -> list[str]:
    labels: list[str] = []
    for _, row in frame.iterrows():
        if "case" in frame.columns:
            labels.append(str(row["case"]))
        else:
            labels.append(
                "Alpha_{alpha:g}_Beta_{beta:g}_Gamma_{gamma:g}".format(
                    alpha=float(row["alpha"]),
                    beta=float(row["beta"]),
                    gamma=float(row["gamma"]),
                )
            )
    return labels


def _preview_case_labels(frame: Any, limit: int = 20) -> str:
    labels = _summary_case_labels(frame)
    if not labels:
        return "none"
    preview = ", ".join(labels[:limit])
    if len(labels) > limit:
        preview += f", ... ({len(labels) - limit} more)"
    return preview


def _finite_range_text(values: Any) -> str:
    if values.empty:
        return "min=n/a, max=n/a"
    return f"min={float(values.min()):.6g}, max={float(values.max()):.6g}"


def _available_metric_columns(summary: Any) -> list[str]:
    parameters = {
        "alpha",
        "beta",
        "gamma",
        "case",
        "status",
        "exit_code",
        "source_case",
    }
    return [column for column in summary.columns if column not in parameters]


def _variable_from_metric_name(metric: Optional[str], coordinate: str) -> Optional[str]:
    if not metric:
        return None

    if metric.endswith("_max"):
        return metric[:-4]
    if metric.endswith("_integral"):
        return metric[: -len("_integral")]

    location_suffix = f"_{coordinate}_at_max"
    if metric.endswith(location_suffix):
        return metric[: -len(location_suffix)]

    return None


def plot_metric_slices(
    summary: Any,
    metric: str,
    fixed: str = "gamma",
    x: Optional[str] = None,
    y: Optional[str] = None,
    output_file: Optional[str | Path] = None,
    cmap: str = "viridis",
    ncols: Optional[int] = None,
    figsize_per_panel: tuple[float, float] = (4.0, 3.4),
    annotate: bool = False,
    value_format: str = ".3g",
    title: Optional[str] = None,
    vmin: Optional[float] = None,
    vmax: Optional[float] = None,
    log_scale: bool = False,
    dpi: int = 200,
    show: bool = False,
) -> tuple[Any, Any]:
    """Plot 2D heatmap slices of one metric over alpha/beta/gamma space.

    Args:
        summary: One-row-per-simulation DataFrame returned by
            ``summarize_campaign_step`` or read from a metrics CSV.
        metric: Metric column to plot, such as ``"T_max"`` or
            ``"CH4_w_integral"``.
        fixed: Parameter held fixed in each panel. One of ``alpha``, ``beta``,
            or ``gamma``.
        x: Parameter on the horizontal axis. Defaults to the first non-fixed
            parameter.
        y: Parameter on the vertical axis. Defaults to the second non-fixed
            parameter.
        output_file: Optional image path. The format is inferred from the
            extension, for example ``.png`` or ``.pdf``.
        cmap: Matplotlib colormap name. Missing/failed cases are shown in gray.
        ncols: Number of subplot columns. Defaults to at most three.
        figsize_per_panel: Width and height of each slice panel in inches.
        annotate: If true, write the metric value inside each populated cell.
        value_format: Format specifier used for annotations.
        title: Optional figure title.
        vmin, vmax: Optional shared colorbar limits.
        log_scale: If true, use logarithmic color scaling. Non-positive values
            are shown as gray cells, like missing or failed simulations.
        dpi: Output resolution for raster formats.
        show: If true, call ``plt.show()``.

    Returns:
        ``(figure, axes)`` from Matplotlib.
    """

    pd = _require_pandas()
    plt, np = _require_matplotlib()
    from matplotlib.colors import LogNorm, Normalize

    parameter_columns = ["alpha", "beta", "gamma"]
    if fixed not in parameter_columns:
        raise ValueError("fixed must be one of: alpha, beta, gamma")
    if metric not in summary.columns:
        available = _available_metric_columns(summary)
        preview = ", ".join(available[:20])
        if len(available) > 20:
            preview += ", ..."
        raise KeyError(
            f"Metric column not found: {metric}. Available metric columns: "
            f"{preview or 'none'}. Check --columns and --metrics-variables."
        )

    free_parameters = [parameter for parameter in parameter_columns if parameter != fixed]
    x_column = x or free_parameters[0]
    y_column = y or free_parameters[1]

    for column in [fixed, x_column, y_column]:
        if column not in parameter_columns:
            raise ValueError(f"Plot axis must be one of alpha, beta, gamma: {column}")
    if len({fixed, x_column, y_column}) != 3:
        raise ValueError("fixed, x, and y must refer to three different parameters.")

    fixed_values = _sorted_unique_values(summary, fixed)
    x_values = _sorted_unique_values(summary, x_column)
    y_values = _sorted_unique_values(summary, y_column)
    if not fixed_values:
        raise ValueError(f"No finite values found for fixed parameter: {fixed}")

    if ncols is None:
        ncols = min(3, len(fixed_values))
    nrows = math.ceil(len(fixed_values) / ncols)

    summary = summary.copy()
    summary[metric] = pd.to_numeric(summary[metric], errors="coerce")
    metric_values = summary[metric].dropna()
    if log_scale:
        metric_values = metric_values.loc[metric_values > 0]
        if metric_values.empty:
            numeric_metric = summary[metric]
            finite_values = numeric_metric.dropna()
            nonpositive_cases = summary.loc[
                numeric_metric.notna() & numeric_metric.le(0)
            ]
            missing_cases = summary.loc[numeric_metric.isna()]
            if finite_values.empty:
                detail = "all metric values are missing or non-numeric"
                affected = summary
            else:
                detail = _finite_range_text(finite_values)
                affected = nonpositive_cases
            raise ValueError(
                f"Metric '{metric}' has no positive finite values for logarithmic "
                f"plotting ({detail}; finite={len(finite_values)}, "
                f"positive=0, missing={len(missing_cases)}). "
                f"Affected simulations: {_preview_case_labels(affected)}"
            )

    if vmin is None:
        vmin = float(metric_values.min()) if not metric_values.empty else 0.0
    if vmax is None:
        vmax = float(metric_values.max()) if not metric_values.empty else 1.0
    if log_scale and (vmin <= 0 or vmax <= 0):
        raise ValueError("vmin and vmax must be positive when log_scale=True.")
    if vmin > vmax:
        raise ValueError("vmin must be smaller than or equal to vmax.")
    if vmin == vmax:
        delta = abs(vmin) * 0.05 if vmin != 0 else 1.0
        vmin -= delta
        vmax += delta
    norm = LogNorm(vmin=vmin, vmax=vmax) if log_scale else Normalize(vmin=vmin, vmax=vmax)

    colormap = plt.get_cmap(cmap).copy()
    colormap.set_bad("#d9d9d9")

    fig_width = figsize_per_panel[0] * ncols
    fig_height = figsize_per_panel[1] * nrows
    fig, axes = plt.subplots(
        nrows,
        ncols,
        figsize=(fig_width, fig_height),
        squeeze=False,
        layout="constrained",
    )

    image = None
    flat_axes = list(axes.ravel())
    for axis, fixed_value in zip(flat_axes, fixed_values):
        subset = summary.loc[summary[fixed].eq(fixed_value)]
        pivot = subset.pivot_table(
            index=y_column,
            columns=x_column,
            values=metric,
            aggfunc="mean",
        ).reindex(index=y_values, columns=x_values)

        values = pivot.to_numpy(dtype=float)
        if log_scale:
            masked_values = np.ma.masked_where(values <= 0, values)
            masked_values = np.ma.masked_invalid(masked_values)
        else:
            masked_values = np.ma.masked_invalid(values)
        image = axis.imshow(
            masked_values,
            origin="lower",
            aspect="auto",
            cmap=colormap,
            norm=norm,
        )

        axis.set_title(f"{fixed} = {_format_axis_value(fixed_value)}")
        axis.set_xlabel(x_column)
        axis.set_ylabel(y_column)
        axis.set_xticks(range(len(x_values)))
        axis.set_yticks(range(len(y_values)))
        axis.set_xticklabels([_format_axis_value(value) for value in x_values])
        axis.set_yticklabels([_format_axis_value(value) for value in y_values])

        if annotate:
            for row_index, _ in enumerate(y_values):
                for column_index, _ in enumerate(x_values):
                    value = values[row_index, column_index]
                    if not np.isnan(value):
                        axis.text(
                            column_index,
                            row_index,
                            format(value, value_format),
                            ha="center",
                            va="center",
                            fontsize=8,
                        )

    for axis in flat_axes[len(fixed_values):]:
        axis.set_axis_off()

    if image is not None:
        colorbar = fig.colorbar(image, ax=flat_axes, shrink=0.92)
        colorbar.set_label(metric)

    scale_text = ", log scale" if log_scale else ""
    fig.suptitle(
        title or f"{metric} slices at fixed {fixed}{scale_text} (gray = failed/missing)"
    )

    if output_file is not None:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=dpi)

    if show:
        plt.show()

    return fig, axes


def plot_metric_slices_from_csv(
    metrics_file: str | Path,
    metric: str,
    fixed: str = "gamma",
    output_file: Optional[str | Path] = None,
    log_scale: bool = False,
    **kwargs: Any,
) -> tuple[Any, Any]:
    """Read a metrics CSV and plot 2D heatmap slices for one metric."""

    pd = _require_pandas()
    summary = pd.read_csv(metrics_file)
    return plot_metric_slices(
        summary,
        metric=metric,
        fixed=fixed,
        output_file=output_file,
        log_scale=log_scale,
        **kwargs,
    )


def _split_columns(text: Optional[str]) -> Optional[list[str]]:
    if text is None or not text.strip():
        return None
    return [item.strip() for item in text.split(",") if item.strip()]


def _print_case_list(prefix: str, cases: Sequence[str]) -> None:
    for case_name in cases:
        print(f"{prefix}: {case_name}")


def _failure_summary_label(failure: CaseFailure) -> str:
    if failure.source == "soot":
        return "incomplete soot"
    if failure.source == "metrics":
        return "metric problem"
    return "incomplete"


def _print_failures(failures: Sequence[CaseFailure]) -> None:
    for failure in failures:
        print(f"Failed ({_failure_summary_label(failure)}): {failure.case}")
        if failure.file is not None:
            print(f"  file: {failure.file}")
        if failure.detail:
            print(f"  detail: {failure.detail}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Load FIVES campaign Solution.final.out files for one step."
    )
    parser.add_argument("campaign_directory", help="Folder containing CampaignStatus.csv")
    parser.add_argument("--step", default="Step07", help="Step folder to load, e.g. Step07 or 7")
    parser.add_argument(
        "--columns",
        help="Comma-separated columns to load, e.g. x,T,CH4_w,O2_w or 2,3,369",
    )
    parser.add_argument(
        "--include-soot",
        action="store_true",
        help=f"Also read optional {SOOT_FILE_NAME} files from the selected step.",
    )
    parser.add_argument(
        "--soot-columns",
        help="Comma-separated soot columns to load, e.g. fv(tot),N(tot),d32(agg).",
    )
    parser.add_argument(
        "--soot-prefix",
        default="soot_",
        help="Prefix added to soot column labels before merging them into profiles.",
    )
    parser.add_argument(
        "--combine",
        action="store_true",
        help="Create one stacked DataFrame in memory. Useful for plotting, but can be large.",
    )
    parser.add_argument(
        "--missing",
        choices=("warn", "ignore", "raise"),
        default="warn",
        help="How to handle successful cases missing Solution.final.out.",
    )
    parser.add_argument(
        "--missing-soot",
        choices=("warn", "ignore", "raise"),
        default="ignore",
        help="How to handle successful cases missing Solution.soot.out.",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print a compact summary after loading.",
    )
    parser.add_argument(
        "--metrics-output",
        help="Write one-row-per-simulation metrics to this CSV file.",
    )
    parser.add_argument(
        "--metrics-variables",
        help=(
            "Comma-separated variables to summarize. Defaults to all loaded "
            "variables except x."
        ),
    )
    parser.add_argument(
        "--coordinate",
        default="x",
        help="Coordinate column used for location and integral metrics.",
    )
    parser.add_argument(
        "--include-status",
        action="store_true",
        help="Include case/status/exit_code diagnostic columns in the metrics CSV.",
    )
    parser.add_argument(
        "--plot-metric",
        help="Metric column to plot as heatmap slices, e.g. T_max or CH4_w_integral.",
    )
    parser.add_argument(
        "--plot-output",
        help="Image file for the heatmap slices, e.g. T_max_by_gamma.png.",
    )
    parser.add_argument(
        "--plot-fixed",
        choices=("alpha", "beta", "gamma"),
        default="gamma",
        help="Parameter held fixed in each heatmap panel.",
    )
    parser.add_argument("--plot-x", choices=("alpha", "beta", "gamma"), help="Heatmap x-axis.")
    parser.add_argument("--plot-y", choices=("alpha", "beta", "gamma"), help="Heatmap y-axis.")
    parser.add_argument(
        "--plot-cmap",
        default="viridis",
        help="Matplotlib colormap used for heatmap slices.",
    )
    parser.add_argument(
        "--plot-vmin",
        type=float,
        help="Minimum value for the plot color scale.",
    )
    parser.add_argument(
        "--plot-vmax",
        type=float,
        help="Maximum value for the plot color scale.",
    )
    parser.add_argument(
        "--plot-annotate",
        action="store_true",
        help="Write metric values inside heatmap cells.",
    )
    parser.add_argument(
        "--plot-log",
        action="store_true",
        help="Use logarithmic color scaling for the plotted metric.",
    )
    args = parser.parse_args(argv)

    requested_columns = _split_columns(args.columns)
    plot_variable = _variable_from_metric_name(args.plot_metric, args.coordinate)
    if (args.metrics_output or args.plot_metric) and requested_columns is not None:
        requested_as_text = [str(item) for item in requested_columns]
        if args.coordinate not in requested_as_text:
            requested_columns.insert(0, args.coordinate)
    requested_soot_columns = _split_columns(args.soot_columns)
    if (
        args.include_soot
        and (args.metrics_output or args.plot_metric)
        and requested_soot_columns is not None
    ):
        requested_soot_as_text = [str(item) for item in requested_soot_columns]
        if args.coordinate not in requested_soot_as_text:
            requested_soot_columns.insert(0, args.coordinate)
        if (
            plot_variable is not None
            and args.soot_prefix
            and plot_variable.startswith(args.soot_prefix)
        ):
            soot_plot_variable = plot_variable[len(args.soot_prefix):]
            if soot_plot_variable not in requested_soot_as_text:
                requested_soot_columns.append(soot_plot_variable)

    effective_missing_soot = args.missing_soot
    if (
        effective_missing_soot == "ignore"
        and plot_variable is not None
        and args.soot_prefix
        and plot_variable.startswith(args.soot_prefix)
    ):
        effective_missing_soot = "warn"

    data = load_campaign_step(
        args.campaign_directory,
        args.step,
        columns=requested_columns,
        include_soot=args.include_soot,
        soot_columns=requested_soot_columns,
        soot_prefix=args.soot_prefix,
        combine=args.combine,
        missing=args.missing,
        missing_soot=effective_missing_soot,
    )

    metrics = None
    if args.metrics_output or args.plot_metric:
        metrics_variables = _split_columns(args.metrics_variables)
        if metrics_variables is None and plot_variable is not None:
            metrics_variables = _first_profile_columns(data)
            if plot_variable not in metrics_variables:
                metrics_variables.append(plot_variable)

        metrics = summarize_campaign_step(
            data,
            variables=metrics_variables,
            coordinate=args.coordinate,
            include_status=args.include_status,
        )
        if args.metrics_output:
            metrics.to_csv(args.metrics_output, index=False, na_rep="NaN")

    if args.plot_metric:
        if metrics is None:
            raise RuntimeError("Internal error: metrics were not computed before plotting.")
        try:
            plot_metric_slices(
                metrics,
                metric=args.plot_metric,
                fixed=args.plot_fixed,
                x=args.plot_x,
                y=args.plot_y,
                output_file=args.plot_output,
                cmap=args.plot_cmap,
                vmin=args.plot_vmin,
                vmax=args.plot_vmax,
                annotate=args.plot_annotate,
                log_scale=args.plot_log,
            )
        except Exception as exc:
            print(f"Error while plotting metric '{args.plot_metric}': {exc}")
            if data.temperature_failures:
                _print_case_list("Failed (temperature too low)", data.temperature_failures)
            if data.load_failures:
                _print_failures(data.load_failures)
            if data.metric_failures:
                _print_failures(data.metric_failures)
            return 1

    if args.summary:
        print(f"Campaign: {data.root}")
        print(f"Step: {data.step}")
        print(f"Successful cases loaded: {len(data.profiles)}")
        print(f"Missing files: {len(data.missing_files)}")
        if args.include_soot:
            missing_soot_count = len(data.missing_soot_files or [])
            print(f"Soot profiles loaded: {len(data.soot_profiles or {})}")
            print(f"Missing soot files: {missing_soot_count}")
        print(f"Columns described: {len(data.columns)}")
        if data.temperature_failures:
            _print_case_list("Failed (temperature too low)", data.temperature_failures)
        if data.load_failures:
            _print_failures(data.load_failures)
        if data.metric_failures:
            _print_failures(data.metric_failures)
        if data.combined_profiles is not None:
            rows, cols = data.combined_profiles.shape
            print(f"Combined profile shape: {rows} rows x {cols} columns")
        if metrics is not None:
            rows, cols = metrics.shape
            if args.metrics_output:
                print(f"Metrics written: {args.metrics_output}")
            print(f"Metrics shape: {rows} rows x {cols} columns")
        if args.plot_metric and args.plot_output:
            print(f"Plot written: {args.plot_output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
