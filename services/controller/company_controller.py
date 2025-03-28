# services/controller/company_controller.py
from db.company import get_company_by_code
from config import CurrentConfig # Import configuration
import logging

# Configure logger (assuming configured globally in app.py)
logger = logging.getLogger(__name__)

class CompanyController:
    def __init__(self):
        # Get the default company code from configuration
        self.default_company_code = CurrentConfig.DEFAULT_COMPANY_CODE
        logger.info(f"CompanyController initialized with default code: {self.default_company_code}")

    def get_company_data(self, company_code=None):
        """
        Retrieves company data from the database.
        Uses the default company code from config if no code is provided.
        """
        code_to_use = company_code if company_code else self.default_company_code
        
        if not code_to_use:
             logger.error("No company code specified or configured.")
             return None
             
        try:
            company_data = get_company_by_code(code_to_use)
            if not company_data:
                logger.error(f"Company with code {code_to_use} not found in database.")
                return None
            logger.debug(f"Company data retrieved successfully for code {code_to_use}.")
            return company_data
        except Exception as e:
            # Error is logged within get_company_by_code, re-raise or handle here
            logger.error(f"Failed to get company data for code {code_to_use}: {e}")
            # Depending on requirements, might return None or re-raise
            return None # Return None to indicate failure to controller caller