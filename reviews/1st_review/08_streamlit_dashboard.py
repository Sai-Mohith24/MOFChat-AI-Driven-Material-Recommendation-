"""
08_streamlit_dashboard.py

This is the frontend UI for our MOFChat AI assistant. 
It wraps the Tabular RAG architecture (from script 07) into an interactive web interface 
so that materials scientists can chat with the database without writing any code.

To run this file, open your terminal and run:
streamlit run 08_streamlit_dashboard.py
"""

import streamlit as st
import os
import sys

# Add the parent directory to Python path so we can import the original agent_core
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

try:
    from agent_core import MOFHybridAgent
except ImportError:
    st.error("Could not import MOFHybridAgent. Make sure this script is run from the correct directory.")
    st.stop()

# Configure Streamlit page UI
st.set_page_config(
    page_title="MOFChat: AI-Driven Material Recommendation",
    page_icon="🧪",
    layout="centered"
)

# Load the hybrid agent. We use @st.cache_resource so it doesn't reload the 
# heavy LLM and FAISS databases every time the user types a new message.
@st.cache_resource
def load_agent():
    # We change the working directory temporarily so FAISS can find the indexes in the parent folder
    original_cwd = os.getcwd()
    target_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    os.chdir(target_dir)
    
    try:
        agent = MOFHybridAgent()
    except Exception as e:
        os.chdir(original_cwd)
        st.error(f"Failed to load AI Agent: {str(e)}")
        st.stop()
        
    os.chdir(original_cwd)
    return agent

st.title("MOFChat: Tabular RAG Dashboard 🧪")
st.markdown("""
**Welcome to the future of Materials Discovery.**
This dashboard uses a Deep Learning *FT-Transformer* combined with *Llama 3* 
to instantly search 12,020 MOFs using natural language.
""")

# Initialize the AI agent
agent = load_agent()

# Session state to remember the chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display previous chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# React to user input
if prompt := st.chat_input("E.g., 'Find MOFs with surface area > 4000 and low density'"):
    
    # 1. Show user message on screen
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # 2. Process query with a loading spinner
    with st.spinner("🤖 Applying FT-Transformer & Llama 3 Reasoning..."):
        try:
            response = agent.answer_query(prompt)
        except Exception as e:
            response = f"An error occurred during inference: {str(e)}"
            
    # 3. Show AI response on screen
    with st.chat_message("assistant"):
        st.markdown(response)
    st.session_state.messages.append({"role": "assistant", "content": response})

