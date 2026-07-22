# Remote-sensing business rules

## Imagery

- Support metadata, acquisition time, cloud cover, footprint, resolution, sensor, and processing level.
- Processing steps include radiometric calibration, atmospheric correction, geometric correction, clipping, and band/index products.
- Preserve step parameters, operator, timestamps, output URI, status, and progress.
- A processing step is complete only when a physical artifact inside controlled storage passes format-signature, size, and SHA256 verification. Never treat a database flag or invented output URI as generated imagery.
- Imagery ingestion must read driver, CRS, WGS84 footprint, resolution, dimensions, bands, and tags from the physical GeoTIFF/IMG/HDF file. Persist the file in controlled storage, deduplicate by SHA256, and derive catalog counts from the database.
- Public Sentinel/STAC ingestion must retain the selected item identifier, item URL, individual source-band URLs, platform/instrument, product URI, processing baseline, provider, license URL, and public-data classification. Stack only source bands with identical CRS, affine transform, width, and height. Require Raster Extension scale, offset, and nodata for every band, apply them to a floating reflectance artifact, and reject rather than silently resample or retain quantized DN as L2A reflectance.
- Extract sensor/platform, acquisition time, processing level, and cloud cover from case-insensitive common raster tag aliases before consulting user input. User values are optional controlled fallback or date-only precision refinement; reject conflicting file/user values instead of overwriting either one. Persist the final value, tag name, raster value, user value, date precision, timezone assumption, and decision source in `raster_metadata.business_metadata`.
- Do not seed operational imagery metadata without a physical raster, size, and SHA256. With no verified operational asset, return an explicit empty workbench state and keep imagery quality gates unresolved; demo rasters remain visibly labeled and cannot be described as production evidence.
- When opening the imagery workbench, synchronize the current backend overview with the asset catalog and prefer its verified operational image. Demo imagery is only a fallback and must not become the default merely because its acquisition date is newer or its processing pipeline is complete.
- Historical coverage uses the complete persisted 13-prefecture/122-county hierarchy. For every actual imagery asset and every county, compute WGS84 footprint intersection area divided by full county geography area, preserve zero-coverage cells, and distinguish operational and demo time slices. Do not substitute bounding boxes, fixed years, or client percentages.
- Historical issue tracing derives only from persisted ingestion times, required processing steps, current physical source/artifact SHA256 revalidation, project cloud thresholds, and retained artifact histories. Missing historical imagery remains an explicit empty time range rather than a synthetic 1980–2024 series.
- Built-in processing may execute explicit scale/offset calibration, DOS1 atmospheric correction, CRS reprojection, clipping with persisted administrative geometry, and true-color/false-color/NDVI band products. Never represent a file copy or an unconfigured external model as scientific processing.
- A verified Sentinel-2 L2A source may satisfy radiometric and atmospheric requirements through source-level acceptance only when the physical tags prove applied STAC scaling and floating BOA reflectance. Revalidate the artifact and checksum, require a capable stable user, explicit no-algorithm confirmation and justification, preserve product/baseline/provider/license evidence, record `algorithm_executed=false`, and reuse rather than copy the source. Geometric, clipping, and band-product steps still require new verified artifacts.
- Band products require four distinct physical red, green, blue, and NIR indexes, preferably resolved from descriptions. Compute NDVI only for finite, non-negative reflectance with a positive denominator, persist invalid pixels as nodata, and keep valid results within `[-1, 1]`.
- Write processing outputs through a temporary GeoTIFF and atomically replace the final path. Persist source/output checksums, exact parameters, raster structure, processor version, stable operator identity, and role snapshot. Rerunning an upstream step must invalidate every downstream artifact while retaining superseded evidence for audit.
- Automatic image registration must bind two distinct operational assets through checksum-verified processing artifacts. Estimate translation on a server-generated common pixel window, require sufficient valid overlap, dynamic range and peak-to-sidelobe ratio, write the moving image onto the exact reference grid, and recompute physical-output residual. The accepted residual is capped by the persisted project positional-accuracy pixel rule; caller-supplied offsets or evidence URIs are not completion evidence.
- Pan-sharpening must bind two different operational assets from one traceable product and require acquisition times within 60 seconds. Revalidate each controlled file, size, SHA256, radiometric-calibration/reflectance tags, and product identity. Require at least three multispectral bands, one physical panchromatic band, and a panchromatic resolution at least 1.5 times finer. Process bounded windows on the panchromatic grid, reject insufficient overlap, spectral correlation, spatial-detail gain, or excessive output pixels, and atomically persist the GeoTIFF with complete source/output checksums and stable operator-role evidence. Demo assets, grayscale derivatives, ordinary upsampling, and cross-scene inputs are not panchromatic evidence.
- Automatic change-candidate vectorization must keep corner-touching raster components separate so it cannot emit self-touching invalid Polygons. Validate every candidate with PostGIS geometry validity, project containment, and the run's frozen area rule before writing the atomic GeoJSON and database batch; any invalid geometry or candidate-count overflow rejects the whole run attempt without partial evidence.

## Plot interpretation

- `plot_code` is the unique business identifier.
- Store area in hectares; display hectares and mu using `1 hectare = 15 mu` from a shared TypeScript utility.
- Farmland requires a crop type. Non-farmland must not retain a crop type.
- Attribute or geometry edits create immutable versions and audit records.
- Bulk attribute assignment requires explicit plot selection and a documented imagery/field evidence comment. It must never infer crop types from missing values or administrative membership, and every affected plot receives its own immutable version.
- Drawing, vertex editing, splitting, merging, deletion, undo, and redo must either work or remain disabled with an explicit reason.
- Plot splitting starts from an explicitly selected task plot and a user-drawn WGS84 LineString. Execute topology with PostGIS `ST_Split`; accept exactly two valid pieces, require each piece to be at least 0.01 hectares, and verify geography-area conservation within a documented numerical tolerance.
- A successful split soft-deletes the source, creates two inherited child plots in the same task, writes immutable versions for the deleted source and both children, rematches field points by spatial coverage, reopens quality gates, and persists stable operator/role evidence plus source/result lineage in `plot_edit_operations`.
- Plot merging requires an explicit map selection of 2–20 task plots. Require the same county, reject source overlaps above 1 square meter, and use PostGIS `ST_UnaryUnion`; the result must be one valid Polygon rather than a disconnected MultiPolygon.
- When ownership village, land class, crop, planting mode, or irrigation attributes differ, show the conflicts and require the interpreter to confirm final values and evidence. A successful merge soft-deletes every source, creates one task-scoped result, versions all affected plots, rematches field points, reopens quality gates, and persists stable operator/role evidence plus source/result lineage.
- Undo and redo operate on the latest eligible split/merge operation, never by decrementing versions. Persist applied/reverted version snapshots, lock every related plot, and reject the action if any current version or active/deleted state differs from the expected snapshot.
- Each undo/redo creates new immutable plot versions, rematches field points, reopens quality gates, and appends a stable operator/role event. Any new plot mutation after undo must supersede the remaining redo branch.
- External plot snapshots must preserve source name, original feature ID, version, update time, source URI, and province/city/district hierarchy. Never present untraceable rectangles or flat, ungrouped demo geometry as real plots.
- Preserve the complete Heilongjiang hierarchy as province → 13 prefecture-level regions → 122 county-level regions. Empty plot groups must remain visible instead of disappearing from the hierarchy.
- Keep the province-wide parcel integration baseline at all 13 prefecture-level regions, all 122 county-level regions, at least 35,000 traceable OSM Polygon features, and at least 110 county-level regions with 20 features each. The resource catalog must visibly group all 122 counties under their 13 prefecture parents and expand every populated county work area down to individual parcels by default. Any smaller snapshot requires an explicit scope change and matching documentation.
- Preserve valid closed rectangles, contiguous land-use areas, and traceable OSM relation MultiPolygon parts in external snapshots. The current integration accepts 0.05–500 hectare polygons with at least five closed-ring coordinates; preserve way/relation IDs, relation part numbers, source links, versions, and timestamps; never duplicate or simplify geometry merely to inflate counts.
- Map supported OSM land-use tags explicitly to farmland, orchard, forest, grassland, water, or construction land. Catalog summaries and 2D/3D map styles must distinguish all six classes instead of silently flattening them.
- Preserve the source `landuse` distinction for `farmland`, `greenhouse_horticulture`, `orchard`, `plant_nursery`, and `meadow`. Map them to farmland, orchard, and grassland business classes during import, and expose those classes through the resource catalog and both map modes instead of presenting every polygon as farmland.
- Keep task plot identity/source/class/bbox catalog data separate from full map geometry. Full Polygon viewport queries must join `task_plots`, use WGS84 bounds, and return all matches only when the complete result is within the configured limit. Over-limit views return the exact match count and no partial features, requiring the user to zoom closer.
- Apply the same task scope to every plot read path: point/click lookup, code-based boundary lookup, workbench attributes, version history, and rollback target access. Verify `task_plots` before loading or exposing the plot/version and use a task-scoped not-found response for unassigned data.

## Quality

- Check geometry validity/closure, positive area, required attributes, land/crop logic, topology, and positional accuracy.
- Persist non-passing rules as issues with severity, source, status, description, assignee, and timestamps.
- A task cannot advance when blocking rules or unresolved gates remain.
- Scope every check and gate through an explicit task-to-plot assignment. A task must never inherit unrelated active plots merely because they exist in the same database.
- Provide a task-level full check that reports coverage, pass/fail counts, average score, per-rule counts, issue count, duration, and submission readiness in one auditable transaction.
- Re-running the task check supersedes prior automatic quality-rule findings while preserving field-verification findings and manual review issues.
- Expose persisted findings through a pageable queue with rule, status, severity, plot and administrative-region filters. Each plot-level item must include enough version and attribute context to support map location and remediation.
- Reviewer-raised `REVIEW_*` findings require an explicit confirmation action, evidence comment, authorized resolver, timestamp, and immutable audit record. Automatic quality findings close only through re-check; field findings close only through the field-resolution workflow.

## Field verification

- Store WGS84 coordinates, capture time, investigator, photos, voice notes, observations, and forms.
- Accept CSV and physical `.xlsx` batches of at most 500 records. Parse XLSX only on the server; validate archive structure, paths, encryption, expanded size, formulas, headers, timezone-aware capture times, coordinates, and photo evidence. Persist the original file SHA256 and stable uploader-role evidence, and roll back the entire batch when any record fails.
- Match field points to plots spatially and record offset distance and status.
- Thresholds are configurable and decisions are auditable.
- Store offset distance, nearest-neighbor search radius, positional pixel tolerance, and imagery/field time-gap thresholds per project. Matching services must read the persisted values rather than hard-code them, and each rule update must preserve before/after audit values.
- Resolution supports correcting indoor data, accepting field data, compromise, rejection, and reopening.

## Review

- Workflow: interpreting → self check → quality review → client review → completed.
- Pass, return, and reject actions require role checks and comments where correction is needed.
- Returning or rolling back reopens the appropriate workflow state without deleting history.
- Resolve reviewers from active project membership by stable user code. Self check requires the interpreter capability, quality review requires the quality-inspector capability, and client review requires the client-reviewer capability.
- Plot rollback is restricted to quality inspectors and project managers. Review and rollback audits retain display name, stable user code, and the role held at execution time.

## Statistics and disasters

- Aggregate by administrative region, land class, crop type, planting mode, and time.
- Scope every area aggregate through explicit task-to-plot assignments and exclude soft-deleted plots. Return prefecture, county, land class, crop, planting mode, and village groups with hectare/mu values and percentages.
- Use the live task aggregate for the current monitoring year. Historical trend points require persisted real snapshots; never seed fixed trend values. CSV export is restricted to project managers and records stable exporter identity and role in the file.
- Historical snapshot imports are restricted to project managers and physical UTF-8 CSV files. Require years earlier than the current monitoring year, validate total/farmland/crop area containment, persist the file SHA256, source URI/version, conflict strategy, stable role evidence, and immutable payload, and retain superseded import batches when replacing a year.
- Disaster patches store type, severity, affected area, crop, detection date, status, source, and geometry.
- Manual disaster corrections create reviewer and comment audit data.
- Import disaster model results as task-scoped EPSG:4326 GeoJSON FeatureCollections. Persist source URI/version, source feature ID, canonical content SHA256, import batch, stable importer code, and role snapshot; never seed or present untraceable rectangles as real results.
- Recompute disaster area with PostGIS geography and require valid Polygon geometry fully covered by the persisted project boundary. Imports are atomic. Duplicate source features are rejected; explicit patch-code replacement resets previous review fields and returns the patch to pending review.

## Delivery

- Generate only after final review.
- Package vector, attributes, statistics, disaster data, field verification, quality issues, reviews, reports, and a manifest.
- Record version, generator, timestamps, size, checksum, manifest, quality summary, and download path.
- Validate that the physical artifact exists before serving it.
- Generate task vectors from `task_plots`, never from the entire plot table. Project managers generate packages; project managers and client reviewers may download them.
- Block final review and package generation while quality issues or field-verification resolutions remain open. Mark a package stale when the task changed after generation or its plot count no longer matches the task scope.
- Write through a temporary ZIP and atomically replace the final file. Recompute file size and SHA-256 before every download; retained stale packages are audit history, not current deliverables.
- Include every existing checksum-verified thematic map and independent-supervision report as a physical ZIP member. Revalidate and reference the current source imagery, completed processing artifacts, and task/project dataset catalog with controlled URI, size, checksum, version, classification, and status evidence. Each embedded member except the recursively self-describing manifest stores its own size and SHA-256. Archive categories explicitly distinguish included, verified-reference, and not-provided evidence.
- Snapshot thematic-map, supervision-report, dataset-catalog, and imagery-processing counts plus latest timestamps. Any later change makes the package stale. Generating a new version marks every prior completed package superseded so one task cannot expose multiple current deliverables.

## Service sharing

- Persist service registration, endpoint and health URLs, API documentation, resource identity/checksum, classification, exposure scope, authentication mode, owner, stable registrar identity, independent client approval, access applications, credential summaries, health evidence, invocation metrics, and revocation events.
- Resolve internal imagery, thematic-map, delivery, vector, statistics, and other assets from the project database and compare the physical resource checksum. Never grant publish eligibility from a browser-supplied checksum alone. Confidential resources cannot use public exposure; public endpoints require HTTPS; non-public endpoints require authentication.
- API-key secrets are returned only in the approval response. Persist only SHA-256, last four characters, issuer, expiry, status, and revocation evidence. Usage audit accepts either an authorized project manager or a matching active, unexpired key and records method, path, response status, duration, and bytes.
- Health checks perform a bounded server-side HTTP request, refuse redirects, and reject loopback, private, link-local, multicast, reserved, and unspecified addresses unless the exact host is deployment-allowlisted. Persist unsuccessful probes instead of displaying a permanent healthy state.
- Revoking a service locks it and all active credentials, revokes them in one transaction, and appends an immutable event. Keep rejected, revoked, and historical requests visible for audit rather than deleting them.
