import streamlit as st
from openai import OpenAI
from st_audiorec import st_audiorec
import os
import sqlite3
import re
import time

# 1. Configurações Iniciais e Interface Limpa
st.set_page_config(page_title="FocoAmigo - Assistente TDAH", page_icon="🧠", layout="centered")

st.title("🧠 FocoAmigo")
st.caption("Sua rotina simplificada com inteligência artificial e recompensas.")

# 2. Funções do Banco de Dados (SQLite) com Pontuação
def conectar_banco():
    return sqlite3.connect("tdah_app.db")

def criar_tabelas():
    conn = conectar_banco()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tarefas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao TEXT NOT NULL,
            concluida INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuario_progresso (
            id INTEGER PRIMARY KEY,
            pontos INTEGER DEFAULT 0
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO usuario_progresso (id, pontos) VALUES (1, 0)")
    conn.commit()
    conn.close()

def obter_pontos():
    conn = conectar_banco()
    cursor = conn.cursor()
    cursor.execute("SELECT pontos FROM usuario_progresso WHERE id = 1")
    resultado = cursor.fetchone()
    conn.close()
    return resultado[0] if resultado else 0

def adicionar_pontos(qtd):
    conn = conectar_banco()
    cursor = conn.cursor()
    cursor.execute("UPDATE usuario_progresso SET pontos = pontos + ? WHERE id = 1", (qtd,))
    conn.commit()
    conn.close()

def salvar_tarefa(descricao):
    conn = conectar_banco()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO tarefas (descricao) VALUES (?)", (descricao,))
    conn.commit()
    conn.close()

def alternar_status_tarefa(id_tarefa, status_atual):
    conn = conectar_banco()
    cursor = conn.cursor()
    novo_status = 1 if status_atual == 0 else 0
    cursor.execute("UPDATE tarefas SET concluida = ? WHERE id = ?", (novo_status, id_tarefa))
    conn.commit()
    conn.close()
    if novo_status == 1:
        adicionar_pontos(10)
        st.toast("⭐ +10 Pontos de Foco!")

def listar_tarefas():
    conn = conectar_banco()
    cursor = conn.cursor()
    cursor.execute("SELECT id, descricao, concluida FROM tarefas")
    dados = cursor.fetchall()
    conn.close()
    return dados

def limpar_todas_tarefas():
    conn = conectar_banco()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tarefas")
    conn.commit()
    conn.close()

# Inicializa o banco de dados
criar_tabelas()

# Exibe o placar de pontos no topo do menu lateral
st.sidebar.markdown(f"## 🏆 Seus Pontos: **{obter_pontos()}**")
API_KEY = st.sidebar.text_input("Insira sua OpenAI API Key", type="password")

if API_KEY:
    client = OpenAI(api_key=API_KEY)

    opcao = st.radio(
        "O que vamos fazer agora?",
        ["Minhas Tarefas & Progresso", "Dividir uma Nova Tarefa", "Organizar Fluxo de Pensamentos", "⏱️ Timer Pomodoro"],
        index=0
    )

    st.divider()

    # --- ABA 1: TAREFAS ---
    if opcao == "Minhas Tarefas & Progresso":
        st.subheader("📋 Suas Micro-tarefas de Hoje")
        tarefas_atuais = listar_tarefas()
        
        if not tarefas_atuais:
            st.info("Você não tem micro-tarefas geradas no momento. Vá em 'Dividir uma Nova Tarefa' para começar!")
        else:
            total = len(tarefas_atuais)
            concluidas = sum(1 for t in tarefas_atuais if t[2] == 1)
            porcentagem = concluidas / total if total > 0 else 0.0
            
            st.write(f"Progresso Atual: **{concluidas}/{total}** tarefas feitas")
            st.progress(porcentagem)
            
            if porcentagem == 1.0:
                st.success("🎉 Incrível! Você completou tudo o que planejou!")
                st.balloons()

            st.write("---")

            for id_t, desc, concluida in tarefas_atuais:
                checado = True if concluida == 1 else False
                if st.checkbox(desc, value=checado, key=f"check_{id_t}"):
                    if not checado:
                        alternar_status_tarefa(id_t, 0)
                        st.rerun()
                else:
                    if checado:
                        alternar_status_tarefa(id_t, 1)
                        st.rerun()

            st.write("---")
            if st.button("🗑️ Limpar Painel e Recomeçar"):
                limpar_todas_tarefas()
                st.rerun()

    # --- ABA 2: DIVIDIR TAREFA ---
    elif opcao == "Dividir uma Nova Tarefa":
        st.subheader("🎙️ Entrada por Voz ou Texto")
        audio_gravado = st_audiorec()
        texto_transcrito = ""

        if audio_gravado is not None:
            with st.spinner("Transcrevendo sua voz..."):
                try:
                    nome_arquivo_temp = "temp_audio.wav"
                    with open(nome_arquivo_temp, "wb") as f:
                        f.write(audio_gravado)
                    with open(nome_arquivo_temp, "rb") as arquivo_audio:
                        transcricao = client.audio.transcriptions.create(model="whisper-1", file=arquivo_audio)
                    texto_transcrito = transcricao.text
                    st.success(f"Entendido: \"{texto_transcrito}\"")
                    os.remove(nome_arquivo_temp)
                except Exception as e:
                    st.error(f"Erro ao processar áudio: {e}")

        valor_padrao = texto_transcrito if texto_transcrito else ""
        input_usuario = st.text_input("Qual tarefa vamos simplificar?", value=valor_padrao)
        
        if st.button("Destrinchar e Salvar no Meu Dia ✨") and input_usuario:
            with st.spinner("A IA está desconstruindo a meta em passos fáceis..."):
                prompt = (
                    f"O usuário tem TDAH e está paralisado diante desta tarefa: '{input_usuario}'. "
                    "Quebre-a em 3 a 5 passos sequenciais extremamente fáceis e curtos. "
                    "Escreva APENAS a lista com cada item iniciando com um traço '-', sem introduções ou comentários."
                )
                response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
                resposta_texto = response.choices.message.content
                
                linhas = resposta_texto.split('\n')
                items_salvos = 0
                for linha in linhas:
                    item_limpo = re.sub(r'^[-\d.\s*]+', '', linha).strip()
                    if item_limpo:
                        salvar_tarefa(item_limpo)
                        items_salvos += 1
                if items_salvos > 0:
                    st.success(f"Sucesso! {items_salvos} passos simples adicionados.")
                    st.rerun()

    # --- ABA 3: BRAIN DUMP ---
    elif opcao == "Organizar Fluxo de Pensamentos":
        st.subheader("📝 Despejo de Ideias (Brain Dump)")
        input_pensamentos = st.text_area("Despeje os pensamentos aqui:", height=150)
        
        if st.button("Organizar Mente 🪄") and input_pensamentos:
            with st.spinner("Estruturando as informações..."):
                prompt = (
                    f"O usuário fez um 'brain dump' por ansiedade ou distração do TDAH:\n'{input_pensamentos}'\n\n"
                    "Organize esse texto em tópicos curtos e claros: 1. Prioridades Urgentes (Fazer hoje), "
                    "2. Ideias Importantes e 3. Lembretes para depois. Evite blocos grandes de texto."
                )
                response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
                st.write(response.choices.message.content)

    # --- ABA 4: POMODORO ---
    elif opcao == "⏱️ Timer Pomodoro":
        st.subheader("⏱️ Cronômetro de Foco Inteligente")
        tipo_timer = st.selectbox("Escolha o ritmo de foco:", ["25 minutos de Foco / 5 de Descanso", "15 minutos de Foco / 3 de Descanso"])
        minutos_foco = 25 if "25" in tipo_timer else 15
        minutos_pausa = 5 if "25" in tipo_timer else 3
        
        col1, col2 = st.columns(2)
        with col1: botao_foco = st.button("🔥 Iniciar Bloco de Foco")
        with col2: botao_pausa = st.button("☕ Iniciar Pausa Curta")
            
        placeholder_timer = st.empty()
        placeholder_barra = st.empty()

        if botao_foco:
            tempo_total_segundos = minutos_foco * 60
            for segundos_restantes in range(tempo_total_segundos, -1, -1):
                mins, segs = divmod(segundos_restantes, 60)
                placeholder_timer.metric(label="Tempo Restante", value=f"{mins:02d}:{segs:02d}")
                placeholder_barra.progress((tempo_total_segundos - segundos_restantes) / tempo_total_segundos)
                time.sleep(1)
            adicionar_pontos(25)
            st.success("🎯 Foco concluído! +25 Pontos adicionados!")
            st.balloons()
            time.sleep(2)
            st.rerun()

        if botao_pausa:
            tempo_total_segundos = minutos_pausa * 60
            for segundos_restantes in range(tempo_total_segundos, -1, -1):
                mins, segs = divmod(segundos_restantes, 60)
                placeholder_timer.metric(label="Pausa", value=f"{mins:02d}:{segs:02d}")
                placeholder_barra.progress((tempo_total_segundos - segundos_restantes) / tempo_total_segundos)
                time.sleep(1)
            st.rerun()
else:
    st.warning("Por favor, insira sua chave de API da OpenAI na barra lateral para começar.")
