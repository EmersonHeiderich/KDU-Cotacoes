# /db/clientes.py
import logging
from db.connection import get_db_connection

# Configuração do logger
# logging.basicConfig(level=logging.INFO) # Configured in app.py
logger = logging.getLogger(__name__)

def verificar_cliente_existente(cnpj, code):
    """Checks if a client exists in the database by CNPJ or code."""
    if not cnpj and not code:
        logger.warning("Attempted to check client existence with no CNPJ or code.")
        return None
        
    sql = "SELECT * FROM clients WHERE "
    params = []
    conditions = []
    if cnpj:
        conditions.append("cnpj = %s")
        params.append(cnpj)
    if code:
        conditions.append("code = %s")
        params.append(str(code)) # Ensure code is compared as string if DB field is text

    sql += " OR ".join(conditions) + ";"
    
    try:
        logger.info(f"Verifying client existence for CNPJ {cnpj} or code {code}...")
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                result = cur.fetchone()
                if result:
                    logger.info(f"Client found: {result['client_id']} for CNPJ {cnpj} / code {code}")
                else:
                    logger.info(f"Client not found for CNPJ {cnpj} / code {code}")
                return result
    except Exception as e:
        logger.error(f"Error verifying client existence: {str(e)}", exc_info=True)
        raise

def atualizar_cliente(cliente_dados):
    """Updates an existing client's information in the database."""
    required_fields = ['code', 'name', 'number_state_registration', 'city_name', 
                       'state_abbreviation', 'cep', 'address', 'neighborhood', 
                       'address_number', 'ibge_city_code']
    if not all(field in cliente_dados for field in required_fields):
        logger.error("Missing required fields for updating client.")
        raise ValueError("Dados insuficientes para atualizar cliente.")

    try:
        client_code_str = str(cliente_dados['code']) # Ensure code is string for WHERE clause
        logger.info(f"Updating client with code {client_code_str}...")
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE clients SET
                        name = %(name)s,
                        number_state_registration = %(number_state_registration)s,
                        city_name = %(city_name)s,
                        state_abbreviation = %(state_abbreviation)s,
                        cep = %(cep)s,
                        address = %(address)s,
                        neighborhood = %(neighborhood)s,
                        address_number = %(address_number)s,
                        ibge_city_code = %(ibge_city_code)s,
                        date_update = NOW()
                    WHERE code = %(code_str)s;
                """, {**cliente_dados, 'code_str': client_code_str})
                conn.commit()
                logger.info(f"Client {client_code_str} updated successfully.")
    except Exception as e:
        logger.error(f"Error updating client {client_code_str}: {str(e)}", exc_info=True)
        raise

def inserir_cliente(cliente_dados):
    """Inserts a new client into the database."""
    required_fields = ['code', 'name', 'cnpj', 'number_state_registration', 'city_name', 
                       'state_abbreviation', 'cep', 'address', 'neighborhood', 
                       'address_number', 'ibge_city_code']
    if not all(field in cliente_dados for field in required_fields):
        logger.error("Missing required fields for inserting client.")
        raise ValueError("Dados insuficientes para inserir cliente.")
        
    try:
        client_code = cliente_dados['code']
        logger.info(f"Inserting new client with code {client_code}...")
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO clients (
                        code, name, cnpj, number_state_registration, city_name, 
                        state_abbreviation, cep, address, neighborhood, 
                        address_number, ibge_city_code, date_creation, date_update
                    )
                    VALUES (
                        %(code)s, %(name)s, %(cnpj)s, %(number_state_registration)s, %(city_name)s, 
                        %(state_abbreviation)s, %(cep)s, %(address)s, %(neighborhood)s, 
                        %(address_number)s, %(ibge_city_code)s, NOW(), NOW()
                    );
                """, cliente_dados)
                conn.commit()
                logger.info(f"Client {client_code} inserted successfully.")
    except Exception as e:
        # Handle potential unique constraint violations gracefully
        if "duplicate key value violates unique constraint" in str(e).lower():
             logger.warning(f"Attempted to insert duplicate client (code/cnpj): {client_code}/{cliente_dados.get('cnpj')}. Error: {e}")
             # Decide if re-raising is needed or just log
        else:
            logger.error(f"Error inserting client {client_code}: {str(e)}", exc_info=True)
        raise # Re-raise by default