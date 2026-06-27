#!/usr/bin/env python3
"""
Brute-forcer de clé Meross
Teste jusqu'à 10k combinaisons/sec avec la signature capturée
"""
import hashlib
import json
import sys
import itertools
import string
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

class MerossKeyBruteForcer:
    def __init__(self, message_id: str, timestamp: int, target_sign: str):
        self.message_id = message_id
        self.timestamp = timestamp
        self.target_sign = target_sign.lower()
        self.found_key = None
        
    def _calculate_sign(self, key: str) -> str:
        """Calcule la signature Meross"""
        return hashlib.md5(
            f"{self.message_id}{key}{self.timestamp}".encode()
        ).hexdigest()
    
    def test_key(self, key: str) -> bool:
        """Test si une clé produit la signature correcte"""
        sign = self._calculate_sign(key)
        if sign == self.target_sign:
            self.found_key = key
            return True
        return False
    
    def brute_force_common_patterns(self):
        """Teste les patterns courants Meross"""
        patterns = [
            # Hex strings (32 chars)
            *[f"{i:032x}" for i in range(1000)],
            # Default Meross keys connus
            "23x17ahWarFH6w29",
            "16byoxo7x@_",
            "meross_default",
            "admin",
            "password",
            "123456",
            "12345678",
            "87654321",
            # Patterns simples
            "0" * 32,
            "1" * 32,
            "a" * 32,
            "f" * 32,
            # UUID-like
            "00000000000000000000000000000000",
            "ffffffffffffffffffffffffffffffff",
        ]
        
        print(f"🔑 Testing {len(patterns)} common patterns...")
        for i, key in enumerate(patterns):
            if i % 100 == 0:
                print(f"   Progress: {i}/{len(patterns)}", end="\r")
            
            if self.test_key(key):
                print(f"\n✅ KEY FOUND: {self.found_key}")
                return True
        
        print(f"   Testing {len(patterns)} patterns... ❌ Not found\n")
        return False
    
    def brute_force_charset(self, charset: str, min_len: int, max_len: int, max_attempts: int = 1000000):
        """Teste toutes les combinaisons d'un charset"""
        print(f"🔍 Brute-forcing charset: {charset[:50]}...")
        print(f"   Length range: {min_len}-{max_len}, max {max_attempts} attempts")
        
        attempts = 0
        
        for length in range(min_len, max_len + 1):
            print(f"\n   Testing length {length}...")
            
            for attempt_num, combo in enumerate(itertools.product(charset, repeat=length)):
                if attempts >= max_attempts:
                    print(f"   Reached max attempts ({max_attempts})")
                    return False
                
                key = "".join(combo)
                if self.test_key(key):
                    print(f"\n✅ KEY FOUND: {self.found_key}")
                    return True
                
                attempts += 1
                if attempts % 10000 == 0:
                    print(f"   Attempts: {attempts:,}", end="\r")
        
        return False
    
    def brute_force_hex(self, length: int = 32, max_attempts: int = 1000000):
        """Brute-force hex strings (most likely for Meross)"""
        print(f"🔍 Brute-forcing HEX (length {length})...")
        print(f"   Max {max_attempts:,} attempts (~{max_attempts//10000}s at 10k/sec)")
        
        for i in range(max_attempts):
            if i >= 16**length:  # Total possible hex combinations
                print(f"   Exhausted all {16**length:,} combinations")
                return False
            
            # Format as hex string
            key = f"{i:0{length}x}"
            
            if self.test_key(key):
                print(f"\n✅ KEY FOUND: {self.found_key}")
                return True
            
            if i % 10000 == 0 and i > 0:
                print(f"   Attempts: {i:,}", end="\r")
        
        return False

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 meross_bruteforcer.py <parsed_capture.json>")
        print("Or:    python3 meross_bruteforcer.py <messageId> <timestamp> <sign>")
        sys.exit(1)
    
    # Parse arguments
    if sys.argv[1].endswith(".json"):
        # Mode 1: Extract from parsed JSON
        json_file = Path(sys.argv[1])
        if not json_file.exists():
            print(f"❌ File {json_file} not found")
            sys.exit(1)
        
        print(f"📖 Loading {json_file}...")
        try:
            with open(json_file) as f:
                data = json.load(f)
        except json.JSONDecodeError:
            print("❌ Invalid JSON file")
            sys.exit(1)
        
        # Extract first POST request
        message_id = data.get("messageId")
        timestamp = data.get("timestamp")
        target_sign = data.get("sign")
        
        if not all([message_id, timestamp, target_sign]):
            print("❌ JSON missing required fields: messageId, timestamp, sign")
            sys.exit(1)
    else:
        # Mode 2: Direct arguments
        if len(sys.argv) < 4:
            print("❌ Need 3 arguments: messageId timestamp sign")
            sys.exit(1)
        message_id, timestamp, target_sign = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    
    print("="*70)
    print("MEROSS KEY BRUTE-FORCER")
    print("="*70)
    print(f"messageId: {message_id}")
    print(f"timestamp: {timestamp}")
    print(f"target_sign: {target_sign}")
    print()
    
    bruter = MerossKeyBruteForcer(message_id, timestamp, target_sign)
    
    # Strategy 1: Common patterns
    if bruter.brute_force_common_patterns():
        print(f"\n🎉 SUCCESS! Key: {bruter.found_key}")
        return
    
    # Strategy 2: Hex 32-char (most likely)
    print("\n📊 Strategy 2: Hex strings (32 chars, most probable)")
    if bruter.brute_force_hex(length=32, max_attempts=100000):
        print(f"\n🎉 SUCCESS! Key: {bruter.found_key}")
        return
    
    # Strategy 3: Alphanumeric 16-32 chars
    print("\n📊 Strategy 3: Alphanumeric (16-24 chars)")
    if bruter.brute_force_charset(string.ascii_lowercase + string.digits, 16, 24, max_attempts=50000):
        print(f"\n🎉 SUCCESS! Key: {bruter.found_key}")
        return
    
    print("\n❌ Key not found with current strategies")
    print("💡 Try:")
    print("   1. Capture again - make sure app was using device during capture")
    print("   2. Check if sign is correct (should be 32 hex chars)")
    print("   3. Manually check Refoss app Settings > About > Key")

if __name__ == "__main__":
    main()
