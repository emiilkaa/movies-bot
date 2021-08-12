# Movies Bot

Description
---
Movies Bot can help you find information about a movie or pick up a movie you want to watch!

The bot has two main functions: 'Find a movie' and 'Pick a movie'.
'Find a movie' helps you find information about movies you're interested in. First the name of the movie is requested, then the user is asked to choose which of the 5 movies (the first 5 search results on IMDb) he had in mind. The bot then shows basic information about the movie, and offers to see cast, synopsis, and trailers.
'Pick a movie' shows one random movie of the given genre among the first 100 popular movies of that genre in the IMDb top. The information about this movie is shown in the same format as the Find a movie feature.

Installation and Getting Started
---
1. First, install all the required packages listed in `requirements.txt`. This can be done by using the command:
`pip install -r requirements.txt`
2. In the same folder where the `main.py` file is located, put the `tg_token` file containing a single line - your Telegram bot's token.
3. Just run the `main.py` file and enjoy the bot!