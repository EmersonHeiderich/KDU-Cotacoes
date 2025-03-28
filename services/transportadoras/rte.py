# services/transportadoras/rte.py
import requests
import time
import logging
from config import CurrentConfig # Import configuration
from decimal import Decimal, InvalidOperation # Use Decimal

logger = logging.getLogger(__name__)

# Constants from Config
URL_TOKEN_COTACAO = CurrentConfig.RTE_TOKEN_COTACAO_URL
URL_TOKEN_BUSCA_CIDADE = CurrentConfig.RTE_TOKEN_BUSCA_CIDADE_URL
URL_CITY_ID_BY_ZIP_CODE = CurrentConfig.RTE_CITY_ID_URL
URL_COTACAO_RTE = CurrentConfig.RTE_COTACAO_URL
RTE_USERNAME = CurrentConfig.RTE_USERNAME
RTE_PASSWORD = CurrentConfig.RTE_PASSWORD
API_TIMEOUT = CurrentConfig.DEFAULT_API_TIMEOUT

# Simple in-memory token cache
_token_cache = {
    'cotacao': {'token': None, 'expires_at': 0},
    'busca_cidade': {'token': None, 'expires_at': 0}
}

def _obter_token_rte(token_url, cache_key):
    """Gets or refreshes an access token for a specific RTE API endpoint."""
    cache = _token_cache[cache_key]
    
    # Check cache validity (consider a buffer before expiration)
    if cache['token'] and time.time() < cache['expires_at'] - 60: # 60s buffer
        logger.debug(f"Using cached RTE token for '{cache_key}'. Expires at: {time.ctime(cache['expires_at'])}")
        return cache['token']

    logger.info(f"Requesting new RTE token for '{cache_key}' from {token_url}")
    payload = {
        "auth_type": "DEV", # Or "PROD" depending on environment/API requirements
        "grant_type": "password",
        "username": RTE_USERNAME,
        "password": RTE_PASSWORD
    }
    headers = {"content-type": "application/x-www-form-urlencoded"}
    
    try:
        response = requests.post(token_url, data=payload, headers=headers, timeout=API_TIMEOUT)
        response.raise_for_status() # Raises HTTPError for bad responses
        
        token_data = response.json()
        access_token = token_data.get('access_token')
        expires_in = int(token_data.get('expires_in', 3600)) # Default 1 hour
        
        if not access_token:
             logger.error(f"Access token not found in RTE response for '{cache_key}'.")
             raise ValueError(f"Token RTE ausente na resposta ({cache_key}).")
             
        # Update cache
        cache['token'] = access_token
        cache['expires_at'] = time.time() + expires_in
        
        logger.info(f"Successfully obtained new RTE token for '{cache_key}'.")
        logger.debug(f"RTE Token '{cache_key}' expires at: {time.ctime(cache['expires_at'])}")
        return access_token
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error requesting RTE token for '{cache_key}': {e}", exc_info=True)
        raise ConnectionError(f"Erro de comunicação ao obter token RTE ({cache_key}): {e}") from e
    except (ValueError, KeyError, TypeError) as e:
        logger.error(f"Error processing RTE token response for '{cache_key}': {e}", exc_info=True)
        raise ValueError(f"Erro ao processar resposta do token RTE ({cache_key}): {e}") from e

def obter_token_cotacao():
    """Facade function to get the quotation token."""
    return _obter_token_rte(URL_TOKEN_COTACAO, 'cotacao')

def obter_token_busca_cidade():
    """Facade function to get the city search token."""
    return _obter_token_rte(URL_TOKEN_BUSCA_CIDADE, 'busca_cidade')

def obter_city_id_rte(zip_code):
    """Queries the RTE API for the CityId corresponding to a Zip Code."""
    if not zip_code or not str(zip_code).isdigit():
        logger.error(f"Invalid Zip Code provided for RTE City ID lookup: {zip_code}")
        raise ValueError("CEP inválido para consulta de cidade RTE.")
        
    zip_code_clean = str(zip_code).strip()
    logger.info(f"Querying RTE City ID for Zip Code: {zip_code_clean}")
    
    try:
        token = obter_token_busca_cidade()
        url = f"{URL_CITY_ID_BY_ZIP_CODE}?zipCode={zip_code_clean}"
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
        response = requests.get(url, headers=headers, timeout=API_TIMEOUT)
        
        # Log status and raw response text for debugging
        logger.debug(f"RTE City ID Lookup - Status: {response.status_code}")
        response_body_text = response.text
        logger.debug(f"RTE City ID Lookup - Response Body: {response_body_text[:500]}") # Log truncated
        
        response.raise_for_status() # Check for HTTP errors
        
        data = response.json()
        
        # Check for API-specific errors within the JSON response
        # RTE often returns a list with an error message object
        if isinstance(data, list) and data and "Message" in data[0]:
            error_message = data[0]['Message']
            logger.error(f"RTE API error getting City ID for CEP {zip_code_clean}: {error_message}")
            # Standardize common errors
            if "CEP NAO ENCONTRADO" in error_message.upper():
                 raise LookupError("CEP não encontrado na base RTE.")
            raise ValueError(f"Erro API RTE (busca cidade): {error_message}")
        elif isinstance(data, dict) and "CityId" in data:
            city_id = data.get('CityId')
            if city_id is not None:
                 logger.info(f"RTE City ID found for CEP {zip_code_clean}: {city_id}")
                 return city_id
            else:
                 logger.error(f"RTE City ID is null in response for CEP {zip_code_clean}. Data: {data}")
                 raise LookupError("CityId nulo retornado pela API RTE.")
        else:
            # Unexpected response structure
            logger.error(f"Unexpected response structure from RTE City ID API for CEP {zip_code_clean}. Data: {data}")
            raise ValueError("Estrutura de resposta inesperada da API de cidade RTE.")

    except requests.exceptions.HTTPError as http_err:
        error_msg = f"Erro HTTP {http_err.response.status_code}"
        try: # Try to parse potential JSON error body
             error_data = http_err.response.json()
             if isinstance(error_data, list) and error_data and "Message" in error_data[0]:
                 api_message = error_data[0]['Message']
                 logger.error(f"RTE API HTTP error getting City ID ({error_msg}): {api_message}")
                 raise ValueError(f"Erro API RTE ({error_msg}): {api_message}") from http_err
        except ValueError: # Body is not JSON or structure is wrong
             pass # Fall through to generic error
        logger.error(f"RTE City ID lookup failed: {error_msg}. Response: {http_err.response.text[:200]}", exc_info=True)
        raise ConnectionError(f"Erro HTTP ao buscar cidade RTE ({error_msg})") from http_err
        
    except requests.exceptions.RequestException as req_err:
        logger.error(f"Error during RTE City ID lookup request for CEP {zip_code_clean}: {req_err}", exc_info=True)
        raise ConnectionError(f"Erro de comunicação ao buscar cidade RTE: {req_err}") from req_err
    except (ValueError, LookupError) as e: # Catch specific errors raised above
         raise e # Re-raise specific errors
    except Exception as e:
        logger.exception(f"Unexpected error getting RTE City ID for CEP {zip_code_clean}: {e}")
        raise RuntimeError(f"Erro inesperado ao buscar cidade RTE: {e}") from e


def build_rte_payload(dados, destination_city_id):
    """Builds the payload for the RTE quotation generation API."""
    try:
        # Clean CNPJ and CEP (digits only)
        origin_zip_clean = ''.join(filter(str.isdigit, dados['comp_cep']))
        dest_zip_clean = ''.join(filter(str.isdigit, dados['cli_cep']))
        customer_taxid_clean = ''.join(filter(str.isdigit, dados['comp_cnpj']))
        receiver_taxid_clean = ''.join(filter(str.isdigit, dados['cli_cnpj']))
        
        # Prepare package details (API expects integer dimensions in cm)
        packs_rte = []
        for pack in dados.get('pack', []):
             packs_rte.append({
                 "AmountPackages": int(pack.get('AmountPackages', 1)),
                 "Weight": float(Decimal(pack['Weight'])), # Float for JSON
                 "Length": int(Decimal(pack['Length'])),   # Integer cm
                 "Height": int(Decimal(pack['Height'])),   # Integer cm
                 "Width": int(Decimal(pack['Width']))     # Integer cm
             })

        if not packs_rte:
            raise ValueError("Lista de embalagens (Packs) está vazia para RTE.")

        payload = {
            "OriginZipCode": origin_zip_clean,
            "OriginCityId": dados['comp_city_id'], # From company data (config)
            "DestinationZipCode": dest_zip_clean,
            "DestinationCityId": destination_city_id, # Obtained via API lookup
            "TotalWeight": float(dados['total_weight']), # Float for JSON
            "EletronicInvoiceValue": float(dados['invoice_value']), # Float for JSON
            "CustomerTaxIdRegistration": customer_taxid_clean, # CNPJ Remetente
            "ReceiverCpfcnp": receiver_taxid_clean, # CNPJ Destinatário
            "Packs": packs_rte,
            "ContactName": dados.get('comp_contact_name', ''), # From config/company
            "ContactPhoneNumber": dados.get('comp_contact_phone', ''), # From config/company
            "TotalPackages": int(dados['total_packages']) # Required by API
        }
        logger.debug(f"RTE Quotation Payload: {payload}")
        return payload
        
    except (KeyError, ValueError, TypeError, InvalidOperation) as e:
        logger.error(f"Error building RTE quotation payload: {e}", exc_info=True)
        raise ValueError(f"Dados inválidos para cotação RTE: {e}") from e

def process_rte_response(response_data):
    """Processes the JSON response from the RTE quotation API."""
    if not response_data or not isinstance(response_data, dict):
        logger.error("Invalid RTE quotation response data received.")
        return {"message": "Resposta inválida da API RTE Cotação"}

    # Check for API-level errors (often indicated by a 'Message' field)
    if "Message" in response_data and response_data["Message"]:
        error_message = response_data["Message"]
        logger.error(f"RTE Quotation API returned error: {error_message}")
        # Standardize common errors
        if "NAO ATENDEMOS" in error_message.upper() or \
           "CIDADE NAO ATENDIDA" in error_message.upper():
            return {"message": "Destino não atendido"}
        return {"message": f"Erro API RTE: {error_message}"}
        
    # Process successful response
    try:
        value_api = response_data.get('Value')
        delivery_time_api = response_data.get('DeliveryTime')
        protocol_number = response_data.get('ProtocolNumber')

        frete_val = None
        if value_api is not None:
             try:
                  value_dec = Decimal(value_api)
                  if value_dec > 0: frete_val = float(value_dec)
                  else: logger.warning(f"RTE returned non-positive frete: {value_api}")
             except (InvalidOperation, ValueError):
                  logger.warning(f"Invalid frete value from RTE: {value_api}")
                  
        prazo_val = None
        if delivery_time_api is not None:
             try:
                  prazo_int = int(delivery_time_api)
                  if prazo_int >= 0: prazo_val = prazo_int # Allow 0 days? Check API meaning
                  else: logger.warning(f"RTE returned negative prazo: {delivery_time_api}")
             except ValueError:
                  logger.warning(f"Invalid prazo value from RTE: {delivery_time_api}")

        if frete_val is not None and prazo_val is not None:
            logger.info(f"RTE Quote successful: Frete={frete_val}, Prazo={prazo_val}, Protocolo={protocol_number}")
            return {
                "frete": frete_val,
                "prazo": prazo_val,
                "cotacao": protocol_number,
                "message": None # Success
            }
        else:
            logger.error(f"RTE response structure ok, but frete or prazo missing/invalid. Data: {response_data}")
            # Try to find more specific errors if available (e.g., in sub-objects)
            return {"message": "Frete ou prazo inválido na resposta RTE"}
            
    except (KeyError, TypeError, ValueError) as e:
        logger.error(f"Error processing RTE success response: {e}. Data: {response_data}", exc_info=True)
        return {"message": f"Erro processamento RTE: {e}"}


def gera_cotacao_rte(dados):
    """Generates a quote with RTE (Rodonaves)."""
    logger.info("Requesting quote from RTE (Rodonaves)...")
    final_result = {
        "Transportadora": "RTE", 
        "modal": "Rodoviário", 
        "frete": None, 
        "prazo": None, 
        "cotacao": None, 
        "message": "Falha na inicialização"
    }

    try:
        # 1. Get Destination City ID
        destination_city_id = obter_city_id_rte(dados['cli_cep'])
        
        # 2. Get Quotation Token
        token_cotacao = obter_token_cotacao()
        
        # 3. Build Payload
        payload = build_rte_payload(dados, destination_city_id)
        
        # 4. Make Quotation Request
        headers = {
            "accept": "application/json",
            "content-type": "application/json", # Use standard JSON content type
            "Authorization": f"Bearer {token_cotacao}"
        }
        
        start_time = time.time()
        response = requests.post(URL_COTACAO_RTE, json=payload, headers=headers, timeout=API_TIMEOUT)
        elapsed_time = time.time() - start_time
        logger.info(f"RTE Quotation API response time: {elapsed_time:.2f} seconds")

        # Log raw status and body
        logger.debug(f"RTE Quotation Raw Response Status: {response.status_code}")
        response_body_text = response.text
        try:
            response_data = response.json()
            logger.debug(f"RTE Quotation Raw Response Body (JSON): {response_data}")
        except ValueError:
            response_data = None
            logger.debug(f"RTE Quotation Raw Response Body (Non-JSON): {response_body_text[:500]}")

        # Check HTTP status
        if response.status_code != 200:
            http_error_msg = f"Erro HTTP {response.status_code} {response.reason}"
            api_message = http_error_msg
            if response_data and isinstance(response_data, dict) and "Message" in response_data:
                 api_message = response_data["Message"] # Use API message if available
            logger.error(f"RTE quotation request failed: {api_message}. Raw: {response_body_text[:200]}")
            final_result["message"] = api_message
            return final_result

        # 5. Process Successful Response
        processed = process_rte_response(response_data)
        final_result.update(processed)

    except (ValueError, LookupError, ConnectionError) as known_err: # Catch specific errors from helpers
         logger.error(f"Failed RTE quotation due to known error: {known_err}")
         final_result["message"] = str(known_err)
    except requests.exceptions.Timeout:
        elapsed_time = time.time() - start_time # Recalculate time if timeout happened during quote request
        logger.error(f"RTE Quotation API request timed out after {elapsed_time:.2f}s.")
        final_result["message"] = f"Timeout RTE ({API_TIMEOUT}s)"
    except requests.exceptions.RequestException as e:
        logger.error(f"RTE Quotation API request failed: {e}", exc_info=True)
        final_result["message"] = f"Erro comunicação RTE: {e}"
    except Exception as e:
        logger.exception(f"Unexpected error during RTE quotation: {e}")
        final_result["message"] = f"Erro inesperado RTE: {e}"
        
    return final_result