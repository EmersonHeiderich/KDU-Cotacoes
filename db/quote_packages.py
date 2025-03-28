# db/quote_packages.py
import logging
from db.connection import get_db_connection

# Configure logger (assuming configured globally in app.py)
logger = logging.getLogger(__name__)

def inserir_quote_packages(quote_id, packages):
    """Inserts packages associated with a quote into the quote_packages table."""
    if not quote_id or not packages:
        logger.warning(f"Attempted to insert packages with invalid quote_id ({quote_id}) or no packages.")
        return

    try:
        logger.info(f"Inserting {len(packages)} package types for quote ID: {quote_id}")
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Prepare data for executemany for efficiency
                package_values = [
                    (
                        quote_id,
                        package.get('AmountPackages', 1), # Default to 1 if missing
                        package.get('Weight'),
                        package.get('Length'),
                        package.get('Height'),
                        package.get('Width')
                    )
                    for package in packages
                ]
                
                # Check for missing essential data before inserting
                for val in package_values:
                     if None in val[1:]: # Check if Weight, Length, Height, Width are None
                         logger.error(f"Missing package dimension/weight data for quote_id {quote_id}. Package data: {val}")
                         raise ValueError("Dados dimensionais ou de peso ausentes para um pacote.")

                insert_query = """
                    INSERT INTO quote_packages (
                        quote_id, amount_packages, weight, length, height, width
                    ) VALUES (%s, %s, %s, %s, %s, %s);
                """
                cur.executemany(insert_query, package_values)
                conn.commit()
                logger.info(f"Successfully inserted packages for quote ID: {quote_id}")
    except Exception as e:
        logger.error(f"Error inserting packages for quote ID {quote_id}: {str(e)}", exc_info=True)
        # Consider rolling back if part of a larger transaction context elsewhere
        raise