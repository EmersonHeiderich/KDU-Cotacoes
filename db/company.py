# db/company.py
import logging
from db.connection import get_db_connection

# Configure logger (assuming configured globally in app.py)
logger = logging.getLogger(__name__)

def get_company_by_code(code):
    """
    Fetches company information from the database using the provided code.
    """
    if not code:
        logger.warning("Attempted to fetch company with no code.")
        return None
        
    try:
        logger.info(f"Fetching company information for code {code}...")
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                query_sql = """
                    SELECT 
                        company_id, code, name, cnpj, number_state_registration, 
                        city_name, state_abbreviation, cep, address, neighborhood, 
                        address_number, ibge_city_code
                    FROM companies
                    WHERE code = %s;
                """
                cur.execute(query_sql, (str(code),)) # Ensure code is treated as string if needed
                company_data = cur.fetchone()

                if company_data:
                    logger.info(f"Company found: {company_data['company_id']} for code {code}")
                    # No need to manually create dict, RealDictCursor does it
                    return company_data 
                else:
                    logger.error(f"No company found with code {code}.")
                    return None
                    
    except Exception as e:
        logger.error(f"Error fetching company information for code {code}: {str(e)}", exc_info=True)
        raise # Re-raise exception