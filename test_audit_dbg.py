import sys
sys.path.insert(0, 'src')
from godmode.core.audit import _redact

cases = [
    ("Anthropic api03", "ANTHROPIC_API_KEY=sk-ant-api03-1234567890ABCDEFGHIJKLMNOPQRSTUVXYZ"),
    ("Anthropic short", "sk-ant-WxYzAbCdEfGhIjKlMnOpQrStUv"),
    ("OpenAI proj", "sk-proj-" + "A"*30),
    ("OpenAI long", "sk-" + "A"*45),
    ("Bearer", "Bearer abc123_-.abcdefghij0123456789"),
    ("Google", "AIzaSyABCDEFGHIJKLMNOPQRSTUVWX"),
    ("Groq", "gsk_" + "X"*28),
    ("NVIDIA", "nvapi-" + "x"*20),
    ("JWT", "eyJhbGciOiJIUzI1.eyJzdWIiOiIxMjM0.NTckZW3N9p6ZGw"),
    ("Slack", "xoxb-1234567890-abcdefghijklmnop"),
    ("GitHub ghp", "ghp_AbCdEfGhIjKlMnOpQrStUvWxYz123456"),
    ("Hex 50", "a"*50),
]
for label, val in cases:
    out = _redact({"t": val})
    ok = "***redacted***" in out["t"]
    status = "PASS" if ok else "FAIL"
    print(f"{label}: {status}")
