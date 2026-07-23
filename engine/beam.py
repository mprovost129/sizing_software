"""Beam analysis with two or more supports.

The legacy public API is preserved for the single-span case:

- ``analyze(total_length, loads, a1=0, a2=None)``
- ``back_span_deflection(...)``
- ``tip_deflection(...)``

Internally, those now sit on top of a generalized continuous-beam
solver that can handle any number of simple supports along the member.
That gives us a real path to multi-span checks without abandoning the
existing overhang implementation.
"""
from dataclasses import dataclass

from .loads import PointLoad, UniformLoad


def _normalize_support_positions(total_length, a1=0.0, a2=None, support_positions=None):
    if support_positions is None:
        if a2 is None:
            a2 = total_length
        support_positions = [a1, a2]
    ordered = sorted(float(x) for x in support_positions)
    if len(ordered) < 2:
        raise ValueError("At least two supports are required.")
    if ordered[0] < -1e-9 or ordered[-1] > total_length + 1e-9:
        raise ValueError("Support positions must lie within the member length.")
    for left, right in zip(ordered, ordered[1:]):
        if right - left <= 1e-9:
            raise ValueError("Support positions must be strictly increasing.")
    return ordered


def _uniform_load_bounds(load, total_length):
    start = float(load.start)
    end = float(total_length if load.end is None else load.end)
    if start > total_length + 1e-9 or end > total_length + 1e-9:
        raise ValueError("Distributed load extents must lie within the member length.")
    return start, end


def _uniform_load_intensity_at(loads, x, total_length):
    total = 0.0
    for load in loads:
        if isinstance(load, UniformLoad):
            start, end = _uniform_load_bounds(load, total_length)
            if start - 1e-9 <= x <= end + 1e-9:
                total += load.w
        elif not isinstance(load, PointLoad):
            raise TypeError(f"Unsupported load type: {type(load)!r}")
    return total


# A single cubic (Hermite) beam element gives EXACT nodal displacements
# and member forces, but its interpolated deflection BETWEEN nodes is
# wrong under distributed load -- exactly 0.8x the true value at the
# midspan of a UDL simple span, and worse at cantilever tips. Fixing
# that requires meshing each segment (the span between consecutive
# supports / point loads / member ends) into several elements so the
# piecewise-cubic shape converges to the true quartic deflected shape.
# 16 elements/segment converges deflection to well under 0.01%; reactions
# and moments are unaffected (already exact at any mesh density).
ELEMENTS_PER_SEGMENT = 16


def _analysis_nodes(total_length, loads, support_positions):
    breakpoints = {0.0, float(total_length), *support_positions}
    for load in loads:
        if isinstance(load, PointLoad):
            breakpoints.add(float(load.location))
        elif isinstance(load, UniformLoad):
            start, end = _uniform_load_bounds(load, total_length)
            breakpoints.update((start, end))
    ordered = sorted(breakpoints)
    nodes = set(ordered)
    for left, right in zip(ordered, ordered[1:]):
        for k in range(1, ELEMENTS_PER_SEGMENT):
            nodes.add(left + (right - left) * k / ELEMENTS_PER_SEGMENT)
    return sorted(nodes)


def _solve_linear_system(A, b):
    n = len(A)
    if n == 0:
        return []
    aug = [row[:] + [rhs] for row, rhs in zip(A, b)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-12:
            raise ValueError("Beam stiffness matrix is singular for the given support layout.")
        if pivot != col:
            aug[col], aug[pivot] = aug[pivot], aug[col]
        pivot_val = aug[col][col]
        for j in range(col, n + 1):
            aug[col][j] /= pivot_val
        for row in range(n):
            if row == col:
                continue
            factor = aug[row][col]
            if abs(factor) < 1e-12:
                continue
            for j in range(col, n + 1):
                aug[row][j] -= factor * aug[col][j]
    return [aug[i][n] for i in range(n)]


def _solve_support_reactions(total_length, loads, support_positions, E=1.0, I=1.0):
    """Continuous-beam solver via Euler-Bernoulli beam stiffness."""
    node_positions_ft = _analysis_nodes(total_length, loads, support_positions)
    node_positions_in = [x * 12 for x in node_positions_ft]
    node_index = {x: i for i, x in enumerate(node_positions_ft)}
    n_nodes = len(node_positions_ft)
    n_dof = n_nodes * 2

    K = [[0.0 for _ in range(n_dof)] for _ in range(n_dof)]
    F = [0.0 for _ in range(n_dof)]
    for i in range(n_nodes - 1):
        L = node_positions_in[i + 1] - node_positions_in[i]
        element_midpoint_ft = (node_positions_ft[i] + node_positions_ft[i + 1]) / 2
        total_uniform_w = _uniform_load_intensity_at(loads, element_midpoint_ft, total_length) / 12.0
        k = [
            [12 * E * I / L ** 3, 6 * E * I / L ** 2, -12 * E * I / L ** 3, 6 * E * I / L ** 2],
            [6 * E * I / L ** 2, 4 * E * I / L, -6 * E * I / L ** 2, 2 * E * I / L],
            [-12 * E * I / L ** 3, -6 * E * I / L ** 2, 12 * E * I / L ** 3, -6 * E * I / L ** 2],
            [6 * E * I / L ** 2, 2 * E * I / L, -6 * E * I / L ** 2, 4 * E * I / L],
        ]
        feq = [
            -total_uniform_w * L / 2,
            -total_uniform_w * L ** 2 / 12,
            -total_uniform_w * L / 2,
            total_uniform_w * L ** 2 / 12,
        ]
        dofs = [2 * i, 2 * i + 1, 2 * (i + 1), 2 * (i + 1) + 1]
        for r in range(4):
            F[dofs[r]] += feq[r]
            for c in range(4):
                K[dofs[r]][dofs[c]] += k[r][c]

    for load in loads:
        if isinstance(load, PointLoad):
            idx = node_index.get(float(load.location))
            if idx is None:
                raise ValueError("Point load location must align with an analysis node.")
            F[2 * idx] += -load.p

    constrained = sorted(2 * node_index[x] for x in support_positions)
    free = [i for i in range(n_dof) if i not in constrained]
    d = [0.0 for _ in range(n_dof)]
    if free:
        Kff = [[K[r][c] for c in free] for r in free]
        Ff = [F[r] for r in free]
        df = _solve_linear_system(Kff, Ff)
        for dof, value in zip(free, df):
            d[dof] = value

    reactions_by_dof = []
    for dof in constrained:
        total = sum(K[dof][j] * d[j] for j in range(n_dof)) - F[dof]
        reactions_by_dof.append(total)

    support_reactions = {pos: reactions_by_dof[i] for i, pos in enumerate(support_positions)}
    return {
        "node_positions_ft": node_positions_ft,
        "node_positions_in": node_positions_in,
        "displacements": d,
        "support_reactions": support_reactions,
        "support_positions": support_positions,
    }


def _reactions(total_length, loads, a1=0.0, a2=None, support_positions=None):
    supports = _normalize_support_positions(total_length, a1=a1, a2=a2, support_positions=support_positions)
    solved = _solve_support_reactions(total_length, loads, supports)
    return [solved["support_reactions"][x] for x in supports]


def shear_at(x, loads, a1=0.0, a2=None, total_length=None, side="plus",
             support_positions=None, reactions=None):
    """Shear at x with one-sided evaluation at discontinuities.

    `reactions` may be passed in to avoid re-solving the (potentially
    expensive) continuous-beam system on every query -- reactions do not
    depend on x, so callers looping over many x values should solve once
    and pass the result here. When omitted, they are solved on demand.
    """
    if total_length is None:
        total_length = a2
    supports = _normalize_support_positions(total_length, a1=a1, a2=a2, support_positions=support_positions)
    cmp = (lambda p, q: p >= q) if side == "plus" else (lambda p, q: p > q)
    if reactions is None:
        reactions = _reactions(total_length, loads, support_positions=supports)
    v = 0.0
    for support_x, reaction in zip(supports, reactions):
        if cmp(x, support_x):
            v += reaction
    for load in loads:
        if isinstance(load, UniformLoad):
            start, end = _uniform_load_bounds(load, total_length)
            loaded_length = max(0.0, min(x, end) - start)
            v -= load.w * loaded_length
        elif isinstance(load, PointLoad):
            if cmp(x, load.location):
                v -= load.p
    return v


def moment_at(x, loads, a1=0.0, a2=None, total_length=None, support_positions=None, reactions=None):
    if total_length is None:
        total_length = a2
    supports = _normalize_support_positions(total_length, a1=a1, a2=a2, support_positions=support_positions)
    if reactions is None:
        reactions = _reactions(total_length, loads, support_positions=supports)
    m = 0.0
    for support_x, reaction in zip(supports, reactions):
        if x >= support_x:
            m += reaction * (x - support_x)
    for load in loads:
        if isinstance(load, UniformLoad):
            start, end = _uniform_load_bounds(load, total_length)
            loaded_length = max(0.0, min(x, end) - start)
            if loaded_length:
                centroid = start + loaded_length / 2
                m -= load.w * loaded_length * (x - centroid)
        elif isinstance(load, PointLoad):
            if x > load.location:
                m -= load.p * (x - load.location)
    return m


def _critical_x_values(support_positions, total_length, loads, n_samples=300):
    xs = {0.0, total_length, *support_positions}
    for load in loads:
        if isinstance(load, PointLoad):
            xs.add(load.location)
        elif isinstance(load, UniformLoad):
            start, end = _uniform_load_bounds(load, total_length)
            xs.update((start, end))
    for i in range(n_samples + 1):
        xs.add(total_length * i / n_samples)
    return sorted(xs)


@dataclass
class BeamResults:
    total_length: float
    support_positions: list[float]
    reactions: list[float]
    v_max: float
    v_max_x: float
    m_max: float
    m_max_x: float

    @property
    def a1(self):
        return self.support_positions[0]

    @property
    def a2(self):
        return self.support_positions[1]

    @property
    def r1(self):
        return self.reactions[0]

    @property
    def r2(self):
        return self.reactions[1]


def analyze(total_length, loads, a1=0.0, a2=None, support_positions=None) -> BeamResults:
    supports = _normalize_support_positions(total_length, a1=a1, a2=a2, support_positions=support_positions)
    reactions = _reactions(total_length, loads, support_positions=supports)
    v_max = v_max_x = m_max = m_max_x = 0.0
    for x in _critical_x_values(supports, total_length, loads):
        for side in ("minus", "plus"):
            v = shear_at(x, loads, total_length=total_length, side=side,
                         support_positions=supports, reactions=reactions)
            if abs(v) > abs(v_max):
                v_max, v_max_x = v, x
        m = moment_at(x, loads, total_length=total_length, support_positions=supports, reactions=reactions)
        if abs(m) > abs(m_max):
            m_max, m_max_x = m, x
    return BeamResults(
        total_length=total_length,
        support_positions=supports,
        reactions=reactions,
        v_max=v_max,
        v_max_x=v_max_x,
        m_max=m_max,
        m_max_x=m_max_x,
    )


def _shape_from_solved(solved, samples_per_element=24):
    """Reconstruct the sampled deflected shape (xs_ft, ys_in, downward-
    positive) from an already-solved FEM system -- the Hermite cubic
    interpolation between nodes. Split out so a single solve can yield both
    the reactions and the shape."""
    xs_ft = []
    ys_in = []
    node_positions_ft = solved["node_positions_ft"]
    node_positions_in = solved["node_positions_in"]
    d = solved["displacements"]

    for i in range(len(node_positions_ft) - 1):
        x1_ft = node_positions_ft[i]
        x2_ft = node_positions_ft[i + 1]
        L = node_positions_in[i + 1] - node_positions_in[i]
        v1 = d[2 * i]
        th1 = d[2 * i + 1]
        v2 = d[2 * (i + 1)]
        th2 = d[2 * (i + 1) + 1]
        start_j = 0 if i == 0 else 1
        for j in range(start_j, samples_per_element + 1):
            xi_ft = x1_ft + (x2_ft - x1_ft) * j / samples_per_element
            xi_in = (xi_ft - x1_ft) * 12
            r = xi_in / L
            n1 = 1 - 3 * r ** 2 + 2 * r ** 3
            n2 = xi_in * (1 - 2 * r + r ** 2)
            n3 = 3 * r ** 2 - 2 * r ** 3
            n4 = xi_in * (r ** 2 - r)
            upward_in = n1 * v1 + n2 * th1 + n3 * v2 + n4 * th2
            xs_ft.append(xi_ft)
            ys_in.append(-upward_in)
    return xs_ft, ys_in


def _deflection_shape(total_length, loads, E, I, a1=0.0, a2=None, support_positions=None, samples_per_element=24):
    supports = _normalize_support_positions(total_length, a1=a1, a2=a2, support_positions=support_positions)
    solved = _solve_support_reactions(total_length, loads, supports, E=E, I=I)
    return _shape_from_solved(solved, samples_per_element)


def deflection_shape(total_length, loads, E, I, support_positions):
    """Public accessor for the full sampled deflected shape: parallel
    lists (xs_ft, ys_in), downward-positive. Solves the FEM system once."""
    return _deflection_shape(total_length, loads, E, I, support_positions=support_positions)


def reactions_and_shape(total_length, loads, E, I, support_positions):
    """One FEM solve returning BOTH the support reactions (list, in support
    order) and the sampled deflected shape (xs_ft, ys_in, downward-positive).
    Lets continuous-beam pattern analysis get statics and deflection from a
    single solve per load case."""
    supports = _normalize_support_positions(total_length, support_positions=support_positions)
    solved = _solve_support_reactions(total_length, loads, supports, E=E, I=I)
    reactions = [solved["support_reactions"][x] for x in supports]
    xs_ft, ys_in = _shape_from_solved(solved)
    return reactions, xs_ft, ys_in


def max_deflection_between(total_length, loads, E, I, x1, x2, support_positions):
    xs, ys = _deflection_shape(total_length, loads, E, I, support_positions=support_positions)
    candidates = [y for x, y in zip(xs, ys) if x1 - 1e-9 <= x <= x2 + 1e-9]
    return max(candidates) if candidates else 0.0


def deflection_at(total_length, loads, E, I, x, support_positions):
    xs, ys = _deflection_shape(total_length, loads, E, I, support_positions=support_positions)
    closest_i = min(range(len(xs)), key=lambda i: abs(xs[i] - x))
    return ys[closest_i]


def back_span_deflection(total_length, loads, E, I, a1=0.0, a2=None):
    """Maximum downward deflection (in) between the first two supports."""
    if a2 is None:
        a2 = total_length
    return max_deflection_between(total_length, loads, E, I, a1, a2, [a1, a2])


def tip_deflection(total_length, loads, E, I, a1=0.0, a2=None, side="left", support_positions=None):
    """Deflection (in, absolute value) at the tip of the left or right overhang."""
    if support_positions is None:
        if a2 is None:
            a2 = total_length
        supports = [a1, a2]
    else:
        supports = _normalize_support_positions(total_length, a1=a1, a2=a2, support_positions=support_positions)
    if side == "left":
        if supports[0] <= 1e-9:
            return 0.0
        return abs(deflection_at(total_length, loads, E, I, 0.0, supports))
    if side == "right":
        if supports[-1] >= total_length - 1e-9:
            return 0.0
        return abs(deflection_at(total_length, loads, E, I, total_length, supports))
    raise ValueError(f"side must be 'left' or 'right', got {side!r}")
