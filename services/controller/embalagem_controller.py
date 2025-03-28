# services/controller/embalagem_controller.py
from services.packages.package_manager import PackageManager
import logging

# Configure logger (assuming configured globally in app.py)
logger = logging.getLogger(__name__)

class EmbalagemController:
    
    def __init__(self):
        # Instantiate PackageManager here if it's lightweight, or pass if shared
        self.package_manager = PackageManager()

    def coletar_dados_embalagens(self, packages_data_list):
        """
        Processes a list of package data dictionaries from the frontend,
        adds them using PackageManager, and returns aggregated data.
        """
        if not isinstance(packages_data_list, list):
             logger.error("Invalid input: packages_data_list must be a list.")
             raise TypeError("Input must be a list of package data.")
             
        logger.info(f"Processing {len(packages_data_list)} package entries.")
        
        for package_info in packages_data_list:
            package_type = package_info.get('type')
            try:
                quantidade = int(package_info.get('quantidade', 1)) # Default to 1
                if quantidade <= 0:
                     logger.warning(f"Skipping package with non-positive quantity: {package_info}")
                     continue # Skip packages with zero or negative quantity

                if package_type == 'predefined':
                    package_id = int(package_info['package_id'])
                    # Allow optional weight override, ensure it's float
                    peso_override_str = package_info.get('peso')
                    peso_override = float(peso_override_str) if peso_override_str is not None else None
                    
                    self.package_manager.select_pre_defined_package(package_id, peso_override, quantidade)
                    logger.debug(f"Added predefined package: ID={package_id}, Qty={quantidade}, WeightOverride={peso_override}")

                elif package_type == 'custom':
                    # Validate and convert custom package data
                    nome = package_info.get('nome', 'Custom') # Default name if missing
                    comprimento = float(package_info['comprimento'])
                    altura = float(package_info['altura'])
                    largura = float(package_info['largura'])
                    peso = float(package_info['peso'])

                    # Basic validation for dimensions and weight
                    if not all(d > 0 for d in [comprimento, altura, largura, peso]):
                         logger.warning(f"Skipping custom package with invalid dimensions/weight: {package_info}")
                         continue

                    self.package_manager.add_custom_package(
                        nome, comprimento, altura, largura, peso, quantidade
                    )
                    logger.debug(f"Added custom package: Name={nome}, Qty={quantidade}")
                
                else:
                    logger.warning(f"Unknown package type encountered: '{package_type}'. Skipping.")
            
            except (KeyError, ValueError, TypeError) as e:
                 logger.error(f"Error processing package entry: {package_info}. Error: {e}")
                 # Decide whether to raise error or just log and skip
                 # Raising error might be better to inform user of bad data
                 raise ValueError(f"Erro nos dados da embalagem: {e}. Verifique os valores.") from e

        # Get the aggregated results after processing all entries
        processed_data = self.package_manager.get_packages_for_cotation()
        logger.info(f"Package processing complete. Total Weight: {processed_data['total_weight']}, "
                    f"Total Volume: {processed_data['total_volume']}, Total Packages: {processed_data['total_packages']}")
        return processed_data

    # Keep static method to easily get predefined packages for the template
    @staticmethod
    def get_predefined_packages():
        """Returns the dictionary of predefined packages."""
        # Creates a temporary instance just to access the data
        # Alternatively, make pre_defined_packages a class variable or load from config/db
        temp_manager = PackageManager()
        return temp_manager.pre_defined_packages