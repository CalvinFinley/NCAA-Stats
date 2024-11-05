import pandas as pd

d1Teams = pd.read_csv("./Data/ncaa_synergy_id_names_map_2024_2025.csv").ncaaId25.tolist()

schedule = pd.DataFrame(columns=['teamName1', 'teamId1', 'teamName2', 'teamId2', 'gameId', 'date'])
schedule.to_csv("games_2024_2025.csv", index=False)

teamBox = pd.DataFrame(columns=['Name', 'MP', 'GS', 'FGM', 'FGA', '3FG', '3FGA', 'FT', 'FTA',
       'PTS', 'ORebs', 'DRebs', 'Tot Reb', 'AST', 'TO', 'STL', 'BLK', 'PF',
       'DQ', 'Tech Fouls', 'teamId', 'opponentId', 'gameId'])
teamBox.to_csv("team_box_scores_2024_2025.csv", index=False)

playerBox = pd.DataFrame(columns=['#', 'Name', 'P', 'MP', 'GS', 'FGM', 'FGA', '3FG', '3FGA', 'FT', 'FTA',
       'PTS', 'ORebs', 'DRebs', 'Tot Reb', 'AST', 'TO', 'STL', 'BLK', 'PF',
       'DQ', 'Tech Fouls', 'teamId', 'opponentId', 'gameId'])
playerBox.to_csv("player_box_scores_2024_2025.csv", index=False)

playerPossessionData = pd.DataFrame(columns=[ 'poss', 1,   -1,   2,  -2,   3,   -3,   4,  -4,   5,   -5,   6,  -6,   7,  -7,
         8,  -8,   9,  -9,  10,  -10,  11, -11,  12,  -12,  13, -13,  14,  -14,
        15,  -15,  16,  -16,  17, -17,  18, -18, 19, -19])
playerPossessionData.to_csv("player_possession_stats_2024_2025.csv", index=True)

teamPossessionCount = pd.DataFrame(columns=['teamId', 'possessions'])

teams_eff_dict = {team: {'rating':[0.92, 0.92], 'poss':[0, 0]} for team in d1Teams}
adjustedEfficiency = pd.DataFrame(teams_eff_dict)
adjustedEfficiency = adjustedEfficiency.explode(adjustedEfficiency.columns.tolist()).T
adjustedEfficiency.reset_index(inplace=True)
adjustedEfficiency.columns = ['teamId','adjOff','adjDef','possOff','possDef']

teams_reb_dict = {team: {'rating':[0.3, 0.3], 'poss':[0, 0]} for team in d1Teams}
adjustedRebounding = pd.DataFrame(teams_reb_dict)
adjustedRebounding = adjustedRebounding.explode(adjustedRebounding.columns.tolist()).T
adjustedRebounding.reset_index(inplace=True)
adjustedRebounding.columns = ['teamId', 'adjOffReb', 'adjDefReb', 'chancesOff', 'chancesDef']

adjustedEfficiency.to_csv("adjusted_efficiency_2024_2025.csv", index=False)
adjustedRebounding.to_csv("adjusted_rebounding_2024_2025.csv", index=False)

pbpDf = pd.DataFrame(columns=['description', 'team', 'time', 'quarter', 'eventType', 'team1', 'lineup1', 'team2', 'lineup2', 'gameID'])
pbpDf.to_csv("pbp_2024_2025.csv", index=False)