# services/totvs/person.py
import requests # Keep requests import if make_totvs_api_request is not used directly everywhere
import re
import json
import logging
from services.totvs.api import make_totvs_api_request, legal_entities_search_url # Use centralized request function
from config import CurrentConfig

logger = logging.getLogger(__name__)

# Mapping of Brazilian states (UF) to their IBGE code prefix (string)
# Ensure this map is accurate and complete
UF_TO_IBGE_PREFIX = {
    "AC": "12", "AL": "27", "AP": "16", "AM": "13", "BA": "29",
    "CE": "23", "DF": "53", "ES": "32", "GO": "52", "MA": "21",
    "MT": "51", "MS": "50", "MG": "31", "PA": "15", "PB": "25",
    "PR": "41", "PE": "26", "PI": "22", "RJ": "33", "RN": "24",
    "RS": "43", "RO": "11", "RR": "14", "SC": "42", "SP": "35",
    "SE": "28", "TO": "17"
}

def _is_cnpj_like(value):
    """Checks if a string looks like a CNPJ (digits only or with punctuation)."""
    if not isinstance(value, str):
        return False
    digits_only = ''.join(filter(str.isdigit, value))
    return len(digits_only) == 14

def _clean_state_registration(value):
    """Cleans state registration number, returning 'ISENTO' if empty or invalid."""
    if not value or not isinstance(value, str):
        return "ISENTO"
    # Remove non-alphanumeric characters (adjust if specific formats need preservation)
    cleaned = re.sub(r'\W+', '', value).upper() # Keep only letters/numbers, uppercase
    return cleaned if cleaned else "ISENTO"

def _format_ibge_code(partial_code, state_abbr):
    """Formats the full 7-digit IBGE city code."""
    if not partial_code or not state_abbr:
        return None
    prefix = UF_TO_IBGE_PREFIX.get(str(state_abbr).upper())
    if not prefix:
        logger.warning(f"Could not find IBGE prefix for state: {state_abbr}")
        return None
    # Ensure partial code is padded correctly (assuming API gives 5 digits)
    try:
        partial_code_str = str(int(partial_code)).zfill(5) # Convert to int, back to str, pad
        return prefix + partial_code_str
    except (ValueError, TypeError):
        logger.warning(f"Invalid partial IBGE code format: {partial_code}")
        return None

def get_legal_entity_data(identifier):
    """
    Queries the TOTVS API for legal entity data based on CNPJ or internal code.
    Returns a dictionary with structured client data or None if not found/error.
    """
    if not identifier:
        logger.warning("get_legal_entity_data called with empty identifier.")
        return None

    identifier_str = str(identifier).strip()
    page = 1
    page_size = 1 # We only expect/need one result

    # Determine filter type based on identifier format
    if _is_cnpj_like(identifier_str):
        filter_key = "cnpjList"
        # Clean CNPJ to digits only if API requires it, otherwise use original format
        # Assuming API can handle formatted CNPJ for now:
        identifier_value = [identifier_str] 
        # If API needs digits only: identifier_value = [''.join(filter(str.isdigit, identifier_str))]
        search_type = "CNPJ"
    else:
        # Assume it's an internal code
        try:
             identifier_value = [int(identifier_str)]
             filter_key = "personCodeList"
             search_type = "Code"
        except ValueError:
             logger.error(f"Invalid identifier format: '{identifier_str}'. Expected CNPJ or numeric code.")
             return None # Invalid identifier type

    logger.info(f"Searching TOTVS for legal entity with {search_type}: {identifier_value[0]}")

    # Construct payload for the API request
    payload = {
        "filter": {
            filter_key: identifier_value,
        },
        "expand": "addresses", # Request addresses to be included
        "page": page,
        "pageSize": page_size
    }

    try:
        # Use the centralized request function
        response_data = make_totvs_api_request('POST', legal_entities_search_url, json_data=payload)

        if not response_data or response_data.get("count", 0) == 0 or not response_data.get("items"):
            logger.warning(f"No legal entity found in TOTVS for {search_type}: {identifier_value[0]}")
            return None # Not found

        # Process the first item found
        item = response_data["items"][0]
        
        # --- Extract Core Information ---
        code = item.get("code")
        name = item.get("name")
        cnpj_raw = item.get("cnpj") # CNPJ as returned by API
        
        # Clean state registration
        number_state_registration = _clean_state_registration(item.get("numberStateRegistration"))

        # --- Extract Address Information ---
        addresses = item.get("addresses", [])
        address_info = None
        
        # Prioritize address type 5 (Delivery), then fallback to the first address
        for address in addresses:
            if address.get("addressTypeCode") == 5: # 'Delivery'
                address_info = address
                logger.debug("Found 'Delivery' address (type 5).")
                break
        
        if not address_info and addresses:
            address_info = addresses[0]
            logger.debug("No 'Delivery' address found, using the first address.")
        elif not addresses:
             logger.warning(f"No addresses found for entity code {code}.")
             # Decide how to handle missing address: return None or partial data?
             # Returning partial data might cause issues later. Best to return None or raise error.
             raise ValueError(f"Endereço não encontrado para o cliente código {code}.")

        city_name = address_info.get("cityName")
        state_abbreviation = address_info.get("stateAbbreviation")
        cep_raw = address_info.get("cep") # CEP might have punctuation
        address_street = address_info.get("address") # Street name part
        neighborhood = address_info.get("neighborhood")
        address_number = address_info.get("addressNumber")
        public_place = address_info.get("publicPlace") # e.g., "Rua", "Avenida"

        # Combine public place with street address if needed
        full_address = f"{public_place} {address_street}".strip() if public_place else address_street

        # Clean CEP (digits only)
        cep_clean = ''.join(filter(str.isdigit, cep_raw)) if cep_raw else None

        # Format IBGE code
        ibge_city_code_partial = address_info.get("ibgeCityCode")
        ibge_city_code = _format_ibge_code(ibge_city_code_partial, state_abbreviation)
        
        # Format CNPJ for consistency (e.g., with punctuation)
        cnpj_formatted = ClienteController._format_cnpj_for_db(None, ''.join(filter(str.isdigit, cnpj_raw))) if cnpj_raw else None # Use helper from ClienteController

        # --- Assemble Final Dictionary ---
        client_details = {
            "code": code,
            "name": name,
            "cnpj": cnpj_formatted, # Use formatted CNPJ
            "number_state_registration": number_state_registration,
            "city_name": city_name,
            "state_abbreviation": state_abbreviation,
            "cep": cep_clean, # Use cleaned CEP (digits only might be better for APIs)
            "address": full_address,
            "neighborhood": neighborhood,
            "address_number": address_number,
            "ibge_city_code": ibge_city_code
        }

        # Validate essential fields in the final structure
        if not all(client_details.get(k) for k in ['code', 'name', 'cnpj', 'cep', 'ibge_city_code']):
             logger.error(f"Essential client details missing after processing API response for {code}: {client_details}")
             raise ValueError(f"Dados essenciais do cliente {code} estão faltando após processamento.")

        logger.info(f"Successfully processed legal entity data for code {code}")
        return client_details

    # Catch specific errors from make_totvs_api_request or processing
    except (ValueError, ConnectionError, LookupError) as e: 
        logger.error(f"Failed to get/process legal entity data for identifier {identifier}: {e}", exc_info=True)
        # Re-raise the specific error to be potentially handled by the caller
        raise e 
    except Exception as e:
        logger.exception(f"Unexpected error getting legal entity data for identifier {identifier}: {e}")
        # Wrap unexpected errors
        raise RuntimeError(f"Erro inesperado ao buscar dados do cliente: {e}") from e


# Example Usage (for testing)
if __name__ == "__main__":
    from services.controller.cliente_controller import ClienteController # For _format_cnpj_for_db
    logging.basicConfig(level=logging.DEBUG)
    
    test_identifier = input("Digite o código ou CNPJ da pessoa jurídica para teste: ")
    try:
        legal_entity_data = get_legal_entity_data(test_identifier)

        if legal_entity_data:
            print("\nDados mapeados da pessoa jurídica:")
            print(json.dumps(legal_entity_data, indent=4, ensure_ascii=False))
        else:
            print("\nNenhum dado encontrado para o identificador informado.")
            
    except Exception as e:
         print(f"\nOcorreu um erro durante o teste: {e}")