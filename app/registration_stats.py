"""Read-only account registration trends in Moscow calendar periods."""
PERIODS = {'day':('day','29 days','1 day'), 'week':('week','11 weeks','1 week'), 'month':('month','11 months','1 month')}

def account_registration_stats(connection, period, role='user'):
    if role not in ('user', 'coach'):
        raise ValueError('Неверная роль')
    if not isinstance(period, str) or period not in PERIODS:
        raise ValueError('Выберите дни, недели или месяцы')
    unit, lookback, step = PERIODS[period]
    rows = connection.execute("""
        WITH periods AS (
            SELECT generate_series(
                date_trunc(?, CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Moscow') - ?::interval,
                date_trunc(?, CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Moscow'),
                ?::interval
            ) AS starts_at
        )
        SELECT to_char(p.starts_at, 'YYYY-MM-DD') AS starts_on,
               to_char((p.starts_at + ?::interval - interval '1 day')::date, 'YYYY-MM-DD') AS ends_on,
               count(u.id) FILTER (WHERE r.user_id IS NOT NULL) AS with_promo,
               count(u.id) FILTER (WHERE r.user_id IS NULL) AS without_promo
        FROM periods p
        LEFT JOIN users u ON u.role=?
            AND u.registered_at >= (p.starts_at AT TIME ZONE 'Europe/Moscow')
            AND u.registered_at < ((p.starts_at + ?::interval) AT TIME ZONE 'Europe/Moscow')
            AND u.registered_at <= CURRENT_TIMESTAMP
        LEFT JOIN promo_redemptions r ON r.user_id=u.id
        GROUP BY p.starts_at ORDER BY p.starts_at
    """, (unit,lookback,unit,step,step,role,step))
    buckets = [dict(row) for row in rows]
    return {'period':period, 'buckets':buckets, 'with_promo':sum(row['with_promo'] for row in buckets),
            'without_promo':sum(row['without_promo'] for row in buckets), 'timezone':'Europe/Moscow'}

def client_registration_stats(connection, period):
    return account_registration_stats(connection, period, 'user')
