"""Run WorkoutPlan against the local PostgreSQL test copy."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    sys.path.insert(0, str(ROOT / 'data' / 'pg-python'))
    os.environ['DATABASE_URL'] = (
        'host=127.0.0.1 port=15432 dbname=workoutplan_test user=workoutplan_test connect_timeout=5'
    )
    os.environ['PGPASSWORD'] = (ROOT / 'data' / 'postgres-test-password.txt').read_text(encoding='ascii').strip()
    import server
    server.init()
    port = 18744
    with server.ThreadingHTTPServer(('127.0.0.1', port), server.Handler) as httpd:
        print(f'WorkoutPlan PostgreSQL test: http://127.0.0.1:{port}', flush=True)
        httpd.serve_forever()


if __name__ == '__main__':
    main()
