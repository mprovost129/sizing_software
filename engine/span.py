"""Span input modes.

A user may give a beam's span three different ways, matching how spans
are typically shown on drawings or measured in the field:

  - out_to_out       -- outside face of left bearing to outside face of
                         right bearing (the overall cut length).
  - inside           -- inside face of left bearing to inside face of
                         right bearing (the clear span).
  - center_to_center -- center of left bearing to center of right
                         bearing.

Structural analysis always runs on the clear (inside-to-inside) span --
per project convention, matching how most residential span tables
define "span" -- regardless of which mode the user entered it in. The
other two modes are converted to clear span here using the bearing
lengths at each support before the beam is analyzed.
"""
from typing import Literal

SpanMode = Literal["out_to_out", "inside", "center_to_center"]

SPAN_MODE_LABELS: dict[str, str] = {
    "out_to_out": "Out to out (outside face of bearing to outside face of bearing)",
    "inside": "Inside span (inside face of bearing to inside face of bearing)",
    "center_to_center": "Center to center of bearing",
}


def clear_span(
    given_span_ft: float,
    span_mode: SpanMode,
    bearing_length_left_in: float,
    bearing_length_right_in: float,
) -> float:
    """Convert a span given in `span_mode` to the clear (inside-to-inside)
    span used for structural analysis, in feet."""
    if span_mode == "out_to_out":
        reduction_in = bearing_length_left_in + bearing_length_right_in
    elif span_mode == "center_to_center":
        reduction_in = (bearing_length_left_in + bearing_length_right_in) / 2
    elif span_mode == "inside":
        reduction_in = 0.0
    else:
        raise ValueError(f"Unknown span mode: {span_mode!r}")

    result = given_span_ft - reduction_in / 12
    if result <= 0:
        raise ValueError(
            f"Clear span must be positive; got {result:.3f} ft after "
            f"subtracting bearing lengths from the given {span_mode} span "
            f"of {given_span_ft:.3f} ft.",
        )
    return result
