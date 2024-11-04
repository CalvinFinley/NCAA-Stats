import requests
import pandas as pd
import json
from io import StringIO
import os
import re

from utility import base_url, headers

class Team():

    def __init__(self, id, loadPlayerStats=False, source='web') -> None:
        self.teamId = id
        self.name = None
        self.source = source
        
        self.load_data(loadPlayerStats)
    
    def load_data(self, loadPlayerStats: bool):
        if self.source == 'web':
            self._sourceData = {}
            self._sourceData['games'] = requests.get(base_url + f'teams/{self.teamId}', headers=headers).text
            self._sourceData['roster'] = requests.get(base_url + f'teams/{self.teamId}/roster', headers=headers).text
            if loadPlayerStats:
                self._sourceData['playerStats'] = requests.get(base_url + f'teams/{self.teamId}/season_to_date_stats', headers=headers).text
            #self._save_data_to_file()
        elif self.source == 'file':
            if os.path.isdir('DataDirectory/Team'):
                with open(f"DataDirectory/Team/team_{self.teamId}.json", mode='r', encoding='utf-8') as htmlf:
                    self._sourceData =  json.load(htmlf)
            else:
                pass # Add error handling for if there is no saved data
        else:
            pass # Add error handling for if wrong source type is given
        
        self.load_games()
        self.load_roster()
        if loadPlayerStats:
            self.load_player_stats()
        
    def load_games(self):
                        
        games = pd.read_html(StringIO(self._sourceData['games']), extract_links='body')[0]
        games = games.loc[0::2]
        games = games.loc[~games.Opponent.apply(lambda x: x[0]).str.contains('Contest exempted')] # Error handling, see 560986

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
        games[['Result','TeamScore','OpponentScore']] = list(map(lambda l: l[:3], games['Result'].apply(lambda x: re.split(' |-', x))))

        games = games[['GameID','Date','Opponent','OpponentID','Result','TeamScore','OpponentScore','Attendance']]
        games.reset_index(drop=True, inplace=True)

        self.games = games

    def load_roster(self):
            
            roster = pd.read_html(StringIO(self._sourceData['roster']), extract_links='body')[0]
            ids = roster['Name'].apply(lambda x: x[1].split('/')[-1])
            roster = roster.map(lambda x: x[0])
            roster['PlayerID'] = ids
            roster = roster[['PlayerID', 'Name', '#', 'Class', 'Position', 'Height', 'Hometown','High School', 'GP', 'GS']]
            
            self.roster = roster
    
    def load_player_stats(self):
        self.playerStats = pd.read_html(StringIO(self._sourceData['playerStats']))[0]

    def _save_data_to_file(self):
        if os.path.isdir('DataDirectory/Team') and self.source == 'web':
            with open(f"DataDirectory/Team/team_{self.teamId}.json", mode="w", encoding="utf-8") as jsonf:
                json.dump(self._sourceData, jsonf)