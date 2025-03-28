# services/transportadoras/ssw.py
import requests
import xml.etree.ElementTree as ET
import html
import time
import logging
from config import CurrentConfig # Import configuration
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation # Use Decimal

logger = logging.getLogger(__name__)

# Constants from Config
SSW_BASE_URL = CurrentConfig.SSW_BASE_URL
SSW_SOAP_ACTION = CurrentConfig.SSW_SOAP_ACTION
SSW_CARRIERS_CONFIG = CurrentConfig.SSW_CARRIERS # Dict of carrier configs
API_TIMEOUT = CurrentConfig.DEFAULT_API_TIMEOUT

def get_ssw_carrier_config(carrier_code):
    """Retrieves the configuration for a specific SSW carrier."""
    config = SSW_CARRIERS_CONFIG.get(carrier_code.upper())
    if not config:
         logger.error(f"Configuration for SSW carrier code '{carrier_code}' not found.")
         raise ValueError(f"Configuração SSW não encontrada para {carrier_code}")
    return config

def _build_ssw_soap_body(config, dados_usuario):
    """Builds the SOAP XML body for the SSW request."""
    
    # Extract required data, converting types as needed
    try:
        dominio = config['dominio']
        login = config['login']
        senha = config['senha']
        mercadoria = int(config['mercadoria'])
        
        # Clean CNPJ/CEP (digits only)
        cnpj_pagador_clean = ''.join(filter(str.isdigit, dados_usuario['comp_cnpj']))
        cnpj_destinatario_clean = ''.join(filter(str.isdigit, dados_usuario['cli_cnpj']))
        cep_origem_clean = ''.join(filter(str.isdigit, dados_usuario['comp_cep']))
        cep_destino_clean = ''.join(filter(str.isdigit, dados_usuario['cli_cep']))
        
        # Use Decimal for monetary/weight/volume, then convert to string/float as needed by API
        valor_nf = Decimal(dados_usuario['invoice_value']).quantize(Decimal('0.01'))
        peso_total = Decimal(dados_usuario['total_weight']).quantize(Decimal('0.01')) # e.g., 2 decimals
        volume_total = Decimal(dados_usuario['volume_total']).quantize(Decimal('0.0001')) # e.g., 4 decimals
        quantidade = int(dados_usuario['total_packages'])
        
    except (KeyError, ValueError, TypeError, InvalidOperation) as e:
        logger.error(f"Invalid data for building SSW payload for {config.get('dominio')}: {e}", exc_info=True)
        raise ValueError(f"Dados inválidos para cotação SSW ({config.get('dominio')}): {e}") from e

    # Construct the XML Body
    # Note: SSW API seems to expect integer/decimal types specified via xsi:type
    # Ensure values are formatted correctly (e.g., no thousands separators for numbers)
    body = f'''<soapenv:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:urn="urn:sswinfbr.sswCotacao">
        <soapenv:Header/>
        <soapenv:Body>
            <urn:cotar soapenv:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
                <dominio xsi:type="xsd:string">{dominio}</dominio>
                <login xsi:type="xsd:string">{login}</login>
                <senha xsi:type="xsd:string">{senha}</senha>
                <cnpjPagador xsi:type="xsd:string">{cnpj_pagador_clean}</cnpjPagador>
                <cepOrigem xsi:type="xsd:integer">{cep_origem_clean}</cepOrigem>
                <cepDestino xsi:type="xsd:integer">{cep_destino_clean}</cepDestino>
                <valorNF xsi:type="xsd:decimal">{valor_nf}</valorNF> 
                <quantidade xsi:type="xsd:integer">{quantidade}</quantidade>
                <peso xsi:type="xsd:decimal">{peso_total}</peso> 
                <volume xsi:type="xsd:decimal">{volume_total}</volume> 
                <mercadoria xsi:type="xsd:integer">{mercadoria}</mercadoria>
                <cnpjDestinatario xsi:type="xsd:string">{cnpj_destinatario_clean}</cnpjDestinatario>
                {'''
                <!-- Optional fields - keep empty or omit if not used -->
                <coletar xsi:type="xsd:string"></coletar>
                <entDificil xsi:type="xsd:string"></entDificil>
                <destContribuinte xsi:type="xsd:string"></destContribuinte>
                <qtdePares xsi:type="xsd:integer"></qtdePares>
                <fatorMultiplicador xsi:type="xsd:integer"></fatorMultiplicador>
                '''}
            </urn:cotar>
        </soapenv:Body>
    </soapenv:Envelope>'''
    
    logger.debug(f"SSW SOAP Payload ({dominio}):\n{body[:1000]}...") # Log truncated payload
    return body.encode('utf-8') # Encode to bytes


def _parse_ssw_response(response_text, carrier_code, config):
    """Parses the XML response from the SSW API."""
    try:
        root = ET.fromstring(response_text)
        # Define namespaces used in the SSW response
        namespaces = {
            'SOAP-ENV': 'http://schemas.xmlsoap.org/soap/envelope/',
            'ns1': 'urn:sswinfbr.sswCotacao' # Check if this prefix is correct in response
            # Add other namespaces if necessary
        }

        # Find the 'return' element containing the inner XML or error message
        # Path might vary, inspect actual response XML
        return_element = root.find('.//ns1:cotarResponse/return', namespaces) # Common path
        if return_element is None:
             # Try another common path if the first fails
             return_element = root.find('.//return') 

        if return_element is None:
            logger.error(f"Element 'return' not found in SSW response for {carrier_code}.")
            # Check for SOAP Fault
            fault_string = root.findtext('.//faultstring')
            if fault_string:
                logger.error(f"SSW SOAP Fault ({carrier_code}): {fault_string}")
                return {"message": f"Erro SOAP SSW: {fault_string}"}
            return {"message": "Elemento 'return' não encontrado na resposta SSW"}

        return_xml_content = return_element.text
        if not return_xml_content:
             logger.error(f"Element 'return' is empty in SSW response for {carrier_code}.")
             return {"message": "Resposta interna SSW vazia"}

        # --- Parse the inner XML content within the 'return' tag ---
        try:
            inner_root = ET.fromstring(return_xml_content)
            
            # Check for errors reported within the inner XML
            cod_erro = inner_root.findtext('.//erro', default='0').strip()
            mensagem_erro = inner_root.findtext('.//mensagem', default='').strip()
            
            if cod_erro != '0' or mensagem_erro:
                # Decode HTML entities in error message
                if mensagem_erro:
                    mensagem_erro = html.unescape(mensagem_erro)
                
                logger.warning(f"SSW API returned error for {carrier_code}: Code={cod_erro}, Message='{mensagem_erro}'")
                # Standardize common errors
                if "CEP NAO ENCONTRADO" in mensagem_erro.upper() or \
                   "NAO ATENDE A REGIAO" in mensagem_erro.upper() or \
                   cod_erro == '99': # Assuming 99 means not served
                    return {"message": "Destino não atendido"}
                return {"message": f"Erro SSW ({cod_erro}): {mensagem_erro}" if mensagem_erro else f"Erro SSW Cód: {cod_erro}"}

            # If no error, extract freight value and delivery time
            valor_frete_str = inner_root.findtext('.//totalFrete', default='0').strip()
            prazo_str = inner_root.findtext('.//prazo', default='0').strip()
            
            valor_frete = None
            prazo = None
            
            try:
                valor_frete_dec = Decimal(valor_frete_str.replace(',', '.')) # Handle potential comma decimal separator
                if valor_frete_dec <= 0:
                     logger.warning(f"SSW returned non-positive freight for {carrier_code}: {valor_frete_dec}")
                else:
                     # Apply carrier-specific adjustments (e.g., Zanotelli)
                     adjustment_factor = config.get('adjustment_factor')
                     if adjustment_factor and adjustment_factor != 1:
                         try:
                              valor_frete_dec = (valor_frete_dec / Decimal(adjustment_factor))\
                                                 .quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                              logger.info(f"Applied adjustment factor {adjustment_factor} to {carrier_code}. New frete: {valor_frete_dec}")
                         except (TypeError, ValueError, InvalidOperation):
                              logger.error(f"Invalid adjustment factor {adjustment_factor} for {carrier_code}. Skipping adjustment.")

                     valor_frete = float(valor_frete_dec) # Convert final Decimal to float

            except (InvalidOperation, ValueError):
                 logger.warning(f"Invalid freight value from SSW for {carrier_code}: {valor_frete_str}")

            try:
                prazo_int = int(prazo_str)
                if prazo_int <= 0:
                     logger.warning(f"SSW returned non-positive prazo for {carrier_code}: {prazo_int}")
                else:
                     prazo = prazo_int
            except ValueError:
                 logger.warning(f"Invalid prazo value from SSW for {carrier_code}: {prazo_str}")

            if valor_frete is not None and prazo is not None:
                 logger.info(f"SSW Quote successful ({carrier_code}): Frete={valor_frete}, Prazo={prazo}")
                 return {
                     "frete": valor_frete,
                     "prazo": prazo,
                     "cotacao": None, # SSW doesn't seem to return a quote ID here
                     "message": None # Success
                 }
            else:
                 # Treat cases with zero/invalid frete/prazo as 'not served' or specific error
                 logger.warning(f"SSW quote for {carrier_code} resulted in invalid frete/prazo.")
                 return {"message": "Destino não atendido ou cotação inválida"}

        except ET.ParseError as e:
            logger.error(f"Error parsing inner XML from SSW return tag ({carrier_code}): {e}\nContent: {return_xml_content[:500]}", exc_info=True)
            return {"message": f"Erro ao analisar XML interno SSW: {e}"}

    except ET.ParseError as e:
        logger.error(f"Error parsing outer SSW SOAP response ({carrier_code}): {e}\nContent: {response_text[:500]}", exc_info=True)
        return {"message": f"Erro ao analisar SOAP SSW: {e}"}
    except Exception as e:
         logger.error(f"Unexpected error parsing SSW response ({carrier_code}): {e}", exc_info=True)
         return {"message": f"Erro inesperado ao processar resposta SSW: {e}"}


def consultar_transportadora(carrier_code, dados_usuario):
    """
    Queries a specific SSW carrier based on its code and user data.
    """
    logger.info(f"Requesting quote from SSW Carrier: {carrier_code}...")
    
    try:
        config = get_ssw_carrier_config(carrier_code)
        body = _build_ssw_soap_body(config, dados_usuario)
        
        headers = {
            'Content-Type': 'text/xml; charset=utf-8',
            'SOAPAction': SSW_SOAP_ACTION
        }
        
        start_time = time.time()
        response = requests.post(SSW_BASE_URL, headers=headers, data=body, timeout=API_TIMEOUT)
        elapsed_time = time.time() - start_time
        logger.info(f"SSW API response time ({carrier_code}): {elapsed_time:.2f} seconds")
        logger.debug(f"SSW Response Body ({carrier_code}):\n{response.text[:1000]}...")

        if response.status_code != 200:
            logger.error(f"SSW request failed ({carrier_code}): HTTP {response.status_code} {response.reason}")
            # Try parsing for SOAP fault
            try:
                 root = ET.fromstring(response.text)
                 fault_string = root.findtext('.//faultstring')
                 if fault_string:
                      return {
                          "Transportadora": carrier_code, "modal": "Rodoviário", "frete": None, 
                          "prazo": None, "cotacao": None, "message": f"Erro SOAP SSW ({response.status_code}): {fault_string}"
                      }
            except ET.ParseError:
                 pass # Ignore if not XML
            return {
                "Transportadora": carrier_code, "modal": "Rodoviário", "frete": None, 
                "prazo": None, "cotacao": None, "message": f"Erro HTTP {response.status_code} SSW"
            }
            
        # Parse the successful response
        parsed_result = _parse_ssw_response(response.text, carrier_code, config)
        
        return {
            "Transportadora": carrier_code, # Return the internal code
            "modal": "Rodoviário", # Assuming all SSW are Rodoviário
            **parsed_result # Includes frete, prazo, cotacao, message
        }

    except ValueError as ve: # Catch config or payload building errors
         logger.error(f"Configuration or data error for SSW {carrier_code}: {ve}")
         return {"Transportadora": carrier_code, "modal": "Rodoviário", "frete": None, "prazo": None, "cotacao": None, "message": str(ve)}
    except requests.exceptions.Timeout:
        elapsed_time = time.time() - start_time
        logger.error(f"SSW API request timed out ({carrier_code}) after {elapsed_time:.2f}s.")
        return {"Transportadora": carrier_code, "modal": "Rodoviário", "frete": None, "prazo": None, "cotacao": None, "message": f"Timeout SSW ({API_TIMEOUT}s)"}
    except requests.exceptions.RequestException as e:
        logger.error(f"SSW API request failed ({carrier_code}): {e}", exc_info=True)
        return {"Transportadora": carrier_code, "modal": "Rodoviário", "frete": None, "prazo": None, "cotacao": None, "message": f"Erro comunicação SSW: {e}"}
    except Exception as e:
         logger.exception(f"Unexpected error during SSW quotation for {carrier_code}: {e}")
         return {"Transportadora": carrier_code, "modal": "Rodoviário", "frete": None, "prazo": None, "cotacao": None, "message": f"Erro inesperado SSW: {e}"}