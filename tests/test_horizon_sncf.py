from datetime import datetime, timezone
from uuid import uuid4

import httpx

from app.db import SessionLocal
from app.horizon_convergence_schemas import HorizonSncfPollRequest
from app.horizon_models import HorizonGlobalEvent
from app.services.horizon_sncf import HorizonSncfService, SNCF_SIRI_ENDPOINT


def test_sncf_siri_alert_becomes_official_operational_event_without_behavior_claim():
    db = SessionLocal()
    tag = uuid4().hex[:10]
    xml = f"""<?xml version='1.0' encoding='UTF-8'?>
    <Siri xmlns='http://www.siri.org.uk/siri'>
      <ServiceDelivery>
        <SituationExchangeDelivery>
          <Situations>
            <PtSituationElement>
              <CreationTime>2026-08-20T00:00:00Z</CreationTime>
              <SituationNumber>FR:SNCF:{tag}</SituationNumber>
              <Progress>open</Progress>
              <Severity>severe</Severity>
              <Summary>Trafic interrompu sur une ligne test</Summary>
              <Description>Incident d'exploitation synthétique.</Description>
              <ValidityPeriod>
                <StartTime>2026-08-20T00:05:00Z</StartTime>
                <EndTime>2026-08-20T03:00:00Z</EndTime>
              </ValidityPeriod>
              <Affects><Networks><AffectedNetwork><AffectedLine><LineRef>line-{tag}</LineRef></AffectedLine></AffectedNetwork></Networks></Affects>
            </PtSituationElement>
          </Situations>
        </SituationExchangeDelivery>
      </ServiceDelivery>
    </Siri>""".encode("utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == SNCF_SIRI_ENDPOINT
        return httpx.Response(200, content=xml, headers={"content-type": "application/xml"}, request=request)

    mock = httpx.Client(transport=httpx.MockTransport(handler))
    request = HorizonSncfPollRequest(max_situations=10)
    observed_at = datetime(2026, 8, 20, 0, 10, tzinfo=timezone.utc)
    try:
        first = HorizonSncfService(db).poll(request, client=mock, observed_at=observed_at)
        assert first["new_observations"] == 1
        assert first["promoted_events_created_or_reused"] == 1
        assert first["critical_semantics"]["transport_disruption_is_behavioral_outcome"] is False
        event = db.query(HorizonGlobalEvent).filter(HorizonGlobalEvent.id == first["event_ids"][0]).one()
        assert event.event_type == "rail_transport_disruption"
        assert event.source == "sncf-service-alerts"
        assert event.raw_facts["normalized_facts"]["operational_impact"] is True
        assert event.raw_facts["normalized_facts"]["line_ref"] == f"line-{tag}"

        replay = HorizonSncfService(db).poll(request, client=mock, observed_at=observed_at)
        assert replay["new_observations"] == 0
        assert replay["replayed_observations"] == 1
        assert replay["event_ids"] == first["event_ids"]
    finally:
        mock.close()
        db.close()
