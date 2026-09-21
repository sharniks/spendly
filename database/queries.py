from database.db import get_db


def get_recent_transactions(user_id, limit=10):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT date, description, category, amount FROM expenses "
            "WHERE user_id = ? ORDER BY date DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_summary_stats(user_id):
    conn = get_db()
    try:
        totals_row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS cnt "
            "FROM expenses WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        top_row = conn.execute(
            "SELECT category, SUM(amount) AS t FROM expenses "
            "WHERE user_id = ? GROUP BY category ORDER BY t DESC LIMIT 1",
            (user_id,),
        ).fetchone()

        top_category = top_row["category"] if top_row is not None else "—"

        return {
            "total_spent": float(totals_row["total"]),
            "transaction_count": int(totals_row["cnt"]),
            "top_category": top_category,
        }
    finally:
        conn.close()


def get_category_breakdown(user_id):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT category, SUM(amount) AS total FROM expenses "
            "WHERE user_id = ? GROUP BY category ORDER BY total DESC",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    grand_total = sum(row["total"] for row in rows)
    if not grand_total:
        return []

    categories = []
    for row in rows:
        percent = round((row["total"] / grand_total) * 100)
        categories.append(
            {
                "name": row["category"],
                "total": row["total"],
                "percent": percent,
            }
        )

    remainder = 100 - sum(cat["percent"] for cat in categories)
    if remainder:
        categories[0]["percent"] += remainder

    return categories
