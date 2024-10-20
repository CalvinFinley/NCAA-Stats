
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

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
base_url = "https://stats.ncaa.org/"


def get_Teams(year):
    r = requests.get("https://stats.ncaa.org/selection_rankings/nitty_gritties/37268", headers=headers)
    soup = BeautifulSoup(r.text, 'html.parser')
    net_table = soup.find('tbody')
    names, ids, conferences = [], [], []

    for row in net_table.find_all('tr'):
        names.append(row.contents[1].text.strip())
        ids.append(row.contents[1].contents[-1].get('href'))
        conferences.append(row.contents[3].text)
    print('b')
    return {team:List for team,List in zip(names,zip(ids,conferences))}

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
            self._save_data_to_file()
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


class Game():

    def __init__(self, gameID, loadShotChart=False, source='web') -> None:
        self.gameId = gameID
        self.teams = None
        self.source = source

        self.load_data(loadShotChart)

    
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
            if os.path.isdir('DataDirectory/Game'):
                with open(f"DataDirectory/Game/game_{self.gameId}.json", mode='r', encoding='utf-8') as htmlf:
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
        self.starters = {team:[" ".join(player.split(', ')[::-1]) for player in self.boxScore[team].loc[self.boxScore[team].GS==1,'Name'].tolist()[:-1]] \
                         for team in self.teams}
    
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
   
    def _save_data_to_file(self):
        if os.path.isdir('DataDirectory/Game'):
            with open(f"DataDirectory/Game/game_{self.gameId}.json", mode="w", encoding="utf-8") as jsonf:
                json.dump(self._sourceData, jsonf)
    
class PbpItem():

    def __init__(self, row):
        self.__description  = row.text
        self.__team         = row.team
        self.__time         = row.Time
        self.__quarter      = row.Quarter
        self.__eventType    = row.eventType
    
    @property
    def description(self):
        return self.__description

    @property
    def team(self):
        return self.__team
    
    @property
    def time(self):
        return self.__time
    
    @property
    def quarter(self):
        return self.__quarter
    
    @property
    def eventType(self):
        return self.__eventType
    
    @property
    def previousEvent(self):
        return self.__previousEvent
    
    @previousEvent.setter
    def previousEvent(self, event):
        self.__previousEvent = event
    
    @property
    def currentLineups(self):
        if not self.previousEvent:
            return self.__currentLineups
        if self.eventType != 12: # substitution
            return self.previousEvent.currentLineups
        else:
            lineups = deepcopy(self.previousEvent.currentLineups) # deepcopy for dict to not alter previous events
            player = self.description.split(',')[0]
            if 'substitution out' in self.description:
                lineups[self.team].remove(player)
            if 'substitution in' in self.description:
                lineups[self.team].append(player)
            return lineups
    
    @currentLineups.setter
    def currentLineups(self, lineups):
        self.__currentLineups = lineups
        
    @property
    def data(self):
        return self.__dict__
    
    @property
    def isPossessionEnding(self):
        if any(playType in self.description for playType in ['rebound defensive',' turnover']):
            return True
        if (self.isFGA or self.isLastFTA) and 'made' in self.description:
            return True
        else: return False
    
    @property
    def isFGA(self):
        if self.eventType == 3 or self.eventType == 4: 
            return True
        else: return False
    
    @property
    def isLastFTA(self):
        return any(ftType in self.description for ftType in ['2of2','1of1','3of3'])
    
    @property
    def eventType1(self):
        types = ['rebound (defensive,offensive,team,offensivedeadball)', 'turnover (offensive,badpass,travel,outofbounds,lostball,other,shotclock,team)','assist', \
                 'steal','jumpball (won,lost,heldball)','substitution (in,out)','foul (personal,offesnsive,shooting,2freethrow,1freethrow)','foulon','freethrow (#of#,made,missed)', \
                 'timeout (short,full,commercial)']
        shotAttributes = ['made','missed','layup','jumpshot','hookshot','turnaroundjumpshot','drivinglayup','stepbackjumpshot','pullupjumpshot','floatingjumpshot','blocked','fromturnover','2ndchance','pointsinthepaint','fastbreak']

class PbpLoader():

    def __init__(self, data, teams: list, starters: dict) -> None:
        self.load_pbp(data, teams, starters)
    
    def load_pbp(self, data, teams: list, starters: dict):
        pbp = [quarter for quarter in pd.read_html(StringIO(data), header=0) if 'Time' in quarter.columns]
        
        # Add quarter to pbp
        for q, table in enumerate(pbp):
            table.insert(0,'Quarter',q+1)
        
        pbp = pd.concat(pbp).reset_index(drop=True)
        pbp.columns = ['Quarter','Time',teams[0],'Score',teams[1]]

        # Add column for the text of each event
        team1 = pbp.loc[~pbp.iloc[:,-1].isna(),pbp.columns[-1]].to_frame('text')
        team1['team'] = pbp.columns[-1]
        team2 = pbp.loc[~pbp.iloc[:,2].isna(),pbp.columns[2]].to_frame('text')
        team2['team'] = pbp.columns[2]

        combinedDesc = pd.concat([team1,team2]).sort_index()
        combinedDesc.loc[combinedDesc.index.duplicated(keep='last'),'team'] = None
        combinedDesc = combinedDesc.loc[~combinedDesc.index.duplicated()]

        pbp[['text','team']] = combinedDesc

        # Delete placeholder offensive rebounds between free throws
        pbp.drop(index=pbp[pbp.text.str.contains('offensivedeadball')].index, inplace=True)

        # Reorder events recorded at the same time
        pbp['eventType'] = pbp.text.apply(self.assign_event_type)
        df = pbp.sort_values(by=['Quarter','Time','eventType'],ascending=[True,False,True]).reset_index(drop=True)

        # Create list of play-by-play items
        self.items = []
        for i, row in df.iterrows():
            self.items.append(PbpItem(row))
            # Manually set starters
            if i == 0:
                self.items[-1].currentLineups = starters
                self.items[-1].previousEvent = None
            else: 
                self.items[-1].previousEvent = self.items[-2]
                
    @staticmethod
    def assign_event_type(text):
        if 'start' in text:
            return 0
        if any(etype in text for etype in ['won', 'lost', 'startperiod']) and 'jumpball' in text:
            return 1
        if ', block' in text:
            return 2
        if any(etype in text for etype in ['2pt', '3pt']) and 'missed' in text:
            return 3
        if any(etype in text for etype in ['2pt', '3pt']) and 'made' in text:
            return 4
        if 'assist' in text:
            return 5
        if 'rebound' in text:
            return 6
        if any(etype in text for etype in ['foulon', 'foul']):
            return 7
        if 'heldball' in text:
            return 8
        if 'steal' in text:
            return 9
        if 'turnover' in text:
            return 10
        if 'timeout' in text:
            return 11
        if 'substitution' in text:
            return 12
        if 'freethrow' in text:
            return 13
        if 'end' in text:
            return 14