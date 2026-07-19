"""Helpers for scalable continuous-beam input handling.

Keeps the 4th-through-10th span rows consistent across form validation,
view parsing, result rendering, and saved-design reporting.
"""

MAX_CONTINUOUS_SPANS = 10
MAX_EXTRA_SPANS = MAX_CONTINUOUS_SPANS - 3
DEFAULT_EXTRA_SUPPORT_TYPE = "wall_plate"
DEFAULT_EXTRA_BEARING_IN = "3.5"


def blank_extra_span_rows():
    return [
        {
            "span_label": f"Span {index}",
            "support_label": f"B{index}",
            "span_ft": "",
            "support_type": DEFAULT_EXTRA_SUPPORT_TYPE,
            "bearing_length_in": DEFAULT_EXTRA_BEARING_IN,
            "errors": {},
        }
        for index in range(4, MAX_CONTINUOUS_SPANS + 1)
    ]


def parse_extra_span_rows(data):
    raw_spans = data.getlist("extra_span_ft")
    raw_support_types = data.getlist("extra_support_type")
    raw_bearings = data.getlist("extra_bearing_length_in")
    rows = []
    extra_spans = []
    extra_support_types = []
    extra_bearings = []
    seen_blank = False
    has_errors = False

    for row_index in range(MAX_EXTRA_SPANS):
        span_label_number = row_index + 4
        support_label = f"B{span_label_number}"
        span_raw = (raw_spans[row_index] if row_index < len(raw_spans) else "").strip()
        support_type = (
            (raw_support_types[row_index] if row_index < len(raw_support_types) else DEFAULT_EXTRA_SUPPORT_TYPE).strip()
            or DEFAULT_EXTRA_SUPPORT_TYPE
        )
        bearing_raw = (raw_bearings[row_index] if row_index < len(raw_bearings) else DEFAULT_EXTRA_BEARING_IN).strip()
        row = {
            "span_label": f"Span {span_label_number}",
            "support_label": support_label,
            "span_ft": span_raw,
            "support_type": support_type,
            "bearing_length_in": bearing_raw,
            "errors": {},
        }

        if not span_raw:
            seen_blank = True
            if bearing_raw not in ("", DEFAULT_EXTRA_BEARING_IN) or support_type != DEFAULT_EXTRA_SUPPORT_TYPE:
                row["errors"]["span_ft"] = "Enter a span before filling this support row."
                has_errors = True
            rows.append(row)
            continue

        if seen_blank:
            row["errors"]["span_ft"] = "Continuous spans must be entered in order without gaps."
            has_errors = True

        try:
            span_value = float(span_raw)
            if span_value <= 0:
                raise ValueError
            extra_spans.append(span_value)
        except ValueError:
            row["errors"]["span_ft"] = "Enter a span greater than 0."
            has_errors = True

        try:
            bearing_value = float(bearing_raw)
            if bearing_value < 0.5:
                raise ValueError
            extra_bearings.append(bearing_value)
        except ValueError:
            row["errors"]["bearing_length_in"] = "Bearing length must be at least 0.5 in."
            has_errors = True

        extra_support_types.append(support_type)
        rows.append(row)

    return {
        "rows": rows,
        "extra_spans": extra_spans,
        "extra_support_types": extra_support_types,
        "extra_bearings": extra_bearings,
        "has_errors": has_errors,
    }


def full_span_values(data):
    spans = [data["span_ft"]]
    if data.get("span_2_ft"):
        spans.append(data["span_2_ft"])
    if data.get("span_3_ft"):
        spans.append(data["span_3_ft"])
    spans.extend(data.get("extra_spans_ft") or [])
    return spans


def interior_bearing_values(data):
    values = []
    if data.get("span_2_ft"):
        values.append(data["bearing_length_mid_in"])
    if data.get("span_3_ft"):
        values.append(data["bearing_length_mid_2_in"])
    values.extend(data.get("extra_interior_bearing_lengths_in") or [])
    return values


def support_type_sequence(data):
    sequence = [data["support_type_left"]]
    if data.get("span_2_ft"):
        sequence.append(data.get("support_type_mid") or DEFAULT_EXTRA_SUPPORT_TYPE)
    if data.get("span_3_ft"):
        sequence.append(data.get("support_type_mid_2") or DEFAULT_EXTRA_SUPPORT_TYPE)
    sequence.extend(data.get("extra_interior_support_types") or [])
    sequence.append(data["support_type_right"])
    return sequence
