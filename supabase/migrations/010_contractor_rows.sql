-- Migration 010: Contractor pipeline tables
-- Apply to live project: hdhovyrlnfojtkqbcegh
-- Run Phase 0A Python migration script AFTER this migration is applied.

-- ---------------------------------------------------------------------------
-- pipeline_config
-- One row per market. The orchestrator loads this at run start.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pipeline_config (
  id                        uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  market_id                 text        UNIQUE NOT NULL,
  display_name              text,
  country                   text        NOT NULL,
  locale                    text        NOT NULL,
  cities                    jsonb       NOT NULL DEFAULT '[]',
  tier_a_subcategories      jsonb       NOT NULL DEFAULT '[]',
  tier_b_subcategories      jsonb       NOT NULL DEFAULT '[]',
  role_map                  jsonb       NOT NULL DEFAULT '{}',
  subcategory_local_map     jsonb       NOT NULL DEFAULT '{}',
  search_templates          jsonb       NOT NULL DEFAULT '[]',
  batch_size                integer     NOT NULL DEFAULT 10,
  min_yield_threshold       integer     NOT NULL DEFAULT 3,
  research                  jsonb       NOT NULL DEFAULT '{}',
  active                    boolean     NOT NULL DEFAULT true,
  -- Migration lock: set true until Phase 0A completes, then release
  migration_locked          boolean     NOT NULL DEFAULT true,
  migration_validated_at    timestamptz,
  migration_row_count       integer,
  -- New market first-run gate
  first_run                 boolean     NOT NULL DEFAULT true,
  gate_after_research       boolean     NOT NULL DEFAULT false,
  gate_before_sync          boolean     NOT NULL DEFAULT false,
  created_at                timestamptz NOT NULL DEFAULT now(),
  updated_at                timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- contractor_rows
-- Canonical contractor/company record store. Replaces XLSX as source of truth.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS contractor_rows (
  id                        uuid        PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Market scope
  market_id                 text        NOT NULL REFERENCES pipeline_config(market_id),

  -- Identity (normalized)
  company                   text        NOT NULL,
  company_display           text,
  city                      text        NOT NULL DEFAULT '',
  city_normalized           text,
  country                   text        NOT NULL DEFAULT 'CO',
  category                  text,
  subcategory               text,
  integration_type          text,
  role_in_reformai          text,
  company_url               text,
  company_url_domain        text,

  -- Dedupe keys
  dedupe_key                text        UNIQUE NOT NULL,
  domain_dedupe_key         text,

  -- Research stage
  contact_name              text,
  contact_role              text,
  contact_link              text,
  priority_tier             text,
  relationship_strength     text,
  research_notes            text,
  confidence_score          float,

  -- Extraction stage
  email                     text,
  phone                     text,
  contact_logic             text,
  contact_source_url        text,
  extraction_status         text        NOT NULL DEFAULT 'pending',
  extraction_notes          text,
  failure_triage            text,
  validated_replacement_url text,
  validated_final_url       text,
  url_validation_result     text,
  search_discovery_result   text,
  search_replacement_url    text,
  search_discovery_notes    text,
  search_source             text,
  search_query              text,

  -- Catalog stage
  catalog_tier              text,
  site_type                 text,
  catalog_confirmed         boolean,
  product_subpages_found    boolean,
  product_count_estimate    integer     DEFAULT 0,
  image_count               integer     DEFAULT 0,
  has_specs                 boolean,
  selected_for_extraction   boolean,
  catalog_notes             text,

  -- Run provenance
  created_by_run_id         uuid        REFERENCES runs(id),
  last_updated_by_run_id    uuid        REFERENCES runs(id),

  -- Migration metadata (populated during Phase 0A; null for records created by orchestrator)
  source_system             text        NOT NULL DEFAULT 'orchestrator',
  migration_batch_id        text,
  legacy_workbook_name      text,
  legacy_sheet_name         text,
  legacy_row_number         integer,
  legacy_import_notes       text,

  -- HubSpot (reserved — NOT populated until future HubSpot phase)
  hubspot_company_id        text,
  hubspot_contact_id        text,
  hubspot_sync_status       text        NOT NULL DEFAULT 'not_synced',
  hubspot_last_synced_at    timestamptz,
  hubspot_sync_error        text,
  hubspot_owner_id          text,
  hubspot_lifecycle_stage   text,
  hubspot_external_id       text,

  -- Timestamps
  created_at                timestamptz NOT NULL DEFAULT now(),
  updated_at                timestamptz NOT NULL DEFAULT now()
);

-- Indexes
CREATE UNIQUE INDEX IF NOT EXISTS contractor_rows_dedupe_key
  ON contractor_rows(dedupe_key);

CREATE INDEX IF NOT EXISTS contractor_rows_domain
  ON contractor_rows(company_url_domain, market_id)
  WHERE company_url_domain IS NOT NULL;

CREATE INDEX IF NOT EXISTS contractor_rows_email
  ON contractor_rows(email)
  WHERE email IS NOT NULL;

CREATE INDEX IF NOT EXISTS contractor_rows_extraction_status
  ON contractor_rows(extraction_status, market_id);

CREATE INDEX IF NOT EXISTS contractor_rows_market_subcategory_city
  ON contractor_rows(market_id, subcategory, city_normalized);

CREATE INDEX IF NOT EXISTS contractor_rows_migration_batch
  ON contractor_rows(migration_batch_id)
  WHERE migration_batch_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS contractor_rows_hubspot_status
  ON contractor_rows(hubspot_sync_status, market_id);

-- ---------------------------------------------------------------------------
-- contractor_evidence
-- Raw research provenance per row — source URLs, content snippets, confidence.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS contractor_evidence (
  id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id              uuid        REFERENCES runs(id),
  contractor_row_id   uuid        REFERENCES contractor_rows(id) ON DELETE CASCADE,
  source_url          text,
  source_type         text,  -- 'search_result' | 'company_page' | 'directory_listing'
  raw_content         text,
  search_query        text,
  confidence_score    float,
  captured_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS contractor_evidence_row
  ON contractor_evidence(contractor_row_id);

CREATE INDEX IF NOT EXISTS contractor_evidence_run
  ON contractor_evidence(run_id);

-- ---------------------------------------------------------------------------
-- contractor_approval_queue
-- Gate records. Operator approves here before pipeline proceeds.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS contractor_approval_queue (
  id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id          uuid        REFERENCES runs(id),
  market_id       text        REFERENCES pipeline_config(market_id),
  gate_type       text        NOT NULL,
  -- 'research_yield_low' | 'first_run' | 'pre_extraction' | 'pre_hubspot_sync'
  trigger_reason  text,
  rows_pending    integer,
  status          text        NOT NULL DEFAULT 'pending',
  -- 'pending' | 'approved' | 'rejected' | 'auto_passed'
  reviewed_at     timestamptz,
  review_notes    text,
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS contractor_approval_pending
  ON contractor_approval_queue(status, market_id)
  WHERE status = 'pending';

-- ---------------------------------------------------------------------------
-- contractor_sync_log
-- Row-level HubSpot sync history. Reserved — not populated until HubSpot phase.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS contractor_sync_log (
  id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id              uuid        REFERENCES runs(id),
  contractor_row_id   uuid        REFERENCES contractor_rows(id) ON DELETE CASCADE,
  sync_operation      text,
  -- 'create_company' | 'update_company' | 'create_contact' | 'associate'
  hubspot_object_id   text,
  status              text,  -- 'success' | 'error' | 'skipped'
  error_message       text,
  request_payload     jsonb,
  response_payload    jsonb,
  synced_at           timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS contractor_sync_log_row
  ON contractor_sync_log(contractor_row_id);

-- ---------------------------------------------------------------------------
-- Seed pipeline_config for Colombia (existing market, migration_locked = true)
-- ---------------------------------------------------------------------------
INSERT INTO pipeline_config (
  market_id, display_name, country, locale,
  cities,
  tier_a_subcategories,
  tier_b_subcategories,
  role_map,
  subcategory_local_map,
  search_templates,
  batch_size, min_yield_threshold,
  research,
  active, migration_locked, first_run,
  gate_after_research, gate_before_sync
) VALUES (
  'co-renovation',
  'Colombia Renovation Contractors',
  'CO', 'es-CO',
  '["Bogota","Medellin","Cali","Barranquilla","Santa Marta"]',
  '["Tile & Ceramic Installer","Hardwood / Engineered Wood Flooring Installer","Vinyl / SPC / LVP Flooring Installer","Countertop Fabricator & Installer","Microcement Applicator (Floors & Walls)","Carpet Installer","Epoxy Floor Coating Specialist","Concrete Polishing & Grinding","Stone Restoration & Polishing","Glass, Glazing & Mirror Installer","Backsplash & Tile Installer"]',
  '["Painter (Interior & Exterior)","Fireplace & Chimney Installer","Wallpaper Installer","HVAC Installer"]',
  '{"Tile & Ceramic Installer":"Tile and ceramic installation for renovation projects","Hardwood / Engineered Wood Flooring Installer":"Hardwood and engineered wood flooring supply and installation","Vinyl / SPC / LVP Flooring Installer":"Vinyl and SPC flooring supply and installation","Countertop Fabricator & Installer":"Countertop supply and install for kitchen/bath renovations","Microcement Applicator (Floors & Walls)":"Microcement surface application","Carpet Installer":"Carpet supply and installation","Epoxy Floor Coating Specialist":"Epoxy and resin floor coatings","Concrete Polishing & Grinding":"Concrete polishing and grinding","Stone Restoration & Polishing":"Stone restoration and polishing","Glass, Glazing & Mirror Installer":"Glass, mirror and shower division install","Backsplash & Tile Installer":"Backsplash and tile installation","Painter (Interior & Exterior)":"Painting services for renovation projects","Fireplace & Chimney Installer":"Fireplace design, supply, and installation","Wallpaper Installer":"Wallpaper and wall-covering install","HVAC Installer":"A/C and ventilation install"}',
  '{"es-CO":{"Tile & Ceramic Installer":"instalador de ceramica y porcelana","Hardwood / Engineered Wood Flooring Installer":"instalador de pisos de madera","Vinyl / SPC / LVP Flooring Installer":"instalador de pisos vinilicos","Countertop Fabricator & Installer":"fabricante e instalador de mesones","Microcement Applicator (Floors & Walls)":"aplicador de microcemento","Carpet Installer":"instalador de alfombras","Epoxy Floor Coating Specialist":"especialista en pisos de epoxido","Concrete Polishing & Grinding":"pulido y esmerilado de concreto","Stone Restoration & Polishing":"restauracion y pulido de piedra","Glass, Glazing & Mirror Installer":"instalador de vidrio y espejos","Backsplash & Tile Installer":"instalador de salpicadero y azulejo","Painter (Interior & Exterior)":"pintor de interiores y exteriores","Fireplace & Chimney Installer":"instalador de chimeneas","Wallpaper Installer":"instalador de papel tapiz","HVAC Installer":"instalador de aire acondicionado y ventilacion"}}',
  '["{subcategory_local} {city} Colombia empresa","{subcategory_local} {city} contratista","{subcategory_local} {city} proveedor"]',
  10, 3,
  '{"max_per_query":5,"confidence_threshold":0.65,"tavily_topic":"general"}',
  true,
  true,   -- migration_locked: release AFTER Phase 0A validates
  false,  -- first_run: false because historical data exists
  false, false
)
ON CONFLICT (market_id) DO NOTHING;

-- Seed Mexico (greenfield — no migration needed, lock is false)
INSERT INTO pipeline_config (
  market_id, display_name, country, locale,
  cities, tier_a_subcategories, tier_b_subcategories,
  role_map, subcategory_local_map, search_templates,
  batch_size, min_yield_threshold, research,
  active, migration_locked, first_run,
  gate_after_research, gate_before_sync
) VALUES (
  'mx-renovation',
  'Mexico Renovation Contractors',
  'MX', 'es-MX',
  '["Ciudad de Mexico","Guadalajara","Monterrey","Puebla","Queretaro","Merida","Leon","Tijuana"]',
  '["Tile & Ceramic Installer","Hardwood / Engineered Wood Flooring Installer","Vinyl / SPC / LVP Flooring Installer","Countertop Fabricator & Installer","Microcement Applicator (Floors & Walls)","Carpet Installer","Epoxy Floor Coating Specialist","Concrete Polishing & Grinding","Stone Restoration & Polishing","Glass, Glazing & Mirror Installer","Backsplash & Tile Installer"]',
  '["Painter (Interior & Exterior)","Fireplace & Chimney Installer","Wallpaper Installer","HVAC Installer"]',
  '{}', '{}',
  '["{subcategory_local} {city} Mexico empresa","{subcategory_local} {city} contratista","{subcategory_local} {city} instalador"]',
  10, 3,
  '{"max_per_query":5,"confidence_threshold":0.65,"tavily_topic":"general"}',
  false,  -- not active yet — enable when ready to run
  false,  -- no migration needed
  true,   -- first_run gate enabled
  false, false
)
ON CONFLICT (market_id) DO NOTHING;

-- Seed Portugal (greenfield)
INSERT INTO pipeline_config (
  market_id, display_name, country, locale,
  cities, tier_a_subcategories, tier_b_subcategories,
  role_map, subcategory_local_map, search_templates,
  batch_size, min_yield_threshold, research,
  active, migration_locked, first_run,
  gate_after_research, gate_before_sync
) VALUES (
  'pt-renovation',
  'Portugal Renovation Contractors',
  'PT', 'pt-PT',
  '["Lisboa","Porto","Braga","Coimbra","Setubal","Faro"]',
  '["Tile & Ceramic Installer","Hardwood / Engineered Wood Flooring Installer","Vinyl / SPC / LVP Flooring Installer","Countertop Fabricator & Installer","Microcement Applicator (Floors & Walls)","Carpet Installer","Epoxy Floor Coating Specialist","Concrete Polishing & Grinding","Stone Restoration & Polishing","Glass, Glazing & Mirror Installer","Backsplash & Tile Installer"]',
  '["Painter (Interior & Exterior)","Fireplace & Chimney Installer","Wallpaper Installer","HVAC Installer"]',
  '{}', '{}',
  '["{subcategory_local} {city} Portugal empresa","{subcategory_local} {city} instalador","{subcategory_local} {city} fornecedor"]',
  10, 3,
  '{"max_per_query":5,"confidence_threshold":0.65,"tavily_topic":"general"}',
  false, false, true, false, false
)
ON CONFLICT (market_id) DO NOTHING;

-- Seed Spain (greenfield)
INSERT INTO pipeline_config (
  market_id, display_name, country, locale,
  cities, tier_a_subcategories, tier_b_subcategories,
  role_map, subcategory_local_map, search_templates,
  batch_size, min_yield_threshold, research,
  active, migration_locked, first_run,
  gate_after_research, gate_before_sync
) VALUES (
  'es-renovation',
  'Spain Renovation Contractors',
  'ES', 'es-ES',
  '["Madrid","Barcelona","Valencia","Sevilla","Zaragoza","Malaga","Bilbao"]',
  '["Tile & Ceramic Installer","Hardwood / Engineered Wood Flooring Installer","Vinyl / SPC / LVP Flooring Installer","Countertop Fabricator & Installer","Microcement Applicator (Floors & Walls)","Carpet Installer","Epoxy Floor Coating Specialist","Concrete Polishing & Grinding","Stone Restoration & Polishing","Glass, Glazing & Mirror Installer","Backsplash & Tile Installer"]',
  '["Painter (Interior & Exterior)","Fireplace & Chimney Installer","Wallpaper Installer","HVAC Installer"]',
  '{}', '{}',
  '["{subcategory_local} {city} Espana empresa","{subcategory_local} {city} instalador","{subcategory_local} {city} contratista"]',
  10, 3,
  '{"max_per_query":5,"confidence_threshold":0.65,"tavily_topic":"general"}',
  false, false, true, false, false
)
ON CONFLICT (market_id) DO NOTHING;
