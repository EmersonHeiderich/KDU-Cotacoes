# services/totvs/api.py
import requests
import logging
from config import CurrentConfig # Import configuration

logger = logging.getLogger(__name__)

# Construct URLs from config
auth_url = f"{CurrentConfig.TOTVS_BASE_URL}/authorization/v2/token"
legal_entities_search_url = f"{CurrentConfig.TOTVS_BASE_URL}/person/v2/legal-entities/search"

# Store token globally within the module (simple caching)
_access_token = None
# Could add expiration time checking if needed

def get_access_token():
    """
    Obtains or retrieves a cached access token for the TOTVS API.
    Handles authentication using credentials from config.
    """
    global _access_token
    # Simple cache check - could be enhanced with expiration time
    if _access_token:
        logger.debug("Using cached TOTVS access token.")
        return _access_token

    auth_data = {
        "username": CurrentConfig.TOTVS_USERNAME,
        "password": CurrentConfig.TOTVS_PASSWORD,
        "client_id": CurrentConfig.TOTVS_CLIENT_ID,
        "client_secret": CurrentConfig.TOTVS_CLIENT_SECRET,
        "grant_type": "password"
    }
    
    logger.info(f"Requesting new TOTVS access token from {auth_url}")
    logger.debug(f"TOTVS auth_data: {auth_data}") # Log auth_data
    try:
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        response = requests.post(auth_url, data=auth_data, headers=headers, timeout=CurrentConfig.DEFAULT_API_TIMEOUT) # Include headers
        response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)
        
        token_data = response.json()
        _access_token = token_data.get("access_token")
        
        if not _access_token:
             logger.error("Access token not found in TOTVS API response.")
             raise ValueError("Falha ao obter token de acesso TOTVS: token ausente na resposta.")
             
        logger.info("Successfully obtained new TOTVS access token.")
        # Simple caching: store the token
        # Add expiration logic here if needed (parse 'expires_in', store expiration timestamp)
        return _access_token
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error requesting TOTVS access token: {e}", exc_info=True)
        raise ConnectionError(f"Erro de comunicação ao obter token TOTVS: {e}") from e
    except ValueError as e:
        logger.error(f"Error processing TOTVS token response: {e}", exc_info=True)
        raise # Re-raise specific value errors

def make_totvs_api_request(method, url, headers=None, json_data=None, params=None):
    """Makes an authenticated request to the TOTVS API."""
    access_token = get_access_token() # Get token (handles caching/refresh)
    
    default_headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
         # Add other common headers if needed
    }
    if headers:
        default_headers.update(headers)

    logger.debug(f"Making TOTVS API request: {method} {url}")
    try:
        response = requests.request(
            method, 
            url, 
            headers=default_headers, 
            json=json_data, 
            params=params, 
            timeout=CurrentConfig.DEFAULT_API_TIMEOUT
        )
        response.raise_for_status() # Check for HTTP errors
        logger.debug(f"TOTVS API request successful ({response.status_code})")
        return response.json() # Return parsed JSON response

    except requests.exceptions.HTTPError as http_err:
         # Log specific HTTP errors
         logger.error(f"HTTP error during TOTVS API request to {url}: {http_err}")
         try:
             error_details = http_err.response.json()
             logger.error(f"TOTVS API Error Details: {error_details}")
             # Raise a more specific error or return None/error structure
             raise ValueError(f"Erro da API TOTVS ({http_err.response.status_code}): {error_details}") from http_err
         except ValueError: # If response is not JSON
              raise ValueError(f"Erro da API TOTVS ({http_err.response.status_code}): {http_err.response.text}") from http_err
    except requests.exceptions.RequestException as req_err:
         logger.error(f"Request exception during TOTVS API request to {url}: {req_err}", exc_info=True)
         raise ConnectionError(f"Erro de comunicação com a API TOTVS: {req_err}") from req_err
    except ValueError as json_err: # Error parsing JSON response
         logger.error(f"Error parsing JSON response from {url}: {json_err}", exc_info=True)
         raise ValueError(f"Resposta inválida (não JSON) da API TOTVS: {json_err}") from json_err
