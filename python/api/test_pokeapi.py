import requests
url = "https://pokeapi.co/api/v2/move/1"
response = requests.get(url)
print(response.status_code)
data = response.json()
print(data["name"])
print(data.keys())