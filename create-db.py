import sqlite3 as sql

con = sql.connect('wordle-discord.db')


con.execute("""
    CREATE TABLE WordleDailyStat (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        wordleId INT,
        authorId TEXT,
        serializedBytes TEXT
        );
""")