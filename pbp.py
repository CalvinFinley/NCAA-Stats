import pandas as pd
from io import StringIO
from copy import deepcopy
    
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
        if self.eventType != 15 and self.eventType != 16: # substitution
            return self.previousEvent.currentLineups
        else:
            lineups = deepcopy(self.previousEvent.currentLineups) # deepcopy for dict to not alter previous events
            player = self.description.split(',')[0].strip()
            if 'substitution out' in self.description:
                try:
                    lineups[self.team].remove(player)
                except:
                    lineups[self.team] = list(set(lineups[self.team]))
                
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
        if any(self.eventType == n for n in [3,4,5,6]): 
            return True
        else: return False
    
    @property
    def isLastFTA(self):
        return any(ftType in self.description for ftType in ['2of2','3of3'])
    
    @property
    def eventType1(self):
        self.attributes = []
        possibilities = ['rebound defensive', 'rebound offensive', 
                         ['2pt', ' made'], ['2pt', ' missed'], ['3pt', ' made'], ['3pt', ' missed'], 
                         ['freethrow', ' made'], ['freethrow', ' missed'], ['3pt', ' made'], ['3pt', ' missed'], 
                         'turnover', 'assist', 'steal', ', block']
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
        if '2pt' in text and 'missed' in text:
            return 3
        if '3pt' in text and 'missed' in text:
            return 4
        if '2pt' in text and 'made' in text:
            return 5
        if '3pt' in text and 'made' in text:
            return 6
        if 'assist' in text:
            return 7
        if 'rebound' in text and 'offensive' in text:
            return 8
        if 'rebound' in text and 'defensive' in text:
            return 9
        if any(etype in text for etype in ['foulon', 'foul']):
            return 10
        if 'heldball' in text:
            return 11
        if 'steal' in text:
            return 12
        if ', turnover' in text:
            return 13
        if 'timeout' in text:
            return 14
        if 'substitution in' in text:
            return 15
        if 'substitution out' in text:
            return 16
        if 'freethrow' in text and 'missed' in text and not any(f'{n}of{n}' in text for n in [1,2,3]):
            return 17
        if 'freethrow' in text and 'made' in text:
            return 18
        if 'freethrow' in text and 'missed' in text:
            return 19
        if 'end' in text:
            return 20