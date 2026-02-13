/**
 * SynthoCAD Frontend Application
 * Main application logic and UI handlers
 */

// State management
const state = {
    currentTab: 'generate',
    currentModel: null,
    extractedParams: {},
    currentFilename: null
};

// Example prompts
const examples = {
    cylinder: "Create a cylinder with 20mm diameter and 50mm height",
    box: "Create a rectangular box with dimensions 50mm x 30mm x 10mm",
    tube: "Create a hollow tube with 30mm outer diameter, 5mm wall thickness, and 40mm height",
    bracket: "Create an L-shaped bracket with 50mm x 50mm legs, 10mm thick, and 5mm fillet radius"
};

// ========== Initialization ==========

document.addEventListener('DOMContentLoaded', () => {
    initializeTabs();
    initializeGenerateTab();
    initializeModelsTab();
    initializeParametersTab();
    initializeCleanupTab();
    initializeMonitoringTab();
    checkBackendStatus();
    checkFreeCADStatus();
});

// ========== Tab Management ==========

function initializeTabs() {
    const tabs = document.querySelectorAll('.tab');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const tabName = tab.dataset.tab;
            switchTab(tabName);
        });
    });
}

function switchTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');

    // Update tab content
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
    document.getElementById(`${tabName}-tab`).classList.add('active');

    state.currentTab = tabName;

    // Load data for specific tabs
    if (tabName === 'models') {
        loadModels();
    } else if (tabName === 'cleanup') {
        loadStorageStats();
    } else if (tabName === 'monitoring') {
        loadMonitoringStats();
    }
}

// ========== Generate Tab ==========

function initializeGenerateTab() {
    // Validate Prompt
    document.getElementById('validate-prompt-btn').addEventListener('click', async () => {
        const prompt = document.getElementById('prompt-input').value.trim();
        if (!prompt) {
            showToast('Please enter a prompt', 'error');
            return;
        }

        showLoading('validate-prompt-btn');
        try {
            const result = await api.validatePrompt(prompt);
            showResult('prompt-result', result, 'success');
            showToast('Prompt is valid!', 'success');
        } catch (error) {
            showResult('prompt-result', { error: error.message }, 'error');
            showToast(`Validation failed: ${error.message}`, 'error');
        } finally {
            hideLoading('validate-prompt-btn');
        }
    });

    // Generate from Prompt
    document.getElementById('generate-from-prompt-btn').addEventListener('click', async () => {
        const prompt = document.getElementById('prompt-input').value.trim();
        const openFreecad = document.getElementById('open-freecad-prompt').checked;

        if (!prompt) {
            showToast('Please enter a prompt', 'error');
            return;
        }

        showLoading('generate-from-prompt-btn');
        try {
            const result = await api.generateFromPrompt(prompt, openFreecad);
            showResult('prompt-result', result, 'success');
            showToast('Model generated successfully!', 'success');
            
            // Extract filename for parameters tab
            if (result.py_file) {
                const filename = result.py_file.split('/').pop().split('\\').pop();
                document.getElementById('param-file-input').value = filename;
            }
        } catch (error) {
            showResult('prompt-result', { error: error.message }, 'error');
            showToast(`Generation failed: ${error.message}`, 'error');
        } finally {
            hideLoading('generate-from-prompt-btn');
        }
    });

    // Generate from JSON
    document.getElementById('generate-from-json-btn').addEventListener('click', async () => {
        const jsonText = document.getElementById('json-input').value.trim();
        const outputName = document.getElementById('output-name-input').value.trim();
        const openFreecad = document.getElementById('open-freecad-json').checked;

        if (!jsonText) {
            showToast('Please enter JSON data', 'error');
            return;
        }

        let jsonData;
        try {
            jsonData = JSON.parse(jsonText);
        } catch (error) {
            showToast('Invalid JSON format', 'error');
            return;
        }

        showLoading('generate-from-json-btn');
        try {
            const result = await api.generateFromJSON(jsonData, outputName || null, openFreecad);
            showResult('json-result', result, 'success');
            showToast('Model generated successfully!', 'success');
            
            if (result.py_file) {
                const filename = result.py_file.split('/').pop().split('\\').pop();
                document.getElementById('param-file-input').value = filename;
            }
        } catch (error) {
            showResult('json-result', { error: error.message }, 'error');
            showToast(`Generation failed: ${error.message}`, 'error');
        } finally {
            hideLoading('generate-from-json-btn');
        }
    });

    // Load JSON File
    document.getElementById('load-json-file-btn').addEventListener('click', () => {
        document.getElementById('json-file-input').click();
    });

    document.getElementById('json-file-input').addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = (event) => {
                document.getElementById('json-input').value = event.target.result;
                showToast('JSON file loaded', 'success');
            };
            reader.readAsText(file);
        }
    });

    // Example buttons
    document.querySelectorAll('.example-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const example = btn.dataset.example;
            document.getElementById('prompt-input').value = examples[example];
        });
    });
}

// ========== Models Tab ==========

function initializeModelsTab() {
    document.getElementById('refresh-models-btn').addEventListener('click', loadModels);
    
    // FreeCAD controls
    document.getElementById('open-freecad-btn').addEventListener('click', async () => {
        const stepFile = document.getElementById('step-file-input').value.trim();
        if (!stepFile) {
            showToast('Please enter a STEP file name', 'error');
            return;
        }

        showLoading('open-freecad-btn');
        try {
            const result = await api.openInFreeCAD(stepFile);
            showResult('freecad-result', result, 'success');
            showToast('Opened in FreeCAD', 'success');
        } catch (error) {
            showResult('freecad-result', { error: error.message }, 'error');
            showToast(`Failed to open FreeCAD: ${error.message}`, 'error');
        } finally {
            hideLoading('open-freecad-btn');
        }
    });

    document.getElementById('reload-freecad-btn').addEventListener('click', async () => {
        const stepFile = document.getElementById('step-file-input').value.trim();
        if (!stepFile) {
            showToast('Please enter a STEP file name', 'error');
            return;
        }

        showLoading('reload-freecad-btn');
        try {
            const result = await api.reloadInFreeCAD(stepFile);
            showResult('freecad-result', result, 'success');
            showToast('Reloaded in FreeCAD', 'success');
        } catch (error) {
            showResult('freecad-result', { error: error.message }, 'error');
            showToast(`Failed to reload: ${error.message}`, 'error');
        } finally {
            hideLoading('reload-freecad-btn');
        }
    });
}

async function loadModels() {
    const container = document.getElementById('models-list');
    container.innerHTML = '<div class="loading">Loading models...</div>';

    try {
        const stats = await api.getStorageStats();
        const models = extractModelsFromStats(stats);
        
        if (models.length === 0) {
            container.innerHTML = '<div class="empty-state">No models found. Generate your first model!</div>';
            return;
        }

        container.innerHTML = models.map(model => `
            <div class="model-card">
                <div class="model-icon">📦</div>
                <div class="model-info">
                    <div class="model-name">${model.name}</div>
                    <div class="model-meta">
                        ${model.hasJson ? '📄 JSON' : ''} 
                        ${model.hasPy ? '🐍 Python' : ''} 
                        ${model.hasStep ? '🔧 STEP' : ''}
                    </div>
                </div>
                <div class="model-actions">
                    <button class="btn-icon" onclick="openModelInFreeCAD('${model.name}')" title="Open in FreeCAD">
                        👁️
                    </button>
                    <button class="btn-icon" onclick="editModelParameters('${model.name}')" title="Edit Parameters">
                        ⚙️
                    </button>
                    <button class="btn-icon btn-danger" onclick="deleteModelPrompt('${model.name}')" title="Delete">
                        🗑️
                    </button>
                </div>
            </div>
        `).join('');
    } catch (error) {
        container.innerHTML = `<div class="error-state">Failed to load models: ${error.message}</div>`;
    }
}

function extractModelsFromStats(stats) {
    // This is a simplified version - in reality you'd need directory listing API
    const models = [];
    // Placeholder implementation
    return models;
}

// Model action functions (global scope for onclick)
window.openModelInFreeCAD = async (modelName) => {
    try {
        await api.openInFreeCAD(`${modelName}.step`);
        showToast(`Opening ${modelName} in FreeCAD`, 'success');
    } catch (error) {
        showToast(`Failed to open: ${error.message}`, 'error');
    }
};

window.editModelParameters = (modelName) => {
    document.getElementById('param-file-input').value = `${modelName}_generated.py`;
    switchTab('parameters');
    document.getElementById('extract-params-btn').click();
};

window.deleteModelPrompt = async (modelName) => {
    if (confirm(`Delete model "${modelName}" and all related files?`)) {
        try {
            await api.deleteModel(modelName, false);
            showToast(`Deleted ${modelName}`, 'success');
            loadModels();
        } catch (error) {
            showToast(`Failed to delete: ${error.message}`, 'error');
        }
    }
};

// ========== Parameters Tab ==========

function initializeParametersTab() {
    document.getElementById('extract-params-btn').addEventListener('click', async () => {
        const filename = document.getElementById('param-file-input').value.trim();
        if (!filename) {
            showToast('Please enter a Python file name', 'error');
            return;
        }

        showLoading('extract-params-btn');
        try {
            const result = await api.extractParameters(filename);
            state.extractedParams = result.parameters || [];
            state.currentFilename = filename;
            displayParameters(result);
            showToast(`Extracted ${result.total_count} parameters`, 'success');
        } catch (error) {
            showResult('param-result', { error: error.message }, 'error');
            showToast(`Failed to extract parameters: ${error.message}`, 'error');
        } finally {
            hideLoading('extract-params-btn');
        }
    });

    document.getElementById('update-params-btn').addEventListener('click', async () => {
        const filename = state.currentFilename;
        if (!filename) {
            showToast('Please extract parameters first', 'error');
            return;
        }

        const parameters = getUpdatedParameters();
        if (Object.keys(parameters).length === 0) {
            showToast('No parameters changed', 'info');
            return;
        }

        showLoading('update-params-btn');
        try {
            const result = await api.updateParameters(filename, parameters);
            showResult('param-result', result, 'success');
            showToast('Parameters updated', 'success');
        } catch (error) {
            showResult('param-result', { error: error.message }, 'error');
            showToast(`Update failed: ${error.message}`, 'error');
        } finally {
            hideLoading('update-params-btn');
        }
    });

    document.getElementById('regenerate-btn').addEventListener('click', async () => {
        const filename = state.currentFilename;
        if (!filename) {
            showToast('Please extract parameters first', 'error');
            return;
        }

        const parameters = getUpdatedParameters();
        if (Object.keys(parameters).length === 0) {
            showToast('No parameters changed', 'info');
            return;
        }

        const openFreecad = document.getElementById('open-freecad-regen').checked;

        showLoading('regenerate-btn');
        try {
            const result = await api.regenerateWithParameters(filename, parameters, openFreecad);
            showResult('param-result', result, 'success');
            showToast('Model regenerated successfully!', 'success');
        } catch (error) {
            showResult('param-result', { error: error.message }, 'error');
            showToast(`Regeneration failed: ${error.message}`, 'error');
        } finally {
            hideLoading('regenerate-btn');
        }
    });
}

function displayParameters(result) {
    const container = document.getElementById('parameters-container');
    const listContainer = document.getElementById('parameters-list');
    const countBadge = document.getElementById('param-count');

    container.style.display = 'block';
    countBadge.textContent = result.total_count;

    if (!result.parameters || result.parameters.length === 0) {
        listContainer.innerHTML = '<div class="empty-state">No parameters found</div>';
        return;
    }

    listContainer.innerHTML = result.parameters.map((param, index) => `
        <div class="param-item">
            <div class="param-info">
                <div class="param-name">${param.name}</div>
                <div class="param-meta">
                    Type: ${param.type} | 
                    Default: ${param.value} | 
                    Line: ${param.line}
                </div>
            </div>
            <div class="param-input">
                <input 
                    type="number" 
                    step="any"
                    id="param-${index}" 
                    data-param-name="${param.name}"
                    value="${param.value}"
                    class="param-value-input"
                >
            </div>
        </div>
    `).join('');
}

function getUpdatedParameters() {
    const parameters = {};
    const inputs = document.querySelectorAll('.param-value-input');
    
    inputs.forEach((input, index) => {
        const paramName = input.dataset.paramName;
        const newValue = parseFloat(input.value);
        const originalValue = state.extractedParams[index]?.value;

        if (newValue !== originalValue && !isNaN(newValue)) {
            parameters[paramName] = newValue;
        }
    });

    return parameters;
}

// ========== Cleanup Tab ==========

function initializeCleanupTab() {
    document.getElementById('refresh-stats-btn').addEventListener('click', loadStorageStats);
    
    document.getElementById('cleanup-by-age-btn').addEventListener('click', async () => {
        const maxAge = parseInt(document.getElementById('cleanup-age').value);
        const dryRun = document.getElementById('cleanup-dry-run').checked;

        if (isNaN(maxAge) || maxAge < 1) {
            showToast('Please enter a valid age', 'error');
            return;
        }

        showLoading('cleanup-by-age-btn');
        try {
            const result = await api.cleanupByAge(maxAge, 'all', dryRun);
            showResult('cleanup-result', result, 'success');
            showToast(dryRun ? 'Dry run completed' : 'Cleanup completed', 'success');
            loadStorageStats();
        } catch (error) {
            showResult('cleanup-result', { error: error.message }, 'error');
            showToast(`Cleanup failed: ${error.message}`, 'error');
        } finally {
            hideLoading('cleanup-by-age-btn');
        }
    });

    document.getElementById('cleanup-by-count-btn').addEventListener('click', async () => {
        const maxCount = parseInt(document.getElementById('cleanup-count').value);
        const dryRun = document.getElementById('cleanup-dry-run').checked;

        if (isNaN(maxCount) || maxCount < 1) {
            showToast('Please enter a valid count', 'error');
            return;
        }

        showLoading('cleanup-by-count-btn');
        try {
            const result = await api.cleanupByCount(maxCount, 'all', dryRun);
            showResult('cleanup-result', result, 'success');
            showToast(dryRun ? 'Dry run completed' : 'Cleanup completed', 'success');
            loadStorageStats();
        } catch (error) {
            showResult('cleanup-result', { error: error.message }, 'error');
            showToast(`Cleanup failed: ${error.message}`, 'error');
        } finally {
            hideLoading('cleanup-by-count-btn');
        }
    });

    document.getElementById('cleanup-all-btn').addEventListener('click', async () => {
        const maxAge = parseInt(document.getElementById('cleanup-age').value);
        const maxCount = parseInt(document.getElementById('cleanup-count').value);
        const dryRun = document.getElementById('cleanup-dry-run').checked;

        if (!dryRun && !confirm('Are you sure you want to run full cleanup?')) {
            return;
        }

        showLoading('cleanup-all-btn');
        try {
            const result = await api.cleanup(maxAge, maxCount, dryRun);
            showResult('cleanup-result', result, 'success');
            showToast(dryRun ? 'Dry run completed' : 'Full cleanup completed', 'success');
            loadStorageStats();
        } catch (error) {
            showResult('cleanup-result', { error: error.message }, 'error');
            showToast(`Cleanup failed: ${error.message}`, 'error');
        } finally {
            hideLoading('cleanup-all-btn');
        }
    });

    document.getElementById('delete-model-btn').addEventListener('click', async () => {
        const modelName = document.getElementById('delete-model-name').value.trim();
        if (!modelName) {
            showToast('Please enter a model name', 'error');
            return;
        }

        if (!confirm(`Delete model "${modelName}"?`)) {
            return;
        }

        showLoading('delete-model-btn');
        try {
            const result = await api.deleteModel(modelName, false);
            showResult('delete-result', result, 'success');
            showToast(`Deleted ${modelName}`, 'success');
            document.getElementById('delete-model-name').value = '';
            loadStorageStats();
        } catch (error) {
            showResult('delete-result', { error: error.message }, 'error');
            showToast(`Delete failed: ${error.message}`, 'error');
        } finally {
            hideLoading('delete-model-btn');
        }
    });
}

async function loadStorageStats() {
    try {
        const stats = await api.getStorageStats();
        
        document.getElementById('total-files').textContent = stats.total_files || 0;
        document.getElementById('total-size').textContent = `${stats.total_size_mb || 0} MB`;
        
        if (stats.by_type) {
            document.getElementById('json-files').textContent = stats.by_type.json?.file_count || 0;
            document.getElementById('py-files').textContent = stats.by_type.py?.file_count || 0;
            document.getElementById('step-files').textContent = stats.by_type.step?.file_count || 0;
        }
    } catch (error) {
        showToast(`Failed to load stats: ${error.message}`, 'error');
    }
}

// ========== Monitoring Tab ==========

function initializeMonitoringTab() {
    document.getElementById('refresh-monitoring-btn').addEventListener('click', loadMonitoringStats);
    
    document.getElementById('operation-filter').addEventListener('change', (e) => {
        loadRetryHistory(e.target.value);
    });
}

async function loadMonitoringStats() {
    try {
        const result = await api.getRetryStats();
        const stats = result.statistics;

        document.getElementById('success-rate').textContent = `${stats.success_rate || 0}%`;
        document.getElementById('total-operations').textContent = stats.total_operations || 0;
        document.getElementById('avg-attempts').textContent = stats.average_attempts || 0;
        document.getElementById('failed-ops').textContent = stats.failed_operations || 0;

        displayRetryHistory(result.history || []);
    } catch (error) {
        showToast(`Failed to load monitoring stats: ${error.message}`, 'error');
    }
}

async function loadRetryHistory(operation = '') {
    try {
        const result = await api.getRetryStats(operation || null);
        displayRetryHistory(result.history || []);
    } catch (error) {
        showToast(`Failed to load history: ${error.message}`, 'error');
    }
}

function displayRetryHistory(history) {
    const container = document.getElementById('retry-history');

    if (history.length === 0) {
        container.innerHTML = '<div class="empty-state">No retry history</div>';
        return;
    }

    container.innerHTML = history.slice(0, 20).map(record => `
        <div class="history-item ${record.success ? 'success' : 'failed'}">
            <div class="history-icon">${record.success ? '✅' : '❌'}</div>
            <div class="history-details">
                <div class="history-operation">${record.operation}</div>
                <div class="history-meta">
                    Attempt ${record.attempt} | ${new Date(record.timestamp).toLocaleString()}
                    ${record.elapsed_seconds ? ` | ${record.elapsed_seconds.toFixed(2)}s` : ''}
                </div>
                ${record.error ? `<div class="history-error">${record.error}</div>` : ''}
            </div>
        </div>
    `).join('');
}

// ========== Status Checks ==========

async function checkBackendStatus() {
    const statusEl = document.getElementById('api-status');
    try {
        await api.healthCheck();
        statusEl.classList.add('online');
        statusEl.querySelector('.status-label').textContent = 'Backend: Online';
    } catch (error) {
        statusEl.classList.add('offline');
        statusEl.querySelector('.status-label').textContent = 'Backend: Offline';
    }
}

async function checkFreeCADStatus() {
    const statusEl = document.getElementById('freecad-status');
    try {
        const result = await api.checkFreeCAD();
        if (result.installed) {
            statusEl.classList.add('online');
            statusEl.querySelector('.status-label').textContent = 'FreeCAD: Ready';
        } else {
            statusEl.classList.add('offline');
            statusEl.querySelector('.status-label').textContent = 'FreeCAD: Not Found';
        }
    } catch (error) {
        statusEl.classList.add('offline');
        statusEl.querySelector('.status-label').textContent = 'FreeCAD: Unknown';
    }
}

// ========== UI Helpers ==========

function showResult(elementId, data, type = 'info') {
    const element = document.getElementById(elementId);
    element.style.display = 'block';
    element.className = `result-box ${type}`;
    element.innerHTML = `<pre>${JSON.stringify(data, null, 2)}</pre>`;
}

function showLoading(buttonId) {
    const button = document.getElementById(buttonId);
    button.dataset.originalText = button.textContent;
    button.textContent = 'Loading...';
    button.disabled = true;
}

function hideLoading(buttonId) {
    const button = document.getElementById(buttonId);
    button.textContent = button.dataset.originalText || button.textContent;
    button.disabled = false;
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    const icons = {
        success: '✅',
        error: '❌',
        warning: '⚠️',
        info: 'ℹ️'
    };
    
    toast.innerHTML = `
        <span class="toast-icon">${icons[type] || icons.info}</span>
        <span class="toast-message">${message}</span>
    `;
    
    container.appendChild(toast);
    
    setTimeout(() => toast.classList.add('show'), 10);
    
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}
