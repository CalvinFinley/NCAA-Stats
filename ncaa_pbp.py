
import re
import requests
import pandas as pd
from io import StringIO
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.firefox.options import Options

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
base_url = "https://stats.ncaa.org/"


def get_Teams(year):
    r = requests.get("https://stats.ncaa.org/selection_rankings/nitty_gritties/31608", headers=headers)
    soup = BeautifulSoup(r.text, 'html.parser')
    net_table = soup.find('tbody')
    names, ids, conferences = [], [], []

    for row in net_table.find_all('tr'):
        names.append(row.contents[1].text.strip())
        ids.append(row.contents[1].contents[-1].get('href'))
        conferences.append(row.contents[3].text)
    
    return {team:List for team,List in zip(names,zip(ids,conferences))}

class Team():

    def __init__(self, id, loadPlayerStats=False) -> None:
        self.__id = id
        self.__name = None
        
        self.load_games()
        self.load_roster()

        if loadPlayerStats:
            self.load_player_stats()
        else:
            self.__playerStats = None
    
    @property
    def id(self):
        return self.__id
    
    @property
    def name(self):
        return self.__name
    
    @property
    def games(self):
        return self.__games
    
    @property
    def roster(self):
        return self.__roster
    
    @property
    def playerStats(self):
        return self.__playerStats
    
    def load_games(self):
        games = pd.read_html(base_url + f'teams/{self.__id}',extract_links='body')[0]
        games = games.loc[0::2]

        games['Date'] = games['Date'].apply(lambda x: x[0])
        games['Date'] = pd.to_datetime(games['Date'])

        games['Attendance'] = games['Attendance'].apply(lambda x: x[0])

        games[['Opponent','OpponentID']] = games['Opponent'].tolist()
        games['Opponent'] = games['Opponent'].apply(lambda x: re.findall(r"[a-zA-Z. ()&']+",x)[0].strip())
        games.dropna(subset='OpponentID',inplace=True)
        games['OpponentID'] = games['OpponentID'].apply(lambda x: x.split('/')[2])

        games[['Result','GameID']] = games['Result'].tolist()
        games.dropna(subset='GameID',inplace=True)
        games['GameID'] = games['GameID'].apply(lambda x: x.split('/')[2])

        # Fix handling of overtime games (try team 561231)
        games[['Result','TeamScore','OpponentScore']] = games['Result'].apply(lambda x: re.split(' |-', x)).tolist()

        games = games[['GameID','Date','Opponent','OpponentID','Result','TeamScore','OpponentScore','Attendance']]
        games.reset_index(drop=True, inplace=True)

        self.__games = games
    
    def load_roster(self):
        roster = pd.read_html(base_url + f'teams/{self.__id}/roster',extract_links='body')[0]
        ids = roster['Name'].apply(lambda x: x[1].split('/')[-1])
        roster = roster.map(lambda x: x[0])
        roster['PlayerID'] = ids
        roster = roster[['PlayerID', 'Name', '#', 'Class', 'Position', 'Height', 'Hometown','High School', 'GP', 'GS']]
        
        self.__roster = roster
    
    def load_player_stats(self):
        self.__playerStats = pd.read_html(base_url + f'teams/{self.__id}/season_to_date_stats')[0]



class Game():

    def __init__(self, id, loadShotChart=False) -> None:
        self.id = id
        self.teams = None
        self.__pbp = None

        self.load_boxScore()
        self.load_pbp()

        if loadShotChart:
            self.load_shotChart()
        else:
            self.__shotChart = None
    
    def load_boxScore(self):
        r = requests.get(base_url + f'contests/{self.id}/individual_stats', headers=headers)
        soup = BeautifulSoup(r.text, 'html.parser')
        print(r)
        
        # Get teams' IDs from the hyperlink on the team name from the quarter-by-quarter scoring table
        self.teams = [team['href'].split('/')[-1] for team in soup.find('table').find_all('a', {'class':'skipMask'})]

        tables = pd.read_html(StringIO(r.text),match='FGM',header=0)
        self.__boxScore = {self.teams[2]: tables[1], self.teams[0]: tables[0]}

        # Properly format starters' names for each team
        self.__starters = {team:[" ".join(player.split(', ')[::-1]) for player in self.__boxScore[team].loc[self.__boxScore[team].GS==1,'Name'].tolist()[:-1]] \
                         for team in self.teams}
    
    def load_pbp(self):
        r = requests.get(base_url + f'contests/{self.id}/play_by_play', headers=headers)
        self.__pbp = pd.concat([quarter for quarter in pd.read_html(StringIO(r.text), header=0) if 'Time' in quarter.columns]).reset_index(drop=True)
    
    def load_shotChart(self):
        options = Options()
        options.add_argument("--headless")
        driver = webdriver.Firefox(options=options)
        driver.get(base_url + f'contests/{self.id}/box_score')
        soup = BeautifulSoup(driver.page_source, "html.parser")
        driver.quit()
        shotsList = soup.find_all('circle')[3:-4]

        shots = pd.DataFrame([shot.attrs for shot in shotsList])
        shots[['Period','player_id','team_id','shot','ShotMade']] = pd.DataFrame(shots['class'].to_list())

        shots['text']   = pd.DataFrame([shot.text for shot in shotsList])
        shots['Team']   = shots['text'].apply(lambda string: re.findall('\\((.+)\\)',string)[0])
        shots['Player'] = shots['text'].apply(lambda string: re.findall('by (.+)\\(',string)[0])
        shots['Time']   = shots['text'].apply(lambda string: re.findall('... (.*) :',string)[0])

        shots.drop(columns=['r','style','class','shot','text'], inplace=True)

        # Sort the events based on period and time remaining in quarter; this is mainly due to overtime periods being out of order
        shots.sort_values(['Period','Time'],ascending=[True,False],inplace=True)
        shots.reset_index(drop=True,inplace=True)

        self.__shotChart = shots

    @property
    def boxScore(self):
        return self.__boxScore
    
    @property
    def starters(self):
        return self.__starters
    
    @property
    def pbp(self):
        return self.__pbp
    
    @property
    def shotChart(self):
        return self.__shotChart
        