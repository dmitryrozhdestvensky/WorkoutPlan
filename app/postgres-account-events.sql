CREATE OR REPLACE FUNCTION workoutplan_track_account() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        NEW.registered_at := COALESCE(NEW.registered_at, CURRENT_TIMESTAMP);
        IF NEW.role IN ('coach', 'user') AND NEW.is_del = 0 THEN
            INSERT INTO account_count_events(role, delta, occurred_at, user_id)
            VALUES (NEW.role, 1, NEW.registered_at, NEW.id);
        END IF;
    ELSIF NEW.is_del IS DISTINCT FROM OLD.is_del AND NEW.role IN ('coach', 'user') THEN
        INSERT INTO account_count_events(role, delta, user_id)
        VALUES (NEW.role, CASE WHEN NEW.is_del = 1 THEN -1 ELSE 1 END, NEW.id);
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS workoutplan_account_events ON users;
CREATE TRIGGER workoutplan_account_events
BEFORE INSERT OR UPDATE OF is_del ON users
FOR EACH ROW EXECUTE FUNCTION workoutplan_track_account();

CREATE TABLE IF NOT EXISTS exercise_tags (
    exercise_id INTEGER NOT NULL REFERENCES exercises(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (exercise_id, tag_id)
);
CREATE INDEX IF NOT EXISTS exercise_tags_tag_idx ON exercise_tags(tag_id);
UPDATE tag_groups SET name = 'Группа мышц' WHERE name = 'Мышцы';
UPDATE tag_groups SET name = 'Зона тела' WHERE name = 'Часть тела';
UPDATE tag_groups SET name = 'Сложность' WHERE name = 'Сложность техники';
UPDATE tag_groups SET name = 'Особенности' WHERE name = 'Способ выполнения';

ALTER TABLE tags ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;
