import os
from dotenv import load_dotenv
import requests
import fitz  # PyMuPDF
import docx
from flask import Flask, render_template, request
from werkzeug.utils import secure_filename

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB de tamanho máximo
ALLOWED_EXTENSIONS = {'pdf', 'docx'}

# Obtém as chaves de API do .env
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
SERPAPI_API_KEY = os.getenv('SERPAPI_API_KEY')

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_pdf(pdf_path):
    text = ""
    with fitz.open(pdf_path) as doc:
        for page in doc:
            text += page.get_text()
    return text

def extract_text_from_docx(docx_path):
    doc = docx.Document(docx_path)
    return "\n".join([para.text for para in doc.paragraphs])

def get_source_from_serpapi(query):
    url = "https://serpapi.com/search"
    params = {
        "engine": "google",
        "q": query,
        "api_key": SERPAPI_API_KEY,
        "num": 1
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if "organic_results" in data and len(data["organic_results"]) > 0:
            return data["organic_results"][0].get("link", "Fonte não encontrada")
    except requests.RequestException:
        pass
    return "Fonte não encontrada"

def analyze_plagiarism_with_source(text):
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "Você é um assistente que detecta plágio comparando textos."},
            {"role": "user", "content": (
                "Verifique se esse texto possui plágio na internet e destaque os trechos plagiados. "
                "Para cada trecho, informe também a fonte original (por exemplo, a URL ou outra referência). "
                "\n\n" + text
            )}
        ]
    }

    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        deepseek_result = response.json()["choices"][0]["message"]["content"]
        # Exemplo simples de parsing:
        resultado_completo = ""
        linhas = deepseek_result.splitlines()
        for linha in linhas:
            if linha.strip().startswith("Trecho"):
                trecho = linha.split("Trecho:", 1)[1].strip()
                fonte = get_source_from_serpapi(trecho)
                resultado_completo += f"Trecho: {trecho} - Fonte: {fonte}\n"
            else:
                resultado_completo += linha + "\n"
        return resultado_completo
    return f"Erro na API DeepSeek (status: {response.status_code})"

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/comparacao_texto", methods=["GET", "POST"])
def comparacao_texto():
    text1, text2, ai_analysis = "", "", ""
    if request.method == "POST":
        text1 = request.form.get("text1", "")
        text2 = request.form.get("text2", "")
        comparison_text = f"Comparação:\nTexto 1:\n{text1}\n\nTexto 2:\n{text2}"
        ai_analysis = analyze_plagiarism_with_source(comparison_text)
    return render_template("comparacao.html", text1=text1, text2=text2, ai_analysis=ai_analysis)

@app.route("/verificacao_plagio", methods=["GET", "POST"])
def verificacao_plagio():
    text, plagio_result, file_text = "", "", ""

    if request.method == "POST":
        if "file" in request.files and request.files["file"].filename != "":
            file = request.files["file"]
            if allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                if filename.lower().endswith(".pdf"):
                    file_text = extract_text_from_pdf(file_path)
                elif filename.lower().endswith(".docx"):
                    file_text = extract_text_from_docx(file_path)
        text = request.form.get("text", "") or file_text
        plagio_result = analyze_plagiarism_with_source(text)

    return render_template("plagio.html", text=text, plagio_result=plagio_result)

if __name__ == "__main__":
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(debug=True)
