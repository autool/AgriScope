---
name: remote-sensing-gis-platform
description: Develop, refactor, review, test, or deploy the remote-sensing production, change-detection, imagery-processing, field/UAV/IoT verification, supervision, quality review, statistics, archive, sharing, and delivery platform in /root/gis. Use for Vue 3/TypeScript GIS work, Vben5-inspired application layouts, OpenLayers/Cesium interaction, FastAPI/PostGIS services, agricultural pest monitoring, workflow rules, Docker delivery, or project coding-standard updates.
---

# Remote Sensing GIS Platform

Build production-oriented increments for the agricultural remote-sensing platform while preserving its architecture, GIS invariants, workflow auditability, and runnable state.

## Required workflow

1. Read repository instructions, `CODEBUDDY.md`, current source, runtime state, and tests before relying on earlier context.
2. Derive the complete user-visible workflow, database changes, API contract, frontend state, error states, permissions, and verification evidence required by the request.
3. Keep backend flow `Routes → Services → DAO → Models` and frontend flow `Views → Components → Store → API`.
4. Implement the real business behavior. Do not leave enabled controls that only display a message or use synthetic GIS data without an explicit demo label.
5. Preserve TypeScript strictness, parameterized SQL, WGS84 API geometry, explicit OpenLayers projection, and stationary Cesium behavior.
6. Verify in proportion to risk: backend tests and Ruff, frontend typecheck/lint/build, database queries, API calls, and browser screenshots or interaction checks.
7. Keep services runnable after changes when the task involves implementation.
8. Before committing, inspect the repository's currently effective commitlint, package scripts, and Git hook configuration. Follow the discovered rules, never invent a format, write the title and body in detailed professional Chinese, and never bypass hooks without explicit user authorization.

## Reference routing

- Read [references/architecture.md](references/architecture.md) for cross-layer changes, API work, database migrations, Docker, testing, naming, and security rules.
- Read [references/frontend-vben5.md](references/frontend-vben5.md) for navigation, layout preferences, route tabs, page containers, dense operational UI, responsive behavior, and frontend refactors.
- Read [references/business-rules.md](references/business-rules.md) for plot interpretation, imagery processing, field verification, disaster assessment, quality rules, review states, statistics, and delivery packages.
- Read [references/procurement-requirements.md](references/procurement-requirements.md) for Heilongjiang production scheduling, multi-temporal change detection, supervision, advanced imagery production, thematic mapping, archives, security, UAV, IoT, and pest/disease requirements derived from public procurement files.

Read every reference relevant to the current task before editing. Do not load unrelated references.

## Architecture gates

- Reject route handlers that contain SQL or call a DAO directly.
- Reject components that call Axios/fetch directly or receive OpenLayers/Cesium instances through prop chains.
- Reject JavaScript application source; use `.ts` and `<script setup lang="ts">`.
- Reject giant views that combine unrelated modules or duplicate business panels.
- Reject interpolated SQL, untracked schema edits, fake successful responses, silent exception swallowing, or raw backend stack traces in the browser.
- Reject automatic Cesium rotation, flight, camera drift, or movement caused only by switching to 3D. Explicit user navigation may reposition once without animation.
- Reject administrative or business boundaries drawn as placeholder rectangles when the feature is presented as real data.
- Reject flat administrative lists or plot-derived region trees that hide real empty regions. Province-wide resources must preserve province → prefecture → county work area → real parcel hierarchy.
- Reject province-wide OSM parcel snapshots below all 13 prefecture-level regions, all 122 county-level regions, 35,000 traceable Polygon features, or 110 county-level regions with at least 20 features each unless the documented business scope is explicitly reduced. Preserve valid 0.05–500 hectare closed parcels, including regular rectangles and traceable relation MultiPolygon parts.
- Reject OSM imports that flatten unlike land-use tags into one fake class. Explicitly map supported tags to farmland, orchard, forest, grassland, water, and construction land; preserve way/relation source IDs, relation part numbers, source links, versions, and timestamps; differentiate all six business classes in the catalog plus 2D/3D rendering.
- Reject hierarchy that exists only in data but is visually hidden behind collapsed or undifferentiated nodes. Province-wide workbenches must explicitly present province → prefecture → county work area → real parcel counts, group all 122 county entries under their 13 visible prefecture parents, expand every populated county through individual parcels by default, open the boundary catalog to county level, provide explicit prefecture/county/parcel expansion controls, and support region or plot search. Expanding only one representative branch or showing prefectures without their county children is not acceptable.
- Reject administrative boundaries that use visually indistinguishable strokes. The map must differentiate province, prefecture, and county boundaries by width and dash pattern, with an adjacent legend and live prefecture/county/plot coverage counts.
- At province scale, label real prefecture boundaries with their parcel counts so small land-use polygons are not mistaken for missing data; progressively reveal county work areas and individual parcel detail at closer scales.
- Reject province-wide workbenches that download every full parcel geometry to construct the catalog. Keep the complete task-scoped catalog as lightweight plot identity/source/class/bbox data, and load full Polygon geometry by task plus current WGS84 viewport only at editing scales. When a viewport exceeds 5,000 matches, return the exact count and an explicit zoom requirement with zero partial features; never present an arbitrary truncated subset as complete.
- Reject plot read paths that query the global plot table and defer task validation to later mutations. Point/click lookup, plot-code boundary lookup, workbench attributes, version history, and rollback target reads must carry `task_code`, verify `task_plots` before exposing the object, and return a task-scoped 404 for unassigned plots without revealing cross-task existence.
- Reject hard-coded quality or field-verification thresholds when the settings UI presents them as configurable. Persist project rules and audit every change.
- Reject browser-only XLSX parsing or partial field-record imports. Field CSV/XLSX batches are limited to 500 records and must reuse one server-side atomic matching transaction. Server-side XLSX parsing must validate ZIP structure, paths, encryption, expanded size, formulas, headers, timezone-aware capture times, WGS84 coordinates, and photo evidence while persisting the physical file SHA-256 plus stable uploader-role audit.
- Reject task quality gates that scan every active plot without an explicit task-plot scope. Batch checks must use task assignments, bulk spatial metrics, and one transaction rather than hundreds of per-plot commits.
- Reject parcel snapshot reloads that retain prior-scope plot quality checks or overwrite the previous import audit. In one transaction, remove derived `plot_quality_checks`, resolve only open automatic `quality_rule` issues with stable system evidence, reset the task score, preserve manual/field issues and full history, and append a new immutable import-cycle record.
- Re-running automatic quality checks may resolve prior `quality_rule` findings only; it must preserve field-verification and manually raised issues.
- Reject quality dashboards that expose counts without an actionable issue queue. Persisted findings must be pageable, filterable by rule/status/severity/region, and able to select and focus the associated plot on the map.
- Reject bulk attribute updates that infer crops or silently target a whole region. Bulk remediation must use explicit plot selections, task-scope validation, a required evidence comment, one immutable version per plot, and a quality recheck gate.
- Reject plot splitting implemented only in the browser or by replacing the source geometry. Splits must use a user-drawn WGS84 LineString and PostGIS `ST_Split`, produce exactly two valid pieces of at least 0.01 hectares, conserve area, soft-delete the source, create two task-scoped children, preserve source/child versions, rematch field points, and persist stable operator-role evidence in `plot_edit_operations`.
- Reject plot merging that auto-selects a region, silently chooses one source's attributes, or returns a MultiPolygon. Users must explicitly select 2–20 task plots; the server must lock them, require one district, reject overlaps above 1 square meter, use PostGIS `ST_UnaryUnion` to produce one valid Polygon, require explicit conflict resolution for business attributes, soft-delete every source, create one task-scoped result, version every affected plot, rematch field points, reopen quality gates, and persist lineage plus stable operator-role evidence.
- Reject browser-only undo/redo, version-number decrementing, or restoration that can overwrite later edits. Persist applied and reverted version snapshots per split/merge operation, lock and compare every related plot before history actions, restore by creating new immutable versions, rematch field points, reopen quality gates, write stable operator-role events, and supersede every redo branch when a new plot mutation occurs.
- Reject imagery steps or product cards that claim completion without a verifiable physical artifact and checksum evidence.
- Reject built-in imagery processing that copies files or labels unconfigured 6S/FLAASH work as completed. Built-in steps must use explicit calibration, DOS1, reprojection, persisted-boundary clipping, or band-mapping parameters, write outputs atomically, and invalidate downstream artifacts when an upstream step is rerun.
- Reject hard-coded imagery catalog counts or user-entered spatial metadata when it can be extracted from the uploaded raster file.
- Reject imagery upload flows that require users to retype business metadata already present in raster tags or silently choose between conflicting values. Sensor/platform, acquisition time, processing level, and cloud cover must use case-insensitive common tag aliases, fall back to optional controlled user input only when absent, reject conflicts, and persist final value, raster tag/value, user value, precision, timezone assumption, and source under `raster_metadata.business_metadata`.
- Reject hard-coded sidebar badges, dashboard totals, or module work-item counts. Navigation counters must come from the current project/task backend aggregate and distinguish verified operational imagery from demo assets and pending work from completed records.
- Reject fixed notification badges, inert notification buttons, fake project switchers, or permanently healthy service labels. Header notifications must aggregate real current-task blockers and pending records with working module routes; single-project contexts must be presented as status rather than an unavailable switch action.
- Reject frontend-defined workflow completion or seeded project progress percentages. Dashboard stages and overall progress must be derived server-side from verified operational imagery, task plot completion, quality-gate coverage/pass evidence, field-resolution state, persisted review state, and a current checksum-backed delivery package.
- Reject seeded operational imagery metadata without a physical raster, file size, and SHA-256. Workbench overview must allow an explicit no-imagery state, quality checks must keep the imagery gate unresolved, and every demo raster must remain visibly labeled as demo.
- Reject prefilled sensor, acquisition time, processing level, or dated imagery evidence in upload/edit forms, and reject fixed-person/fixed-time review rows in initialization SQL. Business facts must come from the uploaded file, its controlled handoff metadata, or an actual user action.
- Reject review, rollback, or delivery authorization based only on client-submitted names or role strings. Resolve an active project user by stable user code, enforce server-side capabilities, lock workflow rows during transitions, and persist reviewer code plus role snapshots in audit records.
- Reject review workbenches that mix prior task cycles with the current approval evidence or load unbounded audit history into the overview. Preserve full history for delivery, expose its total count, and show a bounded current remediation cycle beginning at the latest data reload, review return/rejection, rollback, or field batch import.
- Reject delivery packages built from all active plots instead of the explicit task scope. Supersede packages whose task timestamp or plot count is stale, restrict generation/download by capability, write ZIPs atomically, and verify size plus SHA-256 before download.
- Reject delivery eligibility based only on `task.status=completed`, and reject reports that describe empty field/disaster collections as completed evidence. Recheck verified operational imagery, full task quality coverage, all passing gates, average score, open issues, and pending field work immediately before generation; reports must label absent optional evidence explicitly.
- Reject manual closure of automatic quality or field-verification findings. Only persisted `REVIEW_*` manual findings may be confirmed closed by authorized reviewers with evidence comments and resolver identity/role snapshots.
- Reject disaster patches seeded as untraceable rectangles or imported without source URI/version, source feature ID, content checksum, batch code, and stable user-role audit. Disaster GeoJSON imports must be atomic, task-scoped, capability-checked, and explicit about reject versus replace conflict behavior.
- Reject client-supplied disaster area. Accept only WGS84 Polygon geometry, validate it against the persisted project boundary, and recompute affected hectares with PostGIS geography. Replacing model evidence must reset prior manual review conclusions.
- Reject area statistics that scan all active plots instead of joining the explicit `task_plots` scope. Task statistics must exclude deleted plots and cover prefecture, county, land class, crop, planting mode, and village dimensions.
- Reject fixed or synthetic annual trend values. The current monitoring year must use the live task aggregate; historical years require persisted real snapshots. Statistics export requires a stable authorized project-manager identity and must include exporter role evidence.
- Reject unaudited or mutable historical trend imports. Only authorized project managers may import physical UTF-8 CSV history files; every year must precede the current monitoring year, area containment rules must pass, and the system must preserve the file SHA-256, source URI/version, conflict strategy, stable role evidence, and immutable original payload. Replacements may change the current snapshot but must retain prior import batches.
- Reject production work represented only by one province-wide task. Production plans must create explicit batches and auditable work packages by administrative scope, area, plot count, deadline, and stable assignee identity; package progress and reconciliation must come from persisted assignments.
- Reject before/after change detection that uses unverified imagery, unsynchronized views, fixed rectangles, or client-only candidates. Persist source and target asset versions, alignment evidence, rule profile, candidate geometry, change class, confidence, interpreter decision, exclusion reason, and immutable review history.
- Reuse `change_detection_runs`, `change_candidates`, and `change_detection_events` for multi-temporal work. A run must bind two distinct `imagery_assets` physical files in acquisition order, require operational status, file/checksum evidence, completed calibration/correction, intersecting WGS84 footprints, alignment evidence, and an offset within the persisted project rule. Snapshot the rule version, rule values, task update time, and explicit task-plot count when creating the run.
- Change-candidate imports must be one frozen atomic EPSG:4326 Polygon FeatureCollection of 1–500 features per run. Reject import when the task update timestamp or explicit plot count differs from the run snapshot and require a new run. Preserve source name/URI/version, source feature ID, content SHA-256, batch code, evidence URI, confidence, area recomputed by PostGIS, and one of the six procurement change classes. Apply the run's frozen 200/400 m² rule snapshot rather than the current mutable settings. Every confirmation, reclassification, or exclusion requires stable reviewer capability and evidence text and must append an immutable event; exclusions additionally require a reason.
- Built-in candidate discovery may consume only the common-grid physical previews generated from the run-bound rasters. Persist algorithm code/version, every parameter, both preview SHA-256 values, the physical GeoJSON URI, and its result SHA-256. Automatic candidates must remain `unclassified` until a reviewer assigns one of the six procurement classes with evidence; reject candidate counts above the configured limit instead of silently truncating or presenting a partial batch as complete.
- Before/after visualization must use server-generated previews from the two run-bound physical rasters, not unrelated public basemaps or browser-only resampling. Recheck source SHA-256 before first generation, reproject both rasters to one WGS84 intersection grid, use the same RGB stretch ranges, persist an atomic cache manifest with source/preview checksums and renderer version, and apply one shared frontend zoom/pan transform to swipe, user-triggered flicker, and side-by-side modes.
- Reject generic asset lists that omit source lineage. Every imagery, raster, vector, tabular, control, DEM, weather, management, UAV, and IoT dataset must preserve source, version, checksum, CRS, extent, time range, security classification, task use, and derived-artifact lineage.
- Reject a quality-inspector review being presented as independent project supervision. Supervision requires a separate role, sampling plan, process inspection, evidence, findings, rework deadline, reinspection, county evaluation, and immutable report.
- Reject orthorectification, registration, fusion, mosaicking, color balancing, or thematic-map generation claims without checksum-backed physical artifacts and measurable resolution, coverage, positional, band/bit-depth, layout, and format acceptance evidence.
- Reject public map/data services without persisted service registration, approval, credentials, documentation, health checks, usage audit, and revocation; reject confidential datasets being published through public endpoints.
- Reject UAV or monitoring-device records without real source identity, coordinates, capture/telemetry time, operator/device ownership, physical evidence, checksum, status, and maintenance/fault audit.
- Reject pest/disease dashboards based on fixed alerts or unaudited model output. Preserve station/device observations, model code/version, inputs, confidence, validation metrics, prediction basis, human review, warning delivery, and superseded model evidence.

## Frontend product principles

- Adapt Vben5 patterns; do not import the entire framework or copy its visual identity.
- Drive the application shell from typed, persisted preferences: sidebar, header, route tabs, KeepAlive, content width, density, transition, and maximize state.
- Drive menu and page behavior from route metadata. Keep business pages independently lazy-loaded.
- Optimize desktop GIS work for scan speed, split panes, queues, filters, maps, detail panels, audit history, and recovery states.
- Use restrained color and hairline surfaces. Reserve strong color for selection, severity, status, and primary actions.
- Define loading, empty, error, disabled, permission-denied, offline, unsaved, and destructive states for interactive features.

## Verification baseline

Run the relevant commands from their project directories:

```bash
cd backend
poetry run pytest -q
poetry run ruff check .

cd ../frontend
npm run typecheck
npm run lint
npm run build
```

For GIS or layout changes, additionally inspect a rendered page and verify layer visibility, projection, labels, user interaction, 2D/3D state, and absence of unintended camera motion.
