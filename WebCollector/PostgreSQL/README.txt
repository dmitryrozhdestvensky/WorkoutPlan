FITNESS PostgreSQL schema, version 1

Target database: workoutplan
Target schema: fitness

1. Back up workoutplan using pg_dump -Fc before applying.
2. Review 001_fitness_schema.sql.
3. Run with psql -v ON_ERROR_STOP=1 -f 001_fitness_schema.sql.
4. Verify with psql -c "SELECT table_name FROM information_schema.tables WHERE table_schema='fitness' ORDER BY table_name;".

This migration does not drop or alter existing public tables.
It adds a foreign key from fitness.trainer_user_links to public.users(id).
It does NOT import data and does NOT change users or their auth credentials.
Always verify existing schema objects before applying migration to an existing fitness schema.
