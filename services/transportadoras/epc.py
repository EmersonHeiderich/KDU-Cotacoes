# services/transportadoras/epc.py
import requests
from datetime import datetime
import time
import logging
from config import CurrentConfig # Import configuration
from decimal import Decimal, InvalidOperation # Use Decimal for calculations

logger = logging.getLogger(__name__)

# Constants from Config
URL_EPC = CurrentConfig.EPC_URL
AUTH_EPC = (CurrentConfig.EPC_USER, CurrentConfig.EPC_PASSWORD)
FATOR_CUBAGEM_EPC = Decimal(CurrentConfig.EPC_CUBAGE_FACTOR) # Use Decimal
API_TIMEOUT = CurrentConfig.DEFAULT_API_TIMEOUT

def _calcular_peso_cubado_epc(packages):
    """Calculates the total cubed weight for EPC using Decimal."""
    peso_cubado_total = Decimal(0)
    if not packages: return peso_cubado_total
    
    for pack in packages:
        try:
            comprimento_cm = Decimal(pack['Length'])
            altura_cm = Decimal(pack['Height'])
            largura_cm = Decimal(pack['Width'])
            quantidade = Decimal(pack.get('AmountPackages', 1))

            # Calculate volume in cubic meters
            volume_m3 = (comprimento_cm / 100) * (altura_cm / 100) * (largura_cm / 100)
            peso_cubado_unitario = volume_m3 * FATOR_CUBAGEM_EPC
            peso_cubado_total += peso_cubado_unitario * quantidade
        except (KeyError, TypeError, ValueError, InvalidOperation) as e:
             logger.error(f"Error calculating cubed weight for package {pack}: {e}. Skipping.")
             # Continue calculation with other packages, or raise error if needed
             
    # Return rounded Decimal (e.g., 4 decimal places)
    return peso_cubado_total.quantize(Decimal('0.0001'))

def construir_payload_epc(dados):
    """Constructs the payload for the EPC quote request."""
    peso_real_total = dados.get('total_weight', Decimal(0))
    peso_cubado_total = _calcular_peso_cubado_epc(dados.get('pack', []))

    # EPC API might expect the cubed weight in the 'volume' field based on original code
    # Verify this requirement with EPC documentation.
    # If it expects actual volume, calculate and send that instead.
    volume_para_api = peso_cubado_total # Assuming it expects cubed weight here
    
    # Clean CNPJ (remove punctuation) if API requires digits only
    cnpj_pagador_clean = ''.join(filter(str.isdigit, dados['comp_cnpj']))
    cnpj_destinatario_clean = ''.join(filter(str.isdigit, dados['cli_cnpj']))
    
    # Clean CEP (digits only)
    cep_origem_clean = ''.join(filter(str.isdigit, dados['comp_cep']))
    cep_destino_clean = ''.join(filter(str.isdigit, dados['cli_cep']))

    payload = {
        "cnpjPagador": cnpj_pagador_clean, # Assuming API needs digits only
        "cepOrigem": cep_origem_clean,     # Assuming API needs digits only
        "cnpjDestinatario": cnpj_destinatario_clean, # Assuming API needs digits only
        "cepDestino": cep_destino_clean,   # Assuming API needs digits only
        "embalagem": "CX", # Fixed value, or derive from packages if needed
        "valorNF": float(dados['invoice_value']), # API might expect float
        "quantidade": int(dados['total_packages']), # API likely expects integer
        "peso": float(peso_real_total), # Send actual weight - API might expect float
        "volume": float(volume_para_api) # Send cubed weight (as float) - VERIFY API DOCS
    }
    logger.debug(f"EPC Payload: {payload}")
    return payload

def solicitar_cotacao_epc(payload):
    """Sends the quote request to EPC and returns the response."""
    start_time = time.time()
    try:
        response = requests.post(URL_EPC, json=payload, auth=AUTH_EPC, timeout=API_TIMEOUT)
        elapsed_time = time.time() - start_time
        logger.info(f"EPC API response time: {elapsed_time:.2f} seconds")

        # Attempt to parse JSON regardless of status code for error messages
        try:
            response_data = response.json()
            logger.debug(f"EPC Response Body: {response_data}")
        except ValueError:
            response_data = None # Not JSON
            logger.debug(f"EPC Response Body (Non-JSON): {response.text}")

        # Check status code *after* attempting to get JSON error message
        if response.status_code != 200:
            error_msg = f"HTTP Error {response.status_code} {response.reason}"
            api_error = None
            if response_data and isinstance(response_data, dict):
                 api_error = response_data.get('erro') # Check specific error key
            
            if api_error:
                 # Specific known error message handling
                 if "Regiao de origem e destino nao atendida" in api_error:
                     final_message = "Destino não atendido"
                 else:
                     final_message = api_error # Use API's error message
                 logger.error(f"EPC API returned error: {final_message}")
            else:
                 final_message = f"Erro desconhecido: {error_msg}. Response: {response.text[:200]}" # Truncate long non-JSON responses
                 logger.error(f"EPC request failed: {final_message}")

            return {
                "Transportadora": "EPC", "modal": "Rodoviário", "frete": None, 
                "prazo": None, "cotacao": None, "message": final_message
            }

        # Status code is 200, return the parsed JSON data
        return response_data

    except requests.exceptions.Timeout:
        elapsed_time = time.time() - start_time
        logger.error(f"EPC API request timed out after {elapsed_time:.2f} seconds (>{API_TIMEOUT}s limit).")
        return {
            "Transportadora": "EPC", "modal": "Rodoviário", "frete": None, 
            "prazo": None, "cotacao": None, "message": f"Timeout ({API_TIMEOUT}s)"
        }
    except requests.exceptions.RequestException as e:
        elapsed_time = time.time() - start_time
        logger.error(f"EPC API request failed: {e}", exc_info=True)
        return {
            "Transportadora": "EPC", "modal": "Rodoviário", "frete": None, 
            "prazo": None, "cotacao": None, "message": f"Erro de comunicação: {e}"
        }

def _processar_resposta_epc(response_data):
    """Processes the successful JSON response from EPC."""
    if not response_data or not isinstance(response_data, dict):
        logger.error("Invalid EPC response data received for processing.")
        return {"message": "Resposta inválida da API"}

    try:
        # Extract and convert freight value
        frete_str = response_data.get("totalfrete", "0")
        # Replace thousand separators (.) then decimal separator (,)
        valor_frete = Decimal(frete_str.replace('.', '').replace(',', '.'))

        # Extract and calculate delivery time
        prazo_str = response_data.get("prazo") # Expected format "DD/MM/YYYY"
        prazo_entrega_dias = None
        if prazo_str:
            try:
                data_prazo = datetime.strptime(prazo_str, "%d/%m/%Y").date()
                data_atual = datetime.now().date()
                # Calculate difference in days, ensure non-negative
                prazo_entrega_dias = max(0, (data_prazo - data_atual).days) 
            except ValueError:
                logger.warning(f"Invalid date format for 'prazo' from EPC: {prazo_str}")
        
        cotacao_numero = response_data.get("numero") # Quote number from EPC

        logger.info(f"EPC Quote successful: Frete={valor_frete}, Prazo={prazo_entrega_dias}, Cotacao={cotacao_numero}")

        return {
            "frete": float(valor_frete) if valor_frete is not None else None, # Convert Decimal to float for consistency
            "prazo": prazo_entrega_dias,
            "cotacao": cotacao_numero,
            "message": None # Indicates success
        }

    except (InvalidOperation, KeyError, TypeError, ValueError) as e:
        logger.error(f"Error processing EPC success response: {e}. Data: {response_data}", exc_info=True)
        return {"message": f"Erro ao processar resposta EPC: {e}"}


def gera_cotacao_epc(dados):
    """Generates a quote with EPC."""
    logger.info("Requesting quote from EPC (Princesa dos Campos)...")
    try:
        payload = construir_payload_epc(dados)
        response_data = solicitar_cotacao_epc(payload)

        if response_data and response_data.get('message') is None: # Check if solicitation was successful
            processed_result = _processar_resposta_epc(response_data)
            # Combine results
            return {
                "Transportadora": "EPC",
                "modal": "Rodoviário",
                **processed_result # Includes frete, prazo, cotacao, message
            }
        else:
             # Solicitation failed, response_data contains the error structure
             return response_data if response_data else {
                 "Transportadora": "EPC", "modal": "Rodoviário", "frete": None, 
                 "prazo": None, "cotacao": None, "message": "Falha na solicitação à API EPC"
             }
             
    except Exception as e:
        logger.exception(f"Unexpected error during EPC quotation: {e}")
        return {
            "Transportadora": "EPC", "modal": "Rodoviário", "frete": None, 
            "prazo": None, "cotacao": None, "message": f"Erro inesperado: {e}"
        }