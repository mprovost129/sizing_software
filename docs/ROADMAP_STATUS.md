# Roadmap Status

Updated: 2026-07-19

This file is a working checkpoint against `docs/Structural_Design_Software_Roadmap.docx` and `docs/Structural_Design_Platform_Master_Plan.docx`, so current progress is visible without opening the Word docs.

## Current Position

The project is in Phase 2: a form-based member designer built on top of the Phase 1 calculation engine.

Completed in the live app:

- Single-span SPF No. 2 sizing with bending, shear, bearing, reactions, live-load deflection, and total-load deflection
- Uniform dead/live/snow loads plus point loads
- Span input modes: clear, out-to-out, and center-to-center
- Per-support bearing lengths and left/right support type selection
- Size scan for the most economical passing nominal section
- Saved designs, detail pages, CSV export, and PDF export
- Single-span left/right cantilevers (overhangs) with verified reactions, shear, moment, back-span and cantilever deflection checks, and explicit net-uplift failure reporting
- Material picker expanded beyond SPF No. 2 to a sawn-lumber library of SPF, Douglas Fir-Larch, and Hem-Fir grades within the current dimension-lumber workflow
- Southern Pine added (Select Structural / No.1 / No.2): unlike the CF-scaled species, SP uses NDS-S Table 4B size-specific Fb tabulated per nominal size with CF = 1.0, and is otherwise a normal sawn material (Cr, CM, CL, and the sawn size set all apply); representative Table 4B values flagged for cross-check
- Solid post / timber sizes: 4x4 and 4x6 dimension-lumber sizes (existing species, correct size factors) plus a Posts & Timbers "timber" material category (Douglas Fir-Larch SS/No.1/No.2, NDS-S Table 4D) with sizes 6x6/6x8/8x8. Timbers take their own lower reference values, no Cr, CF = 1.0, dry service, and are monolithic (no ply multiplier); they flow through both the beam and column designers with the 4-category size picker (sawn / LVL / glulam / timber). Representative Table 4D values flagged for cross-check
- Built-up (multi-ply) members of 1-4 plies: section properties scale with ply count, the repetitive-member factor Cr is correctly suppressed for built-up members, and the ply count flows through the designer, saved designs, detail/list/project views, and CSV/PDF exports (labeled e.g. "3-ply 2x10")
- Beam stability factor CL (NDS 3.3.3, lateral-torsional buckling): an optional unbraced-compression-edge length reduces bending capacity for members whose top edge is not continuously braced; the default is continuously braced (CL = 1.0), the slenderness ratio RB is reported, RB > 50 is flagged as a loud failure, and CL/RB flow through the designer, detail, and CSV/PDF exports
- Wet service factor CM (NDS-S Table 4A): a Dry/Wet service-condition selector applies the wet-service reductions (Fb x 0.85 when Fb.CF > 1150 psi else 1.0, Fv x 0.97, Fc-perp x 0.67, E/Emin x 0.90) to bending, shear, bearing, deflection, and beam-stability checks for exterior/damp members; the default is Dry (CM = 1.0), and the CM factors flow through the designer, detail, and CSV/PDF exports
- LVL (laminated veneer lumber) as an engineered material category: generic E-graded grades (1.55E through 2.1E, named by MoE) using the volume/depth factor CV = (12/d)^0.136 in place of CF, with Cr suppressed, dry-service only, and 1.75"-wide laminations (the ply control sets built-up width). LVL depths (7-1/4" through 18") are selectable, the size picker filters to match the material category, wet+LVL and material/size mismatches are blocked, and it flows through run/scan/save/detail/CSV/PDF
- Glulam (glued-laminated timber) as an engineered material category: generic NDS Table 5A stress classes (20F-1.5E through 30F-2.1E, balanced layups) using the NDS 5.3.6 volume factor CV = (21/L)^0.1 (12/d)^0.1 (5.125/b)^0.1 applied as the LESSER of CV and CL (never both), with Cr suppressed and dry-service only. Glulam is a monolithic width x depth section (the ply control is hidden), standard sizes 3-1/2x9" through 6-3/4x21" are selectable, the size picker filters by category, wet+glulam and material/size mismatches are blocked, and it flows through run/scan/save/detail/CSV/PDF
- Result-panel loading diagram updated to draw true beam geometry with support offsets and overhang dimensions
- Loading diagrams now draw distributed zones across their true extents and concentrated-load arrows at their actual member coordinates, including coincident load aggregation
- The unsaved member preview now redraws full-length, partial distributed, and point loads directly from load-row edits before analysis is submitted
- Point and distributed load schedules now include per-row duplicate/remove controls and section-level clear-all actions, with capacity-aware controls and immediate preview refresh
- Saved designs can be reopened as ownership-checked working copies with all spans, supports, bearings, settings, baseline loads, point loads, and distributed zones prepopulated while preserving the original record
- User-owned named load templates can save, update, apply, and delete complete baseline/point/distributed load schedules directly from the Loads tab without submitting the beam
- Settings tab with user-editable back-span and cantilever deflection criteria, persisted on saved designs and reflected in exports
- Loads tab expansion with psf/plf input basis, on-center spacing conversion, standard load components (D, L, S, Lr, W), and member-type default load presets
- Loads tab now supports expandable point-load entry rows instead of a fixed three-row stub, so designers can surface additional concentrated loads on demand without cluttering the default form
- Partial-length distributed load zones are supported end to end, including additive D/L/S/Lr/W rows, psf-to-plf normalization, exact engine breakpoints, saved-design recomputation, and CSV/PDF load schedules
- Multi-span engine groundwork: continuous-beam analysis core added at the engine level with benchmark coverage for equal-span two-span behavior
- First-pass continuous workflow surfaced in the designer for 2-span through 10-span members, including end overhangs, interior supports, interior bearing checks, span-by-span deflection checks, cantilever tip checks, and multi-support result rendering
- Saved designs can now be grouped under optional project containers so jobs can be organized by customer/address/project instead of a flat list
- Projects now have ownership-scoped create/edit/detail pages, client/address/notes context, pass/fail design summaries, preselected new-design links, and project-level CSV exports
- The saved-design workspace now includes project/design search, pass/fail filtering, empty-project discovery, and CSV exports that preserve the active result set
- Projects can export a single paginated PDF calculation package with a project cover sheet, pass/fail member index, project notes, and every member's complete calculation report
- Projects now carry lifecycle status and optional job numbers, while designs support immutable linked revisions with notes, current-version filtering, and directly accessible version history
- Selective project issues now snapshot exact member revisions into reproducible PDF packages, retain issue labels/notes/creator/timestamps, preserve package order, and protect issued revisions from deletion
- Result details now include true shear, moment, and deflection diagrams rather than only the loading sketch
- PDF export now includes project context, full load schedules, point loads, support/geometry schedules, and embedded analysis diagrams for a more report-like calculation package
- Settings tab now includes serviceability presets and floor-subfloor performance tuning that tighten recommended deflection limits without assuming composite action
- Column / post designer (NEW member type): a dedicated page checks axial compression per NDS 3.7 (fc = P/A vs F'c = Fc x CD x CF x CP), with the column stability factor CP, per-axis slenderness le/d and le/b (each with its own unbraced length and the end-condition factor Ke), governing load-combination selection, a loud le/d > 50 failure, and c = 0.8 sawn / 0.9 engineered. It reuses the full material library (sawn incl. Southern Pine, LVL, glulam) and built-up plies; dry-service, concentric-load MVP
- Column designs are saved, recomputed from stored inputs, and reach beam-style parity: a ColumnDesign model with an optional project link, a saved-columns list on the designer, a detail page (recompute + delete), a PDF calculation report, and a Columns section on the project page
- The project calculation package now spans both member types: the project PDF cover sheet counts and indexes columns and appends a full axial-compression report per column, and the project CSV export gains a Columns section (slenderness, CP, governing ratio). Issue snapshot packages remain beams-only. (Standalone column revisions/issues remain a follow-up.)
- Beam-columns (combined axial + bending, NDS 3.9.2): the column designer accepts an optional lateral load producing strong-axis bending (M = w*H^2/8), and evaluates the interaction (fc/Fc')^2 + fb/[Fb'(1 - fc/FcE1)] <= 1.0 per load combination with the P-delta amplification, reporting axial, bending, and combined interaction checks separately. FcE1 is the Euler stress in the plane of bending; the compression edge is braced by default (CL = 1.0) or takes an unbraced length. Beam-columns save, recompute, show a detail page, export a PDF, and appear in the project package -- full parity with pure columns
- End-notch shear reduction (NDS 3.4.3.2): the beam designer takes an optional tension-side end-notch depth; the remaining depth dn reduces the shear capacity by (dn/d)^2 (equivalently the notch magnifies the shear stress by (d/dn)^2 at the re-entrant corner), evaluated at the maximum-shear section, with a through-notch failing loudly. The notch flows through run/save/detail/CSV/PDF via the shear-check label and a detail summary row
- Round-hole net-section shear check: an optional hole diameter (and location) adds a shear check on the reduced depth dn = d - hole at the hole, using the actual shear at that location (so holes in low-shear zones near midspan are not over-penalized); blank location uses the maximum-shear section. A simplified rational check (not manufacturer hole charts), it flows through run/save/detail/CSV/PDF as an extra check plus a detail row
- Long-term deflection creep factor Kcr (NDS 3.5.2): an optional Settings-tab selector (None / 1.5 seasoned-dry / 2.0 unseasoned-or-wet) amplifies the sustained (dead-load) portion of the total-deflection check for long-term creep; the live/transient check is unaffected. Default is immediate-only (Kcr = 1.0), so existing designs are unchanged; when set, the total-deflection check is labelled "long-term, Kcr=..." across run/save/detail/CSV/PDF
- Connection designer (NEW): a dedicated page computes the single-shear lateral design value Z of a dowel-type fastener (bolt, lag, nail, screw) per NDS Chapter 12 -- the minimum of the six yield-limit modes, with dowel bearing strengths derived from the connected members' specific gravities (the G values in the material library), the Rd reduction term, and load duration CD. It reports Z, the governing mode, all six mode values, Z', the total capacity for n fasteners, and demand/capacity for an applied load. The optional group-action factor Cg (NDS 11.3-1, from the row count, spacing, and member E*A) and geometry factor CDelta (NDS 12.5.1, from end distance and spacing vs. the diameter-based minimums, with a not-permitted failure) now feed Z' = Z x CD x Cg x CDelta. A single/double-shear selector switches between the two- and three-member yield-limit sets (double shear uses the four Im/Is/IIIs/IV modes with the two-shear-plane factors, ~2x the single-shear capacity, and combines both side members' stiffness for Cg). Wet CM, temperature, and edge distance are follow-ups
- Connection designs are saved, recomputed from stored inputs, and reach beam/column-style parity: a ConnectionDesign model with an optional project link, a saved-connections list on the designer, a detail page (recompute + delete), a PDF report, a Connections section on the project page, and inclusion in the project PDF/CSV package
- Withdrawal (axial) design (NDS 12.2): a Loading selector on the connection designer switches between lateral (shear) and withdrawal. In withdrawal mode it computes the reference withdrawal design value W per inch of penetration from the holding member's specific gravity and the fastener diameter -- nails 1380*G^2.5*D, wood screws 2850*G^2*D, lag screws 1800*G^1.5*D^0.75 -- then W' = W x penetration x CD per fastener and the total capacity for n fasteners, with demand/capacity for an applied uplift load. Bolts report "not designed for withdrawal." The lateral-only inputs (shear planes, Fyb, side member, load-to-grain, Cg/CDelta) hide in withdrawal mode. Withdrawal flows through run/save/detail/PDF and the project PDF/CSV package alongside lateral connections. Toe-nail Ctn is a follow-up
- Connection wet service factor CM (NDS Table 11.3.3): a Dry/Wet service-condition selector on the connection designer reduces capacity for members that are wet in service (MC > 19%). Laterally loaded dowels take CM = 0.7; withdrawal takes CM = 0.25 for nails/spikes and 0.7 for lag/wood screws (this is a different table from the beam NDS-S Table 4A CM). Default Dry (CM = 1.0) leaves existing designs unchanged. It applies to both lateral (Z' = Z x CD x CM x Ctn x Cg x CDelta) and withdrawal (W' = W x pen x CD x CM x Ctn), and flows through run/save/detail/PDF/CSV, shown only when it governs
- Connection toe-nail factor Ctn (NDS 12.5.4): a "Toe-nailed" checkbox reduces capacity for nails or spikes driven at an angle to the grain -- Ctn = 0.83 laterally, 0.67 in withdrawal. It applies only to nails/spikes (a bolt/lag/screw marked toe-nailed keeps Ctn = 1.0) and stacks multiplicatively with CD/CM/Cg/CDelta. Default off (Ctn = 1.0). Flows through run/save/detail/PDF, shown only when it governs
- Connection temperature factor Ct (NDS Table 11.3.4): a service-temperature selector (Normal T <= 100F / 100-125F / 125-150F) reduces capacity for fasteners at sustained elevated temperatures. Ct = 1.0 normal; 0.8 dry / 0.7 wet at 100-125F; 0.7 dry / 0.5 wet at 125-150F (it reads the wet/dry from the same service-condition selector, so it stacks with CM). Applies to both lateral and withdrawal, default Normal (Ct = 1.0), flows through run/save/detail/PDF, shown only when it governs. This completes the environmental adjustment set (CD, CM, Ct, Ctn, Cg, CDelta)
- Connection edge-distance check (NDS Table 12.5.1A): an optional edge-distance input (in the geometry section) is checked against the minimum for larger dowels (D >= 0.25 in) -- 1.5D parallel/unloaded, or 4D toward a loaded perpendicular-to-grain edge. Below the minimum the connection is flagged "not permitted" (fails even when the yield-limit ratio alone would pass), with a loud warning banner; adequate edge distance is noted as such. Nails/screws (D < 0.25) are not tabulated (governed by splitting) and are not checked. It is a geometric adequacy check (pass/fail), not a strength factor, and flows through run/save/detail/PDF
- Steel side plates (NDS 12.3.3): the side member can now be a steel plate instead of a wood species. A side-member-type selector switches between Wood and Steel plate; for steel the dowel bearing strength Fe = 1.5*Fu is used directly in the yield-limit equations (ASTM A36 Fe = 87,000 psi, ASTM A572 Gr.50 / A992 Fe = 97,500 psi) with the plate thickness as the side bearing length, and steel's E = 29,000,000 psi feeds the group-action Cg. Single or double shear (one or two plates). A thin steel plate correctly outperforms a same-thickness wood side member (which would crush). The result notes that the plate itself must still be checked per AISC (net section, bearing, block shear) -- that is out of scope here. Flows through run/save/detail/PDF. This is the last major dowel-connection item; the connection designer now covers yield-limit Z, withdrawal W, the full environmental factors (CM, Ct, Ctn), Cg/CDelta, edge distance, and steel side plates

## What Is Next

The roadmap's near-term priorities still make sense, with one adjustment: single-span cantilevers are now complete, so the next major structural-analysis step is multi-span rather than overhang support.

Recommended next build order:

1. Multi-span engine
   Expand beyond the current first-pass 10-span workflow to more spans and richer continuous-member cases.
2. Loads tab expansion
   Continue refining saved-design workflows with project-level template sharing and selective load-template organization.
3. Project-container expansion
   Add issue supersession/status controls and optional transmittal metadata for formal package workflows.
4. Engineering-report expansion
   Keep growing the current PDF package with firm branding, cover sheets, assumptions, and later sealed-report style structure if needed.
5. Settings-tab expansion
   Keep growing serviceability controls with later options such as vibration guidance, finish-sensitive presets, or richer member-specific tuning.

## Known Gaps

These are intentionally not covered yet:

- Multi-span continuous members beyond the current first-pass 10-span workflow
- Fixed or moment connections
- Masonry-specific bearing minimums
- Hold-down hardware sizing for uplift cases
- Full graphical editor / object-based modeling
