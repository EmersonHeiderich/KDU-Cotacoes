# services/controller/cliente_controller.py
from services.totvs.person import get_legal_entity_data
from db.clientes import verificar_cliente_existente, atualizar_cliente, inserir_cliente
import logging
import re # Import re for data cleaning

# Configure logger (assuming configured globally in app.py)
logger = logging.getLogger(__name__)

class ClienteController:
    def coletar_dados_cliente(self, identifier, invoice_value):
        """
        Collects client data using the provided code or CNPJ identifier,
        interacts with the database (check/insert/update), and returns client data.
        """
        logger.info(f"Collecting client data for identifier: {identifier}")
        
        try:
            # Fetch data from external source (e.g., TOTVS API)
            client_data_api = get_legal_entity_data(identifier)

            if not client_data_api:
                logger.warning(f"No data found from API for identifier: {identifier}")
                return None, None # Indicate failure: client not found

            # Basic cleaning/validation of API data before DB interaction
            # Example: Ensure essential fields exist
            required_api_fields = ['code', 'name', 'cnpj']
            if not all(field in client_data_api for field in required_api_fields):
                 logger.error(f"Incomplete data received from API for identifier {identifier}: {client_data_api}")
                 raise ValueError("Dados da API do cliente estão incompletos.")

            # Clean CNPJ from API data (assuming it might have punctuation)
            api_cnpj_clean = ''.join(filter(str.isdigit, client_data_api['cnpj']))
            client_data_api['cnpj'] = self._format_cnpj_for_db(api_cnpj_clean) # Format for DB if needed

            # Check if the client already exists in our database
            cliente_existente_db = verificar_cliente_existente(
                client_data_api['cnpj'], client_data_api['code']
            )

            if cliente_existente_db:
                logger.info(f"Client found in DB (ID: {cliente_existente_db['client_id']}). Checking for updates...")
                
                # Compare existing data with new data from API
                if not self._dados_sao_iguais(cliente_existente_db, client_data_api):
                    logger.info("Client data has changed. Updating database...")
                    atualizar_cliente(client_data_api)
                else:
                    logger.info("Client data is up-to-date. No database update needed.")
                # Use the potentially updated data from the API for the session
                final_client_data = client_data_api
            else:
                logger.info("Client not found in DB. Inserting new client...")
                inserir_cliente(client_data_api)
                final_client_data = client_data_api # Use the inserted data

            # Ensure invoice value is a float
            invoice_val_float = float(invoice_value)
            
            logger.info(f"Client data collection and processing successful for identifier: {identifier}")
            return final_client_data, invoice_val_float

        except (ValueError, LookupError) as ve: # Catch specific errors from DB/API handling
            logger.error(f"Validation or lookup error during client data collection for {identifier}: {str(ve)}")
            raise # Re-raise to be caught by the route handler
        except Exception as e:
            logger.exception(f"Unexpected error collecting client data for {identifier}: {str(e)}")
            raise # Re-raise generic exceptions

    def _dados_sao_iguais(self, db_data, api_data):
        """Compares client data from the database with data from the API."""
        # Fields to compare (adjust based on what's important and available)
        # Ensure keys match the dictionary keys from DB and API results
        campos_para_comparar = [
            ('name', 'name'), 
            ('number_state_registration', 'number_state_registration'), 
            ('city_name', 'city_name'),
            ('state_abbreviation', 'state_abbreviation'), 
            ('cep', 'cep'), 
            ('address', 'address'), 
            ('neighborhood', 'neighborhood'),
            ('address_number', 'address_number'), 
            ('ibge_city_code', 'ibge_city_code')
            # Add/remove fields as necessary
        ]

        for db_field, api_field in campos_para_comparar:
            # Use .get() with default None to avoid KeyError if a field is missing
            valor_banco = db_data.get(db_field)
            valor_api = api_data.get(api_field)

            # Normalize and compare values (e.g., strip whitespace, handle case-insensitivity if needed)
            # Comparing as strings is generally safer for varying data types
            val_banco_str = str(valor_banco).strip() if valor_banco is not None else ''
            val_api_str = str(valor_api).strip() if valor_api is not None else ''

            if val_banco_str != val_api_str:
                logger.info(f"Data difference detected in field '{db_field}': DB='{val_banco_str}', API='{val_api_str}'")
                return False # Data is different

        return True # No differences found

    def _format_cnpj_for_db(self, cnpj_digits):
        """Formats a 14-digit CNPJ string for database storage (e.g., with punctuation). Adjust if DB format differs."""
        if len(cnpj_digits) == 14:
            return f"{cnpj_digits[:2]}.{cnpj_digits[2:5]}.{cnpj_digits[5:8]}/{cnpj_digits[8:12]}-{cnpj_digits[12:]}"
        return cnpj_digits # Return original if not 14 digits
        
    # _mapear_campo_para_api can be removed if the field names are consistent
    # or kept if mapping is complex/expected to change.
    # Assuming consistency for now based on _dados_sao_iguais structure.