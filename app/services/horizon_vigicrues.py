from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256

import httpx
from sqlalchemy.orm import Session

from ..horizon_convergence_schemas import HorizonVigicruesPollRequest
from ..horizon_source_models import HorizonRawObservation, HorizonSource
from ..horizon_source_schemas import HorizonCandidateBuild, HorizonObservationIngest, HorizonSourceUpsert
from .horizon_sources import HorizonSourceService


VIGICRUES_GEOJSON_ENDPOINT = "https://www.vigicrues.gouv.fr/services/InfoVigiCru.geojson"
LEVEL_NAMES = {1: "vert", 2: "jaune", 3: "orange", 4: "rouge"}


class HorizonVigicruesService:
    ENGINE_VERSION = "horizon-vigicrues-v1.1-v0.1"
    USER_AGENT = "Human-Agency-Engine-HORIZON/0.1"

    def __init__(self, db: Session):
        self.db = db

    def _source(self) -> HorizonSource:
        source = HorizonSourceService(self.db).upsert_source(
            HorizonSourceUpsert(
                source_key="vigicrues-official",
                name="Vigicrues official vigilance",
                source_class="official_primary",
                adapter_kind="vigicrues_info_geojson_v1_1",
                domains=["flood", "hydrology", "civil_protection", "realtime"],
                geography=["FR"],
                base_locator=VIGICRUES_GEOJSON_ENDPOINT,
                trust_weight=0.98,
                refresh_seconds=1800,
                requires_credentials=False,
                enabled=True,
                metadata_json={
                    "role": "official_river_flood_vigilance",
                    "evidence_roles": ["confirmation", "physical_state"],
                    "provider": "Vigicrues",
                    "warning_horizon_hours": 24,
                    "format": "GeoJSON",
                },
            )
        )
        if not source.enabled:
            raise ValueError("Vigicrues source is disabled")
        return source

    @staticmethod
    def _feature_identity(properties: dict, geometry: object) -> str:
        stable = {
            "segment": properties.get("CdEntCru") or properties.get("cdentcru") or properties.get("id"),
            "label": properties.get("lbentcru") or properties.get("LbEntCru"),
            "level": properties.get("NivInfViCr"),
            "geometry": geometry,
        }
        return sha256(repr(stable).encode("utf-8")).hexdigest()[:32]

    @staticmethod
    def _bbox(geometry: object) -> list[float] | None:
        if not isinstance(geometry, dict):
            return None
        coordinates = geometry.get("coordinates")
        points: list[tuple[float, float]] = []

        def walk(value: object) -> None:
            if isinstance(value, list):
                if len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
                    points.append((float(value[0]), float(value[1])))
                else:
                    for item in value:
                        walk(item)

        walk(coordinates)
        if not points:
            return None
        xs = [item[0] for item in points]
        ys = [item[1] for item in points]
        return [min(xs), min(ys), max(xs), max(ys)]

    def poll(
        self,
        request: HorizonVigicruesPollRequest,
        *,
        client: httpx.Client | None = None,
        observed_at: datetime | None = None,
    ) -> dict:
        source = self._source()
        as_of = observed_at or datetime.now(timezone.utc)
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=timezone.utc)
        owned_client = client is None
        if client is None:
            client = httpx.Client(
                timeout=httpx.Timeout(20.0),
                follow_redirects=True,
                headers={"User-Agent": self.USER_AGENT, "Accept": "application/geo+json,application/json"},
            )
        try:
            response = client.get(VIGICRUES_GEOJSON_ENDPOINT)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RuntimeError(f"Vigicrues poll failed: {str(exc)[:300]}") from exc
        finally:
            if owned_client:
                client.close()

        features = payload.get("features") if isinstance(payload, dict) else None
        if not isinstance(features, list):
            raise RuntimeError("Vigicrues response contains no GeoJSON features")

        created_observations: list[int] = []
        replayed_observations: list[int] = []
        candidate_ids: list[int] = []
        event_ids: list[int] = []
        ignored = 0
        source_service = HorizonSourceService(self.db)
        for feature in features[: request.max_features]:
            if not isinstance(feature, dict):
                continue
            props = feature.get("properties") or {}
            if not isinstance(props, dict):
                continue
            try:
                level = int(props.get("NivInfViCr") or 0)
            except (TypeError, ValueError):
                level = 0
            if level < request.minimum_level:
                ignored += 1
                continue
            segment = str(props.get("CdEntCru") or props.get("cdentcru") or props.get("id") or "").strip()
            label = str(props.get("lbentcru") or props.get("LbEntCru") or segment or "tronçon").strip()
            if not segment:
                continue
            identity = self._feature_identity(props, feature.get("geometry"))
            external_key = f"vigicrues:{segment}:{level}:{identity}"
            existing = self.db.query(HorizonRawObservation).filter(
                HorizonRawObservation.source_id == source.id,
                HorizonRawObservation.external_key == external_key,
            ).one_or_none()
            if existing is None:
                observation = HorizonObservationIngest(
                    external_key=external_key,
                    observation_type="official_river_flood_vigilance",
                    title=f"Vigicrues {LEVEL_NAMES.get(level, level)} — {label}"[:255],
                    summary=(
                        f"Vigilance crues officielle niveau {LEVEL_NAMES.get(level, level)} "
                        f"sur le tronçon {label}."
                    ),
                    source_url=VIGICRUES_GEOJSON_ENDPOINT,
                    geography=["FR", f"VIGICRUES:{segment}"],
                    canonical_facts={
                        "segment_code": segment,
                        "segment_label": label,
                        "vigilance_level": level,
                        "vigilance_color": LEVEL_NAMES.get(level, str(level)),
                        "territory_code": props.get("cdensup_1"),
                        "territory_type": props.get("typensup_1"),
                        "bbox": self._bbox(feature.get("geometry")),
                    },
                    raw_metadata={
                        "engine": self.ENGINE_VERSION,
                        "feature_id": feature.get("id") or props.get("id"),
                        "provider_properties": props,
                        "geometry_type": (feature.get("geometry") or {}).get("type") if isinstance(feature.get("geometry"), dict) else None,
                        "warning_horizon_hours": 24,
                    },
                    event_time=as_of,
                    published_at=None,
                    observed_at=as_of,
                )
                observation_row, _ = source_service.ingest_observation(source, observation)
                created_observations.append(observation_row.id)
            else:
                observation_row = existing
                replayed_observations.append(existing.id)

            candidate = source_service.build_candidate(
                HorizonCandidateBuild(
                    observation_ids=[observation_row.id],
                    event_type="river_flood_risk",
                    title=f"Vigicrues {LEVEL_NAMES.get(level, level)} — {label}"[:255],
                    geography=["FR", f"VIGICRUES:{segment}"],
                    normalized_facts={
                        "provider": "vigicrues",
                        "segment_code": segment,
                        "segment_label": label,
                        "vigilance_level": level,
                        "vigilance_color": LEVEL_NAMES.get(level, str(level)),
                        "official_warning_horizon_hours": 24,
                        "physical_state_not_behavior": True,
                    },
                    normalizer_version=self.ENGINE_VERSION,
                )
            )
            candidate_ids.append(candidate.id)
            event = source_service.promote_candidate(candidate)
            event_ids.append(event.id)

        return {
            "engine": self.ENGINE_VERSION,
            "source_key": source.source_key,
            "features_received": len(features),
            "minimum_level": request.minimum_level,
            "features_ignored_below_threshold": ignored,
            "new_observations": len(set(created_observations)),
            "replayed_observations": len(set(replayed_observations)),
            "candidates_created_or_reused": len(set(candidate_ids)),
            "promoted_events_created_or_reused": len(set(event_ids)),
            "event_ids": sorted(set(event_ids)),
            "critical_semantics": {
                "source_is_official_primary": True,
                "warning_is_behavioral_signal": False,
                "warning_horizon_hours": 24,
                "vigilance_level_is_probability": False,
            },
        }
