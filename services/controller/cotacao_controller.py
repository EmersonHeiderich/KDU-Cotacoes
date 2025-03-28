# services/controller/cotacao_controller.py
from config import CurrentConfig # Import configuration
# Import carrier functions
from services.transportadoras.btu import gera_cotacao_braspress
from services.transportadoras.epc import gera_cotacao_epc
from services.transportadoras.esm import gera_cotacao_es_miguel
from services.transportadoras.rte import gera_cotacao_rte
from services.transportadoras.ssw import consultar_transportadora, get_ssw_carrier_config # Updated import
from services.transportadoras.tnt import calcular_frete_tnt
# Import DB functions
from db.quotes import inserir_quote, get_next_protocolo
from db.quote_packages import inserir_quote_packages
from db.quote_responses import inserir_quote_response
# Import other controllers if needed (or pass data)
from services.controller.company_controller import CompanyController 
import eventlet
import logging
from decimal import Decimal # Use Decimal for monetary values

# Configure logger (assuming configured globally in app.py)
logger = logging.getLogger(__name__)

class CotacaoController:

    def gerar_protocolo(self):
        """Generates a unique sequential protocol number for the quote."""
        try:
            protocolo = get_next_protocolo()
            logger.info(f"Generated new protocol: {protocolo}")
            return protocolo
        except Exception as e:
            logger.error(f"Failed to generate protocol: {e}", exc_info=True)
            raise # Re-raise to indicate failure

    def obter_dados_base_para_cotacao(self, client_data, packages_data, invoice_value):
        """
        Compiles essential client, package, and company data needed for carrier APIs.
        Does NOT include the protocol, which is generated later.
        """
        logger.debug("Preparing base data for quotation APIs.")
        if not client_data or not packages_data or invoice_value is None:
            logger.error("Missing client, packages, or invoice value for preparing quote data.")
            return None

        # Get company data using CompanyController
        company_controller = CompanyController() # Instantiate here or inject if preferred
        company_data = company_controller.get_company_data()
        if not company_data:
            logger.error("Failed to retrieve company (origin) data. Cannot proceed.")
            # This should ideally raise an error or be handled more explicitly
            return None

        # Prepare package list structure if needed (already seems correct from PackageManager)
        packs_list = packages_data.get('pack', [])
        if not packs_list:
             logger.error("Package list ('pack') is empty in packages_data.")
             return None

        # Assemble the base data dictionary
        cotacao_base_data = {
            # Company (Origin) Details
            "comp_name": company_data.get('name'),
            "comp_cnpj": company_data.get('cnpj'),
            "comp_number_state_registration": company_data.get('number_state_registration'),
            "comp_city_name": company_data.get('city_name'),
            "comp_state_abbreviation": company_data.get('state_abbreviation'),
            "comp_cep": company_data.get('cep'),
            "comp_ibge_city_code": company_data.get('ibge_city_code'),
            "comp_city_id": CurrentConfig.DEFAULT_COMPANY_CITY_ID_RTE,
            "comp_contact_name": CurrentConfig.DEFAULT_COMPANY_CONTACT_NAME, # From config
            "comp_contact_phone": CurrentConfig.DEFAULT_COMPANY_CONTACT_PHONE, # From config

            # Client (Destination) Details
            "cli_cnpj": client_data.get('cnpj'),
            "cli_cep": client_data.get('cep'),
            "cli_number_state_registration": client_data.get('number_state_registration', 'ISENTO'), # Default to ISENTO
            "cli_ibge_city_code": client_data.get('ibge_city_code'),
            # Add other client fields if needed by any carrier API (e.g., city name, state)

            # Shipment Details
            "invoice_value": Decimal(invoice_value), # Use Decimal for accuracy
            "pack": packs_list, # The list of package dictionaries
            "total_weight": Decimal(packages_data.get('total_weight', 0)),
            "total_packages": int(packages_data.get('total_packages', 0)),
            "volume_total": Decimal(packages_data.get('total_volume', 0)),
        }
        
        # Log a snippet of the prepared data (avoid logging full sensitive data if possible)
        logger.debug(f"Base quote data prepared for Client CNPJ: {cotacao_base_data['cli_cnpj']}, "
                     f"Total Weight: {cotacao_base_data['total_weight']}")
        return cotacao_base_data

    def salvar_cotacao_inicial(self, cotacao_data_final):
        """Saves the initial quote record and its associated packages to the database."""
        try:
            # Insert the main quote record
            quote_id = inserir_quote(cotacao_data_final)
            logger.info(f"Main quote record saved with ID: {quote_id}, Protocol: {cotacao_data_final['protocolo']}")
            
            # Insert associated packages
            inserir_quote_packages(quote_id, cotacao_data_final['pack'])
            logger.info(f"Associated packages saved for quote ID: {quote_id}")
            
            return quote_id
        except Exception as e:
            logger.error(f"Error saving initial quote data for protocol {cotacao_data_final.get('protocolo')}: {e}", exc_info=True)
            raise # Re-raise to be caught by the background task handler

    def solicitar_cotacoes(self, quote_id, cotacao_data, socket_callback):
        """
        Orchestrates concurrent quote requests to carriers using eventlet GreenPool.
        Saves responses to the database and triggers the SocketIO callback.
        """
        if not cotacao_data or not quote_id:
            logger.error("Insufficient data to request quotations.")
            return

        logger.info(f"Requesting quotes for Quote ID: {quote_id}, Protocol: {cotacao_data['protocolo']}...")

        # List of functions to call for each carrier/modal
        transportadoras_tasks = []

        # Add tasks for non-SSW carriers
        transportadoras_tasks.extend([
            lambda: gera_cotacao_braspress(cotacao_data, modal="R"), # Rodoviário
            lambda: gera_cotacao_braspress(cotacao_data, modal="A"), # Aéreo
            lambda: gera_cotacao_epc(cotacao_data),
            lambda: gera_cotacao_es_miguel(cotacao_data),
            lambda: gera_cotacao_rte(cotacao_data),
            lambda: calcular_frete_tnt(cotacao_data),
        ])

        # Add tasks for SSW carriers from config
        for carrier_code in CurrentConfig.SSW_CARRIERS.keys():
             # Use a factory function to capture the carrier_code correctly in the lambda's scope
             def create_ssw_task(code=carrier_code):
                 return lambda: consultar_transportadora(
                     carrier_code=code, # Pass the code to identify config
                     dados_usuario=cotacao_data
                 )
             transportadoras_tasks.append(create_ssw_task())

        # Use GreenPool for concurrency
        pool = eventlet.GreenPool()
        results_processed = 0

        # Callback function to handle results from each greenlet
        def handle_carrier_result(cotacao_response):
            nonlocal results_processed
            results_processed += 1
            if cotacao_response and isinstance(cotacao_response, dict) and 'Transportadora' in cotacao_response:
                try:
                    # Save the response to the database
                    inserir_quote_response(quote_id, cotacao_response)
                    # Emit the result via SocketIO callback
                    socket_callback(cotacao_response)
                    logger.info(f"Processed response from {cotacao_response['Transportadora']} for quote {quote_id}.")
                except Exception as e:
                    logger.error(f"Error processing/saving response for quote {quote_id} from "
                                 f"{cotacao_response.get('Transportadora', 'Unknown')}: {e}", exc_info=True)
                    # Optionally emit an error state for this carrier via socket_callback
                    error_response = {
                        'Transportadora': cotacao_response.get('Transportadora', 'Unknown'),
                        'message': f'Erro interno ao processar resposta: {e}',
                        'frete': None, 'prazo': None, 'cotacao': None, 'modal': '-'
                    }
                    socket_callback(error_response) # Emit error state
            else:
                # Handle cases where the carrier function failed or returned invalid data
                logger.warning(f"Invalid or failed response received from a carrier task for quote {quote_id}.")
                # Optionally emit a generic failure state if needed

        # Spawn greenlets for each carrier task
        logger.info(f"Spawning {len(transportadoras_tasks)} tasks for quote {quote_id}.")
        for task_func in transportadoras_tasks:
            pool.spawn_n(self._execute_carrier_request, task_func, handle_carrier_result)

        # Wait for all tasks to complete
        pool.waitall()
        logger.info(f"All {results_processed} carrier tasks completed for quote {quote_id}.")


    def _execute_carrier_request(self, carrier_func, result_callback):
        """Helper method to safely execute a single carrier request function."""
        try:
            # Execute the specific carrier function (e.g., gera_cotacao_braspress)
            cotacao_result = carrier_func()
            result_callback(cotacao_result) # Pass result (or None/error dict) to handler
        except Exception as e:
            # Log error specific to this carrier function execution
            # The function name isn't easily accessible here without inspect, log generically
            logger.error(f"Exception during carrier request execution: {e}", exc_info=True)
            # Call the callback with None or an error structure to indicate failure
            # result_callback(None) # Or potentially an error dict if needed
            # Let the carrier function itself return the error dict if possible