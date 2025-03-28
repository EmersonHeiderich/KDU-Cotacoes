# config.py
import os
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'fallback_secret_key_for_dev')
    DEBUG = False
    TESTING = False
    
    # Database Configuration
    DB_HOST = os.environ.get('DB_HOST', '10.1.5.2')
    DB_PORT = os.environ.get('DB_PORT', '5432')
    DB_NAME = os.environ.get('DB_NAME', 'cotacoes')
    DB_USER = os.environ.get('DB_USER', 'postgres')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', '20Kdu21@@ti') # Use env var in production!

    # TOTVS API Configuration
    TOTVS_BASE_URL = os.environ.get('TOTVS_BASE_URL', 'http://10.1.1.221:11980/api/totvsmoda')
    TOTVS_USERNAME = os.environ.get('TOTVS_USERNAME', '77776')
    TOTVS_PASSWORD = os.environ.get('TOTVS_PASSWORD', 'ib77776') # Use env var in production!
    TOTVS_CLIENT_ID = os.environ.get('TOTVS_CLIENT_ID', 'kduapiv2')
    TOTVS_CLIENT_SECRET = os.environ.get('TOTVS_CLIENT_SECRET', '9157489678') # Use env var in production!

    # Company Default Code (Origin for Quotes)
    DEFAULT_COMPANY_CODE = os.environ.get('DEFAULT_COMPANY_CODE', '100000011')
    print(f"DEBUG: Raw value for DEFAULT_COMPANY_CITY_ID_RTE is: '{os.environ.get('DEFAULT_COMPANY_CITY_ID_RTE', '6609')}'")
    DEFAULT_COMPANY_CITY_ID_RTE = int(os.environ.get('DEFAULT_COMPANY_CITY_ID_RTE', '6609'))
    DEFAULT_COMPANY_CONTACT_NAME = os.environ.get('DEFAULT_COMPANY_CONTACT_NAME', 'Departamento de TI')
    DEFAULT_COMPANY_CONTACT_PHONE = os.environ.get('DEFAULT_COMPANY_CONTACT_PHONE', '46988259847')
    
    # Carrier Specific Configurations
    # EPC (Princesa dos Campos)
    EPC_URL = os.environ.get('EPC_URL', 'https://3kusfy-prd-protheus.totvscloud.com.br:11586/rest_prd/TMSWS001')
    EPC_USER = os.environ.get('EPC_USER', '10424098')
    EPC_PASSWORD = os.environ.get('EPC_PASSWORD', '#epc10424098') # Use env var in production!
    EPC_CUBAGE_FACTOR = int(os.environ.get('EPC_CUBAGE_FACTOR', '250'))
    
    # ESM (Expresso São Miguel)
    ESM_URL = os.environ.get('ESM_URL', 'https://wsintegcli01.expressosaomiguel.com.br:40504/wsservernet/rest/frete/buscar/portal-cliente')
    ESM_ACCESS_KEY = os.environ.get('ESM_ACCESS_KEY', 'E0D625BFCD0B49E0B1D0E05EA1130A0C') # Use env var!
    ESM_CUSTOMER_CNPJ = os.environ.get('ESM_CUSTOMER_CNPJ', '10424098000168')
    ESM_CUBAGE_FACTOR = int(os.environ.get('ESM_CUBAGE_FACTOR', '300'))

    # BTU (Braspress)
    BTU_URL = os.environ.get('BTU_URL', 'https://api.braspress.com/v1/cotacao/calcular/json')
    BTU_USER = os.environ.get('BTU_USER', '10424098000168_PRD')
    BTU_PASSWORD = os.environ.get('BTU_PASSWORD', 'XA3r26Wg3S3U3bqF') # Use env var!
    
    # TNT
    TNT_URL = os.environ.get('TNT_URL', 'https://ws.tntbrasil.com.br:443/tntws/CalculoFrete')
    TNT_LOGIN = os.environ.get('TNT_LOGIN', 'pedidos@kdu.com.br')
    TNT_PASSWORD = os.environ.get('TNT_PASSWORD', 'Kdufat2019@@') # Use env var!
    TNT_CUBAGE_FACTOR = int(os.environ.get('TNT_CUBAGE_FACTOR', '150'))

    # RTE (Rodonaves)
    RTE_TOKEN_COTACAO_URL = os.environ.get('RTE_TOKEN_COTACAO_URL', 'https://quotation-apigateway.rte.com.br/token')
    RTE_TOKEN_BUSCA_CIDADE_URL = os.environ.get('RTE_TOKEN_BUSCA_CIDADE_URL', 'https://01wapi.rte.com.br/token')
    RTE_CITY_ID_URL = os.environ.get('RTE_CITY_ID_URL', 'https://01wapi.rte.com.br/api/v1/busca-por-cep')
    RTE_COTACAO_URL = os.environ.get('RTE_COTACAO_URL', 'https://quotation-apigateway.rte.com.br/api/v1/gera-cotacao')
    RTE_USERNAME = os.environ.get('RTE_USERNAME', 'INDUSTRIAKDU')
    RTE_PASSWORD = os.environ.get('RTE_PASSWORD', 'F2BE4RH5') # Use env var!

    # SSW (Shared System Web) - Base URL and credentials/config per carrier
    SSW_BASE_URL = os.environ.get('SSW_BASE_URL', 'https://ssw.inf.br/ws/sswCotacao/index.php')
    SSW_SOAP_ACTION = 'urn:sswinfbr.sswCotacao#cotacao'
    
    SSW_CARRIERS = {
        'BAU': { # Bauer
            'dominio': 'BAU',
            'login': os.environ.get('SSW_BAU_LOGIN', 'kdu'),
            'senha': os.environ.get('SSW_BAU_PASSWORD', 'sq2n6m1'), # Use env var!
            'mercadoria': int(os.environ.get('SSW_BAU_MERCADORIA', '3')),
        },
        'PEP': { # Zanotelli (formerly PEP)
            'dominio': 'PEP',
            'login': os.environ.get('SSW_PEP_LOGIN', 'kduconf'),
            'senha': os.environ.get('SSW_PEP_PASSWORD', 'kduconf'), # Use env var!
            'mercadoria': int(os.environ.get('SSW_PEP_MERCADORIA', '38')),
            'adjustment_factor': float(os.environ.get('SSW_PEP_ADJUSTMENT_FACTOR', '0.88')) # Specific adjustment
        },
        'EUC': { # Eucatur
            'dominio': 'EUC',
            'login': os.environ.get('SSW_EUC_LOGIN', 'kdu'),
            'senha': os.environ.get('SSW_EUC_PASSWORD', '10424098'), # Use env var!
            'mercadoria': int(os.environ.get('SSW_EUC_MERCADORIA', '1')),
        }
        # Add other SSW carriers here if needed
    }
    
    # General API Settings
    DEFAULT_API_TIMEOUT = int(os.environ.get('DEFAULT_API_TIMEOUT', '25'))

class DevelopmentConfig(Config):
    DEBUG = True
    # Example: Override DB for development if needed
    # DB_HOST = 'localhost' 

class ProductionConfig(Config):
    DEBUG = False
    # Ensure strong SECRET_KEY and all credentials are set via environment variables

# Select configuration based on environment variable
app_env = os.environ.get('FLASK_ENV', 'development')

if app_env == 'production':
    CurrentConfig = ProductionConfig
else:
    CurrentConfig = DevelopmentConfig # Default to Development
