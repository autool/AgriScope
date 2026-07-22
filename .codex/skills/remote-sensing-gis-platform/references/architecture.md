# Architecture and delivery reference

## Backend

- Routes accept requests, validate with Pydantic, call one or more Services, and return typed responses.
- Services own workflow decisions, authorization decisions, transactions, and custom business exceptions.
- DAOs own SQLAlchemy CRUD and spatial SQL. Bind every value; never interpolate SQL.
- Models contain ORM mappings only.
- Public functions and methods use explicit Python types and Chinese docstrings with `Args:` and `Returns:` where applicable.
- Use custom exceptions instead of raising `HTTPException` below Routes.
- Authorization decisions belong in Services and must resolve active persisted project users by stable user code. Client role labels are presentation data, never authorization evidence.
- Lock mutable workflow rows with `SELECT ... FOR UPDATE` before review state transitions to prevent concurrent double approval.

## Frontend

- Views compose page-level workflows and must stay small.
- Components implement reusable presentation or interaction units.
- Pinia Stores own business state, async orchestration, loading/error state, layout preferences, map state, and layer state.
- API modules are the only callers of the Axios instance in `request.ts`.
- Use TypeScript strict mode. Components use `<script setup lang="ts">`; `ref` names end in `Ref`, computed names end in `Computed`.
- Keep OpenLayers `Map` and Cesium `Viewer` inside map components. Expose narrow commands; never place raw instances in cross-component props.

## API and errors

- Target success envelope: `{"code": 200, "data": ...}`.
- Error bodies include `code` and safe Chinese `msg`, paired with the correct HTTP status.
- Request headers include `X-Requested-With`; token injection belongs in the interceptor.
- Show safe global error messages. Log raw stacks only on the server or in explicitly enabled development diagnostics.
- CORS must support `http://localhost:5173` and `http://localhost`.

## Database and GIS

- API geometry uses EPSG:4326. Ensure both operands of spatial predicates share the SRID.
- OpenLayers reads API GeoJSON with `dataProjection: 'EPSG:4326'` and `featureProjection: 'EPSG:3857'`.
- Add GIST indexes to queried geometry columns.
- Update `backend/scripts/init_db.sql` and add a migration or deterministic import script for schema/data changes.
- Store source name, source URI, version/date, administrative code, and parent code for external boundary snapshots.
- Keep generated delivery files outside source modules and checksum them.

## Containers

- Use multi-stage backend and frontend builds; serve production frontend through Nginx.
- Inject credentials through environment variables. Ignore local `.env` files.
- Configure health checks for PostGIS, backend, and frontend. Depend on healthy services rather than startup order alone.

## Verification and handoff

- Add Service tests for business decisions and schema tests for validation rules.
- Verify migrations against an existing development database and fresh initialization when possible.
- Verify browser behavior for interactive UI and GIS changes, including labels, toggles, empty states, and camera stability.
- Preserve user changes in dirty worktrees and avoid destructive Git commands.

## Commit preparation

- Before creating a commit, inspect the configuration that is effective at that moment: `commitlint.config.*`, `.commitlintrc*`, relevant `package.json` scripts and dependencies, `.husky/`, active `.git/hooks/`, `git config --get core.hooksPath`, and `pre-commit` configuration when present.
- Treat repository configuration as authoritative. Do not impose Conventional Commits or a fixed type/scope list when the repository does not require it.
- Write commit titles and bodies in Chinese. Describe the affected scope, important behavior, compatibility or migration impact, and verification evidence with professional, specific wording.
- Do not use `--no-verify` or otherwise bypass hooks unless the user explicitly authorizes it.
