# Heilongjiang public procurement requirements

Use this reference when planning or reviewing production scheduling, change detection,
imagery production, supervision, archives, data sharing, UAV work, or agricultural IoT.
The requirements below are derived from public Heilongjiang government procurement
notices and their attached tender documents. Do not present them as completed unless
the platform has persisted evidence and executable workflows.

## Remote-sensing production baseline

- Support production plans triggered by imagery availability and divide work into
  auditable packages by prefecture, county, area, plot count, deadline, and assignee.
- Use verified current imagery together with prior survey results, daily change data,
  management information, ecological redlines, DEM/control data, weather, field, and
  other registered datasets. Preserve source, version, checksum, CRS, extent, security
  classification, acquisition time, and lineage for every dataset.
- Provide synchronized before/after imagery comparison, swipe/flicker tools, candidate
  change discovery, manual confirmation, exclusion reasons, confidence, evidence, and
  six change classes: suspected construction, farmland outflow, construction/facility
  agriculture change, non-farmland agricultural change, unused-land change, and
  farmland attribute-label change.
- Make project/task rule profiles configurable. The procurement baseline includes
  construction/facility-agriculture minimum area 200 m², other agricultural minimum
  area 400 m², imagery boundary match within 2 pixels, completeness at least 98%,
  boundary-ground agreement at least 90%, land-class accuracy at least 90%, and key
  field accuracy at least 95%.
- Preserve CGCS2000 and Gauss-Krüger production/export definitions even though service
  APIs remain EPSG:4326. Record every reprojection rather than silently replacing CRS.

## Implemented production-foundation contract

- Reuse `dataset_assets` and `dataset_lineages` for the nine supported source types.
  Registration remains `pending` until physical or independently repeatable evidence is
  verified; a caller-provided checksum alone must not mark an asset verified.
- Reuse `production_batches`, `work_packages`, and `work_package_plots`. Batch creation
  snapshots the persisted project-rule version and values. Package creation derives area
  and plots from the selected real district plus current `task_plots`, then persists every
  plot relation explicitly.
- Derive package progress from current explicitly assigned plot states. Never accept area,
  plot totals, or progress percentages from the browser.
- Persist creation and every scheduling transition in `production_audit_events`, including
  stable operator code, role snapshot, and previous/new values.
- Keep `/api/v1/production/overview` truthful: all 122 district work areas remain visible;
  absent assets, batches, and packages return zero/empty states rather than seed records.
- Continue using independent `independent_supervisor` capabilities. The foundation role is
  not evidence that supervision workflow, reports, or acceptance have been implemented.

## Imagery production and temporal traceability

- Support control points, RPC/GCP geometric correction, DEM-assisted orthorectification,
  regional block adjustment, registration, pan-sharpening/fusion, enhancement, color
  balancing, mosaicking, clipping, and county/province output.
- Validate physical output resolution, cloud cover, band count, bit depth, coverage,
  positional accuracy, format, file size, and SHA-256 before accepting a product.
- Maintain historical imagery coverage matrices and issue-tracing timelines. A public
  procurement example requires problem tracing across 1980–2024 imagery.
- Never classify an open public test image as confidential operational evidence.

## Supervision, acceptance, maps, and archives

- Add an independent supervision role and workflow for sampling plans, process checks,
  findings, evidence, rework deadlines, reinspection, multi-round closure, county
  evaluation, and immutable supervision reports.
- Keep automatic quality checks, interpreter self-check, quality review, client review,
  and independent project supervision as distinct evidence streams.
- Archive source datasets, intermediate artifacts, final vectors/rasters, plot record
  sheets, statistics, thematic maps, reports, quality evidence, approvals, and manifests.
- Provide a thematic-map composer with title, neatline, north arrow, scale bar, legend,
  producer, date, map number, layout templates, bulk generation, and physical checksums.
- Publish approved map/data services only through registered endpoints with application,
  approval, credentials, documentation, health state, usage audit, and revocation.

## Security and operational requirements

- Support data classification, isolated/offline deployment, export approval, watermark,
  download audit, least privilege, security-level protection evidence, domestic operating
  systems, and confidential-data handling. Public/demo data must remain visibly distinct.
- Define measurable service targets instead of permanent green status. The agricultural
  IoT procurement baseline includes 10,000 devices, 500 users, operation response below
  3 seconds, continuous 24-hour service, severe-fault response within 2 hours, and five
  years of operation and storage planning.

## UAV, field IoT, pest, and disease extension

- Manage UAV missions, flight boundaries, operators, aircraft/sensor identity, capture
  time, raw files, orthomosaics, evidence photos/videos, checksums, and linked findings.
- Register monitoring stations and devices by province/prefecture/county, device type,
  location, vendor, owner, status, photos, telemetry, maintenance, and fault reason.
- Ingest telemetry and images through documented idempotent APIs; track online, offline,
  abnormal, maintenance, and retired states with a closed fault workflow.
- Support configurable pest/disease report generation, province/prefecture/county review
  and return, electronic ledgers, exports, mobile collection, expert consultation, and
  alert delivery.
- AI recognition and prediction must preserve model code/version, training/evaluation
  source, deployment target, input data, confidence, accuracy/recall/F1/ROC evidence,
  prediction basis, human review, and superseded versions. Never use fixed fake alerts.

## Official sources

- Heilongjiang land-change survey and key land-class remote monitoring, 2026:
  `planId=8a1d03f99c5b179d019cf96e911329c7`
- Land-change suspected-polygon extraction, 2025:
  `planId=2c9082219a80a086019a94e587a26db6`
- High-resolution satellite imagery processing, 2025:
  `planId=2c90833d98a22c8d0198c62fa96e60e6`
- Ecological remote-sensing processing and field verification, 2025:
  `planId=2c9085629760f2820197875ee13e72c2`
- River/lake dynamic remote monitoring, 2025:
  `planId=2c90857897ce8fa701982bb69484792e`
- Production-construction remote monitoring, 2025:
  `planId=2c90820a996530530199740910b55262`
- Crop pest/disease field monitoring network, 2026:
  `planId=2c90879a9af98660019afce5c3636607`

Source portal: `https://hljcg.hlj.gov.cn/`.
