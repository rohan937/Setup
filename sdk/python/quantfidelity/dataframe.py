"""DataFrame/table conversion helpers. Pandas is optional.

Provides lightweight utilities for converting pandas DataFrames (or plain
list[dict]) to the list[dict] format expected by EvidenceBundle setters.
Pandas is never imported at module level — all imports are lazy so that
projects without pandas installed can still use the rest of the SDK.
"""
from __future__ import annotations

import math
from typing import Any


def is_dataframe_like(obj: Any) -> bool:
    """Return True if *obj* is a pandas DataFrame.

    Detection is duck-type based so pandas is never imported at module level.
    """
    cls = type(obj)
    return (
        cls.__name__ == "DataFrame"
        and hasattr(cls, "iterrows")
        and hasattr(cls, "to_dict")
    )


def _nan_to_none(val: Any) -> Any:
    """Convert NaN/NaT/numpy scalars to Python-native types safely.

    Rules applied in order:
    1. ``None`` passes through unchanged.
    2. numpy scalars (have ``.item()``) are unwrapped to Python natives;
       float NaN is converted to ``None``.
    3. datetime-like objects (have ``.isoformat()``) are converted to ISO strings.
    4. Plain Python ``float`` NaN is converted to ``None``.
    5. pandas NA/NaT are detected via ``pd.isna()`` and converted to ``None``.
    """
    if val is None:
        return None

    # numpy scalars → Python native
    if hasattr(val, "item"):
        try:
            converted = val.item()
            if isinstance(converted, float) and math.isnan(converted):
                return None
            return converted
        except Exception:
            pass

    # pandas Timestamp / datetime → ISO string
    if hasattr(val, "isoformat"):
        try:
            return val.isoformat()
        except Exception:
            pass

    # plain float NaN
    if isinstance(val, float) and math.isnan(val):
        return None

    # pandas NA / NaT (catch-all)
    try:
        import pandas as pd  # noqa: PLC0415
        if pd.isna(val):
            return None
    except (ImportError, TypeError, ValueError):
        pass

    return val


def _df_to_records(df: Any) -> list[dict[str, Any]]:
    """Convert a pandas DataFrame to ``list[dict]`` with NaN→None, datetimes→ISO."""
    records: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        records.append({col: _nan_to_none(val) for col, val in row.items()})
    return records


def rows_from_table(obj: Any) -> list[dict[str, Any]]:
    """Accept ``list[dict]`` or a pandas DataFrame; return ``list[dict]``.

    Parameters
    ----------
    obj:
        Either a ``list[dict]`` or a pandas ``DataFrame``.

    Returns
    -------
    list[dict]
        Rows with NaN/NaT converted to ``None`` and datetimes to ISO strings.

    Raises
    ------
    QuantFidelityValidationError
        If *obj* is neither a list of dicts nor a DataFrame.
    """
    from quantfidelity.exceptions import QuantFidelityValidationError  # noqa: PLC0415

    if isinstance(obj, list):
        if obj and not isinstance(obj[0], dict):
            raise QuantFidelityValidationError(
                f"rows_from_table: list items must be dicts, got {type(obj[0]).__name__}"
            )
        return normalize_records(obj)

    if is_dataframe_like(obj):
        return _df_to_records(obj)

    raise QuantFidelityValidationError(
        f"rows_from_table: expected list[dict] or pandas DataFrame, got {type(obj).__name__}"
    )


def validate_required_columns(
    rows: list[dict[str, Any]],
    required_columns: list[str],
    context: str = "",
) -> None:
    """Raise :class:`~quantfidelity.exceptions.QuantFidelityValidationError` if
    any required column is missing from all rows.

    Parameters
    ----------
    rows:
        List of record dicts.
    required_columns:
        Column names that must appear in at least one row.
    context:
        Optional description included in the error message.
    """
    from quantfidelity.exceptions import QuantFidelityValidationError  # noqa: PLC0415

    if not rows:
        return
    missing = [col for col in required_columns if not any(col in row for row in rows)]
    if missing:
        ctx = f" in {context}" if context else ""
        raise QuantFidelityValidationError(
            f"Required columns missing{ctx}: {missing}"
        )


def normalize_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a new list of dicts with values safe for JSON serialisation.

    Converts NaN→None and datetimes→ISO strings.  Never mutates the input.

    Parameters
    ----------
    rows:
        Input list of record dicts.

    Returns
    -------
    list[dict]
        A fresh list with all values normalised.
    """
    return [{k: _nan_to_none(v) for k, v in row.items()} for row in rows]
