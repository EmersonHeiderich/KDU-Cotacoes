# services/transportadoras/tnt.py
import requests
import xml.etree.ElementTree as ET
import time
import logging
from config import CurrentConfig # Import configuration
from decimal import Decimal, InvalidOperation # Use Decimal

logger = logging.getLogger(__name__)

# Constants from Config
URL_TNT = CurrentConfig.TNT_URL
TNT_LOGIN = CurrentConfig.TNT_LOGIN
TNT_PASSWORD = CurrentConfig.TNT_PASSWORD
FATOR_CUBAGEM_TNT = Decimal(CurrentConfig.TNT_CUBAGE_FACTOR) # Use Decimal
API_TIMEOUT = CurrentConfig.DEFAULT_API_TIMEOUT

def _calcular_peso_final_tnt(packages, total_weight_real):
    """Calculates total cubed weight and returns the greater of cubed or real weight."""
    peso_cubado_total = Decimal(0)
    if not packages: return total_weight_real # Return real weight if no packages
    
    for pack in packages:
        try:
            comprimento_cm = Decimal(pack['Length'])
            altura_cm = Decimal(pack['Height'])
            largura_cm = Decimal(pack['Width'])
            quantidade = Decimal(pack.get('AmountPackages', 1))

            volume_m3 = (comprimento_cm / 100) * (altura_cm / 100) * (largura_cm / 100)
            peso_cubado_unitario = volume_m3 * FATOR_CUBAGEM_TNT
            peso_cubado_total += peso_cubado_unitario * quantidade
        except (KeyError, TypeError, ValueError, InvalidOperation) as e:
             logger.error(f"Error calculating TNT cubed weight for package {pack}: {e}. Skipping.")
             
    peso_final = max(peso_cubado_total, total_weight_real)
    logger.debug(f"TNT Weight Calc: Real={total_weight_real}, Cubed={peso_cubado_total}, Final={peso_final}")
    return peso_final.quantize(Decimal('0.01')) # Return rounded Decimal

def _build_tnt_soap_body(dados_usuario, tp_situacao_tributaria_dest, peso_final):
    """Builds the SOAP XML body for the TNT request."""
    # Clean CNPJ and CEP (digits only)
    comp_cnpj_clean = ''.join(filter(str.isdigit, dados_usuario['comp_cnpj']))
    cli_cnpj_clean = ''.join(filter(str.isdigit, dados_usuario['cli_cnpj']))
    comp_cep_clean = ''.join(filter(str.isdigit, dados_usuario['comp_cep']))
    cli_cep_clean = ''.join(filter(str.isdigit, dados_usuario['cli_cep']))
    
    # Clean State Registrations (ISENTO or cleaned value)
    # TNT likely expects 'ISENTO' or the number. Assume clean_state_registration handles this.
    comp_ie = dados_usuario.get('comp_number_state_registration', 'ISENTO')
    cli_ie = dados_usuario.get('cli_number_state_registration', 'ISENTO')

    # Ensure 'ISENTO' is used if the value is effectively empty or explicitly ISENTO
    comp_ie = 'ISENTO' if not comp_ie or comp_ie.upper() == 'ISENTO' else comp_ie
    cli_ie = 'ISENTO' if not cli_ie or cli_ie.upper() == 'ISENTO' else cli_ie


    body = f'''<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ser="http://service.calculoFrete.mercurio.com" xmlns:mod="http://model.vendas.lms.mercurio.com">
        <soapenv:Header/>
        <soapenv:Body>
            <ser:calculaFrete>
                <ser:in0>
                    <mod:login>{TNT_LOGIN}</mod:login>
                    <mod:senha>{TNT_PASSWORD}</mod:senha>
                    <mod:nrIdentifClienteRem>{comp_cnpj_clean}</mod:nrIdentifClienteRem>
                    <mod:nrIdentifClienteDest>{cli_cnpj_clean}</mod:nrIdentifClienteDest>
                    <mod:tpFrete>C</mod:tpFrete> 
                    <mod:tpServico>RNC</mod:tpServico> 
                    <mod:cepOrigem>{comp_cep_clean}</mod:cepOrigem>
                    <mod:cepDestino>{cli_cep_clean}</mod:cepDestino>
                    <mod:vlMercadoria>{float(dados_usuario['invoice_value']):.2f}</mod:vlMercadoria> 
                    <mod:psReal>{float(peso_final):.2f}</mod:psReal> 
                    <mod:nrInscricaoEstadualRemetente>{comp_ie}</mod:nrInscricaoEstadualRemetente>
                    <mod:nrInscricaoEstadualDestinatario>{cli_ie}</mod:nrInscricaoEstadualDestinatario>
                    <mod:tpSituacaoTributariaRemetente>CO</mod:tpSituacaoTributariaRemetente> 
                    <mod:tpSituacaoTributariaDestinatario>{tp_situacao_tributaria_dest}</mod:tpSituacaoTributariaDestinatario>
                    <mod:cdDivisaoCliente>3</mod:cdDivisaoCliente> 
                    <mod:tpPessoaRemetente>J</mod:tpPessoaRemetente> 
                    <mod:tpPessoaDestinatario>J</mod:tpPessoaDestinatario> 
                    
                </ser:in0>
            </ser:calculaFrete>
        </soapenv:Body>
    </soapenv:Envelope>'''
    # Ensure floating point numbers have 2 decimal places as expected by some SOAP APIs
    
    # Log payload carefully, masking sensitive info if needed in production logs
    logger.debug(f"TNT SOAP Payload (Sit Trib Dest: {tp_situacao_tributaria_dest}):\n{body[:1000]}...") # Log truncated payload
    return body.encode('utf-8') # Encode body to bytes

def _parse_tnt_response(response_text):
    """Parses the XML response from TNT."""
    try:
        root = ET.fromstring(response_text)
        # Define namespaces used in the TNT response
        namespaces = {
            'soapenv': 'http://schemas.xmlsoap.org/soap/envelope/',
            'ser': 'http://service.calculoFrete.mercurio.com', # Adjust if needed based on actual response
             # Add other namespaces if present in the <out> element or its children
            'ns2': 'http://model.vendas.lms.mercurio.com' # Example based on request structure
        }

        # Find the main output element
        # Use the correct namespace prefix found in the actual response XML
        # The prefix might be different (e.g., ns0, ns1, etc.) or elements might have no prefix
        # Inspect a real response XML to confirm the path and namespaces
        # Common paths: './/ser:out', './/ns1:calculaFreteResponse/out', './/calculaFreteResponse/calculaFreteReturn'
        
        # Try finding 'out' potentially nested within response element
        out_element = root.find('.//ns2:out', namespaces) # Try with ns2 based on request structure
        if out_element is None:
             # Try finding it directly under Body/calculaFreteResponse if ns2 is wrong
             response_element = root.find('.//soapenv:Body/ser:calculaFreteResponse', namespaces)
             if response_element is not None:
                  out_element = response_element.find('out') # No namespace prefix if default
                  if out_element is None: # Try with ser prefix if needed
                       out_element = response_element.find('ser:out', namespaces)

        if out_element is None:
            logger.error("Element 'out' not found in TNT response.")
            # Check for faultstring for more specific errors
            fault_string = root.findtext('.//faultstring')
            if fault_string:
                 logger.error(f"TNT SOAP Fault: {fault_string}")
                 return {"message": f"Erro SOAP TNT: {fault_string}"}
            return {"message": "Elemento 'out' não encontrado na resposta TNT"}

        # Check for error messages within the 'out' element
        # Adjust path based on actual response structure (e.g., './/errorList', './/ns2:errorList')
        error_list = out_element.findtext('.//ns2:errorList', namespaces=namespaces) # Use correct namespace
        if error_list:
            logger.warning(f"TNT API returned error: {error_list}")
            # Standardize common error messages
            if "LOCALIDADE NAO ATENDIDA" in error_list.upper():
                 return {"message": "Destino não atendido"}
            elif "SITUACAO TRIBUTARIA DO DESTINATARIO NAO CONFERE" in error_list.upper():
                 return {"message": "Situação tributária destinatário inválida", "retry_code": "SIT_TRIB"}
            # Add more standardizations as needed
            return {"message": error_list} # Return API error message

        # Extract freight value and delivery time
        # Adjust paths based on actual response structure (e.g., './/vlTotalFrete', './/ns2:vlTotalFrete')
        vl_total_frete_str = out_element.findtext('.//ns2:vlTotalFrete', namespaces=namespaces)
        prazo_entrega_str = out_element.findtext('.//ns2:prazoEntrega', namespaces=namespaces)

        valor_frete = None
        prazo_entrega = None
        
        if vl_total_frete_str:
            try:
                valor_frete = Decimal(vl_total_frete_str)
                if valor_frete <= 0: valor_frete = None # Treat non-positive frete as invalid
            except (InvalidOperation, ValueError):
                logger.warning(f"Invalid freight value from TNT: {vl_total_frete_str}")
                
        if prazo_entrega_str:
             try:
                 prazo_entrega = int(prazo_entrega_str)
                 if prazo_entrega <= 0: prazo_entrega = None # Treat non-positive prazo as invalid
             except ValueError:
                  logger.warning(f"Invalid delivery time from TNT: {prazo_entrega_str}")

        if valor_frete is not None and prazo_entrega is not None:
            logger.info(f"TNT Quote successful: Frete={valor_frete}, Prazo={prazo_entrega}")
            return {
                "frete": float(valor_frete), # Convert Decimal to float
                "prazo": prazo_entrega,
                "cotacao": None, # TNT API doesn't seem to return a quote ID here
                "message": None # Success
            }
        else:
            logger.error("TNT response parsed but frete or prazo is invalid/missing.")
            return {"message": "Frete ou prazo inválido na resposta TNT"}

    except ET.ParseError as e:
        logger.error(f"Error parsing TNT XML response: {e}", exc_info=True)
        return {"message": f"Erro ao analisar XML TNT: {e}"}
    except Exception as e:
         logger.error(f"Unexpected error parsing TNT response: {e}", exc_info=True)
         return {"message": f"Erro inesperado ao processar resposta TNT: {e}"}


def _tentar_calculo_frete_tnt(dados_usuario, tp_situacao_tributaria_dest, peso_final):
    """Attempts freight calculation with a specific recipient tax situation."""
    headers = {'Content-Type': 'text/xml; charset=utf-8', 'SOAPAction': '""'} # SOAPAction might be needed
    body = _build_tnt_soap_body(dados_usuario, tp_situacao_tributaria_dest, peso_final)
    
    start_time = time.time()
    try:
        response = requests.post(URL_TNT, headers=headers, data=body, timeout=API_TIMEOUT)
        elapsed_time = time.time() - start_time
        logger.info(f"TNT API response time (Sit Trib Dest: {tp_situacao_tributaria_dest}): {elapsed_time:.2f} seconds")
        logger.debug(f"TNT Response Body (Sit Trib Dest: {tp_situacao_tributaria_dest}):\n{response.text[:1000]}...")

        if response.status_code != 200:
            logger.error(f"TNT request failed (Sit Trib Dest: {tp_situacao_tributaria_dest}): HTTP {response.status_code} {response.reason}")
            # Try parsing for SOAP fault
            try:
                 root = ET.fromstring(response.text)
                 fault_string = root.findtext('.//faultstring')
                 if fault_string:
                      return {"message": f"Erro SOAP TNT ({response.status_code}): {fault_string}"}
            except ET.ParseError:
                 pass # Ignore if not XML
            return {"message": f"Erro HTTP {response.status_code} na requisição TNT"}

        # Parse the successful response
        return _parse_tnt_response(response.text)

    except requests.exceptions.Timeout:
        elapsed_time = time.time() - start_time
        logger.error(f"TNT API request timed out (Sit Trib Dest: {tp_situacao_tributaria_dest}) after {elapsed_time:.2f}s.")
        return {"message": f"Timeout TNT ({API_TIMEOUT}s)"}
    except requests.exceptions.RequestException as e:
        logger.error(f"TNT API request failed (Sit Trib Dest: {tp_situacao_tributaria_dest}): {e}", exc_info=True)
        return {"message": f"Erro de comunicação TNT: {e}"}
    except Exception as e:
         logger.exception(f"Unexpected error during TNT attempt (Sit Trib Dest: {tp_situacao_tributaria_dest}): {e}")
         return {"message": f"Erro inesperado TNT: {e}"}


def calcular_frete_tnt(dados_usuario):
    """
    Calculates freight with TNT, trying different recipient tax situations if necessary.
    """
    logger.info("Requesting quote from TNT...")
    
    # Calculate final weight (max of real vs cubed)
    try:
        peso_final = _calcular_peso_final_tnt(dados_usuario.get('pack'), dados_usuario.get('total_weight'))
    except Exception as e:
         logger.error(f"Error calculating weight for TNT: {e}")
         return {"Transportadora": "TNT", "modal": "Rodoviário", "frete": None, "prazo": None, "cotacao": None, "message": f"Erro cálculo peso: {e}"}

    # Determine initial tax situation attempt based on IE
    cli_ie = dados_usuario.get('cli_number_state_registration', 'ISENTO')
    is_isento = not cli_ie or cli_ie.upper() == 'ISENTO'
    
    resultados = {} # Store results of attempts

    # Attempt 1: 'NC' if ISENTO, otherwise 'CO'
    sit_trib_tentativa_1 = 'NC' if is_isento else 'CO'
    logger.info(f"TNT Attempt 1: Trying with Sit Trib Dest = {sit_trib_tentativa_1}")
    resultado1 = _tentar_calculo_frete_tnt(dados_usuario, sit_trib_tentativa_1, peso_final)
    resultados[sit_trib_tentativa_1] = resultado1
    if resultado1.get("message") is None: # Success?
        logger.info("TNT Attempt 1 successful.")
        return {"Transportadora": "TNT", "modal": "Rodoviário", **resultado1}
        
    # Attempt 2: Try the other primary option ('CO' if first was 'NC', 'NC' if first was 'CO')
    # Only try 'NC' if the client is indeed ISENTO. Don't try 'NC' if they have an IE.
    sit_trib_tentativa_2 = None
    if sit_trib_tentativa_1 == 'NC': # First was NC (meaning client is ISENTO), try CO
        sit_trib_tentativa_2 = 'CO'
    elif sit_trib_tentativa_1 == 'CO' and is_isento: # First was CO, but client IS ISENTO, try NC
        sit_trib_tentativa_2 = 'NC'
        
    if sit_trib_tentativa_2:
        logger.info(f"TNT Attempt 2: Trying with Sit Trib Dest = {sit_trib_tentativa_2}")
        resultado2 = _tentar_calculo_frete_tnt(dados_usuario, sit_trib_tentativa_2, peso_final)
        resultados[sit_trib_tentativa_2] = resultado2
        if resultado2.get("message") is None: # Success?
            logger.info("TNT Attempt 2 successful.")
            return {"Transportadora": "TNT", "modal": "Rodoviário", **resultado2}
    
    # Attempt 3: If previous attempts failed specifically due to tax situation mismatch, try 'ME'
    should_try_me = False
    last_error_message = ""
    for sit_trib, result in resultados.items():
        if result.get("retry_code") == "SIT_TRIB":
            should_try_me = True
            last_error_message = result.get("message", "Situação tributária destinatário inválida")
            break
        elif result.get("message"): # Store the last known error message otherwise
             last_error_message = result.get("message")

    if should_try_me:
        logger.info("TNT Attempt 3: Tax situation error detected, trying with Sit Trib Dest = ME")
        resultado3 = _tentar_calculo_frete_tnt(dados_usuario, 'ME', peso_final)
        resultados['ME'] = resultado3
        if resultado3.get("message") is None: # Success?
            logger.info("TNT Attempt 3 successful.")
            return {"Transportadora": "TNT", "modal": "Rodoviário", **resultado3}
        elif resultado3.get("message"): # Store ME error if it failed
             last_error_message = resultado3.get("message")

    # All attempts failed, return the last relevant error message
    final_message = last_error_message or "Falha em todas as tentativas de cotação TNT"
    logger.error(f"TNT quotation failed after all attempts. Last error: {final_message}")
    return {
        "Transportadora": "TNT", "modal": "Rodoviário", "frete": None, 
        "prazo": None, "cotacao": None, "message": final_message
    }