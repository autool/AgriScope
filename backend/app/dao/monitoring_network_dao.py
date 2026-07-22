"""田间监测网络、设备故障和病虫害预警数据访问层。"""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

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
from app.models.workbench import AdministrativeBoundary, MonitoringProject


@dataclass(frozen=True)
class AdministrativeContext:
    """监测站坐标命中的省市县真实行政层级。"""

    province_code: str
    province_name: str
    city_code: str
    city_name: str
    district_code: str
    district_name: str


@dataclass(frozen=True)
class DeviceRecord:
    """带监测站编号的设备记录。"""

    device: MonitoringDevice
    station_code: str


@dataclass(frozen=True)
class TelemetryRecord:
    """带设备编号的遥测记录。"""

    telemetry: DeviceTelemetry
    device_code: str


@dataclass(frozen=True)
class FaultRecord:
    """带设备编号的故障记录。"""

    fault: DeviceFault
    device_code: str


@dataclass(frozen=True)
class AssessmentRecord:
    """带设备和模型身份的病虫害识别记录。"""

    assessment: PestAssessment
    device_code: str | None
    model_code: str
    model_version: str


@dataclass(frozen=True)
class AlertRecord:
    """带识别编号的告警记录。"""

    alert: PestAlert
    assessment_code: str


@dataclass(frozen=True)
class ReportAssessmentRecord:
    """报告候选识别结果及行政区、模型和告警上下文。"""

    assessment: PestAssessment
    station: MonitoringStation | None
    model_code: str
    model_version: str
    alert: PestAlert | None


@dataclass(frozen=True)
class ConsultationRecord:
    """带报告编号的专家会商记录。"""

    consultation: ExpertConsultation
    report_code: str


class MonitoringNetworkDAO:
    """封装监测站、设备、遥测、模型、复核和告警数据库操作。"""

    async def get_project_by_code(
        self,
        db: AsyncSession,
        project_code: str,
    ) -> MonitoringProject | None:
        """按项目编号查询项目。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。

        Returns:
            MonitoringProject | None: 项目或空值。
        """
        result = await db.execute(
            select(MonitoringProject).where(
                MonitoringProject.project_code == project_code
            )
        )
        return result.scalar_one_or_none()

    async def get_administrative_context(
        self,
        db: AsyncSession,
        project_id: int,
        district_code: str,
        longitude: float,
        latitude: float,
    ) -> AdministrativeContext | None:
        """验证 WGS84 坐标位于申报县区并返回完整行政层级。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            district_code: 县区编码。
            longitude: WGS84 经度。
            latitude: WGS84 纬度。

        Returns:
            AdministrativeContext | None: 命中层级或空值。
        """
        district = aliased(AdministrativeBoundary)
        city = aliased(AdministrativeBoundary)
        province = aliased(AdministrativeBoundary)
        point = func.ST_SetSRID(func.ST_Point(longitude, latitude), 4326)
        result = await db.execute(
            select(
                province.boundary_code,
                province.boundary_name,
                city.boundary_code,
                city.boundary_name,
                district.boundary_code,
                district.boundary_name,
            )
            .join(city, city.boundary_code == district.parent_code)
            .join(province, province.boundary_code == city.parent_code)
            .where(
                district.project_id == project_id,
                district.boundary_code == district_code,
                district.boundary_level == "district",
                city.project_id == project_id,
                province.project_id == project_id,
                func.ST_Covers(district.geom, point),
            )
        )
        row = result.one_or_none()
        if row is None:
            return None
        return AdministrativeContext(
            province_code=str(row[0]),
            province_name=str(row[1]),
            city_code=str(row[2]),
            city_name=str(row[3]),
            district_code=str(row[4]),
            district_name=str(row[5]),
        )

    async def get_station_by_code(
        self,
        db: AsyncSession,
        project_id: int,
        station_code: str,
    ) -> MonitoringStation | None:
        """查询项目内监测站。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            station_code: 监测站编号。

        Returns:
            MonitoringStation | None: 监测站或空值。
        """
        result = await db.execute(
            select(MonitoringStation).where(
                MonitoringStation.project_id == project_id,
                MonitoringStation.station_code == station_code,
            )
        )
        return result.scalar_one_or_none()

    async def add_station(
        self,
        db: AsyncSession,
        station: MonitoringStation,
    ) -> MonitoringStation:
        """新增监测站。

        Args:
            db: 异步数据库会话。
            station: 监测站模型。

        Returns:
            MonitoringStation: 已刷新监测站。
        """
        db.add(station)
        await db.flush()
        await db.refresh(station)
        return station

    async def list_stations(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> Sequence[MonitoringStation]:
        """查询项目全部监测站。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            Sequence[MonitoringStation]: 监测站列表。
        """
        result = await db.execute(
            select(MonitoringStation)
            .where(MonitoringStation.project_id == project_id)
            .order_by(
                MonitoringStation.district_code,
                MonitoringStation.station_code,
            )
        )
        return result.scalars().all()

    async def get_device_by_code(
        self,
        db: AsyncSession,
        project_id: int,
        device_code: str,
    ) -> MonitoringDevice | None:
        """查询项目内监测设备。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            device_code: 设备编号。

        Returns:
            MonitoringDevice | None: 设备或空值。
        """
        result = await db.execute(
            select(MonitoringDevice).where(
                MonitoringDevice.project_id == project_id,
                MonitoringDevice.device_code == device_code,
            )
        )
        return result.scalar_one_or_none()

    async def add_device(
        self,
        db: AsyncSession,
        device: MonitoringDevice,
    ) -> MonitoringDevice:
        """新增监测设备。

        Args:
            db: 异步数据库会话。
            device: 设备模型。

        Returns:
            MonitoringDevice: 已刷新设备。
        """
        db.add(device)
        await db.flush()
        await db.refresh(device)
        return device

    async def list_device_records(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> list[DeviceRecord]:
        """查询项目设备及所属站点编号。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            list[DeviceRecord]: 设备记录。
        """
        result = await db.execute(
            select(MonitoringDevice, MonitoringStation.station_code)
            .join(
                MonitoringStation,
                MonitoringStation.id == MonitoringDevice.station_id,
            )
            .where(MonitoringDevice.project_id == project_id)
            .order_by(MonitoringStation.station_code, MonitoringDevice.device_code)
        )
        return [DeviceRecord(device=row[0], station_code=str(row[1])) for row in result]

    async def get_telemetry_by_idempotency_key(
        self,
        db: AsyncSession,
        device_id: int,
        idempotency_key: str,
    ) -> DeviceTelemetry | None:
        """按设备和幂等键查询遥测。

        Args:
            db: 异步数据库会话。
            device_id: 设备主键。
            idempotency_key: 上报幂等键。

        Returns:
            DeviceTelemetry | None: 已存在遥测或空值。
        """
        result = await db.execute(
            select(DeviceTelemetry).where(
                DeviceTelemetry.device_id == device_id,
                DeviceTelemetry.idempotency_key == idempotency_key,
            )
        )
        return result.scalar_one_or_none()

    async def add_telemetry(
        self,
        db: AsyncSession,
        telemetry: DeviceTelemetry,
    ) -> DeviceTelemetry:
        """新增设备遥测。

        Args:
            db: 异步数据库会话。
            telemetry: 遥测模型。

        Returns:
            DeviceTelemetry: 已刷新遥测。
        """
        db.add(telemetry)
        await db.flush()
        await db.refresh(telemetry)
        return telemetry

    async def list_telemetry_records(
        self,
        db: AsyncSession,
        project_id: int,
        limit: int = 200,
    ) -> list[TelemetryRecord]:
        """查询项目最近遥测。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            limit: 最大记录数。

        Returns:
            list[TelemetryRecord]: 最近遥测记录。
        """
        result = await db.execute(
            select(DeviceTelemetry, MonitoringDevice.device_code)
            .join(MonitoringDevice, MonitoringDevice.id == DeviceTelemetry.device_id)
            .where(MonitoringDevice.project_id == project_id)
            .order_by(DeviceTelemetry.observed_at.desc())
            .limit(limit)
        )
        return [
            TelemetryRecord(telemetry=row[0], device_code=str(row[1]))
            for row in result
        ]

    async def count_telemetry(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> int:
        """统计项目遥测总数。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            int: 遥测总数。
        """
        result = await db.execute(
            select(func.count(DeviceTelemetry.id))
            .join(MonitoringDevice, MonitoringDevice.id == DeviceTelemetry.device_id)
            .where(MonitoringDevice.project_id == project_id)
        )
        return int(result.scalar_one())

    async def get_fault_by_code(
        self,
        db: AsyncSession,
        project_id: int,
        fault_code: str,
        *,
        for_update: bool = False,
    ) -> DeviceFault | None:
        """查询设备故障并可加行锁。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            fault_code: 故障编号。
            for_update: 是否锁定故障行。

        Returns:
            DeviceFault | None: 故障或空值。
        """
        statement = select(DeviceFault).where(
            DeviceFault.project_id == project_id,
            DeviceFault.fault_code == fault_code,
        )
        if for_update:
            statement = statement.with_for_update()
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    async def add_fault(
        self,
        db: AsyncSession,
        fault: DeviceFault,
    ) -> DeviceFault:
        """新增设备故障。

        Args:
            db: 异步数据库会话。
            fault: 故障模型。

        Returns:
            DeviceFault: 已刷新故障。
        """
        db.add(fault)
        await db.flush()
        await db.refresh(fault)
        return fault

    async def count_open_faults_for_device(
        self,
        db: AsyncSession,
        device_id: int,
    ) -> int:
        """统计设备未关闭故障。

        Args:
            db: 异步数据库会话。
            device_id: 设备主键。

        Returns:
            int: 未关闭故障数。
        """
        result = await db.execute(
            select(func.count(DeviceFault.id)).where(
                DeviceFault.device_id == device_id,
                DeviceFault.status == "open",
            )
        )
        return int(result.scalar_one())

    async def list_fault_records(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> list[FaultRecord]:
        """查询项目故障及设备编号。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            list[FaultRecord]: 故障记录。
        """
        result = await db.execute(
            select(DeviceFault, MonitoringDevice.device_code)
            .join(MonitoringDevice, MonitoringDevice.id == DeviceFault.device_id)
            .where(DeviceFault.project_id == project_id)
            .order_by(DeviceFault.created_at.desc())
        )
        return [FaultRecord(fault=row[0], device_code=str(row[1])) for row in result]

    async def get_model_version(
        self,
        db: AsyncSession,
        project_id: int,
        model_code: str,
        model_version: str,
    ) -> PestModelVersion | None:
        """查询病虫害模型版本。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            model_code: 模型编码。
            model_version: 模型版本。

        Returns:
            PestModelVersion | None: 模型版本或空值。
        """
        result = await db.execute(
            select(PestModelVersion).where(
                PestModelVersion.project_id == project_id,
                PestModelVersion.model_code == model_code,
                PestModelVersion.model_version == model_version,
            )
        )
        return result.scalar_one_or_none()

    async def list_active_model_versions_by_code(
        self,
        db: AsyncSession,
        project_id: int,
        model_code: str,
    ) -> Sequence[PestModelVersion]:
        """查询同编码的活动模型版本。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            model_code: 模型编码。

        Returns:
            Sequence[PestModelVersion]: 活动模型列表。
        """
        result = await db.execute(
            select(PestModelVersion).where(
                PestModelVersion.project_id == project_id,
                PestModelVersion.model_code == model_code,
                PestModelVersion.status == "active",
            )
        )
        return result.scalars().all()

    async def add_model_version(
        self,
        db: AsyncSession,
        model: PestModelVersion,
    ) -> PestModelVersion:
        """新增病虫害模型版本。

        Args:
            db: 异步数据库会话。
            model: 模型版本。

        Returns:
            PestModelVersion: 已刷新模型版本。
        """
        db.add(model)
        await db.flush()
        await db.refresh(model)
        return model

    async def list_model_versions(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> Sequence[PestModelVersion]:
        """查询项目模型版本。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            Sequence[PestModelVersion]: 模型版本列表。
        """
        result = await db.execute(
            select(PestModelVersion)
            .where(PestModelVersion.project_id == project_id)
            .order_by(PestModelVersion.model_code, PestModelVersion.created_at.desc())
        )
        return result.scalars().all()

    async def get_assessment_by_code(
        self,
        db: AsyncSession,
        project_id: int,
        assessment_code: str,
        *,
        for_update: bool = False,
    ) -> PestAssessment | None:
        """查询识别结果并可加行锁。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            assessment_code: 识别编号。
            for_update: 是否锁定记录。

        Returns:
            PestAssessment | None: 识别结果或空值。
        """
        statement = select(PestAssessment).where(
            PestAssessment.project_id == project_id,
            PestAssessment.assessment_code == assessment_code,
        )
        if for_update:
            statement = statement.with_for_update()
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    async def add_assessment(
        self,
        db: AsyncSession,
        assessment: PestAssessment,
    ) -> PestAssessment:
        """新增病虫害识别结果。

        Args:
            db: 异步数据库会话。
            assessment: 识别模型。

        Returns:
            PestAssessment: 已刷新识别结果。
        """
        db.add(assessment)
        await db.flush()
        await db.refresh(assessment)
        return assessment

    async def list_assessment_records(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> list[AssessmentRecord]:
        """查询识别结果及关联设备和模型身份。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            list[AssessmentRecord]: 识别结果记录。
        """
        result = await db.execute(
            select(
                PestAssessment,
                MonitoringDevice.device_code,
                PestModelVersion.model_code,
                PestModelVersion.model_version,
            )
            .join(
                PestModelVersion,
                PestModelVersion.id == PestAssessment.model_version_id,
            )
            .outerjoin(
                MonitoringDevice,
                MonitoringDevice.id == PestAssessment.device_id,
            )
            .where(PestAssessment.project_id == project_id)
            .order_by(PestAssessment.created_at.desc())
        )
        return [
            AssessmentRecord(
                assessment=row[0],
                device_code=str(row[1]) if row[1] is not None else None,
                model_code=str(row[2]),
                model_version=str(row[3]),
            )
            for row in result
        ]

    async def get_alert_by_code(
        self,
        db: AsyncSession,
        project_id: int,
        alert_code: str,
        *,
        for_update: bool = False,
    ) -> PestAlert | None:
        """查询告警并可加行锁。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            alert_code: 告警编号。
            for_update: 是否锁定记录。

        Returns:
            PestAlert | None: 告警或空值。
        """
        statement = select(PestAlert).where(
            PestAlert.project_id == project_id,
            PestAlert.alert_code == alert_code,
        )
        if for_update:
            statement = statement.with_for_update()
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    async def get_alert_by_assessment_id(
        self,
        db: AsyncSession,
        assessment_id: int,
    ) -> PestAlert | None:
        """查询识别结果是否已有告警。

        Args:
            db: 异步数据库会话。
            assessment_id: 识别结果主键。

        Returns:
            PestAlert | None: 告警或空值。
        """
        result = await db.execute(
            select(PestAlert).where(PestAlert.assessment_id == assessment_id)
        )
        return result.scalar_one_or_none()

    async def add_alert(
        self,
        db: AsyncSession,
        alert: PestAlert,
    ) -> PestAlert:
        """新增病虫害告警。

        Args:
            db: 异步数据库会话。
            alert: 告警模型。

        Returns:
            PestAlert: 已刷新告警。
        """
        db.add(alert)
        await db.flush()
        await db.refresh(alert)
        return alert

    async def list_alert_records(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> list[AlertRecord]:
        """查询项目告警及识别编号。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            list[AlertRecord]: 告警记录。
        """
        result = await db.execute(
            select(PestAlert, PestAssessment.assessment_code)
            .join(PestAssessment, PestAssessment.id == PestAlert.assessment_id)
            .where(PestAlert.project_id == project_id)
            .order_by(PestAlert.created_at.desc())
        )
        return [
            AlertRecord(alert=row[0], assessment_code=str(row[1]))
            for row in result
        ]

    async def get_region_boundary(
        self,
        db: AsyncSession,
        project_id: int,
        boundary_code: str,
        boundary_level: str,
    ) -> AdministrativeBoundary | None:
        """按项目、层级和编码查询真实行政边界。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            boundary_code: 行政区编码。
            boundary_level: 行政区层级。

        Returns:
            AdministrativeBoundary | None: 行政区边界或空值。
        """
        result = await db.execute(
            select(AdministrativeBoundary).where(
                AdministrativeBoundary.project_id == project_id,
                AdministrativeBoundary.boundary_code == boundary_code,
                AdministrativeBoundary.boundary_level == boundary_level,
            )
        )
        return result.scalar_one_or_none()

    async def get_report_assessment_records(
        self,
        db: AsyncSession,
        project_id: int,
        assessment_codes: list[str],
    ) -> list[ReportAssessmentRecord]:
        """查询报告显式选择的识别结果及行政区、模型和告警上下文。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            assessment_codes: 识别编号列表。

        Returns:
            list[ReportAssessmentRecord]: 报告候选记录。
        """
        result = await db.execute(
            select(
                PestAssessment,
                MonitoringStation,
                PestModelVersion.model_code,
                PestModelVersion.model_version,
                PestAlert,
            )
            .join(
                PestModelVersion,
                PestModelVersion.id == PestAssessment.model_version_id,
            )
            .outerjoin(
                MonitoringDevice,
                MonitoringDevice.id == PestAssessment.device_id,
            )
            .outerjoin(
                MonitoringStation,
                MonitoringStation.id == MonitoringDevice.station_id,
            )
            .outerjoin(PestAlert, PestAlert.assessment_id == PestAssessment.id)
            .where(
                PestAssessment.project_id == project_id,
                PestAssessment.assessment_code.in_(assessment_codes),
            )
        )
        return [
            ReportAssessmentRecord(
                assessment=row[0],
                station=row[1],
                model_code=str(row[2]),
                model_version=str(row[3]),
                alert=row[4],
            )
            for row in result
        ]

    async def get_report_by_code(
        self,
        db: AsyncSession,
        project_id: int,
        report_code: str,
        *,
        for_update: bool = False,
    ) -> PestReport | None:
        """查询病虫害报告并可锁定审核状态。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            report_code: 报告编号。
            for_update: 是否加行锁。

        Returns:
            PestReport | None: 报告或空值。
        """
        statement = select(PestReport).where(
            PestReport.project_id == project_id,
            PestReport.report_code == report_code,
        )
        if for_update:
            statement = statement.with_for_update()
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    async def get_report_by_id(
        self,
        db: AsyncSession,
        project_id: int,
        report_id: int,
    ) -> PestReport | None:
        """按主键和项目查询病虫害报告。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            report_id: 报告主键。

        Returns:
            PestReport | None: 报告或空值。
        """
        result = await db.execute(
            select(PestReport).where(
                PestReport.project_id == project_id,
                PestReport.id == report_id,
            )
        )
        return result.scalar_one_or_none()

    async def add_report(
        self,
        db: AsyncSession,
        report: PestReport,
    ) -> PestReport:
        """新增报告草稿。

        Args:
            db: 异步数据库会话。
            report: 报告模型。

        Returns:
            PestReport: 已刷新报告。
        """
        db.add(report)
        await db.flush()
        await db.refresh(report)
        return report

    async def list_reports(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> Sequence[PestReport]:
        """查询项目病虫害报告。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            Sequence[PestReport]: 报告列表。
        """
        result = await db.execute(
            select(PestReport)
            .where(PestReport.project_id == project_id)
            .order_by(PestReport.updated_at.desc(), PestReport.report_code)
        )
        return result.scalars().all()

    async def replace_report_items(
        self,
        db: AsyncSession,
        report_id: int,
        items: list[PestReportItem],
    ) -> None:
        """原子替换报告显式识别台账。

        Args:
            db: 异步数据库会话。
            report_id: 报告主键。
            items: 新台账条目。

        Returns:
            None: 无返回值。
        """
        await db.execute(
            delete(PestReportItem).where(PestReportItem.report_id == report_id)
        )
        db.add_all(items)
        await db.flush()

    async def list_report_items(
        self,
        db: AsyncSession,
        report_id: int,
    ) -> Sequence[PestReportItem]:
        """查询报告识别台账。

        Args:
            db: 异步数据库会话。
            report_id: 报告主键。

        Returns:
            Sequence[PestReportItem]: 台账条目。
        """
        result = await db.execute(
            select(PestReportItem)
            .where(PestReportItem.report_id == report_id)
            .order_by(PestReportItem.assessment_code)
        )
        return result.scalars().all()

    async def get_consultation_by_code(
        self,
        db: AsyncSession,
        project_id: int,
        consultation_code: str,
        *,
        for_update: bool = False,
    ) -> ExpertConsultation | None:
        """查询专家会商并可锁定答复状态。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            consultation_code: 会商编号。
            for_update: 是否加行锁。

        Returns:
            ExpertConsultation | None: 会商记录或空值。
        """
        statement = select(ExpertConsultation).where(
            ExpertConsultation.project_id == project_id,
            ExpertConsultation.consultation_code == consultation_code,
        )
        if for_update:
            statement = statement.with_for_update()
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    async def add_consultation(
        self,
        db: AsyncSession,
        consultation: ExpertConsultation,
    ) -> ExpertConsultation:
        """新增专家会商问题。

        Args:
            db: 异步数据库会话。
            consultation: 会商模型。

        Returns:
            ExpertConsultation: 已刷新会商。
        """
        db.add(consultation)
        await db.flush()
        await db.refresh(consultation)
        return consultation

    async def list_consultation_records(
        self,
        db: AsyncSession,
        project_id: int,
        report_id: int | None = None,
    ) -> list[ConsultationRecord]:
        """查询项目或指定报告专家会商。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            report_id: 可选报告主键。

        Returns:
            list[ConsultationRecord]: 会商记录。
        """
        statement = (
            select(ExpertConsultation, PestReport.report_code)
            .join(PestReport, PestReport.id == ExpertConsultation.report_id)
            .where(ExpertConsultation.project_id == project_id)
            .order_by(ExpertConsultation.requested_at.desc())
        )
        if report_id is not None:
            statement = statement.where(ExpertConsultation.report_id == report_id)
        result = await db.execute(statement)
        return [
            ConsultationRecord(
                consultation=row[0],
                report_code=str(row[1]),
            )
            for row in result
        ]

    async def add_event(
        self,
        db: AsyncSession,
        event: MonitoringEvent,
    ) -> MonitoringEvent:
        """新增不可变监测审计事件。

        Args:
            db: 异步数据库会话。
            event: 审计事件。

        Returns:
            MonitoringEvent: 已刷新事件。
        """
        db.add(event)
        await db.flush()
        await db.refresh(event)
        return event

    async def list_events(
        self,
        db: AsyncSession,
        project_id: int,
        limit: int = 100,
    ) -> Sequence[MonitoringEvent]:
        """查询最近监测审计事件。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            limit: 最大事件数。

        Returns:
            Sequence[MonitoringEvent]: 最近事件。
        """
        result = await db.execute(
            select(MonitoringEvent)
            .where(MonitoringEvent.project_id == project_id)
            .order_by(MonitoringEvent.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()
