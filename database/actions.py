from psycopg2 import sql
from database.db import get_connection
from utils.constants import REMINDER_TABLE


def init_db():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("""
                CREATE TABLE IF NOT EXISTS {table} (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    chat_id BIGINT NOT NULL,
                    text TEXT NOT NULL,
                    remind_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    status TEXT DEFAULT 'active'
                );
            """).format(
                table=sql.Identifier(REMINDER_TABLE)
            ))

            # Add status column (safe for existing tables)
            cur.execute(sql.SQL("""
                ALTER TABLE {table}
                ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active'
            """).format(
                table=sql.Identifier(REMINDER_TABLE)
            ))
        conn.commit()
    except Exception as e:
        print("DB init error:", e)
    finally:
        conn.close()


def db_mark_reminder_completed(reminder_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("""
                UPDATE {table}
                SET status = 'completed'
                WHERE id = %s
            """).format(
                table=sql.Identifier(REMINDER_TABLE)
            ), (reminder_id,))
        conn.commit()
    except Exception as e:
        print("Mark completed error:", e)
    finally:
        conn.close()


def db_insert_reminder(user_id, chat_id, text, remind_at):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("""
                INSERT INTO {table} (user_id, chat_id, text, remind_at)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """).format(
                table=sql.Identifier(REMINDER_TABLE)
            ), (user_id, chat_id, text, remind_at))

            reminder_id = cur.fetchone()[0]
        conn.commit()
        return reminder_id
    except Exception as e:
        print("Insert error:", e)
        return None
    finally:
        conn.close()


def db_delete_reminder(reminder_id, user_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("""
                DELETE FROM {table}
                WHERE id = %s AND user_id = %s
            """).format(
                table=sql.Identifier(REMINDER_TABLE)
            ), (reminder_id, user_id))
        conn.commit()
    except Exception as e:
        print("Delete error:", e)
    finally:
        conn.close()


def db_find_reminder_by_id(reminder_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("""
                SELECT id, text, remind_at
                FROM {table}
                WHERE id = %s
                LIMIT 1
            """).format(
                table=sql.Identifier(REMINDER_TABLE)
            ), (reminder_id,))
            return cur.fetchone()
    except Exception as e:
        print("Find error:", e)
        return None
    finally:
        conn.close()


def db_get_user_reminders(user_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("""
                SELECT id, text, remind_at
                FROM {table}
                WHERE user_id = %s AND status = 'active' AND remind_at > NOW()
                ORDER BY remind_at
            """).format(
                table=sql.Identifier(REMINDER_TABLE)
            ), (user_id,))
            return cur.fetchall()
    except Exception as e:
        print("Get reminders error:", e)
        return []
    finally:
        conn.close()


def db_get_status_counts(user_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("""
                SELECT
                    COUNT(*) FILTER (WHERE status = 'active'),
                    COUNT(*) FILTER (WHERE status = 'completed'),
                    COUNT(*)
                FROM {table}
                WHERE user_id = %s
            """).format(
                table=sql.Identifier(REMINDER_TABLE)
            ), (user_id,))
            return cur.fetchone()
    except Exception as e:
        print("Status error:", e)
        return (0, 0, 0)
    finally:
        conn.close()
