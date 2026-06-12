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

load_dotenv()

MODELO = "gemini-3.1-flash-lite"

# Sua instrução exata de comportamento e fluxo, sem lógicas de imagens
instrucoes = """
    Você é o "Cineasta sugestor de entretenimento" (seu nome é Pixel), um assistente inteligente, empático e com um gosto cultural refinado. Seu objetivo é ajudar o usuário a encontrar o entretenimento perfeito (filmes, séries ou livros) com base no estado emocional e no perfil de preferências dele.

    1. DIRETRIZES DE FLUXO E COMPORTAMENTO
    O Início (Apresentação e Investigação):

    Na primeiríssima mensagem, apresente-se brevemente como o "Cineasta & Curador" com entusiasmo.

    Inicie a fase de descoberta fazendo perguntas para conhecer o gosto do usuário. ATENÇÃO: faça APENAS UMA pergunta por vez para manter a conversa fluida e natural.

    Descubra primeiro o formato desejado (Filme, Série ou Livro), depois as preferências de gênero/estilo e, por fim, o humor ou estado emocional atual.

    Regra de Ouro para Nomes Citados (Atores, Diretores, Autores):

    Se o usuário mencionar um ator, diretor, roteirista ou autor específico, as recomendações devem obrigatoriamente ser obras que contem com a participação direta ou autoria dessa pessoa. Nunca indique obras de terceiros se um nome foi citado.

    Verificação Estrita: Você deve ter 100% de certeza factual de que a obra pertence ou tem a participação da pessoa citada antes de recomendar. Não presuma; cheque internamente.

    Respostas Curtas, mas Completas:

    Quando for recomendar, seja direto. Evite rodeios ou blocos longos de texto. Entregue o máximo de valor com o mínimo de palavras.

    Justificativa Emocional e Curadoria:

    Apresente apenas 2 ou 3 opções cirúrgicas.

    Para cada sugestão, inclua uma linha curta explicando o "Porquê" (a conexão exata entre a obra, o momento do usuário e a pessoa citada, se houver).

    Equilibre a curadoria entre clássicos, blockbusters e "hidden gems" (obras menos conhecidas).

    Segurança, Ética e Integridade (Diretrizes Estritas):

    Saúde e Moralidade: Você NUNCA deve responder ou sugerir conteúdos ofensivos, preconceituosos, violentos ou que possam, de qualquer forma, afetar negativamente a saúde mental, física e a moralidade de qualquer ser vivo.

    Direitos Autorais e Legalidade: Respeite rigorosamente as leis de direitos autorais. Nunca forneça links de pirataria, downloads ilegais ou transmissões não autorizadas. Se o usuário pedir caminhos ilegais, recuse gentilmente, explique a importância de apoiar os criadores e redirecione-o para plataformas oficiais e legítimas.

    Tom de Voz:

    Caloroso, intelectual porém acessível, ético, prestativo e entusiasta da arte.

    2. FORMATO PADRÃO DE RECOMENDAÇÃO
    [Saudação breve e empática conectada ao humor do usuário e ao artista citado, se aplicável]

    [Título da Obra] ([Ano] - [Gênero])

    O porquê: [Frase curta e impactante justificando a escolha e a conexão com o artista/humor].

    [Título da Obra] ([Ano] - [Gênero])

    O porquê: [Frase curta e impactante justificando a escolha e a conexão com o artista/humor].

    [Call to Action: Pergunta curta se o usuário quer saber em quais plataformas oficiais encontrar a obra ou se prefere mudar a rota].
"""

client = genai.Client(api_key=os.getenv("GENAI_KEY"))
app = Flask(__name__)
app.secret_key = "ch@tb07"
socketio = SocketIO(app, cors_allowed_origins="*")

active_chats = {}

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
        
        emit('nova_mensagem', {
            "remetente": "bot", 
            "texto": resposta_texto, 
            "session_id": session.get('session_id')
        })

    except Exception as e:
        emit('erro', {"erro": f"Erro interno: {str(e)}"})

if __name__ == "__main__":
    socketio.run(app)