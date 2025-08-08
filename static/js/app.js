// PRISM Analytics - ISRC Metadata Analyzer Frontend
class ISRCAnalyzer {
    constructor() {
        this.baseUrl = window.location.origin;
        this.init();
    }

    init() {
        this.bindEvents();
        console.log('🎵 PRISM Analytics - ISRC Metadata Analyzer initialized');
    }

    bindEvents() {
        // ISRC Analysis Form
        const analysisForm = document.getElementById('isrc-analysis-form');
        if (analysisForm) {
            analysisForm.addEventListener('submit', (e) => this.handleISRCAnalysis(e));
        }

        // Export buttons (will be added dynamically)
        this.bindExportEvents();
    }

    bindExportEvents() {
        document.querySelectorAll('.export-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.handleExport(e));
        });
    }

    async handleISRCAnalysis(event) {
        event.preventDefault();
        
        const formData = new FormData(event.target);
        const isrc = formData.get('isrc').trim().toUpperCase();
        const comprehensive = formData.get('comprehensive') === 'on';
        
        if (!this.validateISRC(isrc)) {
            this.showError('Please enter a valid ISRC format (e.g., USRC17607839)');
            return;
        }
        
        this.showLoading('Analyzing ISRC metadata...');
        this.clearError();
        
        try {
            const response = await fetch('/api/analyze-isrc-enhanced', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    isrc: isrc,
                    comprehensive: comprehensive,
                    include_lyrics: true,
                    include_credits: true,
                    include_technical: true
                })
            });

            const data = await response.json();
            
            if (response.ok) {
                this.displayResults(data);
                this.showSuccess(`Successfully analyzed ISRC: ${isrc}`);
            } else {
                this.showError(data.error || 'Analysis failed');
            }
        } catch (error) {
            this.showError('Network error: ' + error.message);
        } finally {
            this.hideLoading();
        }
    }

    validateISRC(isrc) {
        // ISRC format: 2 letters + 3 alphanumeric + 7 digits
        const isrcRegex = /^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$/;
        return isrcRegex.test(isrc);
    }

    displayResults(data) {
        const resultsContainer = document.getElementById('results');
        if (!resultsContainer) return;

        const confidence = data.confidence_score || 0;
        const confidenceColor = confidence >= 80 ? '#28a745' : confidence >= 60 ? '#ffc107' : '#dc3545';

        resultsContainer.innerHTML = `
            <div class="card">
                <h3>Analysis Results for ${data.isrc}</h3>
                <div class="metadata-summary">
                    <p><strong>Track:</strong> ${data.metadata.title || 'Unknown'}</p>
                    <p><strong>Artist:</strong> ${data.metadata.artist || 'Unknown'}</p>
                    <p><strong>Album:</strong> ${data.metadata.album || 'Unknown'}</p>
                    <p><strong>Confidence Score:</strong> 
                        <span style="color: ${confidenceColor}; font-weight: bold;">${confidence}%</span>
                    </p>
                    <p><strong>Status:</strong> <span style="color: #28a745;">${data.status}</span></p>
                </div>
                <div class="export-options">
                    <button class="export-btn" data-format="json" data-isrc="${data.isrc}">
                        📄 Export JSON
                    </button>
                    <button class="export-btn" data-format="csv" data-isrc="${data.isrc}">
                        📊 Export CSV
                    </button>
                    <button class="export-btn" data-format="pdf" data-isrc="${data.isrc}">
                        📑 Export PDF
                    </button>
                </div>
            </div>
            
            <div class="card">
                <h4>Raw API Response</h4>
                <pre style="background-color: var(--light-gray); padding: 1rem; border-radius: 4px; overflow-x: auto; font-family: var(--font-data); font-size: 12px;">${JSON.stringify(data, null, 2)}</pre>
            </div>
        `;

        // Re-bind export events for new buttons
        this.bindExportEvents();
    }

    async handleExport(event) {
        const format = event.target.dataset.format;
        const isrc = event.target.dataset.isrc;
        
        this.showLoading(`Generating ${format.toUpperCase()} export...`);
        
        try {
            // For now, just simulate export functionality
            await new Promise(resolve => setTimeout(resolve, 1000));
            
            // Create mock data for download
            const mockData = {
                isrc: isrc,
                format: format,
                timestamp: new Date().toISOString(),
                data: 'Mock export data - full implementation pending'
            };
            
            this.downloadMockFile(mockData, format, isrc);
            this.showSuccess(`${format.toUpperCase()} export generated successfully!`);
        } catch (error) {
            this.showError('Export error: ' + error.message);
        } finally {
            this.hideLoading();
        }
    }

    downloadMockFile(data, format, isrc) {
        const content = format === 'json' ? 
            JSON.stringify(data, null, 2) : 
            `ISRC Meta Data Export\nISRC: ${isrc}\nFormat: ${format}\nTimestamp: ${data.timestamp}`;
        
        const blob = new Blob([content], { type: 'text/plain' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `isrc-metadata-${isrc}.${format}`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
    }

    showLoading(message = 'Processing...') {
        const loadingEl = document.getElementById('loading');
        if (loadingEl) {
            loadingEl.innerHTML = `
                <div class="loading"></div>
                <span>${message}</span>
            `;
            loadingEl.style.display = 'block';
        }
    }

    hideLoading() {
        const loadingEl = document.getElementById('loading');
        if (loadingEl) {
            loadingEl.style.display = 'none';
        }
    }

    showError(message) {
        const errorEl = document.getElementById('error');
        if (errorEl) {
            errorEl.innerHTML = `<div class="error-message">${message}</div>`;
            errorEl.style.display = 'block';
        }
    }

    showSuccess(message) {
        const errorEl = document.getElementById('error');
        if (errorEl) {
            errorEl.innerHTML = `<div class="success-message">${message}</div>`;
            errorEl.style.display = 'block';
            
            // Auto-hide success message after 3 seconds
            setTimeout(() => {
                errorEl.style.display = 'none';
            }, 3000);
        }
    }

    clearError() {
        const errorEl = document.getElementById('error');
        if (errorEl) {
            errorEl.style.display = 'none';
        }
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new ISRCAnalyzer();
});