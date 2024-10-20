import requests
import pandas as pd
from bs4 import BeautifulSoup
from tqdm import tqdm

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
base_url = "https://stats.ncaa.org/"

def get_Teams(year):
    yearToLink = {
        2024: "https://stats.ncaa.org/selection_rankings/nitty_gritties/37268", 
        2023: "https://stats.ncaa.org/selection_rankings/nitty_gritties/31608", 
        2022: "https://stats.ncaa.org/selection_rankings/nitty_gritties/25565", 
        2021: "https://stats.ncaa.org/selection_rankings/nitty_gritties/19203", 
        2020: "https://stats.ncaa.org/selection_rankings/nitty_gritties/16183"
    }
    r = requests.get(yearToLink[year], headers=headers)
    soup = BeautifulSoup(r.text, 'html.parser')
    net_table = soup.find('tbody')
    names, ids, conferences = [], [], []

    for row in net_table.find_all('tr'):
        names.append(row.contents[1].text.strip())
        ids.append(row.contents[1].contents[-1].get('href'))
        conferences.append(row.contents[3].text)
    
    return {team:List for team,List in zip(names,zip(ids,conferences))}

def downloadImages():
    r = requests.get("https://stats.ncaa.org/selection_rankings/nitty_gritties/37268", headers=headers)
    soup = BeautifulSoup(r.text, 'lxml')
    images = [img['src'] for img in soup.find_all('img')[1:]]
    teams = get_Teams(2024).keys()

    for team, url in tqdm(zip(teams, images)):
        img_data = requests.get(url).content
        with open(f'Logos/{team}.jpg', 'wb') as handler:
            handler.write(img_data)