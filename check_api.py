import os, httpx
key = os.environ.get("FOOTBALL_API_KEY", "NICHT GESETZT")
print("Key:", key[:8] + "..." if len(key) > 8 else key)
r = httpx.get("https://api.football-data.org/v4/competitions/2000/matches", headers={"X-Auth-Token": key}, timeout=15)
print("Status:", r.status_code)
print(r.text[:500])
