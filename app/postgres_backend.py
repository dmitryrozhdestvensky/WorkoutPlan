from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import psycopg


class Row(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)


def row_factory(cursor):
    names = [column.name for column in cursor.description or ()]

    def make(values):
        return Row(zip(names, (
            value.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            if isinstance(value, datetime) else value for value in values
        )))

    return make


class Connection(psycopg.Connection):
    def execute(self, query, params=None, **kwargs):
        if query == 'BEGIN IMMEDIATE':
            query = 'LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE'
        query = query.replace("datetime('now',?)", "CURRENT_TIMESTAMP + CAST(? AS interval)")
        query = query.replace('id IS NOT ?', 'id IS DISTINCT FROM ?')
        return super().execute(query.replace('?', '%s'), params, **kwargs)


@contextmanager
def connect(url):
    with Connection.connect(url, row_factory=row_factory) as connection:
        yield connection


def initialize(connection):
    schema = Path(__file__).with_name('postgres-account-events.sql')
    connection.execute(schema.read_text(encoding='utf-8'))
