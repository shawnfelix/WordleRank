from unittest.util import strclass
import discord
from discord.ext import commands
import re
import sqlite3
import pickle

API_KEY = ''

con = sqlite3.connect('wordle-discord.db')
intents = discord.Intents().all()
bot = commands.Bot(command_prefix='!', intents=intents)

MESSAGE_HEADER = '------ [w][o][r][d][l][e] ------\n--------- [r][a][n][k] ---------\n'
HELP_MESSAGE = '''```WordleRank Bot v1.0  Help
!help - list of commands
!mystats - display a full history of your wordle stats
!today - display today's leaderboard
!leaderboard avg - display all time avg score```
'''

class User():
    def __init__(self, username, discriminator, uniqueId:str):
        self.username = username
        self.discriminator = discriminator
        self.uniqueId = uniqueId
    def rawName(self):
        return self.username + '#' + self.discriminator

class WordAttempt():
    def __init__(self, scoreArray, countB, countY, countG):
        self.scoreArray = scoreArray
        self.countB = countB
        self.countY = countY
        self.countG = countG    

class WordleDailyStat():
    def __init__(self, wordleId:int, score, user:User, attemptArrayInt, attemptArray):
        self.wordleId = wordleId
        self.score = score
        self.user = user
        self.attemptArrayInt = attemptArrayInt
        self.attemptArray = attemptArray

# deserializes a list of WordleDailyStat table row into an object
def deserialize(rows):
    queryResult = []
    for serStat in rows:
        stat:WordleDailyStat = pickle.loads(serStat[3])
        queryResult.append(stat)
    return queryResult

# serializes a WordleDailyStat object to be stored in DB
def serialize(statObject:WordleDailyStat):
    return pickle.dumps(statObject)

def insert(stat:WordleDailyStat):
    stmt = 'INSERT INTO WordleDailyStat(wordleId, authorId, serializedBytes) values(?, ?, ?)'
    serialized = serialize(stat)
    data = (stat.wordleId, stat.user.uniqueId, serialized)

    con.execute(stmt, data)
    con.commit()

def getAllWordlePosts():
    stmt = 'SELECT * FROM WordleDailyStat'
    res = con.execute(stmt)
    serializedStats = res.fetchall()

    queryResult = []
    for serStat in serializedStats:
        stat = pickle.loads(serStat[3])
        queryResult.append(stat)
    return queryResult

def getWordlePostsByWordleId(wId):
    stmt = 'SELECT * FROM WordleDailyStat WHERE wordleId = ' + wId
    res = con.execute(stmt)
    serializedStats = res.fetchall()

    return deserialize(serializedStats)

def getUserPosts(userId:str):
    stmt = 'SELECT * FROM WordleDailyStat WHERE authorId = ' + "'%s'"%(userId)
    # execute sql return result rows
    serializedStats = con.execute(stmt).fetchall()

    # deserialize rows into objects
    queryResult = []
    for serStat in serializedStats:
        stat = pickle.loads(serStat[3])
        queryResult.append(stat)
    return queryResult

# commands

def leaderboard(wId:int):
    isTodaysFlag = False
    # find the most recently played leaderboard (today's)
    if wId == -1:
        isTodaysFlag = True
        stmt = 'SELECT MAX(wordleId) from WordleDailyStat;'
        wId = con.execute(stmt).fetchone()[0]
    
    stmt = 'SELECT * FROM WordleDailyStat WHERE wordleId = ' + str(wId)
    todaysPostsSerialized = con.execute(stmt).fetchall()
    todaysPosts = deserialize(todaysPostsSerialized)

    # sort the posts by score
    todaysPosts.sort(key=lambda x: x.score, reverse=False )

    result = {}
    prev = None 
    n = 0
    for post in todaysPosts:
        if prev is None or post.score != prev.score:
            n+=1
            place = n 
            prev = post
        result[post.user.rawName()] = [place, post.score]
    
    # generate the message
    strings = []
    for k, placement in result.items():
        strings.append('\n\t' + str(placement[0]) + '. ' + str(placement[1]) + '/6 - ' + k)
    if isTodaysFlag:
        subtitle = "Today's Leaderboard (" + str(wId) + "):"
    else:
        subtitle = "Wordle " + str(wId) + " Leaderboard:"
    placements = "".join(strings)
    return '```' + MESSAGE_HEADER + subtitle + placements + '```'

def todaysLeaderboard():
    return leaderboard(-1)

def leaderboardAvg():
    stmt = 'SELECT DISTINCT authorId FROM WordleDailyStat'
    ids = con.execute(stmt).fetchall()
    avgs = []

    for id in ids: 
        uS, uF, sA, user = calculateStats(id)
        avgs.append((user.username, sA, uS + uF))
    avgs.sort(key=lambda tup: tup[1], reverse=False)

    # generate the message
    strings = []
    for count, tup in enumerate(avgs):
        strings.append('\n\t' + str(count+1) + '. ' + str(tup[1]) + '/6 - ' + tup[0] + '- Total Played: ' + str(tup[2]))
    subtitle = 'All-time average score leaderboard:'
    placements = "".join(strings)
    return '```' + MESSAGE_HEADER + subtitle + placements + '```'

def calculateStats(userId):
    user = None
    successes = 0
    failures = 0
    scoreSum = 0
    scoreAvg = 0
    allPosts = getUserPosts(userId)

    totalPosts = len(allPosts)
    if totalPosts > 0:
        user = allPosts[0].user
    for post in allPosts:
        scoreSum += post.score
        if post.score != 'X':
            successes += 1
        else:
            failures +=1
    
    # calculate average score
    if totalPosts > 0:
        scoreAvg = round(scoreSum / totalPosts, 2)

    return successes, failures, scoreAvg, user
    
def mystats(userId):
    successes, failures, scoreAvg, user = calculateStats(userId)
    subtitle = 'Your stats:\n\t'
    str1 = str(successes) + ' Successes\n\t' + str(failures) + ' Failures\n\t' + str(scoreAvg) + '/6 Average score'
    return '```' + MESSAGE_HEADER + subtitle + str1 + '```'
    
def processWordleMessage(message):
    if message.author.bot is False:
        isWordlePost = re.match('Wordle \d\d\d .\/\d\n\n[⬛⬜🟩🟨]{5}', message.content)
        if isWordlePost is not None:
            # break up string by line
            wordlePost = message.content.split('\n')
            
            wPostNumber = wordlePost[0][7:10]
            # cast the score to an int
            wPostScore = wordlePost[0][11]
            if wPostScore == 'X':
                wPostScore = 7
            else:
                wPostScore = int(wPostScore)
            
            attemptArrayInt = []
            attemptSet = []

            i = 2
            while i < len(wordlePost):
                # word row count stats
                countB = wordlePost[2].count('⬛') + wordlePost[2].count('⬜')
                countY = wordlePost[2].count('🟨')
                countG = wordlePost[2].count('🟩')

                arrayRes = []
                for c in wordlePost[i]:
                    if c == '⬛' or c == '⬜':
                        arrayRes.append(0)
                    elif c == '🟨':
                        arrayRes.append(1)
                    elif c == '🟩':
                        arrayRes.append(2)
                attemptRow = WordAttempt(arrayRes, countB, countY, countG)
                attemptSet.append(attemptRow)
                attemptArrayInt.append(arrayRes)
                i+= 1
            
            user = User(message.author.display_name, message.author.discriminator, message.author.id)

            dailyStat = WordleDailyStat(wPostNumber, wPostScore, user, attemptArrayInt, attemptSet)
            insert(dailyStat)

class MyClient(discord.Client):
    async def databaseImport(self, channelId):
        channel = client.get_channel(channelId)
        messages = await channel.history(limit=1000).flatten()

        for message in messages:
            processWordleMessage(message)
        
        print('Import success')

    async def on_ready(self):
        print('Logged on as {0}!'.format(self.user))

    async def on_message(self, message):
        processWordleMessage(message)
        print('Message from {0.author}: {0.content}'.format(message))

        if message.content == '!mystats':
            mention = message.author.mention
            response = mention + '\n' + mystats(message.author.id)
            channel = client.get_channel(message.channel.id)
            await channel.send(response)
        elif message.content == '!today':
            response = todaysLeaderboard()
            channel = client.get_channel(message.channel.id)
            await channel.send(response)
        elif message.content == '!leaderboard':
            response = leaderboard(230)
            channel = client.get_channel(message.channel.id)
            await channel.send(response)
        elif message.content == '!leaderboard avg':
            response = leaderboardAvg()
            channel = client.get_channel(message.channel.id)
            await channel.send(response)
        elif message.content == '!help':
            response = HELP_MESSAGE
            channel = client.get_channel(message.channel.id)
            await channel.send(response)
        elif message.content == '!import' and message.author.display_name == 'PHELIX':
            await self.databaseImport(message.channel.id)
        

client = MyClient()
client.run(API_KEY)