import sys

if sys.platform != "win32":
    try:
        from gevent import monkey
        # Desativamos o patch de SSL para evitar o conflito com a biblioteca do Gemini
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

# "Prompt de Sistema". 
instrucoes = """
    Você é o "Cineasta & Curador", um assistente inteligente, empático e com um gosto cultural refinado. Seu objetivo é ajudar o usuário a encontrar o entretenimento perfeito (filmes, séries ou livros) com base no estado emocional e no perfil de preferências dele.

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

    FORMATO PADRÃO DE RECOMENDAÇÃO:

    [Saudação breve e empática conectada ao humor do usuário]

    * **[Título da Obra]** ([Ano] - [Gênero])
    * **O porquê:** [Frase curta e impactante justificando a escolha].
    * **[Título da Obra]** ([Ano] - [Gênero])
    * **O porquê:** [Frase curta e impactante justificando a escolha].

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
        print(f"Nova sessão Flask criada: {session['session_id']}")

    session_id = session['session_id']

    if session_id not in active_chats:
        print(f"Criando novo chat Gemini para session_id: {session_id}")
        try:
            chat_session = client.chats.create(
                model=MODELO,
                config=types.GenerateContentConfig(system_instruction=instrucoes)
            )
            active_chats[session_id] = chat_session
            print(f"Novo chat Gemini criado e armazenado para {session_id}")
        except Exception as e:
            app.logger.error(f"Erro ao criar chat Gemini para {session_id}: {e}", exc_info=True)
            raise  

    if session_id in active_chats and active_chats[session_id] is None:
        print(f"Recriando chat Gemini para session_id existente (estava None): {session_id}")
        try:
            chat_session = client.chats.create(
                model=MODELO,
                config=types.GenerateContentConfig(system_instruction=instrucoes)
            )
            active_chats[session_id] = chat_session
        except Exception as e:
            app.logger.error(f"Erro ao recriar chat Gemini para {session_id}: {e}", exc_info=True)
            raise

    return active_chats[session_id]


@app.route('/')
def root():
    return jsonify({
        "api-websocket": "chatbot",
        "status": "ok"
    })


@socketio.on('connect')
def handle_connect():
    print(f"Cliente conectado: {request.sid}")
    
    try:
        get_user_chat()
        user_session_id = session.get('session_id', 'N/A')
        print(f"Sessão Flask para {request.sid} usa session_id: {user_session_id}")
        
        emit('status_conexao', {'data': 'Conectado com sucesso!', 'session_id': user_session_id})
    except Exception as e:
        app.logger.error(f"Erro durante o evento connect para {request.sid}: {e}", exc_info=True)
        emit('erro', {'erro': 'Falha ao inicializar a sessão de chat no servidor.'})


@socketio.on('enviar_mensagem')
def handle_enviar_mensagem(data):
    try:
        mensagem_usuario = data.get("mensagem")
        app.logger.info(f"Mensagem recebida de {session.get('session_id', request.sid)}: {mensagem_usuario}")

        if not mensagem_usuario:
            emit('erro', {"erro": "Mensagem não pode ser vazia."})
            return

        user_chat = get_user_chat()
        if user_chat is None:
            emit('erro', {"erro": "Sessão de chat não pôde ser estabelecida."})
            return

        resposta_gemini = user_chat.send_message(mensagem_usuario)

        resposta_texto = (
            resposta_gemini.text
            if hasattr(resposta_gemini, 'text')
            else resposta_gemini.candidates[0].content.parts[0].text
        )
        
        emit('nova_mensagem', {"remetente": "bot", "texto": resposta_texto, "session_id": session.get('session_id')})
        app.logger.info(f"Resposta enviada para {session.get('session_id', request.sid)}: {resposta_texto}")

    except Exception as e:
        app.logger.error(f"Erro ao processar 'enviar_mensagem' para {session.get('session_id', request.sid)}: {e}", exc_info=True)
        emit('erro', {"erro": f"Ocorreu um erro no servidor: {str(e)}"})


@socketio.on('disconnect')
def handle_disconnect():
    print(f"Cliente desconectado: {request.sid}, session_id: {session.get('session_id', 'N/A')}")


if __name__ == "__main__":
    socketio.run(app)
