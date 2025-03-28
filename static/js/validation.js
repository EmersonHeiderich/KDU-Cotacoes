// static/js/validation.js

document.addEventListener('DOMContentLoaded', function() {
    const identifierInput = document.getElementById('identifier');
    const invoiceValueInput = document.getElementById('invoice_value');
    const clientForm = document.querySelector('form'); // Assuming there's only one form on the client page

    // --- Helper Functions ---

    // Remove non-numeric characters
    function onlyNumbers(value) {
        return value.replace(/\D/g, '');
    }

    // Format CNPJ (14 digits -> XX.XXX.XXX/XXXX-XX)
    function formatCNPJ(value) {
        const digits = onlyNumbers(value);
        if (digits.length <= 2) return digits;
        if (digits.length <= 5) return `${digits.slice(0, 2)}.${digits.slice(2)}`;
        if (digits.length <= 8) return `${digits.slice(0, 2)}.${digits.slice(2, 5)}.${digits.slice(5)}`;
        if (digits.length <= 12) return `${digits.slice(0, 2)}.${digits.slice(2, 5)}.${digits.slice(5, 8)}/${digits.slice(8)}`;
        return `${digits.slice(0, 2)}.${digits.slice(2, 5)}.${digits.slice(5, 8)}/${digits.slice(8, 12)}-${digits.slice(12, 14)}`;
    }

    // Validate CNPJ using the standard algorithm
    function validateCNPJ(cnpj) {
        const digits = onlyNumbers(cnpj);
        if (digits.length !== 14) return false;
        // Check for known invalid sequences (e.g., 000...0, 111...1)
        if (/^(\d)\1+$/.test(digits)) return false;

        let tamanho = 12;
        let numeros = digits.substring(0, tamanho);
        let digitosVerificadores = digits.substring(tamanho);
        let soma = 0;
        let pos = tamanho - 7;
        for (let i = tamanho; i >= 1; i--) {
            soma += parseInt(numeros.charAt(tamanho - i)) * pos--;
            if (pos < 2) pos = 9;
        }
        let resultado = soma % 11 < 2 ? 0 : 11 - soma % 11;
        if (resultado !== parseInt(digitosVerificadores.charAt(0))) return false;

        tamanho = 13;
        numeros = digits.substring(0, tamanho);
        soma = 0;
        pos = tamanho - 7;
        for (let i = tamanho; i >= 1; i--) {
            soma += parseInt(numeros.charAt(tamanho - i)) * pos--;
            if (pos < 2) pos = 9;
        }
        resultado = soma % 11 < 2 ? 0 : 11 - soma % 11;
        if (resultado !== parseInt(digitosVerificadores.charAt(1))) return false;

        return true;
    }

    // Format input value as BRL currency string
    function formatInvoiceValue(value) {
        const digits = onlyNumbers(value);
        if (!digits) return ''; // Return empty if no digits

        // Convert cents to BRL value
        let number = parseFloat(digits) / 100;
        if (isNaN(number)) return ''; // Handle potential NaN

        // Format using Intl API
        return new Intl.NumberFormat('pt-BR', {
            style: 'currency',
            currency: 'BRL',
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        }).format(number);
    }

    // --- Event Listeners ---

    // Identifier (CNPJ or Code) Input Listener
    if (identifierInput) {
        identifierInput.addEventListener('input', function(e) {
            const originalValue = e.target.value;
            const isPotentiallyCnpj = /[.\/-]/.test(originalValue) || onlyNumbers(originalValue).length > 8; // Heuristic

            if (isPotentiallyCnpj) {
                const cnpjDigits = onlyNumbers(originalValue);
                 if (cnpjDigits.length <= 14) {
                     e.target.value = formatCNPJ(cnpjDigits);
                 } else {
                     // Prevent typing more than 14 digits for CNPJ
                     e.target.value = formatCNPJ(cnpjDigits.slice(0, 14));
                 }

                // Basic validation feedback for CNPJ length
                 if (onlyNumbers(e.target.value).length === 14) {
                     if (validateCNPJ(e.target.value)) {
                         identifierInput.setCustomValidity(""); // Valid
                         identifierInput.classList.remove('is-invalid');
                         identifierInput.classList.add('is-valid');
                     } else {
                         identifierInput.setCustomValidity("CNPJ inválido.");
                         identifierInput.classList.remove('is-valid');
                         identifierInput.classList.add('is-invalid');
                     }
                 } else {
                     identifierInput.setCustomValidity(""); // Reset validity while typing
                     identifierInput.classList.remove('is-valid', 'is-invalid');
                 }
            } else {
                 // If it doesn't look like a CNPJ, treat as code (allow any input for now)
                 identifierInput.setCustomValidity("");
                 identifierInput.classList.remove('is-valid', 'is-invalid');
            }
        });
    }

    // Invoice Value Input Listener (Real-time formatting)
    if (invoiceValueInput) {
        invoiceValueInput.addEventListener('input', function(e) {
            // Store cursor position
            let cursorPosition = e.target.selectionStart;
            let originalLength = e.target.value.length;
            
            let formattedValue = formatInvoiceValue(e.target.value);
            e.target.value = formattedValue;

            // Restore cursor position (adjusting for formatting changes)
            let newLength = formattedValue.length;
            cursorPosition = cursorPosition + (newLength - originalLength);
            // Ensure cursor doesn't go beyond the new length or before 'R$ '
            cursorPosition = Math.max(3, Math.min(newLength, cursorPosition)); 
            e.target.setSelectionRange(cursorPosition, cursorPosition);
        });

        // Add blur listener for final validation (optional)
        invoiceValueInput.addEventListener('blur', function(e){
            const digits = onlyNumbers(e.target.value);
            if (!digits || parseFloat(digits) <= 0) {
                 e.target.setCustomValidity("Valor da mercadoria deve ser positivo.");
                 e.target.classList.add('is-invalid');
            } else {
                 e.target.setCustomValidity("");
                 e.target.classList.remove('is-invalid');
                 e.target.classList.add('is-valid');
            }
        });
    }

    // Form Submission Listener (for overall validation before submit)
    if (clientForm) {
        clientForm.addEventListener('submit', function(event) {
             // Re-validate fields on submit
             const idValue = identifierInput ? identifierInput.value : '';
             const invoiceValue = invoiceValueInput ? invoiceValueInput.value : '';
             let isValid = true;

            // Identifier validation
             if (identifierInput) {
                const cnpjDigits = onlyNumbers(idValue);
                const isPotentiallyCnpj = /[.\/-]/.test(idValue) || cnpjDigits.length > 8;
                if(isPotentiallyCnpj && (cnpjDigits.length !== 14 || !validateCNPJ(idValue))) {
                    identifierInput.setCustomValidity("CNPJ inválido.");
                    identifierInput.classList.add('is-invalid');
                    isValid = false;
                } else if (!idValue.trim()){ // Check if empty
                     identifierInput.setCustomValidity("Campo obrigatório.");
                     identifierInput.classList.add('is-invalid');
                     isValid = false;
                } else {
                     identifierInput.setCustomValidity("");
                     identifierInput.classList.remove('is-invalid');
                }
             }
             
             // Invoice Value validation
             if (invoiceValueInput) {
                 const invoiceDigits = onlyNumbers(invoiceValue);
                 if (!invoiceDigits || parseFloat(invoiceDigits) <= 0) {
                     invoiceValueInput.setCustomValidity("Valor da mercadoria inválido ou não informado.");
                     invoiceValueInput.classList.add('is-invalid');
                     isValid = false;
                 } else {
                      invoiceValueInput.setCustomValidity("");
                      invoiceValueInput.classList.remove('is-invalid');
                 }
             }

             // Prevent submission if not valid
            if (!isValid) {
                event.preventDefault();
                event.stopPropagation();
                // Optionally focus the first invalid field
                const firstInvalid = clientForm.querySelector('.is-invalid');
                if(firstInvalid) firstInvalid.focus();
            } else {
                 // Optional: Disable submit button to prevent double clicks
                 const submitButton = clientForm.querySelector('button[type="submit"]');
                 if (submitButton) submitButton.disabled = true;
            }

            clientForm.classList.add('was-validated'); // Trigger Bootstrap's native feedback styles

        }, false); // Use capture phase = false
    }

}); // End DOMContentLoaded