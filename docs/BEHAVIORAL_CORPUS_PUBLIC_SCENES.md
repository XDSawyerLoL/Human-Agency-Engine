# HORIZON — Behavioral Knowledge Corpus & Public Scene Analyzer

## Goal

HORIZON should learn human-dynamics coefficients from documented evidence and observed outcomes rather than from a single model's intuition.

This layer adds two complementary evidence channels:

1. **Behavioral Knowledge** — scientific literature, open-science repositories and large survey archives.
2. **Public Scene Observation** — privacy-preserving aggregate observations from public or licensed camera streams where display and analysis are explicitly authorized.

Neither channel directly changes Human Dynamics coefficients yet. Retrieval and observation first become versioned evidence; empirical calibration comes after outcome extraction and held-out validation.

---

## Behavioral source plan

### Runtime adapters in V0.1

#### OpenAlex

Used for broad scholarly discovery across behavioral economics, psychology, sociology, collective behavior, decision science, public health, transport behavior and adjacent disciplines.

The adapter retrieves metadata, abstracts when available, open-access status, topics and citation counts. Citation count is kept as a discovery signal only; it is never treated as proof that a behavioral effect is true or replicated.

Environment variable:

```text
OPENALEX_API_KEY=<optional/free key depending on service policy>
```

#### PubMed / NCBI Entrez

Used for biomedical, neuroscience, health-behavior and behavioral-science literature. The adapter retrieves PubMed records and abstracts through NCBI E-utilities.

Optional environment variables:

```text
NCBI_EMAIL=<contact email recommended by NCBI>
NCBI_API_KEY=<optional key>
```

### Catalogued for controlled ingestion

#### Open Science Framework (OSF)

OSF contains public projects, registrations, preprints, study materials and research files. The next adapter should prioritize preregistrations, replications, open datasets and machine-readable study materials.

#### World Values Survey (WVS)

WVS provides cross-national values and attitudes data over multiple waves. Raw data must be retrieved under the official WVS terms and must not be silently mirrored or redistributed by HORIZON.

#### European Social Survey (ESS)

ESS provides repeated cross-national data on attitudes, beliefs, behavior and social conditions. Dataset versions, licences and citations must remain attached to any derived calibration artifact.

### Additional source families to add

- Crossref metadata and DOI graph
- PubMed Central open full text where licensing permits
- arXiv / PsyArXiv / SocArXiv metadata and open manuscripts
- DataCite research datasets
- GESIS social-science archives
- ICPSR datasets where access terms permit
- national statistical agencies and Eurostat behavioral/social indicators
- longitudinal household panels where licences permit
- transport/pedestrian/crowd datasets with objective movement outcomes
- replication databases and meta-analyses

---

## Evidence extraction target

A paper should not enter the predictive engine as unstructured prose. HORIZON needs an extraction record such as:

```json
{
  "construct": "social_norm_support",
  "population": "urban_adults",
  "context": "public transport disruption",
  "intervention_or_exposure": "peer compliance visible",
  "behavioral_outcome": "route adoption",
  "effect_direction": "positive",
  "effect_size": null,
  "effect_size_type": null,
  "sample_size": 0,
  "study_design": "observational",
  "replication_status": "unknown",
  "publication_bias_risk": "unknown",
  "source_ids": [],
  "licence": null
}
```

Future coefficient learning should weight study design, replication, sample size, population match, recency/context transfer, source independence and outcome objectivity.

---

## Public Scene Analyzer

### What it measures

The current scene engine accepts anonymous detections and computes:

- object counts;
- person frame occupancy;
- clustering/proximity index;
- aggregate movement speed;
- directional coherence;
- stationary share;
- anonymous dwell-time distributions;
- zone occupancy;
- congestion-like score;
- queue-like score;
- coherent directional-flow signal.

These outputs can become live evidence for Human Dynamics and Event Graph modules.

### What it does not do

The scene data schema is intentionally incompatible with biometric identity fields.

HORIZON Public Scene Analyzer does not support:

- facial recognition;
- identity lookup;
- cross-camera person re-identification;
- persistent tracking of a named or uniquely identifiable person;
- gait identification;
- race, ethnicity, religion, political affiliation or sexual-orientation inference;
- health-status inference;
- facial emotion or mental-state claims.

### Camera registry

HORIZON only displays cameras explicitly configured as authorized for display. Camera discovery is not an internet-wide CCTV scanner.

Configure a JSON list in:

```text
HORIZON_PUBLIC_CAMERAS_JSON
```

Example:

```json
[
  {
    "camera_id": "official-example-1",
    "label": "Public square webcam",
    "location_label": "Example City",
    "provider": "Official webcam provider",
    "public_page_url": "https://provider.example/camera/1",
    "preview_url": "https://provider.example/camera/1/preview.jpg",
    "embed_url": "https://provider.example/camera/1/embed",
    "latitude": 48.0,
    "longitude": 2.0,
    "display_authorized": true,
    "analysis_authorized": false,
    "terms_reference": "https://provider.example/terms"
  }
]
```

A stream may be display-authorized but not analysis-authorized. HORIZON keeps those two permissions separate.

### Windy Webcams

The cockpit is prepared for a future keyed Windy Webcams adapter. Windy exposes public webcam metadata, previews and timelapses through its Webcams API and supports link/embed use on its free tier subject to its terms.

Reserved environment variable:

```text
HORIZON_WINDY_WEBCAMS_API_KEY=<key>
```

The adapter should refresh tokenized preview URLs at page load rather than persist short-lived URLs.

---

## Vision edge adapter — next step

The backend V0.1 analyzes anonymous detections, not raw video. The next component should run close to the camera or in the browser/edge process:

```text
authorized camera frame
        ↓
object detector
        ↓
ephemeral anonymous tracklets
        ↓
velocity / dwell / zone metrics
        ↓
raw frame discarded
        ↓
aggregate SceneObservation → HORIZON
```

Tracklet identifiers, if an implementation needs them internally for motion estimation, should be short-lived and never leave the edge adapter.

Recommended technical approach:

- person/vehicle detector optimized for edge inference;
- short-lived motion tracker;
- no face crop pipeline;
- no biometric embeddings;
- raw-frame retention disabled by default;
- configurable sampling rate;
- per-camera authorization metadata;
- metric-only storage in HORIZON.

---

## Calibration path

The long-term objective is to connect documented human-behavior evidence with real outcomes:

```text
scientific prior
+ historical behavior datasets
+ current world signals
+ anonymous public-scene aggregates
→ Human Dynamics forecast
→ observed outcome
→ error measurement
→ coefficient recalibration
```

Metrics should include Brier score, log loss, calibration error, top-action accuracy, timing error and domain/population transfer error.

The system should retain the exact evidence snapshot available before each forecast to prevent hindsight leakage.
