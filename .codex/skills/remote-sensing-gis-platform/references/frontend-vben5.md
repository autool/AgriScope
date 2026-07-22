# Vben5-inspired frontend reference

## Source baseline

Reference project: `vbenjs/vue-vben-admin`, inspected at commit `0cd87c1` dated 2026-07-18. Use it as an architecture reference, not a dependency or visual skin.

Useful Vben5 patterns:

- Typed preference manager with defaults, persisted overrides, validation, reset, and CSS-variable updates.
- Basic layout composed from header, sidebar, tabbar, breadcrumb/content, footer, widgets, and named slots.
- Route metadata drives titles, access, caching, menus, transitions, and page behavior.
- Tabbar supports persistence, KeepAlive, refresh, maximize, close-other/all, dragging, and visit history.
- Content uses RouterView slots, optional KeepAlive, stable tab keys, and short transitions.
- Application-specific preferences extend framework defaults instead of modifying shared core defaults.

## Project adaptation

Keep the current application lean:

- `layoutStore.ts`: persisted typed preferences, sidebar state, content mode, density, workspace header, transition, and maximize state.
- `tabbarStore.ts`: visited routes, pinned home tab, active path, persistence, and close operations.
- `layouts/WorkbenchLayout.vue`: compose shell components only.
- `components/layout/`: route tabbar, content router, preference drawer, and future breadcrumb/global-search widgets.
- Router metadata: `title`, `description`, `fullWidth`, `keepAlive`, and later `roles`/`permissions`.

Do not:

- Migrate to Vben's monorepo packages solely for visual similarity.
- Duplicate Vben stores or components wholesale.
- Make every preference configurable before a real workflow needs it.
- Use route tabs to conceal poor information architecture.

## Operational UI principles

Use Linear-inspired restraint for dense workspace hierarchy:

- Use a 4px spacing base and compact 8/12/16/24 increments.
- Prefer surface steps and hairline borders over large shadows.
- Keep one primary accent; use semantic colors for status and severity only.
- Use stable split panes for map, layers, queue, and detail inspector.
- For province-wide GIS catalogs, pair a visible `province → prefecture → county work area → real parcel` directory with compact coverage counters, all 13 prefecture groups and all 122 county entries, and search. The prefecture overview must visibly render its county children instead of hiding them behind one scroll-tree branch. Parcel catalogs expand every populated county through individual parcels by default, boundary catalogs default to every prefecture expanded through county level, and compact prefecture/county/parcel controls let users change expansion depth without repetitive clicks.
- Pair administrative boundary layers with a map legend that differentiates province, prefecture, and county strokes and reports live region and plot counts; do not rely on subtle color differences alone.
- Use scale-aware map annotation: prefecture names and plot counts at province scale, county labels at closer scale, and individual plot geometry at editing scale.
- Keep the full hierarchy catalog independent from map geometry. Province overview loads boundaries and counts only; OpenLayers and Cesium request task-scoped full Polygon features for the current WGS84 viewport at editing scales. If the server reports the viewport exceeds its complete-load threshold, show the exact count and a clear zoom-in recovery action rather than rendering a partial sample.

Use Sentry-inspired behavior for quality and incident workflows:

- Separate normal, warning, and failed rules clearly.
- Put problem context, evidence, assignment, actions, and audit history near each other.
- Support fast recovery: retry, refresh, reopen, return for correction, and view raw evidence.

## Acceptance checks

- Sidebar collapse changes the actual grid width and keeps every route reachable.
- Route tabs update from route metadata, survive refresh when persistence is enabled, and cannot close the pinned home tab.
- Refresh remounts only the current route; it does not reload the entire browser.
- Maximize hides nonessential chrome but retains a visible exit control.
- KeepAlive can be disabled, and layout preferences survive a browser refresh.
- Spatial routes remain full width even when boxed content is selected.
- Page transitions never animate or change a Cesium camera.
- At 1080px width, navigation, map, panels, and primary actions remain usable without overlapping.
