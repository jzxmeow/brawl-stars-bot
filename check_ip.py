
import urllib.request

try:
    with urllib.request.urlopen(
        "https://api.ipify.org", timeout=10
    ) as response:
        print("Outbound IP:", response.read().decode())
except Exception as e:
    print("IP check failed:", repr(e))
