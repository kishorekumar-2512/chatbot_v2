"""
backend/chart_builder.py

Smart auto-chart selection: picks a chart type based on the SHAPE of the
query result, instead of the old rule (chart only if exactly 2 columns and
the 2nd is numeric). Pure local computation — no MCP round-trip needed,
since this is deterministic and fast.

Shapes handled:
  1 row,  1 numeric col              -> single_stat  (frontend: animated counter)
  date col + 1 numeric               -> line (or area if question says "cumulative")
  date col + category + 1 numeric    -> multi-series line, one line per category
  label + numeric, few categories    -> donut (parts of a whole)
  label + numeric, many categories   -> bar
  category + subcategory + numeric   -> grouped bar (e.g. "top N per group" results)
  anything else                      -> no chart, table only
"""
from __future__ import annotations

import re
import pandas as pd

_DATE_HINT = re.compile(r"date|time|_at$|created|updated|month|day|year", re.IGNORECASE)
_CUMULATIVE_HINT = re.compile(r"cumulative|running\s+total", re.IGNORECASE)


def _find_date_col(df: pd.DataFrame) -> str | None:
    for col in df.columns:
        if _DATE_HINT.search(col):
            try:
                parsed = pd.to_datetime(df[col], errors="coerce")
                if parsed.notna().sum() >= max(2, int(len(df) * 0.6)):
                    return col
            except Exception:
                continue
    return None


def build_chart(rows: list[dict], title: str, question: str = "") -> tuple[str | None, str | None, dict | None]:
    """
    Returns (chart_json, chart_kind, single_stat):
      chart_json  — Plotly figure JSON string, or None
      chart_kind  — "line" | "area" | "bar" | "donut" | "grouped_bar" | "single_stat" | None
      single_stat — {"label": str, "value": number} when chart_kind == "single_stat", else None
                    (frontend renders this as an animated count-up, not a plotly figure)
    """
    if not rows:
        return None, None, None
    try:
        df = pd.DataFrame(rows)
    except Exception:
        return None, None, None

    cols = list(df.columns)
    numeric_cols = [c for c in cols if pd.api.types.is_numeric_dtype(df[c])]
    non_numeric_cols = [c for c in cols if c not in numeric_cols]

    # Single number result — e.g. "how many customers" — no chart makes sense,
    # but an animated counter does.
    if len(df) == 1 and len(numeric_cols) == 1 and len(cols) <= 2:
        val = df.iloc[0][numeric_cols[0]]
        try:
            val = float(val)
        except (TypeError, ValueError):
            return None, None, None
        return None, "single_stat", {"label": numeric_cols[0].replace("_", " "), "value": val}

    if not numeric_cols:
        return None, None, None  # nothing numeric to plot

    date_col = _find_date_col(df)
    is_cumulative = bool(_CUMULATIVE_HINT.search(question))

    try:
        import plotly.express as px

        # Time series: date + 1 numeric -> line / area
        if date_col and len(cols) == 2:
            metric = numeric_cols[0]
            d = df.sort_values(date_col)
            fig = px.area(d, x=date_col, y=metric, title=title) if is_cumulative \
                else px.line(d, x=date_col, y=metric, markers=True, title=title)
            return fig.to_json(), ("area" if is_cumulative else "line"), None

        # Time series with a breakdown dimension -> multi-series line
        if date_col and len(cols) == 3 and len(non_numeric_cols) == 2:
            metric = numeric_cols[0]
            other_col = [c for c in non_numeric_cols if c != date_col][0]
            d = df.sort_values(date_col)
            fig = px.line(d, x=date_col, y=metric, color=other_col, markers=True, title=title)
            return fig.to_json(), "line", None

        # label + numeric (2 cols): donut for a small set of categories that
        # look like they sum to a whole, otherwise a plain bar chart.
        if len(cols) == 2 and len(non_numeric_cols) == 1:
            label_col, metric = non_numeric_cols[0], numeric_cols[0]
            nunique = df[label_col].nunique()
            looks_like_whole = 2 <= nunique <= 6 and len(df) == nunique
            if looks_like_whole:
                fig = px.pie(df, names=label_col, values=metric, title=title, hole=0.45)
                return fig.to_json(), "donut", None
            fig = px.bar(df, x=label_col, y=metric, title=title)
            fig.update_xaxes(tickangle=-30)
            return fig.to_json(), "bar", None

        # category + subcategory + numeric (3 cols, no date) -> grouped bar
        # (this is exactly the shape of "top N per group" CTE/window results)
        if len(cols) == 3 and len(non_numeric_cols) == 2 and len(numeric_cols) == 1:
            cat1, cat2 = non_numeric_cols
            metric = numeric_cols[0]
            fig = px.bar(df, x=cat1, y=metric, color=cat2, barmode="group", title=title)
            fig.update_xaxes(tickangle=-30)
            return fig.to_json(), "grouped_bar", None

    except Exception:
        return None, None, None

    return None, None, None
