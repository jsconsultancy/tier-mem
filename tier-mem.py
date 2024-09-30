import paramiko
import xml.etree.ElementTree as ET
import re

def read_credentials_from_xml(xml_file):
    """Read ESXi login credentials from an XML file."""
    tree = ET.parse(xml_file)
    root = tree.getroot()
    
    esxi_host = root.find('host').text.strip()
    esxi_user = root.find('username').text.strip()
    esxi_pass = root.find('password').text.strip()
    
    return esxi_host, esxi_user, esxi_pass

def connect_to_esxi(hostname, username, password):
    """Establish an SSH connection to the ESXi host."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        print(f"Connecting to {hostname}...")
        client.connect(hostname, username=username, password=password)
        print("Connected successfully!")
        return client
    except Exception as e:
        print(f"Failed to connect: {e}")
        return None

def execute_command(ssh_client, command):
    """Execute a command on the SSH-connected ESXi host."""
    stdin, stdout, stderr = ssh_client.exec_command(command)
    stdout_lines = stdout.readlines()
    stderr_lines = stderr.readlines()
    
    if stderr_lines:
        print(f"Errors occurred while executing command: {''.join(stderr_lines)}")
    
    return stdout_lines

def get_vm_mapping(ssh_client):
    """Retrieve the VM name and Cartel ID mapping from the ESXi host."""
    print("Retrieving VM names and IDs...")
    esxcli_command = "esxcli --formatter csv vm process list"
    output = execute_command(ssh_client, esxcli_command)

    # Parsing the output to extract VM names and IDs
    vm_mapping = {}
    for line in output[1:]:  # Skip header line if present
        parts = line.strip().split(',')
        if len(parts) >= 5:  # Ensure we have enough columns
            vm_name = parts[1].strip()
            vm_id = parts[4].strip()
            vm_mapping[vm_id] = vm_name
    
    return vm_mapping

def retrieve_memory_stats(ssh_client, vm_mapping):
    """Retrieve memory stats and replace Cartel IDs with VM names."""
    print("Retrieving memory stats for VMs backed by NVMe...")
    memstats_command = (
        "memstats -r vmtier-stats -u mb -s name:memSize:active:tier0Consumed:tier1Consumed"
    )
    memstats_output = execute_command(ssh_client, memstats_command)

    # Replace VM Cartel IDs with VM names
    replaced_output = []
    for line in memstats_output:
        # Replace each VM ID with its corresponding name
        for vm_id, vm_name in vm_mapping.items():
            line = line.replace(f"vm.{vm_id}", vm_name)
        replaced_output.append(line.strip())
    
    return replaced_output

def filter_relevant_lines(memstats_output):
    """Filter out only the relevant lines containing VM data."""
    relevant_lines = []

    # Regex pattern to match lines that have the correct number of columns
    data_pattern = re.compile(r"^\S+\s+\d+\s+\d+\s+\d+\s+\d+$")

    for line in memstats_output:
        if data_pattern.match(line.strip()):
            relevant_lines.append(line.strip())

    return relevant_lines

def main():
    # Read credentials from XML file
    xml_file = 'esxi_credentials.xml'
    esxi_host, esxi_user, esxi_pass = read_credentials_from_xml(xml_file)
    
    # Establish SSH connection to ESXi
    ssh_client = connect_to_esxi(esxi_host, esxi_user, esxi_pass)
    
    if ssh_client is None:
        print("Exiting due to connection failure.")
        return
    
    try:
        # Get the VM name and Cartel ID mapping
        vm_mapping = get_vm_mapping(ssh_client)
        
        # Check if no VMs are running
        if not vm_mapping:
            print("No VMs are currently running on the ESXi host.")
            return
        
        # Retrieve and parse memory stats
        memstats_output = retrieve_memory_stats(ssh_client, vm_mapping)

        # Filter out irrelevant lines
        relevant_lines = filter_relevant_lines(memstats_output)

        # Determine the maximum width of the VM name column
        max_vm_name_length = max(len(vm_name) for vm_name in vm_mapping.values())

        # Print the memory stats output with aligned columns
        print("Memory stats:")
        header_format = f"{{:<{max_vm_name_length}}}  {{:<15}}  {{:<15}}  {{:<20}}  {{:<20}}"
        print(header_format.format("VM Name", "MemSize (MB)", "Active (MB)", "Tier0 Consumed (MB)", "Tier1 Consumed (MB)"))
        print("-" * (max_vm_name_length + 90))
        
        # Print each relevant line in the formatted table
        for line in relevant_lines:
            columns = line.split()
            print(header_format.format(*columns))

    finally:
        # Always close the SSH connection
        print("Closing SSH connection...")
        ssh_client.close()
        print("SSH connection closed.")

if __name__ == "__main__":
    main()
