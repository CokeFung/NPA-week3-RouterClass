from netmiko import ConnectHandler
from pprint import PrettyPrinter
import io
import sys
import time
import yaml

pp = PrettyPrinter(indent=2)
config_path = "./config/"
username = "admin"
password = "cisco"


################################################################################################################
############################################# Other functions ##################################################
def backline():
    print('\r', end='')

def delay_print(s, newline):
    for c in s:
        sys.stdout.write(c)
        sys.stdout.flush()
        time.sleep(0.05)
    if newline:
        print()
    else:
        backline()

################################################################################################################
########################################## Configure IP addresss ###############################################
def configInterfaces():
    print("Start configuring IP addresses to all devices...")
    devices_config = yaml.load(open(config_path + "devices_interface_info.yml"), Loader=yaml.Loader)
    # pp.pprint(devices_config)
    for device in devices_config:
        delay_print("[*] Verifying: " + device['name'], False)
        status = verifyDeviceInfo(device)
        if status:
            delay_print("[+] "+device['name'] + " status: [OK]                  ", True)
        else:
            delay_print("[-] "+device['name'] + " status: [Fixed]               ", True)
        # break
    print()

def verifyDeviceInfo(device):
    status = True
    device_ip = device["management_ip"]
    device_params = {
        "device_type": "cisco_ios",
        "ip": device_ip,
        "username": username,
        "password": password,
    }
    with ConnectHandler(**device_params) as ssh:
        interfaces_data = convertInterfaceData(ssh.send_command('sh ip int br')) 
        # print(interfaces_data)
        # print(device)
        if device["name"][0] == 'R' and device["management_ip"] != interfaces_data["g0/0"][0]:
            return False
        elif device["name"][0] == 'S' and device["management_ip"] != interfaces_data["Vlan99"][0]:
            return False
        if type(device['interfaces']) is list:
            for d in device['interfaces']:
                if d["ip"] != interfaces_data[d["name"]][0]:
                    # print(d)
                    # print(interfaces_data[d["name"]])
                    delay_print("[*] Configuring: {} inteface {}".format(device['name'], d['name']), False)
                    setIPtoInterface(device_params, d['name'], d['ip'], d['subnet'])
                    status = False
    return status

def convertInterfaceData(data):
    replace_list = [
        ["administratively down", "down"],
        ["GigabitEthernet", "g"],
        ["FastEthernet", "f"],
        ["Loopback", "lo"]
    ]
    for w in replace_list:
        data = data.replace(w[0], w[1])
    data = data.split()
    data = [data[i:i+6] for i in range(0, len(data), 6)]
    dict_data = {}
    for i in data[1:]:
        dict_data[i[0]] = i[1:]
    return dict_data

def setIPtoInterface(device_params, interface, ip, subnet):
    with ConnectHandler(**device_params) as ssh:
        ssh.config_mode()
        commands = [
            "int {}".format(interface),
            "ip add {} {}".format(ip, subnet),
            "no shut",
        ]
        ssh.send_config_set(commands)
        ssh.exit_config_mode()
        ssh.save_config()
        result = ssh.send_command('sh ip int br')
        ssh.disconnect()
        return result

################################################################################################################
########################################## Configure access-lists ##############################################
def configACL():
    print("Start configuring access-lists to all devices...")
    device_acl = yaml.load(open(config_path + "devices_access-lists_info.yml"), Loader=yaml.Loader)
    # pp.pprint(acls)
    # pp.pprint(device_acl)
    for dv in device_acl:
        delay_print("[*] Configuring: {}'s ACLs and apply to interfaces".format(dv['name']), False)
        addACLtoDevice(dv['management_ip'], dv['acl'])
        delay_print("[+] Configured: ACLs in {} is applied                  ".format(dv['name']), True)
    print()

def addACLtoDevice(management_ip, acl_list):
    device_params = {
        "device_type": "cisco_ios",
        "ip": management_ip,
        "username": username,
        "password": password,
    }
    acls = yaml.load(open(config_path + "acl_list_info.yml"), Loader=yaml.Loader)
    with ConnectHandler(**device_params) as ssh:
        ssh.enable()
        ssh.config_mode()
        ### Clear old acl and create a new one
        for acl in acl_list:
            acl_info = acls[acl['name']]
            ssh.send_command("no ip access-list {} {}".format(acl_info['type'], acl['name']), expect_string=r"#")
            ssh.send_command("ip access-list {} {}".format(acl_info['type'], acl['name']), expect_string=r"#")
            ### Add rules to ACL
            for r in acl_info['list']:
                ssh.send_command("{} {} {}".format(r['cmd'], r['src'], r['wcd']), expect_string=r"#")
            ssh.send_command("exit", expect_string=r"#")
        ### Apply to interfaces
        for acl in acl_list:
            for intf in acl['interfaces']:
                if intf['name'].lower() == 'vty':
                    ssh.send_command("line vty 0 4", expect_string=r"#")
                    ssh.send_command("access-class {} {}".format(acl['name'], intf['direction']), expect_string=r"#")
                    ssh.send_command("exit", expect_string=r"#")
        ssh.disconnect()


################################################################################################################
########################################## Configure CDP and LLDP ##############################################
def configCDPnLLDP():
    print("Start to running CDP and LLDP in all devices...")
    devices = yaml.load(open(config_path + "devices_management_info.yml"), Loader=yaml.Loader)
    for dv in devices:
        delay_print("[*] Configuring: Enabling CDP in {}".format(dv['name']), False)
        enableCDP(dv['management_ip'])
        delay_print("[*] Configuring: Enabling LLDP in {}".format(dv['name']), False)
        enableLLDP(dv['management_ip'])
        delay_print("[+] CDP and LLDP in {} is running up".format(dv['name']), True)

def enableCDP(device_ip):
    device_params = {
        "device_type": "cisco_ios",
        "ip": device_ip,
        "username": username,
        "password": password,
    }
    with ConnectHandler(**device_params) as ssh:
        ssh.enable()
        ssh.config_mode()
        ssh.send_command('cdp run', expect_string=r"#")
        ssh.disconnect()


def enableLLDP(device_ip):
    device_params = {
        "device_type": "cisco_ios",
        "ip": device_ip,
        "username": username,
        "password": password,
    }
    with ConnectHandler(**device_params) as ssh:
        ssh.enable()
        ssh.config_mode()
        ssh.send_command('lldp run', expect_string=r"#")
        ssh.disconnect()

################################################################################################################
################################### Configure description to interfaces ########################################
def configDescription():
    print("Start Configure all unnterfaces description based on CDP information...")
    devices = yaml.load(open(config_path + "devices_management_info.yml"), Loader=yaml.Loader)
    for dv in devices:
        delay_print("[*] Fetching data: CDP information from {}".format(dv['name']), False)
        cdp_data = fetchCDPinformation(dv['management_ip'])
        delay_print("[*] Configuring: Add description to {}'s interafaces".format(dv['name']), False)
        addDescription2Interfaces(dv['management_ip'], cdp_data)
        delay_print("[+] Added description to all interafaces of {}               ".format(dv['name']), True)
        
def fetchCDPinformation(device_ip):
    device_params = {
        "device_type": "cisco_ios",
        "ip": device_ip,
        "username": username,
        "password": password,
    }
    result = ""
    with ConnectHandler(**device_params) as ssh:
        ssh.enable()
        result = ssh.send_command('show cdp neighbors')
        ssh.disconnect()
    return cdp_string2list(result)

def cdp_string2list(data):
    data = data.split("\n")[5:-2]
    data_clean = []
    for d in data:
        tmp = d.split()
        if ".npa.com" in tmp[0]:
            data_clean.append([
                tmp[1]+""+tmp[2],      #Local interface
                tmp[-2]+" "+tmp[-1],   #Connect to device port
                tmp[0].split('.')[0]   #Connect to device name
                ])
    return data_clean

def addDescription2Interfaces(device_ip, cdp_data):
    device_params = {
        "device_type": "cisco_ios",
        "ip": device_ip,
        "username": username,
        "password": password,
    }
    with ConnectHandler(**device_params) as ssh:
        for data in cdp_data:
            ssh.enable()
            ssh.config_mode()
            ssh.send_command("int {}".format(data[0]), expect_string=r"#")
            ssh.send_command("description \"connect to {} of {}\"".format(data[1], data[2]), expect_string=r"#")
            ssh.send_command("exit", expect_string=r"#")
        ssh.disconnect()
            