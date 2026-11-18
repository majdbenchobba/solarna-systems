# Supabase setup

Apply `migrations/202609200001_solarna_projects.sql` to the Solarna Supabase
project before deploying version 0.5.0.

The migration creates:

- private per-user calculation projects;
- daily or monthly actual-production records;
- row-level security policies restricted to the signed-in user.

The web and mobile applications use only the Supabase publishable key. Do not add
the service-role key to the repository or client configuration.
