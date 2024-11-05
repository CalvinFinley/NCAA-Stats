import re
import requests
import pandas as pd
from io import StringIO
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from copy import deepcopy
import os
import json

from utility import base_url,headers
from pbp import PbpLoader

class Game():

    def __init__(self, gameID, loadShotChart=False, source='web') -> None:
        self.gameId = gameID
        self.teams = None
        self.source = source

        self.load_data(loadShotChart)
        del self._sourceData

    
    def load_data(self, loadShotChart: bool):
        if self.source == 'web':
            self._sourceData = {}
            self._sourceData['boxScore'] = requests.get(base_url + f'contests/{self.gameId}/individual_stats', headers=headers).text
            self._sourceData['pbp'] = requests.get(base_url + f'contests/{self.gameId}/play_by_play', headers=headers).text
            if loadShotChart:
                options = Options()
                options.add_argument("--headless")
                driver = webdriver.Firefox(options=options)
                driver.get(base_url + f'contests/{self.gameId}/box_score')
                self._sourceData['shotChart'] = driver.page_source
                driver.quit()
            self._save_data_to_file()
        elif self.source == 'file':
            if os.path.isdir('D:/DataDirectory/Game'):
                with open(f"D:/DataDirectory/Game/game_{self.gameId}.json", mode='r', encoding='utf-8') as htmlf:
                    self._sourceData =  json.load(htmlf)
            else:
                pass # Add error handling for if there is no saved data
        else:
            pass # Add error handling for if wrong source type is given

        self.load_boxScore()
        self.load_pbp()
        if loadShotChart:
            self.load_shotChart()
    
    def load_boxScore(self):

        soup = BeautifulSoup(self._sourceData['boxScore'], 'html.parser')
        
        # Get teams' IDs from the hyperlink on the team name from the quarter-by-quarter scoring table
        self.teams = [team['href'].split('/')[-1] for team in soup.find('table').find_all('a', {'class':'skipMask'}) if team.text]
        #self.teams = [teams[0], teams[2]]

        tables = pd.read_html(StringIO(self._sourceData['boxScore']),match='FGM',header=0)
        self.boxScore = {self.teams[1]: tables[1], self.teams[0]: tables[0]}

        # Properly format starters' names for each team
        self.set_starters()

        # Method for getting starters when `GS` column is in box score (it was prior to 2024-25 season)
        #self.starters = {team:[" ".join(player.split(', ')[::-1]) for player in self.boxScore[team].loc[self.boxScore[team].GS==1,'Name'].tolist()[:-1]] for team in self.teams}
    
    def load_pbp(self):
        self.pbp = PbpLoader(self._sourceData['pbp'], self.teams, self.starters)

    def load_shotChart(self):
        
        soup = BeautifulSoup(self._sourceData['shotChart'], "html.parser")
        
        shotsList = soup.find_all('circle')[3:-4]

        shots = pd.DataFrame([shot.attrs for shot in shotsList])
        shots[['Period','player_id','team_id','shot','ShotMade']] = pd.DataFrame(shots['class'].to_list())

        shots['text']    = pd.DataFrame([shot.text for shot in shotsList])
        shots['Team']    = shots['text'].apply(lambda string: re.findall('\\((.+)\\)',string)[0])
        shots['Player']  = shots['text'].apply(lambda string: re.findall('by (.+)\\(',string)[0])
        shots['Time']    = shots['text'].apply(lambda string: re.findall('... (.*) :',string)[0])
        shots['game_id'] = self.gameId

        shots.drop(columns=['r','style','class','shot','text'], inplace=True)

        # Sort the events based on period and time remaining in quarter; this is mainly due to overtime periods being out of order
        shots.sort_values(['Period','Time'],ascending=[True,False],inplace=True)
        shots.reset_index(drop=True,inplace=True)

        self.shotChart = shots
    
    def set_starters(self):
        q1pbp = [quarter for quarter in pd.read_html(StringIO(self._sourceData['pbp']), header=0) if 'Time' in quarter.columns][0]
        self.starters = {}
        for i, team in enumerate(self.teams):
            col = 1 if i==0 else -1
            teamCol = q1pbp.loc[:, q1pbp.columns[col]].fillna('None')
            playerEvents = teamCol.loc[teamCol.str.contains(',') & ~teamCol.str.contains('Team,')]
            names = playerEvents.apply(lambda x: x.split(',')[0])
            starters = names.unique().tolist()
            subsIn = playerEvents.loc[playerEvents.str.contains('substitution in')]
            guaranteedStarters = names.loc[playerEvents.loc[:subsIn.index[0]-1].index].unique().tolist()
            nonStarters = names.loc[subsIn.index].unique().tolist()
            for starter in guaranteedStarters:
                try:
                    nonStarters.remove(starter)
                except ValueError:
                    pass
            
            for sub in nonStarters:
                if len(starters) > 5:
                    starters.remove(sub)
            self.starters[team] = starters
   
    def _save_data_to_file(self):
        if os.path.isdir('D:/DataDirectory/Game'):
            with open(f"D:/DataDirectory/Game/game_{self.gameId}.json", mode="w", encoding="utf-8") as jsonf:
                json.dump(self._sourceData, jsonf)
