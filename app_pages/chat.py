import streamlit as st

from mofchat.ui import get_agent, render_response

st.title("MOFChat", anchor=False)
st.caption("Ask for MOFs in plain English. Every number shown comes from the 12,020-MOF CoRE-MOF database; "
           "the plan, SQL and validation are shown under each answer.")

SUGGESTIONS = {
    ":material/filter_alt: Surface area > 4000 and void fraction > 0.8":
        "Find me 3 MOFs with a surface area greater than 4000 and a void fraction greater than 0.8",
    ":material/co2: Best MOFs for CO2 capture": "Recommend MOFs for CO2 capture",
    ":material/balance: Zinc MOFs: high surface area, low density":
        "Which zinc MOFs have high surface area and low density?",
    ":material/compare_arrows: MOFs similar to HKUST-1": "Find MOFs similar to HKUST-1",
    ":material/science: Separate CO2 from N2": "Which MOFs could separate CO2 from N2 by size?",
    ":material/help: What is pore limiting diameter?": "What is the pore limiting diameter and why does it matter?",
}

agent = get_agent(st.session_state.get("use_llm", True), st.session_state.get("planner_mode", "hybrid"),
                  st.session_state.get("model_id"))
show_details = st.session_state.get("show_details", True)

prompt = st.chat_input("e.g. Cu MOFs with open metal sites and PLD between 4 and 6 Å", submit_mode="disable")
if not st.session_state.messages:
    picked = st.pills("Try asking", list(SUGGESTIONS), label_visibility="collapsed", key="suggestion")
    if picked:
        prompt = SUGGESTIONS[picked]
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.rerun()

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.markdown(msg["content"])
        else:
            render_response(msg["content"], show_details)

if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    with st.chat_message("assistant"):
        with st.spinner("Planning, querying the database and checking the answer…"):
            response = agent.answer(st.session_state.messages[-1]["content"])
        render_response(response, show_details)
    st.session_state.messages.append({"role": "assistant", "content": response})
