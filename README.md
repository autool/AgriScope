# AgriScope — 遥感监测内业处理与成果审核平台

面向农业遥感监测业务的全栈 GIS 原型系统。系统使用 FastAPI、PostGIS、Vue 3、OpenLayers 与 Cesium，构建影像预处理、地块解译、质量检查、内外业核查和三级成果审核的一体化桌面工作台。

## 界面预览

### 项目总览

![AgriScope 项目总览](docs/images/dashboard.png)

### 地块解译工作台

![AgriScope 地块解译工作台](docs/images/interpretation-workbench.png)

### 生产调度

![AgriScope 生产调度](docs/images/production-scheduling.png)

### 规则配置

![AgriScope 规则配置](docs/images/rule-settings.png)

## 核心能力

- 卫星影像、解译图斑、灾害斑块、外业核查点和行政区划统一图层管理。
- 内置黑龙江省 1 条省界、13 条地级边界和 122 条县区边界真实数据快照。
- 提供真实 Polygon 绘制、节点编辑、PostGIS 图斑分割与合并、即时撤销/重做、软删除、属性赋值、面积重算、版本和审计闭环。
- 支持质量规则检查、问题定位、操作历史和三级审核流程展示。
- 支持人工审核问题填写复核依据后确认关闭；自动质检和外业问题仍必须通过各自复检流程闭环，不能人工绕过。
- 支持图斑历史版本恢复、审核通过/退回/驳回和整改闭环。
- 项目成员、角色和业务能力持久化；三级审核、版本回退、成果生成与下载均由后端角色门禁控制并记录用户编码和角色快照。
- 支持外业 CSV / Excel 实体文件原子导入、点斑空间匹配、偏移判定和疑点人工处置。
- 支持任务作用域内地级区域、县区、地类、作物、种植模式、权属村面积聚合，使用真实任务面积生成年度趋势，并由项目负责人导出 CSV。
- 支持外部灾害模型 GeoJSON 批量导入、PostGIS 面积与省域校验、分级渲染、受灾面积评估和人工复核确认。
- 支持辐射定标、大气校正、几何校正、裁剪和波段产品流水线。
- OpenLayers 二维地图与 Cesium 三维视图共享选中图斑和业务状态。
- 应用壳层参考 Vben5，支持持久化布局偏好、折叠侧栏、多标签页、KeepAlive、局部刷新和内容最大化。
- 支持 WGS84（EPSG:4326）坐标点查、地图点击查询和包围盒空间查询。
- 使用 PostGIS GIST 空间索引以及 SQLAlchemy 参数化空间表达式。
- 后端严格采用 Routes → Services → DAO → Models 四层结构。
- Docker Compose 一键启动 PostGIS、FastAPI 与 Nginx 前端网关。
- 政府采购业务扩展范围已纳入生产批次与任务分包、多源数据目录、多时相变化检测、独立监理、完整正射影像生产、专题制图、标准化归档、共享审批、涉密安全、无人机、田间物联网和病虫害智能预警。
- 已提供首组生产底座：九类多源数据资产及派生血缘、规则版本快照、生产批次、122 县区工作区、显式图斑作业包、负责人/期限/进度/合并校核/交付状态和不可变操作审计；未登记真实业务记录时保持真实空状态。

## 黑龙江省公开采购业务基线

项目已将黑龙江省政府采购网公开的国土变更调查、疑似变化图斑提取、高分辨率影像处理、生态遥感与野外验证、河湖动态监测、生产建设遥感监管和农作物病虫疫情田间监测项目纳入产品范围。新增能力按依赖关系持续开发：

1. 多源数据目录、技术规则包、生产批次和县区任务分包。当前生产底座已实现，后续继续补充实体资产核验和批量生产工具。
2. 多时相影像同步对比、变化候选生产、六类变化图斑判读与监理质检。
3. RPC/GCP、DEM 正射、区域网平差、配准、融合、匀色、镶嵌和覆盖率验收。
4. 历史影像溯源、专题图集、标准化成果归档和数据共享审批。
5. 无人机任务、田间监测站、物联网设备、AI 病虫害识别与风险预警。

公开采购文件中的最小图斑面积、完整率、边界吻合度、地类准确率、关键字段准确率和像素套合精度将作为可配置规则保存，不在业务代码中硬编码。公开或演示数据继续与正式业务、涉密数据严格区分。

## 项目开发 Skill

项目内置 Codex Skill：

```text
.codex/skills/remote-sensing-gis-platform/
```

使用 `$remote-sensing-gis-platform` 开展本项目功能开发、GIS 交互、Vben5 风格布局重构、后端分层、数据库迁移和交付验证。详细硬约束同时维护在 `CODEBUDDY.md`。

## 环境要求

- Docker 24+
- Docker Compose v2+
- 可选本地开发环境：Python 3.11、Poetry 1.8、Node.js 18+

## 快速启动

在项目根目录执行：

```bash
docker compose up -d --build
```

兼容旧版命令：

```bash
docker-compose up -d --build
```

服务启动完成后访问：

- 平台首页：<http://localhost>
- OpenAPI 文档：<http://localhost:8000/docs>
- 健康检查：<http://localhost:8000/health>

首次启动会自动创建 PostGIS 扩展、`farmland_plots` 表和 GIST 空间索引，导入黑龙江省完整的 1 个省级、13 个地级、122 个县级真实行政边界，并导入 35020 条覆盖全部 122 个县区的 OpenStreetMap 真实地类底块；按项目县界重新归属后，112 个县区分别不少于 20 块。每条底块保存省、地级区域、县区层级、OSM way/relation 来源编号、版本、更新时间和原始链接；该快照用于系统联调，不代表法定基本农田或法定地类调查成果。

## 本地开发

### 后端

```bash
cd backend
cp .env.example .env
poetry install
poetry run uvicorn app.main:app --reload
```

本地运行后端时，请将 `.env` 中数据库主机从 `postgis` 改为 `localhost`。真实 `.env` 文件已加入 `.gitignore`，不得提交到代码仓库。

### 前端

```bash
cd frontend
npm install
npm run dev
```

开发服务器会把 `/api` 和 `/health` 代理到 `http://localhost:8000`。

### 行政区划数据

版本化 GeoJSON 快照位于：

```text
backend/data/administrative_boundaries/heilongjiang_areas_v3_20260721.geojson
```

已有数据库可执行以下命令重新导入省、市、县区三级边界：

```bash
cd backend
poetry run python -m scripts.import_administrative_boundaries
```

导入采用事务替换，数据包含行政代码、父级代码、来源、快照版本和更新时间。

### 真实地类底块边界数据

版本化 GeoJSON 快照位于：

```text
backend/data/farmland/osm_heilongjiang_farmland_20260722.geojson
```

已有数据库可执行以下命令删除旧版 5 条规则矩形并导入真实边界：

```bash
cd backend
poetry run python -m scripts.import_osm_farmland
```

旧数据库升级任务图斑作用域时执行：

```bash
cd backend
psql "$POSTGRES_DSN" -f scripts/migrations/20260721_task_plot_scope.sql
psql "$POSTGRES_DSN" -f scripts/migrations/20260722_plot_split_operations.sql
psql "$POSTGRES_DSN" -f scripts/migrations/20260722_plot_operation_history.sql
psql "$POSTGRES_DSN" -f scripts/migrations/20260722_add_production_foundation.sql
```

其中 `POSTGRES_DSN` 使用 PostgreSQL 原生连接串。`task_plots` 明确保存任务与图斑的分配关系，质量检查、进度统计和提交门禁均以该作用域为准。

需要更新开放数据快照时，先通过 ohsome API 按真实县界补采并保留 OSM
来源元数据，再执行导入：

```bash
cd backend
poetry run python -m scripts.fetch_osm_farmland_snapshot --target-per-district 1000
poetry run python -m scripts.import_osm_farmland
```

快照包含 35020 条唯一 OSM Polygon，覆盖黑龙江省全部 13 个地级区域和 122 个县区；按来源县区统计，113 个县区分别不少于 20 块、84 个县区分别不少于 100 块、38 个县区分别不少于 300 块。数据同时支持 OSM way 与 relation；MultiPolygon relation 按真实组成面拆分，每个分片保留统一 relation 来源链接和独立来源编号。采集标签按业务地类明确映射：`farmland`、`greenhouse_horticulture`、`allotments` 为耕地；`orchard`、`plant_nursery`、`vineyard` 为园地；`forest` 为林地；`meadow`、`grass` 为草地；`reservoir`、`basin` 为水域；`residential`、`commercial`、`industrial`、`construction`、`farmyard` 为建设用地。禁止复制、简化真实几何凑数量，也禁止将不同标签静默冒充为同一地类。

每个县区通过确定性的网格轮询保留空间分散底块，面积筛选范围为 0.05–500 公顷，并接受闭合外环至少 5 个坐标的真实规则矩形。图层资源树按“省域 → 地级区域 → 县区作业大区 → 真实小地块”逐级下钻，目录顶部同时展示 13 个地级区域覆盖总览，二维/三维地图按六类地类差异化渲染。由于 OSM 原始要素通常不提供作物和权属村属性，这些字段保持待解译状态，不以推测值冒充业务成果。

空间工作台在目录顶部固定展示 1 个省级、13 个地级区域、122 个真实县界、122 个县区作业大区和当前真实小地块总数；地级区域总览默认把 13 个地级区域及其 122 个县区分组铺开，县区名称和地块数量不再隐藏在单条树分支中。地块目录继续默认展开全部县区到单地块，行政区划目录默认展开全部地级区域到县级，并提供地级/县区/地块展开控制及行政区或图斑搜索。全省比例尺下，地图使用真实地级行政边界显示各区域底块数量，放大后继续显示县区作业大区和单地块，避免小面积底块在省级视图中难以辨认。

资源目录与地图几何采用独立加载：任务目录只返回图斑编号、来源编号、地类和包围盒，
不携带 35020 个完整 Polygon；二维和三维地图在省级比例尺仅显示真实行政边界及
分级数量，进入县区尺度后按任务和当前 WGS84 视野加载完整图斑。单个视野超过
5000 个图斑时，接口返回真实匹配数量和“继续放大”状态，不返回任意截断子集冒充
完整结果。当前快照下，首屏目录载荷约 5.2 MB，替代原全省完整几何约 28 MB。

地图点查、坐标查询、编号边界、工作台属性和历史版本接口均要求携带当前
`task_code`，并通过 `task_plots` 校验分配关系。图斑存在于数据库但未分配给当前任务
时统一返回 HTTP 404“当前任务未找到”，不会泄露其他任务的数据；属性修改、几何编辑、
质量检查和版本回退继续在服务端重复校验同一任务作用域。

重新导入底块快照时，脚本会在同一事务中删除旧任务范围派生的
`plot_quality_checks`，仅关闭 `source=auto` 且 `issue_type=quality_rule` 的开放问题，
并追加稳定系统身份的失效审计。人工审核问题、外业问题及完整历史不会被删除或
冒充为当前门禁结果。

已有数据库清理早于最近底块重载周期的旧自动质检证据：

```bash
cd backend
psql "$POSTGRES_DSN" -f scripts/migrations/20260722_invalidate_legacy_quality_cycle.sql
psql "$POSTGRES_DSN" -f scripts/migrations/20260722_backfill_system_review_identity.sql
```

### 项目用户、审核与交付迁移

已有数据库升级项目用户角色、审核审计和成果交付约束时执行：

```bash
cd backend
psql "$POSTGRES_DSN" -f scripts/migrations/20260721_project_user_roles.sql
psql "$POSTGRES_DSN" -f scripts/migrations/20260721_delivery_role_scope.sql
```

当前内置内业解译员、外业核查员、质检员、项目负责人、甲方审核代表和独立监理六类项目身份。独立监理与质检员保持不同角色和能力，不能用质检记录冒充监理证据。前端身份切换仅用于联调不同职责，后端仍依据 `project_users.user_code` 独立校验能力。历史成果包若早于任务最新修改时间，或包内图斑数与 `task_plots` 当前作用域不一致，将保留为审计历史并禁止下载。

### 生产调度与多源数据目录

生产调度页由 `/api/v1/production/overview` 返回当前项目任务的真实聚合结果。县区工作区来自完整行政区划和 `task_plots` 任务范围，当前返回全部 122 个县区；没有生产批次或多源资产时返回 0 和空列表，不初始化虚构批次、负责人进度或完成状态。

多源目录覆盖影像、矢量、表格、DEM、控制资料、气象、管理信息、无人机和物联网九类数据，保存来源名称/地址、版本、SHA256、CRS、WGS84 范围、时段、密级、业务/演示标识及父资产血缘。登记记录统一标记为“待实体核验”，仅有来源元数据和客户端提交的校验值不会被描述为已验证生产成果。

生产批次创建时固化 `project_rule_configs.version` 和完整量化规则快照。县区拆包事务从当前任务和真实县区查询有效图斑，把每个 `plot_code` 写入 `work_package_plots`；计划面积和图斑量由数据库计算，后续进度同样根据显式关联和图斑解译状态实时聚合。批次/作业包创建、负责人/期限/状态变更均写入 `production_audit_events` 修改前后值和稳定用户角色快照。

成果包列表与生成接口不会只信任任务的 `completed` 状态，还会即时复核可验证业务
影像、任务图斑质量检查全覆盖、全部门禁通过、平均质量分、开放问题和待处置外业
疑点。质量报告和验收报告会区分真实专项记录与空集合；未提供外业记录或未导入灾害
成果时会明确写入报告，不会描述为已完成专项成果。

### 外业核查 CSV / Excel 导入

内外业核查页面支持最多 500 条记录的 CSV 或 `.xlsx` 文件导入。Excel 模板由后端
实时生成，包含标准表头、示例、字段说明和一级地类下拉选项。服务端校验 XLSX ZIP
结构、内部路径、加密状态、解压后体积、公式单元格、必填表头、WGS84 坐标、带时区
采集时间和照片证据；任一记录越界、重复或不合法时整批回滚。

实体 Excel 导入保存原始文件 SHA-256、来源 URI、版本、来源记录编号、上传人稳定编码
和角色快照，并在同一事务中完成点斑匹配、疑点生成、任务门禁重开和审核记录。CSV
继续使用相同的业务请求模型与原子导入事务。

### 灾害模型 GeoJSON 导入

灾害与长势监测页面支持导入 EPSG:4326 GeoJSON `FeatureCollection`。每个
`Polygon` 的 `properties` 必须包含 `patch_code`、`source_feature_id`、
`disaster_type`、`severity` 和 `detected_at`，可选 `crop_type` 与
`ndvi_change`。后端不信任客户端面积，而是通过 PostGIS geography 重算公顷面积，
并验证几何有效性和完整省域包含关系。

导入批次保存来源 URI、版本、来源要素编号、规范化 GeoJSON SHA-256、导入人编码和
角色快照。`reject` 策略发现重复编号时整批回滚；`replace` 策略仅按相同
`patch_code` 替换，并清空旧人工复核结论等待重新确认。初始化数据库不再生成规则
矩形灾害演示数据，未导入真实模型成果时页面显示明确空状态。

应用侧栏的影像、灾害和外业徽标由工作台概览接口实时返回：影像只统计具备实体
URI、文件大小和 SHA256 的业务资产，灾害和外业只统计当前任务仍待处置的记录；
没有真实数据时不显示固定占位数量。

顶部任务通知同样来自实时概览：业务影像缺失、开放质量问题、外业疑点、灾害待复核、
审核驳回和待生成成果包会形成可点击通知并跳转到对应模块。当前仅有一个项目，因此
项目区域只展示当前上下文，不使用无实际能力的下拉切换控件。

项目总览不再预设流程完成状态或固定进度。后端按影像实体及预处理状态、任务图斑
完成率、质量门禁覆盖与通过率、外业疑点处置、三级审核状态、当前有效成果包六个
阶段等权计算实时进度；缺少业务影像或存在未通过门禁时会明确显示受阻原因。

审核工作台将最近一次底块重载、审核退回/驳回、版本回退或外业批次导入之后的记录
定义为当前整改周期，概览最多返回最近 20 条当前周期记录，同时单独返回当前周期和
完整历史总数。完整审计仍保留在数据库并进入成果交付包，旧联调周期不会冒充本轮
审核依据。

已有数据库清理旧固定进度值：

```bash
cd backend
psql "$POSTGRES_DSN" -f scripts/migrations/20260722_dynamic_workflow_progress.sql
```

已有数据库执行：

```bash
cd backend
psql "$POSTGRES_DSN" -f scripts/migrations/20260722_disaster_geojson_import.sql
```

### 任务面积统计与 CSV 导出

面积统计只聚合 `task_plots` 明确分配给当前任务且未删除的图斑，禁止从全库活动图斑
推断任务范围。接口同时返回地级区域、县区、一级地类、作物类型、种植模式和权属村
六类分组，以及耕地图斑作物录入完成率。当前监测年度使用任务实时面积；只有导入
真实历史统计快照后才展示历史年度，不再使用初始化固定趋势数值。

项目负责人可在统计页面上传 UTF-8 CSV 历史成果，字段为 `monitor_year`、
`total_area_ha`、`farmland_area_ha`、`crop_area_ha`。历史年度必须早于当前监测年度，
耕地面积不得超过总面积、作物面积不得超过耕地面积。导入批次保存原始文件 SHA256、
来源 URI、版本、冲突策略、项目负责人稳定编码和角色，以及不可变的原始年度载荷；
选择替换已有年度时，旧批次仍保留为审计证据。平台不会自动生成或保留虚构历史值。

CSV 包含任务编号、监测年度、导出人稳定编码和角色，以及各维度面积、公顷/亩换算、
占比和年度趋势。只有项目负责人具备后端 `export_statistics` 能力。

已有数据库执行以下迁移清理旧固定年度数值：

```bash
cd backend
psql "$POSTGRES_DSN" -f scripts/migrations/20260722_statistics_task_scope.sql
psql "$POSTGRES_DSN" -f scripts/migrations/20260722_statistics_history_import.sql
```

## 可选 3D Tiles

在前端环境变量中配置 `VITE_CESIUM_3D_TILES_URL` 后，三维视图会加载对应瓦片集。代码固定设置 `maximumScreenSpaceError = 2`，用于保证监管场景下的显示精度。

## 影像处理执行与外部产物登记

影像处理页可直接使用平台内置 Rasterio 处理器执行标准五步流水线：按显式比例系数
和偏移量完成 DN 定标、使用 DOS1 暗目标法进行基础大气校正、重投影到指定 CRS、
按数据库真实行政区边界裁剪，并生成真彩色、标准假彩色和 NDVI 七波段产品栈。
每个输出先写临时 GeoTIFF，再原子替换到受控目录并记录源文件 SHA256、执行参数、
输出尺寸、波段数、数据类型、CRS、处理器版本和操作人角色快照。重跑上游步骤会
自动失效下游结果，并把旧实体证据移入历史记录，避免过期产品继续计入完成率。

外部 GDAL、6S、FLAASH 或生产调度工具完成处理后，应先将 GeoTIFF、IMG 或
HDF 产物放入 `backend/storage/imagery/`，再通过影像处理页面登记相对路径、
处理器名称和版本。后端会校验存储目录边界、文件格式签名、文件大小和 SHA256；
缺少实体文件的步骤不会计入完成率，产品卡片也不会显示为已生成。

数据资产页支持直接上传 GeoTIFF、IMG 和 HDF。后端使用 Rasterio 从实体文件
读取驱动格式、CRS、WGS84 覆盖范围、像元分辨率、栅格尺寸、波段描述和标签，
文件保存于持久化的 `backend_storage` 卷，并通过 SHA256 阻止重复入库。

传感器优先从 `SATELLITE`、`PLATFORM`、`SPACECRAFT_NAME`、`SENSOR`、
`INSTRUMENT` 等标签提取；采集时间支持 `ACQUIRED`、`ACQUISITION_TIME`、
`DATE_ACQUIRED`、`TIFFTAG_DATETIME` 等常见字段；处理级别和云量分别从
`PROCESSING_LEVEL` / `PRODUCT_LEVEL` 与 `CLOUD_COVER` /
`CLOUDY_PIXEL_PERCENTAGE` 等标签读取。标签键大小写不敏感，无时区日期按 UTC
记录明确假设。文件缺失业务标签时才采用人工补录；人工值与文件标签冲突时整次入库
失败。最终值、文件标签、人工值、精度和来源保存在
`raster_metadata.business_metadata` 中供审核追溯。

初始化脚本不再写入固定 GF2 元数据占位记录。未上传可用业务影像时，工作台返回
`imagery: null` 并显示明确空状态；质量检查将影像覆盖标记为缺失门禁。只有具备实体
文件 URI、文件大小和 SHA256 的 `operational` 资产才可作为当前业务影像。标记为
`demo` 的实体影像始终显示“明确演示”，不得用于正式成果表述。

影像入库表单不会预填传感器、采集时间或处理级别，这些字段作为文件标签缺失时的
受控补录项；文件仅提供采集日期时，可人工补充同日精确时刻。地块创建、批量赋值和
分割说明也不再使用固定卫星或固定日期作为默认依据。初始化脚本不会生成固定人员、
固定时间的审核记录。

已有数据库清理旧无实体占位影像：

```bash
cd backend
psql "$POSTGRES_DSN" -f scripts/migrations/20260722_remove_placeholder_imagery.sql
psql "$POSTGRES_DSN" -f scripts/migrations/20260722_remove_seeded_task_audit.sql
```

## API 概览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 应用与数据库健康检查 |
| POST | `/api/v1/plot/query-point` | 按 WGS84 坐标点查图斑 |
| GET | `/api/v1/plot/boundary` | 按编号获取 GeoJSON 边界 |
| POST | `/api/v1/plot/bbox` | 查询包围盒相交图斑 |
| GET | `/api/v1/plot/catalog` | 查询任务作用域轻量分级地块目录 |
| POST | `/api/v1/plot/viewport` | 按任务和当前视野受控加载完整地块几何 |
| GET | `/api/v1/plot/click` | 二三维地图点击查询 |
| GET | `/api/v1/workbench/overview` | 获取项目、任务、影像和审核工作台概览 |
| GET | `/api/v1/project-users` | 查询项目启用用户、角色和业务能力 |
| POST | `/api/v1/workbench/plots` | 创建人工解译图斑并生成初始版本 |
| PATCH | `/api/v1/workbench/plots/{plot_code}/geometry` | 保存节点编辑边界并重算面积 |
| DELETE | `/api/v1/workbench/plots/{plot_code}` | 软删除图斑并保留版本审计 |
| POST | `/api/v1/workbench/tasks/{task_code}/plots/{plot_code}/split` | 使用 WGS84 分割线拆分图斑并生成子图斑、版本和操作审计 |
| POST | `/api/v1/workbench/tasks/{task_code}/plots/merge` | 合并显式选择的同县相邻图斑并人工确认冲突属性 |
| GET | `/api/v1/workbench/tasks/{task_code}/plot-operations/history-state` | 查询当前可撤销和可重做的分割/合并操作 |
| POST | `/api/v1/workbench/tasks/{task_code}/plot-operations/undo` | 撤销最近一个有效操作并生成新版本及事件审计 |
| POST | `/api/v1/workbench/tasks/{task_code}/plot-operations/redo` | 重做最近一个未失效操作并生成新版本及事件审计 |
| POST | `/api/v1/workbench/tasks/{task_code}/quality-checks/run` | 一次事务运行任务全部图斑质检并返回规则汇总 |
| GET | `/api/v1/workbench/tasks/{task_code}/quality-issues` | 分页筛选质量问题并返回关联图斑和规则统计 |
| PATCH | `/api/v1/workbench/tasks/{task_code}/quality-issues/{issue_id}/resolve` | 授权审核人确认关闭人工审核问题并保存复核审计 |
| POST | `/api/v1/workbench/tasks/{task_code}/plots/batch-attributes` | 对显式勾选图斑批量赋值并逐图生成新版本 |
| POST | `/api/v1/workbench/tasks/{task_code}/submit` | 通过全量质量门禁后提交内业自检 |
| GET | `/api/v1/field-verifications` | 获取内外业核查记录和空间匹配统计 |
| POST | `/api/v1/field-verifications/import-csv` | 原子导入已解析 CSV 外业记录并执行空间匹配 |
| POST | `/api/v1/field-verifications/import-xlsx` | 安全解析 XLSX 实体文件、审计文件 SHA256 并原子导入 |
| GET | `/api/v1/field-verifications/import-template.xlsx` | 下载服务端生成的外业 Excel 标准模板 |
| POST | `/api/v1/reviews/tasks/{task_code}/actions` | 执行三级审核状态流转 |
| GET | `/api/v1/reviews/plots/{plot_code}/versions` | 查询图斑历史版本 |
| POST | `/api/v1/reviews/plots/{plot_code}/rollback` | 恢复历史版本并生成新版本 |
| GET | `/api/v1/statistics/area-summary` | 获取多维面积统计和年度趋势 |
| GET | `/api/v1/statistics/area-summary/export.csv` | 项目负责人导出任务作用域多维面积统计 CSV |
| POST | `/api/v1/statistics/annual-snapshots/import-csv` | 项目负责人导入真实历史年度统计并保存文件与角色审计 |
| GET | `/api/v1/statistics/annual-snapshots/import-template.csv` | 下载历史年度统计标准模板 |
| GET | `/api/v1/disasters/summary` | 获取灾害斑块和受灾范围汇总 |
| POST | `/api/v1/disasters/import-geojson` | 批量导入灾害模型 GeoJSON，重算面积并保存来源审计 |
| PATCH | `/api/v1/disasters/{patch_code}` | 人工修正灾害等级和确认状态 |
| GET | `/api/v1/imagery-assets/{asset_code}/processing` | 查询影像预处理流水线 |
| POST | `/api/v1/imagery-assets/{asset_code}/processing/{step_code}/run` | 校验并登记外部处理实体产物 |
| POST | `/api/v1/imagery-assets/{asset_code}/processing/{step_code}/execute` | 使用内置处理器执行步骤并生成受控实体产物 |
| GET | `/api/v1/imagery-assets` | 查询项目真实影像资产目录 |
| POST | `/api/v1/imagery-assets` | 上传影像文件并自动读取栅格与空间元数据 |
| GET | `/api/v1/deliveries` | 查询交付门禁、当前/历史成果包和失效原因 |
| POST | `/api/v1/deliveries/generate` | 项目负责人生成任务作用域成果 ZIP |
| GET | `/api/v1/deliveries/{package_code}/download` | 经角色、时效、大小和 SHA-256 校验后下载成果包 |
| GET | `/api/v1/rule-configs` | 查询项目当前质量与外业校核规则 |
| PATCH | `/api/v1/rule-configs` | 更新项目规则并保存修改前后值审计 |

## 数据安全

- 所有空间查询均由 SQLAlchemy 生成参数化 SQL，不拼接用户输入。
- 数据库异常统一转换为安全提示，原始堆栈仅记录在服务端日志。
- API 经纬度均校验为 WGS84 合法范围。
- 生产环境应通过密钥管理系统覆盖示例数据库密码，并限制数据库端口暴露。

## 开源许可

AgriScope 基于 [Apache License 2.0](LICENSE) 开源。

允许个人和企业使用、修改、分发及商业化，但须保留版权、许可和变更说明。项目包含的行政区划、OpenStreetMap 快照及其他公开数据仍遵循各自来源的授权和署名要求；这些联调数据不代表法定基本农田或法定调查成果。第三方数据归属说明见 [NOTICE](NOTICE)。
