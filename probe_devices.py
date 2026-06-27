#!/usr/bin/env python3
import tinytuya
import json
import sys

targets = [
    {"ip": "192.168.1.69", "mac": "F4:65:0B:E3:BB:48"},
    {"ip": "192.168.1.96", "mac": "2E:82:1D:8A:64:17"},
]

print("Attempting direct connection to known IPs with common credentials...\n")

for target in targets:
    ip = target["ip"]
    mac = target["mac"]
    print(f"Testing {ip} (MAC: {mac})...")
    
    # Try common default credentials
    credentials = [
        {"device_id": "00000000000000000000", "local_key": "0000000000000000"},
        {"device_id": "", "local_key": ""},
        {"device_id": "root", "local_key": "root"},
    ]
    
    for cred in credentials:
        try:
            d = tinytuya.OutletDevice(
                dev_id=cred["device_id"],
                address=ip,
                local_key=cred["local_key"],
                version="3.3"
            )
            result = d.status()
            print(f"  ✓ SUCCESS with cred {cred}")
            print(f"    Response: {json.dumps(result, indent=2)}")
            break
        except Exception as e:
            err_str = str(e)
            if "Connection refused" in err_str or "timeout" in err_str.lower():
                print(f"  ✗ No service on port 6668")
                break
            # Continue trying other credentials
    
    print()
