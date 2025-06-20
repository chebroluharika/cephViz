import os
import sys
import streamlit as st
import paramiko
import json
import time
from datetime import datetime

sys.path.append(os.path.abspath(os.path.dirname(__file__) + "/.."))
import agent

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from backend import session_manager

# 🎨 Streamlit Page Configuration
st.set_page_config(page_title="Ceph AI Bot", page_icon="🤖", layout="wide")

# 🎯 Initialize Session State
if "cluster_data" not in st.session_state:
    st.session_state.cluster_data = {}  
    session_manager.cluster_data = {}

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# 🌙 Custom CSS for ChatGPT-Like UI
st.markdown("""
    <style>
    /* Overall background */
    .main {
        background-color: #f8f9fa; /* Light grayish background */
    }

    /* Chat container */
    .stChatContainer {
        border-radius: 8px;
        padding: 10px;
    }

    /* User messages */
    .stChatMessage.user-msg {
        background-color: #e3f2fd;  /* Light Blue */
        color: #212529;  /* Dark Gray */
        border-radius: 8px;
        padding: 10px;
        margin: 5px 0;
    }

    /* Assistant (Bot) messages */
    .stChatMessage.bot-msg {
        background-color: #f1f3f4;  /* Soft Gray */
        color: #212529;  /* Dark Gray */
        border-radius: 8px;
        padding: 10px;
        margin: 5px 0;
    }

    /* Chat Input */
    .stTextArea {
        background-color: #ffffff; /* White input box */
        color: #000000; /* Black text */
    }
    </style>
    """, unsafe_allow_html=True)


# 🎯 Sidebar: Ceph SSH Authentication
with st.sidebar:
    st.markdown("## 🔐 Connect to Ceph Clusters")
    ssh_username = st.text_input("👤 Username", placeholder="Enter SSH username")
    ssh_password = st.text_input("🔒 Password", placeholder="Enter SSH password", type="password")
    cluster_ips = st.text_area("🌍 Cluster IPs", placeholder="Enter one IP per line", height=100)
    connect_button = st.button("🔗 Connect")

    # SSH Connection Function
    def connect_to_clusters():
        if not ssh_username or not ssh_password or not cluster_ips.strip():
            st.error("❌ Please fill in all fields.")
            return

        ip_list = [ip.strip() for ip in cluster_ips.split("\n") if ip.strip()]
        failed_ips = {}

        for ip in ip_list:
            if ip in [data["ip"] for data in st.session_state.cluster_data.values()]:
                continue  # Prevent duplicates
            
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                ssh.connect(ip, username=ssh_username, password=ssh_password, timeout=5)
                cluster_name = f"Cluster {len(st.session_state.cluster_data) + 1}"
                st.session_state.cluster_data[cluster_name] = {"ip": ip, "session": ssh}
                session_manager.cluster_data = st.session_state.cluster_data
            except Exception as e:
                failed_ips[ip] = str(e)

        if failed_ips:
            for ip, error in failed_ips.items():
                st.error(f"❌ Failed to connect to {ip}: {error}")
        else:
            st.success("✅ Connected successfully!")

    if connect_button:
        connect_to_clusters()

    # 🔗 Display Connected Clusters
    if st.session_state.cluster_data:
        st.markdown("### ✅ Connected Clusters")
        selected_clusters = st.multiselect(
            "Select clusters to disconnect:",
            list(st.session_state.cluster_data.keys()),
            key="selected_disconnect"
        )
        if st.button("❌ Disconnect Selected"):
            for cluster in selected_clusters:
                session = st.session_state.cluster_data[cluster].get("session")
                if session:
                    session.close()
                del st.session_state.cluster_data[cluster]
            st.success("✅ Disconnected successfully!")
            # st.rerun()
        
        for cluster, details in st.session_state.cluster_data.items():
            st.markdown(f"✅ **{cluster}:** `{details['ip']}`")

# 🎯 Main Chat Interface
st.markdown("<h1 style='text-align: center;'>🤖 Ceph AI Chatbot</h1>", unsafe_allow_html=True)

# Display Chat Messages in Styled Bubbles
for message in st.session_state.chat_history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 🎯 Quick Action Buttons
# 🎯 Quick Action Buttons
st.markdown("### ⚡ Quick Actions")
quick_actions = {
    "Check Cluster Health": "ceph health",
    "Get Cluster Status": "ceph status",
    "Check OSD Status": "ceph osd tree",
    "Check Monitor Quorum": "ceph quorum_status",
    "Get CephFS Status": "ceph fs status"
}

cols = st.columns(len(quick_actions))
for i, (label, command) in enumerate(quick_actions.items()):
    if cols[i].button(label):
        # Append the user's quick action to the chat history
        st.session_state.chat_history.append({"role": "user", "content": f"**{label}**"})
        
        # Process the query using the agent
        response = agent.process_query(command, cluster_data=st.session_state.cluster_data)

        # Ensure response is a dict and extract the output correctly
        if isinstance(response, dict) and "output" in response:
            ai_reply = response["output"]
        else:
            ai_reply = str(response)  # Convert to string if not a dictionary

        # Append the assistant's response to the chat history
        st.session_state.chat_history.append({"role": "assistant", "content": ai_reply})
        
        # Force a rerun to update the UI
        st.rerun()

# 🎤 Chat Input
prompt = st.chat_input("💬 Type your message here...")

if prompt:
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    
    # Processing response
    with st.spinner("🤔 Thinking..."):
        response = agent.process_query(prompt, cluster_data=st.session_state.cluster_data)
        if isinstance(response, str):
            try:
                response = json.loads(response)  # Convert string to JSON if possible
            except json.JSONDecodeError:
                response = {"output": response}
        
        ai_reply = response.get("output", "⚠️ Unexpected response format")
        st.session_state.chat_history.append({"role": "assistant", "content": ai_reply})
        st.rerun()

# 🔄 Clear Chat Button
if st.session_state.chat_history:
    if st.button("🗑️ Clear Chat"):
        st.session_state.chat_history = []
        st.rerun()