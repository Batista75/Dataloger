#!/usr/bin/env python3
"""
Parser Wireshark capture pour extraire clé Meross
"""
import json
import re
import sys
from pathlib import Path

def extract_meross_key_from_pcap(pcap_json_file):
    """
    Extrait les informations Meross du fichier JSON parsé par tshark
    """
    pcap_json_file = Path(pcap_json_file)
    
    if not pcap_json_file.exists():
        print(f"❌ Fichier {pcap_json_file} non trouvé")
        return
    
    print(f"📖 Lecture {pcap_json_file}...")
    
    try:
        with open(pcap_json_file) as f:
            packets = json.load(f)
    except json.JSONDecodeError:
        print("❌ Fichier JSON invalide")
        return
    
    found_requests = []
    
    for packet in packets:
        try:
            # Chercher les layers HTTP
            layers = packet.get("_source", {}).get("layers", {})
            http_layer = layers.get("http", {})
            
            # Chercher POST vers /config
            if "http.request.method" in http_layer:
                method = http_layer.get("http.request.method", "")
                uri = http_layer.get("http.request.full_uri", "")
                
                if method == "POST" and "/config" in uri:
                    print(f"\n✅ Trouvé POST vers {uri}")
                    
                    # Essayer extraire le payload (body)
                    if "http.file_data" in http_layer:
                        body_hex = http_layer["http.file_data"]
                        try:
                            body = bytes.fromhex(body_hex).decode("utf-8")
                            found_requests.append(body)
                            print(f"Body:\n{body[:500]}...")
                        except:
                            pass
        except Exception as e:
            pass
    
    # Parser les bodies JSON pour chercher la clé
    print("\n" + "="*60)
    print("RECHERCHE CLE MEROSS")
    print("="*60)
    
    meross_keys = set()
    
    for body_str in found_requests:
        try:
            data = json.loads(body_str)
            
            # La clé est dans header.sign mais c'est une signature
            # Chercher messageId et timestamp pour brute-force calc
            header = data.get("header", {})
            msg_id = header.get("messageId", "")
            timestamp = header.get("timestamp", "")
            sign = header.get("sign", "")
            
            print(f"\nRequest détails:")
            print(f"  messageId: {msg_id}")
            print(f"  timestamp: {timestamp}")
            print(f"  sign: {sign}")
            
            # Si on a les 3 info, on peut tester des clés
            if msg_id and timestamp and sign:
                print(f"\n💡 Avec ces infos, on peut brute-force la clé!")
                print(f"   sign = MD5('{msg_id}' + KEY + '{timestamp}')")
                
        except json.JSONDecodeError:
            pass
    
    if not found_requests:
        print("\n❌ Aucune requête POST /config trouvée")
        print("⚠️  Suggestions:")
        print("  1. Vérifie que tshark a bien capturé")
        print("  2. Lance l'app Refoss PENDANT la capture")
        print("  3. Laisse la capture tourner ≥ 60 secondes")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 parse_meross_capture.py <fichier.json>")
        print("Exemple: python3 parse_meross_capture.py captures/parsed.json")
        sys.exit(1)
    
    extract_meross_key_from_pcap(sys.argv[1])
