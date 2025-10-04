from flask import Flask, request, jsonify, send_from_directory
import os
import subprocess

app = Flask(__name__)

app.config['UPLOAD_FOLDER'] = "" #current

# Serve main.html at the root
@app.route('/')
def serve_main():
    return send_from_directory('.', 'main.html')

# Serve static files (e.g., Bootstrap CSS)
@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory('.', filename)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'resume' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['resume']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if file:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filepath)
        return jsonify({'success': True, 'filename': file.filename}), 200
    return jsonify({'error': 'Unknown error'}), 500

@app.route('/ai_response', methods=['GET'])
def ai_response():
    result = subprocess.run(['python', 'gemini.py'], 
    capture_output=True, 
    text=True)

    if not result:
        result.sdout = "no result"

    return jsonify({"response": result.stdout})


if __name__ == '__main__':
    app.run()
