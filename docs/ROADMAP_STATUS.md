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
