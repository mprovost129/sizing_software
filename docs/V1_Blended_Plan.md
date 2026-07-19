# Sizing Software — Blended V1.0 Plan

Updated: 2026-07-18

This document blends three sources into one plan:

- **`Sizing Software.docx`** — the concrete V1.0 MVP UI/functional spec ("how it should look and function").
- **`Structural_Design_Software_Roadmap.docx`** — phased roadmap + BC Calc-informed functional spec + near-term priorities.
- **`Structural_Design_Platform_Master_Plan.docx`** — the long-term vision and guiding philosophy.

It supersedes `ROADMAP_STATUS.md` as the single planning + status reference (that file is folded in below).

---

## 1. Vision & philosophy (from the master plan)

Build the **"Fusion 360 for residential structural engineering"** — an integrated environment that grows module by module on top of one trustworthy calculation engine. Core principles carried into V1.0:

- **Engine first, UI second.** The calc engine stays independent of the interface (already true: `engine/` has no Django dependency).
- **BC Calc is the functional reference** — match how it *works*, not how it looks. The new doc is our concrete BC Calc-shaped V1.0 target.
- **Accuracy, transparency, verifiability.** Every check explainable and traceable; every release validated against hand-calculated benchmarks.

## 2. What V1.0 is (from the new doc)

A **single-member structural designer** with a BC Calc-style workspace:

```
Navbar (projects · settings · material library · resources · search · profile)
└─ Dashboard
   ├─ Project toolbar (New / Open / Save / Save As / Info / Settings)
   ├─ Member-type toolbar (Joist / Beam / Rafter / Roof Beam / Hip Beam / Column)
   ├─ Member Viewer  ── right-click context menus on member / bearing / load / reaction
   ├─ Member Design Window ── tabs: Span · Settings · Loads · Products · Holes · Notch/Bevel · Connections · Notes
   └─ Member Analysis Window (live control-check pane, right side)
```

One member design = one analysis; a project is a folder of analyses. An explicit run populates the analysis pane with named control checks and utilization %.

---

## 3. V1.0 feature spec vs. current build

Legend: ✅ built · 🟡 partial · ⬜ not started. "Engine" flags items needing calculation-engine work (not just UI).

### 3.1 Application shell / navbar
| V1.0 feature | Status | Notes |
|---|---|---|
| Brand (logo/name) | ✅ | "FrameCalc" brand + nav |
| Projects dropdown (Create New, Project Library) | 🟡 | `BeamProject` model + grouped designs list; no dropdown menu or dedicated project pages |
| Settings dropdown (Company info, App defaults, Material Library) | ⬜ | none yet |
| Resources (Help, Building Code Resources, ToS, Contact) | 🟡 | Guide page exists; others ⬜ |
| Search bar (whole-app search) | ⬜ | |
| Notifications | ⬜ | |
| Profile / Subscription / Log out | 🟡 | Logout ✅ (POST); profile & subscription ⬜ |

### 3.2 Dashboard toolbars
| V1.0 feature | Status | Notes |
|---|---|---|
| Project toolbar: New / Save | 🟡 | Save + save-into-project ✅; New = new blank design |
| Project toolbar: Open / Save As / Project Info / Project Settings | ⬜ | no open-project window, save-as, or per-project default settings |
| Member-type toolbar: Joist / Beam / Rafter | 🟡 | present as **deflection-limit presets on one beam engine**; SVG icons wired (i-joist, beam, rafter) |
| Member-type toolbar: Roof Beam / Hip Beam | ⬜ **Engine** | sloped-member geometry not modeled |
| Member-type toolbar: Column | ⬜ **Engine** | needs an axial/buckling engine — fundamentally different from bending |

### 3.3 Member Viewer
| V1.0 feature | Status | Notes |
|---|---|---|
| Beam elevation with supports, dims, overhangs | ✅ | live geometry preview + result loading diagram; beam depth now scales with member size |
| Beam / bearing artwork as separate swappable layers | 🟡 | `beam_viewer.svg` wired as the beam layer; bearing SVGs still JS-drawn (user is drawing them) |
| Right-click menus (member / bearing / load / reaction) | ⬜ | select product, add loads, edit member, bearing properties, edit/copy/delete load |
| Copy reaction → paste onto another member (linked supports) | ⬜ | flagged "future feature" in the doc too |
| Member edit mode / add hole in viewer | ⬜ | doc marks these future |

### 3.4 Design tab — Span
| V1.0 feature | Status | Notes |
|---|---|---|
| Number of spans (+/−) | ✅ | 1–10 spans |
| Span type: Out-to-out / Clear / Center-to-center | ✅ | (our default is Clear; doc default is Out-to-out — trivial default change) |
| Cantilever on end spans | ✅ | left/right overhangs with tip checks |
| Per-support label (B1, B2, …), editable | 🟡 | auto labels ✅; manual rename ⬜ |
| Support type: Wall/Plate, Beam (dropped), Column, Hanger | 🟡 | wall_plate / column / hanger ✅; "dropped beam" support ⬜ |
| Enable Bearing Analysis toggle | ⬜ | we always run bearing; make it toggleable |
| Support **material** dropdown (Steel, DF, SP, SPF, LVL, Unspecified) | ⬜ **Engine** | bearing check is SPF-only; needs per-material Fc⊥ |
| Support width/length input per bearing | ✅ | (we call it "bearing length"; doc says "width" — align terminology) |

### 3.5 Design tab — Settings
| V1.0 feature | Status | Notes |
|---|---|---|
| Live / Total deflection limits (+ cantilever) | ✅ | member-type defaults, now optional-with-fallback |
| Max total / max cantilever absolute deflection (in) | 🟡 | limit denominators ✅; absolute-inch cap ⬜ |
| Tributary width for area loads | 🟡 | via on-center spacing conversion |
| Service condition: Dry / Wet | ⬜ **Engine** | wet-service factor C_M not applied |
| Usage: Dropped Beam / Flush Beam / Wall Header | ⬜ | affects load application + connections |
| Max depth constraint | ⬜ | limit scan/selection by depth |
| Lateral Torsional Buckling + top/bottom bracing | ⬜ **Engine** | beam-stability factor C_L not applied |

### 3.6 Design tab — Loads
| V1.0 feature | Status | Notes |
|---|---|---|
| Uniform load; Point load | ✅ | full-length uniform + point loads |
| Load components D / L / S / Lr / W with CD | ✅ | durations 0.9 / 1.0 / 1.15 / 1.25 / 1.6 match the doc exactly |
| psf ↔ plf via spacing | ✅ | |
| Uniform **linear**, **trapezoidal**, **concentrated linear** loads | ⬜ **Engine** | partial-length / varying loads need engine + UI |
| Load reference (left/right), start/end, location (top/flush) | ⬜ | richer load placement model |
| Load list with CRUD + edit dialogs | 🟡 | point-load rows + editing; no unified load list/CRUD across all types |

### 3.7 Design tab — Products / Materials
| V1.0 feature | Status | Notes |
|---|---|---|
| Material / series selection | ⬜ **Engine** | **SPF No. 2 hardcoded** |
| Plies (1–4), width, depth selection | ⬜ **Engine** | single-ply sawn only; no built-up members |
| Filtered product list to analyze | ⬜ | depends on a material library |
| Materials: Steel, Douglas Fir, Southern Pine, LVL 1.5–2.3E | ⬜ **Engine** | needs a manufacturer-independent material DB (master-plan calls for this) |

### 3.8 Design tabs — Holes / Notch-Bevel / Connections / Notes
| V1.0 feature | Status | Notes |
|---|---|---|
| Holes (circular/rect/obround, H/V orientation, section reduction) | ⬜ **Engine** | hole rules + reduced-section checks |
| Notch / Bevel (end notches, bevel cut, heel depth, slope) | ⬜ **Engine** | notch-shear rules (NDS 3.4.3), bevel geometry |
| Connections (multi-ply fasteners: nails/bolts/screws; Simpson/Mitek/Fastenmaster) | ⬜ **Engine** | needs fastener capacity DB + built-up member support |
| Notes (member description, notes, notes library) | 🟡 | design `name` field; no description/notes/library |

### 3.9 Member Analysis Window (control checks)
| V1.0 control | Status | Notes |
|---|---|---|
| Moment · End Shear · Total/Live Deflection · Bearings · Control value/% | ✅ | all present with demand/ratio |
| Uplift (only when present) | ✅ | net-uplift flagged as a hard fail |
| Negative Moment (separate) · Continuous Shear (multi-span) | 🟡 | computed as max|M|/|V|; not broken out as named controls |
| Total Negative Deflection (multi-span) | ⬜ | |
| Max Deflection / Cantilever Max Deflection (absolute) | 🟡 | cantilever tip ✅; absolute max not a named control |
| Span/Depth ratio | ⬜ | simple to add |

---

## 4. Build sequence to reach V1.0

Ordered to keep the engine trustworthy and unlock the most functional surface per unit of work. Roughly: finish/round out what exists, then the two big engine expansions (materials, richer loads), then the section-modifying checks, then connections, then the shell/UX.

**A. Round out the current beam designer (small, high polish)**
1. Analysis pane: name **Negative Moment**, **Continuous Shear**, **Span/Depth ratio**, and absolute **Max Deflection** as their own controls (mostly display of values already computed).
2. Span tab: **Enable Bearing Analysis** toggle; editable support labels; align "bearing length" ↔ "width" terminology; default span type to Out-to-out.
3. Settings tab: absolute max-deflection (inch) cap; **Service condition Dry/Wet** (C_M) — small engine factor, real value.

**B. Materials / Products (biggest V1.0 unlock — Engine)**
4. Manufacturer-independent **material database**: Douglas Fir, Southern Pine, SPF (all grades), then LVL grades; per-material Fb/Fv/Fc⊥/E. Master plan explicitly calls for this.
5. **Plies + width/depth** selection and built-up (multi-ply) members.
6. **Products tab** + material-library-driven product list; bearing **support material** dropdown falls out of this.

**C. Richer loads (Engine)**
7. **Partial-length / linear / trapezoidal / concentrated** loads in the engine (the FEM solver already supports arbitrary point loads; distributed-load generalization is the work) + load reference/placement model.
8. Unified **Loads list** with full CRUD and edit dialogs across all load types.

**D. Section-modifying checks (Engine)**
9. **Notch / Bevel** (NDS notch-shear rules, bevel geometry).
10. **Holes** (reduced-section bending/shear, hole placement rules).
11. **Lateral torsional buckling + bracing** (C_L) — needed for dropped beams especially.

**E. Connections (Engine + data)**
12. **Multi-ply fastener** design (nail/bolt/screw capacity, rows/spacing) with a Simpson/Mitek/Fastenmaster-style connector library; concentrated-load side connections.

**F. Application shell / projects / UX**
13. **Projects**: Open, Save As, Project Info, per-project default settings; project library page.
14. **Navbar shell**: Settings dropdown (company info, app defaults, material library link), Resources pages, profile/subscription.
15. **Member viewer context menus** (right-click to select product, add loads, edit load, bearing properties).
16. **Notes** (description, notes, notes library); search; notifications.
17. New member types needing engines: **Column** (axial/buckling), **Roof Beam / Hip Beam** (sloped geometry).

## 5. Scope reconciliation notes

- **The new doc greatly expands V1.0** beyond the current roadmap's near-term list. Current build ≈ the core beam/joist engine + designer (Span/Settings/Loads partial), which is a solid foundation but roughly the first third of the V1.0 surface.
- **Deferred-material decision now on the critical path.** Earlier we deferred expanding materials until "the app fully works." The new V1.0 spec (Products tab, support materials, LVL, plies) makes the material database a V1.0 requirement, not a later phase. Suggest promoting it (step B) once the current beam designer is rounded out.
- **Several items are genuinely new engines**, not UI: Column (axial), Roof/Hip beams (sloped), holes, notches, LTB, connections, wet-service. Each needs its own hand-calc benchmark set before shipping, per the accuracy philosophy.
- **Consistent where it counts:** the doc's load-duration factors (100/90/115/125/160%) exactly match the engine's CD values, and the three span types already match — so the loads and span foundations line up with the vision.
- **Terminology to standardize:** "support width" (doc) vs "bearing length" (app); "Beam" support type = a dropped support; confirm before UI copy is finalized.

## 6. Known gaps carried forward (intentionally not in scope yet)

Fixed/moment connections; masonry-specific bearing minimums; hold-down hardware sizing for uplift (uplift is detected and flagged, not sized); full graphical/object-based editor and whole-building load transfer (master-plan Phases 3–5); AI assistant (Phase 6).
