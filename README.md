# AgriScope — 遥感监测内业处理与成果审核平台

面向农业遥感监测业务的全栈 GIS 原型系统。系统使用 FastAPI、PostGIS、Vue 3、OpenLayers 与 Cesium，构建影像预处理、地块解译、质量检查、内外业核查和三级成果审核的一体化桌面工作台。

## 界面预览

### 项目总览

![AgriScope 项目总览](docs/images/dashboard.png)

### 地块解译工作台

![AgriScope 地块解译工作台](docs/images/interpretation-workbench.png)

### 生产调度

![AgriScope 生产调度](docs/images/production-scheduling.png)

### 公开 Sentinel-2 实体影像

![AgriScope 公开 Sentinel-2 实体影像](docs/images/imagery-public-sentinel.png)

### 历史影像覆盖矩阵与问题追溯

![AgriScope 历史影像覆盖矩阵与问题追溯](docs/images/imagery-history-coverage.png)

### GCP 几何精校正

![AgriScope GCP 几何精校正](docs/images/imagery-gcp-correction.png)

### 双景自动配准与像素残差验收

![AgriScope 双景自动配准与像素残差验收](docs/images/imagery-registration.png)

### 真实双时相变化检测与候选判读

![AgriScope 真实双时相变化检测与候选判读](docs/images/change-detection-real-run.png)

### 影像增强

![AgriScope 影像增强](docs/images/imagery-enhancement.png)

### 多景匀色、镶嵌与覆盖率验收

![AgriScope 多景匀色、镶嵌与覆盖率验收](docs/images/imagery-mosaic-workflow.png)

### 多光谱与全色影像融合

![AgriScope 多光谱与全色影像融合](docs/images/imagery-fusion.png)

### 专题制图工作台

![AgriScope 专题制图工作台](docs/images/thematic-map-workbench.png)

### 成果交付与标准化归档

![AgriScope 成果交付与标准化归档](docs/images/delivery-archive.png)

### 多格式矢量成果导出

![AgriScope 多格式矢量成果导出](docs/images/vector-export-modal.png)

### 数据共享服务

![AgriScope 数据共享服务](docs/images/service-sharing-workbench.png)

### 无人机任务与成果核验

![AgriScope 无人机任务与成果核验](docs/images/uav-workbench.png)

### 病虫害报告与专家会商

![AgriScope 病虫害报告与专家会商](docs/images/monitoring-report-workbench.png)

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
- 支持外业 CSV / Excel 原子导入、原始 XLSX 受控保存、点斑空间匹配、偏移判定和疑点人工处置；处置完整覆盖保留内业、采用外业、显式折中、驳回外业和重新打开，实际改图生成不可变版本，未匹配记录不能虚构图斑修改；现场照片、语音和调查表作为独立实体执行格式、大小、SHA-256 与稳定用户角色审计，历史 URL 明确标为未经校验引用。
- 支持任务作用域内地级区域、县区、地类、作物、种植模式、权属村面积聚合，使用真实任务面积生成年度趋势，并由项目负责人导出 CSV。
- 支持从真实任务图斑按县区和六类地类筛选，生成 GeoJSON、ESRI Shapefile、OGC KML 2.2、OpenFileGDB 四种实体矢量成果；服务端复核要素数量、EPSG:4326、中文属性、逐文件大小和 SHA-256，任务变化后旧版本自动转为审计历史。
- 支持外部灾害模型 GeoJSON 批量导入、PostGIS 面积与省域校验、分级渲染、受灾面积评估和人工复核确认；全部斑块闭环后可生成含空间分布图、等级/类型图表、明细及来源 SHA-256 的 XLSX 实体专题报告，下载和成果归档前重新校验。
- 支持辐射定标、DOS1 大气校正、普通重投影、GCP 仿射精校正、RPC+DEM 严格正射、真实行政区裁剪、百分位拉伸、直方图均衡化和波段产品流水线；GCP 按像素 RMSE 门禁，RPC 正射校验 DEM 实体、覆盖范围和 SHA-256。
- 支持两景不同 `operational` 影像步骤实体的相位相关平移配准：服务端自动计算初始位移、有效重叠率和相关峰旁比，将待配准影像写入参考影像同网格 GeoTIFF，再从实体输出复算像素残差并按项目位置精度规则验收。
- 支持 2–20 景不同影像资产的全局均值/标准差匀色、首景优先或重叠均值合成和真实行政区覆盖率验收。服务端按栅格块处理并限制输出像元数，以完整行政区作为覆盖率分母，只有通过门槛的 GeoTIFF 才会原子落盘并保存输入血缘、大小和 SHA-256。
- 支持从 Element 84 Earth Search 公共 STAC 查询并裁取 Sentinel-2 L2A 蓝、绿、红、近红外四个同网格 COG；强制读取 Raster Extension 的 `scale`、`offset` 和 `nodata` 并转换为浮点 BOA 地表反射率，再复用平台入库门禁。保存 STAC 条目、原始波段 URL、产品 URI、处理基线、公开许可、空间范围、文件大小和 SHA-256。
- 支持历史影像覆盖矩阵与问题追溯：后端以完整 13 个地级区域、122 个县区真实 geography 面积为分母，批量计算每景 WGS84 足迹的县区覆盖率并保留零覆盖单元；时间线重新校验源文件和处理步骤实体 SHA-256，展示入库、必选步骤待办、产物失效、历史替换和演示数据状态，不生成固定年份或虚构历史时相。
- 影像预处理页不再使用固定瓦片冒充当前资产预览：服务端从所选实体源栅格生成带源文件 SHA-256、WGS84 范围、波段索引和 PNG 校验值的真实快视图；真彩色、标准假彩色和 NDVI 仅从已通过实体校验的 `band_products` 七波段产物生成，缺失时明确显示不可用。快视图只用于核验，不计入处理完成率。
- 支持创建绑定两期真实影像、规则版本、任务图斑范围和已校验实体配准成果的多时相变化检测任务；前端不能再手工填写偏差或任意证据 URI。服务端以配准 GeoTIFF 作为后时相来源，将两期栅格生成共同拉伸、带 SHA 清单的卷帘/闪烁/并排预览；既可原子导入外部候选 GeoJSON，也可基于该实体公共网格执行可配置 RGB 差分和四邻域连通域矢量化，避免角点相接像元形成无效自接触 Polygon，并保存算法版本、参数、源/成果 SHA 与实体 GeoJSON。自动候选保持“未分类”，必须由人工归入六类之一后才能确认，重分类与排除均保留不可变审计历史。
- 支持与自动质检和三级审核相互独立的项目监理闭环：独立监理按真实任务图斑执行系统抽样或县区分层随机抽样，固化图斑版本与任务范围快照；过程检查保存实体证据地址，生产团队提交整改，独立监理逐轮复检，并完成县区量化评价。全部门禁通过后生成带大小、SHA-256 和完整证据清单的不可变 JSON 监理报告。
- 支持从已校验 `band_products` 实体栅格批量生成真彩色、标准假彩色和 NDVI 专题图，输出 PNG/PDF 实体文件。版式包含图名、图廓、指北针、比例尺、图例、制图单位、日期和图号；清单同时保存来源 URI/SHA-256、STAC/许可/密级血缘、渲染参数、成图大小与 SHA-256，预览和下载前重新校验实体，公开数据显式标注“非法定调查成果”。
- 成果 ZIP 采用标准目录归档任务矢量、统计、灾害、外业记录、外业照片/语音/调查表实体、原始 XLSX 工作簿、证据事件、质量、审核、报告、真实专题图和独立监理报告；影像源与处理产物通过重新校验的 URI、大小和 SHA-256 血缘引用，多源数据资产目录与归档状态索引一并写入。除清单自身外，每个内嵌文件保存大小和 SHA-256；新增专题图、监理报告、数据资产或影像处理产物会使旧包失效，新版本生成时旧版本明确转为审计历史。
- 支持地图与数据服务受控共享：项目负责人登记服务和真实资源证据，甲方审核代表独立审批；项目成员提交用途和期限明确的访问申请，项目负责人审批并可签发只显示一次的 API Key。数据库仅保存密钥 SHA-256 和末四位，支持真实健康探测、SSRF 内网防护、调用指标审计、单凭证撤销和服务级批量吊销。
- 支持田间监测网络与病虫害预警闭环：监测站坐标必须落在申报县区真实边界内，设备保存厂商、型号、序列号、权属和照片实体 SHA-256；遥测通过设备级幂等键写入，故障驱动设备异常状态并以处置回执闭环。病虫害模型保存实体版本、训练/评估来源和 Accuracy/Recall/F1/ROC AUC，识别结果必须人工复核后才能创建告警，送达时登记真实回执实体。
- 支持从已人工批准的病虫害识别结果显式组卷省、地级、县级监测报告，按县级质检、地级项目负责人、省级甲方三级审核流转；未答复专家会商会阻断提交，省级通过后生成带实体大小和 SHA-256 的 XLSX 电子台账，下载前再次校验文件。
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
2. 多时相变化检测已实现真实影像资格、实体配准成果强制绑定、任务与规则快照、已配准目标栅格公共网格卷帘/闪烁/并排、外部候选 GeoJSON 导入、内置 RGB 差分自动候选发现、六类变化判读和不可变审计；后续继续补充多算法配置。
3. 独立项目监理已实现真实任务图斑抽样、过程检查、问题整改、逐轮复检、县区评价和不可变实体报告；当前数据库无业务监理记录时保持真实空状态。
4. GCP 仿射精校正、RPC/DEM 正射、平移自动配准、影像增强、基础多景镶嵌和全色融合已实现：支持 RPC-only 原始影像入库、控制点残差门禁、受控 DEM 覆盖校验、服务端相位相关位移与实体残差复核、变化检测强制绑定配准成果、百分位拉伸、直方图均衡化、2–20 景全局均值/标准差匀色、完整行政区覆盖率门禁，以及同景多光谱/单波段全色实体的分块直方图匹配 Brovey 融合。当前开发数据库已接入 Google Cloud Public Datasets / USGS 的 Landsat-8 场景 `LC08_L1TP_117028_20200724_20200807_01_T1`，按 MTL 系数生成 30m B2/B3/B4 与 15m B8 TOA 反射率实体。真实融合有效重叠率为 99.4537%，三波段最低光谱相关系数为 0.872138，空间细节增益为 1.903269，并保存 15m GeoTIFF、SHA-256 与完整输入血缘。区域网平差、高级缝线优化和全省规模压测仍待继续建设。
5. 专题制图已实现持久化版式模板、真实波段产品批量成图、PNG/PDF 实体输出、双 SHA-256 校验、公开数据标识和角色审计；标准化交付归档已纳入真实专题图、监理报告、影像处理血缘、多源资产目录、逐文件 SHA-256 和归档源变化失效判断。数据共享已实现注册、甲方审批、访问申请、一次性凭证、健康检查、调用审计和撤销。历史影像覆盖矩阵和处理问题时间线已按实际入库时相实现；当前没有 1980–2024 完整影像语料时保持真实时间范围。完整图集编排、长期历史语料接入和源栅格离线封存仍待继续建设。
6. 田间监测站、物联网设备、幂等遥测、设备故障闭环、AI 病虫害模型版本、人工复核与告警送达已实现；病虫害报告已支持真实识别结果组卷、专家会商实体答复、县市省三级审核和 XLSX 电子台账。无人机任务及地图化规划已实现，移动端采集、飞控实时接入与 10000 台设备规模验证仍待继续建设。

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
psql "$POSTGRES_DSN" -f scripts/migrations/20260722_change_detection_workflow.sql
psql "$POSTGRES_DSN" -f scripts/migrations/20260722_independent_supervision_workflow.sql
psql "$POSTGRES_DSN" -f scripts/migrations/20260722_thematic_map_workflow.sql
psql "$POSTGRES_DSN" -f scripts/migrations/20260722_service_sharing_workflow.sql
psql "$POSTGRES_DSN" -f scripts/migrations/20260722_imagery_enhancement_step.sql
psql "$POSTGRES_DSN" -f scripts/migrations/20260722_imagery_mosaic_workflow.sql
psql "$POSTGRES_DSN" -f scripts/migrations/20260722_imagery_registration_workflow.sql
psql "$POSTGRES_DSN" -f scripts/migrations/20260722_change_detection_registration_binding.sql
psql "$POSTGRES_DSN" -f scripts/migrations/20260723_imagery_fusion_workflow.sql
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

### 独立项目监理

独立监理页由 `/api/v1/supervision/overview` 返回完整 122 县区真实任务范围和监理业务状态。创建计划时只读取 `task_plots` 中的图斑身份、县区和版本，不加载全省完整 Polygon；系统抽样或县区分层随机抽样均可按同一计划编号复现，每个计划最多 5000 个样本，超过上限时明确拒绝而不截断。

监理计划固化任务图斑数量和任务更新时间。基础数据变化后，旧计划不能继续登记检查或生成报告。整改由内业、质检或项目负责人提交，复检、县区评价和报告生成只能由独立监理执行。报告生成要求至少一次过程检查、全部问题闭环、所有抽样县区完成评价，并写入受控目录；下载前重新校验实体文件大小和 SHA-256。

### 专题制图

专题制图页由 `/api/v1/thematic-maps/overview` 返回当前项目的持久化版式、可用实体影像来源和任务成果。来源资格只接受已完成并通过物理文件、大小和 SHA-256 校验的 `band_products` 产物；专题图渲染直接读取该实体栅格，不复用影像快视图缓存，也不会把快视图状态冒充制图完成状态。

项目负责人可保存图幅尺寸、DPI、页边距、图例位置、图廓、指北针、比例尺、标题模式和真实制图单位，并在一批请求中生成 1–12 张真彩色、标准假彩色或 NDVI PNG/PDF。每张成图清单保存来源 URI 与 SHA-256、STAC 条目、许可、密级、产品基线、实际波段描述、拉伸或值域、版式、渲染器版本、成图大小和成图 SHA-256；写出失败时整批回滚数据库记录和临时文件。

公开 Sentinel-2 成图在图面上持续显示“公开数据 · 非法定调查成果”。解译员可在线预览经重新校验的 PNG，项目负责人拥有批量生成和附件下载权限；每次预览与下载分别记录稳定用户编码和角色快照。专题制图模块本身不承担区域网平差、全色融合、高级镶嵌缝线或完整图集编排。

### 生产调度与多源数据目录

生产调度页由 `/api/v1/production/overview` 返回当前项目任务的真实聚合结果。县区工作区来自完整行政区划和 `task_plots` 任务范围，当前返回全部 122 个县区；没有生产批次或多源资产时返回 0 和空列表，不初始化虚构批次、负责人进度或完成状态。

多源目录覆盖影像、矢量、表格、DEM、控制资料、气象、管理信息、无人机和物联网九类数据，保存来源名称/地址、版本、SHA256、CRS、WGS84 范围、时段、密级、业务/演示标识及父资产血缘。登记记录统一标记为“待实体核验”，仅有来源元数据和客户端提交的校验值不会被描述为已验证生产成果。

生产批次创建时固化 `project_rule_configs.version` 和完整量化规则快照。县区拆包事务从当前任务和真实县区查询有效图斑，把每个 `plot_code` 写入 `work_package_plots`；计划面积和图斑量由数据库计算，后续进度同样根据显式关联和图斑解译状态实时聚合。批次/作业包创建、负责人/期限/状态变更均写入 `production_audit_events` 修改前后值和稳定用户角色快照。

成果包列表与生成接口不会只信任任务的 `completed` 状态，还会即时复核可验证业务
影像、任务图斑质量检查全覆盖、全部门禁通过、平均质量分、开放问题和待处置外业
疑点。质量报告和验收报告会区分真实专项记录与空集合；未提供外业记录或未导入灾害
成果时会明确写入报告，不会描述为已完成专项成果。

新成果包使用 `vector/`、`statistics/`、`disasters/`、`field/`、`quality/`、
`review/`、`reports/`、`thematic_maps/`、`supervision/` 和 `archive/` 标准目录。
生成前重新校验当前影像源、全部已完成处理产物、专题图和监理报告实体；专题图与监理
报告直接写入 ZIP，影像源和大体量处理中间栅格通过 `archive/imagery_lineage.json`
保存受控 URI、实体大小和 SHA-256 引用，多源资产写入 `archive/dataset_catalog.json`，
各类证据的“已纳入/校验后引用/未提供”状态写入 `archive/archive_index.json`。

`manifest.json` 保存每个内嵌文件的路径、分类、格式、记录数、来源实体、文件大小和
SHA-256。任务图斑、专题图、监理报告、多源资产目录或当前影像处理产物发生变化后，
历史包立即禁止作为当前成果下载；生成新版本时旧 `completed` 包统一转为
`superseded`，确保同一任务只有一个当前交付版本。当前实现是可校验交付包闭环，尚不
把大体量源栅格完整复制进 ZIP，因此不宣称已经完成长期离线介质封存。

### 数据共享服务

数据共享页使用 `shared_services`、`service_access_requests`、
`service_credentials`、`service_health_checks` 和 `service_usage_events` 保存完整工作流。
项目负责人登记服务地址、健康地址、接口文档、资源编号、资源 SHA-256、密级、暴露
范围、鉴权方式和责任单位；影像、专题图、成果包及多源目录等内部资源必须与数据库
真实实体和 SHA-256 一致，客户端自行填写的校验值不能直接获得发布资格。

服务登记后固定进入 `pending_approval`，只有甲方审核代表具备独立批准或驳回能力。
涉密资源禁止发布到公共范围，公共服务必须使用 HTTPS，非公共服务必须配置鉴权。
项目成员可对已激活服务提交包含申请单位、明确用途和最长 365 天期限的访问申请；
API Key 模式批准后密钥明文只返回一次，数据库仅保存 SHA-256 哈希和末四位。

健康检查由后端实际访问登记地址，保存 HTTP 状态、响应时间、检查人和检查时间。
默认拒绝环回、私网、链路本地、保留和组播地址，离线部署确有需要时通过
`SERVICE_HEALTH_PRIVATE_HOST_ALLOWLIST` 显式列出可信主机。服务调用审计必须通过
项目负责人身份或有效 API Key 哈希校验，保存方法、路径、响应状态、耗时和字节数。
撤销单个凭证或整个服务均保留不可变事件；服务撤销时同一事务吊销全部活动凭证。

当前联调目录登记的是公开 Element 84 Earth Search STAC，已经由项目负责人登记、
甲方审核代表批准，并完成一次 HTTP 200 的真实健康探测。该记录用于公开 Sentinel-2
影像检索，不代表平台对外发布了涉密或法定调查成果。

### 田间监测网络与病虫害预警

田间监测页使用 `monitoring_stations`、`monitoring_devices`、`device_telemetry`、
`device_faults`、`pest_model_versions`、`pest_assessments`、`pest_alerts` 和
`monitoring_events` 保存完整业务链。监测站登记时由 PostGIS 校验 WGS84 坐标确实
位于申报县区真实边界内，并保存来源、版本、权属、照片或验收证据的大小和 SHA-256；
设备保存厂商、型号、序列号、安装时间、权属、状态和照片实体证据。

遥测接口以设备和 `idempotency_key` 组成唯一键。相同键和相同载荷重复上报时返回原
记录，不重复写库；相同键对应不同载荷时明确拒绝。遥测支持数值、JSON 原始载荷及
可选图像实体，在线、离线、异常、维护和退役状态与故障流程保持一致。故障登记后设备
进入异常状态，只有提交处置说明以及回执 URI、大小和 SHA-256 后才能关闭。

病虫害模型版本保存训练来源、评估来源、部署目标、模型实体及 Accuracy、Recall、F1、
ROC AUC 指标；登记新活动版本时旧活动版本转为 `superseded` 并保留替代关系。模型识别
记录保存输入实体、置信度和预测依据，必须由具备能力的真实项目用户批准或驳回；未经
批准不得创建告警。告警保存渠道和真实接收对象，实际送达后必须登记回执实体校验值。
所有动作写入不可变事件，初始化脚本不创建固定站点、设备、模型或告警。

病虫害监测报告使用 `pest_reports`、`pest_report_items` 和
`expert_consultations` 保存报告主表、识别电子台账与专家会商。报告只能显式选择报告
周期内、属于申报行政范围且已经人工批准的识别结果；草稿和退回状态允许修订或发起
会商，存在未答复会商时禁止提交。会商答复必须上传 PDF、Office、图片或 ZIP 实体，
文件大小与 SHA-256 均由服务端计算。

报告按 `draft/returned → county_review → prefecture_review → province_review → approved`
流转，县级由质检员审核、地级由项目负责人审核、省级由甲方审核，任一级均可填写依据
退回。省级通过后服务端原子生成 XLSX，包含报告摘要、识别电子台账、审核与会商证据；
下载前重新核对受控路径、大小和 SHA-256。前端只展示服务端状态和能力门禁，不自行判定
报告完成。初始化脚本不创建固定报告或会商记录，真实无数据时保持空态。

### 无人机飞行任务与成果核验

无人机任务页使用 `uav_aircraft`、`uav_missions`、`uav_artifacts`、
`uav_findings` 和 `uav_events` 保存航空器、飞手资质、飞行范围、实体成果、空间疑点
和不可变审计。航空器登记必须上传登记或适航证书实体；任务创建必须上传飞手执照，
并由 PostGIS 验证 WGS84 飞行 Polygon 完整位于申报县区真实边界内。

原始影像、航迹、照片、视频、正射、DEM 和报告均写入受控存储并保存文件大小与
SHA-256。正射及 DEM 由 Rasterio 提取 CRS、分辨率、尺寸和 WGS84 覆盖范围；正射成果
必须完整覆盖任务范围。任务按 `planned → in_progress → captured → processed → reviewed`
流转：完成采集前必须具备原始影像和航迹，完成处理前必须具备满足任务目标分辨率与
覆盖要求的正射实体，完成审核前必须清空待复核疑点。

疑点坐标必须落在任务飞行范围内，关联图斑必须属于当前任务；人工确认或排除均保存
稳定用户编码、角色快照、复核依据和时间。成果下载前重新核对受控路径、文件大小与
SHA-256。初始化脚本不创建固定航空器、任务、成果或疑点，工作台在无记录时展示数据库
真实空态。

无人机页面提供独立 OpenLayers 空间规划区，默认显示当前业务影像瓦片和真实省、市、县
行政边界。任务负责人可直接绘制 WGS84 飞行 Polygon 并带入任务表单；采集人员可在已选
任务范围内拾取疑点坐标。已有任务边界、当前任务和不同复核状态的疑点采用独立样式，
地图点击可切换任务。客户端绘制只负责提高操作效率，县界包含、任务范围包含和关联图斑
归属仍由 PostGIS 服务端重新校验。

### 外业核查 CSV / Excel 导入

内外业核查页面支持最多 500 条记录的 CSV 或 `.xlsx` 文件导入。Excel 模板由后端
实时生成，包含标准表头、示例、字段说明和一级地类下拉选项。服务端校验 XLSX ZIP
结构、内部路径、加密状态、解压后体积、公式单元格、必填表头、WGS84 坐标、带时区
采集时间和照片证据；任一记录越界、重复或不合法时整批回滚。

实体 Excel 导入将原始工作簿原子保存到 `storage/field-evidence/imports`，记录受控 URI、
文件大小、SHA-256、来源 URI、版本、来源记录编号、上传人稳定编码和角色快照，并在同一
事务中完成点斑匹配、疑点生成、任务门禁重开和审核记录。CSV 继续使用相同的业务请求
模型与原子导入事务，但不会伪造不存在的物理源文件。

每条外业记录可继续展示旧系统传入的 `photo_urls` 和 `voice_url`，但页面会明确标注为
“历史外部引用（未经实体校验）”。业务证据必须上传 JPEG/PNG/WebP 照片、
WAV/MP3/M4A/OGG 语音或 PDF/XLSX 调查表；服务端按类型限制大小，校验扩展名、文件
签名和 MIME，临时写入后原子发布，并保存大小、SHA-256、上传人及不可变上传/下载事件。
下载和成果归档前再次复核受控路径、签名、大小与 SHA-256。外业疑点闭环和最终成果包
生成都要求每条记录至少有一张已验证现场照片，交付 ZIP 会嵌入全部证据实体、校验清单
和事件账本。

疑点处置页面显式提供“保留内业成果、采用外业结论、人工折中方案、驳回外业结论”
四种决策。每次处置必须填写人工复核依据；折中方案必须填写最终地类，最终为耕地时
还必须填写作物类型。采用外业和折中仅能作用于已匹配的任务图斑，实际属性变化会生成
新的不可变图斑版本，并在审核记录中写入最终落地属性、处置人编码和角色快照。

已闭环疑点可在新增证据或发现上次结论问题后重新打开。服务端会恢复关联外业质量问题、
清空当前处置结果、将任务退回解译阶段并清空质量得分；上次决策和处置依据继续保留在
审核历史中，不会被覆盖或删除。

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

全部灾害斑块完成“确认/排除”复核后，质检员或项目负责人可生成受控 XLSX 专题报告。
报告由服务端绘制灾害 Polygon 空间分布图，生成等级面积占比和灾害类型面积图表，并
固化全部斑块明细、来源 URI、版本、来源要素、模型内容 SHA-256、生成人编码和角色快照。
数据库保存报告实体大小和 SHA-256，下载前重新校验；后续导入、替换或复核斑块会使
旧报告转为历史版本，最终成果 ZIP 只嵌入当前通过校验的报告实体。

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

统计页面同时提供“正式报告”入口。项目负责人可生成服务端受控报告版本，每个版本
原子封装为 ZIP，并包含：地级区域、县区、地类、作物、种植模式、权属村和年度趋势
多工作表 XLSX；含任务摘要、种植结构、行政区排名、年度趋势和可自动分页来源审计的 A4 PDF；
以及保存逐文件大小、SHA256 和统计快照摘要的 `manifest.json`。数据库保存 ZIP/XLSX/PDF
三类实体校验值、任务图斑数、任务更新时间、历史快照数量和最近更新时间。任务图斑或
历史年度快照变化后，当前版本自动转为历史；项目负责人和甲方仍可下载历史版本用于审计，
但最终成果包只纳入当前通过实体复核的报告成员。

成果交付页提供独立“矢量成果”入口。项目负责人可选择一个或多个县区、六类地类和
GeoJSON、ESRI Shapefile、OGC KML 2.2、OpenFileGDB 格式，服务端从 `task_plots`
当前任务范围查询真实 Polygon，并保留图斑属性、行政层级和 OSM 来源血缘。单包最多
100000 个要素，空筛选结果会明确拒绝。生成后原子发布 ZIP，数据库保存版本、筛选快照、
任务图斑数和更新时间、稳定生成人角色、生成依据、ZIP 大小/SHA256，以及 manifest
内全部实体成员的大小/SHA256。下载前会重新打开四种格式并核验数量与 EPSG:4326；
项目负责人和甲方可下载，最终成果包只纳入当前任务版本仍有效的矢量导出成员。

已有数据库执行以下迁移清理旧固定年度数值：

```bash
cd backend
psql "$POSTGRES_DSN" -f scripts/migrations/20260722_statistics_task_scope.sql
psql "$POSTGRES_DSN" -f scripts/migrations/20260722_statistics_history_import.sql
psql "$POSTGRES_DSN" -f scripts/migrations/20260723_statistics_reports.sql
psql "$POSTGRES_DSN" -f scripts/migrations/20260723_vector_export_packages.sql
```

## 可选 3D Tiles

在前端环境变量中配置 `VITE_CESIUM_3D_TILES_URL` 后，三维视图会加载对应瓦片集。代码固定设置 `maximumScreenSpaceError = 2`，用于保证监管场景下的显示精度。

## 影像处理执行与外部产物登记

### 公开 Sentinel-2 实体影像导入

`backend/scripts/import_public_sentinel_imagery.py` 通过 Element 84 Earth Search
查询 Sentinel-2 L2A 条目，只接受蓝、绿、红和近红外四个 10 米 COG 同 CRS、同变换、
同尺寸的场景。每个波段必须提供 STAC Raster Extension 的 `scale`、`offset` 和
`nodata`；脚本在裁取时把量化 DN 转换为 `float32` BOA 地表反射率，并将原标度清单
写入实体标签。缺少标度时整次拒绝，不能把量化 DN 冒充 L2A 反射率。生成的 GeoTIFF
再通过现有影像资产 Service 完成
权限校验、Rasterio 元数据提取、SHA256 去重、受控落盘、处理步骤初始化和审计登记：

```bash
cd backend
poetry run python -m scripts.import_public_sentinel_imagery \
  --asset-code S2B-HRB-20260716-PUBLIC \
  --asset-name "Sentinel-2B 哈尔滨公开影像 2026-07-16" \
  --bbox 126.58,45.76,126.68,45.84 \
  --datetime-range 2026-07-16T00:00:00Z/2026-07-16T23:59:59Z \
  --max-cloud-cover 5 \
  --operator-code manager-zhao-zhiyuan \
  --data-status operational
```

候选平台、载荷、采集时间和云量均取自实际 STAC Feature，不按资产名称或命令参数
伪造。输出标签保存 STAC Item、四个波段 URL、Copernicus 数据法律声明、SAFE 产品
URI、处理基线和 `public` 密级。`operational` 只表示该公开实体已通过平台业务影像
文件门禁，不会把公开数据描述为涉密成果，也不代表完成了正射、配准或验收处理。
对 L2A 源影像尚未生成或登记受控 `band_products` 时，真彩色、假彩色和 NDVI 卡片
必须继续显示不可用，不能直接用源文件冒充处理成果。

### 公开 Landsat-8 全色融合来源导入

`backend/scripts/import_public_landsat_pansharpening.py` 从固定的 Google Cloud Public
Datasets Landsat 公开桶读取 Collection 1 Landsat-8 L1 场景，只接受严格格式的 USGS
产品编号，不能通过参数构造任意网络地址。脚本先下载并核对场景 MTL，要求产品编号、
OLI 载荷、UTC 采集时间、云量、太阳高度角以及 B2/B3/B4/B8 的乘法和加法反射率系数
完整有效；随后校验 B2/B3/B4 同 CRS、同仿射网格、同尺寸，B8 为同 CRS 单波段且
分辨率至少优于多光谱 1.5 倍。

脚本按 USGS 公式和太阳高度角把物理 DN 转换为 `float32` TOA 反射率，分别原子生成
三波段多光谱与单波段全色 GeoTIFF，再复用影像资产 Service 完成权限、SHA-256、
受控落盘、处理步骤初始化与稳定用户审计。两个实体均保存产品编号、MTL URL、四个
源波段 URL、全部标定系数、公开许可、裁切范围和全色融合角色：

```bash
cd backend
poetry run python -m scripts.import_public_landsat_pansharpening \
  --scene-id LC08_L1TP_117028_20200724_20200807_01_T1 \
  --bbox 126.58,45.68,126.78,45.88 \
  --multispectral-asset-code L8-HRB-20200724-MS-PUBLIC \
  --panchromatic-asset-code L8-HRB-20200724-PAN-PUBLIC \
  --multispectral-asset-name "Landsat-8 哈尔滨公开多光谱 2020-07-24" \
  --panchromatic-asset-name "Landsat-8 哈尔滨公开全色 2020-07-24" \
  --operator-code manager-zhao-zhiyuan \
  --data-status operational
```

同一数据库中资产编号和实体 SHA-256 必须唯一；重复执行时应使用新的合法资产编号，
或在空数据库中复现。脚本不把 Collection 1 L1 数据描述为大气校正后的地表反射率，
也不会把公开 Landsat 数据标成涉密或法定调查成果。

对导入器已实际应用 STAC 标度的 Sentinel-2 L2A，可在辐射定标和大气校正步骤选择
“L2A 源级承认”。服务端会重新校验实体大小、SHA256、平台/载荷、L2A、
`SOURCE_SCALE_APPLIED=true`、`BOA_REFLECTANCE`、产品 URI、处理基线，以及公开数据的
STAC Item 和许可链接。承认步骤复用同一实体，不复制文件、不运行 DOS1，并在步骤证据
和审核记录中保存 `algorithm_executed=false`。几何重投影、行政区裁剪和波段产品仍须
生成新的校验值实体，不能一并跳过。

几何校正步骤可选择普通坐标系重投影或 GCP 仿射精校正。GCP 模式要求录入 3–100 个
不共线控制点，每个点保存影像列/行、地面 X/Y/Z、控制点编号和真实来源；前端不自动
填入虚构坐标。服务端校验点位不重复且不越出影像像素范围，在目标坐标系中执行一阶
仿射拟合，计算每个控制点的像素残差、整体 RMSE 和最大残差，超过用户明确门槛时拒绝
生成成果。通过后由 Rasterio/GDAL 写出新的 GeoTIFF，标签与步骤证据保存 GCP 坐标系、
点数、残差、重采样方法、输出网格、文件大小和 SHA-256。

已完成步骤可明确“重新执行”或“替换外部产物”。重跑时当前产物证据进入
`artifact_history`，新产物使用唯一受控路径；全部下游步骤回到待处理并保留被替代
证据，避免用旧裁剪或波段产品冒充新控制网下的成果。当前 GCP 实现是平面仿射精校正，
不等同于带 RPC 和 DEM 的严格正射纠正。

RPC/DEM 模式接受没有普通 CRS、但内嵌完整 RPC 命名空间的原始卫星影像。入库时平台
从 RPC 经度/纬度归一化范围生成 WGS84 足迹，并保存 RPC 误差、经纬度和高程尺度；
没有 CRS 且没有 RPC 的栅格仍会被拒绝。辐射定标和大气校正输出会继续保存原 RPC
命名空间，避免在正射前丢失传感器模型。

执行正射时必须填写 `backend/storage/imagery` 内的受控 DEM 相对路径。服务端重新校验
DEM 文件头、CRS、实数高程波段、尺寸、分辨率、WGS84 范围、文件大小和 SHA-256，
并要求 DEM 完整覆盖 RPC 归一化地理范围。Rasterio/GDAL 使用源 RPC 与 DEM 解算目标
网格和像元位置；输出 GeoTIFF 保存 RPC 模型校验值、DEM 证据、高程偏移、重采样方法、
输出 CRS 和 `ORTHORECTIFIED=true`，同时移除已完成使命的 RPC 命名空间，避免正射成果
再次被误当作待纠正原始影像。

影像增强作为第 5 个可选步骤插入行政区裁剪与波段产品之间。未执行增强不会降低必选
流水线完成率，也不会阻断现有波段产品；执行后则会保留旧证据并把波段产品真实重置为
待处理。百分位拉伸允许配置上下限百分位，逐波段计算实际输入阈值并输出 0–1 浮点
栅格；直方图均衡化允许配置 32–4096 个分箱，逐波段计算累计分布函数。两种算法均拒绝
无有效像元或无动态范围的波段，保存每个波段的输入最小值、最大值、阈值/分箱、处理器
版本、实体大小和 SHA-256，不使用 CSS 滤镜或快视图效果冒充处理成果。

多景镶嵌面板只列出当前项目中已通过实体文件、大小和 SHA-256 复核的几何校正、行政区
裁剪、增强或波段产品成果。每个影像资产只能选择一个步骤产物，必须显式选择 2–20 个
不同资产；波段数量或描述不一致时前端预警、服务端再次拒绝。平台可不匀色或按首景
统计执行全局均值/标准差匀色，并使用首景优先或重叠像元均值合成。空波段和常量波段
不会被赋予虚假动态范围。

覆盖验收从数据库读取真实行政区边界，目标网格同时包含影像并集和完整行政区。行政区
落在所有输入影像之外的像元保持 NoData 并进入覆盖率分母，因此局部裁切不能被算成
100% 完整成果。服务端按窗口处理并受 `MAX_IMAGERY_MOSAIC_PIXELS` 上限保护；像元超限、
覆盖不足、处理失败或事务提交失败均不保留部分文件。通过门槛后才原子发布 GeoTIFF，
保存 CRS、分辨率、覆盖像元数、输入资产/步骤/SHA-256、输出大小和 SHA-256，下载前再次
复核实体。当前实现是基础全局匀色和重叠合成，不代表高级缝线优化、区域网平差、全色
融合或全省规模性能验证。

全色融合面板只接受同一可追溯产品、采集时间相差不超过 60 秒的两个不同
`operational` 资产：多光谱实体至少三个波段，全色实体必须为单波段，且两者均须通过
文件大小、SHA-256、辐射定标/反射率标签和产品身份复核。全色分辨率必须至少优于
多光谱 1.5 倍；服务端把多光谱重投影到全色网格，执行分块直方图匹配 Brovey 融合，
并以有效重叠率、三个融合波段的光谱相关系数和空间细节梯度增益作为验收门禁。通过后
原子发布浮点 GeoTIFF，保存双源与输出大小、SHA-256、产品身份、波段、分辨率和稳定
用户角色审计，下载前再次复核实体。演示影像、Sentinel 灰度派生图和普通上采样不能
作为全色来源。当前真实联调使用公开 Landsat-8 同景 B2/B3/B4 与 B8，经 MTL 系数转换
为 TOA 反射率后完成 15m 融合；来源仍明确标记为公开数据，不作为法定调查成果。

双景自动配准面板只允许两个不同 `operational` 影像资产参与正式生产；演示影像可见但
不可选择。用户选择参考景、待配准景及各自真实步骤实体和配准波段，服务端在公共像元
窗口执行相位相关，计算 X/Y 位移、初始偏移、有效重叠率和峰旁比。待配准影像随后写入
参考影像的同 CRS、同仿射网格、同尺寸和同分辨率浮点 GeoTIFF，并从该物理输出再次计算
残差。最终门槛取用户请求与数据库项目位置精度规则的更严格值；无纹理、重叠不足、峰值
不可靠、偏移/残差超限、像元超限或事务失败均不会留下部分文件。任务保存双景 URI、大小、
SHA-256、波段、全部质量指标、输出结构及稳定用户角色，下载前再次复核实体。当前算法只
处理平移偏差，不冒充仿射/投影变换、RPC 正射或区域网平差。新建变化检测任务必须选择
参考景、待配准景和当前任务完全匹配的配准成果，并以配准 GeoTIFF 作为后时相公共网格
预览及自动候选发现来源；手工偏差和任意证据 URI 已从创建表单与接口移除。

波段产品必须使用四个不同波段。前端从实体描述自动识别 Blue/Green/Red/NIR；当前
Sentinel 子集映射为红=3、绿=2、蓝=1、近红外=4。NDVI 仅对有限、非负且分母大于零的
红光/近红外反射率计算，其余像元写为 `NaN`，有效结果限制在 `[-1, 1]`。

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

影像页面的主图来自当前选中资产的实体源栅格，真彩色、标准假彩色和 NDVI 卡片
来自已校验的七波段产品栈，不再对固定瓦片使用 CSS 滤镜模拟。快视图缓存按实体来源
SHA256 隔离，清单保存来源 URI、文件大小、波段索引/描述、WGS84 范围、拉伸参数、
渲染器版本、PNG 大小和 PNG SHA256；读取时会重新校验缓存。`demo` 影像仍显式标记，
快视图本身不会改变预处理步骤状态，也不会被成果交付门禁视为生产产物。

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

所有 `/api/v1` 普通 JSON 成功响应统一使用
`{"code": 200, "data": ...}`，HTTP 201 等语义状态码继续保留；业务、参数和系统错误
使用 `{"code": <HTTP 状态码>, "msg": "安全中文提示"}`。OpenAPI 文档同步展示该契约，
前端请求层不再接受裸 JSON。GeoTIFF、PNG、PDF、XLSX、CSV、ZIP 等实体下载以及带
`Content-Disposition` 的 JSON 报告保持原始媒体类型和 SHA-256/ETag，不进入成功包络。
容器探针 `/health` 保持简洁裸响应，面向业务客户端的 `/api/v1/system-health` 使用统一
包络。

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
| PATCH | `/api/v1/field-verifications/{verification_code}/resolve` | 以四种显式决策处置外业疑点，校验实体照片并记录最终属性与角色审计 |
| PATCH | `/api/v1/field-verifications/{verification_code}/reopen` | 重新打开已处置疑点，恢复质量问题和解译门禁并保留历史结论 |
| POST | `/api/v1/field-verifications/{verification_code}/artifacts` | 上传并校验现场照片、语音或调查表实体证据 |
| GET | `/api/v1/field-verifications/{verification_code}/artifacts/{artifact_code}/download` | 按稳定用户权限复核并下载外业实体证据，同时写入下载审计 |
| GET | `/api/v1/disasters/reports` | 查询当前及历史灾害监测专题报告和实体状态 |
| POST | `/api/v1/disasters/reports` | 全部斑块复核后生成含分布图、统计图和来源审计的 XLSX 报告 |
| GET | `/api/v1/disasters/reports/{report_code}/download` | 按稳定用户权限复核大小与 SHA-256 后下载报告实体 |
| POST | `/api/v1/reviews/tasks/{task_code}/actions` | 执行三级审核状态流转 |
| GET | `/api/v1/reviews/plots/{plot_code}/versions` | 查询图斑历史版本 |
| POST | `/api/v1/reviews/plots/{plot_code}/rollback` | 恢复历史版本并生成新版本 |
| GET | `/api/v1/statistics/area-summary` | 获取多维面积统计和年度趋势 |
| GET | `/api/v1/statistics/area-summary/export.csv` | 项目负责人导出任务作用域多维面积统计 CSV |
| POST | `/api/v1/statistics/annual-snapshots/import-csv` | 项目负责人导入真实历史年度统计并保存文件与角色审计 |
| GET | `/api/v1/statistics/annual-snapshots/import-template.csv` | 下载历史年度统计标准模板 |
| GET | `/api/v1/statistics/reports` | 查询面积统计正式报告当前版本和历史版本 |
| POST | `/api/v1/statistics/reports/generate` | 项目负责人生成 XLSX、PDF、manifest 原子报告包 |
| GET | `/api/v1/statistics/reports/{report_code}/download` | 项目负责人或甲方复核大小与 SHA-256 后下载报告 ZIP |
| GET | `/api/v1/vector-exports/options` | 查询任务真实县区、六类地类、要素数量上限和四种格式能力 |
| GET | `/api/v1/vector-exports` | 查询当前及历史矢量成果导出版本与失效原因 |
| POST | `/api/v1/vector-exports/generate` | 项目负责人按县区、地类和格式生成真实多格式矢量 ZIP |
| GET | `/api/v1/vector-exports/{export_code}/download` | 项目负责人或甲方复核格式、数量、大小和 SHA-256 后下载 |
| GET | `/api/v1/disasters/summary` | 获取灾害斑块和受灾范围汇总 |
| POST | `/api/v1/disasters/import-geojson` | 批量导入灾害模型 GeoJSON，重算面积并保存来源审计 |
| PATCH | `/api/v1/disasters/{patch_code}` | 人工修正灾害等级和确认状态 |
| GET | `/api/v1/imagery-assets/{asset_code}/processing` | 查询影像预处理流水线 |
| GET | `/api/v1/imagery-assets/{asset_code}/quicklooks` | 从实体源影像和已校验波段产物生成真实快视图及来源清单 |
| GET | `/api/v1/imagery-assets/{asset_code}/quicklooks/{product_code}.png` | 读取带 PNG SHA-256 ETag 的源影像、真彩色、假彩色或 NDVI 快视图 |
| POST | `/api/v1/imagery-assets/{asset_code}/processing/{step_code}/run` | 校验并登记外部处理实体产物 |
| POST | `/api/v1/imagery-assets/{asset_code}/processing/{step_code}/execute` | 使用内置处理器执行步骤并生成受控实体产物 |
| POST | `/api/v1/imagery-assets/{asset_code}/processing/{step_code}/accept-source` | 复核 Sentinel-2 L2A 实体与血缘后，无重复算法地承认定标或大气校正要求 |
| GET | `/api/v1/imagery-assets` | 查询项目真实影像资产目录 |
| POST | `/api/v1/imagery-assets` | 上传影像文件并自动读取栅格与空间元数据 |
| GET | `/api/v1/imagery-history/overview` | 按真实县区面积计算历史影像覆盖矩阵，并返回实体处理与问题追溯时间线 |
| GET | `/api/v1/imagery-mosaics/overview` | 查询可用多景实体来源、像元上限和历史镶嵌成果 |
| POST | `/api/v1/imagery-mosaics/jobs` | 执行多景匀色、镶嵌和完整行政区覆盖率验收 |
| GET | `/api/v1/imagery-mosaics/jobs/{job_code}/download` | 重新校验成果大小和 SHA-256 后下载 GeoTIFF |
| GET | `/api/v1/imagery-registrations/overview` | 查询配准来源资格、项目像素精度规则和历史成果 |
| POST | `/api/v1/imagery-registrations/jobs` | 服务端执行相位相关平移配准并复算实体残差 |
| GET | `/api/v1/imagery-registrations/jobs/{job_code}/download` | 重新校验大小和 SHA-256 后下载配准 GeoTIFF |
| GET | `/api/v1/imagery-fusions/overview` | 查询多光谱/全色实体资格、像元上限、真实阻断原因和历史成果 |
| POST | `/api/v1/imagery-fusions/jobs` | 执行同景直方图匹配 Brovey 融合并验收光谱与空间质量 |
| GET | `/api/v1/imagery-fusions/jobs/{job_code}/download` | 重新校验融合成果大小和 SHA-256 后下载 GeoTIFF |
| GET | `/api/v1/deliveries` | 查询交付门禁、单一当前版本、历史包及任务/归档源失效原因 |
| POST | `/api/v1/deliveries/generate` | 项目负责人生成含实体专题图、监理报告、影像血缘和逐文件 SHA-256 的任务成果 ZIP |
| GET | `/api/v1/deliveries/{package_code}/download` | 经角色、任务快照、归档快照、大小和 SHA-256 校验后下载当前成果包 |
| GET | `/api/v1/rule-configs` | 查询项目当前质量与外业校核规则 |
| PATCH | `/api/v1/rule-configs` | 更新项目规则并保存修改前后值审计 |
| GET | `/api/v1/change-detection/overview` | 查询真实影像资格、检测任务、候选队列和判读历史 |
| POST | `/api/v1/change-detection/runs` | 绑定两期已核验影像、规则与配准证据创建检测任务 |
| POST | `/api/v1/change-detection/runs/{run_code}/candidates/import-geojson` | 原子导入六类变化候选 GeoJSON 并重算面积 |
| POST | `/api/v1/change-detection/runs/{run_code}/discover-candidates` | 基于双时相公共网格执行 RGB 差分并生成带校验值的未分类候选成果 |
| PATCH | `/api/v1/change-detection/runs/{run_code}/candidates/{candidate_code}/review` | 人工确认、重分类或排除候选并追加不可变历史 |
| GET | `/api/v1/change-detection/runs/{run_code}/comparison` | 生成或读取双时相公共网格预览及来源校验清单 |
| GET | `/api/v1/change-detection/runs/{run_code}/comparison/{side}.png` | 读取带 SHA-256 ETag 的前/后时相 PNG 预览 |
| GET | `/api/v1/supervision/overview` | 查询 122 县区真实监理工作区、计划、检查、问题和报告状态 |
| POST | `/api/v1/supervision/plans` | 从任务真实图斑创建可复现县区抽样计划并固化数据快照 |
| GET | `/api/v1/supervision/plans/{plan_code}/samples` | 分页读取完整显式样本身份和图斑版本快照 |
| POST | `/api/v1/supervision/plans/{plan_code}/inspections` | 独立监理登记过程检查及证据 |
| POST | `/api/v1/supervision/plans/{plan_code}/inspections/{inspection_code}/findings` | 登记监理问题、严重度、证据和整改期限 |
| POST | `/api/v1/supervision/plans/{plan_code}/findings/{finding_code}/rectification` | 生产团队提交整改说明和证据 |
| POST | `/api/v1/supervision/plans/{plan_code}/findings/{finding_code}/reinspect` | 独立监理保存逐轮复检结论 |
| PATCH | `/api/v1/supervision/plans/{plan_code}/county-evaluations/{region_code}` | 新增或更新县区量化评价并审计修改前后值 |
| POST | `/api/v1/supervision/plans/{plan_code}/report` | 通过闭环门禁后生成不可变实体监理报告 |
| GET | `/api/v1/supervision/reports/{report_code}/download` | 鉴权并复核大小与 SHA-256 后下载报告 |
| GET | `/api/v1/thematic-maps/overview` | 查询版式模板、已校验实体来源和当前任务专题图成果 |
| POST | `/api/v1/thematic-maps/templates` | 项目负责人创建持久化专题图版式并记录稳定身份审计 |
| POST | `/api/v1/thematic-maps/products/generate` | 从同一已校验波段产品实体原子批量生成 PNG/PDF 专题图 |
| GET | `/api/v1/thematic-maps/products/{product_code}/download` | 按预览或附件方式鉴权，并复核签名、大小及 SHA-256 后读取成果 |
| GET | `/api/v1/service-sharing/overview` | 按项目用户能力查询服务、申请、凭证摘要、健康和调用审计 |
| POST | `/api/v1/service-sharing/services` | 项目负责人登记服务与真实资源证据并提交甲方审批 |
| POST | `/api/v1/service-sharing/services/{service_code}/review` | 甲方审核代表批准或驳回服务登记 |
| POST | `/api/v1/service-sharing/services/{service_code}/access-requests` | 项目成员提交用途和期限明确的访问申请 |
| POST | `/api/v1/service-sharing/access-requests/{request_code}/review` | 项目负责人审批访问并按需签发一次性 API Key |
| POST | `/api/v1/service-sharing/services/{service_code}/health-check` | 执行带 SSRF 防护的真实服务健康探测 |
| POST | `/api/v1/service-sharing/services/{service_code}/usage` | 校验项目身份或 API Key 后写入调用审计 |
| POST | `/api/v1/service-sharing/services/{service_code}/revoke` | 撤销服务并原子吊销全部活动凭证 |
| POST | `/api/v1/service-sharing/credentials/{credential_code}/revoke` | 单独撤销一个访问凭证 |
| GET | `/api/v1/monitoring-network/overview` | 查询监测站、设备、遥测、故障、模型、复核和告警真实总览 |
| POST | `/api/v1/monitoring-network/stations` | 校验真实县界后登记监测站及实体证据 |
| POST | `/api/v1/monitoring-network/stations/{station_code}/devices` | 登记设备身份、归属和照片校验值 |
| POST | `/api/v1/monitoring-network/devices/{device_code}/telemetry` | 通过设备级幂等键写入数值、载荷或图像证据 |
| POST | `/api/v1/monitoring-network/devices/{device_code}/faults` | 登记设备故障并切换异常状态 |
| POST | `/api/v1/monitoring-network/faults/{fault_code}/resolve` | 以实体处置回执关闭设备故障 |
| POST | `/api/v1/monitoring-network/models` | 登记模型实体、评估来源和四项验证指标并替代旧版本 |
| POST | `/api/v1/monitoring-network/assessments` | 登记模型输入、置信度和预测依据并进入人工复核 |
| POST | `/api/v1/monitoring-network/assessments/{assessment_code}/review` | 人工批准或驳回模型识别结果 |
| POST | `/api/v1/monitoring-network/assessments/{assessment_code}/alerts` | 仅从已批准识别结果创建待发送告警 |
| POST | `/api/v1/monitoring-network/alerts/{alert_code}/deliver` | 登记告警真实送达回执、大小和 SHA-256 |
| POST | `/api/v1/monitoring-network/reports` | 从已批准识别结果显式创建省、地级或县级报告草稿 |
| PATCH | `/api/v1/monitoring-network/reports/{report_code}` | 在草稿或退回状态修订报告范围、周期和台账条目 |
| POST | `/api/v1/monitoring-network/reports/{report_code}/consultations` | 为报告发起可审计的专家会商 |
| POST | `/api/v1/monitoring-network/consultations/{consultation_code}/answer` | 上传专家答复实体并由服务端计算大小与 SHA-256 |
| POST | `/api/v1/monitoring-network/reports/{report_code}/submit` | 在会商全部答复后提交县级审核 |
| POST | `/api/v1/monitoring-network/reports/{report_code}/review` | 按县、市、省角色能力逐级通过或退回报告 |
| GET | `/api/v1/monitoring-network/reports/{report_code}/download` | 鉴权并重新校验实体后下载省级通过的 XLSX 台账 |
| GET | `/api/v1/uav/overview` | 查询航空器、任务、实体成果、疑点和不可变事件真实总览 |
| POST | `/api/v1/uav/aircraft` | 上传证书并登记航空器、传感器和权属身份 |
| POST | `/api/v1/uav/missions` | 上传飞手资质并创建真实县界内飞行任务 |
| POST | `/api/v1/uav/missions/{mission_code}/artifacts` | 上传原始影像、航迹、照片、视频、正射、DEM 或报告实体 |
| POST | `/api/v1/uav/missions/{mission_code}/status` | 按实体成果、分辨率、覆盖和疑点门禁流转任务状态 |
| POST | `/api/v1/uav/missions/{mission_code}/findings` | 登记任务范围内且绑定实体成果的空间疑点 |
| POST | `/api/v1/uav/missions/{mission_code}/findings/{finding_code}/review` | 人工确认或排除无人机疑点并记录稳定身份审计 |
| GET | `/api/v1/uav/artifacts/{artifact_code}/download` | 鉴权并复核文件大小与 SHA-256 后下载成果 |

## 数据安全

- 所有空间查询均由 SQLAlchemy 生成参数化 SQL，不拼接用户输入。
- 数据库异常统一转换为安全提示，原始堆栈仅记录在服务端日志。
- API 经纬度均校验为 WGS84 合法范围。
- 生产环境应通过密钥管理系统覆盖示例数据库密码，并限制数据库端口暴露。

## 开源许可

AgriScope 基于 [Apache License 2.0](LICENSE) 开源。

允许个人和企业使用、修改、分发及商业化，但须保留版权、许可和变更说明。项目包含的行政区划、OpenStreetMap 快照及其他公开数据仍遵循各自来源的授权和署名要求；这些联调数据不代表法定基本农田或法定调查成果。第三方数据归属说明见 [NOTICE](NOTICE)。
