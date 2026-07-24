"""Pattern (skip) live-load envelopes for continuous beams.

IBC 1607.12 / ASCE 7 4.3.3 require floor and roof live loads to be applied
to the spans of a continuous member in the arrangement producing the
maximum effect. Loading every span fully under-predicts both the maximum
positive span moment (mid-span) and the maximum negative support moment
of a continuous beam -- the true maximum of each occurs under a *pattern*
of live load on some subset of spans.

Because the beam is linear-elastic, the envelope of any response
(moment / shear / deflection) at a point is obtained by superposition,
without enumerating the 2**k span patterns: solve the permanent loads
once and each patternable span's transient load once, then at each point
add the per-span transient contributions whose sign matches the effect
being maximized. That is the exact worst-over-all-patterns value, at a
cost of k+1 solves for k patternable regions.

Only floor live ("live") and roof live ("roof_live") loads are patterned
here -- the loads IBC 1607.12 addresses. Dead is permanent; snow and wind
keep their own (non-skip) provisions and are treated as always-on within
their load combination.
"""
from dataclasses import replace

from . import beam as beam_mod
from .loads import PointLoad, UniformLoad

PATTERNABLE_LOAD_TYPES = frozenset({"live", "roof_live"})


def pattern_regions(total_length, support_positions):
    """Loadable regions for patterning as (start_ft, end_ft): each span
    between consecutive supports, plus any cantilever overhang."""
    bounds = sorted({0.0, float(total_length), *(float(s) for s in support_positions)})
    return [(a, b) for a, b in zip(bounds, bounds[1:]) if b - a > 1e-9]


def _loads_in_region(loads, a, b, total_length):
    """The subset of ``loads`` acting within region [a, b], with distributed
    loads clipped to the region."""
    out = []
    for load in loads:
        if isinstance(load, UniformLoad):
            start = float(load.start)
            end = float(total_length if load.end is None else load.end)
            lo, hi = max(start, a), min(end, b)
            if hi - lo > 1e-9:
                out.append(replace(load, start=lo, end=hi))
        elif isinstance(load, PointLoad):
            loc = float(load.location)
            at_member_end = abs(b - total_length) < 1e-9
            if a - 1e-9 <= loc < b - 1e-9 or (at_member_end and loc <= b + 1e-9):
                out.append(load)
        else:
            raise TypeError(f"Unsupported load type: {type(load)!r}")
    return out


def dense_grid(total_length, support_positions, loads, per_region=40):
    """A sampling grid dense enough to capture envelope peaks: all load and
    support discontinuities plus ``per_region`` interior points per interval."""
    marks = {0.0, float(total_length), *(float(s) for s in support_positions)}
    for load in loads:
        if isinstance(load, UniformLoad):
            marks.add(float(load.start))
            marks.add(float(total_length if load.end is None else load.end))
        elif isinstance(load, PointLoad):
            marks.add(float(load.location))
    bounds = sorted(m for m in marks if -1e-9 <= m <= total_length + 1e-9)
    grid = set(bounds)
    for a, b in zip(bounds, bounds[1:]):
        for k in range(1, per_region):
            grid.add(a + (b - a) * k / per_region)
    return sorted(grid)


def _moment_series(total_length, active, support_positions, xs):
    if not active:
        return [0.0] * len(xs)
    reactions = beam_mod._reactions(total_length, active, support_positions=support_positions)
    return [
        beam_mod.moment_at(x, active, total_length=total_length,
                           support_positions=support_positions, reactions=reactions)
        for x in xs
    ]


def _shear_series(total_length, active, support_positions, samples):
    if not active:
        return [0.0] * len(samples)
    reactions = beam_mod._reactions(total_length, active, support_positions=support_positions)
    return [
        beam_mod.shear_at(x, active, total_length=total_length, side=side,
                          support_positions=support_positions, reactions=reactions)
        for x, side in samples
    ]


def _superpose(base, pieces):
    """Given a base series and a list of per-region transient series, return
    the (upper, lower) envelopes: at each sample, add the transient pieces
    with the sign being maximized (upper) or minimized (lower)."""
    upper = [base[i] + sum(p[i] for p in pieces if p[i] > 0.0) for i in range(len(base))]
    lower = [base[i] + sum(p[i] for p in pieces if p[i] < 0.0) for i in range(len(base))]
    return upper, lower


def _region_pieces(total_length, patternable_loads, support_positions, series_fn, samples):
    pieces = []
    for a, b in pattern_regions(total_length, support_positions):
        region_loads = _loads_in_region(patternable_loads, a, b, total_length)
        if region_loads:
            pieces.append(series_fn(region_loads))
    if not pieces:
        pieces.append([0.0] * len(samples))
    return pieces


def moment_envelope(total_length, always_on, patternable, support_positions, xs=None):
    """(xs, upper, lower) moment envelopes (ft-lb, sagging-positive) over a
    dense grid. ``upper`` is the maximum (most positive/sagging) moment and
    ``lower`` the minimum (most negative/hogging) at each x, over all live
    patterns."""
    if xs is None:
        xs = dense_grid(total_length, support_positions, always_on + patternable)
    base = _moment_series(total_length, always_on, support_positions, xs)
    pieces = _region_pieces(
        total_length, patternable, support_positions,
        lambda rl: _moment_series(total_length, rl, support_positions, xs), xs,
    )
    upper, lower = _superpose(base, pieces)
    return xs, upper, lower


def shear_envelope(total_length, always_on, patternable, support_positions, xs=None):
    """(xs, upper, lower) shear envelopes (lb) over a dense grid, evaluating
    both sides of each discontinuity."""
    grid = dense_grid(total_length, support_positions, always_on + patternable) if xs is None else xs
    samples = [(x, side) for x in grid for side in ("minus", "plus")]
    base = _shear_series(total_length, always_on, support_positions, samples)
    pieces = _region_pieces(
        total_length, patternable, support_positions,
        lambda rl: _shear_series(total_length, rl, support_positions, samples), samples,
    )
    upper, lower = _superpose(base, pieces)
    sample_xs = [x for x, _ in samples]
    return sample_xs, upper, lower


class PatternedBeam:
    """Pre-solved elementary load cases for a continuous beam, so every load
    combination's moment/shear/deflection envelope is assembled by
    superposition arithmetic instead of re-solving the FEM system.

    Each *elementary case* is solved once: the whole-member load of each
    non-patternable type (dead, snow, wind) and, for each patternable type
    (live, roof_live), that type's load restricted to each span. A load
    combination's envelope is then the always-on cases summed as a base plus
    the per-span patternable cases superposed by sign -- no further solves.
    """

    def __init__(self, total_length, loads, support_positions, E, I, per_region=64):
        self.total_length = total_length
        self.support_positions = support_positions
        self.xs = dense_grid(total_length, support_positions, loads, per_region)
        self.v_samples = [(x, side) for x in self.xs for side in ("minus", "plus")]
        by_type = {}
        for ld in loads:
            by_type.setdefault(ld.load_type, []).append(ld)
        # key -> {"m", "v", "d", "patternable"}. Patternable types are split
        # per span; everything else is a single whole-member case.
        self.cases = {}
        for load_type, group in by_type.items():
            if load_type in PATTERNABLE_LOAD_TYPES:
                for ri, (a, b) in enumerate(pattern_regions(total_length, support_positions)):
                    region_loads = _loads_in_region(group, a, b, total_length)
                    if region_loads:
                        self.cases[(load_type, ri)] = self._solve_case(region_loads, E, I, patternable=True)
            else:
                self.cases[(load_type,)] = self._solve_case(group, E, I, patternable=False)

    def _solve_case(self, active, E, I, patternable):
        # One FEM solve yields both the reactions (for moment/shear statics)
        # and the deflected shape for this elementary load case.
        reactions, src_xs, src_ys = beam_mod.reactions_and_shape(
            self.total_length, active, E, I, self.support_positions)
        m = [beam_mod.moment_at(x, active, total_length=self.total_length,
                                support_positions=self.support_positions, reactions=reactions) for x in self.xs]
        v = [beam_mod.shear_at(x, active, total_length=self.total_length, side=side,
                               support_positions=self.support_positions, reactions=reactions)
             for x, side in self.v_samples]
        d = [_interp(src_xs, src_ys, x) for x in self.xs]
        return {"m": m, "v": v, "d": d, "patternable": patternable}

    def _assemble(self, load_types, key):
        base = None
        pieces = []
        for cid, case in self.cases.items():
            if cid[0] not in load_types:
                continue
            series = case[key]
            if case["patternable"]:
                pieces.append(series)
            elif base is None:
                base = list(series)
            else:
                base = [base[i] + series[i] for i in range(len(base))]
        if base is None:
            base = [0.0] * len(self.xs if key != "v" else self.v_samples)
        return base, pieces

    def moment_shear_envelope(self, load_types):
        """(xs, m_upper, m_lower, v_upper, v_lower) for a load combination."""
        base_m, m_pieces = self._assemble(load_types, "m")
        base_v, v_pieces = self._assemble(load_types, "v")
        m_upper, m_lower = _superpose(base_m, m_pieces)
        v_upper, v_lower = _superpose(base_v, v_pieces)
        return self.xs, m_upper, m_lower, v_upper, v_lower

    def deflection_envelope(self, load_types):
        """Max downward deflection at each x over all live patterns."""
        base, pieces = self._assemble(load_types, "d")
        return [base[i] + sum(p[i] for p in pieces if p[i] > 0.0) for i in range(len(base))]

    def max_downward_between(self, load_types, x1, x2):
        env = self.deflection_envelope(load_types)
        vals = [env[i] for i, x in enumerate(self.xs) if x1 - 1e-9 <= x <= x2 + 1e-9]
        return max(vals) if vals else 0.0

    def tip_deflection(self, load_types, side):
        if side == "left":
            x_tip = 0.0
            if self.support_positions[0] <= 1e-9:
                return 0.0
        elif side == "right":
            x_tip = float(self.total_length)
            if self.support_positions[-1] >= self.total_length - 1e-9:
                return 0.0
        else:
            raise ValueError(f"side must be 'left' or 'right', got {side!r}")
        ti = min(range(len(self.xs)), key=lambda i: abs(self.xs[i] - x_tip))
        base, pieces = self._assemble(load_types, "d")
        down = base[ti] + sum(p[ti] for p in pieces if p[ti] > 0.0)
        up = base[ti] + sum(p[ti] for p in pieces if p[ti] < 0.0)
        return max(abs(down), abs(up))

    def region_labels(self):
        """Human label for each pattern region (span between supports, or a
        cantilever), in the order pattern_regions() produces them."""
        sup = [round(float(s), 6) for s in self.support_positions]
        pos_to_idx = {s: i for i, s in enumerate(sup)}
        labels = []
        for a, b in pattern_regions(self.total_length, self.support_positions):
            ia = pos_to_idx.get(round(a, 6))
            ib = pos_to_idx.get(round(b, 6))
            if ia is not None and ib is not None:
                labels.append(f"B{ia + 1}-B{ib + 1}")
            elif ia is None:
                labels.append("left cant.")
            else:
                labels.append("right cant.")
        return labels

    def governing_pattern(self, load_types, key, x, positive):
        """Describe the skip-load arrangement that governs `key` ("m" moment
        or "d" deflection) at position `x`: the spans whose live load is on in
        the worst pattern. Empty when the combination has no patternable load
        (e.g. dead+snow governs)."""
        patternable = sorted({cid[1] for cid, c in self.cases.items()
                              if cid[0] in load_types and c["patternable"]})
        if not patternable:
            return ""
        ti = min(range(len(self.xs)), key=lambda i: abs(self.xs[i] - x))
        loaded = []
        for cid, case in self.cases.items():
            if cid[0] not in load_types or not case["patternable"]:
                continue
            val = case[key][ti]
            if (positive and val > 1e-9) or (not positive and val < -1e-9):
                loaded.append(cid[1])
        loaded = sorted(set(loaded))
        if not loaded or set(loaded) == set(patternable):
            return "all spans"
        labels = self.region_labels()
        return ", ".join(labels[i] for i in loaded)


def peak_abs(upper, lower):
    """Largest magnitude across the (upper, lower) envelope arrays."""
    return max(max((abs(u) for u in upper), default=0.0),
               max((abs(v) for v in lower), default=0.0))


def _interp(xs_src, ys_src, xq):
    if xq <= xs_src[0]:
        return ys_src[0]
    if xq >= xs_src[-1]:
        return ys_src[-1]
    lo, hi = 0, len(xs_src) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if xs_src[mid] <= xq:
            lo = mid
        else:
            hi = mid
    x0, x1 = xs_src[lo], xs_src[hi]
    if x1 - x0 < 1e-12:
        return ys_src[lo]
    t = (xq - x0) / (x1 - x0)
    return ys_src[lo] + t * (ys_src[hi] - ys_src[lo])
