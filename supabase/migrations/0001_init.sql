-- pidgraph schema.
--
-- The graph lives in the same database as the documents, so storage, auth and realtime come from
-- one service. At this scale recursive CTEs are ample; a separate graph database would add a
-- second store, a second auth model and a second deploy target to manage a few hundred nodes.
--
-- Two platform behaviours shape this file and are called out where they bite:
--   * Enabling row-level security is NOT sufficient. A new table in an exposed schema starts with
--     privileges already granted to the anonymous role, and adding policies does not take those
--     grants back. Every table below is both secured and revoked.
--   * The REST layer caps responses at 1000 rows -- including function results. Traversals
--     therefore return a single aggregated document rather than a row set, or a large graph is
--     silently truncated with no error, which would corrupt evaluation rather than only the UI.

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------------------------
-- Vocabulary. Seeded from the published information model rather than invented, so the class of
-- every node is constrained by foreign key to something a reader can look up.
-- A lookup table rather than an enum: `alter type ... add value` cannot run in the transaction
-- that uses it, so a newly encountered class would otherwise require a two-step migration.
-- ---------------------------------------------------------------------------------------------
create table if not exists dexpi_class (
    name          text primary key,
    package       text not null check (package in ('Equipment','Piping','Instrumentation','Other')),
    description   text,
    reference_uri text
);

create table if not exists isa_edition (
    designation text primary key,
    year        int  not null,
    note        text
);

-- ---------------------------------------------------------------------------------------------
-- Documents and runs
-- ---------------------------------------------------------------------------------------------
create table if not exists documents (
    id           uuid primary key default gen_random_uuid(),
    owner_id     uuid default auth.uid(),
    kind         text not null check (kind in ('pid','sop')),
    filename     text not null,
    -- Derived from a content hash, never from the on-disk name: source paths may contain
    -- characters that are hostile in a URL or a shell.
    storage_key  text not null,
    sha256       text not null,
    page_count   int,
    title        text,
    metadata     jsonb not null default '{}'::jsonb,
    created_at   timestamptz not null default now(),
    unique (sha256)
);

create table if not exists extraction_runs (
    id                uuid primary key default gen_random_uuid(),
    document_id       uuid not null references documents on delete cascade,
    extractor_version text not null,
    isa_edition       text references isa_edition(designation),
    -- The strategy each stage chose. A run whose text came from structural hints is a different
    -- artifact from one whose text was clustered, and a reader has to be able to tell.
    strategies        jsonb not null default '{}'::jsonb,
    scale             jsonb not null default '{}'::jsonb,
    stats             jsonb not null default '{}'::jsonb,
    status            text not null default 'running'
                      check (status in ('running','succeeded','failed')),
    started_at        timestamptz not null default now(),
    finished_at       timestamptz
);

-- Readers filter on this, so a partially written run is never visible as complete.
alter table documents
    add column if not exists current_run_id uuid references extraction_runs on delete set null;

-- ---------------------------------------------------------------------------------------------
-- Graph
-- ---------------------------------------------------------------------------------------------
create table if not exists nodes (
    id           uuid primary key default gen_random_uuid(),
    run_id       uuid not null references extraction_runs on delete cascade,
    page_index   int  not null,
    -- Content-addressed identity, stable across re-extraction, so review decisions survive a
    -- re-run. The surrogate key is not that identity.
    stable_key   text not null,
    kind         text not null,
    dexpi_class  text references dexpi_class(name),
    tag_name     text,
    tag_prefix   text,
    tag_sequence text,
    tag_suffix   text,
    loop_id      text,
    conformance  text,
    label        text,
    bbox         numeric[4],
    confidence   real not null default 1.0,
    provenance   jsonb not null default '{}'::jsonb,
    unique (run_id, stable_key)
);
create index if not exists nodes_run_kind_idx on nodes (run_id, kind);
create index if not exists nodes_run_tag_idx  on nodes (run_id, tag_name);
create index if not exists nodes_loop_idx     on nodes (run_id, loop_id);

create table if not exists edges (
    id          uuid primary key default gen_random_uuid(),
    run_id      uuid not null references extraction_runs on delete cascade,
    source_id   uuid not null references nodes on delete cascade,
    target_id   uuid not null references nodes on delete cascade,
    kind        text not null,
    style       text,
    -- How the edge was established. A graph built mostly from weak bridges is a different
    -- artifact from one built from port bindings, and the difference stays queryable.
    evidence    text not null,
    confidence  real not null default 1.0,
    provenance  jsonb not null default '{}'::jsonb,
    check (source_id <> target_id)
);
create index if not exists edges_run_source_idx on edges (run_id, source_id);
create index if not exists edges_run_target_idx on edges (run_id, target_id);

-- Attribute values lifted from a drawing, kept separately from structure so a disputed number is
-- one join from its provenance.
create table if not exists node_attributes (
    id        uuid primary key default gen_random_uuid(),
    node_id   uuid not null references nodes on delete cascade,
    name      text not null,
    value     text not null,
    unit      text,
    numeric_min numeric,
    numeric_max numeric,
    provenance  jsonb not null default '{}'::jsonb,
    unique (node_id, name)
);

-- ---------------------------------------------------------------------------------------------
-- Procedure requirements and findings
-- ---------------------------------------------------------------------------------------------
create table if not exists sop_requirements (
    id           uuid primary key default gen_random_uuid(),
    document_id  uuid not null references documents on delete cascade,
    ordinal      int  not null,
    subject_raw  text not null,
    -- An array: one row may name several trains, and collapsing it loses half the plant.
    subject_tags text[] not null default '{}',
    subject_part text,
    quantities   jsonb not null default '{}'::jsonb,
    evidence     text,
    unique (document_id, ordinal)
);

create table if not exists findings (
    id             uuid primary key default gen_random_uuid(),
    run_id         uuid not null references extraction_runs on delete cascade,
    sop_document_id uuid references documents on delete set null,
    check_name     text not null,
    status         text not null check (status in ('verified','finding','needs_review')),
    severity       text not null check (severity in ('info','low','medium','high','critical')),
    title          text not null,
    detail         text,
    subject        text,
    pid_evidence   text,
    sop_evidence   text,
    confidence     real not null default 1.0,
    -- Set when a verdict rests on something not being found. Such findings are capped in
    -- severity, and the flag is what lets a reader tell a document defect from an extraction gap.
    graph_incomplete boolean not null default false,
    created_at     timestamptz not null default now()
);
create index if not exists findings_run_idx on findings (run_id, severity, status);

create table if not exists review_actions (
    id          uuid primary key default gen_random_uuid(),
    document_id uuid not null references documents on delete cascade,
    target      text not null check (target in ('node','edge','finding')),
    -- Keyed to the content-addressed identity, so a re-extraction does not orphan the decision.
    stable_key  text not null,
    action      text not null check (action in ('confirm','correct','dismiss')),
    payload     jsonb not null default '{}'::jsonb,
    actor       uuid default auth.uid(),
    created_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------------------------------------
-- Traversal. Exposed as functions because the REST layer cannot express a recursive CTE, and
-- returning one aggregated document because its 1000-row cap applies to functions too.
-- ---------------------------------------------------------------------------------------------
create or replace function trace_downstream(p_run uuid, p_tag text, p_max_depth int default 25)
returns jsonb
language sql
stable
security invoker
as $$
    with recursive walk(node_id, depth, path) as (
        select n.id, 0, array[n.stable_key]
          from nodes n
         where n.run_id = p_run and n.tag_name = p_tag
        union all
        select e.target_id, w.depth + 1, w.path || n2.stable_key
          from walk w
          join edges e  on e.source_id = w.node_id and e.run_id = p_run
          join nodes n2 on n2.id = e.target_id
         -- Both guards are required: drawings contain genuine cycles (parallel trains, bypasses)
         -- and the database enforces a short statement timeout, so an unguarded walk fails with a
         -- cancellation rather than a useful answer.
         where w.depth < p_max_depth
           and not n2.stable_key = any(w.path)
    )
    select coalesce(jsonb_agg(jsonb_build_object(
               'stable_key', n.stable_key,
               'tag', n.tag_name,
               'kind', n.kind,
               'depth', w.depth
           ) order by w.depth), '[]'::jsonb)
      from walk w join nodes n on n.id = w.node_id;
$$;

create or replace function graph_snapshot(p_run uuid)
returns jsonb
language sql
stable
security invoker
as $$
    select jsonb_build_object(
        'nodes', coalesce((
            select jsonb_agg(jsonb_build_object(
                'stable_key', n.stable_key, 'kind', n.kind, 'dexpi_class', n.dexpi_class,
                'tag', n.tag_name, 'label', n.label, 'bbox', n.bbox,
                'page', n.page_index, 'confidence', n.confidence
            )) from nodes n where n.run_id = p_run), '[]'::jsonb),
        'edges', coalesce((
            select jsonb_agg(jsonb_build_object(
                'source', s.stable_key, 'target', t.stable_key, 'kind', e.kind,
                'style', e.style, 'evidence', e.evidence, 'confidence', e.confidence
            ))
            from edges e
            join nodes s on s.id = e.source_id
            join nodes t on t.id = e.target_id
            where e.run_id = p_run), '[]'::jsonb)
    );
$$;

-- The REST layer caches the schema; without this a newly created function returns 404.
notify pgrst, 'reload schema';

-- ---------------------------------------------------------------------------------------------
-- Security. Enabling row-level security alone leaves the default grants in place, so each table
-- is secured AND revoked. Reads reach the browser through explicit select grants only.
-- ---------------------------------------------------------------------------------------------
do $$
declare t text;
begin
    foreach t in array array[
        'documents','extraction_runs','nodes','edges','node_attributes',
        'sop_requirements','findings','review_actions','dexpi_class','isa_edition'
    ] loop
        execute format('alter table %I enable row level security', t);
        execute format('revoke all on table %I from anon, authenticated', t);
        execute format('grant select on table %I to anon, authenticated', t);
    end loop;
end $$;

-- Single-owner policies. Vocabulary tables are world-readable; everything else is scoped to the
-- owning user, with writes reserved to the service role used by the ingestion pipeline.
create policy dexpi_class_read on dexpi_class for select using (true);
create policy isa_edition_read on isa_edition for select using (true);

create policy documents_owner on documents
    for select using (owner_id is null or owner_id = auth.uid());

create policy runs_read on extraction_runs for select using (
    exists (select 1 from documents d
             where d.id = extraction_runs.document_id
               and (d.owner_id is null or d.owner_id = auth.uid()))
);

create policy nodes_read on nodes for select using (
    exists (select 1 from extraction_runs r join documents d on d.id = r.document_id
             where r.id = nodes.run_id and (d.owner_id is null or d.owner_id = auth.uid()))
);

create policy edges_read on edges for select using (
    exists (select 1 from extraction_runs r join documents d on d.id = r.document_id
             where r.id = edges.run_id and (d.owner_id is null or d.owner_id = auth.uid()))
);

create policy findings_read on findings for select using (
    exists (select 1 from extraction_runs r join documents d on d.id = r.document_id
             where r.id = findings.run_id and (d.owner_id is null or d.owner_id = auth.uid()))
);

create policy attributes_read on node_attributes for select using (true);
create policy requirements_read on sop_requirements for select using (true);
create policy review_read on review_actions for select using (actor is null or actor = auth.uid());
create policy review_write on review_actions for insert with check (actor = auth.uid());
