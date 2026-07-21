import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from godmode.core.key_rotator import KeyRotator

def main():
    rotator = KeyRotator()
    rotator.fetch_keys()
    print("Found Gemini keys:", len(rotator.keys["gemini"]))
    print("Found Claude keys:", len(rotator.keys["claude"]))
    print("Sample Gemini key:", rotator.get_key("gemini"))
    print("Sample Claude key:", rotator.get_key("claude"))

if __name__ == "__main__":
    main()
