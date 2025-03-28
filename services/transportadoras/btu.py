# services/transportadoras/btu.py
import requests
import base64
import time
import logging
from config import CurrentConfig # Import configuration
from decimal import Decimal, InvalidOperation # Use Decimal

logger = logging.getLogger(__name__)

# Constants from Config
BTU_URL = CurrentConfig.BTU_URL
BTU_USER = CurrentConfig.BTU_USER
BTU_PASSWORD = CurrentConfig.BTU_PASSWORD
API_TIMEOUT = CurrentConfig.DEFAULT_API_TIMEOUT

def get_auth_header(username, password):
    """Generates the Basic Authentication header."""
    if not username or not password:
         logger.error("BTU username or password missing in configuration.")
         raise ValueError("Credenciais BTU ausentes.")
    auth_str = f"{username}:{password}"
    auth_encoded = base64.b64encode(auth_str.encode()).decode('ascii')
    return {
        'Authorization': f'Basic {auth_encoded}',
        'Content-Type': 'application/json;charset=UTF-8',
        'Accept': 'application/json' # Specify JSON accept
        # 'User-Agent': 'YourAppName/1.0' # Optional: Set a User-Agent
    }

def build_payload(dados, modal):
    """Constructs the payload for the Braspress API request."""
    try:
        # Clean CNPJ and CEP (digits only)
        cnpj_remetente_clean = ''.join(filter(str.isdigit, dados['comp_cnpj']))
        cnpj_destinatario_clean = ''.join(filter(str.isdigit, dados['cli_cnpj']))
        cep_origem_clean = ''.join(filter(str.isdigit, dados['comp_cep']))
        cep_destino_clean = ''.join(filter(str.isdigit, dados['cli_cep']))
        
        # Validate modal
        modal_upper = str(modal).upper()
        if modal_upper not in ['R', 'A']:
            raise ValueError(f"Modal inválido para Braspress: {modal}. Usar 'R' ou 'A'.")

        # Prepare cubagem details (convert dimensions from cm to meters)
        cubagem = []
        for pack in dados.get('pack', []):
             cubagem.append({
                 "altura": float(Decimal(pack['Height']) / 100), # cm to m, float for JSON
                 "largura": float(Decimal(pack['Width']) / 100),  # cm to m, float for JSON
                 "comprimento": float(Decimal(pack['Length']) / 100), # cm to m, float for JSON
                 "volumes": int(pack.get('AmountPackages', 1)) # Ensure integer
             })

        if not cubagem:
            raise ValueError("Lista de embalagens (cubagem) está vazia.")

        payload = {
            "cnpjRemetente": cnpj_remetente_clean,
            "cnpjDestinatario": cnpj_destinatario_clean,
            "modal": modal_upper, # R = Rodoviário, A = Aéreo
            "tipoFrete": "1", # 1 = CIF (Remetente paga) - Check if correct
            "cepOrigem": cep_origem_clean,
            "cepDestino": cep_destino_clean,
            "vlrMercadoria": float(dados['invoice_value']), # Float for JSON
            "peso": float(dados['total_weight']), # Float for JSON
            "volumes": int(dados['total_packages']), # Integer
            "cubagem": cubagem
        }
        logger.debug(f"BTU Payload (Modal: {modal_upper}): {payload}")
        return payload

    except (KeyError, ValueError, TypeError, InvalidOperation) as e:
        logger.error(f"Error building BTU payload (Modal: {modal}): {e}", exc_info=True)
        raise ValueError(f"Dados inválidos para cotação BTU: {e}") from e

def process_btu_response(response_data, modal):
    """Processes the JSON response data from Braspress."""
    if not response_data or not isinstance(response_data, dict):
        logger.error("Invalid BTU response data received.")
        return {"message": "Resposta inválida da API BTU"}

    # Check for errors reported by the API
    # Structure might vary, check API docs. Common patterns: 'hasError', 'errors', 'message'
    if response_data.get("hasError", False) or "errorList" in response_data or "message" in response_data:
        error_message = response_data.get("message", "Erro desconhecido BTU")
        error_list = response_data.get("errorList", [])
        detailed_error = "; ".join(str(e) for e in error_list) if error_list else "Sem detalhes"
        final_message = f"{error_message}: {detailed_error}".strip(': ')
        
        logger.error(f"BTU API returned error (Modal: {modal}): {final_message}")
        # Standardize common errors
        if "CEP NAO ATENDIDO" in final_message.upper() or \
           "NAO ATENDE" in final_message.upper():
            return {"message": "Destino não atendido"}
        # Add more known error standardizations here
        return {"message": final_message}

    # Process successful response
    try:
        frete_val = None
        frete_api = response_data.get('totalFrete') # Key might be different
        if frete_api is not None:
            try:
                frete_dec = Decimal(frete_api)
                if frete_dec > 0:
                    frete_val = float(frete_dec)
                else:
                    logger.warning(f"BTU returned non-positive frete (Modal: {modal}): {frete_api}")
            except (InvalidOperation, ValueError):
                logger.warning(f"Invalid frete value from BTU (Modal: {modal}): {frete_api}")

        prazo_val = None
        prazo_api = response_data.get('prazo') # Key might be different
        if prazo_api is not None:
             try:
                  prazo_int = int(prazo_api)
                  if prazo_int > 0:
                       prazo_val = prazo_int
                  else:
                       logger.warning(f"BTU returned non-positive prazo (Modal: {modal}): {prazo_api}")
             except ValueError:
                  logger.warning(f"Invalid prazo value from BTU (Modal: {modal}): {prazo_api}")

        cotacao_id = response_data.get('id') # API's quote identifier

        if frete_val is not None and prazo_val is not None:
            modal_desc = "Rodoviário" if modal == "R" else "Aéreo"
            logger.info(f"BTU Quote successful (Modal: {modal_desc}): Frete={frete_val}, Prazo={prazo_val}, ID={cotacao_id}")
            return {
                "frete": frete_val,
                "prazo": prazo_val,
                "cotacao": cotacao_id,
                "message": None # Success
            }
        else:
            logger.error(f"BTU response structure ok, but frete or prazo missing/invalid (Modal: {modal}). Data: {response_data}")
            return {"message": "Frete ou prazo inválido na resposta BTU"}

    except (KeyError, TypeError, ValueError) as e:
        logger.error(f"Error processing BTU success response (Modal: {modal}): {e}. Data: {response_data}", exc_info=True)
        return {"message": f"Erro processamento BTU: {e}"}


def gera_cotacao_braspress(dados, modal):
    """Generates a quote with Braspress for the specified modal (R or A)."""
    modal_upper = str(modal).upper()
    modal_desc = "Rodoviário" if modal_upper == "R" else "Aéreo"
    logger.info(f"Requesting quote from BTU (Braspress) - Modal: {modal_desc}...")
    
    final_result = {
        "Transportadora": "BTU",
        "modal": modal_desc,
        "frete": None,
        "prazo": None,
        "cotacao": None,
        "message": "Falha na inicialização"
    }

    try:
        # Get authentication header
        headers = get_auth_header(BTU_USER, BTU_PASSWORD)
        # Build payload
        payload = build_payload(dados, modal_upper)
        
        start_time = time.time()
        response = requests.post(BTU_URL, json=payload, headers=headers, timeout=API_TIMEOUT)
        elapsed_time = time.time() - start_time
        logger.info(f"BTU API response time (Modal: {modal_desc}): {elapsed_time:.2f} seconds")
        
        # Log raw response status and body (truncated)
        logger.debug(f"BTU Raw Response Status (Modal: {modal_desc}): {response.status_code}")
        response_body_text = response.text
        try:
            response_data = response.json()
            logger.debug(f"BTU Raw Response Body (JSON, Modal: {modal_desc}): {response_data}")
        except ValueError:
            response_data = None
            logger.debug(f"BTU Raw Response Body (Non-JSON, Modal: {modal_desc}): {response_body_text[:500]}")

        # Check for HTTP errors first
        if response.status_code != 200:
            http_error_msg = f"Erro HTTP {response.status_code} {response.reason}"
            if response_data and isinstance(response_data, dict): # Try to get API message from JSON body
                error_message = response_data.get("message", http_error_msg)
                error_list = response_data.get("errorList", [])
                detailed_error = "; ".join(str(e) for e in error_list) if error_list else ""
                final_message = f"{error_message}: {detailed_error}".strip(': ')
            else: # Use HTTP status if body is not helpful JSON
                final_message = http_error_msg
            
            logger.error(f"BTU request failed (Modal: {modal_desc}): {final_message}. Raw Text: {response_body_text[:200]}")
            final_result["message"] = final_message
            return final_result

        # Process the successful JSON response
        processed_result = process_btu_response(response_data, modal_upper)
        final_result.update(processed_result)
        
    except ValueError as ve: # Catch config or payload building errors
         logger.error(f"Configuration or data error for BTU (Modal: {modal_desc}): {ve}")
         final_result["message"] = str(ve)
    except requests.exceptions.Timeout:
        elapsed_time = time.time() - start_time
        logger.error(f"BTU API request timed out (Modal: {modal_desc}) after {elapsed_time:.2f}s.")
        final_result["message"] = f"Timeout BTU ({API_TIMEOUT}s)"
    except requests.exceptions.RequestException as e:
        logger.error(f"BTU API request failed (Modal: {modal_desc}): {e}", exc_info=True)
        final_result["message"] = f"Erro comunicação BTU: {e}"
    except Exception as e:
        logger.exception(f"Unexpected error during BTU quotation (Modal: {modal_desc}): {e}")
        final_result["message"] = f"Erro inesperado BTU: {e}"
        
    return final_result