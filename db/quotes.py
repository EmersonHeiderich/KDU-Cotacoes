# db/quotes.py
import logging
from db.connection import get_db_connection
from decimal import Decimal

# Configure logger (assuming configured globally in app.py)
logger = logging.getLogger(__name__)

def get_next_protocolo():
    """Retrieves the next available protocol number."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Use sequence or MAX + 1. Sequence is generally safer for concurrency.
                # Assuming MAX+1 for now based on original code.
                # Add error handling for potential non-integer values if column allows.
                cur.execute("SELECT MAX(protocolo) AS max_protocolo FROM quotes;")
                result = cur.fetchone()
                last_protocolo = result['max_protocolo'] if result and result['max_protocolo'] is not None else 0
                next_protocolo = int(last_protocolo) + 1 # Ensure integer conversion
                logger.info(f"Last protocol: {last_protocolo}. Next protocol: {next_protocolo}")
                return next_protocolo
    except Exception as e:
        logger.error(f"Error getting next protocol: {str(e)}", exc_info=True)
        raise

def inserir_quote(quote_data):
    """Inserts a new quote record into the quotes table and returns the generated quote_id."""
    required_fields = ['protocolo', 'comp_cnpj', 'cli_cnpj', 'invoice_value', 
                       'total_weight', 'total_packages', 'volume_total']
    if not all(field in quote_data and quote_data[field] is not None for field in required_fields):
        logger.error(f"Missing required fields for inserting quote: {quote_data}")
        raise ValueError("Dados insuficientes para inserir cotação.")

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Get client_id using cli_cnpj
                cur.execute("SELECT client_id FROM clients WHERE cnpj = %s;", (quote_data['cli_cnpj'],))
                client = cur.fetchone()
                if not client:
                    logger.error(f"Client with CNPJ {quote_data['cli_cnpj']} not found.")
                    raise LookupError(f"Cliente com CNPJ {quote_data['cli_cnpj']} não encontrado.")
                client_id = client['client_id']

                # Get origin_company_id using comp_cnpj
                cur.execute("SELECT company_id FROM companies WHERE cnpj = %s;", (quote_data['comp_cnpj'],))
                company = cur.fetchone()
                if not company:
                    logger.error(f"Company with CNPJ {quote_data['comp_cnpj']} not found.")
                    raise LookupError(f"Empresa de origem com CNPJ {quote_data['comp_cnpj']} não encontrada.")
                company_id = company['company_id']

                logger.info(f"Inserting quote with Protocol: {quote_data['protocolo']} for client {client_id}, company {company_id}")

                # Insert quote record
                insert_query = """
                    INSERT INTO quotes (
                        protocolo, origin_company_id, client_id, invoice_value,
                        total_weight, total_packages, total_volume, quote_date 
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                    RETURNING quote_id;
                """
                cur.execute(insert_query, (
                    quote_data['protocolo'],
                    company_id,
                    client_id,
                    Decimal(quote_data['invoice_value']), # Ensure Decimal for precision
                    Decimal(quote_data['total_weight']),
                    int(quote_data['total_packages']),
                    Decimal(quote_data['volume_total'])
                ))
                quote_id = cur.fetchone()['quote_id']
                conn.commit()
                logger.info(f"Quote inserted successfully. ID: {quote_id}, Protocol: {quote_data['protocolo']}")
                return quote_id
    except (LookupError, ValueError) as ve: # Catch specific known errors
         logger.error(f"Validation or lookup error inserting quote: {str(ve)}")
         raise # Re-raise specific errors
    except Exception as e:
        logger.error(f"Error inserting quote (Protocol: {quote_data.get('protocolo')}): {str(e)}", exc_info=True)
        # Consider rolling back if necessary
        raise

def _decimal_to_float_or_int(obj):
    """
    Recursively convert Decimal objects to float or int (if no fractional part).
    Handles lists and dicts.
    """
    if isinstance(obj, list):
        return [_decimal_to_float_or_int(item) for item in obj]
    elif isinstance(obj, dict):
        return {k: _decimal_to_float_or_int(v) for k, v in obj.items()}
    elif isinstance(obj, Decimal):
        # Convert to int if the decimal has no fractional part, otherwise float
        return int(obj) if obj % 1 == 0 else float(obj)
    else:
        return obj

def get_last_quotations(limit=15):
    """Retrieves the most recent quotations."""
    try:
        logger.info(f"Retrieving last {limit} quotations.")
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        q.quote_id, q.protocolo, c.code, c.name, c.cnpj,
                        q.invoice_value, q.total_packages, q.total_volume, q.quote_date
                    FROM quotes q
                    JOIN clients c ON q.client_id = c.client_id
                    ORDER BY q.quote_date DESC
                    LIMIT %s;
                """, (limit,))
                results = cur.fetchall()
                logger.info(f"Retrieved {len(results)} recent quotations.")
                # Convert Decimal types for JSON serialization/template rendering
                return _decimal_to_float_or_int(results)
    except Exception as e:
        logger.error(f"Error retrieving last quotations: {str(e)}", exc_info=True)
        raise

def filter_quotations(filters):
    """
    Filters quotations based on provided criteria.
    filters: dict with potential keys 'code', 'cnpj', 'name', 'date'.
    """
    try:
        logger.info(f"Filtering quotations with criteria: {filters}")
        base_query = """
            SELECT 
                q.quote_id, q.protocolo, c.code, c.name, c.cnpj,
                q.invoice_value, q.total_packages, q.total_volume, q.quote_date
            FROM quotes q
            JOIN clients c ON q.client_id = c.client_id
            WHERE 1=1
        """
        params = {}
        
        if filters.get('code'):
            base_query += " AND c.code = %(code)s"
            params['code'] = filters['code']
        
        if filters.get('cnpj'):
            # Normalize CNPJ if needed (e.g., remove punctuation) before query
            cnpj_clean = ''.join(filter(str.isdigit, filters['cnpj']))
            if cnpj_clean:
                 base_query += " AND c.cnpj = %(cnpj)s" # Assuming DB stores CNPJ with punctuation
                 params['cnpj'] = filters['cnpj'] # Use original format if DB expects it, else use cnpj_clean
                 # Check DB format if issues arise
        
        if filters.get('name'):
            base_query += " AND c.name ILIKE %(name)s"
            params['name'] = f"%{filters['name']}%"
        
        if filters.get('date'):
            # Ensure date is in 'YYYY-MM-DD' format for comparison
            try:
                # Basic validation, can be enhanced
                validated_date = filters['date'] # Assume YYYY-MM-DD for now
                base_query += " AND DATE(q.quote_date) = %(date)s"
                params['date'] = validated_date
            except ValueError:
                 logger.warning(f"Invalid date format received for filtering: {filters['date']}")
                 # Optionally ignore the date filter or return an error

        base_query += " ORDER BY q.quote_date DESC LIMIT 100;" # Limit results for performance
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(base_query, params)
                results = cur.fetchall()
                logger.info(f"Found {len(results)} quotations matching filters.")
                return _decimal_to_float_or_int(results)
    except Exception as e:
        logger.error(f"Error filtering quotations: {str(e)}", exc_info=True)
        raise

def get_quote_details(quote_id):
    """Retrieves comprehensive details for a specific quote ID."""
    try:
        logger.info(f"Retrieving details for quote ID: {quote_id}")
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Get main quote and client data
                cur.execute("""
                    SELECT 
                        q.quote_id, q.protocolo, q.invoice_value, q.total_weight,
                        q.total_packages, q.total_volume, q.quote_date,
                        c.code, c.name, c.cnpj, c.city_name, c.state_abbreviation,
                        c.address, c.address_number, c.neighborhood, c.cep, c.ibge_city_code
                    FROM quotes q
                    JOIN clients c ON q.client_id = c.client_id
                    WHERE q.quote_id = %s;
                """, (quote_id,))
                quote = cur.fetchone()
                
                if not quote:
                    logger.warning(f"No quote found with ID {quote_id}.")
                    return None
                
                # Get package data
                cur.execute("""
                    SELECT qp.amount_packages, qp.weight, qp.length, qp.height, qp.width
                    FROM quote_packages qp
                    WHERE qp.quote_id = %s;
                """, (quote_id,))
                packages_raw = cur.fetchall()
                
                # Get carrier responses, joining with carriers table for name
                cur.execute("""
                    SELECT 
                        qr.response_id, qr.carrier_id, cr.trade_name AS carrier_trade_name, 
                        qr.modal, qr.shipping_value, qr.deadline_days, qr.quote_carrier, qr.message
                    FROM quote_responses qr
                    JOIN carriers cr ON qr.carrier_id = cr.carrier_id
                    WHERE qr.quote_id = %s
                    ORDER BY 
                        CASE WHEN qr.shipping_value IS NULL THEN 1 ELSE 0 END, -- Sort NULLs last
                        qr.shipping_value ASC; -- Then sort by value ascending
                """, (quote_id,))
                responses_raw = cur.fetchall()
                
                # Process and structure the data
                quote_details = _decimal_to_float_or_int(quote) # Convert Decimals in main quote data
                
                # Process packages
                packages = []
                for pkg_raw in packages_raw:
                    pkg = _decimal_to_float_or_int(pkg_raw)
                    try:
                        # Calculate volume per unit for display (cm -> m)
                        volume_unitario = (pkg['length'] / 100) * (pkg['height'] / 100) * (pkg['width'] / 100)
                        pkg['volume_unitario'] = round(volume_unitario, 5) # Add calculated volume
                    except (TypeError, KeyError):
                         pkg['volume_unitario'] = 0 # Handle potential missing dimensions
                         logger.warning(f"Could not calculate volume for package in quote {quote_id}: {pkg_raw}")
                    packages.append(pkg)

                # Process responses and calculate percentages
                responses = []
                valid_shipping_values = [float(resp['shipping_value']) for resp in responses_raw if resp['shipping_value'] is not None and resp['shipping_value'] > 0]
                # Calculate total shipping value for percentage calculation (sum of valid, non-zero fretes)
                # total_shipping = sum(valid_shipping_values) if valid_shipping_values else 1.0 # Avoid division by zero

                # --- Alternative Percentage Logic: % relative to the quote's invoice value ---
                invoice_value = quote_details.get('invoice_value', 0)

                for resp_raw in responses_raw:
                    resp = _decimal_to_float_or_int(resp_raw)
                    shipping_value = resp.get('shipping_value')
                    
                    # Calculate percentage relative to invoice value
                    frete_percent = 0
                    if shipping_value is not None and shipping_value > 0 and invoice_value > 0:
                         try:
                             frete_percent = (shipping_value / invoice_value) * 100
                         except ZeroDivisionError:
                              frete_percent = 0

                    # Calculate percentage relative to total frete (original logic)
                    # frete_percent = (shipping_value / total_shipping * 100) if shipping_value is not None and shipping_value > 0 else 0
                    
                    resp['frete_percent'] = round(frete_percent, 2) # Add calculated percentage
                    responses.append(resp)

                # Structure the final output
                result = {
                    "quote": quote_details,
                    "client": { # Extract client details for clarity in template (optional)
                        "code": quote_details.pop("code"),
                        "name": quote_details.pop("name"),
                        "cnpj": quote_details.pop("cnpj"),
                        "city_name": quote_details.pop("city_name"),
                        "state_abbreviation": quote_details.pop("state_abbreviation"),
                        "address": quote_details.pop("address"),
                        "address_number": quote_details.pop("address_number"),
                        "neighborhood": quote_details.pop("neighborhood"),
                        "cep": quote_details.pop("cep"),
                        "ibge_city_code": quote_details.pop("ibge_city_code")
                    },
                    "packages": packages,
                    "responses": responses
                }
                
                logger.info(f"Successfully retrieved details for quote ID {quote_id}.")
                return result

    except Exception as e:
        logger.error(f"Error getting details for quote ID {quote_id}: {str(e)}", exc_info=True)
        raise