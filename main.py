import logging
import random
import re
import requests

import aiogram.utils.markdown as md
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.dispatcher.filters import Text
from aiogram.utils.exceptions import BotBlocked, MessageToDeleteNotFound
from aiogram.utils.helper import Helper, HelperMode, Item
from bs4 import BeautifulSoup
from imdb import IMDb
from youtubesearchpython import VideosSearch


class BotStates(Helper):
    mode = HelperMode.snake_case
    FIND_MOVIE = Item()


class ImdbParser:
    def __init__(self):
        self.ia = IMDb()

    def get_first_results(self, search_query, n=5):
        movies = self.ia.search_movie(search_query)
        if n < len(movies):
            movies = movies[:n]
        for i in range(len(movies)):
            desc = movies[i]["title"]
            try:
                desc += " (" + str(movies[i]["year"]) + ")"
            except KeyError:
                pass
            movies[i] = (desc, movies[i].movieID)
        return movies

    def __call__(self, movie_id):
        movie = self.ia.get_movie(movie_id)
        self.ia.update(movie, info="akas")

        titles = [movie["title"]]
        try:
            titles.append(movie["original title"])
        except KeyError:
            try:
                if len(movie["akas"]) > 0 and "(original title)" in movie["akas"][0]:
                    original_title = (
                        movie["akas"][0].replace("(original title)", "").strip()
                    )
                    titles.append(original_title)
            except KeyError:
                pass
        if len(titles) == 2 and titles[1] == titles[0]:
            titles.pop()

        countries = year = directors = genre = rating = plot = cover_url = None

        try:
            countries = ", ".join(movie["country"])
        except KeyError:
            pass

        try:
            year = movie["year"]
        except KeyError:
            self.ia.update(movie, info="release dates")
            try:
                if len(movie["release dates"]) > 0:
                    year = int(
                        re.search(
                            r"\d{1,2}\s[a-zA-Z]{3,9}\s\d{4}", movie["release dates"][0]
                        ).group(0)[-4:]
                    )
            except (KeyError, AttributeError, ValueError):
                pass

        try:
            directors = movie["directors"]
            for i in range(len(directors)):
                directors[i] = directors[i]["name"]
            directors = ", ".join(directors)
        except KeyError:
            pass

        try:
            genre = ", ".join(movie["genre"])
        except KeyError:
            pass

        try:
            rating = movie["rating"]
        except KeyError:
            pass

        try:
            if len(movie["plot"]) > 0:
                plot = movie["plot"][0].split("::")[0]
        except KeyError:
            pass

        try:
            cover_url = movie["full-size cover url"]
        except KeyError:
            try:
                cover_url = movie["cover url"]
            except KeyError:
                pass

        result = f""
        if cover_url is not None:
            result += f"{md.hide_link(cover_url)}"
        result += f'{md.hbold("Title")}: {md.quote_html(titles[0])}\n'
        if len(titles) == 2:
            result += f'{md.hbold("Original title")}: {md.quote_html(titles[1])}\n'
        result += f"\n"
        if year is not None:
            result += f'{md.hbold("Release year")}: {year}\n'
        if countries is not None:
            result += f'{md.hbold("Countries")}: {countries}\n'
        if directors is not None:
            result += f'{md.hbold("Directors")}: {directors}\n'
        if genre is not None:
            result += f'{md.hbold("Genres")}: {genre}\n'
        if rating is not None:
            result += f'{md.hbold("IMDb rating")}: {rating}\n'
        if plot is not None and len(result) + len(plot) >= 40900:
            plots_url = f"https://www.imdb.com/title/tt{movie_id}/plotsummary"
            result += f'\nYou can read plot summaries {md.hlink("here", plots_url)}.'
        elif plot is not None:
            result += f'\n{md.hbold("Plot summary")}:\n{md.quote_html(plot)}'
        return result

    def get_cast(self, movie_id):
        movie = self.ia.get_movie(movie_id)
        cast = movie["cast"]
        message = f":\n\n"
        if len(cast) > 30:
            cast = cast[:30]
            message = f" (first roles):\n\n"
        result = f'{md.hbold("Cast")}' + message
        k = 0
        for i in range(len(cast)):
            try:
                result += f'{i + 1 - k}. {md.hbold(cast[i]["name"])}'
                if str(cast[i].currentRole).strip():
                    result += f" as {str(cast[i].currentRole).strip()}"
                if str(cast[i].notes).strip():
                    note = str(cast[i].notes).strip()
                    if note[0] != "(" and note[-1] != ")":
                        note = "(" + note + ")"
                    result += f" {note}"
                result += f"\n"
            except KeyError:
                k += 1
        if "first" in message:
            url = "https://www.imdb.com/title/tt" + movie_id + "/fullcredits/"
            result += f'\nYou can see the full cast and crew {md.hlink("here", url)}. '
        return result

    def get_synopsis(self, movie_id):
        movie = self.ia.get_movie(movie_id)
        try:
            return f'{md.hbold("Synopsis")}:\n\n{movie["synopsis"][0]}'
        except (KeyError, IndexError):
            return f"It looks like we don't have a synopsis for this title yet 😞"

    def get_trailers(self, movie_id):
        movie = self.ia.get_movie(movie_id)
        title = movie["title"]
        year = None
        try:
            year = movie["year"]
        except KeyError:
            self.ia.update(movie, info="release dates")
            try:
                if len(movie["release dates"]) > 0:
                    year = int(
                        re.search(
                            r"\d{1,2}\s[a-zA-Z]{3,9}\s\d{4}", movie["release dates"][0]
                        ).group(0)[-4:]
                    )
            except (KeyError, AttributeError, ValueError):
                pass
        if year is not None:
            search_query = f"{title} ({year}) trailer"
        else:
            search_query = f"{title} trailer"
        search = VideosSearch(search_query, limit=10)
        results = search.result()
        result_message = f'{md.hbold("Trailers")}:\n\n'
        for i in range(10):
            result_message += f'{i + 1}) {md.hlink(results["result"][i]["title"], results["result"][i]["link"])}\n'
        warning = (
            f'These are the top 10 search results for "{search_query}" on YouTube. We apologize if the '
            "trailer you were looking for is not among "
            "them."
        )
        result_message += f"\n{md.hitalic(warning)}"
        return result_message

    @staticmethod
    def get_random_by_genre(genre):
        modify_genres = {"Film Noir": "film-noir", "Short Film": "short"}
        if genre in modify_genres:
            genre = modify_genres[genre]
        genre = genre.lower()
        page = random.randint(0, 1) * 50 + 1
        url = (
            f"https://www.imdb.com/search/title/?title_type=feature&genres={genre}&view=simple&start={page}&explore"
            f"=genres"
        )
        r = requests.get(url)
        soup = BeautifulSoup(r.text, "lxml")
        num = random.randint(0, 49)
        movie_url = soup.find_all("span", class_="lister-item-header")[num].a["href"]
        movie_id = re.search(r"/tt\d+/", movie_url).group(0)[3:-1]
        return movie_id


with open("tg_token", encoding="utf-8") as tg_token:
    TG_TOKEN = tg_token.readline().strip()

bot = Bot(token=TG_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot, storage=MemoryStorage())
dp.middleware.setup(LoggingMiddleware())
logging.basicConfig(level=logging.INFO)

menu = types.ReplyKeyboardMarkup(
    resize_keyboard=True, row_width=1, one_time_keyboard=True
)
menu.add(*["Find a movie", "Pick a movie"])

imdb_parser = ImdbParser()

genres = [
    "Action",
    "Adventure",
    "Animation",
    "Biography",
    "Comedy",
    "Crime",
    "Documentary",
    "Drama",
    "Family",
    "Fantasy",
    "Film Noir",
    "History",
    "Horror",
    "Music",
    "Musical",
    "Mystery",
    "Romance",
    "Sci-Fi",
    "Short Film",
    "Sport",
    "Thriller",
    "War",
    "Western",
]

pages = []
for page_num in range(4):
    pages.append(types.InlineKeyboardMarkup(row_width=3))
    current_page_buttons = []
    for j in range(6 * page_num, min(6 * page_num + 6, 23)):
        current_page_buttons.append(
            types.InlineKeyboardButton(
                text=genres[j], callback_data="Genre_" + genres[j]
            )
        )
    pages[-1].add(*current_page_buttons)
    if page_num == 0:
        pages[-1].add(
            types.InlineKeyboardButton(text="▶️", callback_data="genres_page_2")
        )
    elif page_num == 3:
        pages[-1].add(
            types.InlineKeyboardButton(text="◀️", callback_data="genres_page_3")
        )
    else:
        pages[-1].add(
            types.InlineKeyboardButton(
                text="◀", callback_data="genres_page_" + str(page_num)
            )
        )
        pages[-1].insert(
            types.InlineKeyboardButton(
                text="▶️", callback_data="genres_page_" + str(page_num + 2)
            )
        )
    pages[-1].add(
        types.InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_search")
    )


@dp.errors_handler(exception=BotBlocked)
async def error_bot_blocked(update: types.Update, exception: BotBlocked):
    return True


@dp.message_handler(commands="start")
async def cmd_start(message: types.Message):
    start_message = (
        "Hi! This is Movies Bot and it will help you search for the right information on movies you're "
        "interested in or pick up movies you want to watch!\nTo get information about a movie, "
        "click on 'Find a movie' and follow the instructions. In addition to basic movie information, "
        "you can also see cast, synopsis, and trailers of the movie.\nTo find a new movie, "
        "click on 'Pick a movie' and select the genre you're interested in. The bot will do the "
        "rest!\nWe hope you like it!"
    )
    await message.answer(start_message, reply_markup=menu)


@dp.message_handler(Text(equals="Find a movie"))
async def find_movie(message: types.Message):
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_search")
    )
    await dp.current_state(user=message.from_user.id).set_state(BotStates.FIND_MOVIE)
    await message.reply(
        "Please enter the name of the movie, or click the button to cancel the request.",
        reply_markup=keyboard,
    )


@dp.message_handler(state=BotStates.FIND_MOVIE)
async def choose_movie(message: types.Message):
    title = message.text
    results = imdb_parser.get_first_results(title)
    if len(results) == 0:
        await message.reply("No movies were found for this query.", reply_markup=menu)
    else:
        keyboard = types.InlineKeyboardMarkup(row_width=1)
        buttons = [
            types.InlineKeyboardButton(text=movie[0], callback_data="Movie_" + movie[1])
            for movie in results
        ]
        buttons.append(
            types.InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_search")
        )
        keyboard.add(*buttons)
        await message.reply(
            "Please choose which movie you are interested in.\nIf your movie is not on the list, "
            "please click Cancel and try searching again, specifying the title.",
            reply_markup=keyboard,
        )
    await dp.current_state(user=message.from_user.id).reset_state()


@dp.callback_query_handler(Text(startswith="Movie_"))
async def print_movie(call: types.CallbackQuery):
    movie_id = call.data[6:]
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    actions = ["Cast", "Synopsis", "Trailers"]
    buttons = [
        types.InlineKeyboardButton(text=action, callback_data=action + "_" + movie_id)
        for action in actions
    ]
    keyboard.add(*buttons)
    info = imdb_parser(movie_id)
    if len(info) <= 4096:
        await call.message.edit_text(info, reply_markup=keyboard)
    else:
        last_sent = await call.message.edit_text(info[:4096])
        for i in range(4096, len(info), 4096):
            if i + 4096 >= len(info):
                last_sent = await last_sent.reply(
                    info[i : i + 4096], reply_markup=keyboard
                )
            else:
                last_sent = await last_sent.reply(info[i : i + 4096])
    await call.answer()
    await call.message.answer("Select the desired function:", reply_markup=menu)


@dp.callback_query_handler(Text(startswith="Cast_"))
async def print_cast(call: types.CallbackQuery):
    movie_id = call.data[5:]
    await call.message.reply(imdb_parser.get_cast(movie_id))
    await call.answer()


@dp.callback_query_handler(Text(startswith="Synopsis_"))
async def synopsis_warning(call: types.CallbackQuery):
    movie_id = call.data[9:]
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton(
            text="☑️ Yes", callback_data="show_synopsis_" + movie_id
        )
    )
    keyboard.add(
        types.InlineKeyboardButton(text="❌ No", callback_data="cancel_synopsis")
    )
    await call.message.reply(
        f'{md.hbold("Spoilers! The synopsis below may give away important plot points.")}\nAre '
        f"you sure you want to see it?",
        reply_markup=keyboard,
    )
    await call.answer()


@dp.callback_query_handler(Text(startswith="show_synopsis_"))
async def show_synopsis(call: types.CallbackQuery):
    movie_id = call.data[14:]
    info = imdb_parser.get_synopsis(movie_id)
    if len(info) <= 4096:
        await call.message.edit_text(info)
    else:
        last_sent = await call.message.edit_text(info[:4096])
        for i in range(4096, len(info), 4096):
            last_sent = await last_sent.reply(info[i : i + 4096])
    await call.answer()


@dp.callback_query_handler(text="cancel_synopsis")
async def cancel_synopsis(call: types.CallbackQuery):
    try:
        await call.message.delete()
    except MessageToDeleteNotFound:
        await call.message.edit_text("OK! The synopsis won't be shown.")
    await call.answer()


@dp.callback_query_handler(Text(startswith="Trailers_"))
async def print_trailer(call: types.CallbackQuery):
    movie_id = call.data[9:]
    await call.message.reply(imdb_parser.get_trailers(movie_id))
    await call.answer()


@dp.message_handler(Text(equals="Pick a movie"))
async def choose_genre(message: types.Message):
    await message.reply(
        "Select the genre you are interested in by scrolling through the pages, or click Cancel to "
        "cancel your search.",
        reply_markup=pages[0],
    )


@dp.callback_query_handler(Text(startswith="genres_page_"))
async def change_page(call: types.CallbackQuery):
    await call.message.edit_reply_markup(pages[int(call.data[-1]) - 1])
    await call.answer()


@dp.callback_query_handler(Text(startswith="Genre_"))
async def pick_movie(call: types.CallbackQuery):
    genre = call.data[6:]
    movie_id = imdb_parser.get_random_by_genre(genre)
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    actions = ["Cast", "Synopsis", "Trailers"]
    buttons = [
        types.InlineKeyboardButton(text=action, callback_data=action + "_" + movie_id)
        for action in actions
    ]
    keyboard.add(*buttons)
    info = imdb_parser(movie_id)
    if len(info) <= 4096:
        await call.message.edit_text(info, reply_markup=keyboard)
    else:
        last_sent = await call.message.edit_text(info[:4096])
        for i in range(4096, len(info), 4096):
            if i + 4096 >= len(info):
                last_sent = await last_sent.reply(
                    info[i : i + 4096], reply_markup=keyboard
                )
            else:
                last_sent = await last_sent.reply(info[i : i + 4096])
    await call.answer()
    await call.message.answer("Select the desired function:", reply_markup=menu)


@dp.callback_query_handler(text="cancel_search")
@dp.callback_query_handler(state="*")
async def cancel_search(call: types.CallbackQuery):
    await dp.current_state(user=call.from_user.id).reset_state()
    message = "Select the desired function:"
    try:
        await call.message.delete()
        message = f'{md.hcode("Canceling...")}\n' + message
    except MessageToDeleteNotFound:
        await call.message.edit_text(f'{md.hcode("Canceling...")}')
    await call.message.answer(message, reply_markup=menu)
    await call.answer()


async def shutdown(dispatcher: Dispatcher):
    await dispatcher.storage.close()
    await dispatcher.storage.wait_closed()


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_shutdown=shutdown)
