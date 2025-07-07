import paramiko
import os
import json
from dotenv import load_dotenv

load_dotenv()

class CephOperations:
    def __init__(self):
        self.connected_clusters = {}


    def connect_cluster(self, cluster_ip, username, password):
        """Attempts to establish an SSH connection using given credentials."""
        print(f"Connecting to Ceph cluster at {cluster_ip}...")

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            ssh.connect(cluster_ip, username=username, password=password)
            print(f"✅ Authentication successful for {username}@{cluster_ip}")
            return ssh  # Return the SSH session
        except paramiko.AuthenticationException:
            print("❌ Connection failed: Authentication failed.")
            return None
        except Exception as e:
            print(f"❌ Connection error: {str(e)}")
            return None

    def disconnect_cluster(self, ip):
        """Disconnect from a Ceph cluster node."""
        if ip not in self.connected_clusters:
            return {"error": f"Cluster {ip} is not connected."}

        self.connected_clusters[ip].close()
        del self.connected_clusters[ip]
        return {"message": f"Disconnected from {ip}"}

    def run_ceph_command(self, ssh_client, command):
        """Execute a Ceph command on the specified cluster node."""
        print(f"Debug: {command}")
        print(f"Debug: {ssh_client}")
        try:
            stdin, stdout, stderr = ssh_client.exec_command(command)
            output = stdout.read().decode()
            error = stderr.read().decode()

        #     return {"output": output.strip(), "error": error.strip()}
        # except Exception as e:
        #     return {"error": f"Failed to execute command: {str(e)}"}
        # Attempt to parse output as JSON
            print(type(output))
            try:
                output = json.loads(output)  # Convert to dictionary if it's valid JSON
            except json.JSONDecodeError:
                print("Not converting to JSON")
                pass  # Keep it as a string if it's not JSON

            return {"output": output, "error": error}
        except Exception as e:
            return {"error": f"Failed to execute command: {str(e)}"}
    
    def get_cluster_status(self, ssh_client):
        """Retrieve the status of a connected Ceph cluster."""
        print("In the backend.py")
        print(f"Debug: {type(ssh_client)}")
        return self.run_ceph_command(ssh_client, "ceph status")

    def osd_status(self, ssh_client):
        """Get the status of OSDs in the Ceph cluster."""
        return self.run_ceph_command(ssh_client, "ceph osd status -f json")

    def get_cluster_health(self, ssh_client):
        """Retrieve Ceph cluster health status."""
        return self.run_ceph_command(ssh_client, "ceph health")

    def list_filesystems(self, ssh_client):
        """List all CephFS filesystems."""
        return self.run_ceph_command(ssh_client, "ceph fs ls")

    def get_filesystem_metadata(self, ssh_client, fs_name="cephfs"):
        """Retrieve metadata information for a Ceph filesystem."""
        command = f"ceph fs get {fs_name}"
        return self.run_ceph_command(ssh_client, command)

    def get_filesystem_info(self, ssh_client, fs_name="cephfs"):
        """Retrieve metadata information for a Ceph filesystem."""
        command = f"ceph fs volume info {fs_name}"
        return self.run_ceph_command(ssh_client, command)

    def list_mds_nodes(self, ssh_client):
        """List all MDS (Metadata Server) nodes and its state for CephFS."""
        return self.run_ceph_command(ssh_client, "ceph fs status -f json-pretty")

    def get_mds_perf(self, ssh_client):
        """Get performance details of CephFS MDS nodes."""
        return self.run_ceph_command(ssh_client, "ceph fs perf stats -f json-pretty")

    def list_filesystem_clients(self, ssh_client):
        """List all active CephFS clients."""
        return self.run_ceph_command(ssh_client, "ceph fs dump | grep client")

    def get_active_mds(self, ssh_client):
        """Check which MDS nodes are active and standby."""
        return self.run_ceph_command(ssh_client, "ceph fs status -f json-pretty")

    ### ✅ CEPHFS PERFORMANCE MONITORING ###
    def get_filesystem_performance(self, ssh_client):
        """Retrieve CephFS performance metrics."""
        return self.run_ceph_command(ssh_client, "ceph fs perf stats -f json-pretty")

    def get_mds_memory_usage(self, ssh_client):
        """Retrieve memory usage of MDS nodes."""
        return self.run_ceph_command(ssh_client, "ceph tell mds.* heap stats")

    def get_cephfs_metadata_pool_usage(self, ssh_client, fs_name=""):
        """Get metadata pool usage for a given CephFS."""
        command = f"ceph df | grep {fs_name}" if fs_name else "ceph df"
        return self.run_ceph_command(ssh_client, command)