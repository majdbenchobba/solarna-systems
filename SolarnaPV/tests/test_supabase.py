from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT
    / "supabase"
    / "migrations"
    / "202609200001_solarna_projects.sql"
)


class SupabaseMigrationTests(unittest.TestCase):
    def test_user_project_and_production_tables_are_private(self):
        sql = MIGRATION.read_text(encoding="utf-8").lower()
        self.assertIn("create table if not exists public.solarna_projects", sql)
        self.assertIn(
            "create table if not exists public.solarna_production_records",
            sql,
        )
        self.assertEqual(sql.count("enable row level security"), 2)
        self.assertGreaterEqual(sql.count("auth.uid()"), 4)
        self.assertEqual(sql.count("revoke all on public.solarna_"), 2)
        self.assertNotIn("service_role", sql)


if __name__ == "__main__":
    unittest.main()
