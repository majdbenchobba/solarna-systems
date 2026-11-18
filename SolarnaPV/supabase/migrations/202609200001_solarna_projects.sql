create extension if not exists pgcrypto;

create table if not exists public.solarna_projects (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 120),
  site_name text not null check (char_length(site_name) between 1 and 120),
  latitude double precision not null check (latitude between -90 and 90),
  longitude double precision not null check (longitude between -180 and 180),
  system jsonb not null default '{}'::jsonb,
  report jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.solarna_production_records (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid not null references public.solarna_projects(id) on delete cascade,
  period_start date not null,
  period_type text not null check (period_type in ('daily', 'monthly')),
  actual_kwh numeric(14, 4) not null check (actual_kwh >= 0),
  source text not null default 'csv' check (char_length(source) between 1 and 40),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (project_id, period_type, period_start)
);

create index if not exists solarna_projects_user_updated_idx
  on public.solarna_projects (user_id, updated_at desc);

create index if not exists solarna_production_user_project_idx
  on public.solarna_production_records (user_id, project_id, period_start);

create or replace function public.set_solarna_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists solarna_projects_updated_at on public.solarna_projects;
create trigger solarna_projects_updated_at
before update on public.solarna_projects
for each row execute function public.set_solarna_updated_at();

drop trigger if exists solarna_production_updated_at
  on public.solarna_production_records;
create trigger solarna_production_updated_at
before update on public.solarna_production_records
for each row execute function public.set_solarna_updated_at();

alter table public.solarna_projects enable row level security;
alter table public.solarna_production_records enable row level security;

drop policy if exists "Users manage their Solarna projects"
  on public.solarna_projects;
create policy "Users manage their Solarna projects"
on public.solarna_projects
for all
to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

drop policy if exists "Users manage their Solarna production records"
  on public.solarna_production_records;
create policy "Users manage their Solarna production records"
on public.solarna_production_records
for all
to authenticated
using (
  (select auth.uid()) = user_id
  and exists (
    select 1
    from public.solarna_projects
    where solarna_projects.id = solarna_production_records.project_id
      and solarna_projects.user_id = (select auth.uid())
  )
)
with check (
  (select auth.uid()) = user_id
  and exists (
    select 1
    from public.solarna_projects
    where solarna_projects.id = solarna_production_records.project_id
      and solarna_projects.user_id = (select auth.uid())
  )
);

revoke all on public.solarna_projects from anon;
revoke all on public.solarna_production_records from anon;
grant select, insert, update, delete on public.solarna_projects to authenticated;
grant select, insert, update, delete
  on public.solarna_production_records to authenticated;
