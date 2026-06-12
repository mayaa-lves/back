import sys

if sys.platform != "win32":
    try:
        from gevent import monkey
        monkey.patch_all()
    except ImportError:
        print("Gevent não instalado!")

from flask import Flask, request, session, jsonify
from flask_socketio import SocketIO, emit
from google import genai
from google.genai import types
from dotenv import load_dotenv
from uuid import uuid4
import os
import re

load_dotenv()

MODELO = "gemini-3.1-flash-lite"

instrucoes = """
    Você é o "Cineasta sugestor de entreterimento" (seu nome é Pixel), um assistente inteligente, empático e com um gosto cultural refinado. Seu objetivo é ajudar o usuário a encontrar o entretenimento perfeito (filmes, séries ou livros) com base no estado emocional e no perfil de preferências dele.

    DIRETRIZES DE FLUXO E COMPORTAMENTO:

    1. O Início (Apresentação e Investigação):
    - Na primeiríssima mensagem, apresente-se brevemente como o "Cineasta & Curador" com entusiasmo.
    - Inicie a fase de descoberta fazendo perguntas para conhecer o gosto do usuário. ATENÇÃO: faça APENAS UMA pergunta por vez para manter a conversa fluida e natural.
    - Descubra primeiro o formato desejado (Filme, Série ou Livro), depois as preferências de gênero/estilo e, por fim, o humor ou estado emocional atual.

    2. Respostas Curtas, mas Completas:
    - Quando for recomendar, seja direto. Evite rodeios ou blocos longos de texto. Entregue o máximo de valor com o mínimo de palavras.

    3. Justificativa Emocional e Curadoria:
    - Apresente apenas 2 ou 3 opções cirúrgicas.
    - Para cada sugestão, inclua uma linha curta explicando o "Porquê" (a conexão exata entre a obra e o momento do usuário).
    - Equilibre a curadoria entre clássicos, blockbusters e "hidden gems" (obras menos conhecidas).

    4. Segurança, Ética e Integridade (Diretrizes Estritas):
    - Saúde e Moralidade: Você NUNCA deve responder ou sugerir conteúdos ofensivos, preconceituosos, violentos ou que possam, de qualquer forma, afetar negativamente a saúde mental, física e a moralidade de qualquer ser vivo.
    - Direitos Autorais e Legalidade: Respeite rigorosamente as leis de direitos autorais. Nunca forneça links de pirataria, downloads ilegais ou transmissões não autorizadas. Se o usuário pedir caminhos ilegais, recuse gentilmente, explique a importância de apoiar os criadores e redirecione-o para plataformas oficiais e legítimas.

    5. Tom de Voz:
    - Caloroso, intelectual porém acessível, ético, prestativo e entusiasta da arte.

    ---

    FORMATO PADRÃO DE RECOMENDAÇÃO (SIGA DETALHADAMENTE):

    [Saudação breve e empática conectada ao humor do usuário]

    * **[Título da Obra 1]** ([Ano] - [Gênero])
    * **O porquê:** [Frase curta e impactante justificando a escolha].
    * **[Título da Obra 2]** ([Ano] - [Gênero])
    * **O porquê:** [Frase curta e impactante justificando a escolha].

    [Call to Action: Pergunta curta se o usuário quer saber em quais plataformas oficiais encontrar a obra ou se prefere mudar a rota].

    [Mídia: Escreva Aqui o Nome Exato da Obra 1]
"""

client = genai.Client(api_key=os.getenv("GENAI_KEY"))
app = Flask(__name__)
app.secret_key = "ch@tb07"
socketio = SocketIO(app, cors_allowed_origins="*")

active_chats = {}

def buscar_cartaz(nome_obra):
    """Busca a imagem tratando erros de forma robusta com o parâmetro obrigatório keywords"""
    if not nome_obra:
        return None
    try:
        from duckduckgo_search import DDGS
        # Limpa caracteres residuais como colchetes soltos ou pontos finais
        nome_limpo = nome_obra.replace('[', '').replace(']', '').replace('.', '').strip()
        termo_busca = f"{nome_limpo} movie book poster portrait"
        
        ddgs = DDGS()
        resultados = ddgs.images(keywords=termo_busca, max_results=1)
        if resultados and len(resultados) > 0:
            return resultados[0].get('image')
    except Exception as e:
        print(f"Erro na busca do DuckDuckGo: {e}")
    return None

def get_user_chat():
    if 'session_id' not in session:
        session['session_id'] = str(uuid4())
    session_id = session['session_id']

    if session_id not in active_chats or active_chats[session_id] is None:
        chat_session = client.chats.create(
            model=MODELO,
            config=types.GenerateContentConfig(system_instruction=instrucoes)
        )
        active_chats[session_id] = chat_session
    return active_chats[session_id]

@app.route('/')
def root():
    return jsonify({"api-websocket": "chatbot", "status": "ok"})

@socketio.on('connect')
def handle_connect():
    try:
        get_user_chat()
        emit('status_conexao', {'data': 'Conectado com sucesso!', 'session_id': session.get('session_id')})
    except Exception as e:
        emit('erro', {'erro': 'Falha ao inicializar a sessão de chat.'})

@socketio.on('enviar_mensagem')
def handle_enviar_mensagem(data):
    try:
        mensagem_usuario = data.get("mensagem")
        if not mensagem_usuario:
            return

        user_chat = get_user_chat()
        resposta_gemini = user_chat.send_message(mensagem_usuario)
        resposta_texto = resposta_gemini.text if hasattr(resposta_gemini, 'text') else resposta_gemini.candidates[0].content.parts[0].text
        
        # 🌟 BUSCA ROBUSTA: Captura o nome independente de espaços ou pontos colados
        url_cartaz = None
        match = re.search(r'\[Mídia:\s*(.*?)\]', resposta_texto, re.IGNORECASE)
        if match:
            nome_da_midia = match.group(1).strip()
            url_cartaz = buscar_cartaz(nome_da_midia)
        
        # 🌟 MUDANÇA CRÍTICA: Não apagamos mais via regex violento para evitar o sumiço do texto!
        # Apenas removemos a linha exata do [Mídia: ...] de forma limpa.
        linhas = resposta_texto.split('\n')
        linhas_filtradas = [l for l in list(linhas) if not l.strip().startswith('[Mídia:')]
        texto_limpo = '\n'.join(linhas_filtradas).strip()

        emit('nova_mensagem', {
            "remetente": "bot", 
            "texto": texto_limpo, 
            "cartaz": url_cartaz,
            "session_id": session.get('session_id')
        })

    except Exception as e:
        emit('erro', {"erro": f"Erro interno no servidor: {str(e)}"})

if __name__ == "__main__":
    socketio.run(app)