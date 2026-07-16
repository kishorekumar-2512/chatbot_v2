"""Data source abstraction layer for database connections.

Supports local PostgreSQL (PgAdmin) and cloud PostgreSQL (AWS RDS, etc.).
Switch between sources by setting DATA_SOURCE_TYPE and DATABASE_URL in .env.
"""
import os
from abc import ABC, abstractmethod
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv

load_dotenv()


class DataSource(ABC):
    """Abstract data source interface."""

    @abstractmethod
    def get_connection(self):
        pass

    @abstractmethod
    def execute_query(self, sql: str) -> list:
        pass

    @abstractmethod
    def health_check(self) -> dict:
        pass

    @abstractmethod
    def close(self):
        pass


class PostgresDataSource(DataSource):
    """PostgreSQL data source — works with both local PgAdmin and cloud (AWS RDS, etc.)."""

    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL')
        self.ssl_mode = os.getenv('DB_SSL_MODE', 'prefer')
        self.pool_size = int(os.getenv('DB_POOL_SIZE', '10'))

        # Connection pool
        connect_kwargs = {}
        if self.ssl_mode == 'require':
            connect_kwargs['sslmode'] = 'require'

        self._pool = pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=self.pool_size,
            dsn=self.database_url,
            **connect_kwargs
        )

    def get_connection(self):
        return self._pool.getconn()

    def return_connection(self, conn):
        self._pool.putconn(conn)

    def execute_query(self, sql: str) -> list:
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                columns = [desc[0] for desc in cur.description]
                rows = [dict(zip(columns, row)) for row in cur.fetchall()]
            conn.commit()
            return rows
        except Exception:
            conn.rollback()
            raise
        finally:
            self.return_connection(conn)

    def health_check(self) -> dict:
        try:
            self.execute_query('SELECT 1 AS ok')
            source_type = 'cloud' if self.ssl_mode == 'require' else 'local'
            return {
                'status': 'healthy',
                'source_type': source_type,
                'pool_size': self.pool_size,
            }
        except Exception as e:
            return {'status': 'unhealthy', 'error': str(e)}

    def close(self):
        self._pool.closeall()


def get_data_source() -> DataSource:
    """Factory function — returns the configured data source."""
    return PostgresDataSource()
