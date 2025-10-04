

import os
from dotenv import load_dotenv
load_dotenv()
from google import genai
from google.genai import types


# Set the Gemini API key in the environment for the client

# 1️⃣ Make sure you set your API key beforehand:
# export GOOGLE_API_KEY="your_api_key_here"
# or set it in code (not recommended for production):

client = genai.Client(api_key="AIzaSyD3ksfBGLU5IcK2rysSqbEKUTaR5kF-QAA")

# 2️⃣ Path to your resume file
resume_path = "Resume.pdf"

# 3️⃣ Extract text from the PDF file
import PyPDF2
with open(resume_path, "rb") as f:
    reader = PyPDF2.PdfReader(f)
    resume_text = "\n".join(page.extract_text() or "" for page in reader.pages)
print("Extracted resume text.")

# 4️⃣ Create your instruction prompt
prompt = """
You are an expert academic and career advisor.
Analyze the provided resume carefully and provide:
1. Course recommendations to strengthen the person’s skills.
2. Possible career paths based on their experience, strengths, and interests.
3. Key skills or technologies they should learn next.
4. A short summary of their profile in 3–4 sentences.

Respond in a well-structured markdown format.
"""

# 5️⃣ Generate analysis

# 5️⃣ Generate analysis
response = client.models.generate_content(
    model="gemini-2.5-flash",  # Fast and powerful model
    contents=[
        resume_text,
        prompt
    ],
    config=types.GenerateContentConfig(
        temperature=0.7,  # balanced creativity
        thinking_config=types.ThinkingConfig(thinking_budget=50)  # allow some reasoning time
    ),
)

# 6️⃣ Print model’s analysis
print("\n===== GEMINI RESUME ANALYSIS =====\n")
print(response.text)