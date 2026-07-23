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
- Public Sentinel-2 integration must preserve the Earth Search STAC item, original COG band URLs, SAFE product URI, processing baseline, provider, Copernicus legal notice, and public classification. Treat a verified public raster as usable business input without presenting it as confidential source data or an accepted production product.
- The implemented public historical-imagery contract searches the server-fixed Microsoft Planetary Computer `landsat-c2-l2` collection by bounded WGS84 bbox, date range, and cloud threshold. Single-scene import accepts only a stable Item ID; atomic batch import accepts 1–10 unique Item IDs, unique asset codes, one shared bbox, batch code, stable operator and evidence. The server refetches every Item, validates unsigned Azure COG hosts, keeps short-lived SAS values in memory only, requires complete target coverage and co-gridded Blue/Green/Red/NIR Raster Extension metadata, applies scale/offset/nodata to floating surface-reflectance GeoTIFFs, then invokes the existing imagery batch service once. Any scene failure removes all public temporary subsets. It persists ordered STAC, product, WRS, provider, licence, public classification, physical size, SHA-256 and canonical batch-manifest evidence plus a non-statutory notice. The current real integration includes 1986, 1988 and 1989 Landsat-5 subsets over the same Harbin bbox; these three traceable scenes are not a complete 1980–2024 provincial corpus.
- Earth Search COG subsets must apply each band's STAC Raster Extension scale/offset/nodata and persist the original calibration list. Sentinel-2 L2A may satisfy radiometric and atmospheric gates through an audited no-algorithm source acceptance only after physical BOA-reflectance and checksum verification; reprojection, administrative clipping, and thematic products remain separate checksum-backed outputs.
- The implemented source-level acceptance contract now keeps Sentinel-2 L2A and Landsat Collection 2 Level-2 as separate evidence profiles. Landsat acceptance revalidates the current physical checksum, Planetary Computer/USGS lineage, matching STAC/product identity, WRS, public licence, unsigned Azure COG URLs, four ordered floating reflectance bands, and the complete calibration ledger before reusing the same source for radiometric and atmospheric gates. It records `algorithm_executed=false`, profile-specific processor versions, stable-user justification and immutable review events. The real 1986 Landsat-5 entity has passed both gates without file duplication; geometric correction, clipping, enhancement and band products remain pending physical outputs.
- The implemented imagery workbench preview contract reads the selected physical raster
  rather than a fixed map tile. It persists source and PNG checksums, WGS84 bounds,
  band selection, stretch/value range, and renderer version. True-color, false-color,
  and NDVI quicklooks are available only from a checksum-verified `band_products`
  artifact, remain visibly demo when their source is demo, and do not count as an
  accepted production artifact by themselves.
- The implemented historical-imagery contract builds one real matrix cell for every
  persisted imagery time slice and each of the complete 122 county boundaries. Coverage
  is the WGS84 footprint/county intersection geography area divided by the full county
  geography area; zero cells remain visible and demo time slices remain separate. Its
  trace timeline revalidates source and processing-artifact SHA-256 values and derives
  import, required-step, invalid-artifact, cloud-rule, and superseded-artifact events
  from persisted evidence. The current real acquisition range is returned as-is; the
  platform does not fabricate the procurement example's 1980–2024 archive when those
  physical source scenes have not been supplied.
- The implemented geometric-correction contract supports ordinary reprojection,
  first-order affine GCP correction from 3–100 traceable non-collinear control points,
  and GDAL RPC/DEM orthorectification. RPC-only source rasters derive WGS84 footprints
  from the physical RPC model and retain that model through radiometric/atmospheric
  outputs. The server validates controlled DEM signature, CRS, real elevation data,
  complete RPC-range coverage, size, and SHA-256 before warping, then persists RPC,
  DEM, grid, resampling, and orthorectified-output evidence. GCP correction retains its
  per-point residual/RMSE gate. Reruns preserve prior evidence and invalidate downstream
  artifacts without deleting history. This is not regional block adjustment or fusion.
- The implemented optional enhancement step sits between administrative clipping and
  band products. Leaving it pending does not reduce required-pipeline completion or block
  products; executing it performs per-band percentile contrast stretch or histogram
  equalization, rejects empty/constant bands, writes a physical 0–1 floating GeoTIFF,
  persists actual ranges/thresholds/bins and checksum evidence, and invalidates downstream
  products. Browser-only display filters are not accepted as enhancement evidence.
- The implemented automatic-registration contract selects two distinct operational
  imagery assets and one checksum-verified processing artifact per asset. The server
  estimates a translation on their real common pixel window using phase correlation,
  rejects inadequate valid overlap, texture, peak-to-sidelobe ratio, or initial offset,
  and writes the moving image onto the reference CRS, resolution, dimensions, and grid.
  It then recomputes residual from the physical output and applies the stricter of the
  requested threshold and persisted project positional-pixel rule. Passing jobs retain
  input/output size and SHA-256, shift/residual/overlap/correlation evidence, stable user
  role audit, atomic output, and download revalidation. This is translation registration,
  not affine/projective registration, orthorectification, or regional block adjustment.
  New change-detection runs must bind this persisted registration job and use its verified
  output for the target-side common-grid preview; typed offsets or arbitrary evidence URIs
  are not accepted.
- The implemented candidate-discovery contract exposes its algorithms from a server-side
  registry. RGB mean absolute difference and RGB change-vector magnitude use distinct score
  formulas and default thresholds; every run persists the selected code, name, version,
  formula, parameters, source-preview checksums, and physical GeoJSON checksum. These RGB
  scores discover candidates only: they do not claim NDVI, land classification, or any of
  the six procurement change classes. All automatic candidates remain unclassified until
  a capable reviewer records a class and evidence.
- The implemented multi-scene mosaic contract selects 2–20 distinct imagery assets and
  one checksum-verified processing artifact per asset. Inputs must have consistent band
  counts and descriptions. The Rasterio worker computes statistics, applies optional
  global mean/std balancing, and performs first-scene or overlap-mean compositing in
  bounded raster windows. Empty or constant bands are rejected instead of being given
  synthetic contrast.
- Coverage acceptance uses the complete persisted administrative geometry as the
  denominator and a target grid containing both the imagery union and the full boundary;
  administrative pixels outside all scenes remain NoData. Tasks above the configured
  pixel ceiling or below the explicit coverage threshold leave no partial output. Passing
  jobs persist an atomic GeoTIFF, resolution/CRS/coverage counts, input checksums, output
  size/SHA-256, stable user-role audit, and download revalidation. This is not advanced
  seamline optimization, regional block adjustment, pan-sharpening, or province-scale
  load-test evidence.
- The implemented pan-sharpening contract selects two different operational assets from
  the same traceable product with acquisition times no more than 60 seconds apart. Both
  controlled files are revalidated by size and SHA-256 and must expose radiometric-
  calibration/reflectance tags plus identical product identity. The multispectral source
  provides at least three bands; the physical single-band panchromatic source must be at
  least 1.5 times finer. The bounded-window histogram-matched Brovey worker targets the
  panchromatic grid and enforces output pixels, valid overlap, per-band spectral
  correlation, and spatial-detail gradient gain before atomically publishing a floating
  GeoTIFF. Passing jobs preserve complete input/output lineage and stable user-role audit,
  and downloads revalidate the artifact. Demo imagery, grayscale derivatives, ordinary
  upsampling, and different-scene pairs are rejected. The current real integration uses
  Google Cloud Public Datasets / USGS Landsat-8 scene
  `LC08_L1TP_117028_20200724_20200807_01_T1`: B2/B3/B4 and B8 are converted from physical
  DN values to TOA reflectance with the scene MTL coefficients. The verified 15 m result
  records 99.4537% valid overlap, 0.872138 minimum per-band spectral correlation, and
  1.903269 spatial-detail gradient gain. It remains public-data processing evidence, not
  a statutory survey product or proof of all-sensor fusion support.

## Supervision, acceptance, maps, and archives

- Add an independent supervision role and workflow for sampling plans, process checks,
  findings, evidence, rework deadlines, reinspection, multi-round closure, county
  evaluation, and immutable supervision reports.
- Keep automatic quality checks, interpreter self-check, quality review, client review,
  and independent project supervision as distinct evidence streams.
- Archive source datasets, intermediate artifacts, final vectors/rasters, plot record
  sheets, statistics, thematic maps, reports, quality evidence, approvals, and manifests.
- The implemented delivery-archive contract physically embeds verified thematic maps and
  independent-supervision reports, while revalidating and referencing large imagery source
  and processing rasters by controlled URI, size, SHA-256, version, classification, and
  processing evidence. It also includes the project/task dataset catalog, an explicit
  included/referenced/not-provided archive index, and per-file size/SHA-256 values for
  every embedded member except the self-describing manifest. Changes to thematic maps,
  supervision reports, dataset catalogs, or current imagery-processing artifacts make
  older packages stale; a new package explicitly supersedes prior completed versions.
  This remains the controlled online delivery package; large physical rasters are handled
  by the separate task-level offline-media archive described below.
- The implemented offline-media contract requires a current checksum-verified delivery
  package and revalidates every operational source raster, every completed processing step
  with a distinct physical output, and every verified project/task dataset entity. It
  writes complete files into independently extractable capacity-bounded ZIP64 volumes,
  rejects over-capacity single files without truncation, stores a manifest inside every
  volume, and publishes a canonical top-level manifest containing ordered volume and
  complete source snapshots. Generation uses same-filesystem temporary storage, reopens
  and hashes every embedded member, publishes atomically, cleans all files on database
  failure, preserves stable-user generation/supersession/download events, supersedes the
  prior current version, and blocks download after delivery or source evidence changes.
  This is executable task-level physical-media preservation, not evidence of a supplied
  1980–2024 corpus or a long-term institutional retention program.
- Provide a thematic-map composer with title, neatline, north arrow, scale bar, legend,
  producer, date, map number, layout templates, bulk generation, and physical checksums.
- The implemented thematic-map contract reads a checksum-verified `band_products`
  physical raster directly, persists layout templates, and generates 1–12 PNG/PDF maps
  per atomic batch. Each product manifest preserves source URI/SHA-256, STAC item,
  license, public classification, product baseline, actual bands, stretch or value range,
  layout, renderer version, output size/SHA-256, and stable operator-role evidence.
  Preview and download revalidate controlled path, signature, size, and checksum; maps
  made from public Sentinel-2 evidence retain a visible non-statutory-results label.
  The implemented task-atlas contract requires the complete current verified PNG map set,
  preserves an explicit page order, and atomically publishes a versioned ZIP containing a
  cover/table-of-contents PDF, original PNG members, and a canonical checksum manifest.
  It revalidates the current source set and every ZIP/PDF/member checksum before download
  or delivery, supersedes prior versions, and makes delivery stale when atlas state changes.
  This is executable task-level atlas composition; it is not evidence that regional block
  adjustment, advanced seamline mosaicking, or a 1980–2024 historical corpus has been
  supplied.
- Publish approved map/data services only through registered endpoints with application,
  approval, credentials, documentation, health state, usage audit, and revocation.
- The implemented service-sharing contract uses persisted registrations, independent
  client-review approval, database-verified internal resource checksums, classification
  and exposure rules, purpose/expiry-bound access applications, one-time API-key display,
  hashed credential storage, bounded SSRF-protected health probes, authenticated usage
  events, individual credential revocation, and atomic service-wide credential revocation.
  The current real catalog entry is the public Element 84 Earth Search STAC endpoint;
  it is not evidence that confidential or statutory survey products are publicly served.

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
- The implemented field-monitoring contract persists stations, devices, idempotent
  telemetry, device faults, model versions, assessments, alerts, and immutable events.
  Station WGS84 coordinates must fall inside the declared persisted district boundary;
  device photos, optional telemetry files, model artifacts, assessment inputs, fault
  resolutions, and alert-delivery receipts preserve physical size and SHA-256 evidence.
  Reusing an idempotency key with a different canonical payload is rejected. New active
  model versions supersede but do not delete prior evidence, and only a stable authorized
  human review can make an assessment eligible for alert creation.
- The implemented pest-report contract builds province, prefecture, or county reports
  only from explicitly selected human-approved assessments inside the persisted reporting
  period and real administrative scope. Open expert consultations block submission;
  answers require controlled PDF, Office, image, or ZIP artifacts with server-computed
  size and SHA-256. County quality inspection, prefecture project management, and province
  client review are capability-gated server transitions with immutable events. Province
  approval atomically produces a checksum-backed XLSX electronic ledger containing the
  report summary, assessment evidence, review trail, and consultation evidence, and the
  artifact is revalidated before download.
- The implemented UAV contract persists aircraft and sensor identity, aircraft
  certificates, pilot licences, district-contained WGS84 flight Polygons, missions,
  controlled physical artifacts, spatial findings, human review, and immutable events.
  Raster artifacts are inspected for CRS, resolution, dimensions, and WGS84 footprint;
  orthomosaics must cover the mission boundary and satisfy the planned resolution.
  Capture completion requires raw imagery plus a flight log, processing completion
  requires a qualifying orthomosaic, and review completion requires no pending findings.
  The TypeScript workbench provides an OpenLayers planning map with current imagery
  tiles, real administrative boundaries, mission Polygon drawing, task selection, and
  finding-coordinate picking while retaining all authoritative spatial validation on
  the server. A standalone mobile route lists only executable missions and atomically
  submits terminal GPS/accuracy/time, a signature-checked physical photo, and a linked
  spatial finding under a stable capture code; exact payload/photo digest retries are
  idempotent and conflicting reuse is rejected. Downloads revalidate controlled path,
  size, and SHA-256. These implemented contracts are not evidence that live flight-control
  integration, long-term archival retention, or 10,000-device scale testing are complete.

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
