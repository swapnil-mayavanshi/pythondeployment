from flask import Flask, request, render_template_string, send_file, jsonify
import os
import fitz  # PyMuPDF
import pandas as pd
import xml.etree.ElementTree as ET
import pyreadstat
import uuid
import tempfile
import shutil
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create uploads directory
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# ---------------- File Processing Functions ----------------

def replace_text_in_pdf(input_pdf_path, old_text, new_text):
    """Replace text in PDF file"""
    pdf_document = fitz.open(input_pdf_path)
    font_name = "Times-Roman"
    
    for page in pdf_document:
        text_instances = page.search_for(old_text)
        if text_instances:
            original_text_info = page.get_text("dict")['blocks']
            
            for rect in text_instances:
                page.add_redact_annot(rect)
            page.apply_redactions()
            
            for rect in text_instances:
                original_fontsize = 12
                for block in original_text_info:
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            if old_text in span["text"]:
                                original_fontsize = span["size"]
                                break
                        else:
                            continue
                        break
                    else:
                        continue
                    break
                
                font_params = {
                    'fontsize': original_fontsize,
                    'fontname': font_name
                }
                insert_point = fitz.Point(rect.x0, rect.y1 - 2.3)
                page.insert_text(insert_point, new_text, **font_params)
    
    output_path = input_pdf_path.replace('.pdf', '_modified.pdf')
    pdf_document.save(output_path)
    pdf_document.close()
    return output_path

def replace_text_in_csv(input_csv_path, old_text, new_text):
    """Replace text in CSV file"""
    df = pd.read_csv(input_csv_path, dtype=str)
    df = df.applymap(lambda x: x.replace(old_text, new_text) if isinstance(x, str) else x)
    
    output_path = input_csv_path.replace('.csv', '_modified.csv')
    df.to_csv(output_path, index=False)
    return output_path

def replace_text_in_xml(input_xml_path, old_text, new_text):
    """Replace text in XML file"""
    tree = ET.parse(input_xml_path)
    root = tree.getroot()
    
    def replace_in_element(elem):
        if elem.text and old_text in elem.text:
            elem.text = elem.text.replace(old_text, new_text)
        if elem.tail and old_text in elem.tail:
            elem.tail = elem.tail.replace(old_text, new_text)
        for k, v in elem.attrib.items():
            if old_text in v:
                elem.attrib[k] = v.replace(old_text, new_text)
        for child in elem:
            replace_in_element(child)
    
    replace_in_element(root)
    
    output_path = input_xml_path.replace('.xml', '_modified.xml')
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    return output_path

def replace_text_in_xpt(input_xpt_path, old_text, new_text):
    """Replace text in XPT file"""
    df, meta = pyreadstat.read_xport(input_xpt_path)
    df = df.applymap(lambda x: x.replace(old_text, new_text) if isinstance(x, str) else x)
    
    output_path = input_xpt_path.replace('.xpt', '_modified.xpt')
    pyreadstat.write_xport(df, output_path, file_format_version=8, table_name=meta.table_name)
    return output_path

# ---------------- Routes ----------------

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        if 'pdf_file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['pdf_file']
        old_text = request.form.get('old_text', '').strip()
        new_text = request.form.get('new_text', '').strip()
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not old_text:
            return jsonify({'error': 'Text to find is required'}), 400
        
        # Save uploaded file
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
        file.save(file_path)
        
        # Process file based on extension
        ext = os.path.splitext(filename)[1].lower()
        
        if ext == '.pdf':
            output_path = replace_text_in_pdf(file_path, old_text, new_text)
        elif ext == '.csv':
            output_path = replace_text_in_csv(file_path, old_text, new_text)
        elif ext == '.xml':
            output_path = replace_text_in_xml(file_path, old_text, new_text)
        elif ext == '.xpt':
            output_path = replace_text_in_xpt(file_path, old_text, new_text)
        else:
            os.remove(file_path)
            return jsonify({'error': f'Unsupported file type: {ext}'}), 400
        
        # Send the modified file
        response = send_file(
            output_path,
            as_attachment=True,
            download_name=f"modified_{filename}",
            mimetype='application/octet-stream'
        )
        
        # Clean up files after sending
        def remove_files():
            try:
                os.remove(file_path)
                os.remove(output_path)
            except:
                pass
        
        # Schedule cleanup (in production, use a proper background task)
        import threading
        threading.Timer(10.0, remove_files).start()
        
        return response
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---------------- HTML Template ----------------

HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Document Text Replacer</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        
        .container {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
            padding: 40px;
            width: 100%;
            max-width: 900px;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 40px;
            position: relative;
            overflow: hidden;
        }
        
        .container::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: linear-gradient(90deg, #667eea, #764ba2);
        }
        
        .left-panel {
            display: flex;
            flex-direction: column;
            gap: 25px;
        }
        
        .right-panel {
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            gap: 25px;
        }
        
        .logo-text {
            color: #dc3545;
            font-size: 1.2rem;
            font-weight: 700;
            text-align: center;
            margin-bottom: 5px;
            grid-column: 1 / -1;
        }
        
        h1 {
            color: #333;
            font-size: 2.5rem;
            font-weight: 700;
            text-align: center;
            margin-bottom: 10px;
            grid-column: 1 / -1;
            background: linear-gradient(135deg, #667eea, #764ba2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        
        .subtitle {
            text-align: center;
            color: #666;
            margin-bottom: 30px;
            grid-column: 1 / -1;
            font-size: 1.1rem;
        }
        
        .form-group {
            position: relative;
        }
        
        label {
            display: block;
            margin-bottom: 8px;
            color: #555;
            font-weight: 600;
            font-size: 0.95rem;
            transition: color 0.3s ease;
        }
        
        input[type="text"] {
            width: 100%;
            padding: 15px 20px;
            border: 2px solid #e1e5e9;
            border-radius: 12px;
            font-size: 1rem;
            transition: all 0.3s ease;
            background: rgba(255, 255, 255, 0.9);
            position: relative;
        }
        
        input[type="text"]:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
            transform: translateY(-2px);
        }
        
        .file-upload-area {
            position: relative;
            border: 2px dashed #e1e5e9;
            border-radius: 12px;
            padding: 40px 20px;
            text-align: center;
            transition: all 0.3s ease;
            cursor: pointer;
            background: rgba(255, 255, 255, 0.5);
        }
        
        .file-upload-area:hover {
            border-color: #667eea;
            background: rgba(102, 126, 234, 0.05);
            transform: translateY(-2px);
        }
        
        .file-upload-area.dragover {
            border-color: #667eea;
            background: rgba(102, 126, 234, 0.1);
            transform: scale(1.02);
        }
        
        .upload-icon {
            font-size: 3rem;
            color: #667eea;
            margin-bottom: 15px;
            display: block;
            transition: transform 0.3s ease;
        }
        
        .file-upload-area:hover .upload-icon {
            transform: scale(1.1);
        }
        
        .upload-text {
            color: #666;
            font-size: 1.1rem;
            margin-bottom: 10px;
            font-weight: 500;
        }
        
        .upload-subtext {
            color: #999;
            font-size: 0.9rem;
        }
        
        input[type="file"] {
            position: absolute;
            opacity: 0;
            width: 100%;
            height: 100%;
            cursor: pointer;
        }
        
        .file-info {
            margin-top: 15px;
            padding: 10px;
            background: rgba(102, 126, 234, 0.1);
            border-radius: 8px;
            color: #667eea;
            font-weight: 500;
            display: none;
        }
        
        .btn {
            padding: 15px 30px;
            border: none;
            border-radius: 12px;
            font-size: 1.1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            min-width: 200px;
        }
        
        .btn-primary {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            box-shadow: 0 8px 25px rgba(102, 126, 234, 0.3);
        }
        
        .btn-primary:hover:not(:disabled) {
            transform: translateY(-3px);
            box-shadow: 0 12px 35px rgba(102, 126, 234, 0.4);
        }
        
        .btn-success {
            background: linear-gradient(135deg, #28a745, #20c997);
            color: white;
            box-shadow: 0 8px 25px rgba(40, 167, 69, 0.3);
        }
        
        .btn-success:hover {
            transform: translateY(-3px);
            box-shadow: 0 12px 35px rgba(40, 167, 69, 0.4);
        }
        
        .btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none !important;
        }
        
        .spinner {
            display: none;
            margin-top: 20px;
        }
        
        .spinner.show {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            color: #667eea;
            font-weight: 500;
        }
        
        .spinner::after {
            content: '';
            width: 20px;
            height: 20px;
            border: 2px solid #e1e5e9;
            border-top: 2px solid #667eea;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        .status-message {
            padding: 15px 20px;
            border-radius: 12px;
            margin-top: 20px;
            font-weight: 500;
            text-align: center;
            display: none;
            animation: slideIn 0.5s ease;
        }
        
        .status-success {
            background: rgba(40, 167, 69, 0.1);
            color: #28a745;
            border: 1px solid rgba(40, 167, 69, 0.2);
        }
        
        .status-error {
            background: rgba(220, 53, 69, 0.1);
            color: #dc3545;
            border: 1px solid rgba(220, 53, 69, 0.2);
        }
        
        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(-10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        .process-steps {
            display: flex;
            flex-direction: column;
            gap: 15px;
            margin-top: 20px;
        }
        
        .step {
            display: flex;
            align-items: center;
            gap: 15px;
            padding: 15px;
            background: rgba(255, 255, 255, 0.7);
            border-radius: 10px;
            transition: all 0.3s ease;
        }
        
        .step-number {
            width: 30px;
            height: 30px;
            background: #667eea;
            color: white;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 600;
            font-size: 0.9rem;
        }
        
        .step-text {
            color: #666;
            font-size: 0.95rem;
        }
        
        @media (max-width: 768px) {
            .container {
                grid-template-columns: 1fr;
                gap: 30px;
                padding: 30px 20px;
            }
            
            h1 {
                font-size: 2rem;
            }
            
            .btn {
                min-width: 100%;
            }
        }
        
        .file-types {
            color: #999;
            font-size: 0.85rem;
            margin-top: 10px;
            text-align: center;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo-text">Jhonsan & Jhonason</div>
        <h1>Document Text Replacer</h1>
        <p class="subtitle">Replace text in PDF, CSV, XML, and XPT files with ease</p>
        
        <div class="left-panel">
            <div class="form-group">
                <label for="old_text">🔍 Text to Find</label>
                <input type="text" id="old_text" placeholder="Enter the text you want to replace..." required>
            </div>
            
            <div class="form-group">
                <label for="new_text">✏️ Replace With</label>
                <input type="text" id="new_text" placeholder="Enter the replacement text...">
            </div>
            
            <div class="form-group">
                <label>📁 Upload Document</label>
                <div class="file-upload-area" id="fileUploadArea">
                    <span class="upload-icon">⬆️</span>
                    <div class="upload-text">Drop your file here or click to browse</div>
                    <div class="upload-subtext">Supports PDF, CSV, XML, XPT files</div>
                    <input type="file" id="pdf-file-input" accept=".pdf,.csv,.xml,.xpt">
                    <div class="file-info" id="fileInfo"></div>
                </div>
                <div class="file-types">Supported formats: PDF, CSV, XML, XPT (Max 16MB)</div>
            </div>
        </div>
        
        <div class="right-panel">
            <div class="process-steps">
                <div class="step">
                    <div class="step-number">1</div>
                    <div class="step-text">Enter the text you want to find and replace</div>
                </div>
                <div class="step">
                    <div class="step-number">2</div>
                    <div class="step-text">Upload your document (PDF, CSV, XML, or XPT)</div>
                </div>
                <div class="step">
                    <div class="step-number">3</div>
                    <div class="step-text">Click process to generate your modified file</div>
                </div>
            </div>
            
            <button type="button" class="btn btn-primary" id="processBtn" disabled>
                <span>🚀 Process Document</span>
            </button>
            
            <div class="spinner" id="loadingSpinner">
                <span>Processing your document...</span>
            </div>
            
            <div class="status-message" id="statusMessage"></div>
            
            <button type="button" class="btn btn-success" id="downloadBtn" style="display: none;">
                <span>⬇️ Download Modified File</span>
            </button>
        </div>
    </div>
    
    <script>
        const fileInput = document.getElementById('pdf-file-input');
        const fileUploadArea = document.getElementById('fileUploadArea');
        const fileInfo = document.getElementById('fileInfo');
        const processBtn = document.getElementById('processBtn');
        const downloadBtn = document.getElementById('downloadBtn');
        const spinner = document.getElementById('loadingSpinner');
        const statusMessage = document.getElementById('statusMessage');
        const oldTextInput = document.getElementById('old_text');
        const newTextInput = document.getElementById('new_text');
        
        let currentFile = null;
        
        // File upload handling
        fileUploadArea.addEventListener('click', () => fileInput.click());
        
        fileUploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            fileUploadArea.classList.add('dragover');
        });
        
        fileUploadArea.addEventListener('dragleave', () => {
            fileUploadArea.classList.remove('dragover');
        });
        
        fileUploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            fileUploadArea.classList.remove('dragover');
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                handleFileSelect(files[0]);
            }
        });
        
        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                handleFileSelect(e.target.files[0]);
            }
        });
        
        function handleFileSelect(file) {
            const allowedTypes = ['.pdf', '.csv', '.xml', '.xpt'];
            const fileExt = '.' + file.name.split('.').pop().toLowerCase();
            
            if (!allowedTypes.includes(fileExt)) {
                showStatus('Please select a valid file type (PDF, CSV, XML, or XPT)', 'error');
                return;
            }
            
            if (file.size > 16 * 1024 * 1024) {
                showStatus('File size must be less than 16MB', 'error');
                return;
            }
            
            currentFile = file;
            fileInfo.innerHTML = `📄 ${file.name} (${formatFileSize(file.size)})`;
            fileInfo.style.display = 'block';
            checkFormValidity();
        }
        
        function formatFileSize(bytes) {
            if (bytes === 0) return '0 Bytes';
            const k = 1024;
            const sizes = ['Bytes', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }
        
        // Form validation
        function checkFormValidity() {
            const hasFile = currentFile !== null;
            const hasOldText = oldTextInput.value.trim() !== '';
            
            processBtn.disabled = !(hasFile && hasOldText);
        }
        
        oldTextInput.addEventListener('input', checkFormValidity);
        newTextInput.addEventListener('input', checkFormValidity);
        
        // Process button click
        processBtn.addEventListener('click', async () => {
            if (!currentFile || !oldTextInput.value.trim()) {
                showStatus('Please select a file and enter text to find', 'error');
                return;
            }
            
            const formData = new FormData();
            formData.append('pdf_file', currentFile);
            formData.append('old_text', oldTextInput.value.trim());
            formData.append('new_text', newTextInput.value.trim());
            
            setProcessingState(true);
            
            try {
                const response = await fetch('/upload', {
                    method: 'POST',
                    body: formData
                });
                
                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.error || 'Processing failed');
                }
                
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                
                // Store download URL for later use
                downloadBtn.setAttribute('data-url', url);
                downloadBtn.setAttribute('data-filename', `modified_${currentFile.name}`);
                
                showStatus('✅ Document processed successfully!', 'success');
                downloadBtn.style.display = 'flex';
                
            } catch (error) {
                showStatus(`❌ Error: ${error.message}`, 'error');
            } finally {
                setProcessingState(false);
            }
        });
        
        // Download button click
        downloadBtn.addEventListener('click', () => {
            const url = downloadBtn.getAttribute('data-url');
            const filename = downloadBtn.getAttribute('data-filename');
            
            if (url && filename) {
                const a = document.createElement('a');
                a.href = url;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                a.remove();
                window.URL.revokeObjectURL(url);
                
                showStatus('📥 Download started!', 'success');
            }
        });
        
        function setProcessingState(processing) {
            processBtn.disabled = processing;
            if (processing) {
                spinner.classList.add('show');
                downloadBtn.style.display = 'none';
                hideStatus();
            } else {
                spinner.classList.remove('show');
            }
        }
        
        function showStatus(message, type) {
            statusMessage.textContent = message;
            statusMessage.className = `status-message status-${type}`;
            statusMessage.style.display = 'block';
            
            if (type === 'error') {
                setTimeout(() => hideStatus(), 5000);
            }
        }
        
        function hideStatus() {
            statusMessage.style.display = 'none';
        }
        
        // Add some interactive animations
        document.querySelectorAll('.btn').forEach(btn => {
            btn.addEventListener('mouseenter', function() {
                this.style.transform = 'translateY(-3px)';
            });
            
            btn.addEventListener('mouseleave', function() {
                if (!this.disabled) {
                    this.style.transform = 'translateY(0)';
                }
            });
        });
        
        document.querySelectorAll('input[type="text"]').forEach(input => {
            input.addEventListener('focus', function() {
                this.parentElement.querySelector('label').style.color = '#667eea';
            });
            
            input.addEventListener('blur', function() {
                this.parentElement.querySelector('label').style.color = '#555';
            });
        });
    </script>
</body>
</html>'''

if __name__ == '__main__':
    # Get port from environment variable (Railway sets this automatically)
    port = int(os.environ.get('PORT', 5000))
    
    # Check if running in production (Railway sets RAILWAY_ENVIRONMENT)
    is_production = os.environ.get('RAILWAY_ENVIRONMENT') is not None
    
    if is_production:
        # Production settings
        app.run(host='0.0.0.0', port=port, debug=False)
    else:
        # Development settings
        app.run(host='0.0.0.0', port=port, debug=True)
