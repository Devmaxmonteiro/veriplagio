import os
import requests
import fitz  # PyMuPDF
import docx
from io import BytesIO
from flask import Flask, render_template, request, send_file
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

# Carrega as variáveis de ambiente do .env
load_dotenv()

app = Flask(__name__)

# Configurações
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Chaves de API do .env
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
GPTZERO_API_KEY = os.getenv('GPTZERO_API_KEY')
SERPAPI_API_KEY = os.getenv('SERPAPI_API_KEY')

############################################################
#                  FUNÇÕES DE APOIO
############################################################

def detectar_ia(texto):
    """
    Usa GPTZero para detectar se o texto foi gerado por IA.
    """
    url = "https://api.gptzero.me/v1/detect"
    headers = {"Authorization": f"Bearer {GPTZERO_API_KEY}"}
    data = {"text": texto}
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        return response.json()
    return {"error": "Falha ao detectar IA"}

def humanizar_texto(texto):
    """
    Usa DeepSeek para reescrever/parafrasear o texto.
    """
    url = "https://api.deepseek.com/v1/paraphrase"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}"}
    data = {"text": texto}
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        resp_json = response.json()
        return resp_json.get("paraphrased_text", "Erro na reescrita")
    return "Erro ao humanizar texto"

def extract_text_from_pdf(pdf_path):
    """
    Extrai texto de um PDF usando PyMuPDF.
    """
    text = ""
    with fitz.open(pdf_path) as doc:
        for page in doc:
            text += page.get_text()
    return text

def extract_text_from_docx(docx_path):
    """
    Extrai texto de um DOCX usando python-docx.
    """
    document = docx.Document(docx_path)
    return "\n".join(para.text for para in document.paragraphs)

def get_source_from_serpapi(query):
    """
    Usa a SerpApi para pesquisar o trecho e retornar a fonte original (URL) do texto.
    """
    url = "https://serpapi.com/search"
    params = {
        "engine": "google",
        "q": query,
        "api_key": SERPAPI_API_KEY,
        "num": 1  # Retorna o resultado mais relevante
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        organic = data.get("organic_results", [])
        if organic and len(organic) > 0:
            return organic[0].get("link", "Fonte não encontrada")
    except Exception:
        pass
    return "Fonte não encontrada"

def analyze_plagiarism_with_source(text):
    """
    Processa a resposta (simulada ou real) da API de plágio e retorna:
      - resultado_bruto: string para exibição (contendo "Trecho: ... - Fonte: ...")
      - trechos_plagio: lista de dicionários com "trecho" e "fonte" (obtida via SerpApi)
    """
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}",
               "Content-Type": "application/json"}
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
    if response.status_code != 200:
        return f"Erro na API DeepSeek (status: {response.status_code})", []

    deepseek_result = response.json()["choices"][0]["message"]["content"]
    resultado_bruto = ""
    trechos_plagio = []

    linhas = deepseek_result.splitlines()
    for linha in linhas:
        if linha.strip().startswith("Trecho"):
            try:
                # Supõe o formato: "Trecho: <texto>" ou "Trecho: <texto> - Fonte: <alguma_coisa>"
                after_trecho = linha.split("Trecho:", 1)[1].strip()
                if "- Fonte:" in after_trecho:
                    trecho, fonte_part = after_trecho.split("- Fonte:", 1)
                    trecho = trecho.strip()
                    # Aqui, em vez de usar o que vem na resposta, buscamos via SerpApi:
                    fonte = get_source_from_serpapi(trecho)
                else:
                    trecho = after_trecho
                    fonte = get_source_from_serpapi(trecho)
                trechos_plagio.append({"trecho": trecho, "fonte": fonte})
                resultado_bruto += f"Trecho: {trecho} - Fonte: {fonte}\n"
            except Exception:
                resultado_bruto += linha + "\n"
        else:
            resultado_bruto += linha + "\n"

    return resultado_bruto, trechos_plagio

def verificar_plagio_relatorio(texto):
    """
    SIMULA (ou chama uma API real) um relatório de plágio no estilo CopiSpider.
    Retorna:
      - total_termos: número total de palavras do texto
      - total_similaridade: percentual total de similaridade (soma simulada)
      - resultados: lista de dicionários com dados (fonte, termos, termos_comuns, similitude)
    """
    palavras_texto = len(texto.split())
    resultados = [
        {"fonte": "https://quantumcloud.com/inovacao.pdf",
         "termos": 1494,
         "termos_comuns": 129,
         "similitude": 3.7,
         "visualizar_link": "#"},
        {"fonte": "https://exemplo.com/tecnologia-educacao.pdf",
         "termos": 999,
         "termos_comuns": 88,
         "similitude": 2.1,
         "visualizar_link": "#"},
        {"fonte": "https://outroexemplo.com/trabalho-academico.html",
         "termos": 2000,
         "termos_comuns": 300,
         "similitude": 10.0,
         "visualizar_link": "#"}
    ]
    total_similaridade = sum(item["similitude"] for item in resultados)
    return palavras_texto, round(total_similaridade, 2), resultados

def search_with_serpapi(query):
    """
    Pesquisa o query na SerpApi e retorna uma lista de resultados.
    """
    url = "https://serpapi.com/search"
    params = {
        "engine": "google",
        "q": query,
        "api_key": SERPAPI_API_KEY,
        "num": 3
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        organic = data.get("organic_results", [])
        results = []
        for item in organic:
            results.append({
                "title": item.get("title", "Sem título"),
                "link": item.get("link", "#"),
                "snippet": item.get("snippet", "")
            })
        return results
    except Exception as e:
        return [{"title": "Erro ao buscar no SerpApi", "link": "#", "snippet": str(e)}]

############################################################
#                      ROTAS FLASK
############################################################

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/detectar_ia', methods=['POST'])
def detectar_ia_view():
    texto = request.form.get('texto', '')
    resultado = detectar_ia(texto)
    return render_template('detector_ia.html', resultado=resultado, texto=texto)

@app.route('/humanizar_texto', methods=['POST'])
def humanizar_texto_view():
    texto = request.form.get('texto', '')
    texto_humanizado = humanizar_texto(texto)
    return render_template('humanizador.html', texto=texto, texto_humanizado=texto_humanizado)

@app.route('/verificar_plagio', methods=['POST'])
def verificar_plagio_view():
    texto = request.form.get('texto', '')
    total_termos, total_similaridade, resultados = verificar_plagio_relatorio(texto)
    return render_template('relatorio_plagio.html',
                           texto=texto,
                           total_termos=total_termos,
                           total_similaridade=total_similaridade,
                           resultados=resultados)

@app.route('/comparar_textos', methods=['GET', 'POST'])
def comparar_textos_view():
    text1, text2 = "", ""
    results_text1, results_text2 = [], []
    if request.method == 'POST':
        text1 = request.form.get('text1', '')
        text2 = request.form.get('text2', '')
        results_text1 = search_with_serpapi(text1)
        results_text2 = search_with_serpapi(text2)
    return render_template('comparador.html',
                           text1=text1,
                           text2=text2,
                           results_text1=results_text1,
                           results_text2=results_text2)

if __name__ == '__main__':
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    app.run(debug=True)
