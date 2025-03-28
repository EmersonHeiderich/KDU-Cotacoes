# services/packages/package_manager.py
import logging
from decimal import Decimal, ROUND_HALF_UP # Use Decimal for precision

logger = logging.getLogger(__name__)

class Package:
    """Represents a single type of package with its dimensions, weight, and quantity."""
    
    # Use Decimal for dimensions and weight for accuracy
    _DECIMAL_CONTEXT = Decimal(1).quantize(Decimal('0.00001')) # Context for 5 decimal places

    def __init__(self, nome, comprimento, altura, largura, peso, quantidade=1):
        try:
            self.nome = str(nome)
            self.comprimento = self._validate_positive_decimal(comprimento, 'comprimento') # cm
            self.altura = self._validate_positive_decimal(altura, 'altura') # cm
            self.largura = self._validate_positive_decimal(largura, 'largura') # cm
            self.peso = self._validate_positive_decimal(peso, 'peso') # kg
            self.quantidade = self._validate_positive_integer(quantidade, 'quantidade')
        except (ValueError, TypeError) as e:
             logger.error(f"Error initializing Package '{nome}': {e}")
             raise # Re-raise for caller to handle

    def _validate_positive_decimal(self, value, name):
        """Validates if a value is a positive Decimal."""
        try:
            dec_value = Decimal(value)
            if dec_value <= 0:
                 raise ValueError(f"{name.capitalize()} must be positive.")
            # Apply context if needed, e.g., for rounding dimensions upon creation
            # return dec_value.quantize(self._DECIMAL_CONTEXT, rounding=ROUND_HALF_UP)
            return dec_value 
        except (TypeError, ValueError, InvalidOperation) as e:
             raise ValueError(f"Invalid value for {name}: {value}. Must be a positive number.") from e
             
    def _validate_positive_integer(self, value, name):
        """Validates if a value is a positive integer."""
        try:
            int_value = int(value)
            if int_value <= 0:
                 raise ValueError(f"{name.capitalize()} must be a positive integer.")
            return int_value
        except (TypeError, ValueError):
             raise ValueError(f"Invalid value for {name}: {value}. Must be a positive integer.") from e

    def get_volume_unitario(self):
        """Calculates the volume of a single package in cubic meters (m³) using Decimal."""
        # Convert cm to meters (Decimal division)
        length_m = self.comprimento / Decimal(100)
        height_m = self.altura / Decimal(100)
        width_m = self.largura / Decimal(100)
        # Calculate volume
        volume = length_m * height_m * width_m
        # Return rounded to a reasonable number of decimal places (e.g., 5)
        return volume.quantize(self._DECIMAL_CONTEXT, rounding=ROUND_HALF_UP)

    def to_dict(self):
        """Returns a dictionary representation of the package, suitable for APIs/session."""
        volume_unitario = self.get_volume_unitario()
        return {
            # Fields often required by carrier APIs (check case sensitivity)
            'AmountPackages': self.quantidade, # Total count of this package type
            'Weight': float(self.peso),         # Weight per package (some APIs might want total weight for this type) - converting to float for JSON/API compatibility if Decimal isn't handled
            'Length': float(self.comprimento),  # Dimensions per package (cm) - converting to float
            'Height': float(self.altura),       # - converting to float
            'Width': float(self.largura),       # - converting to float
            
            # Additional info for display or internal use
            'nome': self.nome,
            'quantidade': self.quantidade,
            'peso': float(self.peso),           # - converting to float
            'comprimento': float(self.comprimento), # - converting to float
            'altura': float(self.altura),       # - converting to float
            'largura': float(self.largura),     # - converting to float
            'volume_unitario': float(volume_unitario) # Volume per package (m³) - converting to float
        }
        
    def __repr__(self):
        volume = self.get_volume_unitario()
        return (f"Package(nome={self.nome}, q={self.quantidade}, dims="
                f"{self.comprimento}x{self.altura}x{self.largura}cm, "
                f"peso={self.peso}kg, vol_unit={volume}m³)")


class PackageManager:
    """Manages selected packages and calculates totals for quotation."""
    
    def __init__(self):
        # Consider loading from config or DB instead of hardcoding
        self.pre_defined_packages = {
            # ID: {nome, comprimento, altura, largura, peso_padrao}
            1: {'nome': 'PP', 'comprimento': 43, 'altura': 35, 'largura': 18, 'peso_padrao': 3},
            2: {'nome': 'P', 'comprimento': 43, 'altura': 35, 'largura': 21, 'peso_padrao': 6},
            3: {'nome': 'M', 'comprimento': 70, 'altura': 43, 'largura': 21, 'peso_padrao': 10},
            4: {'nome': 'G', 'comprimento': 70, 'altura': 43, 'largura': 31, 'peso_padrao': 20},
            5: {'nome': 'Bau', 'comprimento': 43, 'altura': 35, 'largura': 31, 'peso_padrao': 10},
            6: {'nome': 'Ternos', 'comprimento': 96, 'altura': 63, 'largura': 26, 'peso_padrao': 15}
        }
        self.selected_packages = [] # List to store Package objects

    def select_pre_defined_package(self, package_id, peso_override=None, quantidade=1):
        """Adds a predefined package type to the list, allowing weight override."""
        package_id = int(package_id) # Ensure ID is integer
        if package_id not in self.pre_defined_packages:
            logger.error(f"Invalid predefined package ID selected: {package_id}")
            raise ValueError(f"ID de embalagem pré-definida inválido: {package_id}.")
            
        package_template = self.pre_defined_packages[package_id]
        
        # Determine the weight to use
        if peso_override is not None:
            try:
                 # Validate the override weight
                 final_peso = Package._validate_positive_decimal(None, peso_override, 'peso override') # Use static validation method
            except ValueError as e:
                 logger.error(f"Invalid weight override for package ID {package_id}: {peso_override}. Error: {e}")
                 raise ValueError(f"Peso inválido fornecido para embalagem {package_template['nome']}: {peso_override}") from e
        else:
            final_peso = Decimal(package_template['peso_padrao']) # Use default weight

        try:
            # Create a Package instance
            package = Package(
                nome=package_template['nome'],
                comprimento=Decimal(package_template['comprimento']),
                altura=Decimal(package_template['altura']),
                largura=Decimal(package_template['largura']),
                peso=final_peso,
                quantidade=quantidade
            )
            self.selected_packages.append(package)
            logger.debug(f"Selected predefined package: {package}")
        except (ValueError, TypeError) as e:
             logger.error(f"Failed to create predefined package instance for ID {package_id}: {e}")
             # Re-raise or handle as appropriate
             raise

    def add_custom_package(self, nome, comprimento, altura, largura, peso, quantidade=1):
        """Adds a custom-defined package to the list."""
        try:
            package = Package(nome, comprimento, altura, largura, peso, quantidade)
            self.selected_packages.append(package)
            logger.debug(f"Added custom package: {package}")
        except (ValueError, TypeError) as e:
             logger.error(f"Failed to create custom package instance '{nome}': {e}")
             # Re-raise or handle
             raise

    def get_packages_for_cotation(self):
        """
        Returns aggregated package data for quotation APIs and display.
        Uses Decimal for internal calculations, converts totals to float for output if needed.
        """
        if not self.selected_packages:
             logger.warning("get_packages_for_cotation called with no selected packages.")
             return {
                 'pack': [], 'total_weight': 0.0, 'total_packages': 0, 'total_volume': 0.0
             }

        packages_list_dict = [pkg.to_dict() for pkg in self.selected_packages]
        
        total_weight_decimal = Decimal(0)
        total_volume_decimal = Decimal(0)
        total_packages_count = 0
        
        for package in self.selected_packages:
            qty = Decimal(package.quantidade)
            total_weight_decimal += package.peso * qty
            total_volume_decimal += package.get_volume_unitario() * qty
            total_packages_count += package.quantidade
            
        # Quantize totals for consistency
        total_volume_final = total_volume_decimal.quantize(Package._DECIMAL_CONTEXT, rounding=ROUND_HALF_UP)
        total_weight_final = total_weight_decimal.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) # e.g., 2 decimal places for weight

        return {
            'pack': packages_list_dict, # List of individual package type dicts
            'total_weight': float(total_weight_final),     # Convert final total to float for session/JSON
            'total_packages': total_packages_count,
            'total_volume': float(total_volume_final)      # Convert final total to float
        }

    def clear_packages(self):
        """Clears the list of selected packages."""
        self.selected_packages = []
        logger.info("Cleared selected packages.")