import json
import os
import re
import sys
import warnings
from typing import Any, Dict

import paramiko

# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Add the parent directory to sys.path to access Backend/
from .backend import session_manager
from .backend.functionality import (
    CephOperations,  # Import CephOperations from backend.py
)
from dotenv import load_dotenv
from langchain.agents import AgentType, initialize_agent
from langchain.memory import ConversationBufferMemory
from langchain.tools import Tool
from langchain_community.llms import Ollama
from pydantic import BaseModel, Field

# Load environment variables
load_dotenv()

# # Global variable to store the last used cluster
last_used_cluster = None

# Suppress specific FutureWarnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Suppress Paramiko warnings
# paramiko.util.log_to_file("/dev/null")  # Redirects logs to /dev/null (Linux/macOS)

HUGGINGFACEHUB_API_TOKEN = os.getenv("HUGGINGFACEHUB_API_TOKEN")

# Initialize Ceph operations
ceph_ops = CephOperations()

# In-memory storage for cluster mappings (Cluster 1 → IP)
# TODO: Persist this in a file or DB to retain connections after restart
cluster_mapping = {}


class DynamicModel(BaseModel):
    # Use a dictionary to hold arbitrary fields
    data: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        # Allow arbitrary types of data
        arbitrary_types_allowed = True


# Function to parse the raw response dynamically
def parse_dynamic_data(raw_data: Any) -> DynamicModel:
    try:
        # If raw_data is a string, you may need to convert it into a dictionary or another structure
        if isinstance(raw_data, str):
            # Example conversion: You could split the string into a dict based on patterns
            # This is a basic example that assumes the string is a list of key-value pairs
            # Customize this to match the expected structure of the raw output.
            raw_data = {
                "output": raw_data
            }  # Assuming the string represents some "output"

        # Now that the data is in a dictionary format, parse it using DynamicModel
        if isinstance(raw_data, dict):
            return DynamicModel(data=raw_data)
        else:
            raise ValueError("Expected raw_data to be a dictionary.")
    except Exception as e:
        return {"status": "error", "message": f"Failed to parse data: {str(e)}"}


def format_dynamic_output(parsed_data: Any) -> str:
    # Check if the data is a DynamicModel instance
    if isinstance(parsed_data, DynamicModel):
        parsed_data = parsed_data.data  # Extract the 'data' attribute

    formatted_output = "Response:\n"

    # If the parsed data is still a dictionary, process it
    if isinstance(parsed_data, dict):
        for key, value in parsed_data.items():
            if isinstance(value, dict):
                formatted_output += f"**{key}**: \n"
                formatted_output += format_dynamic_output(
                    DynamicModel(data=value)
                )  # Recursive formatting
            elif isinstance(value, list):
                formatted_output += f"**{key}**: \n"
                for idx, item in enumerate(value):
                    formatted_output += f"  - {idx}: {item}\n"
            else:
                formatted_output += f"**{key}**: {value}\n"
    else:
        formatted_output += "⚠️ Invalid response format.\n"

    return formatted_output


# Tool Functions
def debug_tool_execution(action_name, action_input):
    """Debug function to print tool execution details."""
    print(f"\n🔍 DEBUG: Tool Called -> {action_name}")
    print(f"🔹 Input Passed: {action_input}")


def connect_cluster(cluster_name, cluster_ip):
    """Prompts user for cluster details, connects via SSH, and stores session in session manager."""
    # Prompt user for cluster details
    # cluster_name = input("🔗 Enter cluster name (e.g., Cluster 1): ").strip()
    # cluster_ip = input("🌐 Enter cluster IP: ").strip()
    username = "root"
    password = "passwd"
    # username = input("🔑 Enter your username: ").strip()
    # password = getpass.getpass("🔒 Enter your password: ").strip()

    print(f"🚀 Attempting to connect {cluster_name} ({cluster_ip})...")

    # Check if cluster is already connected
    if cluster_name in session_manager.cluster_data:
        return json.dumps(
            {"status": "success", "message": f"✅ {cluster_name} is already connected."}
        )

    # Attempt SSH connection
    ceph_ops = CephOperations()
    session = ceph_ops.connect_cluster(cluster_ip, username, password)

    if session:
        # Store in session manager with the same format as frontend.py
        session_manager.cluster_data[cluster_name] = {
            "ip": cluster_ip,
            "session": session,  # Store session for later use
        }
        return json.dumps(
            {
                "status": "success",
                "message": f"✅ Connected to {cluster_name} at {cluster_ip}",
            }
        )
    else:
        return json.dumps(
            {
                "status": "error",
                "message": "❌ Connection failed: Authentication failed.",
            }
        )


def fetch_session_of_cluster(cluster_name: str):
    print("Fetches the session of the cluster")
    cluster_info = session_manager.cluster_data.get(cluster_name.strip())
    print("Cluster info: ", cluster_info)
    print("Cluster sessions: ", session_manager.cluster_data.get(cluster_name))
    if not cluster_info:
        return json.dumps(
            {
                "status": "error",
                "message": f"❌ No active session for {cluster_name}. Connect first.",
            }
        )

    cluster_session = cluster_info.get("session")
    if not cluster_session:
        return json.dumps(
            {
                "status": "error",
                "message": f"❌ No active session object found for {cluster_name}.",
            }
        )

    print("Inside fetch session: ", type(cluster_session))
    return cluster_session


def get_cluster_status(cluster_name: str):
    """Fetches Ceph cluster status using the cluster_name as parameter"""
    cluster_name = (
        re.search(r"Cluster \d+", cluster_name).group()
        if re.search(r"Cluster \d+", cluster_name)
        else "Cluster 1"
    )
    print(f"🚀 Entered get_cluster_status() for {cluster_name}")
    try:
        return ceph_ops.get_cluster_status(fetch_session_of_cluster(cluster_name))

    except Exception as e:
        return json.dumps(
            {"status": "error", "message": f"❌ Failed to execute command: {str(e)}"}
        )


def get_cluster_health(cluster_name: str):
    """Fetches the health status of a Ceph cluster using the cluster_name as parameter"""
    cluster_name = (
        re.search(r"Cluster \d+", cluster_name).group()
        if re.search(r"Cluster \d+", cluster_name)
        else "Cluster 1"
    )
    print(f"🚀 Entered get_cluster_health() for {cluster_name}")
    try:
        session = fetch_session_of_cluster(cluster_name)
        print(session)
        print(type(session))
        return ceph_ops.get_cluster_health(session)

    except Exception as e:
        return json.dumps(
            {"status": "error", "message": f"❌ Failed to execute command: {str(e)}"}
        )


def osd_status(cluster_name: str):
    """Fetches the status of OSDs in a Ceph cluster using the cluster_name as parameter"""
    cluster_name = (
        re.search(r"Cluster \d+", cluster_name).group()
        if re.search(r"Cluster \d+", cluster_name)
        else "Cluster 1"
    )
    print(f"🚀 Entered get_osds() for {cluster_name}", flush=True)
    try:
        output = ceph_ops.osd_status(fetch_session_of_cluster(cluster_name))

        # osd_data = output.get('output', '')
        # error_msg = output.get('error', '')

        # if error_msg:
        #     return f"⚠️ **Error fetching OSDs**: {error_msg}"

        # if not osd_data:
        #     return f"❌ No OSD data available for {cluster_name}."

        # parsed_data = parse_dynamic_data(osd_data)
        # formatted_output = format_dynamic_output(parsed_data)
        print(output)
        # print(output['OSDs'])
        print(type(output))
        # Generate a formatted string for each OSD
        formatted_osds = [
            f"Host: {osd['host name']}, ID: {osd['id']}, Used: {osd['kb used']}, State: {', '.join(osd['state'])}"
            for osd in output["output"]["OSDs"]
        ]

        # Join the formatted strings into a single response
        return {
            "message": f"📌 **List of Object Storage Daemons (OSDs) for {cluster_name} for multiple hostnames:**",
            "OSD_Summary": "\n".join(formatted_osds),
        }
        # for osd in output["output"]["OSDs"]:
        #     print(f"Host: {osd['host name']}, ID: {osd['id']}, Used: {osd['kb used']}, State: {', '.join(osd['state'])}")

        # return f"📌 **List of Object Storage Deamons(OSDs) for {cluster_name} for multiple hostnames:** Here is the summary: \n\n{output['output']['OSDs']}\n"

    except Exception as e:
        return json.dumps(
            {"status": "error", "message": f"❌ Failed to execute command: {str(e)}"}
        )


def list_filesystems(cluster_name: str):
    """Lists all CephFS filesystems using the cluster_name as parameter."""
    cluster_name = (
        re.search(r"Cluster \d+", cluster_name).group()
        if re.search(r"Cluster \d+", cluster_name)
        else "Cluster 1"
    )
    print(f"🚀 Entered list_filesystems() for {cluster_name}")
    try:
        output = ceph_ops.list_filesystems(fetch_session_of_cluster(cluster_name))

        # Extract relevant information from the output
        if output and isinstance(output, dict):
            fs_info = output.get("output", "No filesystem info available")
            # error_info = output.get('error', '')

            # Format the string nicely
            # result = f"\n📂 **Filesystem List** for {cluster_name}:\n"
            # result += f"  - {fs_info}\n"

            # if error_info:
            #     result += f"⚠️ **Error**: {error_info}\n"
            # else:
            #     result += "\n✅ Filesystem information retrieved successfully."

            return fs_info

        return f"❌ No data returned from {cluster_name}."

    except Exception as e:
        return json.dumps(
            {"status": "error", "message": f"❌ Failed to execute command: {str(e)}"}
        )


def get_filesystem_metadata(cluster_name: str, fs_name: str):
    """Fetches metadata information for a Ceph filesystem using the cluster_name and file system name as a parameter from the user"""
    cluster_name = (
        re.search(r"Cluster \d+", cluster_name).group()
        if re.search(r"Cluster \d+", cluster_name)
        else "Cluster 1"
    )
    print(f"🚀 Entered get_filesystem_metadata() for {cluster_name}")
    try:
        return ceph_ops.get_filesystem_metadata(
            fetch_session_of_cluster(cluster_name, fs_name)
        )
    except Exception as e:
        return json.dumps(
            {"status": "error", "message": f"❌ Failed to execute command: {str(e)}"}
        )


def get_filesystem_info(cluster_name: str, fs_name="cephfs"):
    """Fetches filesystem info using the cluster_name as parameter"""
    cluster_name = (
        re.search(r"Cluster \d+", cluster_name).group()
        if re.search(r"Cluster \d+", cluster_name)
        else "Cluster 1"
    )
    print(f"🚀 Entered get_filesystem_info() for {cluster_name}")
    try:
        return ceph_ops.get_filesystem_info(
            fetch_session_of_cluster(cluster_name), fs_name
        )
    except Exception as e:
        return json.dumps(
            {"status": "error", "message": f"❌ Failed to execute command: {str(e)}"}
        )


def list_mds_nodes(cluster_name: str):
    """Lists MDS nodes, state, pool availability and its usage for CephFS using the cluster_name as parameter"""
    cluster_name = (
        re.search(r"Cluster \d+", cluster_name).group()
        if re.search(r"Cluster \d+", cluster_name)
        else "Cluster 1"
    )
    print(f"🚀 Entered list_mds_nodes() for {cluster_name}")
    try:
        return ceph_ops.list_mds_nodes(fetch_session_of_cluster(cluster_name))
    except Exception as e:
        return json.dumps(
            {"status": "error", "message": f"❌ Failed to execute command: {str(e)}"}
        )


def get_mds_perf(cluster_name: str):
    """Gets MDS performance for CephFS using the cluster_name as parameter"""
    cluster_name = (
        re.search(r"Cluster \d+", cluster_name).group()
        if re.search(r"Cluster \d+", cluster_name)
        else "Cluster 1"
    )
    print(f"🚀 Entered get_mds_perf() for {cluster_name}")
    try:
        return ceph_ops.get_mds_perf(fetch_session_of_cluster(cluster_name))
    except Exception as e:
        return json.dumps(
            {"status": "error", "message": f"❌ Failed to execute command: {str(e)}"}
        )


def list_filesystem_clients(cluster_name: str):
    """Lists all active CephFS clients using the cluster_name as parameter"""
    cluster_name = (
        re.search(r"Cluster \d+", cluster_name).group()
        if re.search(r"Cluster \d+", cluster_name)
        else "Cluster 1"
    )
    print(f"🚀 Entered list_filesystem_clients() for {cluster_name}")
    try:
        return ceph_ops.list_filesystem_clients(fetch_session_of_cluster(cluster_name))
    except Exception as e:
        return json.dumps(
            {"status": "error", "message": f"❌ Failed to execute command: {str(e)}"}
        )


def get_active_mds(cluster_name: str):
    """Checks which MDS nodes are active and standby using the cluster_name as parameter"""
    cluster_name = (
        re.search(r"Cluster \d+", cluster_name).group()
        if re.search(r"Cluster \d+", cluster_name)
        else "Cluster 1"
    )
    print(f"🚀 Entered get_active_mds() for {cluster_name}")
    try:
        return ceph_ops.get_active_mds(fetch_session_of_cluster(cluster_name))
    except Exception as e:
        return json.dumps(
            {"status": "error", "message": f"❌ Failed to execute command: {str(e)}"}
        )


def get_filesystem_performance(cluster_name: str):
    """Fetches CephFS performance metrics using the cluster_name as parameter"""
    cluster_name = (
        re.search(r"Cluster \d+", cluster_name).group()
        if re.search(r"Cluster \d+", cluster_name)
        else "Cluster 1"
    )
    print(f"🚀 Entered get_filesystem_performance() for {cluster_name}")
    try:
        return ceph_ops.get_filesystem_performance(
            fetch_session_of_cluster(cluster_name)
        )
    except Exception as e:
        return json.dumps(
            {"status": "error", "message": f"❌ Failed to execute command: {str(e)}"}
        )


def get_mds_memory_usage(cluster_name: str):
    """Gets MDS memory usage for CephFS using the cluster_name as parameter"""
    cluster_name = (
        re.search(r"Cluster \d+", cluster_name).group()
        if re.search(r"Cluster \d+", cluster_name)
        else "Cluster 1"
    )
    print(f"🚀 Entered get_mds_memory_usage() for {cluster_name}")
    try:
        return ceph_ops.get_mds_memory_usage(fetch_session_of_cluster(cluster_name))
    except Exception as e:
        return json.dumps(
            {"status": "error", "message": f"❌ Failed to execute command: {str(e)}"}
        )


def get_cephfs_metadata_pool_usage(cluster_name: str, fs_name: str):
    """Gets CephFS metadata pool usage using the cluster_name as parameter"""
    cluster_name = (
        re.search(r"Cluster \d+", cluster_name).group()
        if re.search(r"Cluster \d+", cluster_name)
        else "Cluster 1"
    )
    print(f"🚀 Entered get_cephfs_metadata_pool_usage() for {cluster_name}")
    try:
        return ceph_ops.get_cephfs_metadata_pool_usage(
            fetch_session_of_cluster(cluster_name), fs_name
        )
    except Exception as e:
        return json.dumps(
            {"status": "error", "message": f"❌ Failed to execute command: {str(e)}"}
        )

# Use all the tools

# Define AI Tools
tools = [
    Tool(
        name="Get Cluster Status",
        func=get_cluster_status,
        description=(
            "Fetch the current Ceph cluster status by providing 'cluster_name'. Ensure the response includes basic info about the cluster. Retrieve the info such as id, health, services such as mon, mgr, mds, osd, pools and volumes for both the Cluster 1 and Cluster 2. Retrieve the key metrics and show in structured format. Summarise with the data avaialble"
            # "Retrieve Key Metrics and Actionable Insights from the data."
        ),
        force_execute=True,
    ),
    Tool(
        name="Get Cluster Health",
        func=get_cluster_health,
        description="Gets the health status of a Ceph cluster. Provide 'cluster_name'. Retrieve Key Metrics and Actionable Insights from the data",
    ),
    Tool(
        name="Get OSD status",
        func=osd_status,
        description="Retrieves status of OSDs in the Ceph cluster. Provide 'cluster_name'. Extract the relevant information from the output, such as the number of hosts and their respective statuses, kb used along with id. Update in table format with columns as 'Host', 'id', 'kb used', 'state' along with the individual entries.",
        force_execute=True,  # Always force execution of tool
    ),
    Tool(
        name="List Filesystems",
        func=list_filesystems,
        description="List all CephFS filesystems. Provide 'cluster_name'. Retrieves 'name', 'metadata pools', 'data pools'. You must always use the available tools to get fresh information. Do not assume previous results are still valid. If a tool exists to fetch data, always use it instead of relying on memory.",
        # return_direct=True
        force_execute=True,  # Always force execution of tools
    ),
    Tool(
        name="Get Filesystem Metadata",
        func=get_filesystem_metadata,
        description="Retrieve metadata information for a Ceph filesystem. Provide 'cluster_name' and 'fs_name'. The fs_name is identified from the query. If file system (fs) name is missing, ask the user to provide, or if you agent can fetch the file system name from previous command use one of the file system name. Extract the values of all and display in readbale format for the user",
    ),
    Tool(
        name="Get Filesystem Info",
        func=get_filesystem_info,
        description="Retrieve information about a Ceph filesystem. Provide 'cluster_name' and available 'fs name'",
    ),
    Tool(
        name="List MDS Nodes",
        func=list_mds_nodes,
        description="""List all MDS nodes for CephFS. Provide 'cluster_name'. 
        Analyze the following Ceph FS metadata and return a structured JSON output summarizing the key metrics:

        1. **MDS Nodes**:
        - List all active and standby MDS nodes.
        - Include relevant details such as `name`, `rank`, `state`, `dirs`, `inos`, and `rate`.

        2. **Filesystem Clients**:
        - Provide filesystem names (`fs`) and the number of clients connected.

        3. **Storage Pools**:
        - List each pool with details such as `name`, `type`, `available space`, and `used space`.

        4. **MDS Version Information**:
        - Include the Ceph version and the associated daemon names.""",
    ),
    Tool(
        name="Get MDS Performance",
        func=get_mds_perf,
        description="Get performance details of CephFS MDS nodes. Provide 'cluster_name'",
    ),
    Tool(
        name="List Filesystem Clients",
        func=list_filesystem_clients,
        description="List all active CephFS clients. Provide 'cluster_name'",
    ),
    Tool(
        name="Get Active MDS",
        func=get_active_mds,
        description="Check which MDS nodes are active and standby. Provide 'cluster_name'",
    ),
    Tool(
        name="Get Filesystem Performance",
        func=get_filesystem_performance,
        description="Retrieve CephFS performance metrics. Provide 'cluster_name'",
    ),
    Tool(
        name="Get MDS Memory Usage",
        func=get_mds_memory_usage,
        description="Retrieve memory usage of MDS nodes. Provide 'cluster_name'",
    ),
    Tool(
        name="Get CephFS Metadata Pool Usage",
        func=get_cephfs_metadata_pool_usage,
        description="Get metadata pool usage for a CephFS. Provide 'cluster_name' and available 'fs name'",
    ),
]

# Memory for Chat History
memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

# agent_prompt = """You are a Ceph management assistant. Only answer questions related to Ceph cluster status, health, storage, and performance.
# If a query is unrelated to Ceph, respond with: 'I can only assist with Ceph-related queries.'

# - If the user asks to **connect** to a cluster (e.g., "Connect to Cluster 1" or "Establish connection to Cluster 1"), always use `Connect`.
# - If the user asks for **cluster health** (e.g., "Check Cluster 1 health" or "Get health status"), always use `Get Cluster Health`.
# - If the user asks for **cluster status** (e.g., "What is the status of Cluster 1?"), always use `Get Cluster Status`.
# - If the user asks to **list OSDs** (e.g., "List OSDs of Cluster 1?"), use `List OSDs`.

# Do not make assumptions. Only respond with the correct tool.
# Do NOT guess. Only respond using the correct tool.


# """
agent_prompt = """
You are a Ceph management assistant. Only answer questions related to Ceph clusters. 
If a query is unrelated to Ceph, respond with: 'I can only assist with Ceph-related queries.'
Each time you are queried about a specific cluster (e.g., 'Cluster 1' or 'Cluster 2'),ensure that you fetch the latest session information and context for that cluster.
If you are asked to execute a command, always execute and not reuse.

- If the user asks to **connect** to a cluster (e.g., "Connect to Cluster 1" or "Establish connection to Cluster 1"), always use `Connect`.
- If the user asks for **cluster health** (e.g., "Check Cluster 1 health" or "Get health status"), always use `Get Cluster Health`.
- If the user asks for **cluster status** (e.g., "What is the status of Cluster 1?"), always use `Get Cluster Status`.
- If the user asks for **osd status** (e.g., "What is the status of OSD in Cluster 1?"), always use `Get OSD Status`.
- If the user asks to **list filesystems** (e.g., "List Filesystems of Cluster 1"), use `List Filesystems`.
- If the user asks for **filesystem metadata** (e.g., "Get metadata for CephFS on Cluster 1"), use `Get Filesystem Metadata`.
- If the user asks for **filesystem info** (e.g., "What is the info for CephFS on Cluster 1?"), use `Get Filesystem Info`.
- If the user asks to **list MDS nodes** (e.g., "List MDS nodes of Cluster 1?"), use `List MDS Nodes`.
- If the user asks for **MDS performance** (e.g., "Check MDS performance of Cluster 1"), use `Get MDS Performance`.
- If the user asks to **list filesystem clients** (e.g., "List active clients for Cluster 1"), use `List Filesystem Clients`.
- If the user asks for **active MDS nodes** (e.g., "Check active MDS nodes in Cluster 1"), use `Get Active MDS`.
- If the user asks for **filesystem performance** (e.g., "Get performance stats for CephFS on Cluster 1"), use `Get Filesystem Performance`.
- If the user asks for **MDS memory usage** (e.g., "What is the MDS memory usage for Cluster 1?"), use `Get MDS Memory Usage`.
- If the user asks for **CephFS metadata pool usage** (e.g., "Check metadata pool usage for CephFS on Cluster 1"), use `Get CephFS Metadata Pool Usage`.

For every response:

1. Think about the best course of action for the given query.
2. First, provide the `Thought:` on how the query relates to the Ceph task and any observations you make.
3. Afterward, provide the `Action:` that you will take in response to the user's query, such as calling a specific tool or performing a task. 

How to represent the data to the user?
Given the JSON output or Python Dictionary from a Ceph command, generate a well-structured and concise summary in a human-readable format. The summary should include:

1. **High-Level Overview**  
   - What this data represents (e.g., cluster status, storage usage, client connections, etc.).  
   
2. **Key Metrics & Details**  
   - List all relevant details such as connected clients, metadata servers (MDS), object storage devices (OSDs), pools, cluster health, and performance statistics.  
   - Convert bytes to MB/GB where applicable for better readability.  
   - Categorize active vs. standby components where necessary.  

3. **Health & Error Reporting**  
   - Highlight any warnings, errors, or anomalies in the cluster.  
   - If no issues are found, explicitly state that the cluster is healthy.  

4. **Actionable Insights**  
   - If possible, suggest any recommended actions based on the data (e.g., "Consider adding more OSDs if storage utilization is above 80%").  

Ensure that the output is formatted using **sections, bullet points, and human-friendly wording**. Do not include unnecessary JSON or code; just provide the summary. 

When the user asked to Compare the results and status?

You will receive a JSON dictionary with 'cluster_name' keys:  
- `"Cluster 1"`: Contains the respective details of the first cluster.  
- `"Cluster 2"`: Contains the respective details of the second cluster.  

Your task is to **analyze and compare both clusters** by generating a structured, human-readable comparison summary.
Ensure the comparison is structured with **sections, bullet points, and clear formatting**.

Do not make assumptions. Only respond with the correct tool.
Do NOT guess. Only respond using the correct tool.
"""


llm = Ollama(model="llama3.2")


def query_llm(prompt: str):
    return llm.text_generation(prompt, max_new_tokens=1000)


# # generate_params = {GenParams.MAX_NEW_TOKENS: 25}
# model = Model(
#     model_id = "meta-llama/llama-3-3-70b-instruct",  # Specify the model ID
#     credentials={"apikey": os.getenv("WATSONX_API_KEY"), "url":"https://us-south.ml.cloud.ibm.com"},  # Get API key and URL from environment variables
#     # params=generate_params,  # Set generation parameters
#     project_id="377a2200-c8e0-4fe3-8542-76191dcd221f",  # Get project ID from environment variables
# )

# # Wrap the model with WatsonxLLM to use with LangChain
# llm = WatsonxLLM(model=model)

# Initialize AI Agent
agent = initialize_agent(
    tools=tools,
    llm=llm,  # Use the updated ChatHuggingFace model
    agent=AgentType.CONVERSATIONAL_REACT_DESCRIPTION,
    # agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
    memory=memory,
    prompt=agent_prompt,
    verbose=True,
    # max_iterations=5,  # Stop after first response
    handle_parsing_errors=True,
    # stop_token=["\n"],
    temperature=0.9,
    top_k=50,  # Limits the sampled tokens to the top_k most likely ones
    top_p=0.9,  # Nucleus sampling: chooses from top-p tokens (probability mass)
    repetition_penalty=1.2,  # Penalizes repeating tokens in output
    num_return_sequences=1,  # Number of sequences to generate
    no_repeat_ngram_size=2,  # Prevents repetition of n-grams
    do_sample=True,  # Set to True for sampling-based generation (as opposed to greedy)
)


def process_query(query: str, cluster_data):
    """Processes user queries using the AI agent, ensuring active session is used."""
    try:
        print(f"DEBUG: Cluster Data {cluster_data}")
        if not cluster_data:
            return {"output": "⚠️ No active Ceph cluster. Please connect first."}

        # # !!!!!!!! Note: Comment if loop when running via streamlit
        # if len(cluster_data) != 2:
        #     connect_cluster(cluster_name = "Cluster 1", cluster_ip = "10.0.67.46")
        #     # connect_cluster(cluster_name = "Cluster 2", cluster_ip = "10.8.128.21")
        #     connect_cluster(cluster_name = "Cluster 2", cluster_ip = "10.0.64.37")

        print("DEBUG: Cluster Data =", cluster_data)  # Debugging

        cluster_list = get_target_clusters(query, cluster_data)

        if cluster_list:
            print(f"Executing command on: {cluster_list} with query {query}")
        else:
            print("❌ No active session found. Please reconnect.")

        if len(cluster_list) == 1:
            for cluster_name in cluster_list:
                print("Inside process query: ", cluster_name)
                agent_input = {"input": f"Cluster: {cluster_name}\nQuery: {query}"}

            response = agent.invoke(agent_input)
            return response
        else:
            results = {}
            clean_query = re.sub(r"\bCluster\s*\d+\b", "", query).strip()
            for cluster_name in cluster_list:
                agent_input = {
                    "input": f"Cluster: {cluster_name}\nQuery: {clean_query}"
                }
                results[cluster_name] = agent.invoke(agent_input)["output"]
            print("Results: ", results)

            summary_input = {
                "input": (
                    f"{results}\n\n"
                    "Do not use Tool to summarise this."
                    "Compare the cluster status results for the available clusters in the dictionary (e.g., 'Cluster 1', 'Cluster 2'). "
                    "Identify key differences and summarize in a structured format:\n"
                    "- **Overall Cluster Health**: State the health status (e.g., HEALTH_OK, HEALTH_WARN).\n"
                    "- **Key Metrics**: Compare active/standby nodes, OSDs, pools, and object count.\n"
                    "- **Differences & Similarities**: Highlight variations in services, usage, or warnings.\n"
                    "- **Missing Data**: If any cluster's output is missing, acknowledge it.\n"
                    "- **Recommended Actions**: Suggest troubleshooting steps concisely.\n\n"
                    "Keep the summary short, structured, and easy to read."
                )
            }

            if re.search(r"\b(graph|visual)\w*", clean_query):
                json_input = {
                    "input": (
                        f"{results}\n\n"
                        "Analyze the above cluster status results and extract key details in a structured JSON format. "
                        "The output **should not assume predefined fields** but instead dynamically infer all available information. "
                        "Use the following approach:\n\n"
                        "🔹 **Identify clusters**: Extract cluster names dynamically.\n"
                        "🔹 **Extract meaningful metrics**: Identify all measurable parameters reported, such as health status, monitor count, OSD count, storage usage, warnings, etc.\n"
                        "🔹 **Handle missing data**: If certain information is absent, exclude it instead of forcing a placeholder.\n"
                        "🔹 **Ensure valid JSON output**: Return an array of JSON objects, with each cluster represented as a dictionary containing the extracted details.\n\n"
                        "⚠️ Do not assume a fixed structure—only include fields that are explicitly present in the input."
                    )
                }
                json_input_results = agent.invoke(json_input)
                print(f"Graph Input: {json_input_results['output']['clusters']}")

                graph_input = {
                    "input": (
                        f"Given the following structured JSON data:\n{json_input_results['output']['clusters']}\n\n"
                        "🎯 **Task:** Extract numerical values as they appear and generate a simple graphical representation.\n\n"
                        "✅ **Guidelines:**\n"
                        "1️⃣ **Display data as it is:** Do not infer missing values or overprocess the input.\n"
                        "2️⃣ **Choose the best graph type based on available data:**\n"
                        "   - 📊 **Bar Chart**: For comparing values.\n"
                        "   - 📈 **Line Chart**: If time-based trends exist.\n"
                        "   - 🟠 **Pie Chart**: For percentage breakdowns.\n"
                        "3️⃣ **Handle missing data gracefully:**\n"
                        "   - If a metric is missing, exclude it.\n"
                        "   - If no numerical data is available, generate a simple summary instead of failing.\n"
                        "4️⃣ **Output Format:**\n"
                        "   - **ASCII/Unicode Graph**: Simple text-based output.\n"
                        "   - **HTML/SVG Code**: For embedding in a dashboard.\n"
                        "   - **JSON Representation**: For further processing.\n\n"
                        "⚠️ **Important Instructions:**\n"
                        "🔹 **NEVER leave the output empty.** If the data is unclear, provide a minimal summary or a fallback visualization.\n"
                        "🔹 **DO NOT return 'Invalid' or 'Incomplete Response'.** Instead, respond with a simplified textual representation or a message stating what is missing.\n"
                        "🔹 **If unable to generate a graph, return a structured explanation of the available numerical data.**\n\n"
                        "🚀 **Always return something useful, even if the data is limited!**"
                    )
                }
                return agent.invoke(graph_input)  # Let the agent handle comparison
            else:
                return agent.invoke(summary_input)

    except Exception as e:
        return f"⚠️ Error processing query: {str(e)}"


# Extract cluster names from user input
def extract_clusters_from_input(user_input, available_clusters):
    """Extracts cluster names mentioned in user input and validates against available clusters."""
    mentioned_clusters = []

    # Match cluster patterns like "Cluster 1", "Cluster 2", etc.
    matches = re.findall(r"Cluster\s*\d+", user_input, re.IGNORECASE)

    # Normalize and validate clusters
    for match in matches:
        cluster_name = match.strip()  # Normalize formatting
        if cluster_name in available_clusters:
            mentioned_clusters.append(cluster_name)

    return mentioned_clusters


# Determine which clusters to run the command on
def get_target_clusters(user_input, cluster_data):
    """Determines the target clusters based on user input, session availability, and previous usage."""
    global last_used_cluster  # Allow modification of the global variable
    available_clusters = list(cluster_data.keys())  # Get all available clusters

    # Extract clusters from user input
    selected_clusters = extract_clusters_from_input(user_input, available_clusters)

    # If user mentioned specific clusters, use them
    if selected_clusters:
        last_used_cluster = selected_clusters[-1]  # Store the last mentioned cluster
        return selected_clusters

    # If no specific clusters are mentioned, use the last used cluster
    if last_used_cluster in available_clusters:
        return [last_used_cluster]

    # As a final fallback, use the first available active cluster
    for cluster_name, cluster_info in cluster_data.items():
        session = cluster_info.get("session")
        print("Inside get target cluster: ", cluster_name)
        if isinstance(session, paramiko.SSHClient):  # Ensure it's an active session
            return [cluster_name]

    # If no valid cluster is found
    return None
