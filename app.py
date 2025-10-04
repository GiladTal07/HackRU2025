from flask import Flask, request, jsonify, send_from_directory
import os
import subprocess


import pathlib

app = Flask(__name__)

app.config['UPLOAD_FOLDER'] = ""  # current directory

# Path to the Gemini output file
GEMINI_OUTPUT_MD = "resume_recommendation.md"

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
        # After saving the resume, run gemini_v2.py to generate the output
        subprocess.run(['python', 'gemini_v2.py'], capture_output=True, text=True)
        return jsonify({'success': True, 'filename': file.filename}), 200
    return jsonify({'error': 'Unknown error'}), 500




# Endpoint to return only the last Gemini markdown output, and run gemini_v2.py if needed
@app.route('/ai_response', methods=['GET'])
def ai_response():
    output_path = pathlib.Path(GEMINI_OUTPUT_MD)
    # If the output file does not exist, run gemini_v2.py to generate it
    if not output_path.exists():
        subprocess.run(['python', 'gemini_v2.py'], capture_output=True, text=True)
    if output_path.exists():
        try:
            with output_path.open('r', encoding='utf-8') as f:
                content = f.read()
            return jsonify({"response": content})
        except Exception as e:
            return jsonify({"error": f"Failed to read Gemini output: {e}"}), 500
    else:
        return jsonify({"response": "No Gemini output file found. Please run Gemini v2 first."})

# Endpoint to download the Gemini markdown file directly
@app.route('/download_gemini_output', methods=['GET'])
def download_gemini_output():
    output_path = pathlib.Path(GEMINI_OUTPUT_MD)
    if output_path.exists():
        return send_from_directory('.', GEMINI_OUTPUT_MD, as_attachment=True)
    else:
        return jsonify({"error": "Gemini output file not found."}), 404


if __name__ == '__main__':
    app.run()
