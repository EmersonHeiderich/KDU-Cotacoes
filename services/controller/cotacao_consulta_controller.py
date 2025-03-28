# services/controller/cotacao_consulta_controller.py
from flask import render_template, request, jsonify
from db.quotes import get_last_quotations, filter_quotations, get_quote_details
import logging

# Configure logger (assuming configured globally in app.py)
logger = logging.getLogger(__name__)

class CotacaoConsultaController:

    def show_consultations(self):
        """Renders the consultations page with the latest quotes."""
        try:
            # Retrieve the last 15 quotations
            quotations = get_last_quotations(limit=15)
            return render_template('consultations.html', quotations=quotations)
        except Exception as e:
            logger.error(f"Error showing consultations: {str(e)}", exc_info=True)
            # Return template with error message
            return render_template('consultations.html', quotations=[], error="Erro ao carregar cotações recentes.")

    def filter_consultations(self):
        """Applies filters and returns filtered quotations as JSON."""
        try:
            # Extract filter parameters from query string
            filters = {
                'code': request.args.get('code', '').strip(),
                'cnpj': request.args.get('cnpj', '').strip(),
                'name': request.args.get('name', '').strip(),
                'date': request.args.get('date', '').strip() # Expected format YYYY-MM-DD
            }
            # Basic validation can be added here if needed (e.g., date format)
            
            quotations = filter_quotations(filters)
            return jsonify({'quotations': quotations})
            
        except Exception as e:
            logger.error(f"Error filtering consultations: {str(e)}", exc_info=True)
            return jsonify({'error': 'Erro interno ao filtrar cotações.'}), 500 # Internal Server Error

    def show_quote_details(self, quote_id):
        """Renders the details page for a specific quote ID."""
        if not isinstance(quote_id, int) or quote_id <= 0:
             logger.warning(f"Invalid quote_id requested: {quote_id}")
             return render_template('quote_details.html', error="ID da cotação inválido."), 400 # Bad Request
             
        try:
            quote_data = get_quote_details(quote_id)
            if not quote_data:
                logger.warning(f"Quote details not found for ID: {quote_id}")
                return render_template('quote_details.html', error="Cotação não encontrada."), 404 # Not Found
                
            # Pass the structured data to the template
            return render_template('quote_details.html', 
                                   quote=quote_data['quote'], 
                                   client=quote_data['client'],
                                   packages=quote_data['packages'],
                                   responses=quote_data['responses'])
                                   
        except Exception as e:
            logger.error(f"Error showing quote details for ID {quote_id}: {str(e)}", exc_info=True)
            return render_template('quote_details.html', error="Erro interno ao carregar detalhes da cotação."), 500