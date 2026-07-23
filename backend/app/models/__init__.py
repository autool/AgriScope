"""数据库模型。"""

from app.models.acceptance_report import AcceptanceReport
from app.models.dataset_asset_verification import DatasetAssetVerification
from app.models.disaster_report import DisasterReport
from app.models.growth_monitoring import (
    GrowthMonitoringEvent,
    GrowthMonitoringRun,
    GrowthMonitoringZone,
)
from app.models.imagery_fusion import ImageryFusionEvent, ImageryFusionJob
from app.models.imagery_import import ImageryImportBatch, ImageryImportBatchItem
from app.models.imagery_mosaic import (
    ImageryMosaicEvent,
    ImageryMosaicInput,
    ImageryMosaicJob,
)
from app.models.imagery_registration import (
    ImageryRegistrationEvent,
    ImageryRegistrationJob,
)
from app.models.monitoring_network import (
    DeviceFault,
    DeviceTelemetry,
    ExpertConsultation,
    MonitoringDevice,
    MonitoringEvent,
    MonitoringStation,
    PestAlert,
    PestAssessment,
    PestModelVersion,
    PestReport,
    PestReportItem,
)
from app.models.plot import Base, FarmlandPlot
from app.models.plot_attribute_field import (
    ProjectPlotAttributeField,
    ProjectPlotAttributeFieldAudit,
)
from app.models.plot_attribute_workbook import PlotAttributeImportBatch
from app.models.service_sharing import (
    ServiceAccessRequest,
    ServiceCredential,
    ServiceHealthCheck,
    ServiceUsageEvent,
    SharedService,
)
from app.models.statistics_report import StatisticsReport
from app.models.supervision import (
    SupervisionCountyEvaluation,
    SupervisionEvent,
    SupervisionFinding,
    SupervisionInspection,
    SupervisionPlan,
    SupervisionReinspection,
    SupervisionReport,
    SupervisionSample,
)
from app.models.thematic_map import (
    ThematicMapEvent,
    ThematicMapProduct,
    ThematicMapTemplate,
)
from app.models.uav import UavAircraft, UavArtifact, UavEvent, UavFinding, UavMission
from app.models.vector_export import VectorExportPackage
from app.models.workbench import (
    DatasetAsset,
    DatasetLineage,
    FieldVerification,
    FieldVerificationArtifact,
    FieldVerificationArtifactEvent,
    ImageryAsset,
    MonitoringProject,
    MonitoringTask,
    PlotQualityCheck,
    PlotVersion,
    ProductionAuditEvent,
    ProductionBatch,
    ProjectRuleConfig,
    ProjectRuleConfigAudit,
    QualityIssue,
    ReviewRecord,
    TaskPlot,
    WorkPackage,
    WorkPackagePlot,
)

__all__ = [
    "AcceptanceReport",
    "Base",
    "DatasetAsset",
    "DatasetAssetVerification",
    "DatasetLineage",
    "DeviceFault",
    "DeviceTelemetry",
    "DisasterReport",
    "ExpertConsultation",
    "FarmlandPlot",
    "FieldVerification",
    "FieldVerificationArtifact",
    "FieldVerificationArtifactEvent",
    "GrowthMonitoringEvent",
    "GrowthMonitoringRun",
    "GrowthMonitoringZone",
    "ImageryAsset",
    "ImageryFusionEvent",
    "ImageryFusionJob",
    "ImageryImportBatch",
    "ImageryImportBatchItem",
    "ImageryMosaicEvent",
    "ImageryMosaicInput",
    "ImageryMosaicJob",
    "ImageryRegistrationEvent",
    "ImageryRegistrationJob",
    "MonitoringProject",
    "MonitoringDevice",
    "MonitoringEvent",
    "MonitoringStation",
    "MonitoringTask",
    "PestAlert",
    "PestAssessment",
    "PestModelVersion",
    "PestReport",
    "PestReportItem",
    "ProductionBatch",
    "ProductionAuditEvent",
    "ProjectRuleConfig",
    "ProjectRuleConfigAudit",
    "ProjectPlotAttributeField",
    "ProjectPlotAttributeFieldAudit",
    "PlotQualityCheck",
    "PlotAttributeImportBatch",
    "PlotVersion",
    "QualityIssue",
    "ReviewRecord",
    "ServiceAccessRequest",
    "ServiceCredential",
    "ServiceHealthCheck",
    "ServiceUsageEvent",
    "SharedService",
    "StatisticsReport",
    "SupervisionCountyEvaluation",
    "SupervisionEvent",
    "SupervisionFinding",
    "SupervisionInspection",
    "SupervisionPlan",
    "SupervisionReinspection",
    "SupervisionReport",
    "SupervisionSample",
    "TaskPlot",
    "ThematicMapEvent",
    "ThematicMapProduct",
    "ThematicMapTemplate",
    "UavAircraft",
    "UavArtifact",
    "UavEvent",
    "UavFinding",
    "UavMission",
    "VectorExportPackage",
    "WorkPackage",
    "WorkPackagePlot",
]
