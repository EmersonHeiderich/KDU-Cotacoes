# services/transportadoras/esm.py
import requests
from datetime import datetime, timedelta
import time
import logging
from config import CurrentConfig # Import configuration
from decimal import Decimal, InvalidOperation # Use Decimal

logger = logging.getLogger(__name__)

# Constants from Config
URL_ES_MIGUEL = CurrentConfig.ESM_URL
HEADERS_ES_MIGUEL = {
    "access_key": CurrentConfig.ESM_ACCESS_KEY,
    "customer": CurrentConfig.ESM_CUSTOMER_CNPJ, # Use CNPJ from config
    "version": "2",
    "Content-Type": "application/json" # Ensure content type is set
}
FATOR_CUBAGEM_ES_MIGUEL = Decimal(CurrentConfig.ESM_CUBAGE_FACTOR) # Use Decimal
API_TIMEOUT = CurrentConfig.DEFAULT_API_TIMEOUT

def _calcular_peso_final_esm(packages, total_weight_real):
    """Calculates total cubed weight and returns the greater of cubed or real weight for ESM."""
    peso_cubado_total = Decimal(0)
    if not packages: return total_weight_real
    
    for pack in packages:
        try:
            comprimento_cm = Decimal(pack['Length'])
            altura_cm = Decimal(pack['Height'])
            largura_cm = Decimal(pack['Width'])
            quantidade = Decimal(pack.get('AmountPackages', 1))
            
            volume_m3 = (comprimento_cm / 100) * (altura_cm / 100) * (largura_cm / 100)
            peso_cubado_unitario = volume_m3 * FATOR_CUBAGEM_ES_MIGUEL
            peso_cubado_total += peso_cubado_unitario * quantidade
        except (KeyError, TypeError, ValueError, InvalidOperation) as e:
             logger.error(f"Error calculating ESM cubed weight for package {pack}: {e}. Skipping.")
             # Potentially re-raise if calculation is critical
             
    peso_final = max(peso_cubado_total, total_weight_real)
    logger.debug(f"ESM Weight Calc: Real={total_weight_real}, Cubed={peso_cubado_total}, Final={peso_final}")
    # ESM API likely expects weight rounded, e.g., to 2 decimal places
    return peso_final.quantize(Decimal('0.01'))

def construir_payload_es_miguel(dados):
    """Constructs the payload for the ESM quote request."""
    try:
        # Calculate final weight
        peso_final = _calcular_peso_final_esm(dados.get('pack'), dados.get('total_weight', Decimal(0)))
        
        # Clean CNPJ (digits only)
        cliente_destino_clean = ''.join(filter(str.isdigit, dados['cli_cnpj']))
        
        payload = {
            "tipoPagoPagar": "P", # Origin pays (Pagador na Origem) - Check if correct
            "codigoCidadeDestino": dados['cli_ibge_city_code'], # 7-digit IBGE code
            "quantidadeMercadoria": int(dados['total_packages']),
            "pesoMercadoria": float(peso_final), # API expects float, use calculated final weight
            "valorMercadoria": float(dados['invoice_value']), # API expects float
            "tipoPeso": "P", # Indicates 'Peso Real' (but value sent is max(real,cubed)) - Verify meaning
            "clienteDestino": cliente_destino_clean, # CNPJ digits only
            "dataEmbarque": datetime.now().strftime("%d/%m/%Y"), # Current date
            "tipoPessoaDestino": "J" # Juridical Person (Legal Entity)
            # Add 'volumes' array if the API supports/requires detailed package dimensions
            # "volumes": [ { "quantidade": p['AmountPackages'], "alturaCm": p['Height'], ... } for p in dados['pack'] ] # Example
        }
        logger.debug(f"ESM Payload: {payload}")
        return payload
    except (KeyError, ValueError, TypeError, InvalidOperation) as e:
        logger.error(f"Error building ESM payload: {e}", exc_info=True)
        raise ValueError(f"Dados inválidos para cotação ESM: {e}") from e

def _processar_resposta_esm(response_data):
    """Processes the successful JSON response from ESM."""
    if not response_data or not isinstance(response_data, dict):
        logger.error("Invalid ESM response data received.")
        # Return structure indicating failure
        return {"frete": None, "prazo": None, "cotacao": None, "message": "Resposta inválida da API ESM"}
        
    if response_data.get("status") != "ok":
        error_msg = response_data.get("mensagem", "Erro desconhecido da API ESM")
        logger.error(f"ESM API returned error status: {error_msg}")
        # Standardize common errors
        if "Nenhuma Unidade de Negocio atende" in error_msg or \
           "LOCALIDADE NAO ATENDIDA" in error_msg.upper(): # Check variations
            final_message = "Destino não atendido"
        else:
            final_message = error_msg
        return {"frete": None, "prazo": None, "cotacao": None, "message": final_message}

    # Process successful response ('status': 'ok')
    try:
        valor_frete = None
        frete_str = response_data.get('valorFrete')
        if frete_str is not None:
             try:
                  # Assuming value is returned as string like "1.234,56" or just number
                  valor_frete_dec = Decimal(str(frete_str).replace('.', '').replace(',', '.'))
                  if valor_frete_dec > 0:
                       valor_frete = float(valor_frete_dec)
                  else:
                       logger.warning(f"ESM returned non-positive frete: {frete_str}")
             except (InvalidOperation, ValueError):
                  logger.warning(f"Invalid frete value from ESM: {frete_str}")

        # Calculate delivery time (Prazo)
        prazo_entrega_dias = None
        try:
            # ESM provides 'previsaoEmbarque' (DD/MM/YYYY) and 'previsaoEntrega' (DD/MM/YYYY HH:MM)
            embarque_str = response_data.get('previsaoEmbarque')
            entrega_str = response_data.get('previsaoEntrega')
            if embarque_str and entrega_str:
                # Use current date as reference if embarque is in the past or invalid
                try:
                    data_embarque = datetime.strptime(embarque_str, "%d/%m/%Y").date()
                    if data_embarque < datetime.now().date(): data_embarque = datetime.now().date()
                except ValueError:
                     data_embarque = datetime.now().date()
                     
                # Use only the date part of entrega for day calculation
                data_entrega = datetime.strptime(entrega_str.split()[0], "%d/%m/%Y").date() 
                prazo_entrega_dias = max(0, (data_entrega - data_embarque).days)
        except (ValueError, TypeError, IndexError):
            logger.warning(f"Could not parse ESM delivery dates. Embarque: {embarque_str}, Entrega: {entrega_str}")

        cotacao_protocolo = response_data.get('cotacaoProtocolo') # ESM's quote protocol

        if valor_frete is not None and prazo_entrega_dias is not None:
             logger.info(f"ESM Quote successful: Frete={valor_frete}, Prazo={prazo_entrega_dias}, Protocolo={cotacao_protocolo}")
             return {
                 "frete": valor_frete,
                 "prazo": prazo_entrega_dias,
                 "cotacao": cotacao_protocolo,
                 "message": None # Success
             }
        else:
             # Handle cases where frete or prazo couldn't be determined from a 'status: ok' response
             logger.error("ESM response status 'ok' but frete or prazo is missing/invalid.")
             return {"frete": None, "prazo": None, "cotacao": cotacao_protocolo, "message": "Frete ou prazo inválido (status ok)"}

    except (KeyError, TypeError, ValueError) as e:
        logger.error(f"Error processing ESM success response: {e}. Data: {response_data}", exc_info=True)
        return {"frete": None, "prazo": None, "cotacao": None, "message": f"Erro processamento ESM: {e}"}


def solicitar_cotacao_es_miguel(payload):
    """Sends the quote request to ESM and returns the raw response dictionary or an error dict."""
    start_time = time.time()
    try:
        response = requests.post(URL_ES_MIGUEL, json=payload, headers=HEADERS_ES_MIGUEL, timeout=API_TIMEOUT)
        elapsed_time = time.time() - start_time
        logger.info(f"ESM API response time: {elapsed_time:.2f} seconds")

        # Log raw response regardless of status
        logger.debug(f"ESM Raw Response Status: {response.status_code}")
        response_body_text = response.text # Store text in case it's not JSON
        try:
             response_data = response.json()
             logger.debug(f"ESM Raw Response Body (JSON): {response_data}")
             return response_data # Return parsed JSON
        except ValueError:
             logger.debug(f"ESM Raw Response Body (Non-JSON): {response_body_text[:500]}")
             # Handle non-JSON response based on status code
             if response.status_code == 200:
                  # Status 200 but not JSON - unexpected
                  logger.error("ESM returned status 200 but response is not valid JSON.")
                  return {"status": "error", "mensagem": "Resposta inesperada da API ESM (não JSON)"}
             else:
                  # Use status code and reason for non-200, non-JSON responses
                  error_msg = f"Erro HTTP ESM {response.status_code} {response.reason}"
                  logger.error(f"{error_msg}. Response: {response_body_text[:200]}")
                  return {"status": "error", "mensagem": error_msg}

    except requests.exceptions.HTTPError as http_err:
         # This block might not be reached if response.json() fails first for non-200 JSON
         # Keeping it as a fallback
         error_msg = f"HTTP Error {http_err.response.status_code} {http_err.response.reason}"
         try:
              error_data = http_err.response.json()
              api_message = error_data.get("mensagem")
              if api_message:
                  if "Nenhuma Unidade de Negocio atende" in api_message: final_message = "Destino não atendido"
                  else: final_message = api_message
                  logger.error(f"ESM API returned HTTP error with message: {final_message}")
                  return {"status": "error", "mensagem": final_message} 
              else:
                  logger.error(f"ESM request failed: {error_msg}. Body: {error_data}")
                  return {"status": "error", "mensagem": f"Erro HTTP ESM: {error_msg}"}
         except ValueError: 
              logger.error(f"ESM request failed: {error_msg}. Response: {http_err.response.text[:200]}")
              return {"status": "error", "mensagem": f"Erro HTTP ESM ({http_err.response.status_code})"}

    except requests.exceptions.Timeout:
        elapsed_time = time.time() - start_time
        logger.error(f"ESM API request timed out after {elapsed_time:.2f} seconds (>{API_TIMEOUT}s limit).")
        return {"status": "error", "mensagem": f"Timeout ESM ({API_TIMEOUT}s)"}
    except requests.exceptions.RequestException as e:
        elapsed_time = time.time() - start_time
        logger.error(f"ESM API request failed: {e}", exc_info=True)
        return {"status": "error", "mensagem": f"Erro de comunicação ESM: {e}"}
    except Exception as e:
         logger.exception(f"Unexpected error during ESM request: {e}")
         return {"status": "error", "mensagem": f"Erro inesperado ESM: {e}"}


def gera_cotacao_es_miguel(dados):
    """Generates a quote with Expresso São Miguel."""
    logger.info("Requesting quote from ESM (Expresso São Miguel)...")
    final_result = {
        "Transportadora": "ESM", 
        "modal": "Rodoviário", 
        "frete": None, 
        "prazo": None, 
        "cotacao": None, 
        "message": "Falha na inicialização" # Default error
    }
    try:
        payload = construir_payload_es_miguel(dados)
        response_data = solicitar_cotacao_es_miguel(payload) # Gets raw dict or error dict
        
        # Process the raw response (which could be success or API error)
        processed_result = _processar_resposta_esm(response_data)
        
        # Update the final result with processed data (frete, prazo, cotacao, message)
        final_result.update(processed_result)
        
    except ValueError as ve: # Catch errors from building payload
         logger.error(f"Failed to build payload for ESM: {ve}")
         final_result["message"] = str(ve)
    except Exception as e:
        logger.exception(f"Unexpected error during ESM quotation generation: {e}")
        final_result["message"] = f"Erro inesperado: {e}"
        
    return final_result