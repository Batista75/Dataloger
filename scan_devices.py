#!/usr/bin/env python3
import tinytuya
import json

print("Scanning for Tuya devices on local network (20 retries)...")
devices = tinytuya.scan(maxretry=20, color=False)

print(f"\nFound {len(devices)} device(s):\n")
for i, dev in enumerate(devices, 1):
    print(f"Device {i}:")
    print(f"  IP: {dev.get('ip')}")
    print(f"  MAC: {dev.get('mac')}")
    print(f"  GWID: {dev.get('gwid')}")
    print(f"  UUID: {dev.get('uuid')}")
    print(f"  Full data: {json.dumps(dev, indent=2)}")
    print()
