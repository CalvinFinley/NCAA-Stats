from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import pandas as pd
from sportsdataverse import wbb

def toc_to_sec(row):
    time_in_quarter = list(map(int, row.time.split(':')))

    time_remaining = 2400 - (row.quarter-1)*600 - (600-time_in_quarter[0]*60-time_in_quarter[1])
    return time_remaining

def get_starters(box):
    rows = box.contents[0].contents[1].find_all('tr')
    players = []

    for i, row in enumerate(rows):
        if i not in [0,len(rows)-1,len(rows)-2]:
            players.append(row.contents[1].string.strip())

    return players[0:5]

def getCurrentLineup(input_row, team):
    """ Calculates the amount of time since a player last committed a foul

    Args:
        row (pd.Series): 
    """
    global df, starters, current_players
    row = input_row[1]
    if row.name == 0:
        return starters[team]
    else:
        description = row['description']
        prev_row = df.loc[row.name - 1]
        lineup = (current_players[team][-1]).copy()
        
        if 'Sub' in description and team_map[team] in description:
            
            subbing_description = row['description'].split()
            in_or_out = subbing_description[1]
            player = row['description'].split('-')[-1].upper()
            if in_or_out == 'out':
                lineup.remove(player)
                return lineup
            else:
                lineup.append(player)
                return lineup
        else:
            return lineup

def scrape_pbp(pbp):
    categories = ['time', 'team', 'description', 'score', 'quarter']
    data = {col:[] for col in categories}

    quarters = pbp.find_all('div',class_='play-by-play-period-table')

    for n, quarter in enumerate(quarters):
        table = quarter.contents[0].contents[3]

        for col in categories:
            if col == 'team':
                column_data = table.find_all('img')
                data[col].extend( [img.attrs['alt'].split()[0] for img in column_data] )
            elif col == 'quarter':
                data[col].extend( [n+1 for i in column_data] )
            else:
                column_data = table.find_all('td',class_=col)
                data[col].extend( [t.string.strip() for t in column_data] )
        

    return pd.DataFrame(data)

class Game():
    def __init__(self, id, season, load_from) -> None:
        self.id = id
        self.season = season
        if load_from == 'web':
            pass
        elif load_from == 'file':
            pass
        else:
            raise ValueError





options = Options()
#options.add_argument("--headless")

url = r'https://www.ncaa.com/game/6064407/'
driver = webdriver.Firefox(options=options)
driver.get(url)

box_scores = {}
starters = {}

# Get the starting lineups for each team
for team in ['away', 'home']:
    driver.find_element(By.CLASS_NAME,f'{team}Team-bg-primary_color').click()

    soup = BeautifulSoup(driver.page_source, 'html.parser')

    box_scores[team] = soup.find('div',id='gamecenterAppContent')

    starters[team] = get_starters(box_scores[team])

team_names = [team for team in soup.find('div',class_='boxscore-team-selector').text.split('\n') if team]
team_map = {'away': team_names[0], 'home':team_names[1]}

# Go to play-by-play section of the page
driver.find_element(By.LINK_TEXT,'PLAY-BY-PLAY').click()

# Get the full play-by-play table
pbp = soup.find('div',class_='gamecenter-tab-play-by-play')

df = scrape_pbp(pbp)


# Lineups 
# --------------------------------------------------------
current_players = {'home':[], 'away':[]}

for team in ['home', 'away']:
    for row in df.iterrows():
        current_players[team].append(getCurrentLineup(row, team))

    df[f'{team}_current_lineup'] = current_players



print(df)

driver.quit()