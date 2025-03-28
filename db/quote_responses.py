# db/quote_responses.py
import logging
from db.connection import get_db_connection
from decimal import Decimal # Import Decimal

# Configure logger (assuming configured globally in app.py)
logger = logging.getLogger(__name__)

def get_carrier_id(carrier_identifier):
    """Gets the carrier_id by its short_name (identifier)."""
    if not carrier_identifier:
        logger.warning("Attempted to get carrier ID with no identifier.")
        return None

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT carrier_id FROM carriers WHERE short_name = %s;", (carrier_identifier,))
                carrier = cur.fetchone()
                if carrier:
                    logger.debug(f"Carrier ID {carrier['carrier_id']} found for identifier '{carrier_identifier}'.")
                    return carrier['carrier_id']
                else:
                    logger.error(f"Carrier with short_name '{carrier_identifier}' not found in database.")
                    return None
    except Exception as e:
        logger.error(f"Error getting carrier_id for '{carrier_identifier}': {str(e)}", exc_info=True)
        raise

def inserir_quote_response(quote_id, response_data):
    """Inserts a carrier's quote response into the quote_responses table."""
    if not quote_id or not response_data or 'Transportadora' not in response_data:
        logger.error(f"Invalid input for inserting quote response: quote_id={quote_id}, response_data={response_data}")
        return # Or raise error

    carrier_identifier = response_data['Transportadora'] # This should be the internal code (e.g., 'BTU')
    
    try:
        carrier_id = get_carrier_id(carrier_identifier)
        if not carrier_id:
            logger.error(f"Carrier '{carrier_identifier}' not found. Response for quote ID {quote_id} will not be inserted.")
            return # Skip insertion if carrier doesn't exist

        modal = response_data.get('modal', 'Rodoviário') # Default modal
        
        # Handle numeric fields, allowing NULL
        shipping_value = response_data.get('frete')
        if shipping_value == '-' or shipping_value == '': shipping_value = None
        # Convert to Decimal if necessary, handle potential errors
        try:
            shipping_value_decimal = Decimal(shipping_value) if shipping_value is not None else None
        except (TypeError, ValueError, InvalidOperation):
             logger.warning(f"Invalid shipping_value '{shipping_value}' for carrier {carrier_identifier}, setting to NULL.")
             shipping_value_decimal = None
             
        deadline_days = response_data.get('prazo')
        if deadline_days == '-' or deadline_days == '': deadline_days = None
        # Convert to Integer if necessary, handle potential errors
        try:
            deadline_days_int = int(deadline_days) if deadline_days is not None else None
        except (TypeError, ValueError):
             logger.warning(f"Invalid deadline_days '{deadline_days}' for carrier {carrier_identifier}, setting to NULL.")
             deadline_days_int = None
        
        quote_carrier = response_data.get('cotacao') # Carrier's own quote reference/ID
        message = response_data.get('message') # Error or info message

        logger.info(f"Inserting response for quote ID: {quote_id}, Carrier: {carrier_identifier} (ID: {carrier_id})")
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO quote_responses (
                        quote_id, carrier_id, modal, shipping_value, deadline_days,
                        quote_carrier, message, response_time -- Assuming response_time is timestamp default NOW()
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW()); 
                """, (
                    quote_id,
                    carrier_id,
                    modal,
                    shipping_value_decimal, # Use Decimal or None
                    deadline_days_int,      # Use Integer or None
                    str(quote_carrier) if quote_carrier is not None else None, # Allow NULL
                    message
                ))
                conn.commit()
                logger.info(f"Response from carrier '{carrier_identifier}' inserted successfully for quote ID: {quote_id}")

    except Exception as e:
        logger.error(f"Error inserting quote response for quote ID {quote_id}, carrier '{carrier_identifier}': {str(e)}", exc_info=True)
        # Consider rolling back if part of a larger transaction
        raise