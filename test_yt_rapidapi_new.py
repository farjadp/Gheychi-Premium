import requests
import json

url = "https://youtube-media-downloader.p.rapidapi.com/v2/video/details"
querystring = {"videoId": "dQw4w9WgXcQ"} # Rick Astley

headers = {
	"X-RapidAPI-Key": "c87faf6a9dmsh0b14ea72f890e09p1e9794jsn0a7724b09dc9",
	"X-RapidAPI-Host": "youtube-media-downloader.p.rapidapi.com"
}

response = requests.get(url, headers=headers, params=querystring)
print(response.status_code)
print(json.dumps(response.json(), indent=2))
