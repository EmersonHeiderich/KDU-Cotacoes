// static/js/packages.js

document.addEventListener('DOMContentLoaded', function() {
    // --- DOM Element References ---
    const packageTypeSelect = document.getElementById('package_type');
    const predefinedPackagesSection = document.getElementById('predefined-packages-section'); // Changed ID
    const customPackageFieldsDiv = document.getElementById('custom-package-fields');
    const packagesTableBody = document.querySelector('#packages-table tbody');
    const totalsParagraph = document.getElementById('totals');
    const requestQuotationsBtn = document.getElementById('request-quotations-btn');
    const addPredefinedPackagesBtn = document.getElementById('add-predefined-packages-btn');
    const addCustomPackageBtn = document.getElementById('add-custom-package-btn');
    const predefinedPackagesForm = document.getElementById('predefined-packages-form'); // Form for predefined
    const customPackageForm = document.getElementById('custom-package-form'); // Form for custom

    // --- State ---
    let packages = []; // Array to hold package objects added by the user

    // --- Helper Functions ---

    // Calculate volume for a package object
    function calculateVolume(pkg) {
        if (!pkg || isNaN(pkg.comprimento) || isNaN(pkg.altura) || isNaN(pkg.largura)) {
            return 0;
        }
        return (pkg.comprimento / 100) * (pkg.altura / 100) * (pkg.largura / 100);
    }

    // Update the display of totals (weight and volume)
    function updateTotals() {
        let totalWeight = 0;
        let totalVolume = 0;
        let totalPackageCount = 0; // Total individual packages

        packages.forEach(pkg => {
            const quantity = pkg.quantidade || 0;
            const weight = pkg.peso || 0;
            const volumeUnit = calculateVolume(pkg);

            totalWeight += weight * quantity;
            totalVolume += volumeUnit * quantity;
            totalPackageCount += quantity;
        });

        // Use formatters if available, otherwise simple formatting
        const formattedWeight = typeof formatNumber === 'function' ? formatNumber(totalWeight, 2) : totalWeight.toFixed(2);
        const formattedVolume = typeof formatNumber === 'function' ? formatNumber(totalVolume, 4) : totalVolume.toFixed(4);

        totalsParagraph.textContent = `Peso Total: ${formattedWeight} kg | Volume Total: ${formattedVolume} m³ | Nº Pacotes: ${totalPackageCount}`;

        // Enable/disable quotation button based on whether packages exist
        requestQuotationsBtn.disabled = packages.length === 0;
    }

    // Render the table of selected packages
    function updatePackagesTable() {
        packagesTableBody.innerHTML = ''; // Clear existing rows
        packages.forEach((pkg, index) => {
            const row = document.createElement('tr');

            // Use formatters for display if available
            const formattedPeso = typeof formatNumber === 'function' ? formatNumber(pkg.peso, 2) : pkg.peso.toFixed(2);
            const formattedComp = typeof formatNumber === 'function' ? formatNumber(pkg.comprimento, 0) : pkg.comprimento;
            const formattedAlt = typeof formatNumber === 'function' ? formatNumber(pkg.altura, 0) : pkg.altura;
            const formattedLarg = typeof formatNumber === 'function' ? formatNumber(pkg.largura, 0) : pkg.largura;


            row.innerHTML = `
                <td>${pkg.nome || 'Personalizada'}</td>
                <td>${formattedComp} x ${formattedAlt} x ${formattedLarg}</td>
                <td>${formattedPeso}</td>
                <td>${pkg.quantidade}</td>
                <td>
                    <button type="button" class="btn btn-danger btn-sm remove-package-btn" data-index="${index}">
                        Remover
                    </button>
                </td>
            `;
            packagesTableBody.appendChild(row);
        });

        // Add event listeners to newly created remove buttons
        document.querySelectorAll('.remove-package-btn').forEach(button => {
            button.addEventListener('click', function() {
                const indexToRemove = parseInt(this.getAttribute('data-index'));
                packages.splice(indexToRemove, 1); // Remove package from array
                updatePackagesTable(); // Re-render table
                updateTotals(); // Update totals display
            });
        });
    }

    // Clear input fields in a given form
    function clearFormFields(formElement) {
        if (!formElement) return;
        formElement.reset(); // Resets form elements to default values

        // Special handling for elements not reset by form.reset() if needed
        formElement.querySelectorAll('.new-weight-input').forEach(input => {
            input.disabled = true; // Ensure weight override is disabled
        });
         formElement.querySelectorAll('.alter-weight-select').forEach(select => {
            select.value = 'no'; // Reset select to 'No'
        });
    }

    // --- Event Listeners ---

    // Toggle between Predefined and Custom package forms
    if (packageTypeSelect) {
        packageTypeSelect.addEventListener('change', function() {
            if (this.value === 'predefined') {
                predefinedPackagesSection.style.display = 'block';
                customPackageFieldsDiv.style.display = 'none';
            } else { // 'custom'
                predefinedPackagesSection.style.display = 'none';
                customPackageFieldsDiv.style.display = 'block';
            }
        });
        // Trigger change on load to set initial state
        packageTypeSelect.dispatchEvent(new Event('change'));
    }


    // Enable/disable weight override input based on selection
    document.querySelectorAll('.alter-weight-select').forEach(select => {
        select.addEventListener('change', function() {
            const row = this.closest('tr');
            const newWeightInput = row.querySelector('.new-weight-input');
            if (this.value === 'yes') {
                newWeightInput.disabled = false;
                newWeightInput.required = true; // Make required if altering
            } else {
                newWeightInput.disabled = true;
                newWeightInput.required = false;
                newWeightInput.value = ''; // Clear value
                 newWeightInput.classList.remove('is-invalid'); // Clear validation state
            }
        });
    });

    // Add selected PREDEFINED packages
    if (addPredefinedPackagesBtn) {
        addPredefinedPackagesBtn.addEventListener('click', function() {
            let packagesAdded = false;
            // Select all quantity inputs within the predefined form
            predefinedPackagesForm.querySelectorAll('.quantity-input').forEach(input => {
                const quantity = parseInt(input.value) || 0;
                if (quantity > 0) {
                    const row = input.closest('tr');
                    const packageId = input.getAttribute('data-package-id'); // Use data attribute
                    const predefinedPackage = predefinedPackagesData[packageId]; // Assumes global predefinedPackagesData

                    if (!predefinedPackage) {
                         console.error(`Predefined package data not found for ID: ${packageId}`);
                         return; // Skip if data is missing
                    }

                    let peso = parseFloat(predefinedPackage.peso_padrao); // Use default weight initially
                    let isValid = true;

                    const alterWeightSelect = row.querySelector('.alter-weight-select');
                    if (alterWeightSelect && alterWeightSelect.value === 'yes') {
                        const newWeightInput = row.querySelector('.new-weight-input');
                        const newPeso = parseFloat(newWeightInput.value);
                        if (isNaN(newPeso) || newPeso <= 0) {
                            alert(`Por favor, insira um peso válido para a embalagem ${predefinedPackage.nome}.`);
                            newWeightInput.classList.add('is-invalid'); // Mark as invalid
                             isValid = false;
                        } else {
                            peso = newPeso;
                            newWeightInput.classList.remove('is-invalid');
                        }
                    }
                    
                    if(isValid) {
                        const packageData = {
                            type: 'predefined',
                            package_id: packageId,
                            nome: predefinedPackage.nome,
                            comprimento: parseFloat(predefinedPackage.comprimento),
                            altura: parseFloat(predefinedPackage.altura),
                            largura: parseFloat(predefinedPackage.largura),
                            peso: peso,
                            quantidade: quantity
                        };
                        packages.push(packageData);
                        packagesAdded = true;
                    }
                }
            }); // End forEach quantity input

            if (packagesAdded) {
                updatePackagesTable();
                updateTotals();
                clearFormFields(predefinedPackagesForm); // Clear inputs after adding
            } else {
                 alert("Nenhuma embalagem pré-definida selecionada (quantidade maior que zero).")
            }
        });
    }

    // Add CUSTOM package
    if (addCustomPackageBtn) {
        addCustomPackageBtn.addEventListener('click', function() {
            // Validate custom form inputs
            const nomeInput = document.getElementById('custom_name');
            const comprimentoInput = document.getElementById('custom_length');
            const alturaInput = document.getElementById('custom_height');
            const larguraInput = document.getElementById('custom_width');
            const pesoInput = document.getElementById('custom_weight');
            const quantidadeInput = document.getElementById('quantity_custom');

            const nome = nomeInput.value.trim() || 'Personalizada'; // Default name
            const comprimento = parseFloat(comprimentoInput.value);
            const altura = parseFloat(alturaInput.value);
            const largura = parseFloat(larguraInput.value);
            const peso = parseFloat(pesoInput.value);
            const quantidade = parseInt(quantidadeInput.value) || 1;

            // Simple validation
            let isValid = true;
            [comprimentoInput, alturaInput, larguraInput, pesoInput, quantidadeInput].forEach(input => {
                 const value = parseFloat(input.value);
                 if(isNaN(value) || value <=0) {
                      input.classList.add('is-invalid');
                      isValid = false;
                 } else {
                      input.classList.remove('is-invalid');
                 }
            });
            // Name validation (optional: check if empty)
            // if (!nome) { nomeInput.classList.add('is-invalid'); isValid = false; }
            // else { nomeInput.classList.remove('is-invalid'); }


            if (!isValid) {
                alert('Por favor, preencha todos os campos da embalagem personalizada com valores numéricos positivos.');
                return;
            }

            const packageData = {
                type: 'custom',
                nome: nome,
                comprimento: comprimento,
                altura: altura,
                largura: largura,
                peso: peso,
                quantidade: quantidade
            };

            packages.push(packageData);
            updatePackagesTable();
            updateTotals();
            clearFormFields(customPackageForm); // Clear custom form
        });
    }

    // Submit packages to backend and request quotations
    if (requestQuotationsBtn) {
        requestQuotationsBtn.addEventListener('click', function() {
            if (packages.length === 0) {
                alert('Por favor, adicione ao menos uma embalagem antes de solicitar cotações.');
                return;
            }

            // Disable button to prevent multiple clicks
            requestQuotationsBtn.disabled = true;
            requestQuotationsBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Enviando...';


            fetch(requestQuotationsBtn.dataset.url, { // Get URL from button's data attribute
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    // Add CSRF token header if needed by Flask-WTF or similar
                },
                body: JSON.stringify(packages) // Send the array of package objects
            })
            .then(response => {
                if (!response.ok) {
                    // Try to parse error message from JSON response body
                     return response.json().then(errData => {
                          throw new Error(errData.error || `Erro ${response.status}: ${response.statusText}`);
                     }).catch(() => {
                          // Fallback if response body is not JSON or doesn't have 'error'
                          throw new Error(`Erro ${response.status}: ${response.statusText}`);
                     });
                }
                return response.json();
            })
            .then(data => {
                if (data.redirect) {
                    window.location.href = data.redirect; // Redirect to quotations page
                } else {
                    // Handle unexpected success response without redirect
                    console.warn("Resposta inesperada do servidor:", data);
                    alert("Ocorreu um erro inesperado. Resposta recebida sem redirecionamento.");
                     // Re-enable button
                    requestQuotationsBtn.disabled = false;
                    requestQuotationsBtn.textContent = 'Solicitar Cotações';
                }
            })
            .catch(error => {
                console.error('Erro ao solicitar cotações:', error);
                alert(`Erro ao enviar dados das embalagens: ${error.message}`);
                 // Re-enable button on error
                requestQuotationsBtn.disabled = false;
                requestQuotationsBtn.textContent = 'Solicitar Cotações';
            });
        });
    }

    // Initial setup
    updateTotals(); // Initialize totals display (likely 0)

}); // End DOMContentLoaded