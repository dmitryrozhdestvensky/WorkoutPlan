"""Run WorkoutPlan against the local PostgreSQL test copy."""
import os
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--production', action='store_true')
    production = parser.parse_args().production
    database = 'workoutplan' if production else 'workoutplan_test'
    data_dir = Path(os.environ.setdefault('WORKOUTPLAN_DATA_DIR', str(ROOT / 'data')))
    sys.path.insert(0, str(data_dir / 'pg-python'))
    password_file = data_dir / 'postgres-test-password.txt'
    if not os.environ.get('PGPASSWORD') and not os.environ.get('PGPASSFILE') and password_file.is_file():
        os.environ['PGPASSWORD'] = password_file.read_text(encoding='utf-8-sig').strip()
    os.environ['DATABASE_URL'] = (
        f'host=127.0.0.1 port=15432 dbname={database} user=workoutplan_test connect_timeout=5'
    )
    import server
    server.init()
    port = 18743 if production else 18744
    with server.ThreadingHTTPServer(('127.0.0.1', port), server.Handler) as httpd:
        print(f'WorkoutPlan PostgreSQL ({database}): http://127.0.0.1:{port}', flush=True)
        httpd.serve_forever()


if __name__ == '__main__':
    main()
