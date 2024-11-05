from game import Game
from team import Team
from utility import headers

import datetime
import requests
import numpy as np
import pandas as pd
from bs4 import BeautifulSoup
from tqdm import tqdm
from collections import defaultdict
from itertools import combinations

season = 2025
seasonStartDate = datetime.date(2024, 11, 4)
base_schedule = "https://stats.ncaa.org/season_divisions/18423/livestream_scoreboards?utf8=%E2%9C%93&season_division_id="

d1Teams = pd.read_csv("./Data/ncaa_synergy_id_names_map_2024_2025.csv").ncaaName.tolist()

allGames = pd.read_csv(f"games_{season-1}_{season}.csv", parse_dates=['date'])
# Comment out this line on the first day, then uncomment
#allGames['date'] = allGames['date'].dt.date

allPbp = pd.read_csv(f"pbp_{season-1}_{season}.csv")

class Day():
    def __init__(self, date, playerPossStats, teamEffDict, teamRebDict):
        self.processSchedule(date)
        self.loadGames()
        self.loadBoxScores()
        self.proccessPBP(playerPossStats)
        self.adjustRatings(teamEffDict, teamRebDict)

    def processSchedule(self, date):
        r = requests.get(base_schedule + f"&game_date={date.month}%2F{date.day}%2F{date.year}", headers=headers)
        
        if r.status_code != 200:
            raise Exception(f"Request for {date} was not successful")
        else:
            soup = BeautifulSoup(r.text, parser='lxml')
        teamTags = soup.find_all('td', attrs={'class':'opponents_min_width'})
        gameIds = [tag['href'] for tag in soup.find_all('a', string='Box Score')]
        gameIds = [link.split('/')[2] for link in gameIds]

        cancelledGames = soup.find_all('div',attrs={'class':'table-responsive'})
        cancelledGames = [ix for ix, game in enumerate(cancelledGames) if 'Canceled' in game.text]

        names1 = []
        names2 = []
        ids1 = []
        ids2 = []

        for i, tag in enumerate(teamTags):
            name = tag.text.strip()
            
            
            if len(tag.contents) > 1:
                teamid = tag.contents[1]['href']
                teamid = teamid.split('/')[-1]
                name = "(".join(name.split(' (')[:-1]) # Get rid of record attached to team name
            else:
                teamid = None
            
            if i % 2 == 0:
                names1.append(name)
                ids1.append(teamid)
            else:
                names2.append(name)
                ids2.append(teamid)

        for cancelled in cancelledGames:
            names1.pop(cancelled)
            ids1.pop(cancelled)
            names2.pop(cancelled)
            ids2.pop(cancelled)
        
        schedule = pd.DataFrame({'teamName1':names1, 'teamId1':ids1, 'teamName2':names2, 'teamId2':ids2, 'gameId': gameIds})
        schedule['date'] = date

        self.schedule = schedule

    def loadGames(self):
        self.games = []
        for row in tqdm(self.schedule.itertuples()):
            if row.teamName1 in d1Teams and row.teamName2 in d1Teams:
                self.games.append(Game(row.gameId, source='web'))
            
    def loadBoxScores(self):
        playerBoxScores = pd.DataFrame()
        for game in tqdm(self.games):
            for teamid, box in game.boxScore.items():
                stats = box.iloc[:-2].copy()
                stats['teamId'] = teamid
                stats['opponentId'] = [team for team in game.teams if team != teamid][0]
                stats['gameId'] = game.gameId
                playerBoxScores = pd.concat([playerBoxScores, stats])
        playerBoxScores.reset_index(drop=True)
        self.playerBox = playerBoxScores

        teamBoxScores = pd.DataFrame()
        for game in tqdm(self.games):
            for teamid, box in game.boxScore.items():
                stats = box.iloc[-1].copy()
                stats['teamId'] = teamid
                stats['opponentId'] = [team for team in game.teams if team != teamid][0]
                stats['gameId'] = game.gameId
                teamBoxScores = pd.concat([teamBoxScores, stats.to_frame().T])
        #teamBoxScores = teamBoxScores.drop(columns=['#', 'P'])
        teamBoxScores = teamBoxScores.reset_index(drop=True)
        self.teamBox = teamBoxScores

    def proccessPBP(self, playerDict):
        teamPossessions = {}

        for game in tqdm(self.games):
            
            ends = np.where([item.isPossessionEnding for item in game.pbp.items])[0]+1
            possessions = np.split(game.pbp.items,ends)
            global poss
            for poss in possessions:
                # Event occurances for each team during the possession
                possStats = {team:[e.eventType if e.team==team else -1*e.eventType if e.team else None for e in poss] for team in game.teams}
                if any([ any(events) for events in possStats.values() ]):
                    for team in game.teams:
                        # Count the number of occurances for each event type while lineups where on the floor
                        for lineup in list(combinations(poss[-1].currentLineups[team],1)):
                            for pt in possStats[team]:
                                if pt and not np.isnan(pt):
                                    playerDict[lineup[0]][pt] += 1
                            playerDict[lineup[0]]['poss'] += 0.5
            
            for team in game.teams:
                teamPossessions[team] = sum([ any(e.team for e in poss) for poss in possessions ]) / 2
        self.teamPossessions = pd.DataFrame(teamPossessions.items(), columns=['teamId', 'possessions'])
        self.playerData = pd.DataFrame(dict(playerDict)).T

    def adjustRatings(self, effDict, rebDict):

        for game in tqdm(self.games):
            
            teams = game.teams

            points = [game.boxScore[team].PTS.iloc[-1] for team in teams]
            aprox_poss = [game.boxScore[team].FGA.iloc[-1] + game.boxScore[team].TO.iloc[-1]
                        + .46 * game.boxScore[team].FTA.iloc[-1] - game.boxScore[team].ORebs.iloc[-1] for team in game.teams]
            possessions = [(aprox_poss[0] + aprox_poss[1])/2]*2
            print
            self.adjustEff(list(map(int, teams)), points, possessions, effDict)

            rebs = [game.boxScore[team].ORebs.iloc[-1] for team in teams]
            chances = [game.boxScore[team].FGA.iloc[-1] - game.boxScore[team].FGM.iloc[-1] for team in game.teams]
            self.adjustReb(list(map(int, teams)), rebs, chances, rebDict)
    
    @staticmethod
    def adjustEff(teams: list, points: list, possessions: list, teams_dict, nationalAverage=0.92, tol=0.0001):
        poss1 = teams_dict[teams[0]]['poss']
        poss2 = teams_dict[teams[1]]['poss']

        weighted_off1 = teams_dict[teams[0]]['rating'][0] * (poss1[0] / (poss1[0] + possessions[0]))
        weighted_def2 = teams_dict[teams[1]]['rating'][1] * (poss2[1] / (poss2[1] + possessions[0]))

        weighted_def1 = teams_dict[teams[0]]['rating'][1] * (poss1[1] / (poss1[1] + possessions[1]))
        weighted_off2 = teams_dict[teams[1]]['rating'][0] * (poss2[0] / (poss2[0] + possessions[1]))

        new_d = teams_dict[teams[1]]['rating'][1]
        new_o = teams_dict[teams[0]]['rating'][0] # for first iteration

        # if it is a team's first game
        if poss1[0] == 0 or poss2[1] == 0:
            new_o, new_d = ((points[0] / possessions[0]) / new_d)*nationalAverage * (possessions[0] / (poss1[0] + possessions[0])) + weighted_off1, \
                            ((points[0] / possessions[0]) / new_o)*nationalAverage * (possessions[0] / (poss2[1] + possessions[0])) + weighted_def2
        else:    
            while True:
                old_o = new_o
                new_o = ((points[0] / possessions[0]) / new_d)*nationalAverage * (possessions[0] / (poss1[0] + possessions[0])) + weighted_off1
                
                new_d = ((points[0] / possessions[0]) / new_o)*nationalAverage * (possessions[0] / (poss2[1] + possessions[0])) + weighted_def2

                if abs(new_o - old_o) < tol:
                    break
        teams_dict[teams[0]]['rating'][0] = new_o
        teams_dict[teams[0]]['poss'][0] += possessions[0]
        teams_dict[teams[1]]['rating'][1] = new_d
        teams_dict[teams[1]]['poss'][1] += possessions[0]
        
        new_d = teams_dict[teams[0]]['rating'][1]
        new_o = teams_dict[teams[1]]['rating'][0] # for first iteration
        
        # if it is a team's first game
        if poss2[0] == 0 or poss1[1] == 0:
            new_o, new_d = ((points[1] / possessions[1]) / new_d)*nationalAverage * (possessions[1] / (poss2[0] + possessions[1])) + weighted_off2, \
                        ((points[1] / possessions[1]) / new_o)*nationalAverage * (possessions[1] / (poss1[1] + possessions[1])) + weighted_def1
        else: 
            while True:
                old_o = new_o
                new_o = ((points[1] / possessions[1]) / new_d)*nationalAverage * (possessions[1] / (poss2[0] + possessions[1])) + weighted_off2

                new_d = ((points[1] / possessions[1]) / new_o)*nationalAverage * (possessions[1] / (poss1[1] + possessions[1])) + weighted_def1
                
                if abs(new_o - old_o) < tol:
                    break
        teams_dict[teams[1]]['rating'][0] = new_o
        teams_dict[teams[1]]['poss'][0] += possessions[1]
        teams_dict[teams[0]]['rating'][1] = new_d
        teams_dict[teams[0]]['poss'][1] += possessions[1]

    @staticmethod
    def adjustReb(teams: list, rebounds: list, possessions: list, reb_dict, nationalAverage=0.31, tol=0.0001):
        poss1 = reb_dict[teams[0]]['poss']
        poss2 = reb_dict[teams[1]]['poss']

        weighted_off1 = reb_dict[teams[0]]['rating'][0] * (poss1[0] / (poss1[0] + possessions[0]))
        weighted_def2 = reb_dict[teams[1]]['rating'][1] * (poss2[1] / (poss2[1] + possessions[0]))

        weighted_def1 = reb_dict[teams[0]]['rating'][1] * (poss1[1] / (poss1[1] + possessions[1]))
        weighted_off2 = reb_dict[teams[1]]['rating'][0] * (poss2[0] / (poss2[0] + possessions[1]))

        new_d = reb_dict[teams[1]]['rating'][1]
        new_o = reb_dict[teams[0]]['rating'][0] # for first iteration

        # if it is a team's first game
        if poss1[0] == 0 or poss2[1] == 0:
            new_o, new_d = ((rebounds[0] / possessions[0]) / new_d)*nationalAverage * (possessions[0] / (poss1[0] + possessions[0])) + weighted_off1, \
                            ((rebounds[0] / possessions[0]) / new_o)*nationalAverage * (possessions[0] / (poss2[1] + possessions[0])) + weighted_def2
        else:    
            while True:
                old_o = new_o
                new_o = ((rebounds[0] / possessions[0]) / new_d)*nationalAverage * (possessions[0] / (poss1[0] + possessions[0])) + weighted_off1
                
                new_d = ((rebounds[0] / possessions[0]) / new_o)*nationalAverage * (possessions[0] / (poss2[1] + possessions[0])) + weighted_def2

                if abs(new_o - old_o) < tol:
                    break
        reb_dict[teams[0]]['rating'][0] = new_o
        reb_dict[teams[0]]['poss'][0] += possessions[0]
        reb_dict[teams[1]]['rating'][1] = new_d
        reb_dict[teams[1]]['poss'][1] += possessions[0]
        
        new_d = reb_dict[teams[0]]['rating'][1]
        new_o = reb_dict[teams[1]]['rating'][0] # for first iteration
        
        # if it is a team's first game
        if poss2[0] == 0 or poss1[1] == 0:
            new_o, new_d = ((rebounds[1] / possessions[1]) / new_d)*nationalAverage * (possessions[1] / (poss2[0] + possessions[1])) + weighted_off2, \
                        ((rebounds[1] / possessions[1]) / new_o)*nationalAverage * (possessions[1] / (poss1[1] + possessions[1])) + weighted_def1
        else: 
            while True:
                old_o = new_o
                new_o = ((rebounds[1] / possessions[1]) / new_d)*nationalAverage * (possessions[1] / (poss2[0] + possessions[1])) + weighted_off2

                new_d = ((rebounds[1] / possessions[1]) / new_o)*nationalAverage * (possessions[1] / (poss1[1] + possessions[1])) + weighted_def1
                
                if abs(new_o - old_o) < tol:
                    break
        reb_dict[teams[1]]['rating'][0] = new_o
        reb_dict[teams[1]]['poss'][0] += possessions[1]
        reb_dict[teams[0]]['rating'][1] = new_d
        reb_dict[teams[0]]['poss'][1] += possessions[1]

today = datetime.date.today()
dateList = [seasonStartDate + datetime.timedelta(days=x) for x in range((today - seasonStartDate).days)]
dateList = [d for d in dateList if d not in allGames.date.unique()]
print(dateList)

for date in dateList:
    print(date)

    teamBox = pd.read_csv("team_box_scores_2024_2025.csv")
    playerBox = pd.read_csv("player_box_scores_2024_2025.csv")
    playerPossessionData = pd.read_csv("player_possession_stats_2024_2025.csv", index_col=0)
    adjustedEfficiency = pd.read_csv("adjusted_efficiency_2024_2025.csv")
    adjustedRebounding = pd.read_csv("adjusted_rebounding_2024_2025.csv")

    playerPossessionData.columns = ['poss'] + list(map(int, playerPossessionData.columns[1:]))
    playerPossDict = defaultdict(lambda: defaultdict(int), playerPossessionData.T.to_dict())
    adjEffDict = {team['teamId']:{'rating':[team['adjOff'],team['adjDef']], 'poss':[team['possOff'],team['possDef']]} 
                  for team in adjustedEfficiency.to_dict(orient='records')}
    adjRebDict = {team['teamId']:{'rating':[team['adjOffReb'],team['adjDefReb']], 'poss':[team['chancesOff'],team['chancesDef']]} 
                  for team in adjustedRebounding.to_dict(orient='records')}

    todaysGames = Day(date, playerPossDict, adjEffDict, adjRebDict)

    teamBox = pd.concat([teamBox, todaysGames.teamBox])
    playerBox = pd.concat([playerBox, todaysGames.playerBox])
    playerPossessionData = pd.DataFrame(dict(playerPossDict)).T
    playerPossessionData = playerPossessionData[[ 'poss', 1,   -1,   2,  -2,   3,   -3,   4,  -4,   5,   -5,   6,  -6,   7,  -7,
         8,  -8,   9,  -9,  10,  -10,  11, -11,  12,  -12,  13, -13,  14,  -14,
        15,  -15,  16,  -16,  17, -17,  18, -18, 19, -19]]

    adjustedEfficiency = pd.DataFrame(adjEffDict)
    adjustedEfficiency = adjustedEfficiency.explode(adjustedEfficiency.columns.tolist()).T
    adjustedEfficiency.reset_index(inplace=True)
    adjustedEfficiency.columns = ['teamId','adjOff','adjDef','possOff','possDef']

    adjustedRebounding = pd.DataFrame(adjRebDict)
    adjustedRebounding = adjustedRebounding.explode(adjustedRebounding.columns.tolist()).T
    adjustedRebounding.reset_index(inplace=True)
    adjustedRebounding.columns = ['teamId','adjOffReb','adjDefReb','chancesOff','chancesDef']

    teamBox.to_csv("team_box_scores_2024_2025.csv", index=False)
    playerBox.to_csv("player_box_scores_2024_2025.csv", index=False)
    playerPossessionData.to_csv("player_possession_stats_2024_2025.csv", index=True)
    adjustedEfficiency.to_csv("adjusted_efficiency_2024_2025.csv", index=False)
    adjustedRebounding.to_csv("adjusted_rebounding_2024_2025.csv", index=False)

    allGames = pd.concat([allGames, todaysGames.schedule])

    dailyPbp = []
    for game in todaysGames.games:
        items = [list(event.data.values())[:5] + [ str(a[i]) for a in event.currentLineups.items() for i in range(2)] + [game.gameId] for event in game.pbp.items]
        gameDf = pd.DataFrame(items, columns=['description', 'team', 'time', 'quarter', 'eventType', 'team1', 'lineup1', 'team2', 'lineup2', 'gameID'])
        dailyPbp.append(gameDf)
    allPbp = pd.concat([allPbp] + dailyPbp)

allGames.to_csv("games_2024_2025.csv", index=False)
allPbp.to_csv("pbp_2024_2025.csv", index=False)