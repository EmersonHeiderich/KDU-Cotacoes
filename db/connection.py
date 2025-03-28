# /db/connection.py
import psycopg2
from psycopg2.extras import RealDictCursor
from config import CurrentConfig # Import configuration
import logging

# Configuração do logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    try:
        connection = psycopg2.connect(
            host=CurrentConfig.DB_HOST,
            port=CurrentConfig.DB_PORT,
            database=CurrentConfig.DB_NAME,
            user=CurrentConfig.DB_USER,
            password=CurrentConfig.DB_PASSWORD,
            cursor_factory=RealDictCursor, # Returns results as dictionaries
            options="-c client_encoding=UTF8" # Ensure UTF8 encoding
        )
        logger.debug(f"Database connection established to {CurrentConfig.DB_HOST}:{CurrentConfig.DB_PORT}/{CurrentConfig.DB_NAME}")
        return connection
    except psycopg2.OperationalError as e:
        logger.error(f"Database connection error: {str(e)}")
        # Consider specific handling for connection errors, e.g., retries or circuit breaking
        raise # Re-raise the exception to be handled upstream
    except Exception as e:
        logger.error(f"Unexpected error connecting to database: {str(e)}")
        raise