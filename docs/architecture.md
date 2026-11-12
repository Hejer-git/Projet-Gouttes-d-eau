# Architecture

## Diagramme d'architecture
```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart TB
  subgraph SRC["Sources de données"]
    IC["API open data Infoclimat<br/>station OMM 07156"]
    IOT["Capteurs IoT agricoles<br/>(phase 2)"]
  end
  subgraph ING["Ingestion batch"]
    COL["Collecteur<br/>fenêtres de 30 jours<br/>reprise sur erreur"]
    CLN["Nettoyage et<br/>contrôle qualité"]
  end
  subgraph STO["Stockage et préparation"]
    AGG["Agrégation journalière<br/>régionale"]
    DB[("SQLite<br/>observation, daily_weather<br/>collection_run, prediction_log")]
  end
  subgraph ML["Apprentissage hors ligne"]
    FEA["Variables<br/>sans fuite"]
    TRN["Entraînement et<br/>validation temporelle"]
    REG[["Artefacts<br/>model_obs, model_clim<br/>metadata.json"]]
  end
  subgraph SRV["Service"]
    API["API FastAPI /v1<br/>predict, history,<br/>model, health"]
  end
  subgraph CLT["Clients"]
    UI["Interface Streamlit"]
    EXT["Systèmes tiers<br/>outils agricoles"]
  end
  CI["CI/CD GitHub Actions<br/>lint, tests, image Docker"]
  IC -->|"HTTPS JSON + jeton"| COL
  IOT -.->|"MQTT ou HTTPS"| COL
  COL --> CLN --> DB
  DB --> AGG --> DB
  DB --> FEA --> TRN --> REG
  REG --> API
  DB --> API
  API -->|"HTTP JSON"| UI
  API -->|"HTTP JSON + X-API-Key"| EXT
  CI -.-> API
```

## Diagramme de composants
```mermaid
%%{init: {'theme':'neutral'}}%%
flowchart TB
  subgraph PKG["Package goutte_deau"]
    CLI["cli.py<br/>commandes"]
    CFG["config.py<br/>paramètres (env)"]
    PIPE["pipeline.py<br/>orchestration"]
    COL["collector.py<br/>client Infoclimat / CSV"]
    HFQ["highfreq.py<br/>pas de 10 min vers 3 h"]
    SYN["synthetic.py<br/>données de test"]
    CLN["cleaning.py<br/>règles qualité"]
    DLY["daily.py<br/>agrégation"]
    DBM["db.py<br/>accès SQLite"]
    FEA["features.py<br/>variables"]
    TRN["train.py<br/>entraînement"]
    EVA["evaluate.py<br/>métriques"]
    PRD["predictor.py<br/>inférence"]
    QUA["quality.py<br/>indicateurs"]
    SCH["schemas.py<br/>modèles Pydantic"]
    API["api.py<br/>routes FastAPI"]
  end
  UI["app/streamlit_app.py<br/>interface"]
  S1[("SQLite")]
  S2[["models/*.joblib<br/>metadata.json"]]
  S3["API Infoclimat"]
  CLI --> PIPE
  CLI --> TRN
  CLI --> PRD
  CLI --> QUA
  PIPE --> COL
  PIPE --> HFQ
  PIPE --> SYN
  PIPE --> CLN
  PIPE --> DLY
  PIPE --> DBM
  COL -->|"HTTPS"| S3
  TRN --> FEA
  TRN --> EVA
  TRN --> DBM
  TRN -->|"écrit"| S2
  PRD --> FEA
  PRD --> DBM
  PRD -->|"lit"| S2
  QUA --> DBM
  DBM -->|"SQL paramétré"| S1
  API --> PRD
  API --> SCH
  API --> DBM
  API --> CFG
  UI -->|"HTTP JSON"| API
```

Images : `docs/img/architecture.png` et `docs/img/components.png` (sources Mermaid dans `docs/diagrams/`).

## Principes
- Le traitement par lots (collecte, nettoyage, entraînement) est séparé du service d'inférence (API).
- Une collecte rejouée met à jour la base sans créer de doublons.
- Cinq variables seulement, un modèle léger, SQLite sans serveur.
- Le schéma est portable vers PostgreSQL ; les capteurs IoT s'ajoutent en amont du collecteur.
