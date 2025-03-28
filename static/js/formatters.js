// static/js/formatters.js

// Function to format numbers as Brazilian Real (BRL) currency
function formatBRL(value) {
    if (value === null || value === undefined || isNaN(value)) {
        return '-'; // Return dash for invalid or null values
    }
    // Handle potential string inputs (e.g., from data attributes)
    const numberValue = typeof value === 'string' ? parseFloat(value) : value;
    if (isNaN(numberValue)) {
        return '-';
    }
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(numberValue);
}

// Function to format numbers with Brazilian locale separators (e.g., for weight, volume)
function formatNumber(value, decimalPlaces = 2) {
     if (value === null || value === undefined || isNaN(value)) {
        return '-'; // Return dash for invalid or null values
    }
     const numberValue = typeof value === 'string' ? parseFloat(value) : value;
     if (isNaN(numberValue)) {
        return '-';
    }
    return new Intl.NumberFormat('pt-BR', {
        minimumFractionDigits: decimalPlaces,
        maximumFractionDigits: decimalPlaces
    }).format(numberValue);
}

// Function to format percentages
function formatPercentage(value) {
    if (value === null || value === undefined || isNaN(value)) {
        return '-';
    }
    const numberValue = typeof value === 'string' ? parseFloat(value) : value;
     if (isNaN(numberValue)) {
        return '-';
    }
    // Assuming the value is already in percentage points (e.g., 15.2 for 15.2%)
    return formatNumber(numberValue, 2) + '%';
}

// Apply formatting on DOMContentLoaded
document.addEventListener('DOMContentLoaded', function() {
    console.log("Formatters script loaded."); // Debug log

    // Format Freight values (data-frete attribute or specific class)
    document.querySelectorAll('[data-frete]').forEach(element => {
        const frete = element.getAttribute('data-frete');
        // Use formatBRL which handles potential null/invalid values
        element.textContent = formatBRL(frete);
    });

     // Format Weight values (data-peso attribute or specific class)
    document.querySelectorAll('[data-peso]').forEach(element => {
        const peso = element.getAttribute('data-peso');
        const formattedPeso = formatNumber(peso, 2); // Format with 2 decimal places
        if (formattedPeso !== '-') {
            element.textContent = formattedPeso + ' kg';
        } else {
            element.textContent = '-';
        }
    });

     // Format Volume values (data-volume attribute or specific class)
    document.querySelectorAll('[data-volume]').forEach(element => {
        const volume = element.getAttribute('data-volume');
        const formattedVolume = formatNumber(volume, 4); // Format with 4 decimal places
        if (formattedVolume !== '-') {
             element.textContent = formattedVolume + ' m³';
        } else {
             element.textContent = '-';
        }
    });

    // Format Invoice values (data-valor-nf attribute or specific class)
    document.querySelectorAll('[data-valor-nf]').forEach(element => {
        const valorNf = element.getAttribute('data-valor-nf');
        element.textContent = formatBRL(valorNf);
    });
    
    // Format totals in the summary sections (Quotations page, Details page)
    const totalWeightElement = document.getElementById('total_weight') || document.querySelector('[data-total-weight]');
    if (totalWeightElement) {
        const totalWeight = totalWeightElement.getAttribute('data-total-weight') || totalWeightElement.getAttribute('data-weight'); // Check both potential attributes
        const formattedWeight = formatNumber(totalWeight, 2);
        totalWeightElement.textContent = formattedWeight !== '-' ? formattedWeight + ' kg' : '-';
    }

    const totalVolumeElement = document.getElementById('total_volume') || document.querySelector('[data-total-volume]');
    if (totalVolumeElement) {
        const totalVolume = totalVolumeElement.getAttribute('data-total-volume') || totalVolumeElement.getAttribute('data-volume');
        const formattedVolume = formatNumber(totalVolume, 4);
        totalVolumeElement.textContent = formattedVolume !== '-' ? formattedVolume + ' m³' : '-';
    }

    const totalValueElement = document.getElementById('total_value') || document.querySelector('[data-total-value]');
    if (totalValueElement) {
        const totalValue = totalValueElement.getAttribute('data-total-value') || totalValueElement.getAttribute('data-invoice-value');
         totalValueElement.textContent = formatBRL(totalValue);
    }

    // Add formatting for percentage columns if needed (example)
    // document.querySelectorAll('.frete-percent-cell').forEach(element => {
    //     const percent = element.getAttribute('data-percent');
    //     element.textContent = formatPercentage(percent);
    // });
});

// Expose functions globally if needed by other scripts (optional)
// window.formatBRL = formatBRL;
// window.formatNumber = formatNumber;
// window.formatPercentage = formatPercentage;