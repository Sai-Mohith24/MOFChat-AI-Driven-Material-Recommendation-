import streamlit as st
import os
from agent_core import MOFHybridAgent

# Configure Streamlit page
st.set_page_config(
    page_title="MOFChat: AI-Driven Material Recommendation",
    page_icon="🧪",
    layout="centered"
)

# Load the hybrid agent using st.cache_resource to avoid re-initialization
@st.cache_resource
def load_agent():
    # Verify prerequisites exist
    if not os.path.exists("hmof.db"):
        st.error("Database 'hmof.db' not found. Please run setup_db.py first.")
        st.stop()
    if not os.path.exists("faiss_mof_index"):
        st.error("Vector store 'faiss_mof_index' not found. Please run setup_vectorstore.py first.")
        st.stop()
        
    return MOFHybridAgent()

st.title("MOFChat: AI-Driven Material Recommendation 🧪")
st.markdown("Ask questions about Metal-Organic Frameworks (MOFs) to get recommendations based on domain knowledge and physical properties.")

# Initialize the agent
agent = load_agent()

# Initialize chat history in session state
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# React to user input
if prompt := st.chat_input("E.g., 'Find MOFs suitable for CO2 capture with surface area > 3000'"):
    
    # Display user message in chat message container
    st.chat_message("user").markdown(prompt)
    
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Display a loading spinner while the agent processes the request
    with st.spinner("Analyzing hMOF database & vector store..."):
        response = agent.run(prompt)
        
    # Display assistant response in chat message container
    with st.chat_message("assistant"):
        st.markdown(response)
        
    # Add assistant response to chat history
    st.session_state.messages.append({"role": "assistant", "content": response})
