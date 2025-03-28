# app.py
import eventlet 
eventlet.monkey_patch() # Essential for eventlet async mode with SocketIO

import datetime
from flask import Flask, render_template, redirect, url_for, request, session, jsonify
from flask_socketio import SocketIO, emit, join_room
from config import CurrentConfig # Import configuration
from services.controller.cliente_controller import ClienteController
from services.controller.embalagem_controller import EmbalagemController
from services.controller.cotacao_controller import CotacaoController
from services.controller.company_controller import CompanyController
from services.controller.cotacao_consulta_controller import CotacaoConsultaController
import logging
import os

# Configure logger
logging.basicConfig(level=logging.INFO if CurrentConfig.DEBUG else logging.WARNING,
                    format='%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s') # Added format
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(CurrentConfig) # Load configuration from object

# Initialize SocketIO
socketio = SocketIO(app, async_mode='eventlet')

# Definition of carrier mapping (Internal Code -> Display Name)
# Ensure the keys (BAU, TNT, etc.) match the 'Transportadora' identifier
# returned by your carrier service functions and used in db.quote_responses.
TRANSPORTADORA_MAP = {
    'BAU': 'Bauer',           # SSW
    'TNT': 'TNT Mercúrio',
    'EPC': 'Princesa dos Campos',
    'EUC': 'Eucatur',         # SSW
    'RTE': 'Rodonaves',
    'PEP': 'Zanotelli',       # SSW
    'BTU': 'Braspress',
    'ESM': 'Exp. São Miguel',
    # Add more mappings as needed, matching the internal codes
}

# Instantiate controllers (Stateless controllers can be global)
cotacao_consulta_controller = CotacaoConsultaController()
company_controller = CompanyController() # Instantiated once if stateless

# Route for the home page
@app.route('/')
def index():
    return render_template('index.html', now=datetime.datetime.now)

# Route for client data input
@app.route('/client', methods=['GET', 'POST'])
def client():
    if request.method == 'POST':
        identifier = request.form.get('identifier')
        invoice_value_str = request.form.get('invoice_value')

        # Basic Server-side validation
        if not identifier or not invoice_value_str:
            error = "Por favor, preencha todos os campos."
            return render_template('client.html', error=error, now=datetime.datetime.now)
        
        try:
            # Clean and convert invoice value
            invoice_value = float(invoice_value_str.replace('R$', '').replace('.', '').replace(',', '.').strip())
            if invoice_value <= 0:
                raise ValueError("Valor da mercadoria deve ser positivo.")
        except ValueError as e:
            error = f"Valor da mercadoria inválido: {e}"
            logger.warning(f"Invalid invoice value submitted: {invoice_value_str}")
            return render_template('client.html', error=error, now=datetime.datetime.now)

        # Instantiate controller for this request
        cliente_controller = ClienteController()
        try:
            client_data, invoice_val = cliente_controller.coletar_dados_cliente(identifier, invoice_value)
            
            if client_data:
                # Store client data in session
                session['client_data'] = client_data
                session['invoice_value'] = invoice_val
                # Clear previous package data
                session.pop('packages_data', None)
                logger.info(f"Client data collected for identifier: {identifier}")
                return redirect(url_for('packages'))
            else:
                error = "Cliente não encontrado ou erro ao obter dados. Verifique o código ou CNPJ."
                logger.warning(f"Client not found or error for identifier: {identifier}")
                return render_template('client.html', error=error, now=datetime.datetime.now)
        except Exception as e:
            logger.exception(f"Error processing client data for identifier {identifier}: {e}")
            error = "Ocorreu um erro interno ao processar os dados do cliente."
            return render_template('client.html', error=error, now=datetime.datetime.now)

    return render_template('client.html', now=datetime.datetime.now)

# Route for package management
@app.route('/packages', methods=['GET', 'POST'])
def packages():
    if 'client_data' not in session:
        logger.warning("Access to /packages without client_data in session. Redirecting.")
        return redirect(url_for('client'))

    if request.method == 'POST':
        packages_data = request.get_json()
        if not packages_data or not isinstance(packages_data, list):
             logger.error("Invalid package data received.")
             return jsonify({'error': 'Dados de embalagem inválidos.'}), 400

        # Instantiate controller for this request
        embalagem_controller = EmbalagemController()
        try:
            processed_packages = embalagem_controller.coletar_dados_embalagens(packages_data)
            # Store package data in session
            session['packages_data'] = processed_packages
            logger.info("Package data processed and stored in session.")
            return jsonify({'redirect': url_for('quotations')})
        except ValueError as e:
             logger.error(f"Error processing packages: {e}")
             return jsonify({'error': str(e)}), 400
        except Exception as e:
            logger.exception(f"Unexpected error processing packages: {e}")
            return jsonify({'error': 'Erro interno ao processar embalagens.'}), 500
            
    # GET Request
    # Instantiate controller to get predefined packages
    embalagem_controller = EmbalagemController()
    return render_template('packages.html',
                           predefined_packages=embalagem_controller.get_predefined_packages(),
                           client_data=session['client_data'],
                           now=datetime.datetime.now)

# Route to display quotations (placeholder page, real work done via SocketIO)
@app.route('/quotations', methods=['GET'])
def quotations():
    if 'client_data' not in session or 'packages_data' not in session:
        logger.warning("Access to /quotations without client/package data. Redirecting.")
        return redirect(url_for('client'))

    # Get data from session
    client_data = session['client_data']
    packages_data = session['packages_data']
    invoice_value = session['invoice_value']

    # Protocol is generated when quoting starts (in SocketIO handler)
    # Removed protocol generation from here

    return render_template('quotations.html',
                           client_data=client_data,
                           packages=packages_data['pack'],
                           # protocolo=protocolo, # Removed - will be shown dynamically
                           total_weight=packages_data['total_weight'],
                           total_volume=packages_data['total_volume'],
                           total_packages=packages_data['total_packages'],
                           invoice_value=invoice_value)

# Routes for quote consultation
@app.route('/consultations', methods=['GET'])
def consultations():
    return cotacao_consulta_controller.show_consultations()

@app.route('/consultations/filter', methods=['GET'])
def consultations_filter():
    return cotacao_consulta_controller.filter_consultations()

@app.route('/consultations/<int:quote_id>', methods=['GET'])
def quote_details(quote_id):
    return cotacao_consulta_controller.show_quote_details(quote_id)

# === SocketIO Event Handlers ===

@socketio.on('start_quotation')
def handle_start_quotation():
    """Handles the client request to start the quotation process."""
    room = request.sid # Use session ID as the room
    join_room(room)
    logger.info(f"SocketIO client {room} connected and joined room.")
    
    # Instantiate controller for this request
    cotacao_controller = CotacaoController()
    
    client_data = session.get('client_data')
    packages_data = session.get('packages_data')
    invoice_value = session.get('invoice_value')
    
    if not all([client_data, packages_data, invoice_value]):
        error_msg = "Dados de cliente, embalagem ou valor da nota ausentes na sessão."
        logger.error(f"{error_msg} for SID {room}")
        emit('quotation_error', {'error': error_msg}, room=room)
        return

    try:
        # Prepare data needed for quotation APIs (excluding protocol for now)
        cotacao_base_data = cotacao_controller.obter_dados_base_para_cotacao(
            client_data,
            packages_data,
            invoice_value
        )
        if not cotacao_base_data:
             emit('quotation_error', {'error': 'Falha ao preparar dados para cotação.'}, room=room)
             return
             
        # Start background task to process quotations
        logger.info(f"Starting background task for quotation processing for SID {room}.")
        socketio.start_background_task(target=process_quotations, cotacao_base_data=cotacao_base_data, room=room)

    except Exception as e:
        logger.exception(f"Error initiating quotation process for SID {room}: {e}")
        emit('quotation_error', {'error': 'Erro interno ao iniciar o processo de cotação.'}, room=room)

def process_quotations(cotacao_base_data, room):
    """Background task to request quotes from carriers and emit results."""
    logger.info(f"Background task started for room {room}.")
    
    # Instantiate controller for this task
    cotacao_controller = CotacaoController()
    
    try:
        # 1. Generate Protocol *HERE* before saving
        protocolo = cotacao_controller.gerar_protocolo()
        cotacao_data_final = {**cotacao_base_data, "protocolo": protocolo}
        logger.info(f"Generated Protocol {protocolo} for room {room}.")
        
        # Emit the protocol number to the client
        socketio.emit('protocol_generated', {'protocolo': protocolo}, room=room)

        # 2. Save initial quote data to DB
        quote_id = cotacao_controller.salvar_cotacao_inicial(cotacao_data_final)
        logger.info(f"Initial quote saved to DB with ID: {quote_id}, Protocol: {protocolo} for room {room}")

        # 3. Define callback for emitting results
        def emit_new_quotation(cotacao_result):
            if not cotacao_result or not isinstance(cotacao_result, dict):
                logger.warning(f"Invalid cotacao_result received in callback for room {room}: {cotacao_result}")
                return
                
            transportadora_code = cotacao_result.get('Transportadora') # Internal code (e.g., 'BTU')
            if not transportadora_code:
                 logger.warning(f"Cotacao result missing 'Transportadora' key for room {room}: {cotacao_result}")
                 return

            # Map internal code to display name
            transportadora_name = TRANSPORTADORA_MAP.get(transportadora_code, transportadora_code) # Fallback to code if not mapped
            cotacao_result['Transportadora'] = transportadora_name # Update for display

            # Simple validity check (can be enhanced)
            frete = cotacao_result.get('frete')
            is_valid = frete is not None and frete != '-' and float(frete) > 0

            if not is_valid:
                # Standardize fields for invalid/error quotes
                cotacao_result['modal'] = '-'
                cotacao_result['frete'] = '-'
                cotacao_result['prazo'] = '-'
                cotacao_result['cotacao'] = '-'
                # Keep the error message if present
            
            # Emit the processed quotation via SocketIO
            socketio.emit('new_quotation', {'cotacao': cotacao_result}, room=room)
            logger.debug(f"Emitted quotation to room {room}: {cotacao_result}")

        # 4. Request quotes from carriers concurrently
        cotacao_controller.solicitar_cotacoes(quote_id, cotacao_data_final, emit_new_quotation)
        
        # 5. Emit completion event
        socketio.emit('quotations_complete', {}, room=room)
        logger.info(f"Quotation process completed for room {room} (Protocol: {protocolo}).")

    except Exception as e:
        logger.exception(f"Error during background quotation processing for room {room}: {e}")
        socketio.emit('quotation_error', {'error': 'Erro interno durante o processamento das cotações.'}, room=room)

if __name__ == '__main__':
    # Use host/port from config or environment variables
    host = os.environ.get('FLASK_RUN_HOST', '10.1.5.2') # Default from original code
    port = int(os.environ.get('FLASK_RUN_PORT', '5001')) # Default from original code
    logger.info(f"Starting Flask-SocketIO server on {host}:{port} with debug={CurrentConfig.DEBUG}")
    socketio.run(app, host=host, port=port, debug=CurrentConfig.DEBUG)
