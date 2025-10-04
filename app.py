from flask import Flask, request, jsonify, send_from_directory
import os
import subprocess
import pathlib

app = Flask(__name__)

# Save in current directory
app.config['UPLOAD_FOLDER'] = "."

# Fixed filename
RESUME_FILENAME = "Resume.pdf"
GEMINI_OUTPUT_MD = "resume_recommendation.md"

@app.route('/')
def serve_main():
    return send_from_directory('.', 'main.html')

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

    # Always save as resume.pdf
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], RESUME_FILENAME)
    file.save(filepath)

    # Run gemini_v2.py after saving
    subprocess.run(['python', 'gemini_v2.py'], capture_output=True, text=True)

    return jsonify({'success': True, 'filename': RESUME_FILENAME}), 200

@app.route('/ai_response', methods=['GET'])
def ai_response():
    output_path = pathlib.Path(GEMINI_OUTPUT_MD)

    # Run Gemini if output doesn't exist
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
        return jsonify({"response": "No Gemini output file found."})

@app.route('/download_gemini_output', methods=['GET'])
def download_gemini_output():
    output_path = pathlib.Path(GEMINI_OUTPUT_MD)
    if output_path.exists():
        return send_from_directory('.', GEMINI_OUTPUT_MD, as_attachment=True)
    else:
        return jsonify({"error": "Gemini output file not found."}), 404

if __name__ == '__main__':
    app.run(debug=True)
