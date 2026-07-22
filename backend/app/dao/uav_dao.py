"""无人机航空器、飞行任务、实体成果和疑点数据访问层。"""

import json
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.uav import UavAircraft, UavArtifact, UavEvent, UavFinding, UavMission
from app.models.workbench import MonitoringProject, MonitoringTask, TaskPlot


@dataclass(frozen=True)
class MissionRecord:
    """带任务、航空器和 GeoJSON 范围的飞行任务记录。"""

    mission: UavMission
    task_code: str
    aircraft_code: str
    aircraft_name: str
    boundary_geojson: dict


@dataclass(frozen=True)
class ArtifactRecord:
    """带任务编号和 GeoJSON 覆盖范围的实体成果记录。"""

    artifact: UavArtifact
    mission_code: str
    footprint_geojson: dict | None


@dataclass(frozen=True)
class FindingRecord:
    """带任务和成果编号的无人机疑点记录。"""

    finding: UavFinding
    mission_code: str
    artifact_code: str


class UavDAO:
    """封装无人机任务全流程数据库操作。"""

    async def get_project_by_code(
        self,
        db: AsyncSession,
        project_code: str,
    ) -> MonitoringProject | None:
        """按编号查询项目。

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

    async def get_task_by_code(
        self,
        db: AsyncSession,
        task_code: str,
    ) -> MonitoringTask | None:
        """按编号查询作业任务。

        Args:
            db: 异步数据库会话。
            task_code: 任务编号。

        Returns:
            MonitoringTask | None: 任务或空值。
        """
        result = await db.execute(
            select(MonitoringTask).where(MonitoringTask.task_code == task_code)
        )
        return result.scalar_one_or_none()

    async def get_aircraft_by_code(
        self,
        db: AsyncSession,
        project_id: int,
        aircraft_code: str,
    ) -> UavAircraft | None:
        """查询项目内航空器。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            aircraft_code: 航空器编号。

        Returns:
            UavAircraft | None: 航空器或空值。
        """
        result = await db.execute(
            select(UavAircraft).where(
                UavAircraft.project_id == project_id,
                UavAircraft.aircraft_code == aircraft_code,
            )
        )
        return result.scalar_one_or_none()

    async def add_aircraft(
        self,
        db: AsyncSession,
        aircraft: UavAircraft,
    ) -> UavAircraft:
        """新增航空器。

        Args:
            db: 异步数据库会话。
            aircraft: 航空器模型。

        Returns:
            UavAircraft: 已刷新航空器。
        """
        db.add(aircraft)
        await db.flush()
        await db.refresh(aircraft)
        return aircraft

    async def list_aircraft(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> Sequence[UavAircraft]:
        """查询项目航空器目录。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            Sequence[UavAircraft]: 航空器列表。
        """
        result = await db.execute(
            select(UavAircraft)
            .where(UavAircraft.project_id == project_id)
            .order_by(UavAircraft.aircraft_code)
        )
        return result.scalars().all()

    async def create_mission_with_validated_boundary(
        self,
        db: AsyncSession,
        *,
        project_id: int,
        task_id: int,
        aircraft_id: int,
        mission: UavMission,
        boundary_geojson: dict,
    ) -> UavMission | None:
        """校验飞行面完全位于真实县界后写入任务。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            task_id: 作业任务主键。
            aircraft_id: 航空器主键。
            mission: 不含持久化几何的任务模型。
            boundary_geojson: WGS84 GeoJSON Polygon。

        Returns:
            UavMission | None: 已写入任务；越界或无效时为空。
        """
        statement = text(
            """
            WITH candidate AS (
                SELECT ST_SetSRID(
                    ST_GeomFromGeoJSON(:boundary_geojson),
                    4326
                ) AS geom
            ), validated AS (
                SELECT
                    candidate.geom,
                    boundary.boundary_name,
                    ST_Area(candidate.geom::geography) / 10000.0 AS area_ha
                FROM candidate
                JOIN administrative_boundaries AS boundary
                  ON boundary.project_id = :project_id
                 AND boundary.boundary_code = :district_code
                 AND boundary.boundary_level = 'district'
                 AND ST_Covers(boundary.geom, candidate.geom)
                WHERE ST_IsValid(candidate.geom)
                  AND GeometryType(candidate.geom) = 'POLYGON'
                  AND ST_Area(candidate.geom::geography) > 0
            )
            INSERT INTO uav_missions (
                project_id, task_id, aircraft_id, mission_code, mission_name,
                district_code, district_name, flight_boundary, planned_area_ha,
                pilot_name, pilot_license_number, pilot_license_uri,
                pilot_license_filename, pilot_license_size_bytes,
                pilot_license_sha256, planned_start_at, planned_end_at,
                altitude_m, expected_resolution_cm, forward_overlap_percent,
                side_overlap_percent, weather_note, status, created_by,
                created_by_code, created_by_role
            )
            SELECT
                :project_id, :task_id, :aircraft_id, :mission_code, :mission_name,
                :district_code, validated.boundary_name, validated.geom,
                validated.area_ha, :pilot_name, :pilot_license_number,
                :pilot_license_uri, :pilot_license_filename,
                :pilot_license_size_bytes, :pilot_license_sha256,
                :planned_start_at, :planned_end_at, :altitude_m,
                :expected_resolution_cm, :forward_overlap_percent,
                :side_overlap_percent, :weather_note, 'planned', :created_by,
                :created_by_code, :created_by_role
            FROM validated
            RETURNING id
            """
        )
        result = await db.execute(
            statement,
            {
                "project_id": project_id,
                "task_id": task_id,
                "aircraft_id": aircraft_id,
                "district_code": mission.district_code,
                "boundary_geojson": json.dumps(boundary_geojson),
                "mission_code": mission.mission_code,
                "mission_name": mission.mission_name,
                "pilot_name": mission.pilot_name,
                "pilot_license_number": mission.pilot_license_number,
                "pilot_license_uri": mission.pilot_license_uri,
                "pilot_license_filename": mission.pilot_license_filename,
                "pilot_license_size_bytes": mission.pilot_license_size_bytes,
                "pilot_license_sha256": mission.pilot_license_sha256,
                "planned_start_at": mission.planned_start_at,
                "planned_end_at": mission.planned_end_at,
                "altitude_m": mission.altitude_m,
                "expected_resolution_cm": mission.expected_resolution_cm,
                "forward_overlap_percent": mission.forward_overlap_percent,
                "side_overlap_percent": mission.side_overlap_percent,
                "weather_note": mission.weather_note,
                "created_by": mission.created_by,
                "created_by_code": mission.created_by_code,
                "created_by_role": mission.created_by_role,
            },
        )
        mission_id = result.scalar_one_or_none()
        if mission_id is None:
            return None
        created = await db.execute(
            select(UavMission).where(UavMission.id == mission_id)
        )
        return created.scalar_one()

    async def get_mission_by_code(
        self,
        db: AsyncSession,
        project_id: int,
        mission_code: str,
        *,
        for_update: bool = False,
    ) -> UavMission | None:
        """查询飞行任务并可锁定。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            mission_code: 任务编号。
            for_update: 是否加行锁。

        Returns:
            UavMission | None: 飞行任务或空值。
        """
        statement = select(UavMission).where(
            UavMission.project_id == project_id,
            UavMission.mission_code == mission_code,
        )
        if for_update:
            statement = statement.with_for_update()
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    async def list_mission_records(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> list[MissionRecord]:
        """查询飞行任务及关联身份和边界。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            list[MissionRecord]: 飞行任务记录。
        """
        result = await db.execute(
            select(
                UavMission,
                MonitoringTask.task_code,
                UavAircraft.aircraft_code,
                UavAircraft.aircraft_name,
                func.ST_AsGeoJSON(UavMission.flight_boundary),
            )
            .join(MonitoringTask, MonitoringTask.id == UavMission.task_id)
            .join(UavAircraft, UavAircraft.id == UavMission.aircraft_id)
            .where(UavMission.project_id == project_id)
            .order_by(UavMission.created_at.desc())
        )
        return [
            MissionRecord(
                mission=row[0],
                task_code=str(row[1]),
                aircraft_code=str(row[2]),
                aircraft_name=str(row[3]),
                boundary_geojson=json.loads(str(row[4])),
            )
            for row in result
        ]

    async def get_artifact_by_code(
        self,
        db: AsyncSession,
        mission_id: int,
        artifact_code: str,
    ) -> UavArtifact | None:
        """查询任务实体成果。

        Args:
            db: 异步数据库会话。
            mission_id: 飞行任务主键。
            artifact_code: 成果编号。

        Returns:
            UavArtifact | None: 成果或空值。
        """
        result = await db.execute(
            select(UavArtifact).where(
                UavArtifact.mission_id == mission_id,
                UavArtifact.artifact_code == artifact_code,
            )
        )
        return result.scalar_one_or_none()

    async def add_artifact(
        self,
        db: AsyncSession,
        artifact: UavArtifact,
    ) -> UavArtifact:
        """新增无人机实体成果。

        Args:
            db: 异步数据库会话。
            artifact: 成果模型。

        Returns:
            UavArtifact: 已刷新成果。
        """
        db.add(artifact)
        await db.flush()
        await db.refresh(artifact)
        return artifact

    async def list_artifact_records(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> list[ArtifactRecord]:
        """查询项目无人机实体成果和覆盖范围。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            list[ArtifactRecord]: 成果记录。
        """
        result = await db.execute(
            select(
                UavArtifact,
                UavMission.mission_code,
                func.ST_AsGeoJSON(UavArtifact.footprint),
            )
            .join(UavMission, UavMission.id == UavArtifact.mission_id)
            .where(UavMission.project_id == project_id)
            .order_by(UavArtifact.created_at.desc())
        )
        return [
            ArtifactRecord(
                artifact=row[0],
                mission_code=str(row[1]),
                footprint_geojson=(
                    json.loads(str(row[2])) if row[2] is not None else None
                ),
            )
            for row in result
        ]

    async def artifact_footprint_covers_mission(
        self,
        db: AsyncSession,
        artifact_id: int,
        mission_id: int,
    ) -> bool:
        """判断正射成果覆盖范围是否完整覆盖任务范围。

        Args:
            db: 异步数据库会话。
            artifact_id: 成果主键。
            mission_id: 任务主键。

        Returns:
            bool: 完整覆盖时为真。
        """
        result = await db.execute(
            select(
                func.ST_Covers(UavArtifact.footprint, UavMission.flight_boundary)
            )
            .join(UavMission, UavMission.id == mission_id)
            .where(
                UavArtifact.id == artifact_id,
                UavArtifact.mission_id == mission_id,
                UavArtifact.footprint.is_not(None),
            )
        )
        return bool(result.scalar_one_or_none())

    async def point_within_mission(
        self,
        db: AsyncSession,
        mission_id: int,
        longitude: float,
        latitude: float,
    ) -> bool:
        """判断疑点坐标是否位于飞行范围内。

        Args:
            db: 异步数据库会话。
            mission_id: 任务主键。
            longitude: WGS84 经度。
            latitude: WGS84 纬度。

        Returns:
            bool: 位于范围内时为真。
        """
        point = func.ST_SetSRID(func.ST_Point(longitude, latitude), 4326)
        result = await db.execute(
            select(func.ST_Covers(UavMission.flight_boundary, point)).where(
                UavMission.id == mission_id
            )
        )
        return bool(result.scalar_one_or_none())

    async def plot_belongs_to_task(
        self,
        db: AsyncSession,
        task_id: int,
        plot_code: str,
    ) -> bool:
        """校验疑点关联图斑属于当前任务。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。
            plot_code: 图斑编号。

        Returns:
            bool: 任务已显式分配该图斑时为真。
        """
        result = await db.execute(
            select(TaskPlot.id).where(
                TaskPlot.task_id == task_id,
                TaskPlot.plot_code == plot_code,
            )
        )
        return result.scalar_one_or_none() is not None

    async def add_finding(
        self,
        db: AsyncSession,
        finding: UavFinding,
    ) -> UavFinding:
        """新增无人机疑点。

        Args:
            db: 异步数据库会话。
            finding: 疑点模型。

        Returns:
            UavFinding: 已刷新疑点。
        """
        db.add(finding)
        await db.flush()
        await db.refresh(finding)
        return finding

    async def get_finding_by_code(
        self,
        db: AsyncSession,
        mission_id: int,
        finding_code: str,
        *,
        for_update: bool = False,
    ) -> UavFinding | None:
        """查询任务疑点并可锁定。

        Args:
            db: 异步数据库会话。
            mission_id: 飞行任务主键。
            finding_code: 疑点编号。
            for_update: 是否加行锁。

        Returns:
            UavFinding | None: 疑点或空值。
        """
        statement = select(UavFinding).where(
            UavFinding.mission_id == mission_id,
            UavFinding.finding_code == finding_code,
        )
        if for_update:
            statement = statement.with_for_update()
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    async def list_finding_records(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> list[FindingRecord]:
        """查询项目无人机疑点及关联编号。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            list[FindingRecord]: 疑点记录。
        """
        result = await db.execute(
            select(UavFinding, UavMission.mission_code, UavArtifact.artifact_code)
            .join(UavMission, UavMission.id == UavFinding.mission_id)
            .join(UavArtifact, UavArtifact.id == UavFinding.artifact_id)
            .where(UavMission.project_id == project_id)
            .order_by(UavFinding.created_at.desc())
        )
        return [
            FindingRecord(
                finding=row[0],
                mission_code=str(row[1]),
                artifact_code=str(row[2]),
            )
            for row in result
        ]

    async def count_pending_findings(
        self,
        db: AsyncSession,
        mission_id: int,
    ) -> int:
        """统计任务待复核疑点。

        Args:
            db: 异步数据库会话。
            mission_id: 飞行任务主键。

        Returns:
            int: 待复核疑点数。
        """
        result = await db.execute(
            select(func.count(UavFinding.id)).where(
                UavFinding.mission_id == mission_id,
                UavFinding.status == "pending_review",
            )
        )
        return int(result.scalar_one())

    async def add_event(
        self,
        db: AsyncSession,
        event: UavEvent,
    ) -> UavEvent:
        """新增无人机不可变审计事件。

        Args:
            db: 异步数据库会话。
            event: 审计事件。

        Returns:
            UavEvent: 已刷新事件。
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
    ) -> Sequence[UavEvent]:
        """查询最近无人机审计事件。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            limit: 最大事件数。

        Returns:
            Sequence[UavEvent]: 最近事件。
        """
        result = await db.execute(
            select(UavEvent)
            .where(UavEvent.project_id == project_id)
            .order_by(UavEvent.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()
