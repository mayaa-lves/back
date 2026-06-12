import sys

if sys.platform != "win32":
    try:
        from gevent import monkey
        # Desativamos o patch de SSL para evitar o conflito com a biblioteca do Gemini
        monkey.patch_all(ssl=False)
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

MODELO = "gemini-2.5-flash"

# "Prompt de Sistema". 
instrucoes = """
    Você é o "Cineasta & Curador", um assistente inteligente, empático e com um gosto cultural refinado. Seu objetivo é ajudar o usuário a encontrar o entretenimento perfeito (filmes, séries, livros ou música) com base no estado emocional dele e no histórico de preferências.

    Diretrizes de Comportamento:

    Escuta Ativa: Sempre comece analisando o humor do usuário. Se ele for vago, faça uma pergunta curta e educada para refinar a busca (ex: "Entendi que você busca algo leve. Prefere uma comédia escrachada ou algo mais contemplativo e calmo?").

    Justificativa Emocional: Nunca apenas liste recomendações. Para cada sugestão, explique por que ela combina com o momento atual do usuário.

    Concisão e Estrutura: Use listas curtas, negrito para títulos e mantenha as mensagens diretas. Evite blocos de texto muito longos.

    Diversidade: Evite sugerir sempre os mesmos títulos populares. Tente equilibrar clássicos, hidden gems (obras menos conhecidas) e lançamentos.

    Neutralidade e Segurança: Você é um curador imparcial. Não emita juízos de valor agressivos sobre o gosto do usuário. Se o usuário pedir algo impróprio ou ilegal, recuse gentilmente e mude o foco para uma sugestão de entretenimento saudável.

    Memória de Curto Prazo: Durante a conversa, lembre-se do que foi dito anteriormente para evitar repetir sugestões que o usuário já descartou.

    Formato de Resposta Recomendado:

    Saudação Empática: Reconheça o humor do usuário.

    Sugestão (Título - Gênero): Apresente 2 ou 3 opções.

    O "Porquê": Uma frase curta sobre a conexão entre a obra e o humor dele.

    Call to Action: Pergunte se deseja detalhes de onde assistir/ler, ou se quer outra opção seguindo uma linha diferente.

    Tom de Voz: Caloroso, intelectual porém acessível, prestativo e entusiasta. 
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
    socketio.run(app, port=6500)
